
from typing import (
    Any,
    Dict,
    List,
    Sequence,
    Set,
)

from .config import Config
from .deserializer import cast_dataclass, to_json
from .jwt import get_oid4vp_access_token, issue_vc
from .models import CredentialsConfig, Order, Organization, PolicyConfig
from .request import Request, Response
from .utils import logger_get

log = logger_get(__name__)

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
        endpoint = Order.ENDPOINT_START
    else:
        log.info("Order is not completed, dispatching stop signals")
        endpoint = Order.ENDPOINT_STOP

    for cm in cms:
        log.info("Dispatching to %s", cm.address)

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

    log.debug("Order: %s", order)
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

    log.debug("Catched credentials: %s", creds)

    for consumer in order.consumers:
        try:
            res = _get(f"{url}/{consumer.did}", throw=False)
            log.debug(res)

            assert res.ok or res.not_found

        except Exception:
            log.exception("Failed to fetch til issuers")
            return

        if res.not_found:
            if create_or_patch:
                for cred in credentials:
                    _post(url, cred)

            continue

        credential = cast_dataclass(CredentialsConfig, res.data)

        log.debug("Credential for %s: %s", consumer.did, credential)

        credential = credential.filter_out(cred_types)

        if create_or_patch:
            credential.credentials.extend(creds)

        _delete(f"{url}/{consumer.did}")
        _post(f"{url}", credential)

