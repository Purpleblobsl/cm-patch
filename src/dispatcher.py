
from typing import (
    Any,
    Dict,
    List,
    Sequence,
    Set,
)

from .deserializer import to_json, try_cast
from .models import Order, Organization, PolicyConfig
from .request import Response, Request
from .utils import logger_get
from .jwt import issue_vc, get_oid4vp_access_token
from .config import Config


log = logger_get(__name__)

def _post(
    url: str,
    data: Any,
    headers: Dict[str,str]|None = None,
) -> Response:
    return Request(
        method="POST",
        url=url,
        headers=headers if headers is not None else {},
        data=to_json(data),
        json=True,
    ).fetch().raise_for_status()

def _get(
    url: str,
    headers: Dict[str,str]|None = None,
) -> Response:
    headers = headers or {}
    headers["Accept"] = "application/json"

    return Request(
        method="GET",
        url=url,
        headers=headers,
    ).fetch().raise_for_status()

def _delete(
    url: str,
    headers: Dict[str,str]|None = None,
) -> Response:
    headers = headers or {}

    return Request(
        method="DELETE",
        url=url,
        headers=headers,
    ).fetch().raise_for_status()

def dispatch_cm_patch(
    order: Order,
    cms: Sequence[Organization.ContractManagement],
):
    def post(url: str, token: str) -> Response:
        return _post(
            url,
            order,
            headers={ "Authorization": f"Bearer {token}" },
        )

    scope_to_vc: Dict[str, str] = {
        cm.scope: issue_vc(credential_id=t[0], format=t[1])
        for cm in cms
        if (t := Config.vc_scope_map(cm.scope)) is not None
    }

    if order.is_completed:
        log.info("Order is completed, dispatching start signals")
        endpoint = "/order/start"
    else:
        log.info("Order is not completed, dispatching stop signals")
        endpoint = "/order/end"

    for cm in cms:
        log.info("Dispatching to %", cm.address)

        url = f"{cm.address}{endpoint}"
        vc = scope_to_vc.get(cm.scope)
        if vc is None:
            log.error("Unknown scope '%s', skipping...")
            continue

        try:
            jwt = get_oid4vp_access_token(
                target_url=cm.address,
                did=Config.HOLDER_DID,
                verifiable_credential=vc,
                key_path=Config.holder_key_path,
                scope=cm.scope,
            )

        except Exception:
            log.exception("Failed to issue the JWT, skipping...")
            continue

        try:
            post(url, jwt)

        except Exception:
            log.exception("Failed to post")
            continue

def dispatch_pap(
    order: Order,
    create_or_patch: bool,
):
    policies: List[PolicyConfig] = PolicyConfig.from_oder(order)
    p_ids: Set[str] = {
        policy.policy["@id"]
        for policy in policies
    }

    url = f"{Config.HOLDER_PAP_URL}/{PolicyConfig.ENDPOINT}"

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
): ... # TODO
