"""`jbus telemetry`: compile every project's records into one SQLite file, with KPI views.

The store is `telemetry.sqlite` in jbus's state directory, in WAL mode, so a reader never waits
on the build. It has one table for each record file of each project (`jbus.telemetry.records`):
the jbus logs, the CI ledger, the home's `merge.log`, the records `jbus.history` and
`jbus.spent` keep, six snapshots, the machine's log of its passes, each
launch's arm (`jbus.telemetry.launches`), the messages of T3 Code's threads
(`jbus.telemetry.messages`), the gate labels a scout writes each week
(`jbus.telemetry.labels`), the gh calls of each hour from the machine's call log
(`jbus.telemetry.ghcalls`), and the crew first load of each install it saw
(`jbus.telemetry.firstload`). Its views give the KPIs (`jbus.telemetry.views`). It keeps a row
forever, save a gate label its week's file replaces, and keeps no text of a message: ids, times,
counts, labels and the length of each text.

A build reads only what is new. A log is read on from `cursors`, the file's inode, the hash of
its first line and the offset its last build read to, and only to its last newline, so a line
still being written waits for the next build. A log whose inode or first line changed, or that
is shorter than the offset, is read again from the start: its rows are keyed by their content
(`values.key`), so a line read twice is one row, the one today's `records` makes of it, and a
row that would not change is not written. A snapshot is read again when its inode, size
or time changed, and a `whole` one then deletes the rows of the records it no longer has.
Each file's rows and its cursor are written in one transaction, so a build stopped at any
point leaves each file either read or not, and the next build reads on from there. So a build
run twice adds nothing the second time, and a build run each pass ends as a build from nothing
would (`--rebuild`), apart from the rows the sources have since dropped.

Each pass runs a build after the launches (`CHORES`), before any project's second half, where
`jbus.chores.daily` trims `events.jsonl` to 14 days. The trim drops only the lines this store
holds (`copied`), so no event is lost to it: a line the store has not read stays in the file
until it has. A pass reads at most `PASS_BYTES` of new files and leaves the rest to the next
pass, so the first build of a large state does not hold up one pass for long. `jbus telemetry`
reads everything, prints what it added and how long it took, and `builds` records each build.

`--rebuild <path>` writes a new store at `path` from the sources alone, as a check: the store
itself is never rebuilt, since the sources no longer have every row it keeps.

`jbus scorecard` reads each measure of `jbus.telemetry.measures` from the store, read only, and
prints one line a measure, or with `--json` a list of them; with `--out <path>` it writes the
scorecard's page there (`jbus.telemetry.scorecard`) and prints the count of each state. It
writes nothing to the store. A pass starts that page for the config's first project at most
each `SCORECARD_EVERY`, as a child it does not wait for.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from pathlib import Path

import jbus
from jbus import verbs
from jbus.telemetry import (
    cursors,
    firstload,
    ghcalls,
    kpis,
    labels,
    launches,
    measures,
    messages,
    migrations,
    records,
    scorecard,
    tokens,
    values,
    views,
)
from jbus.telemetry.records import SOURCES, Source

FILE = "telemetry.sqlite"
PAGE = "kpis.html"
SCORECARD = "scorecard.html"
SCORECARD_EVERY = timedelta(minutes=15)
"""How old the pass's scorecard page may be before a pass builds it again: a pass runs about
twice a minute, and the page is not worth its queries each time."""
PASS_BYTES = 16 * 2**20
"""How much of the record files a pass reads at most; a file is read whole once begun."""
BUSY_MS = 30_000
TRIMMED = next(source for source in SOURCES if source.table == "events")
RAN = "migrations"
"""The store's table of the name of each migration it has run (`jbus.telemetry.migrations`)."""


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
    """Open the store at `where`, made private where it is new, in WAL mode, with every
    migration run on it and its views made again."""
    where.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(where, os.O_WRONLY | os.O_CREAT, 0o600))
    connection = sqlite3.connect(where, timeout=BUSY_MS / 1000, isolation_level=None)
    connection.execute(f"PRAGMA busy_timeout = {BUSY_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    migrate(connection)
    _views(connection)
    return connection


def ran(connection: sqlite3.Connection) -> set[str] | None:
    """The name of each migration the store has run, or None where it keeps no table of them."""
    if not connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (RAN,)
    ).fetchone():
        return None
    return {name for (name,) in connection.execute(f"SELECT name FROM {RAN}")}


