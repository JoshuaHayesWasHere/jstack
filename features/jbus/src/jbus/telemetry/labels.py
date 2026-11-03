"""The gate labels a scout writes each week, as the store's `gate_labels` table.

A scout labels each week's gates by `features/jbus/docs/jbus/gate-labels.md`, into
`reports/gate-labels/<the week's first day>.tsv` (`FOLDER`) in a project's home: a header line
and one row per gate, tab-separated, with its `key` (`<project>#<number>`) and its `outcome`. A
row here is one label: the project whose home holds the file; the week, which is the file's
name, since the scout's first files hold a word in their `week` column; the gate's key; its
outcome and class. It keeps no text: of the evidence and the note, only their lengths. Who
closed the gate is no label: the view `gate_outcomes` (`jbus.telemetry.schema`) takes it from
the gate's record in the store's `questions`.

A file is its week's whole truth for its home, and a scout may write it again, as when a gate
labelled `open` has closed. So a file read again replaces every label it gave before, in one
transaction with its cursor, keyed `gate_labels/<its name>` under the project of the home: the
one table whose rows the store does not keep forever. A file is read again when its inode, size
or time changed, as a snapshot is. A gate labelled twice in a week keeps the last label read. A
file whose name is no date is no week's, and is not read.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import jbus
from jbus.telemetry import cursors

if TYPE_CHECKING:
    from jbus.telemetry import Built

TABLE = "gate_labels"
FOLDER = Path("reports") / "gate-labels"
TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {TABLE} (home TEXT NOT NULL, week TEXT NOT NULL, key TEXT NOT "
    "NULL, outcome TEXT, klass TEXT, outcome_evidence_len INTEGER, note_len INTEGER, "
    "PRIMARY KEY (week, key)) WITHOUT ROWID;\n"
)


def _length(value: str | None) -> int | None:
    return len(value) if value else None


def rows(home: str, week: str, text: str) -> dict[str, tuple]:
    """Each label of a week's file, by its gate's key, in the table's columns."""
    found = {}
    for one in csv.DictReader(io.StringIO(text), delimiter="\t"):
        key = (one.get("key") or "").strip()
        if key:
            found[key] = (
                home,
                week,
                key,
                (one.get("outcome") or "").strip() or None,
                (one.get("klass") or "").strip() or None,
                _length(one.get("outcome_evidence")),
                _length(one.get("note")),
            )
    return found


def _weeks(config: jbus.Config):
    """Each labels file of every project's home, a home read once, with the project it is under
    and its week."""
    seen = set()
    for project in config.projects:
        folder = config.home(project) / FOLDER
        if folder in seen or not folder.is_dir():
            continue
        seen.add(folder)
        for path in sorted(folder.glob("*.tsv")):
            try:
                week = date.fromisoformat(path.stem).isoformat()
            except ValueError:
                continue
            yield project.name, week, path


def read(connection: sqlite3.Connection, config: jbus.Config, built: Built) -> None:
    """Keep each labels file that changed since the last build, its week's labels replaced."""
    for project, week, path in _weeks(config):
        source = f"{TABLE}/{path.name}"
        stat = path.stat()
        held = cursors.held(connection, project, source)
        if held and (held[0], held[3], held[4]) == (stat.st_ino, stat.st_size, stat.st_mtime_ns):
            continue
        text = path.read_text(errors="replace")
        found = rows(project, week, text)
        connection.execute("BEGIN")
        connection.execute(f"DELETE FROM {TABLE} WHERE home = ? AND week = ?", (project, week))
        connection.executemany(
            f"INSERT OR REPLACE INTO {TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)", found.values()
        )
        cursors.keep(
            connection, project, source, stat.st_ino, None, None, stat.st_size, stat.st_mtime_ns
        )
        connection.execute("COMMIT")
        built.rows[TABLE] += len(found)
        built.bytes += len(text.encode())
