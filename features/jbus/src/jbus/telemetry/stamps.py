"""The time a record names, kept in UTC in one form of fixed width (`STAMP`), so that text
order is time order, and its local `day`, since SQLite has no zone of its own to bucket by."""

from __future__ import annotations

import re
from datetime import UTC, datetime, tzinfo

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
