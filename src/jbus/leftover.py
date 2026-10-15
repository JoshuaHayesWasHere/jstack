"""A task that ended with something left: its home is told, once, and has it to close.

A leftover is a row whose thread ended, or whose pull request merged, with a last Result
whose `Left:` line is not `none`, and that no thread is at work on (`ended`). jbus closes
none and starts no thread for one. It sends the row's home one queued message (`tell`): the
slug, its pull request and whether it merged, the `Left:` line whole, each question the
slug asked with its answer or that it is open, and the two ways to end it. The retry key is
`leftover|<slug>|<the first 12 of a hash of the Left: text>|<the home's thread>`, so a home
is told once for a row and a `Left:` text, and again when the text changes. A home that
took over from the one that was told is told too, and its 30 minutes start then.

The home is the one the brief's `Home:` line names (`home_of`), as it is for a crewmate and
for `jmerge`: a scope by its name, by the id in its `home-id` or by the `Was home:` line of
its handoff, and the root for a brief with no such line or one that names no scope. Its
thread is the first word of that home's `home-id`, read on each pass.

`leftover.json` in a project's state directory is the record, a `Record` for each slug:

- `left`: the `Left:` text the record is of. A Result with another text is a new record;
- `thread` and `told`: the home's thread the message went to, and when, or nothing while
  it has not gone;
- `why`: why the row is the user's at once, or nothing: its home has no thread, T3 Code
  does not list that thread as not settled, or the message did not go;
- `stalled`: when the row was said to the user as a stall, or nothing. It is kept through a
  new `Left:` text, so a row is said once;
- `busy`: a thread was at work on the row in the last pass, so it waits on that thread.

Whose a leftover is, is `his`: the home's while it says nothing, and the user's with the
reason it gives. It is the user's by `why`, while no home was told, or once `CLOSE_MINUTES`
have passed since the home was told. That last one is said once, as a `stall` event
(`stall.unclosed`). The list of what waits on the user (`waiting.left`) and the view read
the same record. Every row the list has is judged in the pass that writes it, so a record
it reads has `told` or `why`.

A pass that could not list the threads that are out judges no home's thread: a row whose
home was told stays as it was, and any other is the user's until a pass can.

The timers of what blocks (`waiting.cadence`) sit here beside `CLOSE_MINUTES`: an item that
still blocks `REMIND_MINUTES` after it opened is reminded of once, and every
`REFRESH_MINUTES` the list of what blocks is posted whole.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jbus import mirror, questions, queue, read_json, word, write_json
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import LIVE, World, brief_of, named

EVENTS = {"leftover": "quiet"}
KIND = "leftover"
NAME = "leftover.json"
CLOSE_MINUTES = 30
REMIND_MINUTES = 15
REFRESH_MINUTES = 60
NO_HOME = "it has no home: no home-id names a thread for the home of its brief"
UNLISTED = "its home's thread {thread} is not one T3 Code lists as not settled"
REFUSED = "T3 Code refused the message to its home's thread {thread}"
SILENT = "T3 Code did not take the message to its home's thread {thread}"
UNSEEN = "its home is not told yet: T3 Code did not list the threads that are out"
LATE = "its home, thread {thread}, has not closed it {minutes} min after jbus told it"
MESSAGE = (
    "jbus: {slug} ended with something left, and it is this home's to close. {user} is not "
    "asked: it waits on this home.\n\n"
    "{pull}.\n"
    "Left: {left}\n"
    "{asked}\n\n"
    "Read the last Result of `tasks/{slug}.md` and the answers above, then end it one of two "
    "ways:\n"
    "- something is still to do: write a brief for what is left and queue it as a "
    "follow-up, then close this one as below, with the follow-up's slug as the reason;\n"
    "- nothing more is wanted, or the rest is already somebody's: append a section "
    "`## Result, follow-up (<date>, <the reason>)` to `tasks/{slug}.md` with three lines: "
    "`Status: done`, `Branch: <its branch>   Pull request: none` and `Left: none`. Only "
    "those three end it.\n\n"
    "Send {user} nothing about it. A question only {user} can answer is a gate: take the "
    "default and pipe it to `jbus gate {slug}`. jbus says this row to {user} once if it is "
    "still open {minutes} min from now."
)
_HOME = re.compile(r"^Home:[ \t]*(\S+)", re.M)
_WAS = re.compile(r"^Was home:[ \t]*(\S+)", re.M)


@dataclass(frozen=True)
class Record:
    left: str
    thread: str = ""
    told: str = ""
    why: str = ""
    stalled: str = ""
    busy: bool = False


def path(state: Path) -> Path:
    return state / NAME


def read(state: Path) -> dict[str, Record]:
    """The record of each slug, or none where the file is not one this module wrote."""
    kept = read_json(path(state), {})
    try:
        return {slug: Record(**one) for slug, one in kept.items()}
    except (AttributeError, TypeError):
        return {}


def _write(state: Path, records: dict[str, Record]) -> None:
    write_json(path(state), {slug: asdict(one) for slug, one in sorted(records.items())})


def late(record: Record, now: datetime) -> bool:
    """Whether the home was told `CLOSE_MINUTES` ago or more."""
    if not record.told:
        return False
    return (now - datetime.fromisoformat(record.told)).total_seconds() >= CLOSE_MINUTES * 60


def his(record: Record, now: datetime) -> str:
    """Why a leftover is the user's, or nothing while its home has it."""
    if record.why:
        return record.why
    if late(record, now):
        return LATE.format(thread=record.thread, minutes=CLOSE_MINUTES)
    return ""


