"""Make each line of a work item's log a card for Sous Chef's chat (`card`). A card is one
body of the kind `item`, and its `id` is the project and the line's id. So the relay sends
each card once, and Sous Chef replaces the item's card with the newest. A pass posts a card
for each line that has none yet (`post`) to each webhook route that is the relay
(`relayed`). On a route's first pass, it posts one card for each live item instead of the
whole log.

A card's `actions` are the decisions that the relay's `POST /item` accepts from the chat
(`jbus.chat`).
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import jsettings
from jbus import Refused, read_json, verbs, wake, write_json
from jbus.item import (
    LIVE,
    MOVES,
    Item,
    Move,
    Risk,
    Steer,
    Verb,
    Where,
    advance,
    judged,
    move_of,
    read,
)

CARD = "item"
CARDS = "cards.json"
VIEW_PORT = 4388
RELAY_PORT = 4390
LOOPBACK = ("127.0.0.1", "localhost", "::1")
ACTIONS: dict[Move, str] = {Verb.APPROVE: "approve", Steer.MESSAGE: "message", Steer.HOLD: "hold"}
"""What a card offers, in order, by the name its button sends as the `verb` of the relay's
`POST /item`."""
SAID: dict[Move, str] = {
    Verb.PROPOSE: "Proposed",
    Verb.LINK: "Linked to its row",
    Verb.APPROVE: "Approved",
    Verb.QUEUE: "Queued",
    Verb.LAUNCH: "Launched",
    Verb.WAIT: "Waiting on you",
    Verb.RESUME: "Resumed",
    Verb.HOLD: "Held",
    Verb.DONE: "Done",
    Verb.DROP: "Dropped",
    Verb.STEER: "Steered",
    Steer.MESSAGE: "Messaged",
    Steer.HOLD: "Held",
    Steer.REDIRECT: "Redirected",
}
SAID_IN = {Where.VIEW: " in jbus view", Where.CHAT: " in chat", Where.CLI: " from the command line"}


def actions(item: Item) -> list[str]:
    """Return what the card offers. A review item gets nothing, since the user decides it in
    the view. Any other item gets each of `ACTIONS` that `MOVES` has from the item's state.
    The user approves a redirected item only by its id, in the view or the command, so its
    card offers no approval."""
    if item.risk is Risk.REVIEW:
        return []
    offered = [one for one in ACTIONS if (item.state, one) in MOVES]
    return [ACTIONS[one] for one in offered if not (one is Verb.APPROVE and item.redirect)]


def last(line: dict[str, Any], user: jsettings.Settings) -> str:
    """Write the line as one sentence for the card, as
    "Approved in jbus view by Josh, 11:52 EDT"."""
    where = Where(line["where"])
    said = f"{SAID[move_of(line)]}{SAID_IN.get(where, '')} by {line['by']}"
    return f"{said}, {user.clock(datetime.fromisoformat(line['at']))}"


def view_link(project: str, name: str) -> str:
    """Return the item's page in jbus view. The page is at the first origin in
    `JBUS_VIEW_ORIGINS`, which is the proxy in front of the view. Without one, it is at the
    first name in `JBUS_VIEW_NAMES`, then at the address in `JBUS_VIEW_HOST`, and last at
    127.0.0.1, at the view's port."""
    page = f"/#/{project}/item/{name}"
    origins = [one.strip() for one in os.environ.get("JBUS_VIEW_ORIGINS", "").split(",")]
    origin = next((one for one in origins if one), "")
    if origin:
        return origin.rstrip("/") + page
    names = [one.strip() for one in os.environ.get("JBUS_VIEW_NAMES", "").split(",")]
    host = next((one for one in names if one), os.environ.get("JBUS_VIEW_HOST") or "127.0.0.1")
    return f"http://{host}:{VIEW_PORT}{page}"


def card(item: Item, line: dict[str, Any], user: jsettings.Settings) -> dict[str, Any]:
    """Make the card of one line: the item as it stood after the line, with its risk now. The
    card's `id` is the project and the line's id, since an item's id is unique only within its
    project."""
    return {
        "kind": CARD,
        "id": f"{item.project}.{line['id']}",
        "item": item.id,
        "project": item.project,
        "title": item.title,
        "state": str(item.state),
        "owner": item.owner,
        "risk": str(item.risk),
        "last": last(line, user),
        "actions": actions(item),
        "view": view_link(item.project, item.id),
    }


def relayed(route: wake.Route) -> bool:
    """Say whether the route is the relay on this machine, at `RELAY_PORT` (4390, or the
    `RELAY_PORT` of the environment). The relay is the one way into Sous Chef's chat, which
    is where a card goes."""
    if not route.url or route.blocking:
        return False
    try:
        parts = urllib.parse.urlsplit(route.url)
        port = int(os.environ.get("RELAY_PORT") or RELAY_PORT)
        return parts.hostname in LOOPBACK and parts.port == port
    except ValueError:
        return False


def cards(
    state: Path, lines: list[dict[str, Any]], user: jsettings.Settings, after: int | None
) -> list[dict[str, Any]]:
    """Return the cards still to post after the first `after` of the log's `lines`, in order.
    With None, no card has gone out yet, so return one card for each live item, at its last
    line, and not one for each line of the log."""
    risks: dict[str, Risk] = {}
    found: dict[str, Item] = {}
    made: list[tuple[Item, dict[str, Any]]] = []
    for at, line in enumerate(lines):
        try:
            found[line["item"]] = advance(found.get(line["item"]), line)
        except (Refused, KeyError, ValueError, TypeError):
            continue
        if after is not None and at >= after:
            made.append((found[line["item"]], line))
    if after is None:
        by_id = {one.get("id"): one for one in lines}
        made = [(one, by_id[one.last_event]) for one in found.values() if one.state in LIVE]
    for one, _ in made:
        if one.id not in risks:
            risks[one.id] = judged(state, found[one.id]).risk
    return [card(replace(one, risk=risks[one.id]), line, user) for one, line in made]


def post(run: wake.Pass) -> int:
    """Post each card still to post to each route that is the relay, in order, as the pass's
    step. Record in the route's `cards.json` how many lines of the log have their card. When a
    POST fails, this function posts nothing more to that route in this pass, and the next pass
    starts again from that card. Return how many cards it posted."""
    state, sent = run.state, 0
    for route in run.box.routes:
        if not relayed(route):
            continue
        mark = route.folder / CARDS
        after = read_json(mark, {}).get("carded")
        after = after if isinstance(after, int) else None
        lines = read(state)
        for one in cards(state, lines, run.user, after):
            why = wake._post(route, one)
            if why:
                run.say(f"cards {run.project.name}: card {one['id']} did not go: {why}")
                break
            sent += 1
        else:
            route.folder.mkdir(parents=True, exist_ok=True)
            write_json(mark, {"carded": len(lines)})
    return sent


STEPS = (verbs.Step("close", 80, "cards.post", lambda half: post(half.run)),)
