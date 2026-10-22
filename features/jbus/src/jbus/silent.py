"""What the relay pages when Sous Chef is silent, and how a page reads.

The relay keeps what blocks (`Watch`), from each body on the `blocking` route, and an item
still open in a `reminder` or a `refresh` `PAGE_MINUTES` (45) after it began to block pages
once (`judge`). A page is one line (`page_line`), and a body Sous Chef did not take pages its
first item or event (`unheard_line`).
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
    """The time `value` gives, in ISO form with its zone, else None."""
    if not isinstance(value, str):
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    return at if at.tzinfo else None


def page_line(project: str, line: str, minutes: float, event: str = "") -> str:
    """A page: the project, the line, how long it has blocked, and for (a) the event id. A
    URL that carries a key, as a query or a user, is cut out."""
    said = f"{project}: {SECRET_URL.sub('<url>', line)}, blocking {int(minutes)} min"
    return f"{said}, event {event}" if event else said


def unheard_line(id: str, body: Body) -> str | None:
    """The page for a body on the `blocking` route that Sous Chef did not take: its first
    item or event, and how many more. None for a body that names nothing, an all-clear."""
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
    """What the relay knows of what blocks: each item by its page id, a hash of its project,
    key and when it began to block (so an item that closes and opens again is a new one), the
    page ids marked seen, and the page ids each event id carried, for `/ack`."""

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
    """What a body tells of what blocks, and the pages it makes, each `(page id, line)`.

    The items of an `events`, `reminder` or `refresh` body are kept, under the event id that
    carried them. A `refresh` lists every open item of its project, so the project's items it
    does not list closed: they are dropped. An item a `reminder` or `refresh` lists
    `PAGE_MINUTES` after it began to block (the body's `at` against the item's `opened`), and
    that is not seen, makes a page. The pager's route sends a page id once."""
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
