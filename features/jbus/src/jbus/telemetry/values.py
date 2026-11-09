"""The values a record's fields hold, read as the telemetry store keeps them: a time in UTC as
`STAMP` writes it, its local day, a log line's key, and a text, a count, a number or a mapping
where the record holds one (`jbus.telemetry.records`), and the SQL type of each column by its
name (`_columns`)."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, tzinfo
from typing import Any

Row = dict[str, Any]
"""One row of a table, by column."""
MACHINE = ""
"""The project of a row that is the machine's, as `jbus.alert.MACHINE` names its owner."""

STAMP = "%Y-%m-%dT%H:%M:%S.%fZ"
_WORDED = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})(?::(\d{2}))?(?: (\S+))?")


def utc(said: object, zone: tzinfo | None = None) -> str | None:
    """The time a record names, in UTC as `STAMP` writes it, or None where it names none.

    It reads the forms jbus writes: ISO 8601 with `+00:00` or `Z`, and `YYYY-MM-DD HH:MM` with
    or without seconds, then the zone's word (`EDT`) or nothing, in `zone`. Of an hour the
    clocks go back through, it takes the one whose word the time gives."""
    if not isinstance(said, str) or not said.strip():
        return None
    text = said.strip()
    found = _WORDED.fullmatch(text)
    if found:
        moment = datetime.fromisoformat(f"{found[1]}T{found[2]}:{found[3] or '00'}")
        here = zone or UTC
        word = found[4]
        local = moment.replace(tzinfo=here)
        if word and local.tzname() != word and moment.replace(tzinfo=here, fold=1).tzname() == word:
            local = moment.replace(tzinfo=here, fold=1)
        return local.astimezone(UTC).strftime(STAMP)
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime(STAMP)


def day(at: str | None, zone: tzinfo | None) -> str | None:
    """The local date of a time `utc` wrote, in `zone`, or the machine's zone for None."""
    if at is None:
        return None
    moment = datetime.strptime(at, STAMP).replace(tzinfo=UTC)
    return (moment.astimezone(zone) if zone else moment.astimezone()).date().isoformat()


def key(line: str, before: int) -> str:
    """The key of a log's line: the hash of the line and of the count of equal lines before it,
    as `jbus.wake.entries` makes an event's id."""
    return hashlib.sha256(f"{line}#{before + 1}".encode()).hexdigest()[:16]


def _length(value: object) -> int | None:
    """The length of a text, or None where there is no text."""
    return len(value) if isinstance(value, str) else None


def _count(value: object) -> int | None:
    """The length of a list, or None where there is no list."""
    return len(value) if isinstance(value, list) else None


def _text(value: object) -> str | None:
    """A label as it is, or None where the record holds no string there."""
    return value if isinstance(value, str) else None


def _number(value: object) -> int | None:
    """A whole number as it is, or None."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pull(value: object) -> int | None:
    """The number of the pull request a row's `pr` names, as a URL or `#<n>`, or None."""
    if not isinstance(value, str):
        return _number(value)
    found = re.search(r"/pull/(\d+)", value) or re.fullmatch(r"#?(\d+)", value.strip())
    return int(found[1]) if found else None


SPENT = ("units", "runs", "input", "cached", "written", "output")
KINDS = ("first", "reviews", "fixes", "sends", "homes", "scouts", "capped")
"""The units of a day's spend by kind, as `jgauge.spend.COLUMNS` names them."""
SEVERITIES = ("errors", "warnings", "infos", "others", "dismissed")
"""The counts of a review round's findings by severity, as `jbus.reviewed.round_lines` writes
them: `others` of a severity none of the three, and `dismissed` those its lead dismissed."""


def _columns(*names: str) -> tuple[tuple[str, str], ...]:
    """Columns by name, typed by their suffix: `_len`, counts and numbers are INTEGER."""
    whole = {
        "gate",
        "doors",
        "picks",
        "run",
        "job",
        "attempt",
        "pr",
        "steps",
        "workers",
        "tests",
        "signs",
        "number",
        "options",
        "priority",
        "pushes",
        "holds",
        "on_hold",
        "keeps",
        "bytes",
        "waiting",
        "instances",
        *SPENT,
        *KINDS,
        "checked",
        "round_number",
        "scoped",
        "sections",
        "met",
        "done_when",
        *SEVERITIES,
        "found",
    }
    real = {"slowest_s", "tail_s", "seconds", "minutes"}
    return tuple(
        (
            name,
            "INTEGER"
            if name.endswith("_len") or name in whole
            else "REAL"
            if name in real
            else "TEXT",
        )
        for name in names
    )