def migrate(connection: sqlite3.Connection) -> None:
    """Run each migration the store has not, in name order, each in one transaction with its
    name. A store that counted its migrations by `PRAGMA user_version`, as stores did before
    they kept their names, is moved once to the table, with the names of as many of them as
    its version. The move keeps that version, so a jbus still on the counting code, such as a
    branch not rebased yet, finds every migration it knows run and runs none."""
    if ran(connection) is None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        names = "".join(_kept(name) for name in list(migrations.MIGRATIONS)[:version])
        _once(
            connection,
            f"CREATE TABLE {RAN} (name TEXT PRIMARY KEY) WITHOUT ROWID;\n{names}",
            None,
        )
    done = ran(connection) or set()
    for name, sql in migrations.MIGRATIONS.items():
        if name not in done:
            _once(connection, f"{_kept(name)}{sql}", name)


def _kept(name: str) -> str:
    return f"INSERT INTO {RAN} (name) VALUES ('{name}');\n"


def _once(connection: sqlite3.Connection, sql: str, name: str | None) -> None:
    """Run `sql` in one transaction, which keeps the migration `name`, or makes the table of
    names where `name` is None. Where it fails because another connection did it first, the
    store has it, and that is no error."""
    try:
        connection.executescript(f"BEGIN IMMEDIATE;\n{sql}COMMIT;")
    except sqlite3.Error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        held = ran(connection)
        if held is None or (name is not None and name not in held):
            raise


def _views(connection: sqlite3.Connection) -> None:
    drops = "".join(f"DROP VIEW IF EXISTS {name};\n" for name, _ in reversed(views.VIEWS))
    makes = "".join(f"CREATE VIEW {name} AS {sql};\n" for name, sql in views.VIEWS)
    connection.executescript(f"BEGIN;\n{drops}{makes}COMMIT;")


