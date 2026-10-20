"""The ledger: how much of each provider instance's usage windows is used, and when each resets.

The ledger is one file for each instance, a line for each window, as `room.sh` reads it:

    five_hour 23.5 1792353600
    seven_day 100 1792440000

The window is `five_hour` or `seven_day`, the share is percent used, and the reset is a Unix
time. The built-in instance, `claudeAgent`, keeps the file `LIMITS` names
(`~/.local/state/claude/limits` where it names none), and every other instance the file beside
it, `<LIMITS>.<instanceId>`. Three writers keep them: `jgauge limits`, ahead of time, every two
minutes, from each Claude account's own usage (`jgauge.limits`); `hooks/limits.sh`, from what
Claude Code hands a status line, for the instance its `CLAUDE_CONFIG_DIR` is the home of; and
`jbus`, from a turn T3 Code ended on a usage limit, at 100 until the reset that failure names
(`cap_of`). `room.sh` and `jroles` read them.

`merge` is the one rule every writer keeps: for an instance and a window, two resets under
`SAME` apart are one window, which keeps the larger share and the later reset; otherwise the
later reset wins. A writer floors its reset to the second, and the usage endpoint's reset moves
a second either way from call to call, so one window comes as 1792531799 from one writer and
1792531800 from another: a lower share of it never replaces a cap. So the same failure or the
same reading merged twice changes nothing, and a window that reset is replaced by the next one.

An instance is full at `FULL`, a real cap, for a move off a running thread; a new launch counts
it full earlier, at the user's `headroom` (`jsettings`), so it is passed by before the cap.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WINDOWS = ("five_hour", "seven_day")
FULL = 100.0
BLIND = timedelta(hours=1)
SAME = 300

_ROW = re.compile(r"(five_hour|seven_day) (\d+(?:\.\d+)?) (\d+)")
_ITEM = re.compile(r":(five_hour|seven_day):(\d+)$")
_LIMIT = re.compile(
    r"You.ve hit your (?:(?P<kind>[\w -]*?) )?limit\b[^\n]*?"
    r"(?:resets\s+(?P<when>[^()\n]+?)(?:\s*\((?P<zone>[^)\n]+)\))?)?\s*$",
    re.M,
)
_WHEN = re.compile(
    r"(?:(?P<month>[A-Za-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2}),?\s+)?"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<half>[ap]m)",
    re.I,
)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


@dataclass(frozen=True)
class Record:
    """One instance's use of one window: percent used, and the Unix time it resets."""

    instance: str
    window: str
    used: float
    resets: int

    def line(self) -> str:
        return f"{self.window} {self.used:g} {self.resets}"

    def full(self, now: datetime, at: float = FULL) -> bool:
        return self.used >= at and self.resets > now.timestamp()


Ledger = Mapping[tuple[str, str], Record]


BUILT_IN = "claudeAgent"


def path() -> Path:
    """The file `LIMITS` names, the built-in instance's, as `room.sh` and `hooks/limits.sh`
    find it."""
    named = os.environ.get("LIMITS")
    return Path(named) if named else Path.home() / ".local" / "state" / "claude" / "limits"


def file_of(instance: str, base: Path | None = None) -> Path:
    """The file of `instance`'s windows."""
    base = base or path()
    return base if instance == BUILT_IN else base.with_name(f"{base.name}.{instance}")


def parse(instance: str, text: str) -> dict[tuple[str, str], Record]:
    """The records an instance's file holds. A line that is not one is left out."""
    rows = (_ROW.fullmatch(line.strip()) for line in text.splitlines())
    found = (Record(instance, row[1], float(row[2]), int(row[3])) for row in rows if row)
    return merge({}, found)


def merge(ledger: Ledger, records: Iterable[Record]) -> dict[tuple[str, str], Record]:
    """The ledger with `records` in it, by the rule of the module."""
    merged = dict(ledger)
    for record in records:
        key = (record.instance, record.window)
        kept = merged.get(key)
        if kept is None or record.resets - kept.resets >= SAME:
            merged[key] = record
        elif abs(record.resets - kept.resets) < SAME:
            used = max(record.used, kept.used)
            merged[key] = Record(*key, used, max(record.resets, kept.resets))
    return merged


