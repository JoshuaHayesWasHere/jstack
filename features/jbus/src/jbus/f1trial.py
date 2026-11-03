"""A trial of the narrow rule F1, which logs the gates it would hold and holds none.

The gate-quality scout's F1 (`reports/gate-quality/c2_narrow.py` in the root home) would hold a
gate that a pass closes by silence when two things are true. Its default removes or bypasses
something (`REVERSES`), and a word the user typed earlier, with a marker of a standing rule such
as always, should, keep or never (`MARK`), shares two terms or more with the gate's question,
default and options, one of them in the default. A term counts only when it is rare: in at most
one word in a hundred of the user's (`RARE`). F1 was tuned on the two cases it was built for, so
jbus tries it on new gates and changes nothing by it.

At each close by silence (`questions.silent`), jbus reads the user's words and runs F1 (`held`).
It then adds one line to `f1-trial.jsonl` in the project's state directory for each question it
closed: the question's `number`, `slug` and `asked_at`, the pass's time `at`, whether F1 would
hold it (`would_hold`), and each matched word as its `id` and the shared `terms`, rarest first.
When the read or the rule fails, the line has the `error` in place of `would_hold` and `words`.
The line holds ids and terms, never the text of a word, and nothing in it changes how the gate
closed.

The words are read only, from two places. The first is T3 Code's store (`boxes.store`): every
message its user created in the last `WINDOW`, as the scout's dataset keeps them (`kept`), with
the T3 message's id. The second is the project's word acts that came from the bot's chat, with
the id `act:<the act's id>`. Words of every project count towards how rare a term is, and only
the gate's own project's words, said before the gate was asked, can match it.

A reader looks at the log two weeks after the trial starts, for the true catches against the
false holds.
"""

from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsettings
from jbus import boxes
from jbus.telemetry.messages import DROPPED
from jsettings.store import append_jsonl

if TYPE_CHECKING:
    from jbus.passes import Pass
    from jbus.questions import Question

LOG = "f1-trial.jsonl"
WINDOW = timedelta(days=14)
RARE = 0.01
SHARED = 2
CUT = 4000
LONGEST = 2500
STOP = frozenset(
    [
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "from",
        "have",
        "what",
        "when",
        "then",
        "them",
        "they",
        "into",
        "over",
        "just",
        "also",
        "only",
        "been",
        "were",
        "will",
        "would",
        "should",
        "could",
        "about",
        "which",
        "their",
        "there",
        "here",
        "your",
        "yours",
        "does",
        "done",
        "make",
        "made",
        "like",
        "want",
        "need",
        "more",
        "than",
        "each",
        "other",
        "some",
        "such",
        "very",
        "once",
    ]
)
MARK = re.compile(
    r"\b(always|never|every|must|should|shouldn'?t|don'?t|do not|stop|keep|no longer"
    r"|from now on|need to|needs to)\b",
    re.I,
)
REMOVE = re.compile(
    r"\b(drop|drops|dropped|remove|removes|removed|retire|retires|retired|stop|stops"
    r"|no longer|goes|gone|cut|cuts|delete|deletes|deleted|instead|replace|replaces"
    r"|away|leave out|age out)\b",
    re.I,
)
BYPASS = re.compile(
    r"\b(its own|their own|by hand|itself|themselves|skip|skips|without|outside"
    r"|bypass|instead of)\b",
    re.I,
)
PASTE = re.compile(
    r"t3-citation://|^\s*[\[#]|here is the response|^From the |^Josh \(|^Take a census", re.I
)
_HEARD = """
select m.message_id, t.project_id, m.created_at, json_extract(m.payload_json, '$.text') from
orchestration_v2_projection_messages m
join orchestration_v2_projection_threads t on t.thread_id = m.thread_id
where m.role = 'user' and m.created_at >= ?
and json_extract(m.payload_json, '$.createdBy') = 'user'
"""


@dataclass(frozen=True)
class Word:
    """One message the user typed: the project it was said in, when, its id, and its text."""

    project: str
    at: datetime
    id: str
    text: str


@dataclass(frozen=True)
class Hit:
    """A word F1 matched: its id and the rare terms it shares with the gate."""

    id: str
    terms: tuple[str, ...]


def terms(text: str) -> set[str]:
    text = text.lower().replace("-", " ").replace("_", " ")
    return {one for one in re.findall(r"[a-z][a-z0-9]{3,}", text) if one not in STOP}


