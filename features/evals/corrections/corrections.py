# /// script
# requires-python = ">=3.12"
# ///
"""Count the user's corrections of a home's replies, by class, over a window.

    uv run --script features/evals/corrections/corrections.py --since 2026-11-02 --until 2026-11-09

It reads T3 Code's store read only: the user's own messages (not an agent's sends) in the threads
whose title starts `home: `, each with the reply before it in its thread. A message with a reply
before it is a correction when a cue of one of the classes in `CLASSES` matches its words, and its
class is the first class whose cue does. `README.md` beside this file says how each class is
decided and what it misses.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

STORE = Path.home() / ".t3" / "userdata" / "statev2.sqlite"
HOME_TITLE = "home: "


@dataclass(frozen=True)
class Class:
    """A cause of a correction: its key, the words the count prints, and the cues that decide it,
    each a regular expression over the user's words, matched without regard to case."""

    key: str
    label: str
    cues: tuple[str, ...]


CLASSES: tuple[Class, ...] = (
    Class(
        "unchecked",
        "a fact not checked before it was said",
        (
            r"\bis (that|this) (accurate|right|true)\b",
            r"\bare you guessing\b",
            r"\bno guessing\b",
            r"\bwant accurate\b",
            r"\bwasn'?t it\b",
            r"\bbut we did\b",
            r"\bgoing in circles\b",
            r"\balready (done|did|have|fixed|addressed|turned)\b",
            r"\bturned (that|it|this) off\b",
            r"\bturned back (on|off)\b",
            r"\bi th(r)?ought we\b",
            r"\bwe are supposed to\b",
        ),
    ),
    Class(
        "visual",
        "a visual that missed the ask",
        (
            r"\bnot what i asked\b",
            r"\bwrong (report|chart|diagram|picture|image|page)\b",
            r"\bno lines should cross\b",
            r"\btop down\b",
            r"\bopen this in my (browser|broswer)\b",
            r"\bmore screenshots\b",
            r"\bthis confuses me\b",
        ),
    ),
    Class(
        "missing",
        "a rule that is missing",
        (
            r"\bwhat are these\b",
            r"\bwhat report\b",
            r"\bwhere did that rule come from\b",
            r"\bin the future\b",
        ),
    ),
    Class(
        "broken",
        "a skill rule the reply broke",
        (
            r"\$unslop (the|this|that)\b",
            r"\bneeds me explicit",
        ),
    ),
)

QUOTE = re.compile(r"\[Assistant quote\]\((t3-citation://[^)\s]*)\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(t3-context://[^)\s]*\)")


@dataclass(frozen=True)
class Message:
    """A message the user typed in a home thread: its place in the window, when, the thread's
    title, the user's own words, and the reply before it in its thread."""

    n: int
    at: str
    thread: str
    words: str
    reply: str


def words_of(text: str) -> str:
    """The user's own words in a message: the text with each quote of a reply cut down to the
    comment the user wrote on it, and each pasted picture cut out."""

    def comment(found: re.Match[str]) -> str:
        query = urllib.parse.urlsplit(found.group(1)).query
        return " ".join(urllib.parse.parse_qs(query).get("comment", []))

    return IMAGE.sub(" ", QUOTE.sub(comment, text)).strip()


def class_of(words: str) -> Class | None:
    """The class of a correction whose words these are, or None for a message that corrects
    nothing: the first class in `CLASSES` one of whose cues matches."""
    for one in CLASSES:
        if any(re.search(cue, words, re.IGNORECASE) for cue in one.cues):
            return one
    return None


def bound(day: str, end: bool) -> str:
    """A `--since` or `--until` as a UTC time the store's `created_at` compares with: a day is
    the user's local midnight, at its start for `--since` and at the next day's for `--until`,
    and anything else is taken as an ISO time."""
    try:
        start = date.fromisoformat(day)
    except ValueError:
        at = datetime.fromisoformat(day)
    else:
        at = datetime.combine(start + timedelta(days=1 if end else 0), time()).astimezone()
    if at.tzinfo is None:
        at = at.astimezone()
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


QUERY = """
select m.created_at, t.title, json_extract(m.payload_json, '$.text'),
    coalesce((
        select json_extract(r.payload_json, '$.text')
        from orchestration_v2_projection_messages r
        where r.thread_id = m.thread_id and r.role = 'assistant' and r.created_at < m.created_at
        order by r.created_at desc limit 1
    ), '')
from orchestration_v2_projection_messages m
join orchestration_v2_projection_threads t using (thread_id)
where m.role = 'user'
    and coalesce(json_extract(m.payload_json, '$.createdBy'), 'user') = 'user'
    and substr(t.title, 1, length(:title)) = :title
    and m.created_at >= :since and m.created_at < :until
order by m.created_at, m.message_id
"""


def messages(store: Path, since: str, until: str) -> list[Message]:
    """The user's messages in home threads in the window, oldest first, read only."""
    with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as db:
        rows = db.execute(QUERY, {"title": HOME_TITLE, "since": since, "until": until}).fetchall()
    return [
        Message(n, at, title.removeprefix(HOME_TITLE), words_of(text or ""), reply)
        for n, (at, title, text, reply) in enumerate(rows, 1)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=STORE, help=f"default {STORE}")
    parser.add_argument("--since", required=True, help="a local day YYYY-MM-DD, or an ISO time")
    parser.add_argument("--until", required=True, help="a local day, counted whole, or an ISO time")
    parser.add_argument("--list", action="store_true", help="print each correction as well")
    args = parser.parse_args(argv)
    if not args.store.is_file():
        print(f"no store at {args.store}", file=sys.stderr)
        return 2
    try:
        since, until = bound(args.since, end=False), bound(args.until, end=True)
    except ValueError as e:
        print(f"--since and --until take a day YYYY-MM-DD or an ISO time: {e}", file=sys.stderr)
        return 2
    every = messages(args.store, since, until)
    found = [(one, kind) for one in every if one.reply and (kind := class_of(one.words))]
    print(
        f"{len(found)} of {len(every)} messages in home threads, {since} to {until},"
        " correct the reply before them"
    )
    for kind in CLASSES:
        print(f"{sum(1 for _, k in found if k is kind):>4}  {kind.key:<10} {kind.label}")
    if args.list:
        for one, kind in found:
            print(f"n{one.n}\t{one.at[:16]}\t{kind.key}\t{one.thread}\t{one.words[:100]!r}")
            print(f"\tto {one.reply[:100]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
