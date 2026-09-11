import bean.config as config

from enum import Enum, auto
from pathlib import Path
from typing import (
    Dict,
    Iterable,
    Tuple,
)

#-------------------------------------------------------------------------------

class Mode(Enum):
    DEV     = auto()
    PROD    = auto()

class LogLevel(Enum):
    DEBUG   = auto()
    INFO    = auto()
    WARN    = auto()

#- config ----------------------------------------------------------------------

@config.load(priorities=["envs", "defaults"])
class Config:
    #* app

    APP_MODE: Mode
    APP_NAME: str = "cm-patch"
    APP_PORT: int = 8080
    APP_LOG_LEVEL: LogLevel = LogLevel.INFO
    APP_HOST: str = "cm-patch"

    #* holder

    HOLDER_DID: str
    HOLDER_KEY_PATH: str
    # HOLDER_KEY_TYPE: str # EC
    # HOLDER_SIGNATURE_ALGORITHM: str # ES256

    HOLDER_DSC_URL: str
    HOLDER_PAP_URL: str
    HOLDER_TIL_URL: str

    #* tmf

    TMF_URL: str
    TMF_SUBCRIBE: bool
    TMF_IGNORE_ORGS: Tuple[str, ...] = tuple() # TODO: not implemented

    #* keycloak

    KC_URL: str
    KC_REALM: str
    KC_CLIENT_ID: str
    KC_SCOPE: str
    KC_USER: str
    KC_PASS: str

    #* VC & JWT

    VC_CONFIG_IDS: Tuple[str, ...]
    VC_CONFIG_FORMATS: Tuple[str, ...]
    VC_CONFIG_SCOPES: Tuple[str, ...]

    #* sugar

    @property
    def app_url(self) -> str:
        return f"http://{self.APP_HOST}:{self.APP_PORT}"

    @property
    def kc_url(self) -> str:
        return f"{self.KC_URL}/realms/{self.KC_REALM}"

    @property
    def token_url(self) -> str:
        return f"{self.kc_url}/protocol/openid-connect/token"

    @property
    def oid4vc_url(self) -> str:
        return f"{self.kc_url}/protocol/oid4vc"

    @property
    def vc_configs(self) -> Iterable[Tuple[str, str, str]]:
        return zip(
            self.VC_CONFIG_IDS,
            self.VC_CONFIG_FORMATS,
            self.VC_CONFIG_SCOPES,
        )

    @property
    def holder_key_path(self) -> Path:
        return self._holder_key_path

    def vc_scope_map(self, scope: str) -> Tuple[str, str, str]|None:
        """ return (id, fmt, scope) """
        return self._vc_scope_map.get(scope)

    #* normalizers

    _vc_scope_map: Dict[str, Tuple[str, str, str]] = {}
    @config.normalizer("VC_CONFIG_IDS", "VC_CONFIG_FORMATS", "VC_CONFIG_SCOPES")
    def _vc_to_map(self, ids: Tuple[str], fmts: Tuple[str], scopes: Tuple[str]):
        self._vc_scope_map = {
            scope: (id, fmt, scope)
            for id, fmt, scope in zip(ids, fmts, scopes)
        }
        return ids, fmts, scopes

    _holder_key_path: Path
    @config.normalizer("HOLDER_KEY_PATH")
    def _to_path(self, path: str) -> str:
        self._holder_key_path = Path(path)
        return path

    _holder_key_path: Path
    @config.normalizer(
        "KC_URL",
        "HOLDER_DSC_URL",
        "HOLDER_PAP_URL",
        "HOLDER_TIL_URL",
        series=True,
    )
    def _rstrip_slash(self, url: str) -> str:
        return url.rstrip("/")

    #* validators

    @config.validator("APP_PORT")
    def _is_port(self, port: int) -> bool:
        return 0 < port <= 65535

    @config.validator("HOLDER_KEY_PATH")
    def _is_file(self, path: str) -> bool:
        return Path(path).is_file()

    @config.validator("VC_CONFIG_IDS")
    def _non_empty(self, ids: Tuple) -> bool:
        return bool(ids)

    @config.validator("VC_CONFIG_IDS", "VC_CONFIG_FORMATS", "VC_CONFIG_SCOPES")
    def _match_len(self, ids: Tuple, fmts: Tuple, scopes: Tuple) -> bool:
        return len(ids) == len(fmts) == len(scopes)

