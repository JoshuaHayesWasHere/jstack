"""One gate that jbus holds, answered on the page. It draws an item of the list the you
panel gives, and has no data of its own: the answer is the server's one write."""

from __future__ import annotations

from typing import Any

from jbus.view.state import WAITING_FILE, Read

FIRST = True
SHAPE: dict[str, Any] = {}
SOURCES = (WAITING_FILE,)


def build(read: Read) -> dict[str, Any]:
    return {}