def _text(file: Path) -> str:
    try:
        return file.read_text()
    except (OSError, UnicodeDecodeError):
        return ""


def read(instances: Iterable[str], base: Path | None = None) -> dict[tuple[str, str], Record]:
    """The ledger of `instances`. A file that is not there or cannot be read caps nothing."""
    ledger: dict[tuple[str, str], Record] = {}
    for instance in instances:
        ledger.update(parse(instance, _text(file_of(instance, base))))
    return ledger


def write(record: Record, base: Path | None = None) -> bool:
    """Merge `record` into its instance's file, written whole and renamed into place. True
    when the file changed."""
    file = file_of(record.instance, base)
    before = _text(file)
    merged = merge(parse(record.instance, before), [record])
    text = "".join(f"{merged[key].line()}\n" for key in sorted(merged))
    if text == before:
        return False
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_name(f"{file.name}.{os.getpid()}")
    temporary.write_text(text)
    os.replace(temporary, file)
    return True


def capped_until(
    ledger: Ledger, instance: str, now: datetime, full: float = FULL
) -> datetime | None:
    """When every window of `instance` used to `full` or more has reset, or None while it has
    headroom."""
    resets = [
        record.resets
        for (named, _), record in ledger.items()
        if named == instance and record.full(now, full)
    ]
    return datetime.fromtimestamp(max(resets), UTC) if resets else None


@dataclass(frozen=True)
class Cap:
    """A usage limit a failed turn ended on: its window, its reset, and the line it was read
    from, for the carry-on to quote."""

    window: str
    resets: datetime
    text: str

    def record(self, instance: str) -> Record:
        return Record(instance, self.window, FULL, int(self.resets.timestamp()))


def cap_of(items: Iterable[Mapping[str, object]], now: datetime) -> Cap | None:
    """The usage limit a run's items report, or None for a run that hit none.

    T3 Code ends such a run with a `system_notice` whose itemId ends `:<window>:<reset>`,
    which is read first, once its percent-encoding is undone: T3 Code writes the colons of
    the provider's own id as `%3A`. Where no item has one, the text is read: `You've hit your weekly
    limit · resets Oct 18, 4pm (America/New_York)`, `weekly` the seven-day window and any
    other the five-hour one, the reset in the zone it names. A text whose reset cannot be read
    holds for `BLIND` from `now`."""
    items = list(items)
    noted = (_ITEM.search(urllib.parse.unquote(str(item.get("itemId") or ""))) for item in items)
    said = next(
        (found for item in items if (found := _LIMIT.search(str(item.get("text") or "")))), None
    )
    text = said[0].strip() if said else ""
    named = next((found for found in noted if found), None)
    if named:
        window, resets = named[1], datetime.fromtimestamp(int(named[2]), UTC)
        return Cap(window, resets, text or f"the {window} limit")
    if said is None:
        return None
    window = "seven_day" if "week" in (said["kind"] or "").lower() else "five_hour"
    resets = _reset(said["when"], said["zone"] or "", now) if said["when"] else None
    return Cap(window, resets or now + BLIND, text)


def _reset(when: str, zone: str, now: datetime) -> datetime | None:
    found = _WHEN.fullmatch(when.strip())
    if not found:
        return None
    try:
        tz = ZoneInfo(zone) if zone else UTC
    except (ZoneInfoNotFoundError, ValueError):
        return None
    hour = int(found["hour"]) % 12 + (12 if found["half"].lower() == "pm" else 0)
    here = now.astimezone(tz)
    at = here.replace(hour=hour, minute=int(found["minute"] or 0), second=0, microsecond=0)
    if found["month"]:
        month = found["month"].lower()
        if month not in _MONTHS:
            return None
        try:
            at = at.replace(month=_MONTHS.index(month) + 1, day=int(found["day"]))
        except ValueError:
            return None
        if at < here - timedelta(days=180):
            at = at.replace(year=at.year + 1)
    elif at <= here:
        at += timedelta(days=1)
    return at.astimezone(UTC)
