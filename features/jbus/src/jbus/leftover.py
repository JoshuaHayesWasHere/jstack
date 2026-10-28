"""A task that ended with something left goes to its home: jbus tells the home once, and the
home closes it.

A leftover is a row whose thread ended or whose pull request merged, and whose last Result
has a `Left:` line that is not `none`. No thread is at work on it (`ended`). A row whose
thread ended or hung with no Result at all is a leftover too, once its crew has had its
carry-ons (`watch.unwritten`). For such a row, the `left` text states that reason, and the
message says to carry the thread on, to remove the row, or to end it with a Result.

jbus closes no leftover and starts no thread for one. `tell` writes each leftover's record, and
the record is an item of the one list that wakes a home (`jbus.wakes`), keyed `left:<slug>`: its
home is told of it once while it stays open. The record keeps the text the home is told: the
slug, its pull request and whether it merged, the whole `Left:` line, each question the slug
asked with its answer or a note that it is open, and the two ways to end it. A new `Left:` text
is a new record. When a home takes over from the one jbus told, the new home is told too, and its
30 minutes start then.

The home is the one the brief's `Home:` line names. Its thread is the first word of that
home's `home-id`, which jbus reads on each pass. That rule is `jbriefs.home`, which a
crewmate and `jmerge` also use.

`leftover.json` in a project's state directory is the record, a `Record` for each slug:

- `left` is the `Left:` text the record is for. A Result with another text starts a new
  record.
- `thread` and `told` are the home's thread and when the one list told it (`wakes.json`), or
  empty until it did.
- `why` is why the row is the user's at once, or empty. The reasons are that its home has no
  thread, or that T3 Code lists that thread as settled or does not list it.
- `text` is what its home is told.
- `busy` is true when a thread was at work on the row in the last pass, so the row waits on
  that thread.

`his` says whose a leftover is: a home's while `his` returns nothing, and the user's with
the reason `his` gives. A leftover is the user's when it has a `why`, while jbus has told no
home. Once `CLOSE_MINUTES` have passed since jbus told the home, it is an item of the root home's
too, keyed `left-late <slug>: <left>` (`raised`): it reaches the user only where no root home is
listed to tell (`NO_ROOT`). The list of what waits on the user
(`waiting.left`) and the view read the same record. The pass that writes the list judges
every row on it, so each record the list reads has `told` or `why`.

When a pass could not list the threads that are not settled, it judges no home's thread. A
row whose home jbus told stays as it was. Any other row is the user's until a pass can list
those threads again.

This module sets the timers of what blocks (`waiting.cadence`) beside `CLOSE_MINUTES`. jbus
reminds the user once of an item that still blocks `REMIND_MINUTES` after it opened, and
posts the whole list of what blocks every `REFRESH_MINUTES`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import below
from jbriefs.home import thread_of
from jbus import mirror, questions, queue, read_json, verbs, write_json
from jbus.passes import Pass
from jbus.told import FILE as TOLD
from jbus.told import told_to
from jbus.watch import World, at_work, brief_of, home_thread, last_result, named

KIND = "leftover"
NAME = "leftover.json"
CLOSE_MINUTES = 30
REMIND_MINUTES = 15
REFRESH_MINUTES = 60
NO_HOME = "it has no home: no home-id names a thread for the home of its brief"
UNLISTED = "its home's thread {thread} is not one T3 Code lists as not settled"
UNSEEN = "its home is not told yet: T3 Code did not list the threads that are out"
LATE = "its home, thread {thread}, has not closed it {minutes} min after jbus told it"
NO_ROOT = LATE + ", and no root home is listed to tell"
RAISED = (
    "jbus: {slug} ended with something left, and {late}. It is the root home's now: {user} is "
    "not asked.\n\n"
    "Left: {left}\n\n"
    "Close it as jbus's message to its home says, from the last Result of `tasks/{slug}.md`: a "
    "follow-up brief for what is left, or a `## Result, follow-up` section that ends `Left: "
    "none`. Or tell its home to. A question only {user} can answer is a gate: take the default "
    "and pipe it to `jbus gate {slug}`. Send {user} nothing about it."
)
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
    "default and pipe it to `jbus gate {slug}`. jbus says this row to the root home once if it "
    "is still open {minutes} min from now."
)
UNWRITTEN = (
    "jbus: {slug} ended with nothing written, and it is this home's to close. {user} is not "
    "asked: it waits on this home.\n\n"
    "It is left because {why}. {pull}.\n"
    "{asked}\n\n"
    "Read `tasks/{slug}.md` and its thread {thread}, then end it one of three ways:\n"
    "- the work is wanted and the thread can go on: send it a message to carry on "
    "(`t3_thread_send`), stopping its turn first if it hung;\n"
    "- the work is wanted and the thread cannot go on: a launched row is {user}'s alone to "
    "remove, so ask for its removal with a gate (`jbus gate {slug}`) whose default is that the "
    "row stays, and once it is removed, queue the work again for a new thread;\n"
    "- nothing more is wanted, or it is already done: append a section "
    "`## Result, follow-up (<date>, <the reason>)` to `tasks/{slug}.md` with three lines: "
    "`Status: done`, `Branch: <its branch>   Pull request: none` and `Left: none`. Only "
    "those three end it.\n\n"
    "Send {user} nothing about it. A question only {user} can answer is a gate: take the "
    "default and pipe it to `jbus gate {slug}`. jbus says this row to the root home once if it "
    "is still open {minutes} min from now."
)


@dataclass(frozen=True)
class Record:
    left: str
    thread: str = ""
    told: str = ""
    why: str = ""
    busy: bool = False
    text: str = ""


def _known(one: dict[str, Any]) -> dict[str, Any]:
    """A record's fields this `Record` has, as one written before `stalled` went still has it."""
    return {key: value for key, value in one.items() if key in Record.__dataclass_fields__}


