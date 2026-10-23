"""What the page of `jbus view` opens, counted on this machine and kept nowhere else.

The page posts one line to `POST /usage` for each route it shows, each drawer it opens, and the
first click after it loads. The body is JSON with three fields and no more: `kind`, one of
`KINDS`; `name`, the route, the drawer or what the click opened; and `project`, the project the
page shows, or `""` for every project. The server takes a `name` only from what it already has:
for a route, one of `ROUTES`; for a drawer, the name of one of its panels or `HELP`; for a click,
either of those or `OTHER`. It takes a `project` only from the projects of the state directory.
It refuses anything else with 400, and writes nothing. So a line has four fields, `at`, `kind`,
`name` and `project`, each one a value the server chose, and no row text, slug, thread id or
address can reach it.

`/usage` is a write, as the answer and the steer are: only the server's own page may post it
(`jbus.view`). It needs no `?project=`.

The lines go to `FILE`, in jbus's state directory. Once the file is over `CAP` bytes, the server
keeps only its newest lines that fit in `KEEP` bytes. `jbus view usage` counts the lines of a
window for each kind and name.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import jsettings
from jbus import Refused
from jbus.view import state

USAGE = "/usage"
FILE = "view-usage.jsonl"
KINDS = ("route", "drawer", "click")
ROUTES = ("stack", "project")
HELP = "help"
OTHER = "other"
CAP = 256 * 1024
KEEP = CAP // 2
WINDOW = timedelta(days=7)
_LOCK = threading.Lock()


@dataclass(frozen=True)
class Line:
    at: str
    kind: str
    name: str
    project: str | None


def names(kind: str, drawers: Iterable[str]) -> frozenset[str]:
    """The names a line of this kind may have, given the names of the server's drawers."""
    if kind == "route":
        return frozenset(ROUTES)
    opened = frozenset({*drawers, HELP})
    return opened if kind == "drawer" else opened | {"project", OTHER}


def line(body: bytes, drawers: Iterable[str], projects: Iterable[str], now: datetime) -> Line:
    """The line a body asks for, or `Refused` where it asks for anything but known names."""
    try:
        asked = json.loads(body)
    except ValueError:
        asked = None
    if not isinstance(asked, dict) or set(asked) != {"kind", "name", "project"}:
        raise Refused("refused: a count is a kind, a name and a project")
    kind, name, project = asked["kind"], asked["name"], asked["project"]
    if kind not in KINDS or not isinstance(name, str) or name not in names(kind, drawers):
        raise Refused("refused: a count names a kind and a name the server has")
    if project != "" and (not isinstance(project, str) or project not in set(projects)):
        raise Refused("refused: a count names a project the server has, or none")
    return Line(state.iso(now), kind, name, project or None)


def append(path: Path, one: Line) -> None:
    """Append one line to the file, and past `CAP` keep only its newest lines in `KEEP`."""
    text = json.dumps(asdict(one), sort_keys=True) + "\n"
    with _LOCK:
        with path.open("a") as file:
            file.write(text)
            size = file.tell()
        if size <= CAP:
            return
        kept, room = [], KEEP
        for each in reversed(path.read_bytes().splitlines(keepends=True)):
            room -= len(each)
            if room < 0:
                break
            kept.append(each)
        fresh = path.with_name(f".{path.name}.{os.getpid()}")
        fresh.write_bytes(b"".join(reversed(kept)))
        fresh.replace(path)


def counts(path: Path, since: datetime, project: str | None = None) -> Counter[tuple[str, str]]:
    """How many lines of the file since `since` have each kind and name. It skips a line it
    cannot read, and with `project`, a line of another project."""
    try:
        text = path.read_text()
    except OSError:
        return Counter()
    found: Counter[tuple[str, str]] = Counter()
    for each in text.splitlines():
        try:
            one = json.loads(each)
            at = datetime.fromisoformat(one["at"])
            kind, name = one["kind"], one["name"]
        except (ValueError, TypeError, KeyError):
            continue
        if at >= since and (project is None or one.get("project") == project):
            found[(kind, name)] += 1
    return found


def arguments(shown: argparse.ArgumentParser) -> None:
    shown.add_argument(
        "--since", help="count from this time, the user's zone with none (default: 7 days ago)"
    )
    shown.add_argument("--project", help="count only what was opened on this project")


def report(path: Path, user: jsettings.Settings, now: datetime, args: argparse.Namespace) -> int:
    """Print the counts of a window: a first line with the total, then one line for each kind
    and name, by kind in the order of `KINDS` and the most opened first."""
    given = args.since
    at = state.when(given, user) if given else state.iso(now - WINDOW)
    if at is None:
        raise Refused(f"refused: --since {given!r} is not a time")
    since = datetime.fromisoformat(at)
    found = counts(path, since, args.project)
    print(f"jbus view usage: {sum(found.values())} since {user.stamp(since)}, from {path}")
    order: dict[str, Any] = {kind: n for n, kind in enumerate(KINDS)}
    ranked = sorted(found.items(), key=lambda kv: (order.get(kv[0][0], 9), -kv[1], kv[0][1]))
    for (kind, name), count in ranked:
        print(f"{kind:<7} {name:<10} {count}")
    return 0
