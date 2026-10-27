"""One work item, which the user opens at `#/<project>/item/<id>` and approves there. It draws an
item of the frame's `items`. For each live item it adds where the item came from, `source`, and
whether the item takes the user's go, `approve`: whether `jbus.item`'s `MOVES` has an approval
out of the item's state. So the page shows Approve only where the record would take it, and keeps
no copy of the rules. The go is the server's `POST /approve`."""

from __future__ import annotations

from typing import Any

from jbus import item
from jbus.view.clean import ANY
from jbus.view.state import Read

FIRST = True
SHAPE: dict[str, Any] = {"takes": {ANY: {"source": None, "approve": None}}}


def build(read: Read) -> dict[str, Any]:
    takes = {}
    for one in item.items(read.state).values():
        if one.state in item.LIVE:
            approve = (one.state, item.Verb.APPROVE) in item.MOVES
            takes[one.id] = {"source": one.source, "approve": approve}
    return {"takes": takes}
