"""The page of a project's log after a cursor, which `jbus feed` prints and `GET /feed` serves.

The feed is the project's log, `events.jsonl`, in the order of the file, read after the event a
cursor names (`wake.entries`). Each act is an `act` event of that log (`jbus.acts`), so events and
acts come in one order. The same page is `jbus feed --after <id>` on the command line and
`GET /feed?project=<project>&after=<id>` on the view (`jbus.view`). Nothing is pushed: a bot has
no endpoint, and the user wants no webhook alarms. The verb is `jbus.feed`, and the view's door is
`jbus.view.feeds`.

A page is `{"v", "project", "reset", "cursor", "events"}`. `cursor` is the id of the last event
of the page, or the cursor given where nothing came after it, and the next read is after it. Each
event is a `FeedEvent`, `{"v", "id", "at", "project", "kind", "subject", "line", "need", "act"}`:

- `kind` is the event's kind, and `act` for an act;
- `subject` is the row or question it is about: its slug, or an act's subject, or nothing;
- `need` is what waits on the user about that subject now, as `/stack.json`'s `needs` has it,
  with its `doors`, or null;
- `act` is the act, as `acts.jsonl` has it, for an `act` event, and null for any other.

A cursor the log does not have, because it is not an id or because the daily prune dropped its
event (`wake.LOG_KEEP`), or no cursor, gives a page with `reset` true, no events, the cursor of
the newest event, and `needs`: everything that waits on the user, to catch up from. The cursor
is read before the needs, so an event that comes in between is on the next page. On an empty
log that cursor is `START`, which names the start of the log: a read after it gives every
event from the first one, and waits like a read after any other cursor.

A read may wait: `--wait <s>` or `&wait=<s>`, up to `WAIT_MOST` seconds, is a long poll. It
returns at the first new event, or with no event once the time is up. A reset never waits.

`v` is on the page and on every event. A field may be added within a version, and anything that
changes the shape of one bumps `V`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jbus import acts, wake

V = 1
START = "start"
"""The cursor before the first event of the log; an id is hex, so no event has it."""
WAIT_MOST = 600
TICK = 0.5
WAIT = f"wait is a number of seconds, 0 to {WAIT_MOST}"

Needs = Callable[[], list[dict[str, Any]]]


def read(state: Path, project: str, after: str, needs: Needs) -> dict[str, Any]:
    """The page after the cursor `after`, or the reset where the log has no event of that id.
    `needs` gives what waits on the user now, and is asked only for a page that shows it."""
    log = wake.entries(state)
    cursors = [START] + [one["id"] for one in log]
    if after not in cursors:
        return _page(project, True, cursors[-1], []) | {"needs": needs()}
    new = log[cursors.index(after) :]
    if not new:
        return _page(project, False, after, [])
    shown, made = needs(), {one["id"]: one for one in acts.read(state)}
    return _page(project, False, new[-1]["id"], [_event(project, one, shown, made) for one in new])


def wait(
    state: Path,
    project: str,
    after: str,
    seconds: float,
    needs: Needs,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """The page after `after`, once it has an event or once `seconds` are up. The log is read
    again only when its file changed since the mark taken before the last read, so a line
    written during a read changes the mark."""
    end = clock() + seconds
    mark = _mark(state)
    page = read(state, project, after, needs)
    while not page["reset"] and not page["events"] and clock() < end:
        sleep(min(TICK, max(0.0, end - clock())))
        if (now := _mark(state)) != mark:
            mark, page = now, read(state, project, after, needs)
    return page


def seconds(given: str) -> float:
    """Read a wait, refusing what is not a number of seconds from 0 to `WAIT_MOST`."""
    try:
        made = float(given)
    except ValueError:
        raise ValueError(WAIT) from None
    if not 0 <= made <= WAIT_MOST:
        raise ValueError(WAIT)
    return made


def _page(project: str, reset: bool, cursor: str, events: list[Any]) -> dict[str, Any]:
    return {"v": V, "project": project, "reset": reset, "cursor": cursor, "events": events}


def _event(
    project: str, one: dict[str, Any], needs: list[dict[str, Any]], made: dict[str, Any]
) -> dict[str, Any]:
    subject = str(one.get("subject") or one.get("slug") or "")
    named = [need for need in needs if subject and need.get("subj") == subject]
    named += [need for need in needs if subject and need.get("slug") == subject]
    return {
        "v": V,
        "id": one["id"],
        "at": one["at"],
        "project": project,
        "kind": one["event"],
        "subject": subject,
        "line": one.get("line", ""),
        "need": named[0] if named else None,
        "act": made.get(one.get("act", "")) if one["event"] == acts.KIND else None,
    }


def _mark(state: Path) -> tuple[int, int] | None:
    try:
        seen = (state / wake.LOG).stat()
    except OSError:
        return None
    return seen.st_size, seen.st_mtime_ns
