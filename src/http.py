import json
from functools import wraps
from typing import(
    Any,
    Callable,
    Dict,
    Tuple,
    Literal,
    Mapping,
)

from flask import Flask, request

from .config import Config
from .deserializer import cast_dataclass
from .dispatcher import dispatch_cm_patch, dispatch_pap, dispatch_til
from .models import (
    Order,
    ProductOrderEvent,
)
from .resolver import resolve
from .utils import http_code_to_string, logger_get

#-------------------------------------------------------------------------------

type ResponseReturn = Tuple[str|Mapping[str, Any], int]
type EndpointFn = Callable[[], ResponseReturn]
type HttpMethod = Literal["get", "post"]

log = logger_get(__name__)

# Accumulate endpoints here before creating the Flask application.
endpoints: Dict[HttpMethod, Dict[str, EndpointFn]] = {}

def enpoint(path: str, method: HttpMethod):

    def handler(
        method: HttpMethod,
        path: str,
        fn: EndpointFn,
    ) -> EndpointFn:

        @wraps(fn)
        def enpoint() -> ResponseReturn:
            response: ResponseReturn = fn()
            log.debug(
                "%s %s - %s %s\ndata=%s",
                method.upper(), path,
                response[1], http_code_to_string(response[1]),
                json.dumps(response[0], indent=2)
            )
            return response

        return enpoint

    paths = endpoints.setdefault(method, {})

    if path in paths:
        print(endpoints)
        raise ValueError(
            f"Multiple handlers for the same endpoint ({method.upper()} {path})"
        )

    def register(fn: EndpointFn) -> EndpointFn:
        log.debug(
            "Endpoint registered: %s %s -> %s",
            method.upper(), path, fn.__name__,
        )
        fn = handler(method, path, fn)
        paths[path] = fn
        return fn

    return register

#- server ----------------------------------------------------------------------

def create_server(name: str) -> Flask:
    app = Flask(name)

    for method, paths in endpoints.items():
        register = getattr(app, method)

        for path, fn in paths.items():
            register(
                path,
                strict_slashes=False
            )(fn)

    return app

#- enpoints --------------------------------------------------------------------

@enpoint("/health", method="get")
def health() -> ResponseReturn:
    return {"status": "ok"}, 200

@enpoint(Order.ENDPOINT_LISTEN, method="post")
def tmf_event() -> ResponseReturn:
    if Config.APP_IS_CLIENT:
        log.warning("Service is a client, can't handle events")
        return {"error": "Service is a client, can't handle events"}, 409

    data = request.get_json(silent=True)

    if data is None:
        log.error("Received invalid JSON from TMF")
        return {"error": "invalid JSON"}, 400

    log.debug("TMF event:\n%s", json.dumps(data, indent=2))

    try:
        event = cast_dataclass(ProductOrderEvent, data, extra="ignore")

    except (TypeError, ValueError) as exc:
        log.exception("Invalid TMF product order event")
        return {"error": "Invalid TMF product order event"}, 400

    log.info("Catched %s: %s...", event.eventType, event.eventId)

    if event.eventType == "ProductOrderCreateEvent":
        log.info(
            "Event %s is not a 'ProductOrderStateChangeEvent' or "
            "'ProductOrderDeleteEvent', skipping...",
            event.eventId,
        )
        return "", 204

    cms, order = resolve(event)

    if order is None:
        log.error("No order was generated from event, skipping...")
        return "", 404

    if not order.customers:
        log.error(
            "No customers related to %s, skipping...",
            event.eventId,
        )
        return "", 404

    if not cms:
        log.info(
            "No cm-patch configured in related sellers to %s, skipping...",
            event.eventId,
        )
        return "", 204

    if not order.credentialsConfigurations and not order.authorizationPolicies:
        log.info(
            "No credentials configurations or authorization policies "
            "configured in related product specifications to %s, skipping...",
            event.eventId,
        )
        return "", 204

    log.debug(
        "Resolved seller organizations (%s) linked to the order:\n%s",
        len(cms),
        order,
    )

    try:
        dispatch_cm_patch(order, cms)
    except Exception:
        log.exception("Failed to dispatch order")

    return "", 204

@enpoint(Order.ENDPOINT_START, method="post")
def order_start() -> ResponseReturn:
    return order_handle(start=True)

@enpoint(Order.ENDPOINT_STOP, method="post")
def order_end() -> ResponseReturn:
    return order_handle(start=False)

def order_handle(start: bool) -> ResponseReturn:
    data = request.get_json(silent=True)

    if data is None:
        log.error("Received invalid JSON")
        return {"error": "invalid JSON"}, 400

    log.debug("Order json dump:\n%s", json.dumps(data, indent=2))

    try:
        order = cast_dataclass(Order, data, extra="ignore")

    except (TypeError, ValueError) as exc:
        log.error("Invalid Order: %s", exc)
        return {"error": str(exc)}, 400

    log.debug("Deserialized Order:\n%s", order)

    if not order.customers:
        log.info("No customers configured, skipping...")
        return "", 204

    try:
        dispatch_til(order, create_or_patch=start)
        dispatch_pap(order, create_or_patch=start)

    except Exception as exc:
        log.exception("Failed to dispatch: %s")
        return {"error": str(exc)}, 400

    return "", 204