def reverses(default: str) -> bool:
    """Return whether a default removes or bypasses something."""
    return bool(REMOVE.search(default) or BYPASS.search(default))


def held(project: str, one: Question, words: Sequence[Word]) -> tuple[Hit, ...]:
    """Return the words for which F1 holds the question, rarest first, or none when it would
    let silence close it. `words` are every word heard, of every project: how rare a term is
    is counted over all of them."""
    if not reverses(one.default):
        return ()
    asked = datetime.fromisoformat(one.asked_at)
    seen = Counter(term for word in words for term in terms(word.text))
    rare = math.floor(RARE * len(words))
    options = " ".join(f"{option.name} {option.follows}" for option in one.options)
    gate = {t for t in terms(f"{one.question} {one.default} {options}") if seen[t] <= rare}
    default = terms(one.default)
    hits = []
    for word in words:
        if word.project != project or word.at >= asked or not standing(word.text):
            continue
        shared = gate & terms(word.text)
        if len(shared) >= SHARED and shared & default:
            hits.append(Hit(word.id, tuple(sorted(shared))))
    if not hits:
        return ()
    weight = {t: math.log(len(words) / max(seen[t], 1)) for t in gate}
    return tuple(sorted(hits, key=lambda hit: -sum(weight[t] for t in hit.terms)))


def standing(text: str) -> bool:
    """Return whether a word was typed, not pasted, and says a standing rule."""
    return len(text) <= LONGEST and not PASTE.search(text) and bool(MARK.search(text))


def kept(text: str) -> bool:
    """Return whether a user message is a word of the user's, not a notification, a skill's
    text or another message T3 Code records as the user's."""
    said = re.sub(r"\s+", " ", text).strip().lower()
    return bool(said) and not said.startswith(DROPPED)


def heard(where: Path, state: Path, project: str, now: datetime) -> list[Word]:
    """Return the user's words of the last `WINDOW`, read only. Raise `sqlite3.Error` or
    `OSError` when the store cannot be read. `acts` is imported here since it reads `questions`,
    which calls this module."""
    from jbus import acts

    if not where.is_file():
        raise FileNotFoundError(f"T3 Code keeps no store at {where}")
    since = (now - WINDOW).astimezone(UTC)
    found = []
    with sqlite3.connect(f"file:{where}?mode=ro", uri=True) as db:
        for message, owner, at, text in db.execute(_HEARD, (since.strftime("%Y-%m-%dT%H:%M:%S"),)):
            if text and kept(text) and not message.startswith("limit-resume:"):
                found.append(Word(owner, datetime.fromisoformat(at), message, text[:CUT]))
    for act in acts.read(state):
        if act.get("verb") == "word" and act.get("source") == "bot-chat" and act.get("words"):
            at = datetime.fromisoformat(act["at"])
            if at >= since:
                found.append(Word(project, at, f"act:{act['id']}", act["words"][:CUT]))
    return found


def line(run: Pass, one: Question, words: Sequence[Word] | Exception) -> dict[str, Any]:
    said: dict[str, Any] = {
        "at": jsettings.stamp(run.now),
        "number": one.number,
        "slug": one.slug,
        "asked_at": one.asked_at,
    }
    if isinstance(words, Exception):
        return said | {"error": f"{type(words).__name__}: {words}"}
    try:
        hits = held(run.project.project_id, one, words)
    except Exception as error:
        return said | {"error": f"{type(error).__name__}: {error}"}
    return said | {
        "would_hold": bool(hits),
        "words": [{"id": hit.id, "terms": list(hit.terms)} for hit in hits],
    }


def log(run: Pass, closed: Iterable[Question]) -> None:
    """Add one line to the trial's log for each question that silence closed this pass. Whatever
    the read or the rule raises goes on the line, so the trial changes no close."""
    closed = list(closed)
    if not closed:
        return
    try:
        words: Sequence[Word] | Exception = heard(
            boxes.store(), run.state, run.project.project_id, run.now
        )
    except Exception as error:
        words = error
    lines = [line(run, one, words) for one in closed]
    try:
        append_jsonl(run.state / LOG, lines, mode=0o600)
    except OSError as error:
        run.say(f"f1 trial: {run.state / LOG} could not be written ({error})")
