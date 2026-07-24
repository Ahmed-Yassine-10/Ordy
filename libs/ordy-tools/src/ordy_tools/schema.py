"""Schema validation behind a port.

``BasicSchemaValidator`` implements the JSON Schema subset the platform catalog uses
(type, required, properties, enum, numeric bounds, array/string bounds, uuid format).
It is deliberately strict: unknown keywords are ignored, but every constraint it does
understand is enforced, and unknown top-level properties are rejected for objects that
declare ``additionalProperties: false``.

Production may swap in ``JsonSchemaLibValidator`` (the `jsonschema` extra) for full spec
coverage. Either way the schema step is only ONE of six layers — referential integrity,
server-side pricing, business rules, and caps are independent (doc 03 §3.4).
"""

from __future__ import annotations

import re
from typing import Protocol

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


class SchemaValidator(Protocol):
    def validate(self, instance: object, schema: dict) -> list[str]: ...


class BasicSchemaValidator:
    def validate(self, instance: object, schema: dict) -> list[str]:
        errors: list[str] = []
        self._check(instance, schema, "$", errors)
        return errors

    def _check(self, value: object, schema: dict, path: str, errors: list[str]) -> None:
        expected = schema.get("type")
        if expected:
            types = _TYPES.get(expected)
            # bool is a subclass of int — never accept it as a number
            if types and (not isinstance(value, types) or (expected in {"integer", "number"} and isinstance(value, bool))):
                errors.append(f"{path}: expected {expected}")
                return

        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: must be one of {schema['enum']}")

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(f"{path}: shorter than {schema['minLength']}")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append(f"{path}: longer than {schema['maxLength']}")
            if schema.get("format") == "uuid" and not _UUID_RE.match(value):
                errors.append(f"{path}: not a uuid")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{path}: below minimum {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{path}: above maximum {schema['maximum']}")

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path}: fewer than {schema['minItems']} items")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append(f"{path}: more than {schema['maxItems']} items")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for i, item in enumerate(value):
                    self._check(item, item_schema, f"{path}[{i}]", errors)

        if isinstance(value, dict):
            properties = schema.get("properties", {})
            for required in schema.get("required", []):
                if required not in value:
                    errors.append(f"{path}: missing required '{required}'")
            if schema.get("additionalProperties") is False:
                for key in value:
                    if key not in properties:
                        errors.append(f"{path}: unexpected property '{key}'")
            for key, sub_schema in properties.items():
                if key in value and isinstance(sub_schema, dict):
                    self._check(value[key], sub_schema, f"{path}.{key}", errors)


class JsonSchemaLibValidator:
    """Full-spec validator (requires the 'jsonschema' extra)."""

    def validate(self, instance: object, schema: dict) -> list[str]:
        import jsonschema  # type: ignore

        validator = jsonschema.Draft202012Validator(schema)
        return [f"{'.'.join(str(p) for p in e.path) or '$'}: {e.message}" for e in validator.iter_errors(instance)]


def default_validator() -> SchemaValidator:
    """Prefer the full library when installed; fall back to the built-in subset."""
    try:
        import jsonschema  # type: ignore  # noqa: F401

        return JsonSchemaLibValidator()
    except ImportError:
        return BasicSchemaValidator()
