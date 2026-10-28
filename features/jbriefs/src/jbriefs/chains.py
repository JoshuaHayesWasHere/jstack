"""The rows a brief builds on, as its `Builds on:` line names them. `jbus queue add` holds a
row's `--depends` to these: a row depends only on a row whose code it changes, calls or imports,
and never on the plan layer it sits in: `jbriefs.standing.layered` is the brief's fault for a
line that gives a layer as its reason."""

import re
from collections.abc import Iterable

from jbriefs import parse

_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")


def builds_on(text: str) -> frozenset[str]:
    """The rows a brief's `Builds on:` field names: in each `;` item, the slugs before its colon.

    An item with no colon names rows only when it is a list of slugs, one between each pair of
    commas. Otherwise it is prose, a `;` inside a description or a line with no colon, and names
    none.
    """
    said = _said(parse.fields(text))
    named: set[str] = set()
    for item in said.split(";"):
        head, colon, _ = item.partition(":")
        if colon:
            words = [word.strip("`") for word in re.split(r"[\s,]+", head)]
            named.update(word for word in words if _SLUG.fullmatch(word))
            continue
        words = [word.strip().strip("`") for word in item.split(",")]
        if all(_SLUG.fullmatch(word) for word in words):
            named.update(words)
    return frozenset(named)


def _said(held: Iterable[tuple[str, list[str]]]) -> str:
    return next((" ".join(lines) for name, lines in held if name == "Builds on"), "")
