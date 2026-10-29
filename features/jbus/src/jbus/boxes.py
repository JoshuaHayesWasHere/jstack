"""Read the user's answer to a question box in a T3 Code thread, the basis `--pick` of an approval.

A question box is what an agent's AskUserQuestion shows in T3 Code: a thread's item of the
type `user_input_request`, by an id `turn-item:runtime-request:<the request's id>`, which holds
the questions and the labels each offers. jbus reads the item with `t3_thread_read`, as it
reads a message (`Client.item`). The item does not say who answered it, nor what: an agent may
answer a box with T3 Code's pending-request tool, and T3 Code shows that answer as the user's. So
jbus reads the rest in T3 Code's own store, `$T3CODE_HOME/userdata/statev2.sqlite` (`~/.t3` by
default), read only, as `jbriefs.sends` does: the request's row, with its answers and when it
was resolved, and the command that resolved it. T3 Code gives a command that an MCP client sent
an id that begins `mcp:`, and a command from its app a bare UUID, so a box resolved by a bare
UUID is the user's own answer, and any other is refused (`by_user`).

A pick is a label the user chose among those the question offered (`party.Pick`). Text the user
typed in place of a label is no pick: it is kept in the words, and approves nothing.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.parse
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

import jsettings
from jbus import Config, Refused, party, queue
from jbus.t3 import Client, T3Error

KIND = "user_input_request"
PREFIX = "turn-item:runtime-request:"
STORE = Path("userdata") / "statev2.sqlite"
MCP = "mcp:"
_APP = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_RESOLVED = """
select e.command_id from orchestration_events e
join orchestration_command_receipts r on r.command_id = e.command_id
where e.aggregate_kind = 'thread' and e.stream_id = ? and e.event_type = 'runtime-request.updated'
and r.command_type = 'runtime-request.respond'
and json_extract(e.payload_json, '$.id') = ?
and json_extract(e.payload_json, '$.status') = 'resolved'
order by e.sequence
"""


def store() -> Path:
    return Path(os.environ.get("T3CODE_HOME") or Path.home() / ".t3") / STORE


@dataclass(frozen=True)
class Answered:
    """A request as T3 Code's store keeps it: its status, when it was resolved, its answers by
    question, and the commands that resolved it."""

    status: str
    resolved_at: str
    answers: dict[str, Any]
    commands: tuple[str, ...]


def answered(where: Path, thread: str, request: str) -> Answered | None:
    """Return the request of the thread from the store at `where`, or None when the store has no
    such request. Raise `Refused` when the store cannot be read."""
    if not where.is_file():
        raise Refused(f"refused: T3 Code keeps no store at {where}")
    try:
        with sqlite3.connect(f"file:{where}?mode=ro", uri=True) as db:
            found = db.execute(
                "select status, resolved_at, payload_json"
                " from orchestration_v2_projection_runtime_requests"
                " where runtime_request_id = ? and thread_id = ?",
                (request, thread),
            ).fetchone()
            commands = [one for (one,) in db.execute(_RESOLVED, (thread, request))]
    except sqlite3.Error as error:
        raise Refused(f"refused: T3 Code's store at {where} cannot be read ({error})") from None
    if found is None:
        return None
    status, resolved_at, payload = found
    try:
        answers = json.loads(payload).get("answers") or {}
    except (ValueError, AttributeError):
        answers = {}
    if not isinstance(answers, dict):
        answers = {}
    return Answered(str(status), str(resolved_at or ""), answers, tuple(map(str, commands)))


def by_user(commands: tuple[str, ...]) -> str:
    """Return why the commands are not the user's own answer, or nothing when T3 Code's app
    sent every one of them."""
    if not commands:
        return "T3 Code's store holds no command that answered it"
    for one in commands:
        if one.startswith(MCP):
            return f"an agent answered it through T3 Code's MCP server (command {one})"
        if not _APP.fullmatch(one):
            return f"command {one} answered it, and it is not T3 Code's app"
    return ""


def offered(text: str) -> dict[str, list[str]]:
    """Return the labels each question of a box offers, by the question, from the item's text.
    A text that is not the box's questions offers none."""
    try:
        asked = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(asked, list):
        return {}
    labels: dict[str, list[str]] = {}
    for one in asked:
        if not isinstance(one, dict):
            continue
        options = one.get("options") if isinstance(one.get("options"), list) else []
        named = [str(o.get("label")) for o in options if isinstance(o, dict) and o.get("label")]
        for key in dict.fromkeys(str(one.get(k)) for k in ("id", "question") if one.get(k)):
            labels[key] = named
    return labels


def picks(answers: dict[str, Any], labels: dict[str, list[str]]) -> tuple[party.Pick, ...]:
    """Return each answer that is a label its question offered, in the order given."""
    found = []
    for question, given in answers.items():
        chosen = given if isinstance(given, list) else [given]
        for one in chosen:
            if str(one) in labels.get(question, []):
                found.append(party.Pick(question, str(one)))
    return tuple(found)


def words(answers: dict[str, Any]) -> str:
    """Return the answers on one line, each question with what was chosen or typed."""
    said = []
    for question, given in answers.items():
        chosen = given if isinstance(given, list) else [given]
        said.append(f"{question}: {', '.join(str(one) for one in chosen)}")
    return " ".join("; ".join(said).split())


def picked(config: Config, ref: str) -> queue.Said:
    """Read the user's answer to the question box `<thread id>/<item id>` from T3 Code now: the
    item from its server, and who answered it, when and with what from its store. Return the
    answer on one line, its time in the user's zone, the thread's title, and the labels picked.

    It refuses an item that is not a question box, a box nobody answered yet, and a box that
    an agent, or anything but T3 Code's app, answered, each with the reason.
    """
    thread, _, item = ref.partition("/")
    if not thread or not item.startswith(PREFIX):
        raise Refused(f'refused: --pick is "<thread id>/{PREFIX}<request>", not {ref}')
    try:
        one, text, title = Client(config.server, config.token_path).item(
            thread, item, view="activity"
        )
    except T3Error as error:
        raise Refused(f"refused: T3 Code gave no item {ref} ({error})") from error
    if one.get("type") != KIND:
        raise Refused(f"refused: item {ref} is a {one.get('type') or 'thing'}, not a question box")
    request = urllib.parse.unquote(item.removeprefix(PREFIX))
    where = store()
    kept = answered(where, thread, request)
    if kept is None:
        raise Refused(f"refused: T3 Code's store at {where} has no request {request}")
    if kept.status != "resolved" or not kept.answers:
        raise Refused(f"refused: question box {ref} is not answered: T3 Code has it {kept.status}")
    why = by_user(kept.commands)
    if why:
        raise Refused(f"refused: question box {ref} is not {config.user.user}'s own answer: {why}")
    try:
        at = jsettings.when(kept.resolved_at)
    except ValueError:
        raise Refused(f"refused: question box {ref} has no time it was answered") from None
    at = at if at.tzinfo else at.replace(tzinfo=UTC)
    chosen = picks(kept.answers, offered(text))
    return queue.Said(words(kept.answers), config.user.stamp(at), title, True, ref, chosen)
