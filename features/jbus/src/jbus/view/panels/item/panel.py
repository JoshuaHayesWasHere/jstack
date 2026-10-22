"""One work item, which the user opens at `#/<project>/item/<id>` and steers there. It draws an
item of the frame's `items`. For each live item it adds where the item came from, `source`, and
the steers the item takes, `steers`. Those are the moves that `jbus.item`'s `MOVES` has from the
item's state. A redirect is among them only where the queue has the item's row, since
`jbus.steer` refuses a redirect otherwise. So the page shows only the steers that the record
would take, and keeps no copy of the rules. The steer is the server's `POST /steer`, and an
approval by the item's id is one of its actions."""

from __future__ import annotations

from typing import Any

from jbus import item
from jbus.view.clean import ANY
from jbus.view.state import Read

FIRST = True
SHAPE: dict[str, Any] = {"steering": {ANY: {"source": None, "steers": [None]}}}
APPROVE = "approve"
TAKES = ((item.Verb.APPROVE, APPROVE), *((one, str(one)) for one in item.Steer))


def build(read: Read) -> dict[str, Any]:
    rows = {row["slug"] for row in read.rows}
    steering = {}
    for one in item.items(read.state).values():
        if one.state not in item.LIVE:
            continue
        steers = [name for move, name in TAKES if (one.state, move) in item.MOVES]
        if one.slug not in rows:
            steers = [name for name in steers if name != item.Steer.REDIRECT]
        steering[one.id] = {"source": one.source, "steers": steers}
    return {"steering": steering}
