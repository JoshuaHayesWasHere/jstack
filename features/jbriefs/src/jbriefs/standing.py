"""Two of the user's standing rules, as checks of a brief's fields (`jbriefs.parse.fields`).

`parse.faults` runs both when a row is first queued. One holds a brief's CPU load to a bounded
one, and one keeps its `Builds on:` line from stacking it by plan layer. Each takes the fields
and returns why the brief breaks the rule as one line, or an empty string.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

Fields = Iterable[tuple[str, list[str]]]


def _first(fields: Fields, label: str) -> list[str] | None:
    return next((lines for name, lines in fields if name == label), None)


_EVERY_CORE = re.compile(
    r"stress-ng\b[^\n`]*?--cpu[ =]+0\b"
    r"|--cpu[ =]+[\"']?(?:\$\(nproc\)|`nproc`)"
    r"|\ball(?: the)? (?:cpu )?cores\b"
    r"|\bevery (?:cpu )?core(?=\s*(?:[^\w\s-]|$)"
    r"| (?:busy|loaded|saturated|pinned|maxed|at|of|with|for|to|under|and)\b)",
    re.I,
)
_UNASKED = re.compile(
    r"\b(?:never|not|no|nor|without|instead of|rather than|avoid\w*|don't|refuse[sd]?|forbid\w*)\b",
    re.I,
)
_CLAUSE = re.compile(r"[.;!?](?:\s|$)")
_SPAN = re.compile(r"`[^`]+`")
_WORDS = re.compile(r"(?:all|every)\b", re.I)


def load(fields: Fields) -> str:
    """Why a brief asks for a load that takes every core. `fields` are the brief's head.

    It reads them for `stress-ng --cpu 0`, `--cpu $(nproc)` or every core: `all cores`, or
    `every core` where `core` is the noun, at a stop or before a load word (`busy`, `loaded`), so
    `every core module` and `all core tests` ask for no load. A `Ruled out:` field
    names what was set aside, and a clause that turns the ask down (`never`, `not`, `instead
    of`) does not ask for it either. The words in a code span quote the phrase and do not ask
    for it, while a command there (`stress-ng --cpu 0`) is still the ask. Such a load starves
    every other thread on the machine, and the way to load it is a bounded one, a few cores or
    `taskset`, inside `jgauge test-slot`.
    """
    for label, lines in fields:
        if label == "Ruled out":
            continue
        for line in lines:
            spans = [span.span() for span in _SPAN.finditer(line)]
            for found in _EVERY_CORE.finditer(line):
                quoted = any(a < found.start() and found.end() < b for a, b in spans)
                if quoted and _WORDS.match(found[0]):
                    continue
                clause = _CLAUSE.split(line[: found.start()])[-1]
                if not _UNASKED.search(clause):
                    return (
                        f"brief asks for {found[0]}, a load that takes every core: name a "
                        "bounded load (a few cores, or taskset) and run it inside `jgauge "
                        "test-slot`"
                    )
    return ""


_LAYER = re.compile(r"\blayer\s+\d+\b|\b(?:plan|same|previous|prior|earlier|next)\s+layer\b", re.I)


def layered(fields: Fields) -> str:
    """Why a brief's `Builds on:` line may not be queued, as one line, or an empty string.

    An item whose reason names a plan layer (`the base of layer 2`, `the plan layer before`) is
    at fault. A `--depends` on an open pull request stacks the row on that branch, and a stack
    by layer holds the row behind work its code never touches.
    """
    said = " ".join(_first(fields, "Builds on") or [])
    found = [item.strip() for item in said.split(";") if _LAYER.search(item.partition(":")[2])]
    if not found:
        return ""
    return (
        f"brief's Builds on: line stacks by plan layer ({'; '.join(found)}): a row builds on "
        "another only for code it changes, calls or imports. Sibling work of one layer queues "
        "with no Builds on: line, and with --merge-after where the merge order matters"
    )
