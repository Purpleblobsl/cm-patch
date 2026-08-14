import inspect
from dataclasses import fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import (
    Any,
    Literal,
    Mapping,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

def cast_dataclass[T](
    tp: type[T],
    value: Mapping[str, Any],
    extra: Literal["ignore", "raise"] = "ignore",
) -> T:
    """ Recursively deserialize JSON into dataclasses. """
    if not is_dataclass(tp):
        raise TypeError(f"{tp.__name__} is not a dataclass")
    return try_cast(tp, value, extra=extra)

def try_cast(
    tp: type,
    value: Any,
    extra: Literal["ignore", "raise"] = "ignore",
    path: str = "<root>",
) -> Any:
    """ Recursively deserialize JSON. """
    if value is None: return None

    def e_msg(msg: str) -> str:
        return f"{path}: {msg}"
    def expect_collection():
        if not isinstance(value, (list, set, tuple)):
            raise TypeError(e_msg(
                f"Expected collection, got {type(value).__name__}"
            ))

    origin = get_origin(tp)
    args = get_args(tp)

    # Optional[T] | Union[A, B]
    if origin in (Union, UnionType):
        # Note: this can break serialization:
        #       Union[list|str|int]
        #           -> list(125) -> Error       -> next
        #           -> str(125)  -> Ok          -> return "125"
        #           -> int(125)  -> never runs
        for arg in args:
            if arg is type(None):
                continue

            try:
                return try_cast(arg, value, extra, path)
            except (TypeError, ValueError):
                continue

        raise TypeError(e_msg(f"Cannot deserialize {value!r} as {tp}"))

    # Literal[...]
    if origin is Literal:
        if value not in args:
            raise ValueError(e_msg(f"Expected one of {args}, got {value!r}"))
        return value

    # List[T]
    if origin is list:
        (inner,) = args

        expect_collection()

        return [
            try_cast(inner, item, extra, f"{path}[{i}]")
            for i, item in enumerate(value)
        ]

    # Set[T]
    if origin is set:
        (inner,) = args

        expect_collection()

        return {
            try_cast(inner, item, extra, f"{path}[{i}]")
            for i, item in enumerate(value)
        }

    # Tuple[T, ...] | Tuple[T0, T1, T2, ...]
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(
                try_cast(args[0], item, extra, f"{path}[{i}]")
                for i, item in enumerate(value)
            )

        expect_collection()

        if len(value) != len(args):
            raise ValueError(e_msg(
                f"Expected tuple of length {len(args)}, got {len(value)}"
            ))

        return tuple(
            try_cast(inner, item, extra, f"{path}[{i}]")
            for (i, inner), item in zip(enumerate(args), value)
        )

    # Dict[K, V]
    if origin is dict:
        ktype, vtype = args
        return {
            try_cast(ktype, key,  extra, f"{path}.<key>"):
            try_cast(vtype, item, extra, f"{path}.{key!r}")
            for key, item in value.items()
        }

    # Enum
    if inspect.isclass(tp) and issubclass(tp, Enum):
        if isinstance(value, str):
            return tp[value]
        return tp(value)

    # Dataclass
    if is_dataclass(tp):
        if not isinstance(value, Mapping):
            raise TypeError(e_msg(
                f"Expected object for {tp.__name__}, got {type(value).__name__}"
            ))

        hints = get_type_hints(tp)

        if extra == "raise":
            model_fields = {field.name for field in fields(tp)}
            extra_fields = value.keys() - model_fields

            if extra_fields:
                TypeError(e_msg(
                    f"Unknown field(s) for {tp.__name__}: "
                    f"{', '.join(map(str, extra_fields))}"
                ))

        kwargs = {}

        for field in fields(tp):
            if field.name not in value:
                continue

            try:
                kwargs[field.name] = try_cast(
                    hints[field.name],
                    value[field.name],
                    extra,
                    f"{path}.{field.name}"
                )

            except (TypeError, ValueError) as exc:
                raise type(exc)(f"{tp.__name__}.{field.name}: {exc}") from exc

        return tp(**kwargs)

    # Any
    if tp is Any:
        return value

    # Already the right type
    if isinstance(value, tp):
        return value

    # Primitive / other types
    try:
        return tp(value)
    except (TypeError, ValueError) as exc:
        raise type(exc)(e_msg(
            f"Cannot convert {value!r} to {tp}"
        )) from exc


def to_json(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {
            field.name: to_json(getattr(obj, field.name))
            for field in fields(obj)
        }

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, (list, tuple, set)):
        return [to_json(x) for x in obj]

    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}

    return obj
