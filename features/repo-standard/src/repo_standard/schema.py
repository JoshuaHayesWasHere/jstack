"""A feature manifest checked against the JSON Schema a repo's config names, with the standard
library alone, since the guards run before any install.

It reads the subset the standard's schemas use: `type`, `required`, `properties`,
`additionalProperties`, `items`, `pattern`, `enum`, `const`, `minLength` and `maxLength`, with
`$schema`, `$id`, `title`, `description` and `default` as notes. A `{"$ref": "<file>#<pointer>"}`
names a subschema of a file beside the schema, which is how a repo's extension takes the
standard's core (`schemas/feature.core.schema.json`). It refuses a schema with any other keyword
rather than read half of it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

NOTES = frozenset(("$schema", "$id", "title", "description", "default"))
KEYWORDS = frozenset(
    (
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "pattern",
        "enum",
        "const",
        "minLength",
        "maxLength",
    )
)
TYPES: dict[str, Any] = {
    "object": lambda x: isinstance(x, dict),
    "array": lambda x: isinstance(x, list),
    "string": lambda x: isinstance(x, str),
    "boolean": lambda x: isinstance(x, bool),
    "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
    "number": lambda x: isinstance(x, int | float) and not isinstance(x, bool),
    "null": lambda x: x is None,
}


class Unsupported(ValueError):
    """A schema the subset cannot read: a keyword outside it, or a `$ref` that names nothing."""


def _same(a: Any, b: Any) -> bool:
    """JSON equality, in which `true` is not `1`."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _target(ref: str, here: Path, document: dict[str, Any]) -> Any:
    name, _, pointer = ref.partition("#")
    node: Any = load(here.parent / name) if name else document
    for step in pointer.split("/")[1:]:
        if not isinstance(node, dict) or step not in node:
            raise Unsupported(f"{here.name}: $ref {ref} names nothing")
        node = node[step]
    return node


def _resolved(schema: dict[str, Any], here: Path, document: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        return _resolved(_target(schema["$ref"], here, document), here, document)
    unknown = set(schema) - KEYWORDS - NOTES
    if unknown:
        raise Unsupported(f"{here.name}: keywords outside the subset: {', '.join(sorted(unknown))}")
    out = dict(schema)
    if "properties" in out:
        out["properties"] = {
            key: _resolved(value, here, document) for key, value in out["properties"].items()
        }
    for key in ("items", "additionalProperties"):
        if isinstance(out.get(key), dict):
            out[key] = _resolved(out[key], here, document)
    return out


def load(path: Path) -> dict[str, Any]:
    """The schema at `path` with each `$ref` replaced by what it names. It raises `Unsupported`
    on a keyword outside the subset, and `OSError` or `ValueError` on a file it cannot read."""
    document = json.loads(path.read_text(encoding="utf-8"))
    return _resolved(document, path, document)


def validate(instance: Any, schema: dict[str, Any], where: str = "") -> list[str]:
    """Each way `instance` breaks `schema`, as `<json pointer>: <why>`, or none."""
    here = where or "/"
    kinds = schema.get("type")
    if kinds is not None:
        kinds = kinds if isinstance(kinds, list) else [kinds]
        if not any(TYPES[one](instance) for one in kinds):
            return [f"{here}: is not of type {' or '.join(kinds)}"]
    out = []
    if "const" in schema and not _same(instance, schema["const"]):
        out.append(f"{here}: is not {json.dumps(schema['const'])}")
    if "enum" in schema and not any(_same(instance, one) for one in schema["enum"]):
        out.append(f"{here}: is not one of {json.dumps(schema['enum'])}")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            out.append(f"{here}: is shorter than {schema['minLength']}")
        if len(instance) > schema.get("maxLength", len(instance)):
            out.append(f"{here}: is longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            out.append(f"{here}: does not match {schema['pattern']}")
    if isinstance(instance, list) and "items" in schema:
        for at, one in enumerate(instance):
            out += validate(one, schema["items"], f"{where}/{at}")
    if isinstance(instance, dict):
        out += [f"{here}: lacks {key}" for key in schema.get("required", ()) if key not in instance]
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                out += validate(value, properties[key], f"{where}/{key}")
            elif extra is False:
                out.append(f"{here}: has {key}, which the schema does not allow")
            elif isinstance(extra, dict):
                out += validate(value, extra, f"{where}/{key}")
    return out
