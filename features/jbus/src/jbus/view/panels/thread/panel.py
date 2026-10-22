"""One thread, followed to what it works on: `thread:<role>:<slug>`. The page draws it from the
threads that the threads panel gives the first screen, where each scout's thread comes with its
request. So this panel gives no key of its own and reads no source of its own."""

from __future__ import annotations

from typing import Any

from jbus.view.state import Read

FIRST = True
SHAPE: dict[str, Any] = {}


def build(read: Read) -> dict[str, Any]:
    return {}
