"""The record files `jbus telemetry` compiles, each as one table: what a row of it keeps.

Each source is a module of this package named for the table it fills, `<table>.py`, whose `SOURCE`
is one `Source`, and `SOURCES` holds them in the order of the modules' names, which is the order of
the tables' names (`jbus.telemetry.entries`). A source added is a module of its own, and its table
is made by a migration of its own (`jbus.telemetry.migrations`), never by the first.

A source's `row` is the table's allow-list. It turns one record into the row's columns, and it
is the only way a record reaches the store. It keeps ids, times, counts and labels, and turns
each text of a record into its length (`<name>_len`), so no table holds what a message said.

A source is a `log` or a `snapshot`:

- A log only grows. A row's key is the hash of the line, as JSON with sorted keys (as text where
  the log's lines are text), and of how many equal lines come before it, as `jbus.wake.entries`
  names an event. So two equal lines are two rows, and a line read again, as after the daily trim
  rewrites a log, is the row it was.
- A snapshot is written whole each time. A row's key is the record's own, the column `natural`
  names, and a newer snapshot updates the row and never deletes one, so a record that leaves the
  file stays in the store.

Each time is kept in UTC, in one form of fixed width (`utc`), so that text order is time order,
and each table has the local `day` of its `at` column in the user's zone, since SQLite has no
zone of its own to bucket by.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import tzinfo
from pathlib import Path
from typing import Any, Literal

from jbus.telemetry import entries
from jbus.telemetry.readers import json_lines
from jbus.telemetry.values import Row

SOURCE_MODULE = r"[a-z][a-z0-9_]*"
"""The name of a source's module, which is its table's name."""


@dataclass(frozen=True)
class Source:
    """A file of a project's records and the table it fills.

    `where` is `state`, the project's jbus state (`Config.state`), `home`, its home's
    (`Config.home`), or `machine`, jbus's own state directory, whose rows are the machine's, of
    the project `values.MACHINE`. `columns` are the table's own columns besides `project`, `key`
    and `day`, each with its SQLite type, and `row` makes them of one record. A log's `text` is
    True where its lines are text, not JSON. A snapshot's `records` reads its records from the
    file, and `natural` names the column that is its key. `at` names the column whose local date
    is `day`. A log's `beside`, where given, adds to each record what the files in its file's
    directory hold, before `row`; the row's key is still of the line as written."""

    table: str
    file: str
    kind: Literal["log", "snapshot"]
    columns: tuple[tuple[str, str], ...]
    row: Callable[[Any, tzinfo | None], Row]
    at: str = "at"
    where: Literal["state", "home", "machine"] = "state"
    text: bool = False
    records: Callable[[str], Iterable[Row]] = json_lines
    natural: str = ""
    beside: Callable[[Row, Path], Row] | None = None


SOURCES: tuple[Source, ...] = tuple(
    module.SOURCE for module in entries.modules(__name__, __path__, SOURCE_MODULE)
)
"""Each module's `SOURCE`, in the order of the modules' names."""
