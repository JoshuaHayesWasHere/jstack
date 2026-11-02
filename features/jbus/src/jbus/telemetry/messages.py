"""The messages of T3 Code's threads, by id, as the store's `messages` table.

T3 Code keeps every message of every thread in its own store (`boxes.store()`), and jbus reads
it read only. A row here is one message, of the user or of the assistant: its id, its thread,
who wrote it, when, and the `kind` of a user's message. It keeps no text: as a user's message is
read, `kind` is worked out of its first few hundred characters, and only the label and the
text's length are kept. The view `ask_ledger` (`jbus.telemetry.schema`) joins each message the
user typed to the row, the answer or the reply that followed it.

A message's `project` is the jbus project whose `projectId` its thread is in, else T3 Code's own
id of the project, so a project jbus does not know yet still has its messages kept.

A build reads on from the last message the store read, by the rowid of T3 Code's table, in
batches of `BATCH`, each written with its cursor in one transaction. The cursor keeps the inode
of T3 Code's store and the id of the message at its rowid; a store that is another file, or
whose rows were numbered again (as `VACUUM` may do), is read again from its start. So is a store
last read under other rules (`RULES`) or another map of projects (`sign`), so that each row
holds what a store built from nothing would. A row is keyed by its message id, so a message read
again replaces its row. A store T3 Code does not have, or cannot give, is left for the next
build.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from typing import TYPE_CHECKING

import jbus
from jbus import boxes
from jbus.telemetry import records

if TYPE_CHECKING:
    from datetime import tzinfo

    from jbus.telemetry import Built

TABLE = "messages"
RULES = 1
"""The version of `kind`'s rules: a change to `kind` raises it, and the next build reads every
message again, so each row is labelled by the rules of today."""
BATCH = 5000
HEAD = 400
"""How much of a user's message `kind` reads."""
COLUMNS = records._columns(
    "id", "thread", "role", "at", "project_id", "created_by", "creation_source", "kind", "text_len"
)
TABLE_SQL = (
    f"CREATE TABLE {TABLE} (project TEXT NOT NULL, key TEXT NOT NULL, "
    + ", ".join(f"{name} {kind}" for name, kind in COLUMNS)
    + f", day TEXT, PRIMARY KEY (project, key)) WITHOUT ROWID;\n"
    f"CREATE INDEX {TABLE}_day ON {TABLE} (day);\n"
    f"CREATE INDEX {TABLE}_thread ON {TABLE} (thread, role, at);\n"
    f"CREATE INDEX {TABLE}_key ON {TABLE} (key);\n"
)
DROPPED = (
    "<task-notification>",
    "<system-reminder>",
    "this session is being continued from a previous conversation",
    "<local-command-",
    "context handoff",
    "base directory for this skill",
    "[request interrupted",
    "caveat: the messages below were generated",
    "generate a title that will help the user",
)
"""The starts of a text that T3 Code or an agent put in the user's turn: the week audit's filter."""
_COMMAND = re.compile(r"^[/$][a-z][\w:-]*")
_READ = """
select m.rowid, m.message_id, m.thread_id, m.role, m.created_at, t.project_id,
json_extract(m.payload_json, '$.createdBy'), json_extract(m.payload_json, '$.creationSource'),
case when m.role = 'user' then substr(json_extract(m.payload_json, '$.text'), 1, ?) end,
case when m.role = 'user' then length(json_extract(m.payload_json, '$.text')) end,
length(m.payload_json) from orchestration_v2_projection_messages m
left join orchestration_v2_projection_threads t on t.thread_id = m.thread_id
where m.rowid > ? order by m.rowid limit ?
"""


