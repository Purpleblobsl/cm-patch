
from typing import (
    Iterable,
    List,
    Protocol,
    Sequence,
    Set,
    Tuple,
)

from src.deserializer import cast_dataclass

from .config import Config
from .request import Request, Response
from .utils import logger_get
from .models import (
    Order,
    ProductOrderEvent,
    ProductOrder,
    ProductOffering,
    ProductSpecification,
    Organization,
)

log = logger_get(__name__)

class HasId(Protocol):
    @property
    def id(self) -> str: ...

def resolve(
    event: ProductOrderEvent,
) -> Tuple[Sequence[Organization.ContractManagement], Order]:
    def get(url: str) -> Response:
        return Request(
            method="GET",
            url=url,
            headers={
                "Accept": "application/json",
            },
        ).fetch().raise_for_status()

    def unique_by_id[T: HasId](objs: Iterable[T]) -> List[T]:
        out: List[T] = []
        seen = set()
        for obj in objs:
            if obj.id not in seen:
                seen.add(obj.id)
                out.append(obj)
        return out

    def fetch_ids[T](obj_t: type[T], ids: Iterable[str]) -> List[T]:
        objs: List[T] = []

        for id in ids:
            response: Response = get(
                f"{Config.TMF_URL}{getattr(obj_t, "ENDPOINT")}/{id}"
            )

            objs.append(
                cast_dataclass(obj_t, response.data)
            )

        return objs

    if event.eventType != "ProductOrderStateChangeEvent":
        raise ValueError(f"Unexpected event type: {event.eventType}")

    order: ProductOrder = event.event.productOrder

    log.info("Fetching related consumer organizations to %s", order.id)
    consumers: List[Organization] = fetch_ids(
        Organization, order.get_consumers(),
    )

    assert consumers

    offering_ids: Set[str] = order.get_offerings()

    assert offering_ids

    log.info("Fetching related product offerings to %s", order.id)
    offerings: List[ProductOffering] = fetch_ids(
        ProductOffering, offering_ids,
    )

    specs_ids: Set[str] = {
        offering.productSpecification.id
        for offering in unique_by_id(offerings)
    }

    assert specs_ids

    log.info("Fetching related product specifications to %s", order.id)
    specs: List[ProductSpecification] = fetch_ids(
        ProductSpecification, specs_ids,
    )

    provider_ids: Set[str] = {
        spec.get_provider()
        for spec in unique_by_id(specs)
    }

    assert provider_ids

    log.info("Fetching related organizations to %s", order.id)
    providers = fetch_ids(
        Organization, provider_ids,
    )

    return [
        cm
        for org in providers
        if (cm := org.get_contrat_management_v2()) is not None
    ], Order(
        id=order.id,
        is_completed=order.is_completed,
        productSpecCharacteristic=[
            characteristic
            for spec in specs
            for characteristic in spec.productSpecCharacteristic
        ],
        consumers=[
            Order.Consumer(did=org.did)
            for org in consumers
        ]
    )
        
