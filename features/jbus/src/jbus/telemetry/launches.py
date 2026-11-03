"""The arm each launch of a row is on, from jbus's launch records: the store's `launch_arms`.

jbus writes one record for each launch of a row, `launches/<project>/<slug>/<sha 12>.json` in its
state directory (`jbus.launches.records`), first as an `intent` and then as `launched`. A record
written while a dial ran names, by dial, the arm the launch is on (`arms`), `off` while the dial's
pilot was not started. crew-router-pilot was that dial, and it ended with the pilot's read
(priming-pilot-read), so no record jbus writes now names one. The store keeps one row for each
dial of each launched record, keyed by the record's key and the dial, and never updates one: a
row launched again under the same brief, which keeps its arm, is the row it was.

A record from before `arms` that names `priming`, the pilot's own field, gives that arm of
`crew-router-pilot`. A record that names neither names no dial: from before the store could tell,
or from after the pilot ended. Its one row has no dial and no arm, and `covered` 0. No arm is
guessed for it.

A build reads only the records whose time is at or after the newest one it read (`cursors`, under
the machine's project), and of those only the launched ones, so an `intent` is read again once it
is rewritten as launched.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import tzinfo
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jbus
from jbus import queue, read_json
from jbus.telemetry import cursors, records, stamps

if TYPE_CHECKING:
    from jbus.telemetry import Built

TABLE = "launch_arms"
PILOT = "crew-router-pilot"
"""The dial a record's `priming` field is the arm of."""
PILOT_ARMS = ("trimmed", "control")
COLUMNS = ("slug", "role", "dial", "arm", "covered", "thread", "at")
TABLE_SQL = (
    f"CREATE TABLE {TABLE} (project TEXT NOT NULL, key TEXT NOT NULL, slug TEXT, role TEXT, "
    "dial TEXT, arm TEXT, covered INTEGER, thread TEXT, at TEXT, day TEXT, "
    "PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    f"CREATE INDEX {TABLE}_day ON {TABLE} (day);\n"
    f"CREATE INDEX {TABLE}_row ON {TABLE} (project, slug);\n"
)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def rows(record: dict[str, Any], slug: str, zone: tzinfo | None) -> list[tuple[str, records.Row]]:
    """The rows of one launch record, by key: one for each dial it names, or one that is not
    covered, and none for a record that is not launched."""
    if record.get("state") != "launched":
        return []
    base = _text(record.get("key")) or slug
    said = record.get("arms")
    named = {
        dial: arm
        for dial, arm in (said.items() if isinstance(said, dict) else ())
        if isinstance(dial, str) and isinstance(arm, str)
    }
    if not named and record.get("priming") in PILOT_ARMS:
        named = {PILOT: record["priming"]}
    common = {
        "slug": slug,
        "role": _text(record.get("role")) or queue.CREW,
        "thread": _text(record.get("thread")),
        "at": stamps.utc(record.get("at"), zone),
    }
    if not named:
        return [(base, {**common, "dial": None, "arm": None, "covered": 0})]
    return [
        (f"{base} {dial}", {**common, "dial": dial, "arm": arm, "covered": 1})
        for dial, arm in sorted(named.items())
    ]


def _files(config: jbus.Config, since: int) -> Iterator[tuple[str, str, Path, int]]:
    """Each launch record of a project of the config written at or after `since`, in ns, with its
    project, its slug and its time."""
    for project in config.projects:
        for path in sorted((config.state_dir / "launches" / project.name).glob("*/*.json")):
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                continue
            if mtime >= since:
                yield project.name, path.parent.name, path, mtime


def read(
    connection: sqlite3.Connection, config: jbus.Config, zone: tzinfo | None, built: Built
) -> None:
    """Keep a row for each dial of each launched record the store has not kept."""
    held = cursors.held(connection, records.MACHINE, TABLE)
    since = held[4] if held and held[4] is not None else 0
    found = []
    newest = since
    for project, slug, path, mtime in _files(config, since):
        newest = max(newest, mtime)
        record = read_json(path, {})
        built.bytes += path.stat().st_size
        for key, row in rows(record, slug, zone):
            day = stamps.day(row["at"], zone)
            found.append((project, key, *(row[name] for name in COLUMNS), day))
    names = ", ".join(("project", "key", *COLUMNS, "day"))
    marks = ", ".join("?" for _ in range(len(COLUMNS) + 3))
    connection.execute("BEGIN")
    before = connection.total_changes
    connection.executemany(f"INSERT OR IGNORE INTO {TABLE} ({names}) VALUES ({marks})", found)
    built.rows[TABLE] += connection.total_changes - before
    cursors.keep(connection, records.MACHINE, TABLE, None, None, None, None, newest)
    connection.execute("COMMIT")
