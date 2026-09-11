import re
from dataclasses import dataclass, field, replace
from typing import (
    Any,
    ClassVar,
    Container,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Set,
    dataclass_transform,
)

from .config import Config
from .utils import logger_get, unique_by_id

#-------------------------------------------------------------------------------

log = logger_get(__name__)

df_list = lambda: field(default_factory=list)
df_dict = lambda: field(default_factory=dict)

DID_RE = r"did:[^:]+:[^:]+"

@dataclass_transform(frozen_default=True, kw_only_default=True)
def obj(cls):
    return dataclass(
        frozen=True,
        slots=True,
        kw_only=True,
    )(cls)

#- events ----------------------------------------------------------------------

@obj
class ProductOrderEvent:

    @obj
    class Event:
        productOrder: ProductOrder

    eventId: str
    eventTime: str
    eventType: Literal[
        "ProductOrderCreateEvent",
        "ProductOrderStateChangeEvent",
        "ProductOrderDeleteEvent",
    ]
    event: Event

#- order -----------------------------------------------------------------------

@obj
class Order:

    ENDPOINT_START = "/order/start"
    ENDPOINT_STOP = "/order/stop"

    @obj
    class Customer:
        did: str

    id: str
    is_completed: bool
    credentialsConfigurations: List[
        ProductSpecification.ProductSpecCharacteristic
    ] = df_list()
    authorizationPolicies: List[
        ProductSpecification.ProductSpecCharacteristic
    ] = df_list()
    customers: List[Customer] = df_list()

@obj
class PolicyConfig:
    """ This model can't be used to deserialize, just pray and post """

    ENDPOINT = "/policy"

    policy: Dict[str, Any] = df_dict()

    @staticmethod
    def from_oder(order: Order) -> List[PolicyConfig]:
        policies = []
        default_id = f"{Config.HOLDER_DSC_URL}/policy/"

        for char in unique_by_id(order.authorizationPolicies):
            for policy in map(lambda v: v.value,
                              char.productSpecCharacteristicValue):
                id = policy.get("@id", default_id)
                policy["odrl:uid"] = policy["@id"] = f"{id}/{order.id}"

                policies.append(PolicyConfig(policy=policy))

        return policies

@obj
class CredentialsConfig:

    ENDPOINT = "/issuer"

    @obj
    class Credential:
        @obj
        class Claim:
            name: str
            path: str
            allowedValues: List[str] = df_list()

        credentialsType: str
        claims: List[Claim] = df_list()
        vaidFor: Dict[str, Any] = df_dict()

    did: str
    credentials: List[Credential] = df_list()

    def filter_out(self, credentialsTypes: Container[str]) -> CredentialsConfig:
        return replace(
            self,
            credentials=[
                cred
                for cred in self.credentials
                if cred.credentialsType not in credentialsTypes
            ],
        )

    @staticmethod
    def from_oder(order: Order) -> List[CredentialsConfig]:
        configs = []
        for char in unique_by_id(order.credentialsConfigurations):
            credentials = [ # TODO: validate this
                CredentialsConfig.Credential(**cred.value)
                for cred in char.productSpecCharacteristicValue
            ]

            configs.extend(
                CredentialsConfig(
                    did=org.did,
                    credentials=credentials,
                )
                for org in set(order.customers)
            )

        return configs

#- tmf models ------------------------------------------------------------------

@obj
class ProductOrder:

    ENDPOINT: ClassVar[str] = (
        "/tmf-api/productOrderingManagement/v4/productOrder"
    )

    @obj
    class ProductOrderItem:
        @obj
        class ProductOffering:
            id: str

        @obj
        class Product:
            @obj
            class RelatedParty:
                id: str
                role: Literal[
                    "seller",
                    "customer",
                ]

            productCharacteristic: List[Any] = df_list()
            relatedParty: List[RelatedParty] = df_list()

        id: str
        action: str
        productOffering: ProductOffering

    @obj
    class RelatedParty:
        id: str
        name: str
        role: Literal[
            "seller",
            "customer",
        ]

    id: str
    href: str
    orderDate: str
    productOrderItem: List[ProductOrderItem] = df_list()
    relatedParty: List[RelatedParty] = df_list()
    state: Literal[
        "acknowledged",
        "rejected",
        "pending",
        "held",
        "inProgress",
        "cancelled",
        "completed",
        "failed",
        "partial",
        "assessingCancellation",
        "pendingCancellation",
    ]

    @property
    def is_completed(self) -> bool:
        return self.state == "completed"

    def get_customers(self) -> Set[str]:
        return {
            party.id
            for party in self.relatedParty
            if party.role == "customer"
        }

    def get_sellers(self) -> Set[str]:
        return {
            party.id
            for party in self.relatedParty
            if party.role == "seller"
        }

    def get_offerings(self) -> Set[str]:
        return {
            item.productOffering.id
            for item in self.productOrderItem
        }

