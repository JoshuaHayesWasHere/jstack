"""A thread as T3 Code's own store keeps it, read with no MCP call: the user's newest message of a
thread, and `jbus thread <slug or thread id>`, what a thread last said.

T3 Code keeps its state in `$T3CODE_HOME/userdata/statev2.sqlite` (`~/.t3` by default), and jbus
reads it read only (`store`), as `jbus.boxes` does. A home used to call `t3_thread_read` for two
things this module gives it at no cost to its context:

- the id of the user's newest message in a thread, to pass on as `--message`: `newest_own` is the
  newest message T3 Code has as the user's own (role `user`, `createdBy` `user`, not streaming),
  on T3 Code's index of a thread's newest user messages, and `jbus.t3.resolved` turns a
  `<thread id>/last` into it;
- the id of an older message of the user's, such as a standing word: `own_saying` lists the
  user's own messages that hold some words, `jbus thread [<thread>] --said <words>`;
- what another thread last said: `view` reads the thread's title, whether it is archived or
  settled, its last run's status and time, its pull requests, and its newest assistant message,
  and `View.text` prints them in at most `CAP` characters, that message cut at `SAID` with a line
  that says so.

A slug names the newest thread whose title is a role's for it (`crew: <slug>`, `scout: <slug>`,
`review: <slug>, <n>`, `home: <slug>`), and a line names each of the slug's next two threads.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jbus
from jbus import verbs

STORE = Path("userdata") / "statev2.sqlite"
SAID = 2000
"""The most of a thread's last assistant message `jbus thread` prints."""
CAP = 2600
"""The most `jbus thread` prints in all."""
PULLS = 4
"""The most pull requests `jbus thread` names, the newest linked first."""
FOUND = 5
"""The most messages `jbus thread --said` prints."""
TITLES = ("crew: {slug}", "scout: {slug}", "home: {slug}")
REVIEW = "review: {slug}, "

_NEWEST_OWN = """
select message_id from orchestration_v2_projection_messages
where thread_id = ? and role = 'user' and streaming = 0
and json_extract(payload_json, '$.createdBy') = 'user'
order by updated_at desc, message_id desc limit 1
"""
_OWN_SAYING = """
select message_id, thread_id, created_at, json_extract(payload_json, '$.text')
from orchestration_v2_projection_messages
where role = 'user' and streaming = 0 and json_extract(payload_json, '$.createdBy') = 'user'
and instr(json_extract(payload_json, '$.text'), ?) > 0
"""
_LAST_SAID = """
select json_extract(payload_json, '$.text') from orchestration_v2_projection_messages
where thread_id = ? and role = 'assistant' and streaming = 0
order by created_at desc, message_id desc limit 1
"""
_LAST_RUN = """
select status, coalesce(completed_at, requested_at) from orchestration_v2_projection_runs
where thread_id = ? order by ordinal desc limit 1
"""
_THREAD = """
select thread_id, title, archived_at, payload_json from orchestration_v2_projection_threads
where deleted_at is null and {where} order by updated_at desc
"""


def store() -> Path:
    return Path(os.environ.get("T3CODE_HOME") or Path.home() / ".t3") / STORE


@contextmanager
def opened(where: Path) -> Iterator[sqlite3.Connection]:
    """The store at `where`, read only. Raise `Refused` when there is none or it cannot be read."""
    if not where.is_file():
        raise jbus.Refused(f"refused: T3 Code keeps no store at {where}")
    try:
        with closing(sqlite3.connect(f"file:{where}?mode=ro", uri=True)) as db:
            yield db
    except sqlite3.Error as error:
        raise jbus.Refused(
            f"refused: T3 Code's store at {where} cannot be read ({error})"
        ) from None


def newest_own(where: Path, thread: str) -> str | None:
    """The id of the newest message of the thread that T3 Code has as the user's own, or None
    where it has none."""
    with opened(where) as db:
        found = db.execute(_NEWEST_OWN, (thread,)).fetchone()
    return str(found[0]) if found else None


@dataclass(frozen=True)
class Pull:
    number: int
    url: str
    state: str
    checks: str


