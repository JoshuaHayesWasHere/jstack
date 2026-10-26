"""Replay one day's launches of a project under the launch caps, `max_per_home` and
`max_per_project` (`jbus.dispatch.Caps`), and print the peak crews out per home and for the
project, as they were and as the caps would have held them.

    uv run python features/jbus/tests/launch_caps_replay.py [--day 2026-10-26] [--project jstack]

It reads `item.approved`, `item.launched` and `item.done` from the project's `events.jsonl`. A
crew is out from its launch until its row's `item.done`, or until the day's end when it has none.
That is the most a crew can count: a pass counts a crew thread only while T3 Code lists it as at
work. A row's home is the one its queued brief names (`jbriefs.home.home_of`).

The replay keeps each crew's real length, from its launch to its row's end. A row is ready at its
real launch, so what held it then (its depends, `jgauge room`) still holds it. At each launch and
each end, the crews that ended leave, and the rows that are ready launch in the order they were
ready, each while `Caps.full` leaves its home room.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jbriefs.home import home_of
from jbus import MAX_PER_HOME, MAX_PER_PROJECT, queue
from jbus.dispatch import Caps

ZONE = ZoneInfo("America/New_York")
ROW = re.compile(r" row (\S+) ")


@dataclass
class Crew:
    slug: str
    home: Path
    approved: datetime | None
    launched: datetime
    ended: datetime | None

    def length(self, until: datetime) -> timedelta:
        return (self.ended or until) - self.launched


def crews(events: Path, state: Path, home: Path, start: datetime, end: datetime) -> list[Crew]:
    """Each row launched in [start, end), with its approval before the launch and its first end
    after it."""
    seen: dict[str, dict[str, list[datetime]]] = {}
    for line in events.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = (event or {}).get("event") or ""
        found = ROW.search(event.get("line") or "") if kind.startswith("item.") else None
        if found and kind in ("item.approved", "item.launched", "item.done"):
            at = datetime.fromisoformat(event["at"])
            seen.setdefault(found[1], {}).setdefault(kind, []).append(at)
    made = []
    for slug, kinds in seen.items():
        launches = sorted(at for at in kinds.get("item.launched", []) if start <= at < end)
        if not launches:
            continue
        at = launches[0]
        approvals = [one for one in kinds.get("item.approved", []) if one <= at]
        ends = sorted(one for one in kinds.get("item.done", []) if one >= at)
        brief = queue.brief(state, slug) or ""
        made.append(
            Crew(
                slug,
                home_of(home, brief),
                max(approvals, default=None),
                at,
                ends[0] if ends else None,
            )
        )
    return sorted(made, key=lambda crew: (crew.launched, crew.approved or crew.launched))


def peaks(spans: list[tuple[Crew, datetime, datetime]]) -> tuple[Counter, dict, int, datetime]:
    """The peak crews out per home, with when, and for the project, with when."""
    moves = sorted(
        [(at, 1, crew.home) for crew, at, _ in spans]
        + [(at, -1, crew.home) for crew, _, at in spans],
        key=lambda move: (move[0], move[1]),
    )
    now: Counter = Counter()
    top: Counter = Counter()
    when: dict = {}
    most, most_at = 0, moves[0][0] if moves else datetime.min
    for at, step, home in moves:
        now[home] += step
        if now[home] > top[home]:
            top[home], when[home] = now[home], at
        if now.total() > most:
            most, most_at = now.total(), at
    return top, when, most, most_at


def replay(found: list[Crew], caps: Caps, until: datetime) -> list[tuple[Crew, datetime, datetime]]:
    """Launch each crew at its ready time or later, while the caps leave its home room."""
    waiting = list(found)
    out: list[tuple[Crew, datetime, datetime]] = []
    times = sorted({crew.launched for crew in found})
    while waiting:
        now = times.pop(0)
        caps.out = Counter(crew.home for crew, began, ended in out if began <= now < ended)
        for crew in [one for one in waiting if one.launched <= now]:
            if not caps.full(crew.home):
                ended = now + crew.length(until)
                out.append((crew, now, ended))
                caps.add(crew.home)
                waiting.remove(crew)
                times = sorted(set(times) | {ended})
        if not times and waiting:
            raise SystemExit("the replay ran out of times with rows still waiting")
    return out


def name(home: Path, root: Path) -> str:
    return "root" if home == root else home.name


def stamp(at: datetime) -> str:
    return at.astimezone(ZONE).strftime("%H:%M")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", default="2026-10-26", help="the day, in New York time")
    parser.add_argument("--project", default="jstack")
    parser.add_argument("--per-home", type=int, default=MAX_PER_HOME)
    parser.add_argument("--per-project", type=int, default=MAX_PER_PROJECT)
    args = parser.parse_args()
    state = Path.home() / ".local/state/jbus" / args.project
    home = Path.home() / ".local/state/home" / args.project
    start = datetime.fromisoformat(args.day).replace(tzinfo=ZONE)
    end = start + timedelta(days=1)
    found = crews(state / "events.jsonl", state, home, start, end)
    until = min(end, max((one.ended or one.launched for one in found), default=end))
    real = [(crew, crew.launched, crew.ended or until) for crew in found]
    caps = Caps(args.project, home, args.per_home, args.per_project)
    capped = replay(found, caps, until)
    print(
        f"{args.project} on {args.day}: {len(found)} launches, a crew out from its launch to "
        f"its row's end; caps {args.per_home} per home, {args.per_project} per project"
    )
    for title, spans in (("as launched", real), ("under the caps", capped)):
        top, when, most, most_at = peaks(spans)
        print(f"{title}: the project peaked at {most} crews out, at {stamp(most_at)}")
        for one in sorted(top, key=lambda one: name(one, home)):
            print(f"  {name(one, home)}: {top[one]} at {stamp(when[one])}")
    late = sorted(
        ((began - crew.launched, crew) for crew, began, _ in capped if began > crew.launched),
        key=lambda pair: -pair[0],
    )
    print(f"held by a cap: {len(late)} launches")
    for wait, crew in late:
        minutes = int(wait.total_seconds() // 60)
        print(
            f"  {crew.slug} ({name(crew.home, home)}): {minutes} min after {stamp(crew.launched)}"
        )


if __name__ == "__main__":
    main()
