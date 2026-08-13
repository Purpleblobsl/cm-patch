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


from .models import (
    ProductOrderEvent,
)
from .resolver import resolve
from .utils import http_code_to_string, logger_get
from .deserializer import cast_dataclass

log = logger_get(__name__)

type ResponseReturn = Tuple[str|Mapping[str, Any], int]
type EndpointFn = Callable[[], ResponseReturn]
type HttpMethod = Literal["get", "post"]

################################################################################

# Accumulate endpoints here before creating the Flask application.
endpoints: Dict[HttpMethod, Dict[str, EndpointFn]] = {}

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

################################################################################

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
@enpoint("/health", method="get")
def health() -> ResponseReturn:
    return {"status": "ok"}, 200

@enpoint("/tmf/event", method="post")
def tmf_event() -> ResponseReturn:
    data = request.get_json(silent=True)

    if data is None:
        log.warning("Received invalid JSON from TMF")
        return {"error": "invalid JSON"}, 400

    log.debug("TMF event:\n%s", json.dumps(data, indent=2))

    try:
        event = cast_dataclass(ProductOrderEvent, data, extra="ignore")

    except (TypeError, ValueError) as exc:
        log.warning("Invalid TMF event: %s", exc)
        return {"error": str(exc)}, 400

    log.debug("Deserialized TMF event:\n%s", event)

    if event.eventType != "ProductOrderStateChangeEvent":
        log.info("Catched '%s', skipping...", event.eventType)
        return "", 204

    if not event.event.productOrder.is_completed:
        log.info(
            "Catched '%s' but is not completed (%s), skipping...",
            event.eventType,
            event.event.productOrder.state,
        )
        return "", 204

    log.info("Catched '%s' and is completed, cooking...", event.eventType)

    # TODO: HERE:
    #
    # - [ ] spawn a subproccess
    # - [x] resolve org(s)
    # - [ ] dispatch to the configured contract-management(s)
    # - [ ] money

    orgs = resolve(event)
    log.debug("Resolved Orgs (%s):\n%s", len(orgs), orgs)

    return "", 204
