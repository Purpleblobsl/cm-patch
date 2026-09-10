from typing import (
    Any,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from .config import Config
from .deserializer import cast_dataclass
from .models import (
    Order,
    ProductOrderEvent,
    ProductOrder,
    ProductOffering,
    ProductSpecification,
    Organization,
)
from .request import Request, Response
from .utils import HasId, logger_get, unique_by_id

# ------------------------------------------------------------------------------

log = logger_get(__name__)

# ------------------------------------------------------------------------------

def resolve(
    event: ProductOrderEvent,
) -> Tuple[List[Organization.CmPatch], Optional[Order]]:
    if event.eventType != "ProductOrderStateChangeEvent":
        raise ValueError(f"Unexpected event type: {event.eventType}")

    def get(url: str) -> Response:
        return Request(
            method="GET",
            url=url,
            headers={
                "Accept": "application/json",
            },
        ).fetch().raise_for_status()

    def fetch_ids[T: HasId](obj_t: type[T], ids: Iterable[str]) -> List[T]:
        objs: List[T] = []
        endpoint = f"{Config.TMF_URL}{getattr(obj_t, "ENDPOINT")}"

        log.debug(
            "Fetching to endpoint '%s' ids %s related to order: %s",
            endpoint,
            ids,
            order.id,
        )

        return [
            cast_dataclass(obj_t, get(f"{endpoint}/{id}").data)
            for id in ids
        ]

    def fetch[T: HasId](
        obj_t: type[T],
        ids: Iterable[str],
        resources: str,
    ) -> List[T]:
        if not ids:
            log.warning("No %s related to %s", resources, order.id)
            return []

        log.info("Fetching related %s to %s", resources, order.id)
        objs: List[T] = unique_by_id(fetch_ids(
            obj_t, ids,
        ))

        if not objs:
            log.warning("No %s related to %s", resources, order.id)
            return []

        log.debug("Deserialized %s:\n%s", resources, objs)

        return objs

    # Resource relation paths:
    #   event.relatedParty[] | (.role?) | .id
    #     -> customers: organization
    #     -> sellers: organization
    #
    #   event.productOrder.productOrderItem[].id
    #     -> product-offering.productSpecification.id
    #     -> product-specification


    order: ProductOrder = event.event.productOrder
    sellers_ids: Set[str] = order.get_sellers()

    # TODO: we don't handle bundledProductOffering...
    offerings: List[ProductOffering] = fetch(
        ProductOffering,
        order.get_offerings(),
        "offerings",
    )

    if not offerings: return [], None

    specs: List[ProductSpecification] = fetch(
        ProductSpecification,
        {
            offering.productSpecification.id
            for offering in offerings
        },
        "specifications",
    )

    if not specs: return [], None

    # Note: maybe this is not necessary...
    sellers_ids.update(
        seller
        for spec in specs
        for seller in spec.get_sellers()
    )

    sellers: List[Organization] = fetch(
        Organization,
        sellers_ids,
        "seller organizations",
    )

    if not sellers: return [], None

    customers: List[Organization] = fetch(
        Organization,
        order.get_customers(),
        "customer organizations",
    )

    return list({
        cm
        for seller in sellers
        if (cm := seller.get_cm_patch()) is not None
    }), Order(
        id=order.id,
        is_completed=order.is_completed,
        authorizationPolicies=unique_by_id(
            ap
            for spec in specs
            for ap in spec.get_authorization_policy()
        ),
        credentialsConfigurations=unique_by_id(
            cc
            for spec in specs
            for cc in spec.get_credential_configs()
        ),
        customers=list({
            Order.Customer(did=did)
            for customer in customers
            if (did := customer.get_did()) is not None
        })
    )
        