@dataclass(frozen=True)
class View:
    """A thread as `jbus thread` shows it. `status` is `archived`, `settled` or `open`, the first
    that holds. `run` is the last run's status and when it ended, or when it was asked for where it
    has not ended, empty where the thread has had no run. `said` is the newest assistant message,
    whole. `others` are the other threads the slug named, as `<title> <id>`."""

    thread: str
    title: str
    status: str
    run: tuple[str, str]
    pulls: tuple[Pull, ...]
    said: str
    others: tuple[str, ...] = ()

    def text(self) -> str:
        """The view in at most `CAP` characters. The lines above the message are cut to what
        leaves the message `SAID` of them, and the message to what is left, so the line that
        says it was cut is always there."""
        status, at = self.run
        lines = [
            f"{self.title} ({self.thread})",
            f"status: {self.status}",
            f"last run: {status}, {at}" if status else "last run: none",
            *(f"also: {one}" for one in self.others[:2]),
            *(
                f"pull request #{one.number}: {one.state}, checks {one.checks}, {one.url}"
                for one in self.pulls[:PULLS]
            ),
        ]
        if len(self.pulls) > PULLS:
            lines.append(f"and {len(self.pulls) - PULLS} more pull requests")
        if not self.said:
            return "\n".join([*lines, "last said: nothing yet"])[:CAP]
        cut = f"(cut: the first {{}} of {len(self.said)} characters)"
        head = "\n".join([*lines, "last said:"])[: CAP - SAID - len(cut) - 4]
        room = min(SAID, CAP - len(head) - len(cut) - 4)
        shown = self.said[:room]
        tail = [cut.format(len(shown))] if len(shown) < len(self.said) else []
        return "\n".join([head, shown, *tail])


def _pulls(payload: dict[str, Any]) -> tuple[Pull, ...]:
    listed = payload.get("pullRequests") or []
    ordered = sorted(listed, key=lambda one: str(one.get("linkedAt") or ""), reverse=True)
    return tuple(
        Pull(
            int(one.get("number") or 0),
            str(one.get("url") or ""),
            str((one.get("snapshot") or {}).get("state") or "unknown"),
            str((one.get("snapshot") or {}).get("checksState") or "unknown"),
        )
        for one in ordered
    )


def _threads(db: sqlite3.Connection, named: str) -> list[tuple[Any, ...]]:
    """The threads `named` names, the newest first: the thread of that id, else those whose title
    is a role's for that slug."""
    found = db.execute(_THREAD.format(where="thread_id = ?"), (named,)).fetchall()
    if found:
        return found
    titles = [one.format(slug=named) for one in TITLES]
    where = f"(title in ({', '.join('?' * len(titles))}) or substr(title, 1, ?) = ?)"
    review = REVIEW.format(slug=named)
    return db.execute(_THREAD.format(where=where), (*titles, len(review), review)).fetchall()


def view(where: Path, named: str) -> View:
    """The thread `named` names, a thread id or a slug, from the store at `where`. Raise `Refused`
    where it names none."""
    with opened(where) as db:
        found = _threads(db, named)
        if not found:
            raise jbus.Refused(f"refused: T3 Code's store has no thread {named}, by id or by slug")
        thread, title, archived, raw = found[0]
        run = db.execute(_LAST_RUN, (thread,)).fetchone()
        said = db.execute(_LAST_SAID, (thread,)).fetchone()
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = {}
    status = "archived" if archived else "settled" if payload.get("settledAt") else "open"
    return View(
        thread=str(thread),
        title=str(title),
        status=status,
        run=(str(run[0]), str(run[1])) if run else ("", ""),
        pulls=_pulls(payload),
        said=str(said[0] or "") if said else "",
        others=tuple(f"{one[1]} {one[0]}" for one in found[1:]),
    )


def own_saying(where: Path, words: str, thread: str = "") -> list[str]:
    """The user's own messages that hold `words`, in the thread where one is given, the newest
    first and at most `FOUND` of them, each as `<thread id>/<message id> <time>: <its start>`."""
    asked = (
        _OWN_SAYING + (" and thread_id = ?" if thread else "") + " order by created_at desc limit ?"
    )
    with opened(where) as db:
        found = db.execute(asked, (words, *((thread,) if thread else ()), FOUND)).fetchall()
    return [
        f"{one}/{message} {at}: {' '.join(str(text).split())[:100]}"
        for message, one, at, text in found
    ]


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("thread", nargs="?", help="the thread: its id, or the slug of its row")
    parser.add_argument(
        "--said",
        metavar="WORDS",
        help="in place of the view, the user's own messages that hold these words, in the thread "
        "where one is given, each as THREAD/MESSAGE, its time and its start",
    )


def _run(args: argparse.Namespace, _: jbus.Config) -> int:
    if args.said:
        found = own_saying(store(), args.said, args.thread or "")
        print("\n".join(found) if found else f"none: no message of the user's holds {args.said!r}")
        return 0
    if not args.thread:
        raise jbus.Refused("refused: jbus thread takes a thread, by its id or a slug, or --said")
    print(view(store(), args.thread).text())
    return 0


VERBS = (
    verbs.Verb(
        "thread",
        "what a thread last said, from T3 Code's store: its status, last run, pull requests and "
        "last message",
        _arguments,
        _run,
        config=False,
    ),
)