def ended(run: Pass, world: World, rows: list[queue.Row]) -> list[tuple[str, str]]:
    """The rows whose Result leaves something that no thread is at work on, each with its
    `why`.

    A merged row's thread is at work by its status alone: jbus settles the thread of a
    merge before it tells it, and a settled thread that took the message up is at work.
    """
    found = []
    for row in sorted(rows, key=queue.order):
        slug, why = row["slug"], row.get("why")
        busy = slug in run.told or (world.thread(slug) or {}).get("status") in LIVE
        if row.get("status") == "left" or (row.get("status") == "merged" and why and not busy):
            found.append((slug, why or ""))
    return found


def note(brief: str) -> str:
    """What the last Result of a brief has on its `Left:` line, whole, or nothing where it
    leaves nothing."""
    text = mirror.field(mirror.last_result(brief), "Left")
    return "" if text == "none" else text


def home_of(home: Path, brief: str) -> Path:
    """The directory of the home a brief is, by its `Home:` line.

    A scope is a directory of the home's state whose `home-id` holds an id or whose handoff
    has a `Was home:` line, and the line names it by the directory's name or by either id.
    A brief with no line, or one that names the root's thread or no scope, is the root's.
    """

    def read(file: Path) -> str:
        try:
            return file.read_text(errors="replace")
        except OSError:
            return ""

    def ids(directory: Path) -> tuple[str, str]:
        was = _WAS.search(read(directory / "handoff.md"))
        return (read(directory / "home-id").split()[:1] or [""])[0], was[1] if was else ""

    line = _HOME.search(brief.partition("\n## ")[0])
    name = line[1] if line else ""
    if not name or name in ids(home):
        return home
    for scope in sorted((one for one in home.glob("*") if one.is_dir()), reverse=True):
        now, was = ids(scope)
        if (now or was) and name in (scope.name, now, was):
            return scope
    return home


def _pull(world: World, slug: str, brief: str) -> str:
    """The slug's pull request and whether it merged, as the message says it."""
    url, number = named(mirror.last_result(brief))
    merged = world.merged.get(slug)
    if merged:
        at = " ".join(filter(None, [f"#{merged['number']}", merged.get("url") or url]))
        return f"Its pull request {at} is merged"
    if number:
        return f"Its pull request #{number} {url} is not merged"
    return "It ended with no pull request"


