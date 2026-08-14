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

from src.config import Config

df_list = lambda: field(default_factory=list)
df_dict = lambda: field(default_factory=dict)

################################################################################

@dataclass_transform(frozen_default=True, kw_only_default=True)
def obj(cls):
    return dataclass(
        frozen=True,
        slots=True,
        kw_only=True,
    )(cls)

## events ######################################################################

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

## order #######################################################################

@obj
class Order:

    ENDPOINT_START = "/order/start"
    ENDPOINT_STOP = "/order/stop"

    @obj
    class Consumer:
        did: str

    @obj
    class ProductSpecCharacteristic:
        @obj
        class Value:
            isDefault: bool = True
            value: Dict[str, Any] = df_dict()

        id: str
        name: str
        valueType: str
        productSpecCharacteristicValue: List[Value] = df_list()

    id: str
    is_completed: bool
    productSpecCharacteristic: List[ProductSpecCharacteristic] = df_list()
    consumers: List[Consumer] = df_list()

@obj
class PolicyConfig:
    """ This model can't be used to deserialize, just pray and post """

    ENDPOINT = "/policy"

    policy: Dict[str, Any] = df_dict()

    @staticmethod
    def from_oder(order: Order) -> List[PolicyConfig]:
        policies = []
        default_id = f"{Config.HOLDER_DSC_URL}/policy/"
        for char in order.productSpecCharacteristic:
            if char.valueType == "authorizationPolicy":
                for policy in map(lambda v: v.value,
                                  char.productSpecCharacteristicValue):
                    id = policy.get("@id", default_id)
                    policy["odrl:uid"] = policy["@id"] = f"{id}/{order.id}"
                    policies.append(policy)

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
        for char in order.productSpecCharacteristic:
            if char.valueType == "credentialsConfiguration":
                credentials = [
                    CredentialsConfig.Credential(**cred.value)
                    for cred in char.productSpecCharacteristicValue
                ]

                configs.extend(
                    CredentialsConfig(
                        did=org.did,
                        credentials=credentials,
                    )
                    for org in order.consumers
                )

        return configs

## resources ###################################################################

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

        id: str
        action: str
        productOffering: ProductOffering

    @obj
    class RelatedParty:
        id: str

    id: str
    href: str
    orderDate: str
    productOrderItem: List[ProductOrderItem] = df_list()
    relatedParty: List[RelatedParty] = df_list()
    state: Optional[str] = None

    def get_consumers(self) -> Set[str]:
        return {
            party.id
            for party in self.relatedParty
        }

    def get_offerings(self) -> Set[str]:
        return {
            item.productOffering.id
            for item in self.productOrderItem
        }

    @property
    def is_completed(self) -> bool:
        return self.state == "completed"

@obj
class ProductOffering:

    ENDPOINT: ClassVar[str] = (
        "/tmf-api/productCatalogManagement/v4/productOffering"
    )

    @obj
    class ProductSpecification:
        id: str

    id: str
    href: str
    lastUpdate: str
    lifecycleStatus: str
    name: str
    version: str
    productSpecification: ProductSpecification

@obj
class ProductSpecification:

    ENDPOINT: ClassVar[str] = (
        "/tmf-api/productCatalogManagement/v4/productSpecification"
    )

    @obj
    class RelatedParty:
        id: str
        role: str
        # @referredType: null

    id: str
    href: str
    brand: str
    lastUpdate: str
    lifecycleStatus: str
    name: str
    version: str
    productSpecCharacteristic: List[Dict[str,Any]] = df_list()
    relatedParty: List[RelatedParty] = df_list()

    def get_provider(self) -> str:
        for party in self.relatedParty:
            if party.role == "provider":
                return party.id

        raise ValueError(
            "Invalid product-specification: has no provider organization"
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
    class ContractManagement:
        address: str
        clientId: str
        scope: str

    id: str
    href: str
    name: Optional[str] = None
    tradingName: Optional[str] = None
    externalReference: List[Dict[str, Any]] = df_list()
    partyCharacteristic: List[PartyCharacteristic] = df_list()

    @property
    def did(self) -> str:
        for char in self.partyCharacteristic:
            if char.name == "did":
                return char.value

        for ref in self.externalReference:
            if ref.get("name") == "did":
                return ref["value"]

        raise ValueError("Invalid organization: has no did reference")

    def get_contrat_management(self) -> Optional[ContractManagement]:
        for char in self.partyCharacteristic:
            if char.name == "contractManagement":
                assert(isinstance(char.value, Dict))
                return self.ContractManagement(
                    address=char.value["address"],
                    clientId=char.value["clientId"],
                    scope=char.value["scope"],
                )

        return None

    def get_contrat_management_v2(self) -> Optional[ContractManagement]:
        for char in self.partyCharacteristic:
            if char.name == "contractManagementV2":
                assert(isinstance(char.value, Dict))
                return self.ContractManagement(
                    address=char.value["address"],
                    clientId=char.value["clientId"],
                    scope=char.value["scope"],
                )

        return None