def path(state: Path) -> Path:
    return state / NAME


def read(state: Path) -> dict[str, Record]:
    """Return the record of each slug. Return no records when this module did not write
    the file."""
    kept = read_json(path(state), {})
    try:
        return {slug: Record(**_known(one)) for slug, one in kept.items()}
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
    """Return why a leftover is the user's, or nothing while a home has it: its own, or the
    root home once its own has not closed it in time."""
    return record.why


def ended(run: Pass, world: World, rows: list[queue.Row]) -> list[tuple[str, str]]:
    """Return the rows whose Result leaves something and that no thread is at work on, each
    with its `why`.

    jbus counts a merged row's thread as at work by the thread's status alone. jbus settles
    the thread of a merge before it tells that thread, and a settled thread that picked the
    message up is at work.
    """
    found = []
    for row in sorted(rows, key=queue.order):
        slug, why = row["slug"], row.get("why")
        thread = world.thread(slug)
        told = bool(thread) and jsettings.thread_id(thread.get("threadId", "")) in run.told
        busy = told or at_work([thread] if thread else [], settled_too=True)
        if row.get("status") == "left" or (row.get("status") == "merged" and why and not busy):
            found.append((slug, why or ""))
    return found


def note(brief: str) -> str:
    """Return the whole `Left:` line of a brief's last Result, or nothing when that
    Result leaves nothing."""
    text = below.line(mirror.last_result(brief), "Left:")
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


def key_of(slug: str, left: str, kind: str = "left") -> str:
    """The key of a leftover's item on the one list: its row and its `Left:` text."""
    return f"{kind} {slug}: {left}"


def raised(run: Pass, slug: str, record: Record) -> str:
    """What the root home is told of a leftover its own home did not close in time."""
    late_now = LATE.format(thread=record.thread, minutes=CLOSE_MINUTES)
    return RAISED.format(slug=slug, late=late_now, user=run.user.user, left=record.left)


def _judge(
    run: Pass, world: World, slug: str, brief: str, record: Record, out: set[str] | None
) -> Record:
    """Return a leftover's record after this pass. The record says whether the home or the user
    has the leftover."""
    thread = home_thread(run, brief)
    if not thread:
        return replace(record, why=NO_HOME)
    told = told_to(read_json(run.state / TOLD, {}), thread)
    at = told.get(key_of(slug, record.left), {}).get("at", "")
    if out is None:
        return replace(record, told=at) if at else replace(record, why=UNSEEN)
    if thread not in out:
        return replace(record, why=UNLISTED.format(thread=thread))
    text = message(run, world, slug, brief, record.left)
    record = replace(record, thread=thread, told=at, why="", text=text)
    if not late(record, run.now):
        return record
    root = thread_of(run.home)
    if not root or root not in out:
        return replace(record, why=NO_ROOT.format(thread=thread, minutes=CLOSE_MINUTES))
    return record


def tell(
    run: Pass,
    world: World,
    rows: list[queue.Row],
    out: list[dict[str, Any]] | None,
) -> None:
    """Rewrite `leftover.json`, the record of each leftover that the one list tells its home of.

    `out` is what `threads.out` returned: the threads that are not settled, or None where T3
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
        record = before if same else Record(text)
        if slug in open_now:
            record = _judge(run, world, slug, brief, record, ids)
        kept[slug] = replace(record, busy=slug not in open_now)
    if kept != was:
        _write(run.state, kept)


STEPS = (
    verbs.Step(
        "after-derive",
        10,
        "leftover.tell",
        lambda half: tell(half.run, half.seen.world, half.table, half.out),
        ("world", "rows"),
    ),
)
