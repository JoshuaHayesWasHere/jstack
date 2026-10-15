"""One thread, followed to what it works on: `thread:<role>:<slug>`. It is drawn from the
threads the threads panel gives the first screen, a scout's request with them, so it gives
no key of its own and reads no source of its own."""

from __future__ import annotations

from typing import Any

from jbus.view.state import Read

FIRST = True
SHAPE: dict[str, Any] = {}


def build(read: Read) -> dict[str, Any]:
    return {}
