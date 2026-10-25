"""`jbus flow nudges`: how many times the owner had to restart work that had stopped, in a window.

It reads T3 Code's store (`statev2.sqlite`, opened read-only) for the messages of the threads
whose title is like `--title`, `home: %` by default, every home. The owner's messages are the
user messages T3 Code says the user wrote (`createdBy` `user`, from the web or a phone) and the
words jbus carried to a home (`jbus.word.MESSAGE`), read as the words after its preamble with
the Sous Chef's bracket left out. A slash command and an empty text are no message.

A message is a nudge when it has a stall word (`STALL`) and does not say not to stall, or when it
is a bare "Go" and the home's last message before it asked the owner nothing (`ASKED`). A
message carried to a second home is counted once: a message with the same first 40 characters
in another thread within 10 minutes is that message again. Two of the same words in one thread
are two messages, as two "Go"s three minutes apart are. The rule is the appendix's `nudges.sh`
of the scout `fl-audit-recheck`, made deterministic so each week's count compares with the last.

`messages` and `nudges` are pure over `Message` records, so a test drives them with no store.
`read` is the one function that opens the store.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jbus import Refused

DEFINITION = (
    "Definition: a nudge is a message from Josh in a home thread that restarts work that had "
    "stopped without a decision of his: it tells the home to carry on, or asks why work "
    "stopped, and it answers no question the home asked him. A message carried to a second "
    "home counts once. Approvals, answers, status questions and new work are not nudges."
)
STORE = Path.home() / ".t3" / "userdata" / "statev2.sqlite"
TITLE = "home: %"
THREADS = "orchestration_v2_projection_threads"
MESSAGES = "orchestration_v2_projection_messages"
CARRIED = re.compile(r"^jbus: this is \S+'s own word, said ")
BRACKET = re.compile(r"\[[^]]*context[^]]*\]")
LINK = re.compile(r"\[[^]]*\]\([^)]*\)")
STALL = re.compile(
    r"\bstall(ed|ing)?\b|\bstuck\b|nothing (is )?moving|why are we waiting|what are we waiting"
    r"|are we moving|moving again|push you|left off|keep moving|keep going|carry on|full steam"
    r"|continue moving|restart the",
    re.I,
)
NOT_STALL = re.compile(r"not stall|don.t stall", re.I)
BARE_GO = re.compile(r"^go[.!]*$", re.I)
ASKED = re.compile(r"say \"?go|your go|waits? on your|wait(s|ing)? for your|my pick|\?\s*$", re.I)
SAME = 40
CARRY_SECONDS = 600


@dataclass(frozen=True)
class Message:
    """One message of a thread, as T3 Code's store has it. `by` is its `createdBy`."""

    thread: str
    home: str
    at: datetime
    role: str
    by: str
    text: str


@dataclass(frozen=True)
class Said:
    """One message of the owner's: its words, flattened to one line, its first line, and the
    text of the home's last message before it in the same thread."""

    thread: str
    home: str
    at: datetime
    words: str
    first: str
    before: str


def _flat(text: str) -> str:
    text = LINK.sub("", text).replace("‘", "'").replace("’", "'")
    return " ".join(text.split())


def words(message: Message) -> str | None:
    """Return the owner's words in `message`, or None when it is not the owner's."""
    if message.role != "user":
        return None
    if CARRIED.match(message.text):
        return BRACKET.sub("", " ".join(message.text.split("\n\n")[1:]))
    return message.text if message.by == "user" else None


def messages(found: list[Message], since: datetime, until: datetime) -> list[Said]:
    """Return the owner's messages in `[since, until)`, oldest first, a carried copy left out."""
    kept: list[Said] = []
    before: dict[str, str] = {}
    for one in sorted(found, key=lambda each: each.at):
        if one.role == "assistant":
            before[one.thread] = one.text
            continue
        said = words(one)
        if said is None or not since <= one.at < until:
            continue
        flat = _flat(said)
        if not flat or flat.startswith("/"):
            continue
        head = flat[:SAME].lower()
        if any(
            other.thread != one.thread
            and other.words[:SAME].lower() == head
            and abs((one.at - other.at).total_seconds()) < CARRY_SECONDS
            for other in kept
        ):
            continue
        first = _flat(next(line for line in said.splitlines() if line.strip()))
        kept.append(Said(one.thread, one.home, one.at, flat, first, before.get(one.thread, "")))
    return kept


def nudge(said: Said) -> bool:
    """Say whether one of the owner's messages is a nudge, by the rule of `DEFINITION`."""
    if NOT_STALL.search(said.words):
        return False
    if STALL.search(said.words):
        return True
    return bool(BARE_GO.match(said.words)) and not ASKED.search(said.before)


def nudges(said: list[Said]) -> list[Said]:
    return [one for one in said if nudge(one)]


def read(store: Path, title: str) -> list[Message]:
    """Return every finished message of each thread whose title is like `title`, read-only."""
    if not store.is_file():
        raise Refused(f"refused: {store} is not T3 Code's store")
    query = f"""
        with h as (
            select thread_id, json_extract(payload_json, '$.title') as title from {THREADS}
            where json_extract(payload_json, '$.title') like ?
        )
        select m.thread_id, h.title, m.created_at, m.role,
            coalesce(json_extract(m.payload_json, '$.createdBy'), ''),
            coalesce(json_extract(m.payload_json, '$.text'), '') from {MESSAGES} m
        join h on h.thread_id = m.thread_id
        where m.streaming = 0
    """
    try:
        with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as db:
            rows = db.execute(query, (title,)).fetchall()
    except sqlite3.Error as error:
        raise Refused(f"refused: {store} cannot be read: {error}") from None
    return [
        Message(thread, home, datetime.fromisoformat(at), role, by, text)
        for thread, home, at, role, by, text in rows
    ]


def text(said: list[Said], found: list[Said]) -> str:
    """Return each nudge as a line, its time, home, thread and first line, and the counts."""
    out = [
        f"{one.at.astimezone(UTC):%Y-%m-%dT%H:%MZ}\t{one.home}\t{one.thread}\t{one.first[:100]}"
        for one in found
    ]
    return "\n".join([*out, f"messages {len(said)}, nudges {len(found)}"])
