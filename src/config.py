import os, inspect
from dataclasses import MISSING, fields, is_dataclass
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Iterable,
    List,
    Optional,
    Tuple,
    get_args,
    get_origin,
)

from .utils import Mode

type Primitive  = bool|int|float|str|Enum
type FieldValue = Primitive|list[Primitive]|tuple[Primitive,...]|set[Primitive]
config: Config

@dataclass(frozen=True, kw_only=True, slots=True)
class Config:
    #* app

    MODE: Mode
    APP_NAME: str = "cm-patch"

    #* holder

    HOLDER_DID: str
    HOLDER_KEY_PATH: str
    # HOLDER_KEY_TYPE: str # EC
    # HOLDER_SIGNATURE_ALGORITHM: str # ES256

    #* tmf

    TMF_URL: str
    TMF_IGNORE_ORGS: Tuple[str, ...] = field(default_factory=tuple)

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
            config.VC_CONFIG_IDS,
            config.VC_CONFIG_FORMATS,
            config.VC_CONFIG_SCOPES,
        )

def config_load[T: object](
    cfg: type[T],
    prefix: str = "",
) -> T:
    if not is_dataclass(cfg):
        raise TypeError(f"Config class '{cfg.__name__}' must be a dataclass")

    allowed = get_args(Primitive.__value__)
    def is_valid_field_type(t: Any) -> bool:
        origin = get_origin(t)

        if origin in (list, tuple, set):
            if not (args := get_args(t)): return True
            return is_valid_field_type(args[0])

        return t in allowed or is_enum_t(t)
    def is_enum_t(t: type[FieldValue]) -> bool:
        return inspect.isclass(t) and issubclass(t, Enum)

    def norm(value: FieldValue) -> FieldValue:
        if isinstance(value, list):  return list(value)
        if isinstance(value, tuple): return tuple(value)
        if isinstance(value, set):   return set(value)
        return value

    enum_map: dict[type[Enum], dict[str, Enum]] = {}
    def cast(
        value: str,
        to_type: type[FieldValue]
    ) -> Tuple[FieldValue, Exception|None]:
        origin = get_origin(to_type)
        args = get_args(to_type)

        # Containers
        if origin in (list, set, tuple):
            item_type = args[0] if args else str

            try:
                items = [
                    cast(item.strip(), item_type)
                    for item in value.split(",")
                    if item.strip()
                ]
                error_items = [item for item in items if item[1] is not None]

                if error_items:
                    return value, TypeError(
                        "Container cast error, some values don't match type "
                        f"'{item_type}': {error_items}"
                    )

                return origin(item[0] for item in items), None

            except Exception as e:
                return value, e

        if to_type is bool:
            v = value.lower()
            if v in ("1", "true", "yes", "on"): return True, None
            if v in ("0", "false", "no", "off"): return False, None
            return value, ValueError(f"Invalid boolean: {value}")

        if is_enum_t(to_type):
            mapping = enum_map.get(to_type) # type:ignore
            if not mapping:
                mapping = {m.name.lower(): m for m in to_type} # type:ignore
                enum_map[to_type] = mapping # type:ignore

            v = value.lower()
            if v in mapping: return mapping[v], None

            return value, ValueError(
                f"Invalid value '{value}' for {to_type.__name__}. "
                f"Expected one of: {', '.join(mapping.keys())}"
            )

        try:                   return to_type(value), None
        except Exception as e: return value, e

    values: dict[str, FieldValue] = {}
    errors: List[Exception] = []

    for field in fields(cfg):
        env_name = f"{prefix}{field.name.upper()}"
        value: Optional[str] = os.getenv(env_name)

        if not is_valid_field_type(field.type):
            errors.append(TypeError(
                f"Field '{field.name}' has unsupported type: {field.type}"
            ))

        elif value is not None:

            ft: type[FieldValue] = field.type # type:ignore

            try:
                v, ex = cast(value, ft)
                if ex is not None:
                    errors.append(ex)
                    continue
                values[field.name] = norm(v)

            except (ValueError, TypeError) as e:
                errors.append(e)

        elif field.default is not MISSING:
            values[field.name] = field.default

        elif field.default_factory is not MISSING:
            values[field.name] = field.default_factory()

        else:
            errors.append(ValueError(
                f"Missing required environment variable: {env_name}"
            ))

    if errors:
        raise ExceptionGroup("Configuration errors", errors)

    return cfg(**values)

def config_str(cfg: object) -> str:
    if not is_dataclass(cfg):
        raise TypeError(
            f"Config class '{type(cfg).__name__}' must be a dataclass"
        )

    text: str = f"{type(cfg).__name__}:"

    for field in fields(cfg):
        value = getattr(cfg, field.name)
        text += f"\n  {field.name} = {value}"

    return text

def config_assert():
    assert(len(config.VC_CONFIG_FORMATS) == len(config.VC_CONFIG_IDS))
    assert(len(config.VC_CONFIG_FORMATS) == len(config.VC_CONFIG_SCOPES))

config = config_load(Config)

