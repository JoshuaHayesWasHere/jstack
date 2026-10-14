"""Every thread the last pass saw that is not settled, a crew's, a scout's, a reviewer's, a
home's or any other, each with its liveness, or null where the pass left no list: that is
a blind spot, never a count of none."""

from __future__ import annotations

from typing import Any

from jbus.view.state import PASS_FILE, Read, Spot

FIRST = True
UNLISTED = "the threads that are out are not known: the last pass left no list of them"
_THREAD = {
    key: None
    for key in (
        "title",
        "role",
        "slug",
        "status",
        "live",
        "out",
        "created",
        "updated",
        "run_started",
        "queued",
        "pending",
        "page",
    )
}
SHAPE = {"threads": [_THREAD]}
SOURCES = (PASS_FILE,)


def blind(read: Read) -> list[Spot]:
    return [Spot(UNLISTED, 400)] if read.name and read.out is None else []


def build(read: Read) -> dict[str, Any]:
    return {"threads": read.out}
