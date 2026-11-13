"""The gh calls of each hour, from the machine's call log: the store's `gh_hours`.

Each call `jsettings.proc` makes to GitHub is one line of `gh-calls.jsonl` in jbus's state
directory (`jsettings.proc.CALLS`), and so is each `gh` an agent runs in its own shell, whose
caller is `agent` (`jsettings.agent_gh`). At 16 MiB the file becomes `gh-calls.old.jsonl` and a new
one starts, so the two hold about 9 hours. The store keeps them past that as one row for each hour
(UTC), caller and resource: `calls`, `not_modified` (an `http` of 304), `failed` (a `status` other
than 0 with no 304) and `least`, the lowest `remaining` a line of the row gave. `caller` is the
first function of the line's `caller`, the one before ` < `, and `resource` is `''` for a line
that names none. No endpoint and no line is kept.

A build reads on from one cursor, under the machine's project: the inode, offset and first line's
hash of the file it read last, to its last newline. Where that file is now the old one, the build
reads the rest of it, then the new file from its start. Where it is neither, both files are read
from their start, the old one first, since the file the cursor named is gone. The counts are added
to their rows and the cursor moved in one transaction, so a line is counted once however a build
is stopped, and a build that finds nothing new writes nothing.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

import jbus
from jbus.telemetry import cursors, values
from jsettings.proc import CALLS

if TYPE_CHECKING:
    from jbus.telemetry import Built

TABLE = "gh_hours"
OLD = f"{Path(CALLS).stem}.old.jsonl"
TABLE_SQL = (
    f"CREATE TABLE {TABLE} (hour TEXT NOT NULL, caller TEXT NOT NULL, resource TEXT NOT NULL, "
    "calls INTEGER NOT NULL, not_modified INTEGER NOT NULL, failed INTEGER NOT NULL, "
    "least INTEGER, PRIMARY KEY (hour, caller, resource)) WITHOUT ROWID;\n"
)
_ADD = (
    f"INSERT INTO {TABLE} (hour, caller, resource, calls, not_modified, failed, least) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (hour, caller, resource) DO UPDATE SET "
    "calls = calls + excluded.calls, not_modified = not_modified + excluded.not_modified, "
    "failed = failed + excluded.failed, "
    "least = coalesce(min(least, excluded.least), least, excluded.least)"
)


@dataclass
class _Row:
    calls: int = 0
    not_modified: int = 0
    failed: int = 0
    least: int | None = None

    def add(self, line: dict) -> None:
        self.calls += 1
        unchanged = " 304" in str(line.get("http") or "")
        self.not_modified += unchanged
        self.failed += line.get("status") != 0 and not unchanged
        left = line.get("remaining")
        if isinstance(left, int) and not isinstance(left, bool):
            self.least = left if self.least is None else min(self.least, left)


def _key(line: dict) -> tuple[str, str, str] | None:
    """The hour, caller and resource a line counts toward, or None for a line with no time."""
    stamp = values.utc(line.get("at"))
    if stamp is None:
        return None
    caller = str(line.get("caller") or "").split(" < ", 1)[0]
    return stamp[:13], caller, str(line.get("resource") or "")


@dataclass(frozen=True)
class _File:
    handle: BinaryIO
    inode: int
    size: int
    head: str

    def at(self, held: tuple | None) -> int | None:
        """The offset the cursor read this file to, or None where the cursor names another file:
        one of another inode, of another first line where the cursor read past one, or that is
        shorter than the offset."""
        if held is None or held[0] != self.inode or held[1] > self.size:
            return None
        return held[1] if held[1] == 0 or held[2] == self.head else None


def _file(handle: BinaryIO) -> _File:
    stat = os.fstat(handle.fileno())
    return _File(handle, stat.st_ino, stat.st_size, cursors.head(handle))


def _whole(file: _File, start: int) -> tuple[bytes, int]:
    """The whole lines of `file` from `start`, and the offset after the last of them."""
    file.handle.seek(start)
    data = file.handle.read(file.size - start)
    end = data.rfind(b"\n") + 1
    return data[:end], start + end


def _lines(data: bytes) -> Iterator[dict]:
    for raw in data.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict):
            yield line


def read(
    connection: sqlite3.Connection, config: jbus.Config, built: Built, most: int | None
) -> None:
    """Add the lines the log gained since the last build to their hours, unless `most` bytes are
    read already, which leaves the log to the next build. The new file is opened before the old,
    so a rotation between the two opens both on the one file, and the old is left out."""
    with contextlib.ExitStack() as opened:
        try:
            new = _file(opened.enter_context(open(config.state_dir / CALLS, "rb")))
        except OSError:
            return
        if most is not None and built.bytes >= most:
            built.left += 1
            return
        try:
            old: _File | None = _file(opened.enter_context(open(config.state_dir / OLD, "rb")))
        except OSError:
            old = None
        if old is not None and old.inode == new.inode:
            old = None
        held = cursors.held(connection, values.MACHINE, TABLE)
        chunks = []
        start = new.at(held)
        if start is None and old is not None:
            chunks.append(_whole(old, old.at(held) or 0)[0])
        data, end = _whole(new, start or 0)
        chunks.append(data)
    rows: dict[tuple[str, str, str], _Row] = {}
    for chunk in chunks:
        for line in _lines(chunk):
            key = _key(line)
            if key is not None:
                rows.setdefault(key, _Row()).add(line)
    count = sum(len(chunk) for chunk in chunks)
    if not count and start == end:
        return
    connection.execute("BEGIN")
    connection.executemany(
        _ADD,
        [(*key, row.calls, row.not_modified, row.failed, row.least) for key, row in rows.items()],
    )
    cursors.keep(connection, values.MACHINE, TABLE, new.inode, end, new.head, new.size, None)
    connection.execute("COMMIT")
    built.rows[TABLE] += len(rows)
    built.bytes += count
