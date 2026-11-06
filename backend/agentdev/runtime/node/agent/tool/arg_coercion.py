"""Coerce tool-call arguments to the types a tool's JSON schema declares.

Small models (and the native-call rescue) often pass ``"12"`` for an integer, ``"true"`` for a boolean or a
JSON string for an array. Tools then crash with ``'<' not supported between 'str' and 'int'``. This runs at the
dispatch point for every tool call: convertible values are converted, anything else raises
:class:`ToolArgumentError` naming the argument and the expected type.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Mapping, Optional

_TRUE = {"true", "1", "yes", "y"}
_FALSE = {"false", "0", "no", "n"}


class ToolArgumentError(ValueError):
    """An argument cannot be converted to the type the tool declares."""


def _fail(path: str, expected: str, value: Any) -> ToolArgumentError:
    shown = repr(value)
    if len(shown) > 60:
        shown = shown[:57] + "..."
    return ToolArgumentError(f"argument '{path}' must be {expected}, got {shown}")


def _declared(schema: Mapping[str, Any]) -> Optional[str]:
    kind = schema.get("type")
    if isinstance(kind, list):
        kinds = [k for k in kind if k != "null"]
        return kinds[0] if len(kinds) == 1 else None
    return kind if isinstance(kind, str) else None


def _coerce(value: Any, schema: Any, path: str) -> Any:
    if not isinstance(schema, Mapping):
        return value
    kind = _declared(schema)
    if kind is None or value is None:
        return value
    if kind == "integer":
        if isinstance(value, bool):
            raise _fail(path, "an integer", value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            raise _fail(path, "an integer", value)
        if isinstance(value, str):
            try:
                number = float(value.strip())
            except ValueError:
                raise _fail(path, "an integer", value) from None
            if math.isfinite(number) and number.is_integer():
                return int(number)
        raise _fail(path, "an integer", value)
    if kind == "number":
        if isinstance(value, bool):
            raise _fail(path, "a number", value)
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                number = float(value.strip())
            except ValueError:
                raise _fail(path, "a number", value) from None
            if math.isfinite(number):
                return int(number) if number.is_integer() and "." not in value and "e" not in value.lower() else number
        raise _fail(path, "a number", value)
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in _TRUE:
            return True
        if isinstance(value, str) and value.strip().lower() in _FALSE:
            return False
        if value in (0, 1) and not isinstance(value, float):
            return bool(value)
        raise _fail(path, "a boolean (true/false)", value)
    if kind == "array":
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise _fail(path, "an array", value) from None
        if not isinstance(value, list):
            raise _fail(path, "an array", value)
        items = schema.get("items")
        return [_coerce(item, items, f"{path}[{i}]") for i, item in enumerate(value)] if items else value
    if kind == "object":
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise _fail(path, "an object", value) from None
        if not isinstance(value, dict):
            raise _fail(path, "an object", value)
        return _coerce_object(value, schema, path)
    return value


def _coerce_object(value: Dict[str, Any], schema: Mapping[str, Any], prefix: str) -> Dict[str, Any]:
    props = schema.get("properties")
    if not isinstance(props, Mapping):
        return value
    out = dict(value)
    for key, sub in props.items():
        if key in out:
            out[key] = _coerce(out[key], sub, f"{prefix}.{key}" if prefix else key)
    return out


def coerce_arguments(arguments: Any, schema: Any) -> Any:
    """``arguments`` with every value converted to its declared schema type (new dict; input is not mutated)."""
    if not isinstance(arguments, dict) or not isinstance(schema, Mapping):
        return arguments
    return _coerce_object(arguments, schema, "")
