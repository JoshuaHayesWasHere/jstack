"""What the threads noticed: each record of `noticed.json`, newest first. Each record has its
task, when a pass first found it, its mark, and what took it or why it was dropped. Each poll of
the first screen gets three things: every new record, the newest `MARKED` of the marked records,
and the count of the older marked records. A first pass marks hundreds of records, so the poll
only counts the older ones, and `jbus noticed --all` prints them. The wait band counts the new
records and opens this panel. Where there is no new record, the wait band says nothing.

The panel reads `noticed.json` and writes nothing. A pass writes the file, and
`jbus noticed take|drop` marks its records. Where the file does not exist yet, there is no
record. A file that does not parse is a source that could not be read.
"""

from __future__ import annotations

from typing import Any

from jbus import noticed
from jbus.view.state import WORDS, Read, kept, text, when

FIRST = True
_RECORD = {
    key: None
    for key in (
        "key",
        "slug",
        "kind",
        "section",
        "text",
        "seen_at",
        "mark",
        "row",
        "why",
        "by",
        "at",
    )
}
SHAPE = {"noticed": [_RECORD], "noticed_older": None}
MARKED = 20


def _kept(read: Read) -> list[noticed.Record] | None:
    """The records: an empty list where no pass has kept any yet, or None for a file that
    does not parse."""
    try:
        return (noticed.read(read.state) or []) if read.name else None
    except noticed.Unparsable:
        return None


SOURCES = (kept(noticed.NAME, lambda read: read.once(_kept), 90),)


def build(read: Read) -> dict[str, Any]:
    found = [
        {
            "key": text(one.key, 120),
            "slug": text(one.slug, 80),
            "kind": text(one.kind, 20),
            "section": text(one.section, 120),
            "text": text(one.text, WORDS),
            "seen_at": when(one.seen_at),
            "mark": text(one.mark, 20),
            "row": text(one.row, 80),
            "why": text(one.why),
            "by": text(one.by, 80),
            "at": when(one.at, read.user),
        }
        for one in read.once(_kept) or []
    ]
    found.sort(key=lambda one: (one["seen_at"] or "", one["key"]), reverse=True)
    fresh = [one for one in found if one["mark"] == noticed.NEW]
    shown = fresh + [one for one in found if one["mark"] != noticed.NEW][:MARKED]
    shown.sort(key=lambda one: (one["seen_at"] or "", one["key"]), reverse=True)
    return {"noticed": shown, "noticed_older": len(found) - len(shown)}
