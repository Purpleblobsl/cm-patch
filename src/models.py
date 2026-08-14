from dataclasses import dataclass, field
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    dataclass_transform,
)

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

    @obj
    class Consumer:
        did: str

    id: str
    is_completed: bool
    productSpecCharacteristic: List[Dict[str,Any]] = field(default_factory=list)
    consumers: List[Consumer] = field(default_factory=list)

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
    productOrderItem: List[ProductOrderItem] = field(default_factory=list)
    relatedParty: List[RelatedParty] = field(default_factory=list)
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
    productSpecCharacteristic: List[Dict[str,Any]] = field(default_factory=list)
    relatedParty: List[RelatedParty] = field(default_factory=list)

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
    externalReference: List[Dict[str, Any]] = field(default_factory=list)
    partyCharacteristic: List[PartyCharacteristic] = field(default_factory=list)

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
