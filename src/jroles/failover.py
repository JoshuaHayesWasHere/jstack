"""Which Claude provider instance a launch or a nudge goes to: failover when one is capped.

A usage limit (the 5-hour or the weekly one) caps a provider instance until its reset. T3
Code shows it as a turn that ends `failed` with the text

    You've hit your weekly limit · resets Oct 18, 4pm (America/New_York)

`read_limit` reads that text, and `mark` keeps the reset as the instance's capped-until in
`capped.json`, one file for jbus and for `jroles`: `{"<instanceId>": {"until", "kind", "at"}}`.
`choose` is the one place that says where to go: the primary instance while it is not capped,
the fallback while the primary is, and nowhere (`Choice.instance` is None, with the earliest
reset) while both are. A cap that has passed is not kept in mind: nothing clears it, `until`
is simply behind the clock, so the next launch and the next nudge go back to the primary.

The pair is `PAIR`, a default in code: `claudeAgent` first, `claudeAgent_claude_prime` after
it. A selection that names an instance outside the pair, or another provider, is left as it is.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jroles import Selection

PROVIDER = "claudeAgent"
PRIMARY, FALLBACK = "claudeAgent", "claudeAgent_claude_prime"
PAIR = (PRIMARY, FALLBACK)
BLIND = timedelta(hours=1)
FILE = "capped.json"
WAIT = 75

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
class Limit:
    """A usage limit a failure reported: which one (`weekly`, `session`, ...), when it
    resets, and the line it was read from."""

    kind: str
    until: datetime
    text: str


@dataclass(frozen=True)
class Choice:
    """Where a launch or a nudge goes. `instance` is None while both are capped, and
    `until` is then the earlier reset. `why` is empty when the primary is not capped."""

    instance: str | None
    why: str
    until: datetime | None = None


def _reset(when: str, zone: str, now: datetime) -> datetime | None:
    found = _WHEN.fullmatch(when.strip())
    if not found:
        return None
    try:
        tz = ZoneInfo(zone) if zone else UTC
    except (ZoneInfoNotFoundError, ValueError):
        return None
    hour = int(found["hour"]) % 12 + (12 if found["half"].lower() == "pm" else 0)
    minute = int(found["minute"] or 0)
    here = now.astimezone(tz)
    if found["month"]:
        month = found["month"].lower()
        if month not in _MONTHS:
            return None
        try:
            at = here.replace(
                month=_MONTHS.index(month) + 1,
                day=int(found["day"]),
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
        except ValueError:
            return None
        if at < here - timedelta(days=180):
            at = at.replace(year=at.year + 1)
    else:
        at = here.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if at <= here:
            at += timedelta(days=1)
    return at.astimezone(UTC)


def read_limit(text: str, now: datetime) -> Limit | None:
    """The usage limit a text reports, or None for a text that reports none.

    The reset is read in the zone the text names (UTC where it names none). A limit whose
    reset cannot be read holds for `BLIND` from `now`: it is a cap all the same."""
    found = _LIMIT.search(text)
    if not found:
        return None
    until = _reset(found["when"] or "", found["zone"] or "", now) if found["when"] else None
    return Limit((found["kind"] or "usage").strip(), until or now + BLIND, found[0].strip())


def path() -> Path:
    """`capped.json` in jbus's state directory, where `jbus` writes it."""
    state = os.environ.get("JBUS_STATE_DIR") or Path.home() / ".local" / "state" / "jbus"
    return Path(state) / FILE


def load(file: Path) -> dict[str, datetime]:
    """Each instance's capped-until, as the file has it. An entry that does not read is
    left out: a state that cannot be read caps nothing."""
    try:
        kept = json.loads(file.read_text())
    except (OSError, ValueError):
        return {}
    found: dict[str, datetime] = {}
    for instance, entry in kept.items() if isinstance(kept, dict) else ():
        try:
            until = datetime.fromisoformat(entry["until"])
        except (KeyError, TypeError, ValueError):
            continue
        found[str(instance)] = until if until.tzinfo else until.replace(tzinfo=UTC)
    return found


def mark(file: Path, instance: str, limit: Limit, now: datetime) -> bool:
    """Keep that `instance` is capped until the limit's reset, the later of that and what the
    file already has. True when the file changed: the same failure read again changes
    nothing."""
    kept = load(file)
    if instance in kept and kept[instance] >= limit.until:
        return False
    try:
        raw = json.loads(file.read_text())
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    raw[instance] = {
        "until": limit.until.isoformat(),
        "kind": limit.kind,
        "at": now.isoformat(),
    }
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_name(file.name + ".tmp")
    temporary.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, file)
    return True


def capped(kept: dict[str, datetime], instance: str, now: datetime) -> datetime | None:
    """When `instance` is free again, or None while it is not capped."""
    until = kept.get(instance)
    return until if until is not None and until > now else None


def choose(kept: dict[str, datetime], now: datetime) -> Choice:
    """The instance a launch or a nudge goes to, and why it is not the primary."""
    first, second = (capped(kept, instance, now) for instance in PAIR)
    if first is None:
        return Choice(PRIMARY, "")
    if second is None:
        return Choice(FALLBACK, f"{PRIMARY} is capped until {first.isoformat()}")
    earlier = min(first, second)
    both = f"{PRIMARY} and {FALLBACK} are both capped until {earlier.isoformat()}"
    return Choice(None, both, earlier)


def select(
    selection: Selection, kept: dict[str, datetime], now: datetime
) -> tuple[Choice, Selection]:
    """The selection a launch is sent with, and the choice that made it.

    Only a Claude selection on the primary (named or by default) is moved. While both are
    capped the selection is returned as it is, and the choice has no instance: the launch
    waits."""
    if not movable(selection.provider, selection.instance_id):
        return Choice(selection.instance_id, ""), selection
    choice = choose(kept, now)
    if choice.instance in (None, PRIMARY):
        return choice, selection
    return choice, replace(selection, instance_id=choice.instance)


def movable(provider: str | None, instance: str | None) -> bool:
    """Whether a selection is on the primary, named or by default, which failover may move."""
    return instance == PRIMARY or (instance is None and provider == PROVIDER)


def select_json(
    given: dict[str, Any], kept: dict[str, datetime], now: datetime
) -> tuple[Choice, dict[str, Any]]:
    """`select` for a `modelSelection` as jbus's config has it: a dict that names an
    `instanceId`, and the provider where it names none."""
    instance = given.get("instanceId")
    if not movable(given.get("provider"), instance):
        return Choice(instance, ""), given
    choice = choose(kept, now)
    if choice.instance in (None, PRIMARY):
        return choice, given
    return choice, {**given, "instanceId": choice.instance}