def _zone(connection: sqlite3.Connection, zone: tzinfo | None) -> None:
    """Keep each `day` in the zone the user has now: a store last built in another zone has its
    days worked out again."""
    name = _zone_name(zone)
    held = connection.execute("SELECT value FROM meta WHERE name = 'zone'").fetchone()
    if held and held[0] == name:
        return
    connection.execute("BEGIN")
    timed = ((source.table, source.at) for source in SOURCES if source.at)
    tables = (*timed, (messages.TABLE, "at"))
    for table, at in (*tables, (launches.TABLE, "at"), (firstload.TABLE, "at")):
        found = connection.execute(f"SELECT project, key, {at} FROM {table}")
        connection.executemany(
            f"UPDATE {table} SET day = ? WHERE project = ? AND key = ?",
            [(values.day(at, zone), project, key) for project, key, at in found.fetchall()],
        )
    found = connection.execute("SELECT provider, call, at FROM calls")
    connection.executemany(
        "UPDATE calls SET day = ? WHERE provider = ? AND call = ?",
        [(values.day(at, zone), provider, call) for provider, call, at in found.fetchall()],
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
            yield values.MACHINE, source, config.state_dir / source.file


def _insert(source: Source) -> str:
    """Insert a row, or make the held row of its key the one read now, leaving a row that would
    not change unwritten, so `total_changes` counts only what a read changed."""
    names = ["project", "key", *(name for name, _ in source.columns), "day"]
    marks = ", ".join("?" for _ in names)
    sets = ", ".join(f"{name} = excluded.{name}" for name in names[2:])
    same = " AND ".join(f"{source.table}.{name} IS excluded.{name}" for name in names[2:])
    return (
        f"INSERT INTO {source.table} ({', '.join(names)}) VALUES ({marks}) "
        f"ON CONFLICT (project, key) DO UPDATE SET {sets} WHERE NOT ({same})"
    )


def _values(source: Source, project: str, key: str, row: records.Row, zone: tzinfo | None):
    return (
        project,
        key,
        *(row.get(name) for name, _ in source.columns),
        values.day(row.get(source.at), zone),
    )


def _log(connection, project: str, source: Source, file: Path, zone, built: Built) -> None:
    """Read a log on from its cursor, or from its start where the file is not the one the
    cursor names, and keep each whole line it has not kept."""
    with open(file, "rb") as handle:
        size, inode = os.fstat(handle.fileno()).st_size, os.fstat(handle.fileno()).st_ino
        head = cursors.head(handle)
        held = cursors.held(connection, project, source.table)
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
            if source.beside is not None:
                record = source.beside(record, file.parent)
        if canon not in counts:
            counts[canon] = 0 if start == 0 else _seen(connection, source.table, project, canon)
        key = values.key(canon, counts[canon])
        counts[canon] += 1
        rows.append(_values(source, project, key, source.row(record, zone), zone))
    connection.execute("BEGIN")
    before = connection.total_changes
    connection.executemany(_insert(source), rows)
    built.rows[source.table] += connection.total_changes - before
    cursors.keep(connection, project, source.table, inode, start + end, head, size, None)
    connection.execute("COMMIT")
    built.bytes += end


def _seen(connection, table: str, project: str, canon: str) -> int:
    """How many lines equal to this one the store holds of the project, by their keys."""
    count = 0
    while connection.execute(
        f"SELECT 1 FROM {table} WHERE project = ? AND key = ?",
        (project, values.key(canon, count)),
    ).fetchone():
        count += 1
    return count


def _snapshot(connection, project: str, source: Source, file: Path, zone, built: Built) -> None:
    """Read a snapshot that changed since the last build, and update each record's row."""
    stat = file.stat()
    held = cursors.held(connection, project, source.table)
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
    connection.executemany(_insert(source), rows)
    if source.whole:
        connection.execute(
            f"DELETE FROM {source.table} WHERE project = ? "
            "AND key NOT IN (SELECT value FROM json_each(?))",
            (project, json.dumps([row[1] for row in rows])),
        )
    built.rows[source.table] += connection.total_changes - before
    cursors.keep(
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
        launches.read(connection, config, zone, built)
        ghcalls.read(connection, config, built, most)
        labels.read(connection, config, built)
        _tokens(config, connection, zone, most, built)
        built.rows[firstload.TABLE] += firstload.keep(connection, zone)
        built.ms = round((time.monotonic() - began) * 1000)
        connection.execute(
            "INSERT INTO builds (at, ms, bytes, rows, left) VALUES (?, ?, ?, ?, ?)",
            (
                values.utc(datetime.now(UTC).isoformat()),
                built.ms,
                built.bytes,
                sum(built.rows.values()),
                built.left,
            ),
        )
    finally:
        connection.close()
    return built


def _tokens(config, connection, zone, most: int | None, built: Built) -> None:
    """Copy the sessions T3 names, then the new calls of their transcripts, those written since
    the last build first and then the rest oldest first, within what is left of `most`."""
    found = tokens.sessions(config)
    built.rows["sessions"] += tokens.keep_sessions(connection, found)
    (last,) = connection.execute("SELECT max(at) FROM builds").fetchone()
    since = datetime.fromisoformat(last.replace("Z", "+00:00")) if last else None
    for one in tokens.transcripts({(each.provider, each.session) for each in found}, since):
        changed, read, left = tokens.read(
            connection, one, zone, None if most is None else most - built.bytes
        )
        built.rows["calls"] += changed
        built.bytes += read
        built.left += left


def copied(config: jbus.Config, project: jbus.Project) -> int:
    """How far into the project's `events.jsonl` as it is now the store has read: the cursor's
    offset where its inode and first line are the file's, else 0. `Box.forget` drops no line
    past it. Only the trim rewrites the file, and it calls this first."""
    store, file = path(config), _file(config, project, TRIMMED)
    if not store.is_file():
        return 0
    try:
        with open(file, "rb") as handle:
            inode, head = os.fstat(handle.fileno()).st_ino, cursors.head(handle)
        reader = sqlite3.connect(f"file:{store}?mode=ro", uri=True, timeout=BUSY_MS / 1000)
        try:
            held = cursors.held(reader, project.name, TRIMMED.table)
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


def _page_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store", metavar="path", help="the store to read, the machine's by default"
    )
    parser.add_argument(
        "--week",
        metavar="YYYY-MM-DD",
        type=date.fromisoformat,
        help="a day of the week to show as this week, today by default",
    )
    parser.add_argument(
        "--out", metavar="path", help=f"where to write the page, {PAGE} in jbus's state by default"
    )


def _page(args: argparse.Namespace, config: jbus.Config) -> int:
    """Write one project's KPI page from the store, which it brings to this schema's views first:
    the project `--project` names, or the config's only one."""
    project = config.project(args.project).name
    store = Path(args.store) if args.store else path(config)
    if not store.is_file() or store.stat().st_size == 0:
        print(f"refused: no telemetry store at {store}: run jbus telemetry first")
        return 2
    now = datetime.now(config.user.zone).astimezone(config.user.zone)
    connection = connect(store)
    try:
        board = kpis.board(connection, args.week or now.date(), project)
    finally:
        connection.close()
    out = Path(args.out) if args.out else config.state_dir / PAGE
    out.parent.mkdir(parents=True, exist_ok=True)
    draft = out.with_name(f".{out.name}.{os.getpid()}")
    draft.write_text(kpis.page(board, now))
    draft.replace(out)
    print(f"kpis: {out}: {project}: {board.line()}")
    return 0


def _scorecard_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store", metavar="path", help="the store to read, the machine's by default"
    )
    parser.add_argument("--json", action="store_true", help="print a JSON list of the readings")
    parser.add_argument(
        "--out", metavar="path", help="write the scorecard's page there, not a line a measure"
    )