@obj
class ProductOffering:

    ENDPOINT: ClassVar[str] = (
        "/tmf-api/productCatalogManagement/v4/productOffering"
    )

    @obj
    class ProductSpecification:
        id: str

    # @obj
    # class BlundledOffering:
    #     id: str

    id: str
    name: str
    productSpecification: ProductSpecification
    # bundledProductOffering: List[BlundledOffering] = df_list()

@obj
class ProductSpecification:

    ENDPOINT: ClassVar[str] = (
        "/tmf-api/productCatalogManagement/v4/productSpecification"
    )

    @obj
    class ProductSpecCharacteristic:
        @obj
        class Value:
            isDefault: bool = True
            value: Dict[str, Any] = df_dict()

        id: str
        name: str
        valueType: str
        productSpecCharacteristicValue: List[Value]

    @obj
    class RelatedParty:
        id: str
        role: str

    id: str
    name: str
    productSpecCharacteristic: List[ProductSpecCharacteristic] = df_list()
    relatedParty: List[RelatedParty] = df_list()

    def get_sellers(self) -> Set[str]:
        return {
            party.id
            for party in self.relatedParty
            if party.role == "seller"
        }

    def get_credential_configs(self) -> List[ProductSpecCharacteristic]:
        return unique_by_id(
            char
            for char in self.productSpecCharacteristic
            if char.valueType == "credentialsConfiguration"
        )

    def get_authorization_policy(self) -> List[ProductSpecCharacteristic]:
        return unique_by_id(
            char
            for char in self.productSpecCharacteristic
            if char.valueType == "authorizationPolicy"
        )

@obj
class Organization:

    ENDPOINT: ClassVar[str] = (
        "/tmf-api/party/v4/organization"
    )

    @obj
    class PartyCharacteristic:
        name: str
        value: Any

    @obj
    class CmPatch:
        address: str
        clientId: str # Note: this is not used...
        scope: str

    id: str
    name: Optional[str] = None
    tradingName: Optional[str] = None
    externalReference: List[Dict[str, Any]] = df_list()
    partyCharacteristic: List[PartyCharacteristic] = df_list()

    def get_did(self) -> Optional[str]:
        for i, ref in enumerate(self.externalReference):
            if ref.get("externalReferenceType") != "idm_id": continue

            name = ref.get("name")
            if isinstance(name, str) and re.fullmatch(DID_RE, name):
                return name

            log.warn(
                "Invalid reference 'idm_id' ([%d]=%s) configured in: %s",
                i,
                ref,
                self.id,
            )

        for i, char in enumerate(self.partyCharacteristic):
            if char.name != "did": continue

            name = char.value
            if isinstance(name, str) and re.fullmatch(DID_RE, name):
                return name

            log.warn(
                "Invalid characteristic 'did' ([%d]=%s) configured in: %s",
                i,
                char.value,
                self.id,
            )

        return None

    def get_cm_patch(self) -> Optional[CmPatch]:
        def log_fail(i: int, char: Organization.PartyCharacteristic):
            log.warn(
                "Invalid characteristic 'cmPatch' ([%d]=%s) configured in: %s",
                i,
                char.value,
                self.id,
            )

        for i, char in enumerate(self.partyCharacteristic):
            if char.name != "cmPatch": continue

            if not isinstance(char.value, Dict):
                log_fail(i, char)
                continue

            try:
                return self.CmPatch(
                    address=char.value["address"],
                    clientId=char.value["clientId"],
                    scope=char.value["scope"],
                )

            except (TypeError, KeyError):
                log_fail(i, char)

        return None

