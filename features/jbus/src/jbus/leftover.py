"""A task that ended with something left goes to its home: jbus tells the home once, and the
home closes it.

A leftover is a row whose thread ended or whose pull request merged, and whose last Result
has a `Left:` line that is not `none`. No thread is at work on it (`ended`). A row whose
thread ended or hung with no Result at all is a leftover too, once its crew had its
carry-ons (`watch.unwritten`). Its `left` text is that reason, and its message says to carry
the thread on, to remove the row, or to end it with a Result.

jbus closes no leftover and starts no thread for one. `tell` sends the row's home one queued
message. The message has the slug, its pull request and whether it merged, the whole `Left:`
line, each question the slug asked with its answer or a note that it is open, and the two
ways to end it. The retry key is
`leftover|<slug>|<the first 12 of a hash of the Left: text>|<the home's thread>`, so jbus
tells a home once for a row and a `Left:` text, and again when the text changes. When a home
takes over from the one jbus told, jbus tells the new home too, and its 30 minutes start
then.

The home is the one the brief's `Home:` line names. Its thread is the first word of that
home's `home-id`, which jbus reads on each pass. That rule is `jbriefs.home`, which a
crewmate and `jmerge` also use.

`leftover.json` in a project's state directory is the record, a `Record` for each slug:

- `left` is the `Left:` text the record is for. A Result with another text starts a new
  record.
- `thread` and `told` are the home's thread the message went to and when it went, or empty
  until jbus sends it.
- `why` is why the row is the user's at once, or empty. The reasons are that its home has no
  thread, that T3 Code does not list that thread as not settled, or that the message did not
  go.
- `stalled` is when jbus reported the row to the user as a stall, or empty. A new `Left:`
  text keeps it, so jbus reports a row once.
- `busy` is true when a thread was at work on the row in the last pass, so the row waits on
  that thread.

`his` says whose a leftover is: the home's while `his` returns nothing, and the user's with
the reason `his` gives. A leftover is the user's when it has a `why`, while no home was
told, or once `CLOSE_MINUTES` have passed since jbus told the home. jbus reports that last
case once, as a `stall` event (`stall.unclosed`). The list of what waits on the user
(`waiting.left`) and the view read the same record. The pass that writes the list judges
every row on it, so each record the list reads has `told` or `why`.

A pass that could not list the threads that are not settled judges no home's thread. A row whose
home was told stays as it was, and any other row is the user's until a pass can list them.

This module sets the timers of what blocks (`waiting.cadence`) beside `CLOSE_MINUTES`. jbus
reminds the user once of an item that still blocks `REMIND_MINUTES` after it opened, and
posts the whole list of what blocks every `REFRESH_MINUTES`.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jbriefs.home import home_of, thread_of
from jbus import mirror, questions, queue, read_json, verbs, write_json
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import LIVE, World, brief_of, last_result, named

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
UNWRITTEN = (
    "jbus: {slug} ended with nothing written, and it is this home's to close. {user} is not "
    "asked: it waits on this home.\n\n"
    "It is left because {why}. {pull}.\n"
    "{asked}\n\n"
    "Read `tasks/{slug}.md` and its thread {thread}, then end it one of three ways:\n"
    "- the work is wanted and the thread can go on: send it a message to carry on "
    "(`t3_thread_send`), stopping its turn first if it hung;\n"
    "- the work is wanted and the thread cannot go on: remove the row "
    '(`jbus queue remove {slug} --by <who> --at "<time>"`) and queue it again for a new '
    "thread;\n"
    "- nothing more is wanted, or it is already done: append a section "
    "`## Result, follow-up (<date>, <the reason>)` to `tasks/{slug}.md` with three lines: "
    "`Status: done`, `Branch: <its branch>   Pull request: none` and `Left: none`. Only "
    "those three end it.\n\n"
    "Send {user} nothing about it. A question only {user} can answer is a gate: take the "
    "default and pipe it to `jbus gate {slug}`. jbus says this row to {user} once if it is "
    "still open {minutes} min from now."
)


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
    """Return the record of each slug, or none where the file is not one this module wrote."""
    kept = read_json(path(state), {})
    try:
        return {slug: Record(**one) for slug, one in kept.items()}
    except (AttributeError, TypeError):
        return {}


def _write(state: Path, records: dict[str, Record]) -> None:
    write_json(path(state), {slug: asdict(one) for slug, one in sorted(records.items())})


def late(record: Record, now: datetime) -> bool:
    """Return whether jbus told the home `CLOSE_MINUTES` ago or more."""
    if not record.told:
        return False
    return (now - datetime.fromisoformat(record.told)).total_seconds() >= CLOSE_MINUTES * 60


def his(record: Record, now: datetime) -> str:
    """Return why a leftover is the user's, or nothing while it is its home's."""
    if record.why:
        return record.why
    if late(record, now):
        return LATE.format(thread=record.thread, minutes=CLOSE_MINUTES)
    return ""


def ended(run: Pass, world: World, rows: list[queue.Row]) -> list[tuple[str, str]]:
    """Return the rows whose Result leaves something and that no thread is at work on, each
    with its `why`.

    jbus counts a merged row's thread as at work by the thread's status alone. It settles the
    thread of a merge before it tells that thread, and a settled thread that took the message
    up is at work.
    """
    found = []
    for row in sorted(rows, key=queue.order):
        slug, why = row["slug"], row.get("why")
        busy = slug in run.told or (world.thread(slug) or {}).get("status") in LIVE
        if row.get("status") == "left" or (row.get("status") == "merged" and why and not busy):
            found.append((slug, why or ""))
    return found


def note(brief: str) -> str:
    """Return the whole `Left:` line of a brief's last Result, or nothing where it leaves
    nothing."""
    text = mirror.field(mirror.last_result(brief), "Left")
    return "" if text == "none" else text


def _pull(world: World, slug: str, brief: str) -> str:
    """Return the slug's pull request and whether it merged, as the message says it."""
    url, number = named(mirror.last_result(brief))
    merged = world.merged.get(slug)
    if merged:
        at = " ".join(filter(None, [f"#{merged['number']}", merged.get("url") or url]))
        return f"Its pull request {at} is merged"
    if number:
        return f"Its pull request #{number} {url} is not merged"
    return "It ended with no pull request"


