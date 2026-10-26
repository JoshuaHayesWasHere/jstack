"""What the page of `jbus view` does, kept as events on this machine and nowhere else.

The page posts one event to `POST /usage` when the view opens, for each route it shows, for each
item it opens and for each action it takes. One listener on the page reads an item from the
`data-open` attribute of what was tapped, and one hook reads an action from each write the page
sends, so no panel posts an event of its own. The body is JSON with six fields and no more:

- `kind`, one of `KINDS`;
- `name`: for `open` and `route`, the route, one of `ROUTES`; for `item`, the name of one of the
  server's panels or `HELP`; for `action`, one of `ACTIONS`, the writes the page can send;
- `project`, the project the page shows, or `""` for every project;
- `route`, the route the page showed when it happened;
- `seconds`, the seconds from page load to the event, for the first item or action of its kind
  and name in that page, and null for any other;
- `headless`, true when a headless or driven browser loaded the page (an agent's look, a test),
  so that what is counted is a person's use: the commands leave those lines out.

The server takes a name only from what it already has, a project only from the projects of the
state directory, seconds only as a number from 0 to `LONGEST`, and `headless` only as true or
false. It refuses anything else with 400, and writes nothing. So a line has the time and those six
fields, each a value the server chose or a number, and no row text, slug, thread id or address can
reach it.

`/usage` is a write, as the answer and the steer are: only the server's own page may post it
(`jbus.view`). It needs no `?project=`.

The lines go to `FILE`, in jbus's state directory. A line is kept `KEPT`, 90 days: when the
oldest line is a day past that, the next append drops every line older than `KEPT`. Past `CAP`
bytes, whatever their age, the file keeps only its newest lines that fit in `KEEP` bytes.
`jbus view usage` counts the lines of a window for each kind and name, and `jbus view pace` gives,
for each route and action, the median seconds to its first time in a page, this week against
last.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import jsettings
from jbus import Refused, item
from jbus.view import state

USAGE = "/usage"
FILE = "view-usage.jsonl"
KINDS = ("open", "route", "item", "action")
TIMED = ("item", "action")
ROUTES = ("stack", "triage", "project")
ACTIONS = ("answer", "approve", *(str(one) for one in item.Steer))
FIELDS = {"kind", "name", "project", "route", "seconds", "headless"}
HELP = "help"
LONGEST = 7 * 24 * 3600
KEPT = timedelta(days=90)
SLACK = timedelta(days=1)
CAP = 16 * 1024 * 1024
KEEP = CAP // 2
WINDOW = timedelta(days=7)
_LOCK = threading.Lock()


@dataclass(frozen=True)
class Line:
    at: str
    kind: str
    name: str
    project: str | None
    route: str
    seconds: float | None
    headless: bool


def names(kind: str, drawers: Iterable[str]) -> frozenset[str]:
    """The names a line of this kind may have, given the names of the server's panels."""
    if kind in ("open", "route"):
        return frozenset(ROUTES)
    if kind == "item":
        return frozenset({*drawers, HELP})
    return frozenset(ACTIONS)


def _seconds(given: Any) -> float | None:
    if given is None:
        return None
    if isinstance(given, bool) or not isinstance(given, int | float) or not 0 <= given <= LONGEST:
        raise Refused("refused: seconds are a number from 0 to a week, or null")
    return round(float(given), 1)


def line(body: bytes, drawers: Iterable[str], projects: Iterable[str], now: datetime) -> Line:
    """The line a body asks for, or `Refused` where it asks for anything but known names."""
    try:
        asked = json.loads(body)
    except ValueError:
        asked = None
    if not isinstance(asked, dict) or set(asked) != FIELDS:
        raise Refused(
            "refused: an event is a kind, a name, a project, a route, seconds and headless"
        )
    kind, name, project, route = (asked[key] for key in ("kind", "name", "project", "route"))
    if kind not in KINDS or not isinstance(name, str) or name not in names(kind, drawers):
        raise Refused("refused: an event names a kind and a name the server has")
    if project != "" and (not isinstance(project, str) or project not in set(projects)):
        raise Refused("refused: an event names a project the server has, or none")
    if route not in ROUTES:
        raise Refused("refused: an event names a route the server has")
    if not isinstance(asked["headless"], bool):
        raise Refused("refused: headless is true or false")
    seconds = _seconds(asked["seconds"])
    return Line(state.iso(now), kind, name, project or None, route, seconds, asked["headless"])


def _at(raw: bytes) -> datetime | None:
    try:
        return datetime.fromisoformat(json.loads(raw)["at"])
    except (ValueError, TypeError, KeyError):
        return None


def _replace(path: Path, kept: list[bytes]) -> None:
    fresh = path.with_name(f".{path.name}.{os.getpid()}")
    fresh.write_bytes(b"".join(kept))
    fresh.replace(path)


