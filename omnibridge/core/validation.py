"""Argument validation and coercion for tool calls (defensive, no external schema lib needed)."""
from __future__ import annotations

from typing import Any

from .permissions import ToolDef

_PY_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
             "array": list, "object": dict}


class ValidationError(ValueError):
    pass


def validate_args(tool: ToolDef, args: dict[str, Any] | None) -> dict[str, Any]:
    """Return a normalized copy of args: defaults applied, types coerced, unknown keys kept."""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ValidationError(f"Arguments for {tool.name} must be an object, got {type(args).__name__}")
    out: dict[str, Any] = {}
    for key, spec in tool.params.items():
        if key not in args or args[key] is None:
            if "default" in spec:
                out[key] = spec["default"]
            continue
        value = args[key]
        expected = spec.get("type")
        py_type = _PY_TYPES.get(expected) if expected else None
        if py_type is not None:
            if expected in ("integer", "number") and isinstance(value, str):
                try:
                    value = int(value) if expected == "integer" else float(value)
                except ValueError:
                    raise ValidationError(f"Parameter '{key}' must be {expected}, got {value!r}") from None
            if expected == "boolean" and isinstance(value, str):
                value = value.lower() in ("1", "true", "yes", "on")
            if expected == "array" and not isinstance(value, list):
                raise ValidationError(f"Parameter '{key}' must be an array")
            if expected == "object" and not isinstance(value, dict):
                raise ValidationError(f"Parameter '{key}' must be an object")
            if expected == "string" and not isinstance(value, str):
                value = str(value)
            if not isinstance(value, py_type):
                raise ValidationError(f"Parameter '{key}' must be {expected}, got {type(value).__name__}")
        if "enum" in spec and value not in spec["enum"]:
            raise ValidationError(f"Parameter '{key}' must be one of {spec['enum']}, got {value!r}")
        if "minimum" in spec and isinstance(value, (int, float)) and value < spec["minimum"]:
            raise ValidationError(f"Parameter '{key}' must be >= {spec['minimum']}")
        if "maximum" in spec and isinstance(value, (int, float)) and value > spec["maximum"]:
            raise ValidationError(f"Parameter '{key}' must be <= {spec['maximum']}")
        out[key] = value
    missing = [r for r in tool.required if r not in out or out[r] in (None, "")]
    if missing:
        raise ValidationError(f"Missing required parameter(s) for {tool.name}: {', '.join(missing)}")
    for k, v in args.items():
        out.setdefault(k, v)
    return out
