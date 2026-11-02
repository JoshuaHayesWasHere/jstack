"""Where a build last stopped in each file it reads: the store's `cursors` table.

A cursor is keyed by a project and a source: a jbus record file's table under its project, or a
transcript's path under its provider (`jbus.telemetry.tokens`). It keeps the file's inode, the
offset read to, the hash of its first line, and for a file read whole, its size and time.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any


def head(handle: Any) -> str:
    """The hash of a file's first whole line, or nothing where it has none yet."""
    handle.seek(0)
    first = handle.readline()
    return hashlib.sha256(first).hexdigest()[:16] if first.endswith(b"\n") else ""


def held(connection: sqlite3.Connection, project: str, source: str) -> tuple | None:
    """The cursor's inode, offset, head, size and time, or None where there is none."""
    return connection.execute(
        "SELECT inode, offset, head, size, mtime FROM cursors WHERE project = ? AND source = ?",
        (project, source),
    ).fetchone()


def keep(connection: sqlite3.Connection, project: str, source: str, *values: Any) -> None:
    """Write the cursor: its inode, offset, head, size and time."""
    connection.execute(
        "INSERT OR REPLACE INTO cursors (project, source, inode, offset, head, size, mtime) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project, source, *values),
    )
