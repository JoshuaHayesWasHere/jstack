"""The rows a brief builds on, as its `Builds on:` line names them. `jbus queue add` holds a
row's `--depends` to these: a row depends only on a row whose work it starts from."""

import re

from jbriefs.parse import fields

_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")


def builds_on(text: str) -> frozenset[str]:
    """The rows a brief's `Builds on:` field names: in each `;` item, the slugs before its colon.

    An item with no colon names rows only when it is a list of slugs, one between each pair of
    commas. Otherwise it is prose, a `;` inside a description or a line with no colon, and names
    none.
    """
    said = next((" ".join(lines) for name, lines in fields(text) if name == "Builds on"), "")
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
