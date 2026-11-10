"""The pictures the user sent in a T3 thread, for a brief's `Shown:` line (`jbriefs --shown`).

T3 Code keeps each message in its store's `orchestration_v2_projection_messages`, and a picture
the user sent with one is an item of its payload's `attachments`, `{"type": "image", "id": ...}`.
Its file is `<id>.<extension>` in T3's attachments directory, and stays there until its thread is
deleted. A home names each path on a brief's `Shown:` line, and the crew opens it with the Read
tool before its first edit.

The store is opened read-only, and nothing is written, copied or moved. A message counts when its
role is `user` and its `createdBy` is `user` (or absent), the user's own words: a message an agent
sent in the user's place is left out.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from glob import escape
from pathlib import Path

STORE = Path.home() / ".t3" / "userdata" / "statev2.sqlite"
ATTACHMENTS = Path.home() / ".t3" / "userdata" / "attachments"
WORDS = 12
GONE = "gone"
NO_WORDS = "[User attached one or more files without additional text."

_LINK = re.compile(r"!\[[^\]]*\]\(t3-context://[^)]*\)")
_QUERY = """
select message_id, created_at, payload_json from orchestration_v2_projection_messages
 where thread_id = ? and role = 'user' and streaming = 0
   and coalesce(json_extract(payload_json, '$.createdBy'), 'user') = 'user'
   and created_at >= ?
 order by created_at, message_id
"""


@dataclass(frozen=True)
class Shown:
    """A user message with pictures: its time and id as the store has them, its first words, and
    the file of each picture, or None where it is not on disk."""

    time: str
    message: str
    words: str
    paths: tuple[Path | None, ...]

    def line(self) -> str:
        files = " ".join(GONE if path is None else str(path) for path in self.paths)
        return f"{self.time} {self.message} {json.dumps(self.words, ensure_ascii=False)} {files}"


def first_words(text: str) -> str:
    """The message's first words on one line, with T3's links to its pictures taken out."""
    if text.startswith(NO_WORDS):
        return ""
    return " ".join(_LINK.sub(" ", text).split()[:WORDS])


def file_of(attachments: Path, picture: str) -> Path | None:
    """The picture's file, `<id>.<extension>`, or None where none is on disk."""
    return next(iter(sorted(attachments.glob(f"{escape(picture)}.*"))), None)


def pictures(store: Path, attachments: Path, thread: str, since: str = "") -> list[Shown]:
    """Each user message of the thread from `since` on (the store's own time format) that has a
    picture, in the order they were sent. Raises sqlite3.Error where the store cannot be read."""
    with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as db:
        rows = db.execute(_QUERY, (thread, since)).fetchall()
    found = []
    for message, time, payload in rows:
        said = json.loads(payload)
        images = [one["id"] for one in said.get("attachments") or [] if one.get("type") == "image"]
        if images:
            paths = tuple(file_of(attachments, one) for one in images)
            found.append(Shown(time, message, first_words(said.get("text") or ""), paths))
    return found
