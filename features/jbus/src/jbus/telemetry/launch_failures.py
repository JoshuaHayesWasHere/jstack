"""Each launch that failed or waited, by its cause and with its minutes: the store's
`launch_failures`.

A cause is one of `CAUSES`, read from the records jbus already writes, at the time the store reads
them, since the store keeps no reason's text:

- `sign-in`: a `failover` line of `events.jsonl` whose instance could not sign in
  (`jbus.failover`), from the row's last launch before it in `transitions.jsonl` to the failover.
  A row with no launch there, such as a scout's, has no start and no minutes: none is guessed. A
  row's reason `no launch: <instance> cannot sign in (...)` is a sign-in wait.
- `/tmp`: a row's reason `waiting: /tmp at <n>% of its <what>` (`jbus.cleanup.WAITING`).
- `no slot`: a row's reason `no slot`, a cap of jbus's config (`max_per_home is ...`), or a gate
  held back while every slot is taken.
- `no home-id`: a home start that sat and ended, failed or idle, with no `home-id` written, from
  when it was launched to when the pass saw it end: a failed start `relaunches.json` names
  (`jbus.children`), kept by its thread in `home_starts`. A start that failed signed out is
  `sign-in`, and one that failed on a usage limit is `other` with the limit as `reason`. A start
  written before `relaunches.json` kept `launched` has no start and no minutes.
- `load`: a row's reason `waiting for room on the machine: load is at or over <n>% of <c> cores`,
  where `jgauge room` said the load is over its share of the cores (`jbus.roomwait.reason`; a jbus
  from before wrote the reading after `load`, which is read the same).
- `other`: any other reason that keeps a launch from starting, `waiting for room on the machine`
  with the head of any other no of `jgauge room` but /tmp's after it, or none
  (`jbus.roomwait.reason`), or `no launch: ...` (every instance capped), kept as `reason`, the raw
  text jbus wrote.

A wait is a spell of a row's lines in `waits.jsonl` with one cause: it starts at the first and ends
at the row's next line of another cause or of none; a spell with no such line yet is open, with no
end and no minutes, and the build after its end closes it. Each `events` line keeps its cause as
`launch_cause`, and each `row_waits` line its cause and an `other` reason (`launch_reason`), so a
build makes the table again from the store's own tables, which keep their rows after jbus trims
its files.

A wait on load from before `jbus.dispatch` named it is `other`, as its bare reason says no more.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, tzinfo
from itertools import groupby

from jbus.cleanup import WAITING
from jbus.roomwait import ROOM
from jbus.telemetry import values

TABLE = "launch_failures"
"""One row for each launch failure or wait, made by `v021_launch_failures`: its `slug`, `cause`,
`reason` for `other`, `start`, `end` and `minutes`, and `day`, the local date of its `start`, or of
its `end` where it has no start."""
SIGN_IN, TMP, NO_SLOT, LOAD, NO_HOME_ID, OTHER = (
    "sign-in",
    "/tmp",
    "no slot",
    "load",
    "no home-id",
    "other",
)
CAUSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (SIGN_IN, re.compile(r"no launch: .*\bcannot sign in\b")),
    (TMP, WAITING),
    (
        NO_SLOT,
        re.compile(
            r"no slot$|max_(per_home|per_project|running) is "
            r"|a gate held back while every slot is taken: "
        ),
    ),
    (LOAD, re.compile(rf"{re.escape(ROOM)}: load (\S+ )?is at or over ")),
    (OTHER, re.compile(rf"{re.escape(ROOM)}(: |$)|no launch: ")),
)
"""The cause of each reason a row waits that keeps its launch from starting, the first that
matches its start; a reason none matches is no launch wait."""
FAILOVER = re.compile(r"failover .+?: \S+ could not sign in\b")


def wait(why: object) -> tuple[str | None, str | None]:
    """The cause of a row's reason to wait, and the reason itself for `other`, or two Nones for
    a reason that is no launch wait."""
    text = why if isinstance(why, str) else ""
    found = next((cause for cause, pattern in CAUSES if pattern.match(text)), None)
    return found, text if found == OTHER else None


def event(name: object, line: object) -> str | None:
    """The cause of an `events.jsonl` line: `sign-in` for a failover whose instance could not
    sign in, else none."""
    if name == "failover" and isinstance(line, str) and FAILOVER.match(line):
        return SIGN_IN
    return None


def start(failed: object) -> tuple[str, str | None]:
    """The cause of a failed home start, by what `jbus.children` says it failed on, and the
    reason itself for `other`: a login lapse is `sign-in`, a usage limit `other`, and a run that
    ended, failed or idle, with no `home-id` is `no home-id`. `jbus.children` is imported here,
    since it imports the store's package at its own import."""
    from jbus.children import NOT_SIGNED_IN

    text = failed if isinstance(failed, str) else ""
    if text == NOT_SIGNED_IN:
        return SIGN_IN, None
    if text.endswith(" limit"):
        return OTHER, text
    return NO_HOME_ID, None


