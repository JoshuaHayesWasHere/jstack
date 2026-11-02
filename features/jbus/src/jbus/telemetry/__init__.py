"""`jbus telemetry`: compile every project's records into one SQLite file, with KPI views.

The store is `telemetry.sqlite` in jbus's state directory, in WAL mode, so a reader never waits
on the build. It has one table for each record file of each project (`jbus.telemetry.records`):
the jbus logs, the CI ledger, the home's `merge.log`, the records `jbus.history` and
`jbus.spent` keep, five snapshots, the machine's log of its passes, and the messages of T3
Code's threads (`jbus.telemetry.messages`). Its views give the KPIs (`jbus.telemetry.schema`).
It keeps a row forever, and keeps no text of a message: ids, times, counts, labels and the
length of each text.

A build reads only what is new. A log is read on from `cursors`, the file's inode, the hash of
its first line and the offset its last build read to, and only to its last newline, so a line
still being written waits for the next build. A log whose inode or first line changed, or that
is shorter than the offset, is read again from the start: its rows are keyed by their content
(`records.key`), so a line read twice is one row. A snapshot is read again when its inode, size
or time changed. Each file's rows and its cursor are written in one transaction, so a build
stopped at any point leaves each file either read or not, and the next build reads on from
there. So a build run twice adds nothing the second time, and a build run each pass ends as a
build from nothing would (`--rebuild`), apart from the rows the sources have since dropped.

Each pass runs a build after the launches (`CHORES`), before any project's second half, where
`jbus.chores.daily` trims `events.jsonl` to 14 days. The trim drops only the lines this store
holds (`copied`), so no event is lost to it: a line the store has not read stays in the file
until it has. A pass reads at most `PASS_BYTES` of new files and leaves the rest to the next
pass, so the first build of a large state does not hold up one pass for long. `jbus telemetry`
reads everything, prints what it added and how long it took, and `builds` records each build.

`--rebuild <path>` writes a new store at `path` from the sources alone, as a check: the store
itself is never rebuilt, since the sources no longer have every row it keeps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any

import jbus
from jbus import verbs
from jbus.telemetry import messages, records, schema
from jbus.telemetry.records import SOURCES, Source

FILE = "telemetry.sqlite"
PASS_BYTES = 16 * 2**20
"""How much of the record files a pass reads at most; a file is read whole once begun."""
BUSY_MS = 30_000
TRIMMED = next(source for source in SOURCES if source.table == "events")


@dataclass
class Built:
    """What a build did: rows added or updated by table, bytes read, files left for the next
    build, and how long it took."""

    rows: Counter[str] = field(default_factory=Counter)
    bytes: int = 0
    left: int = 0
    ms: int = 0

    def line(self, path: Path) -> str:
        added = ", ".join(f"{table} {n}" for table, n in sorted(self.rows.items()) if n)
        left = f", {self.left} files left for the next build" if self.left else ""
        return (
            f"telemetry: {path}: {added or 'nothing new'}; {self.bytes} bytes read "
            f"in {self.ms} ms{left}"
        )


def path(config: jbus.Config) -> Path:
    """The store of this machine's jbus."""
    return config.state_dir / FILE


def _zone_name(zone: tzinfo | None) -> str:
    return str(zone) if zone is not None else f"machine {datetime.now().astimezone().tzname()}"


