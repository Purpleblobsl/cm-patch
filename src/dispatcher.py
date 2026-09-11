from typing import (
    Any,
    Dict,
    List,
    Sequence,
    Set,
    Tuple,
)

from .config import Config
from .deserializer import cast_dataclass, to_json
from .jwt import get_oid4vp_access_token, issue_vc
from .models import CredentialsConfig, Order, Organization, PolicyConfig
from .request import Request, Response
from .utils import logger_get

#-------------------------------------------------------------------------------

log = logger_get(__name__)

subscriptions: Dict[str, Tuple[str, ...]] = { # { api: (events...) }
    "productOrderingManagement": (
        "ProductOrderStateChangeEvent",
        # Note: for some reason the tmf-api doesn't emit the delete event...
        "ProductOrderDeleteEvent",
    ),
}

def _post(
    url: str,
    data: Any,
    headers: Dict[str,str]|None = None,
) -> Response:
    headers = dict(headers or {})
    return Request(
        method="POST",
        url=url,
        headers=headers,
        data=to_json(data),
        json=True,
    ).fetch().raise_for_status()

def _get(
    url: str,
    headers: Dict[str,str]|None = None,
    *,
    throw: bool = True,
) -> Response:
    headers = dict(headers or {})
    headers["Accept"] = "application/json"

    res = Request(
        method="GET",
        url=url,
        headers=headers,
    ).fetch()

    if throw:
        res.raise_for_status()

    return res

def _delete(
    url: str,
    headers: Dict[str,str]|None = None,
) -> Response:
    headers = dict(headers or {})

    return Request(
        method="DELETE",
        url=url,
        headers=headers,
    ).fetch().raise_for_status()

#- dispatch --------------------------------------------------------------------

def dispatch_cm_patch(
    order: Order,
    cms: Sequence[Organization.CmPatch],
):
    def post(url: str, token: str) -> Response:
        return _post(
            url,
            order,
            headers={ "Authorization": f"Bearer {token}" },
        )

    if order.is_completed:
        log.info("Order is completed, dispatching start signals")
        endpoint = Order.ENDPOINT_START

    else:
        log.info("Order is not completed, dispatching stop signals")
        endpoint = Order.ENDPOINT_STOP

    log.info("Issuing VCs...")
    scope_to_vc: Dict[str, str] = {
        cm.scope: issue_vc(credential_id=t[0], format=t[1])
        for cm in cms
        if (t := Config.vc_scope_map(cm.scope)) is not None
    }
    log.debug("Issued VCs map: %s", scope_to_vc)

    for cm in cms:
        log.info("Dispatching to %s", cm.address)

        url = f"{cm.address}{endpoint}"
        vc = scope_to_vc.get(cm.scope)
        if vc is None:
            log.error("Unknown scope '%s', skipping...", cm.scope)
            continue

        try:
            jwt = get_oid4vp_access_token(
                target_url=cm.address,
                did=Config.HOLDER_DID,
                verifiable_credential=vc,
                key_path=Config.holder_key_path,
                scope=cm.scope,
            )

        except Exception: # TODO: improve the catch
            log.exception("Failed to issue the JWT, skipping...")
            continue

        if jwt is None: continue

        try:
            post(url, jwt)

        except Exception: # TODO: improve the catch
            log.exception("Failed to post")
            continue

def dispatch_pap(
    order: Order,
    create_or_patch: bool,
):
    policies: List[PolicyConfig] = PolicyConfig.from_oder(order)

    if not policies:
        log.info("No credentials configured, skipping...")
        return

    p_ids: Set[str] = {
        policy.policy["@id"]
        for policy in policies
    }

    url = f"{Config.HOLDER_PAP_URL}{PolicyConfig.ENDPOINT}"

    pap_ids: List[Dict[str, Any]] = [
        d["id"]
        for d in _get(url).data
        if d["odrl:uid"] in p_ids
    ]

    log.info("Deleting matching policies")
    for id in pap_ids:
        _delete(f"{url}/{id}")

    if not create_or_patch: return

    log.info("Uploading policies")
    for policy in policies:
        _post(url, policy.policy)

def dispatch_til(
    order: Order,
    create_or_patch: bool,
):
    url = f"{Config.HOLDER_TIL_URL}{CredentialsConfig.ENDPOINT}"

    credentials: List[CredentialsConfig] = CredentialsConfig.from_oder(order)

    if not credentials:
        log.info("No credentials configured, skipping...")
        return

    creds: List[CredentialsConfig.Credential] = []
    cred_types: Set[str] = set()

    for cred in credentials:
        for c in cred.credentials:
            if c.credentialsType in cred_types:
                log.warning("Duplicated credentialsType %s, skipping...",
                            c.credentialsType)
                continue

            cred_types.add(c.credentialsType)
            creds.append(c)
    # creds: List[CredentialsConfig.Credential] = [
    #     c
    #     for cred in credentials
    #     for c in cred.credentials
    # ]
    # cred_types: Set[str] = {
    #     cred.credentialsType
    #     for cred in creds
    # }

    log.debug("Catched credentials: %s", creds)

    for customer in order.customers:
        log.info("Updating credential for: %s", customer.did)

        try:
            res = _get(f"{url}/{customer.did}", throw=False)
            log.debug(res)

        except Exception: # TODO: improve the catch
            log.exception("Failed to fetch til issuers: %s", customer.did)
            return


        if res.ok or res.not_found:
            log.error("Failed to fetch til issuers: %s", customer.did)
            return

        if res.not_found:
            if create_or_patch:
                for cred in credentials:
                    _post(url, cred)

            continue

        credential = cast_dataclass(CredentialsConfig, res.data)
        log.debug("Credential for %s: %s", customer.did, credential)

        credential = credential.filter_out(cred_types)

        if create_or_patch:
            credential.credentials.extend(creds)

        log.info("Updated credential: %s", credential)

        _delete(f"{url}/{customer.did}")
        _post(f"{url}", credential)

def dispatch_tmf_subscription():
    if not Config.TMF_SUBCRIBE: return

    log.info("Subscribing to the tmf-api: %s", Config.TMF_URL)

    callback = f"{Config.app_url}{Order.ENDPOINT_LISTEN}"

    for url, event in (
        (f"{Config.TMF_URL}/tmf-api/{api}/v4/hub", event)
        for api, events in subscriptions.items()
        for event in events
    ):
        payload = {
            "callback": callback,
            "query": f"eventType={event}",
        }

        log.info("Subscribing to %s", event)

        try:
            res: Response = Request(
                method="POST",
                url=url,
                data=to_json(payload),
                json=True,
            ).fetch()

        except Exception:
            log.exception(
                "Failed to post subscription: %s - %s",
                url,
                event,
            )
            continue

        if res.ok:
            log.info(
                "Succesfully subscribed to %s",
                event,
            )

        elif res.not_found:
            log.error(
                "tmf-api not found: %s",
                Config.TMF_URL,
            )

        elif res.status == 409:
            log.warn(
                "There is already a subscription for the same event: %s",
                event,
            )

        else:
            log.error(
                "Failed to post subscription: %d - %s",
                res.status,
                res.data,
            )

