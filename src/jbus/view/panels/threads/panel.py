"""Every thread the last pass saw that is not settled, a crew's, a scout's, a reviewer's, a
home's or any other, each with its liveness, or null where the pass left no list: that is
a blind spot, never a count of none. A scout's says what its request says of its work,
which the server reads from the home's `scouts/` itself."""

from __future__ import annotations

from typing import Any

from jbus.view.state import PASS_FILE, SCOUTS, THREAD, Read, Source, Spot, _mtime

FIRST = True
UNLISTED = "the threads that are out are not known: the last pass left no list of them"
SHAPE = {"threads": [THREAD]}
SOURCES = (
    PASS_FILE,
    Source(f"{SCOUTS}/", "server", lambda read: {"at": _mtime(read.home / SCOUTS)}, 145),
)


def blind(read: Read) -> list[Spot]:
    return [Spot(UNLISTED, 400)] if read.name and read.out is None else []


def build(read: Read) -> dict[str, Any]:
    return {"threads": read.out}
