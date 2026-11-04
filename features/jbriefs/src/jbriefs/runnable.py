"""Judge a brief's `Done when:` items: does each name a way to check it that anyone can run, or
only say what should hold."""

from __future__ import annotations

import re

from jbriefs.meets import done_when

RUNNERS = (
    "uv run",
    "pytest",
    "make",
    "jbus",
    "jmerge",
    "jgauge",
    "jbriefs",
    "rg",
    "grep",
    "gh",
    "git",
    "sh",
    "bash",
    "python3",
    "test",
)
"""The words a `Done when:` item's command in backticks starts with, for it to be one that runs."""
_RUNNER = re.compile(rf"`(?:{'|'.join(re.escape(one) for one in RUNNERS)})(?=[\s`])")
_TEST_PATH = re.compile(r"(?<![\w./-])(?:[\w.-]+/)*tests/[\w./-]*\.py(?:::[\w\[\]-]+)?\b")
_JUDGED = re.compile(r"\bjudged:\s*\S", re.I)
_RUNS_IN_EACH = (
    "(in each, a command in backticks that starts with a runner, a `tests/...py[::name]` path, or "
    "`judged: <why>`)"
)


def runs(item: str) -> bool:
    """Whether a `Done when:` item names a way to check it: a command in backticks that starts
    with one of `RUNNERS`, a `tests/...py[::name]` path, or `judged: <why>` for what only a
    person can judge."""
    return bool(_RUNNER.search(item) or _TEST_PATH.search(item) or _JUDGED.search(item))


def runnable(text: str) -> str:
    """Why items of a brief's `Done when:` list run nothing (`runs`), as one line: how many, and
    the first. It is an empty string when every item runs something."""
    items = done_when(text.splitlines())
    idle = [item for item in items if not runs(item)]
    if not idle:
        return ""
    return (
        f"brief's Done when: has {len(idle)} of {len(items)} items that run nothing, the first: "
        f"{idle[0]} {_RUNS_IN_EACH}"
    )
