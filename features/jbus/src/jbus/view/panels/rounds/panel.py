"""The rounds of each task: its brief's `## Review` sections in order, each with its verdict, its
head and its count of findings, whether the task needed a second or a scoped pass, and how many
times the crewmate was woken and the branch was rebased.

`jmerge`'s own reader (`ready.said_of`), the one the merge goes by, reads the sections. A section
has no time of its own. A round has a time only where the event log has a `review` event of the
slug whose section names the same head. A brief that cannot be read says so, and has no count at
all: the panel never shows it as a task with no review.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jbus.view.state import _SLUG, EVENTS_FILE, Read, text, when
from jmerge import ready

FIRST = True
_ROUND = {"verdict": None, "head": None, "findings": None, "at": None}
_TASK = {
    "slug": None,
    "read": None,
    "why": None,
    "reviews": [_ROUND],
    "second": None,
    "scoped": None,
    "woke": None,
    "rebases": None,
}
SHAPE = {"rounds": [_TASK]}
SOURCES = (EVENTS_FILE,)
_WOKE = re.compile(r"Wok(e|en)\b")


def brief(read: Read, slug: str) -> tuple[str | None, str]:
    """The slug's brief, from its home or from the copy jbus keeps, or None and why not."""
    if not _SLUG.fullmatch(slug):
        return None, "its slug is not one a brief is named by"
    paths: tuple[Path, ...] = (
        read.home / "tasks" / f"{slug}.md",
        read.state / "briefs" / f"{slug}.md",
    )
    for path in paths:
        try:
            return path.read_text(errors="replace"), ""
        except FileNotFoundError:
            continue
        except OSError as error:
            return None, f"its brief could not be read: {error.strerror or error}"
    return None, "it has no brief in its home or in jbus's copies"


def _times(read: Read, slug: str) -> dict[str, list[str]]:
    """The time of each `review` event of the slug, by the head its section names, oldest
    first."""
    found: dict[str, list[str]] = {}
    for one in read.logged or []:
        at = when(one.get("at"))
        if one.get("event") != "review" or one.get("slug") != slug or not at:
            continue
        for section in ready.said_of(str(one.get("text") or "")).rounds:
            if section.head:
                found.setdefault(section.head, []).append(at)
    return found


def rounds(read: Read, slug: str) -> dict[str, Any]:
    """What the slug's brief says of its rounds."""
    said, why = brief(read, slug)
    if said is None:
        return {"slug": slug, "read": False, "why": why, "reviews": []}
    reader, times = ready.said_of(said), _times(read, slug)
    reviews = []
    for one in reader.rounds:
        at = times.get(one.head, [])
        reviews.append(
            {
                "verdict": text(one.verdict, 40),
                "head": text(one.head, 40),
                "findings": one.found,
                "at": at.pop(0) if at else None,
            }
        )
    lines = said.splitlines()
    return {
        "slug": slug,
        "read": True,
        "why": "",
        "reviews": reviews,
        "second": reader.second,
        "scoped": reader.scoped,
        "woke": sum(1 for line in lines if _WOKE.match(line)),
        "rebases": sum(1 for line in lines if line.startswith("Rebase:")),
    }


def build(read: Read) -> dict[str, Any]:
    slugs = dict.fromkeys(task["slug"] for task in (*read.tasks, *read.ended))
    return {"rounds": [rounds(read, slug) for slug in slugs]}
