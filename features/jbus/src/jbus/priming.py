"""crew-router-pilot: while the pilot runs, each new crew or scout row launches on one of two
primings, and its launch record keeps which, as `priming`.

`trimmed` is the SKILL.md that `/crew` and `/scout` expand. `control` is the priming main had
before the trim, kept at `features/crew/control/` and `features/scout/control/`: the launch's first
line tells the thread to read that copy, by its path in the jstack source jbus runs from, in place
of the slash command, whatever harness the thread runs on. A new row gets the arm
with fewer rows of its role so far, the trimmed one on a tie, so the arms stay within one row of
each other however the rows launch. A row launched again keeps the arm its record names, so a
retry or a changed brief does not move it.

`jbus priming start` starts the pilot. `jbus priming stop <why>` sends every later row to the
control arm: a hard failure on the trimmed arm stops it, and the reason names the row.
`jbus priming` prints the rows of each arm. With no pilot started, every row launches as `/crew`
or `/scout` and its record names no arm. The home removes this module and the control copies
once it acts on the pilot's Result.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jbus
from jbriefs import skills
from jbus import queue, read_json, verbs, write_json
from jbus.launches import records

TRIMMED, CONTROL = "trimmed", "control"
ARMS = (TRIMMED, CONTROL)
COPIES = {
    queue.CREW: "features/crew/control/crew.md",
    queue.SCOUT: "features/scout/control/scout.md",
}
SLUG = r"[A-Za-z0-9][A-Za-z0-9-]*"


def copy(role: str) -> Path:
    """The control copy of `role`'s priming, in the jstack source jbus runs from."""
    return skills.root() / COPIES[role]


def file(state_dir: Path) -> Path:
    return state_dir / "priming.json"


def pick(counts: Counter[str], stopped: bool) -> str:
    """The arm of a new row: the control arm once the pilot is stopped, and otherwise the arm
    with fewer rows in `counts`, the trimmed one on a tie."""
    if stopped or counts[CONTROL] < counts[TRIMMED]:
        return CONTROL
    return TRIMMED


def tally(state_dir: Path, role: str) -> Counter[str]:
    """The rows of `role` on each arm, in every project: a row counts once, however many
    launch records it has."""
    kept: dict[tuple[str, str], str] = {}
    for path in sorted((state_dir / "launches").glob("*/*/*.json")):
        record = read_json(path, {})
        if (record.get("role") or queue.CREW) == role and record.get("priming") in ARMS:
            kept[(path.parent.parent.name, path.parent.name)] = record["priming"]
    return Counter(kept.values())


def arm(run: Any, slug: str, role: str) -> str:
    """The arm a launch of the row puts it on: the one a record of the row already names, or
    else `pick`'s. Nothing while no pilot is started."""
    named = [r["priming"] for _, r in records(run, slug, role) if r.get("priming") in ARMS]
    if named:
        return named[-1]
    pilot = read_json(file(run.config.state_dir), {})
    if not pilot.get("started"):
        return ""
    return pick(tally(run.config.state_dir, role), bool(pilot.get("stopped")))


def recorded(chosen: str) -> dict[str, str]:
    """The field a launch record gets for the arm: none while no pilot is started."""
    return {"priming": chosen} if chosen else {}


def first_line(role: str, slug: str, chosen: str) -> str:
    """The first line of the launch's message, which loads the arm's priming."""
    if chosen != CONTROL:
        return f"/{role} {slug}"
    return (
        f"Read `{copy(role)}` in full now, and follow it as the /{role} skill with the "
        f"arguments `{slug}`: it is the priming of crew-router-pilot's control arm."
    )


def asked_slug(role: str, asked: str) -> str:
    """The slug of a session whose first message launched `role` on either arm, or nothing."""
    plain = re.match(
        rf"\s*(?:/{role}\s+|<command-message>{role}</command-message>\s*"
        rf"<command-name>/{role}</command-name>\s*<command-args>)({SLUG})",
        asked,
    )
    control = re.match(
        rf"\s*Read `[^`]*/{re.escape(COPIES[role])}` in full now, and follow it as the "
        rf"/{role} skill with the arguments `({SLUG})`",
        asked,
    )
    found = plain or control
    return found[1] if found else ""


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        nargs="?",
        choices=("start", "stop"),
        help="start the pilot, or stop its trimmed arm; with none, print each arm's rows",
    )
    parser.add_argument("why", nargs="?", default="", help="for stop: the row and its failure")


def _run(args: argparse.Namespace, config: jbus.Config) -> int:
    path = file(config.state_dir)
    pilot = read_json(path, {})
    now = datetime.now(UTC).isoformat(timespec="seconds")
    if args.action == "start" and not pilot.get("started"):
        write_json(path, {"started": now})
        pilot = read_json(path, {})
    elif args.action == "stop":
        if not args.why.strip():
            print("refused: stop names the row and its hard failure: jbus priming stop '<why>'")
            return 2
        if not pilot.get("started"):
            print("refused: the pilot was never started")
            return 2
        write_json(path, {**pilot, "stopped": args.why.strip(), "stopped_at": now})
        pilot = read_json(path, {})
    if not pilot.get("started"):
        print("crew-router-pilot: not started: every row launches as /crew or /scout")
        return 0
    line = f"crew-router-pilot: started {pilot['started']}"
    if pilot.get("stopped"):
        line += f", trimmed arm stopped {pilot.get('stopped_at', '')}: {pilot['stopped']}"
    print(line)
    for role in (queue.CREW, queue.SCOUT):
        counts = tally(config.state_dir, role)
        print(f"{role}: {', '.join(f'{one} {counts[one]}' for one in ARMS)}")
    return 0


VERBS = (
    verbs.Verb(
        "priming",
        "crew-router-pilot: start it, stop its trimmed arm, or print each arm's rows",
        _arguments,
        _run,
    ),
)