def kind(message_id: str, head: str | None) -> str:
    """What a user's message is, by its id and the start of its text: `dropped` where T3 Code or
    an agent wrote it into the user's turn (a system reminder, a task's notification, a skill's
    text), `answer` for the answer to a question box, `resume` for "continue where you left
    off", `command` for a slash command, else `text`. The week audit's filter, in
    `reports/week-audit/week-audit-data/build.py` of the home."""
    said = " ".join((head or "").split()).lower()
    if not said or said.startswith(DROPPED):
        return "dropped"
    if message_id.startswith("async-answer:"):
        return "answer"
    if said.rstrip(".") == "continue where you left off":
        return "resume"
    if _COMMAND.match(said) or "<command-message>" in said[:200]:
        return "command"
    return "text"


def sign(projects: Iterable[jbus.Project]) -> str:
    """The rules and the map of projects the store's messages were read under."""
    return f"{RULES} " + json.dumps(sorted((one.project_id, one.name) for one in projects))


def read(
    connection: sqlite3.Connection,
    config: jbus.Config,
    zone: tzinfo | None,
    built: Built,
    most: int | None,
) -> None:
    """Keep each message of T3 Code's store the store has not read, batch by batch, and leave
    the rest once `most` bytes are read."""
    where = boxes.store()
    if not where.is_file():
        return
    names = {one.project_id: one.name for one in config.projects}
    signed = sign(config.projects)
    try:
        t3 = sqlite3.connect(f"file:{where}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error:
        return
    try:
        try:
            inode = where.stat().st_ino
            start = _start(connection, t3, inode, signed)
        except (sqlite3.Error, OSError):
            return
        while True:
            if most is not None and built.bytes >= most:
                built.left += 1
                return
            try:
                found = t3.execute(_READ, (HEAD, start, BATCH)).fetchall()
            except sqlite3.Error:
                return
            if not found:
                return
            rows = []
            for rowid, mid, thread, role, at, project_id, by, source, head, length, size in found:
                stamp = records.utc(at)
                rows.append(
                    (
                        names.get(project_id) or project_id or "",
                        mid,
                        mid,
                        thread,
                        role,
                        stamp,
                        project_id,
                        by,
                        source,
                        kind(mid, head) if role == "user" else None,
                        length,
                        records.day(stamp, zone),
                    )
                )
                built.bytes += size or 0
                start = rowid
            _keep(connection, rows, inode, start, found[-1][1], signed, built)
    finally:
        t3.close()


def _start(connection: sqlite3.Connection, t3: sqlite3.Connection, inode: int, signed: str) -> int:
    """The rowid to read on from: the cursor's where it is still this store's, else 0."""
    held = connection.execute(
        "SELECT inode, offset, head FROM cursors WHERE project = '' AND source = ?", (TABLE,)
    ).fetchone()
    was = connection.execute("SELECT value FROM meta WHERE name = ?", (TABLE,)).fetchone()
    if not held or held[0] != inode or not was or was[0] != signed:
        return 0
    there = t3.execute(
        "select message_id from orchestration_v2_projection_messages where rowid = ?", (held[1],)
    ).fetchone()
    return held[1] if there and there[0] == held[2] else 0


def _keep(connection, rows, inode: int, offset: int, head: str, signed: str, built) -> None:
    """Write a batch's rows, each in place of any row of its message, with the cursor."""
    names = ["project", "key", *(name for name, _ in COLUMNS), "day"]
    marks = ", ".join("?" for _ in names)
    connection.execute("BEGIN")
    before = connection.total_changes
    connection.executemany(
        f"DELETE FROM {TABLE} WHERE key = ? AND project <> ?", [(row[1], row[0]) for row in rows]
    )
    connection.executemany(
        f"INSERT OR REPLACE INTO {TABLE} ({', '.join(names)}) VALUES ({marks})", rows
    )
    built.rows[TABLE] += connection.total_changes - before
    connection.execute(
        "INSERT OR REPLACE INTO cursors (project, source, inode, offset, head, size, mtime) "
        "VALUES ('', ?, ?, ?, ?, NULL, NULL)",
        (TABLE, inode, offset, head),
    )
    connection.execute("INSERT OR REPLACE INTO meta (name, value) VALUES (?, ?)", (TABLE, signed))
    connection.execute("COMMIT")