def connect(where: Path) -> sqlite3.Connection:
    """Open the store at `where`, made private where it is new, in WAL mode, with its tables
    at this schema's version and its views made again."""
    where.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(where, os.O_WRONLY | os.O_CREAT, 0o600))
    connection = sqlite3.connect(where, timeout=BUSY_MS / 1000, isolation_level=None)
    connection.execute(f"PRAGMA busy_timeout = {BUSY_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    migrate(connection)
    _views(connection)
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Run each migration the store has not had, each with its new version in one transaction."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    for number in range(version, len(schema.MIGRATIONS)):
        try:
            connection.executescript(
                f"BEGIN;\n{schema.MIGRATIONS[number]}PRAGMA user_version = {number + 1};\nCOMMIT;"
            )
        except sqlite3.Error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def _views(connection: sqlite3.Connection) -> None:
    drops = "".join(f"DROP VIEW IF EXISTS {name};\n" for name, _ in reversed(schema.VIEWS))
    makes = "".join(f"CREATE VIEW {name} AS {sql};\n" for name, sql in schema.VIEWS)
    connection.executescript(f"BEGIN;\n{drops}{makes}COMMIT;")


def _zone(connection: sqlite3.Connection, zone: tzinfo | None) -> None:
    """Keep each `day` in the zone the user has now: a store last built in another zone has its
    days worked out again."""
    name = _zone_name(zone)
    held = connection.execute("SELECT value FROM meta WHERE name = 'zone'").fetchone()
    if held and held[0] == name:
        return
    connection.execute("BEGIN")
    for table, at in (*((source.table, source.at) for source in SOURCES), (messages.TABLE, "at")):
        found = connection.execute(f"SELECT project, key, {at} FROM {table}")
        connection.executemany(
            f"UPDATE {table} SET day = ? WHERE project = ? AND key = ?",
            [(records.day(at, zone), project, key) for project, key, at in found.fetchall()],
        )
    connection.execute("INSERT OR REPLACE INTO meta (name, value) VALUES ('zone', ?)", (name,))
    connection.execute("COMMIT")


def _file(config: jbus.Config, project: jbus.Project, source: Source) -> Path:
    base = config.state(project) if source.where == "state" else config.home(project)
    return base / source.file


def _files(config: jbus.Config) -> Iterator[tuple[str, Source, Path]]:
    """Each record file the store reads, with the project its rows are of: every project's own,
    then the machine's."""
    for project in config.projects:
        for source in SOURCES:
            if source.where != "machine":
                yield project.name, source, _file(config, project, source)
    for source in SOURCES:
        if source.where == "machine":
            yield records.MACHINE, source, config.state_dir / source.file


def _head(handle: Any) -> str:
    """The hash of a file's first whole line, or nothing where it has none yet."""
    handle.seek(0)
    first = handle.readline()
    return hashlib.sha256(first).hexdigest()[:16] if first.endswith(b"\n") else ""


def _insert(source: Source, update: bool) -> str:
    names = ["project", "key", *(name for name, _ in source.columns), "day"]
    marks = ", ".join("?" for _ in names)
    sql = f"INSERT INTO {source.table} ({', '.join(names)}) VALUES ({marks})"
    if not update:
        return sql.replace("INSERT", "INSERT OR IGNORE", 1)
    sets = ", ".join(f"{name} = excluded.{name}" for name in names[2:])
    return f"{sql} ON CONFLICT (project, key) DO UPDATE SET {sets}"


def _values(source: Source, project: str, key: str, row: records.Row, zone: tzinfo | None):
    return (
        project,
        key,
        *(row.get(name) for name, _ in source.columns),
        records.day(row.get(source.at), zone),
    )


def _cursor(connection: sqlite3.Connection, project: str, table: str) -> tuple | None:
    return connection.execute(
        "SELECT inode, offset, head, size, mtime FROM cursors WHERE project = ? AND source = ?",
        (project, table),
    ).fetchone()


def _keep_cursor(connection, project: str, table: str, *values: Any) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO cursors (project, source, inode, offset, head, size, mtime) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project, table, *values),
    )


def _log(connection, project: str, source: Source, file: Path, zone, built: Built) -> None:
    """Read a log on from its cursor, or from its start where the file is not the one the
    cursor names, and keep each whole line it has not kept."""
    with open(file, "rb") as handle:
        size, inode = os.fstat(handle.fileno()).st_size, os.fstat(handle.fileno()).st_ino
        head = _head(handle)
        held = _cursor(connection, project, source.table)
        start = held[1] if held and held[0] == inode and held[2] == head and held[1] <= size else 0
        if held and start == size and held[0] == inode:
            return
        handle.seek(start)
        data = handle.read(size - start)
    end = data.rfind(b"\n") + 1
    counts: dict[str, int] = {}
    rows = []
    for raw in data[:end].splitlines():
        line = raw.decode(errors="replace")
        if source.text:
            canon, record = line, line
        else:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            canon = json.dumps(record, sort_keys=True)
        if canon not in counts:
            counts[canon] = 0 if start == 0 else _seen(connection, source.table, project, canon)
        key = records.key(canon, counts[canon])
        counts[canon] += 1
        rows.append(_values(source, project, key, source.row(record, zone), zone))
    connection.execute("BEGIN")
    before = connection.total_changes
    connection.executemany(_insert(source, update=False), rows)
    built.rows[source.table] += connection.total_changes - before
    _keep_cursor(connection, project, source.table, inode, start + end, head, size, None)
    connection.execute("COMMIT")
    built.bytes += end