def _minutes(start: str | None, end: str | None) -> float | None:
    if start is None or end is None:
        return None
    gone = datetime.strptime(end, values.STAMP) - datetime.strptime(start, values.STAMP)
    return gone.total_seconds() / 60


def _signins(connection: sqlite3.Connection) -> list[tuple]:
    """Each sign-in failure of `events`, from the row's last launch before it, or none."""
    return connection.execute(
        "SELECT e.project, e.key, e.slug, e.launch_cause, NULL, "
        "(SELECT max(t.at) FROM transitions t WHERE t.project = e.project "
        "AND t.slug = e.slug AND t.to_status = 'launched' AND t.at <= e.at), e.at "
        "FROM events e WHERE e.launch_cause IS NOT NULL"
    ).fetchall()


def _starts(connection: sqlite3.Connection) -> list[tuple]:
    """Each failed home start of `home_starts`, from its launch to when its failure was seen."""
    found = connection.execute(
        "SELECT project, key, home, cause, launched, at FROM home_starts"
    ).fetchall()
    return [
        (project, key, home, *start(cause), launched, at)
        for project, key, home, cause, launched, at in found
    ]


def _spells(connection: sqlite3.Connection) -> list[tuple]:
    """Each spell of one launch cause in each row's waits, keyed by its first line, with its
    reason, its start and its end, or no end while it is open."""
    lines = connection.execute(
        "SELECT project, key, slug, launch_cause, launch_reason, at FROM row_waits "
        "WHERE at IS NOT NULL ORDER BY project, slug, at, key"
    ).fetchall()
    found: list[tuple] = []
    for _, held in groupby(lines, key=lambda line: (line[0], line[2])):
        spell: tuple | None = None
        for project, key, slug, cause, reason, at in held:
            if spell is not None and cause == spell[3]:
                continue
            if spell is not None:
                found.append((*spell, at))
            spell = (project, key, slug, cause, reason, at) if cause else None
        if spell is not None:
            found.append((*spell, None))
    return found


def keep(connection: sqlite3.Connection, zone: tzinfo | None) -> int:
    """Make the table again from `events`, `transitions`, `row_waits` and `home_starts`, and
    return how many rows it added, changed or dropped."""
    made = {}
    for project, key, slug, cause, reason, start, end in (
        *_signins(connection),
        *_spells(connection),
        *_starts(connection),
    ):
        day = values.day(start or end, zone)
        made[project, key] = (slug, cause, reason, start, end, _minutes(start, end), day)
    connection.execute("BEGIN")
    found = connection.execute(
        f'SELECT project, key, slug, cause, reason, start, "end", minutes, day FROM {TABLE}'
    ).fetchall()
    held = {(row[0], row[1]): tuple(row[2:]) for row in found}
    gone = [key for key in held if key not in made]
    new = [(*key, *row) for key, row in made.items() if held.get(key) != row]
    connection.executemany(f"DELETE FROM {TABLE} WHERE project = ? AND key = ?", gone)
    connection.executemany(
        f"INSERT OR REPLACE INTO {TABLE} "
        '(project, key, slug, cause, reason, start, "end", minutes, day) '
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        new,
    )
    connection.execute("COMMIT")
    return len(gone) + len(new)
