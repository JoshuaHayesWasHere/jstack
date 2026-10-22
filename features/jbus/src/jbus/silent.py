"""This module decides what the relay pages when Sous Chef is silent, and how a page reads.

The relay keeps a record of what blocks (`Watch`), and updates it from each body on the `blocking`
route. When a `reminder` or a `refresh` lists an item that is still open `PAGE_MINUTES` (45) after
it began to block, the relay pages it once (`judge`). A page is one line (`page_line`). For a body
that Sous Chef did not take, the relay pages its first item or event (`unheard_line`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jbus import leftover

Body = dict[str, Any]

SECRET_URL = re.compile(r"\S+://\S*[@?]\S*?(?=[:,;)]?(\s|$))")
PAGE_MINUTES = leftover.REMIND_MINUTES + 30


def when(value: Any) -> datetime | None:
    """Return the time `value` gives in ISO form with its zone, or None when it gives none."""
    if not isinstance(value, str):
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    return at if at.tzinfo else None


def page_line(project: str, line: str, minutes: float, event: str = "") -> str:
    """Return a page: the project, the line, how long it has blocked, and the event id when
    one is given. `page_line` cuts out a URL that carries a key, as a query or as a user."""
    said = f"{project}: {SECRET_URL.sub('<url>', line)}, blocking {int(minutes)} min"
    return f"{said}, event {event}" if event else said


def unheard_line(id: str, body: Body) -> str | None:
    """Return the page for a body on the `blocking` route that Sous Chef did not take. The
    page names the body's first item or event and says how many more there are. A body that
    names nothing is an all-clear, and `unheard_line` returns None for it."""
    at = when(body.get("at"))
    named = []
    for one in [*(body.get("items") or []), *(body.get("events") or [])]:
        if isinstance(one, dict) and isinstance(one.get("line"), str):
            opened = when(one.get("opened") or one.get("since"))
            minutes = (at - opened).total_seconds() / 60 if at and opened else 0
            project = one.get("project") or body.get("project") or "jbus"
            named.append((str(project), one["line"], max(minutes, 0)))
    if not named:
        return None
    project, line, minutes = named[0]
    more = f" and {len(named) - 1} more" if len(named) > 1 else ""
    return page_line(project, line + more, minutes, id)


@dataclass(frozen=True)
class Watch:
    """The relay's record of what blocks.

    `items` holds each item by its page id. A page id is a hash of the item's project, its
    key and the time it began to block, so an item that closes and opens again gets a new
    id. `seen` holds the page ids marked as seen. `ids` holds, for `/ack`, the page ids that
    came with each event id."""

    items: dict[str, Body] = field(default_factory=dict)
    seen: frozenset[str] = frozenset()
    ids: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Watch:
        try:
            kept = json.loads(path.read_text())
            return cls(kept["items"], frozenset(kept["seen"]), kept["ids"])
        except (OSError, ValueError, KeyError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        part = path.with_suffix(".part")
        with part.open("w") as file:
            json.dump({"items": self.items, "seen": sorted(self.seen), "ids": self.ids}, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(part, path)


def page_id(project: str, key: str, opened: str) -> str:
    named = json.dumps([project, key, opened]).encode()
    return f"open-{hashlib.sha256(named).hexdigest()[:24]}"


def judge(watch: Watch, id: str, body: Body) -> tuple[Watch, list[tuple[str, str]]]:
    """Update the record of what blocks from a body. Return the new `Watch` and the pages the
    body makes, each `(page id, line)`.

    `judge` keeps the items of an `events`, `reminder` or `refresh` body under the body's
    event id. A `refresh` lists every open item of its project, so an item of that
    project that the refresh does not list has closed, and `judge` drops it. An item makes a page
    when a `reminder` or `refresh` lists it `PAGE_MINUTES` or more after it began to block
    (the body's `at` against the item's `opened`) and nobody has marked it seen. The pager's
    route sends each page id once."""
    kind, project = body.get("kind"), body.get("project")
    if kind not in ("events", "reminder", "refresh"):
        return watch, []
    listed: dict[str, Body] = {}
    for one in body.get("items") or []:
        if not isinstance(one, dict):
            continue
        named, key, line = one.get("project") or project, one.get("key"), one.get("line")
        opened = one.get("opened") or one.get("since")
        if all(isinstance(value, str) for value in (named, key, line)) and when(opened):
            item = {"project": named, "key": key, "line": line, "opened": opened}
            listed[page_id(named, key, opened)] = item
    items = watch.items | listed
    ids = {event: list(pages) for event, pages in watch.ids.items()}
    if listed:
        ids[id] = sorted(set(ids.get(id, [])) | set(listed))
    seen = watch.seen
    if kind == "refresh" and isinstance(project, str):
        closed = {page for page, one in items.items() if one["project"] == project} - set(listed)
        items = {page: one for page, one in items.items() if page not in closed}
        seen = seen - closed
        ids = {event: [p for p in pages if p not in closed] for event, pages in ids.items()}
        ids = {event: pages for event, pages in ids.items() if pages}
    pages = []
    at = when(body.get("at"))
    if kind in ("reminder", "refresh") and at:
        for page, one in listed.items():
            minutes = (at - datetime.fromisoformat(one["opened"])).total_seconds() / 60
            if minutes >= PAGE_MINUTES and page not in seen:
                pages.append((page, page_line(one["project"], one["line"], minutes)))
    return Watch(items, seen, ids), pages