def _seen(connection, table: str, project: str, canon: str) -> int:
    """How many lines equal to this one the store holds of the project, by their keys."""
    count = 0
    while connection.execute(
        f"SELECT 1 FROM {table} WHERE project = ? AND key = ?",
        (project, records.key(canon, count)),
    ).fetchone():
        count += 1
    return count


def _snapshot(connection, project: str, source: Source, file: Path, zone, built: Built) -> None:
    """Read a snapshot that changed since the last build, and update each record's row."""
    stat = file.stat()
    held = _cursor(connection, project, source.table)
    if held and (held[0], held[3], held[4]) == (stat.st_ino, stat.st_size, stat.st_mtime_ns):
        return
    text = file.read_text(errors="replace")
    try:
        found = list(source.records(text))
    except ValueError:
        return
    rows = []
    for record in found:
        row = source.row(record, zone)
        natural = row.get(source.natural)
        if natural is not None:
            rows.append(_values(source, project, str(natural), row, zone))
    connection.execute("BEGIN")
    before = connection.total_changes
    connection.executemany(_insert(source, update=True), rows)
    built.rows[source.table] += connection.total_changes - before
    _keep_cursor(
        connection, project, source.table, stat.st_ino, None, None, stat.st_size, stat.st_mtime_ns
    )
    connection.execute("COMMIT")
    built.bytes += len(text.encode())


def build(config: jbus.Config, where: Path | None = None, most: int | None = None) -> Built:
    """Bring the store at `where`, the machine's by default, up to every project's records.
    With `most`, begin no file once that many bytes are read, and count the files left."""
    began = time.monotonic()
    target = where or path(config)
    built = Built()
    connection = connect(target)
    try:
        zone = config.user.zone
        _zone(connection, zone)
        for name, source, file in _files(config):
            if not file.is_file():
                continue
            if most is not None and built.bytes >= most:
                built.left += 1
                continue
            read = _log if source.kind == "log" else _snapshot
            read(connection, name, source, file, zone, built)
        messages.read(connection, config, zone, built, most)
        built.ms = round((time.monotonic() - began) * 1000)
        connection.execute(
            "INSERT INTO builds (at, ms, bytes, rows, left) VALUES (?, ?, ?, ?, ?)",
            (
                records.utc(datetime.now(UTC).isoformat()),
                built.ms,
                built.bytes,
                sum(built.rows.values()),
                built.left,
            ),
        )
    finally:
        connection.close()
    return built


def copied(config: jbus.Config, project: jbus.Project) -> int:
    """How far into the project's `events.jsonl` as it is now the store has read: the cursor's
    offset where its inode and first line are the file's, else 0. `Box.forget` drops no line
    past it. Only the trim rewrites the file, and it calls this first."""
    store, file = path(config), _file(config, project, TRIMMED)
    if not store.is_file():
        return 0
    try:
        with open(file, "rb") as handle:
            inode, head = os.fstat(handle.fileno()).st_ino, _head(handle)
        reader = sqlite3.connect(f"file:{store}?mode=ro", uri=True, timeout=BUSY_MS / 1000)
        try:
            held = _cursor(reader, project.name, TRIMMED.table)
        finally:
            reader.close()
    except (OSError, sqlite3.Error):
        return 0
    return held[1] if held and held[0] == inode and held[2] == head else 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--rebuild",
        metavar="path",
        help="write a new store at this path from the sources alone, to compare with the store",
    )


def _run(args: argparse.Namespace, config: jbus.Config) -> int:
    if args.rebuild:
        target = Path(args.rebuild)
        if target.exists():
            print(f"refused: {target} is there, and a rebuild writes a new file")
            return 2
        print(build(config, target).line(target))
        return 0
    print(build(config).line(path(config)))
    return 0


def _pass(config: jbus.Config, say: Callable[[str], None]) -> None:
    """The pass's build: at most `PASS_BYTES` read, and a line only where files were left."""
    built = build(config, most=PASS_BYTES)
    if built.left:
        say(built.line(path(config)))


VERBS = (
    verbs.Verb(
        "telemetry",
        "compile every project's records into one SQLite file with KPI views",
        _arguments,
        _run,
    ),
)
CHORES = (verbs.Chore(35, "the telemetry store", lambda config, _, __, say: _pass(config, say)),)
