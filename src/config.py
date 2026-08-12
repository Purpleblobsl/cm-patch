import bean.config as config

from enum import Enum, auto
from pathlib import Path
from typing import (
    Iterable,
    Tuple,
)

class Mode(Enum):
    DEBUG   = auto()
    DEV     = auto()
    PROD    = auto()

    @property
    def is_debug(self) -> bool:
        return self == self.DEBUG

type Primitive  = bool|int|float|str|Enum
type FieldValue = Primitive|list[Primitive]|tuple[Primitive,...]|set[Primitive]

@config.load(priorities=["envs", "defaults"])
class Config:
    #* app

    APP_MODE: Mode
    APP_NAME: str = "cm-patch"
    APP_PORT: int = 8080

    #* holder

    HOLDER_DID: str
    HOLDER_KEY_PATH: str
    # HOLDER_KEY_TYPE: str # EC
    # HOLDER_SIGNATURE_ALGORITHM: str # ES256

    #* tmf

    TMF_URL: str
    TMF_IGNORE_ORGS: Tuple[str, ...] = tuple()

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

    #* normalizers

    _holder_key_path: Path
    @config.normalizer("HOLDER_KEY_PATH")
    def to_path(self, path: str) -> str:
        self._holder_key_path = Path(path)
        return path

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

