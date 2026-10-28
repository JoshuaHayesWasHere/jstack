"""The rows a brief builds on, as its `Builds on:` line names them. `jbus queue add` holds a
row's `--depends` to these: a row depends only on a row whose work it starts from. That work is
code the row changes, calls or imports, or a Result it reads, and never the plan layer it sits
in: `layered` is the brief's fault for a line that gives a layer as its reason."""

import re

from jbriefs import parse

_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")
_LAYER = re.compile(r"\blayer\s+\d+\b|\b(?:plan|same|previous|prior|earlier|next)\s+layer\b", re.I)


def builds_on(text: str) -> frozenset[str]:
    """The rows a brief's `Builds on:` field names: in each `;` item, the slugs before its colon.

    An item with no colon names rows only when it is a list of slugs, one between each pair of
    commas. Otherwise it is prose, a `;` inside a description or a line with no colon, and names
    none.
    """
    said = _said(text)
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


def layered(text: str) -> str:
    """Why a brief's `Builds on:` line may not be queued, as one line, or an empty string.

    An item whose reason names a plan layer (`the base of layer 2`, `the plan layer before`) is
    at fault. A `--depends` on an open pull request stacks the row on that branch, and a stack
    by layer holds the row behind work its code never touches.
    """
    held = [
        item.strip() for item in _said(text).split(";") if _LAYER.search(item.partition(":")[2])
    ]
    if not held:
        return ""
    return (
        f"brief's Builds on: line stacks by plan layer ({'; '.join(held)}): a row builds on "
        "another only for code it changes, calls or imports, or for its Result. Sibling work of "
        "one layer queues with no Builds on: line, and with --merge-after where the merge order "
        "matters"
    )


def _said(text: str) -> str:
    return next((" ".join(lines) for name, lines in parse.fields(text) if name == "Builds on"), "")
