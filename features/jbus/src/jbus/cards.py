"""What a work item's card offers (`actions`), and the address of an item's page in jbus view
(`view_link`).

A card's `actions` are the decisions that the relay's `POST /item` accepts from the chat
(`jbus.chat`). jbus posts no card any more.
"""

from __future__ import annotations

import os

from jbus.item import MOVES, Item, Risk, Verb

VIEW_PORT = 4388
ACTIONS: dict[Verb, str] = {Verb.APPROVE: "approve"}
"""What a card offers, in order, by the name its button sends as the `verb` of the relay's
`POST /item`."""


def actions(item: Item) -> list[str]:
    """Return what the card offers. A review item gets nothing, since the user decides it in
    the view. Any other item gets each of `ACTIONS` that `MOVES` has from the item's state."""
    if item.risk is Risk.REVIEW:
        return []
    return [name for one, name in ACTIONS.items() if (item.state, one) in MOVES]


def view_address(page: str) -> str:
    """Return the address of a page of jbus view, `page` being its path and its fragment, such as
    `/#/demo`. The page is at the first origin in `JBUS_VIEW_ORIGINS`, which is the proxy in front
    of the view. Without such an origin, the page is at the first name in `JBUS_VIEW_NAMES`, then
    at the address in `JBUS_VIEW_HOST`, and last at 127.0.0.1, at the view's port."""
    origins = [one.strip() for one in os.environ.get("JBUS_VIEW_ORIGINS", "").split(",")]
    origin = next((one for one in origins if one), "")
    if origin:
        return origin.rstrip("/") + page
    names = [one.strip() for one in os.environ.get("JBUS_VIEW_NAMES", "").split(",")]
    host = next((one for one in names if one), os.environ.get("JBUS_VIEW_HOST") or "127.0.0.1")
    return f"http://{host}:{VIEW_PORT}{page}"


def view_link(project: str, name: str) -> str:
    """Return the item's page in jbus view (`view_address`)."""
    return view_address(f"/#/{project}/item/{name}")
