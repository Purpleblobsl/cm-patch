import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .config import config
from .request import Request, Response
from .utils import base64url_encode, logger_get

log = logger_get(__name__)

PRE_AUTHORIZED_CODE = (
    "urn:ietf:params:oauth:grant-type:pre-authorized_code"
)

################################################################################

@dataclass(frozen=True, slots=True)
class CachedCredential:
    credential: str
    expires_at: datetime

    @property
    def expired(self) -> bool:
        return self.expires_at <= (
            datetime.now(timezone.utc) + VCCache.SAFETY_MARGIN
        )

class VCCache:
    SAFETY_MARGIN = timedelta(minutes=2)
    _creds: Dict[str, CachedCredential] = {}

    @classmethod
    def get(cls, credential_id: str) -> Optional[str]:
        cred = cls._creds.get(credential_id)

        if cred is None:
            return None

        if not cred.expired:
            return cred.credential

        cls._creds.pop(credential_id, None)

        return None

    @classmethod
    def put(
        cls,
        credential_id: str,
        credential: str,
        expires_at: datetime,
    ):
        cls._creds[credential_id] = CachedCredential(
            credential=credential,
            expires_at=expires_at,
        )

################################################################################

def get_access_token() -> str:
    response: Response = Request(
        method="POST",
        url=config.token_url,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "password",
            "client_id": config.KC_CLIENT_ID,
            "username": config.KC_USER,
            "scope": config.KC_SCOPE,
            "password": config.KC_PASS,
        },
        json=False,
    ).fetch().raise_for_status()

    try:
        return response.data["access_token"]
    except KeyError:
        raise RuntimeError("Keycloak response did not contain 'access_token'")

def get_offer_uri(
    credential_id: str,
    access_token: str,
) -> str:
    response = Request(
        method="GET",
        url=f"{config.oid4vc_url}/credential-offer-uri",
        params={
            "credential_configuration_id": credential_id,
        },
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    ).fetch().raise_for_status()

    try:
        return f"{response.data['issuer']}{response.data['nonce']}"

    except KeyError:
        raise RuntimeError(
            "Credential offer response did not contain 'issuer'/'nonce'"
        )

def get_pre_authorized_code(
    offer_uri: str,
    access_token: str,
) -> str:
    response: Response = Request(
        method="GET",
        url=offer_uri,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    ).fetch().raise_for_status()

    try:
        return (
            response.data["grants"]
            [PRE_AUTHORIZED_CODE]
            ["pre-authorized_code"]
        )

    except KeyError:
        raise RuntimeError(
            "Credential offer did not contain 'pre-authorized_code'"
        )

def get_credential_access_token(
    code: str,
) -> str:
    response: Response = Request(
        method="POST",
        url=config.token_url,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": PRE_AUTHORIZED_CODE,
            "pre-authorized_code": code,
        },
        json=False,
    ).fetch().raise_for_status()

    try:
        return response.data["access_token"]
    except KeyError:
        raise RuntimeError(
            "Token response did not contain 'access_token'"
        )

def get_credential(
    credential_id: str,
    format: str,
    access_token: str,
) -> Tuple[str, datetime]:
    response: Response = Request(
        method="POST",
        url=f"{config.oid4vc_url}/credential",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        data={
            "credential_identifier": credential_id,
            "format": format,
        },
        json=True,
    ).fetch().raise_for_status()

    try:
        return response.data["credential"], datetime.now()
    except KeyError:
        raise RuntimeError(
            "Credential response did not contain 'credential'"
        )

def check_credential_format(
    credential_id: str,
    format: str,
):
    response: Response = Request(
        method="GET",
        url= f"{config.kc_url}/.well-known/openid-credential-issuer",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        json=True
    ).fetch().raise_for_status()

    configurations = (
        response.data
        ["credential_configurations_supported"]
    )

    try:
        conf_format = configurations[credential_id]["format"]

    except KeyError:
        raise RuntimeError(
            f"Credential configuration '{credential_id}' not found"
        )

    if conf_format != format:
        raise RuntimeError(
            f"Configured credential format don't match for '{credential_id}' "
            f"({format} != {conf_format})"
        )

