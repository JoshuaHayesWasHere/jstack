"""A JSON Schema validator for the subset `schemas/` uses, with the standard library alone.

The generator runs before `uv sync`, so it cannot import `jsonschema`. The keywords are
`type`, `required`, `properties`, `additionalProperties`, `pattern`, `enum`, `const`, `items`,
`minLength` and `maxLength`, with `$schema`, `$id`, `title`, `description` and `default` read
as notes. A schema with any other keyword is refused rather than half read, and
`tests/test_jtrees_schema.py` holds the verdicts to `jsonschema`'s on a corpus of good and bad
manifests.
"""

from __future__ import annotations

import json
import re
from typing import Any

NOTES = frozenset(("$schema", "$id", "title", "description", "default"))
KEYWORDS = frozenset(
    (
        "type",
        "required",
        "properties",
        "additionalProperties",
        "pattern",
        "enum",
        "const",
        "items",
        "minLength",
        "maxLength",
    )
)
_TYPES: dict[str, Any] = {
    "object": lambda x: isinstance(x, dict),
    "array": lambda x: isinstance(x, list),
    "string": lambda x: isinstance(x, str),
    "boolean": lambda x: isinstance(x, bool),
    "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
    "number": lambda x: isinstance(x, int | float) and not isinstance(x, bool),
    "null": lambda x: x is None,
}


class Unsupported(ValueError):
    """A schema with a keyword outside the subset."""


def _same(a: object, b: object) -> bool:
    """JSON equality: `true` is not `1`."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _at(where: str, key: str | int) -> str:
    return f"{where}/{key}"


def _supported(schema: dict[str, Any], where: str) -> None:
    """Refuse a schema, at any depth, with a keyword outside the subset."""
    unknown = set(schema) - KEYWORDS - NOTES
    if unknown:
        raise Unsupported(
            f"{where or '/'}: keywords outside the subset: {', '.join(sorted(unknown))}"
        )
    for key, value in schema.get("properties", {}).items():
        _supported(value, _at(where, f"properties/{key}"))
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            _supported(schema[key], _at(where, key))


def _check(instance: object, schema: dict[str, Any], where: str, out: list[str]) -> None:
    here = where or "/"
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_TYPES[one](instance) for one in types):
            out.append(f"{here}: is not of type {' or '.join(types)}")
            return
    if "const" in schema and not _same(instance, schema["const"]):
        out.append(f"{here}: is not {json.dumps(schema['const'])}")
    if "enum" in schema and not any(_same(instance, one) for one in schema["enum"]):
        out.append(f"{here}: is not one of {json.dumps(schema['enum'])}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            out.append(f"{here}: is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            out.append(f"{here}: is longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            out.append(f"{here}: does not match {schema['pattern']}")
    if isinstance(instance, list) and "items" in schema:
        for at, one in enumerate(instance):
            _check(one, schema["items"], _at(where, at), out)
    if isinstance(instance, dict):
        for key in schema.get("required", ()):
            if key not in instance:
                out.append(f"{here}: lacks {key}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                _check(value, properties[key], _at(where, key), out)
            elif extra is False:
                out.append(f"{here}: has {key}, which the schema does not allow")
            elif isinstance(extra, dict):
                _check(value, extra, _at(where, key), out)


def validate(instance: object, schema: dict[str, Any]) -> list[str]:
    """Each way `instance` breaks `schema`, as `<json pointer>: <why>`; none when it holds."""
    _supported(schema, "")
    out: list[str] = []
    _check(instance, schema, "", out)
    return out