def _asked(run: Pass, slug: str) -> str:
    """List each question the slug asked, with its answer or a note that it is open."""
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


def message(run: Pass, world: World, slug: str, brief: str, why: str = "") -> str:
    """Write the one message a home gets about a leftover. `why` is the row's `left` text, which a
    row with no Result has in place of a `Left:` line."""
    if not mirror.last_result(brief):
        return UNWRITTEN.format(
            slug=slug,
            user=run.user.user,
            why=why,
            thread=(world.thread(slug) or {}).get("threadId", "not listed"),
            pull=_pull(world, slug, brief),
            asked=_asked(run, slug),
            minutes=CLOSE_MINUTES,
        )
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
    """Return a leftover's record after this pass, which says whether its home or the user
    has it, and send the message once."""
    thread = thread_of(home_of(run.home, brief))
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
    text = message(run, world, slug, brief, record.left)
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
    `Left:` text, even through a pass in which a thread is at work on it. It loses the record
    when the Result leaves nothing or the row is gone.
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
        text = note(brief) or (row.get("why", "") if ended_now and not last_result(brief) else "")
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
    """Record that jbus reported a row to the user as a stall."""
    records = read(state)
    if slug in records:
        stamp = at.astimezone(UTC).isoformat(timespec="seconds")
        _write(state, records | {slug: replace(records[slug], stalled=stamp)})


STEPS = (
    verbs.Step(
        "after-derive",
        10,
        "leftover.tell",
        lambda half: tell(half.run, half.client, half.seen.world, half.table, half.out),
        ("client", "world", "rows"),
    ),
)