def append(path: Path, one: Line, now: datetime) -> None:
    """Append one line to the file. Once its oldest line is `SLACK` past `KEPT`, drop every line
    older than `KEPT`, and past `CAP` keep only its newest lines in `KEEP`."""
    text = json.dumps(asdict(one), sort_keys=True) + "\n"
    with _LOCK:
        with path.open("a") as file:
            file.write(text)
            size = file.tell()
        with path.open("rb") as file:
            first = _at(file.readline())
        if first is not None and first < now - KEPT - SLACK:
            young = now - KEPT
            every = path.read_bytes().splitlines(keepends=True)
            _replace(path, [each for each in every if (_at(each) or now) >= young])
            size = path.stat().st_size
        if size <= CAP:
            return
        kept, room = [], KEEP
        for each in reversed(path.read_bytes().splitlines(keepends=True)):
            room -= len(each)
            if room < 0:
                break
            kept.append(each)
        _replace(path, list(reversed(kept)))


def _read(path: Path) -> Iterator[tuple[datetime, dict[str, Any]]]:
    """Each line of the file with its time, skipping a line it cannot read. A line from before
    `headless` was kept has none, and counts as a person's."""
    try:
        text = path.read_text()
    except OSError:
        return
    for each in text.splitlines():
        try:
            one = json.loads(each)
            at = datetime.fromisoformat(one["at"])
            if at.tzinfo and isinstance(one["kind"], str) and isinstance(one["name"], str):
                yield at, one
        except (ValueError, TypeError, KeyError):
            continue


def counts(path: Path, since: datetime) -> tuple[Counter[tuple[str, str]], int]:
    """How many lines of a person's loads since `since` have each kind and name, and how many
    lines of headless loads were left out."""
    found: Counter[tuple[str, str]] = Counter()
    headless = 0
    for at, one in _read(path):
        if at < since:
            continue
        if one.get("headless") is True:
            headless += 1
        else:
            found[(one["kind"], one["name"])] += 1
    return found, headless


def firsts(
    path: Path, now: datetime
) -> dict[tuple[str, str, str], tuple[list[float], list[float]]]:
    """The seconds to each first item and action of a person's loads, by route, kind and name:
    those of this week, the last `WINDOW`, and those of the week before it."""
    this, last = now - WINDOW, now - 2 * WINDOW
    found: dict[tuple[str, str, str], tuple[list[float], list[float]]] = defaultdict(
        lambda: ([], [])
    )
    for at, one in _read(path):
        seconds, route = one.get("seconds"), one.get("route")
        if one["kind"] not in TIMED or not isinstance(route, str) or at < last or at > now:
            continue
        if one.get("headless") is True:
            continue
        if isinstance(seconds, bool) or not isinstance(seconds, int | float):
            continue
        found[(route, one["kind"], one["name"])][0 if at >= this else 1].append(float(seconds))
    return dict(found)


def arguments(shown: argparse.ArgumentParser) -> None:
    shown.add_argument(
        "--since", help="count from this time, the user's zone with none (default: 7 days ago)"
    )


def report(path: Path, user: jsettings.Settings, now: datetime, args: argparse.Namespace) -> int:
    """Print the counts of a window: a first line with the total of a person's loads and how
    many lines of headless loads were left out, then one line for each kind and name, by kind in
    the order of `KINDS` and the most opened first."""
    given = args.since
    at = state.when(given, user) if given else state.iso(now - WINDOW)
    if at is None:
        raise Refused(f"refused: --since {given!r} is not a time")
    since = datetime.fromisoformat(at)
    found, headless = counts(path, since)
    print(
        f"jbus view usage: {sum(found.values())} since {user.stamp(since)}, from {path}, "
        f"and {headless} headless left out"
    )
    order: dict[str, Any] = {kind: n for n, kind in enumerate(KINDS)}
    ranked = sorted(found.items(), key=lambda kv: (order.get(kv[0][0], 9), -kv[1], kv[0][1]))
    for (kind, name), count in ranked:
        print(f"{kind:<7} {name:<10} {count}")
    return 0


def _median(seconds: list[float]) -> str:
    return f"{statistics.median(seconds):.1f} ({len(seconds)})" if seconds else "-"


def pace(path: Path, user: jsettings.Settings, now: datetime) -> int:
    """Print, for each route and action, the median seconds from page load to its first time in
    a page, this week against last week, with how many pages each median is of, and the change.
    It reads a person's loads only."""
    print(
        "jbus view pace: median seconds from page load to the first of each item and action, "
        f"this week (since {user.stamp(now - WINDOW)}) against the week before, from {path}"
    )
    found = firsts(path, now)
    if not found:
        print("no first action in the last two weeks")
        return 0
    print(f"{'route':<8} {'action':<16} {'this week':<12} {'last week':<12} change")
    for (route, kind, name), (this, last) in sorted(found.items()):
        change = (
            f"{statistics.median(this) - statistics.median(last):+.1f}" if this and last else "-"
        )
        action = f"{kind} {name}"
        print(f"{route:<8} {action:<16} {_median(this):<12} {_median(last):<12} {change}")
    return 0