def _scorecard(args: argparse.Namespace, config: jbus.Config) -> int:
    """Read each measure for one project from the store, opened read only: the project
    `--project` names, or the config's only one."""
    project = config.project(args.project).name
    store = Path(args.store) if args.store else path(config)
    if args.out:
        try:
            print(_scorecard_page(config, project, store, Path(args.out), datetime.now(UTC)))
        except sqlite3.Error as error:
            print(f"refused: no telemetry store to read at {store}: {error}")
            return 2
        return 0
    try:
        connection = sqlite3.connect(f"file:{store}?mode=ro", uri=True, timeout=BUSY_MS / 1000)
    except sqlite3.Error as error:
        print(f"refused: no telemetry store to read at {store}: {error}")
        return 2
    now = datetime.now(UTC)
    try:
        read = [
            (measure, measures.read(connection, measure, project, now, config.user))
            for measure in measures.MEASURES
        ]
    finally:
        connection.close()
    if args.json:
        print(json.dumps([_reading(measure, reading) for measure, reading in read], indent=1))
        return 0
    for measure, reading in read:
        print(_line(measure, reading))
    return 0


def _reading(measure: measures.Measure, reading: measures.Reading) -> dict[str, object]:
    return {
        "name": measure.name,
        "group": measure.group,
        "value": reading.value,
        "unit": measure.unit,
        "n": reading.n,
        "baseline": reading.baseline,
        "state": reading.state,
        "tier": measure.tier,
        "wired": measure.wired,
        "audit": list(measure.audit),
        "note": reading.note,
    }


def _line(measure: measures.Measure, reading: measures.Reading) -> str:
    value = "-" if reading.value is None else f"{round(reading.value, 2):g}"
    baseline = "-" if reading.baseline is None else f"{reading.baseline:g}"
    note = f"  {reading.note}" if reading.note else ""
    return (
        f"{reading.state:<5}  {measure.group:<9}  {measure.name:<22}  {value} {measure.unit}"
        f" of {reading.n}, baseline {baseline}, {measure.tier}{note}"
    )


def _scorecard_page(
    config: jbus.Config, project: str, store: Path, out: Path, now: datetime
) -> str:
    """Write the scorecard's page of `project` at `out`, read from `store` opened read only,
    through a draft file renamed over it; say where, with the count of each state."""
    connection = sqlite3.connect(f"file:{store}?mode=ro", uri=True, timeout=BUSY_MS / 1000)
    try:
        found = scorecard.lines(connection, project, now, config.user)
    finally:
        connection.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    draft = out.with_name(f".{out.name}.{os.getpid()}")
    draft.write_text(scorecard.page(found, config.user.local(now)))
    draft.replace(out)
    return f"scorecard: {out}: {project}: {scorecard.line(found)}"


def _scorecard_chore(config: jbus.Config, now: datetime, say: Callable[[str], None]) -> None:
    """Start the page of the config's first project where it is absent or older than
    `SCORECARD_EVERY`, and no build was started within that time. The build is a child of its
    own, `jbus scorecard --out`, which the pass does not wait for: the registry's reads take
    longer than a pass may. The child's output is kept beside the page, and a build that did not
    end in its line is said here once, as one line, with no alert."""
    if not config.projects:
        return
    out = config.state_dir / SCORECARD
    started = out.with_name(f".{SCORECARD}.started")
    log = out.with_name(f".{SCORECARD}.log")
    if log.is_file() and (said := log.read_text().strip().splitlines()):
        if not said[-1].startswith("scorecard: "):
            say(f"scorecard: no page: {said[-1]}")
        log.write_text("")
    if _younger(out, now) or _younger(started, now):
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    started.touch()
    os.utime(started, (now.timestamp(), now.timestamp()))
    project = config.projects[0].name
    with log.open("w") as output:
        try:
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "jbus",
                    "--project",
                    project,
                    "scorecard",
                    "--out",
                    str(out),
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            say(f"scorecard: no page: {sys.executable} could not be run: {error.strerror}")


def _younger(file: Path, now: datetime) -> bool:
    """Whether `file` is there and was written within `SCORECARD_EVERY` of `now`."""
    return (
        file.exists() and now.timestamp() - file.stat().st_mtime < SCORECARD_EVERY.total_seconds()
    )


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
    verbs.Verb(
        "kpis",
        "write a static page of each KPI against its target, this week and last, from the store",
        _page_arguments,
        _page,
    ),
    verbs.Verb(
        "scorecard",
        "print each health measure of one project against its baseline, from the store, read only",
        _scorecard_arguments,
        _scorecard,
    ),
)
CHORES = (
    verbs.Chore(35, "the telemetry store", lambda config, _, __, say: _pass(config, say)),
    verbs.Chore(
        37, "the scorecard's page", lambda config, _, now, say: _scorecard_chore(config, now, say)
    ),
)