def _asked(run: Pass, slug: str) -> str:
    """Each question the slug asked, with its answer or that it is open."""
    lines = []
    for one in questions.load(run.state):
        if one.slug != slug:
            continue
        if one.answer:
            said = f"answered: {one.answer.line()}"
        else:
            said = f"open, and the default was taken: {one.default}"
        lines.append(f"Question {one.number}: {one.question} It is {said}.")
    return "\n".join(lines) or "It asked no question."


def message(run: Pass, world: World, slug: str, brief: str) -> str:
    """The one message a home gets about a leftover."""
    return MESSAGE.format(
        slug=slug,
        user=run.user.user,
        pull=_pull(world, slug, brief),
        left=note(brief),
        asked=_asked(run, slug),
        minutes=CLOSE_MINUTES,
    )


def _judge(
    run: Pass,
    client: Client,
    world: World,
    slug: str,
    brief: str,
    record: Record,
    out: set[str] | None,
) -> Record:
    """A leftover's record after this pass: whose thread has it, and the message, sent once."""
    thread = word.home(home_of(run.home, brief))
    if not thread:
        return replace(record, why=NO_HOME)
    has = bool(record.told) and record.thread == thread
    if out is None:
        return record if has else replace(record, why=UNSEEN)
    if thread not in out:
        return replace(record, why=UNLISTED.format(thread=thread))
    if has:
        return replace(record, why="")
    digest = hashlib.sha256(record.left.encode()).hexdigest()[:12]
    text = message(run, world, slug, brief)
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": text, "mode": "queue"}
    key = f"{KIND}|{slug}|{digest}|{thread}"
    try:
        client.call("t3_thread_send", {**asked, "clientRequestId": key})
    except T3Refused:
        return replace(record, why=REFUSED.format(thread=thread))
    except T3Error as error:
        run.say(f"wait {slug}: its home could not be told of what it left ({error})")
        return replace(record, why=SILENT.format(thread=thread))
    line = f"{KIND} {slug}: told its home, thread {thread}, of what it left"
    run.find(slug, KIND, line, text, key=f"{digest} {thread}")
    run.say(line)
    at = run.now.astimezone(UTC).isoformat(timespec="seconds")
    return replace(record, thread=thread, told=at, why="")


def tell(
    run: Pass,
    client: Client,
    world: World,
    rows: list[queue.Row],
    out: list[dict[str, Any]] | None,
) -> None:
    """Tell the home of each leftover, once for a row and a `Left:` text, and rewrite
    `leftover.json`.

    `out` is what `threads.out` gave: the threads that are not settled, or None where T3
    Code could not list them. A row keeps its record while its last Result has the same
    `Left:` text, also through a pass in which a thread is at work on it, and loses it when
    the Result leaves nothing or the row is gone.
    """
    was = read(run.state)
    open_now = {slug for slug, _ in ended(run, world, rows)}
    ids = None if out is None else {str(one["id"]) for one in out}
    kept: dict[str, Record] = {}
    for row in sorted(rows, key=queue.order):
        slug = row["slug"]
        ended_now = row.get("status") in ("left", "merged")
        if not (ended_now or slug in was) or slug in run.removed:
            continue
        brief = brief_of(run, slug)
        text = note(brief)
        if not text:
            continue
        before = was.get(slug)
        same = before is not None and before.left == text
        record = before if same else Record(text, stalled=before.stalled if before else "")
        if slug in open_now:
            record = _judge(run, client, world, slug, brief, record, ids)
        kept[slug] = replace(record, busy=slug not in open_now)
    if kept != was:
        _write(run.state, kept)


def said(state: Path, slug: str, at: datetime) -> None:
    """Keep that a row was said to the user as a stall."""
    records = read(state)
    if slug in records:
        stamp = at.astimezone(UTC).isoformat(timespec="seconds")
        _write(state, records | {slug: replace(records[slug], stalled=stamp)})