def issue_vc(
    credential_id: str,
    format: str
) -> str:
    log.info("Issuing VC '%s'", credential_id)

    cred = VCCache.get(credential_id)

    if cred is not None:
        log.debug("CHACE VC: %s", credential_id, cred)
        return cred

    log.debug("Gnerating VC", credential_id)

    log.info("Checking credential format")
    check_credential_format(credential_id, format)

    log.info("Getting access token")
    access_token: str = get_access_token()
    log.debug("Access token: %s", access_token)

    log.info("Getting offer uri")
    offer_uri: str = get_offer_uri(credential_id, access_token)
    log.debug("Offer URI: %s", offer_uri)

    log.info("Getting pre authorized code")
    code: str = get_pre_authorized_code(offer_uri, access_token)
    log.debug("Pre-authorized code: %s", code)

    log.info("Getting credential access token")
    credential_access_token: str = get_credential_access_token(code)
    log.debug("Credential access token: %s", credential_access_token)

    log.info("Getting credential")
    vc, expires_at = get_credential(credential_id,
                                    format,
                                    credential_access_token)
    log.debug("VC: %s", vc)

    VCCache.put(
        credential_id,
        vc,
        expires_at=expires_at,
    )

    return vc

def get_token_endpoint(target_url: str) -> str:
    response: Response = Request(
        method="GET",
        url=f"{target_url}/.well-known/openid-configuration",
        headers={
            "Accept": "application/json",
        },
    ).fetch().raise_for_status()

    try:
        return response.data["token_endpoint"]

    except KeyError:
        raise RuntimeError(
            "OpenID configuration did not contain 'token_endpoint'"
        )

def sign_jwt(
    did: str,
    verifiable_credential: str,
    key_path: str,
) -> str:
    header: Dict[str, str] = {
        "alg": "ES256",
        "typ": "JWT",
        "kid": did,
    }

    payload: Dict[str, Any] = {
        "iss": did,
        "sub": did,
        "vp": {
            "@context": [ "https://www.w3.org/2018/credentials/v1" ],
            "type": [ "VerifiablePresentation" ],
            "verifiableCredential": [ verifiable_credential ],
            "holder": did,
        },
    }

    header_b64 = base64url_encode(
        json.dumps(
            header,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    payload_b64 = base64url_encode(
        json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    signing_input = f"{header_b64}.{payload_b64}"

    with open(key_path, "rb") as file:
        private_key = serialization.load_pem_private_key(
            file.read(),
            password=None,
        )

    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise TypeError("Private key is not an EC private key")

    if not isinstance(private_key.curve, ec.SECP256R1):
        raise TypeError("Private key is not a P-256 key")

    der_signature = private_key.sign(
        signing_input.encode("ascii"),
        ec.ECDSA(hashes.SHA256()),
    )

    r, s = decode_dss_signature(der_signature)

    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    signature_b64 = base64url_encode(signature)

    return f"{signing_input}.{signature_b64}"

def get_oid4vp_access_token(
    target_url: str,
    did: str,
    verifiable_credential: str,
    key_path: str,
    scope: str,
) -> str:
    log.info("Issuing oid4vp access token for '%s'", target_url)

    key = Path(key_path)

    if not key.is_file():
        raise RuntimeError(f"Private key '{key_path}' not found")

    log.info("Getting token endpoint")
    token_endpoint = get_token_endpoint(target_url)
    log.debug("Token endpoint: %s", token_endpoint)

    log.info("Signing JWT")
    vp_token = sign_jwt(
        did=did,
        verifiable_credential=verifiable_credential,
        key_path=key_path,
    )
    log.debug("JWT: %s", vp_token)

    log.info("Requesting credentials")
    response: Response = Request(
        method="POST",
        url=token_endpoint,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "vp_token",
            "vp_token": vp_token,
            "scope": scope,
        },
        json=False,
    ).fetch().raise_for_status()

    try:
        return response.data["access_token"]

    except KeyError:
        raise RuntimeError(
            "OID4VP token response did not contain 'access_token'"
        )

