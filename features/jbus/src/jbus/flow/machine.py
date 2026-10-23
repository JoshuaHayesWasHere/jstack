"""What jbus's journal says about the machine: passes, no room, caps, and passes that failed.

`journalctl --user -u jbus -o short-iso` prints one line a message, each with its time. A pass
starts with systemd's `Starting jbus` line, and what the pass says follows it. `read` splits
the lines into passes, and `machine` gives each pass the reasons it could not launch: no room
on the machine, every account capped, `max_running` reached, dispatch off. A pass's reason
holds from its start to the next pass's start, and at most `HOLD` past its start, since a
timer that stopped proves nothing about the machine. A gap of more than `HOLD` between two
passes is time jbus did not run, and so is a pass that failed, up to the next pass.

The reasons are worded with their numbers taken out, so that the same cause is one reason.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

HOLD = timedelta(minutes=10)
LINE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:?\d\d) \S+ ([^:]+): (.*)$")
STARTS = "Starting jbus"
NO_ROOM = re.compile(r"\bno room: (.*)$")
LOAD = re.compile(r"load [\d.]+ is at or over (\d+)% of \d+ cores")
CAPPED = re.compile(r"\bno launch: .* (?:are|is) (?:both |all )?capped until")
ACCOUNT = re.compile(r"^capped (\S+): (\S+) until")
MAX_RUNNING = re.compile(r"^max_running is \d+ across all projects")
FAILED = re.compile(r"(Failed with result|^pass failed )")
GITHUB = re.compile(r"could not ask GitHub")
WAKE = re.compile(r"^wake failed (\S+): (.*)$")
DISPATCH_OFF = "dispatch is off in the config"
NUMBERS = re.compile(r"\d+(\.\d+)?")


@dataclass
class Pass:
    """One pass: its start and what it said."""

    start: datetime
    said: list[str] = field(default_factory=list)


@dataclass
class Machine:
    """What the journal gives for a window. Each list of reasons holds `(start, end, why)`."""

    passes: int = 0
    first: datetime | None = None
    no_room: list[tuple[datetime, datetime, str]] = field(default_factory=list)
    down: list[tuple[datetime, datetime, str]] = field(default_factory=list)
    failed: int = 0
    github: int = 0
    wakes: dict[str, int] = field(default_factory=dict)
    waited: dict[str, int] = field(default_factory=dict)


def journal(since: datetime, until: datetime) -> list[str]:
    """Return jbus's journal lines for the window, or none where `journalctl` cannot say."""
    try:
        asked = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                "jbus",
                "--since",
                since.strftime("%Y-%m-%d %H:%M:%S %z"),
                "--until",
                until.strftime("%Y-%m-%d %H:%M:%S %z"),
                "-o",
                "short-iso",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return asked.stdout.splitlines() if asked.returncode == 0 else []


def read(lines: Iterable[str]) -> list[Pass]:
    """Split journal lines into passes. Lines before the first pass start are left out."""
    passes: list[Pass] = []
    for line in lines:
        found = LINE.match(line)
        if not found:
            continue
        try:
            when = datetime.fromisoformat(found[1])
        except ValueError:
            continue
        text = found[3]
        if text.startswith(STARTS):
            passes.append(Pass(when))
        elif passes:
            passes[-1].said.append(text)
    return passes


def reasons(said: Iterable[str]) -> list[str]:
    """Return why a pass could not launch, one reason a cause, numbers out."""
    found: list[str] = []
    for text in said:
        why = ""
        if room := NO_ROOM.search(text):
            load = LOAD.search(room[1])
            why = f"no room: load at or over {load[1]}% of the cores" if load else ""
            why = why or f"no room: {NUMBERS.sub('N', room[1])}"
        elif CAPPED.search(text):
            why = "no launch: every account capped"
        elif account := ACCOUNT.match(text):
            why = f"account {account[1]} capped ({account[2]})"
        elif MAX_RUNNING.match(text):
            why = "max_running reached across all projects"
        elif text == DISPATCH_OFF:
            why = "dispatch off in the config"
        if why and why not in found:
            found.append(why)
    return found


def machine(lines: Iterable[str], since: datetime, until: datetime) -> Machine:
    """Return what the journal says about the window."""
    passes = [one for one in read(lines) if since <= one.start <= until]
    made = Machine(passes=len(passes), first=passes[0].start if passes else None)
    for index, one in enumerate(passes):
        after = passes[index + 1].start if index + 1 < len(passes) else until
        end = min(after, one.start + HOLD)
        for why in reasons(one.said):
            made.no_room.append((one.start, end, why))
        if after - one.start > HOLD:
            made.down.append((end, after, "no pass ran"))
        if any(FAILED.search(text) for text in one.said):
            made.down.append((one.start, end, "the pass failed"))
        for text in one.said:
            made.failed += bool(FAILED.search(text))
            made.github += bool(GITHUB.search(text))
            if wake := WAKE.match(text):
                key = f"{wake[1]}: {NUMBERS.sub('N', wake[2]).split(': ')[0]}"
                made.wakes[key] = made.wakes.get(key, 0) + 1
            if NO_ROOM.search(text) and text.startswith("wait "):
                slug = text.split()[1].rstrip(":")
                made.waited[slug] = made.waited.get(slug, 0) + 1
    return made
