"""A task that ended with something left goes to its home: jbus tells the home once, and the
home closes it.

A leftover is a row whose thread ended or whose pull request merged, and whose last Result has a
`Left:` line that is not `none`, as its status says (`ended`). No thread is at work on it. A row
whose review before its pull request is due or running, or whose crew is opening the pull request
that review was for (`reviewing`), is never `left`: the pass judges its pull request `opening`
(`work.Pull.OPENING`) and its row `running`. A row whose thread ended or hung with no Result at all
is a leftover too, once its crew has had its carry-ons (`watch.unwritten`). For such a row, the
`left` text states that reason, and the message says to carry the thread on, to remove the row, or
to end it with a Result.

A row whose branch has commits of its own (`watch.own`) is told neither way to a new brief:
`RESUMES` says that jbus launches it again on its slug, branch and worktree once a cause it waits
on clears (`jbus.pausedon.cleared`), names the rows its Result waits on, and says how the home
makes a wait jbus cannot read into one it can, or closes the row where nothing more is wanted. A
row with no commits on its branch may still take a new brief, as `MESSAGE` and `UNWRITTEN` say.

jbus closes no leftover and starts no thread for one. `tell` writes each leftover's record, and
the record is an item of the one list that wakes a home (`jbus.wakes`), keyed `left:<slug>`: its
home is told of it once while it stays open. The record keeps the text the home is told: the
slug, its pull request and whether it merged, the whole `Left:` line, each question the slug
asked with its answer or a note that it is open, and the three ways to end it. A new `Left:` text
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
home. A home that leaves it open is not told of it a second time, and no other home is told
of it. The list of what waits on the user
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
from jbriefs.home import home_of, thread_of
from jbus import mirror, pausedon, prereview, questions, queue, read_json, review, verbs, write_json
from jbus.passes import Pass
from jbus.told import FILE as TOLD
from jbus.told import told_to
from jbus.watch import World, at_work, brief_of, last_result, named, own

KIND = "leftover"
NAME = "leftover.json"
CLOSE_MINUTES = 30
REMIND_MINUTES = 15
REFRESH_MINUTES = 60
OPENING_MINUTES = 5
NO_HOME = "it has no home: no home-id names a thread for the home of its brief"
UNLISTED = "its home's thread {thread} is not one T3 Code lists as not settled"
UNSEEN = "its home is not told yet: T3 Code did not list the threads that are out"
MESSAGE = (
    "jbus: {slug} ended with something left, and it is this home's to close. {user} is not "
    "asked: it waits on this home.\n\n"
    "{pull}.\n"
    "Left: {left}\n"
    "{asked}\n\n"
    "Read the last Result of `tasks/{slug}.md` and the answers above, then end it one of three "
    "ways:\n"
    "- something is still to do: write a brief for what is left, with a line `Follows: {slug}` "
    "in its head, and queue it as a follow-up, then close this one as below, with "
    "`Outcome: carried by <the follow-up's slug>`;\n"
    "- the rest is already another row's: add the line `Follows: {slug}` to the head of that "
    "row's brief and queue it again, then close this one as below, with "
    "`Outcome: carried by <that row's slug>`;\n"
    "- nothing more is wanted, or the rest is somebody's outside the queue: close it as below, "
    "with `Outcome: dropped, <why>`, or `Outcome: nothing to change, <why>` where the task found "
    "nothing to do.\n\n"
    "To close it, "
    "append a section "
    "`## Result, follow-up (<date>, <the reason>)` to `tasks/{slug}.md` with four lines: "
    "`Status: done`, `Branch: <its branch>   Pull request: none`, `Outcome: <how it ended>` and "
    "`Left: none`. Only those four end it, and the outcome is one of three: "
    "`carried by <slug>`, `nothing to change, <why>` or `dropped, <why>`.\n\n"
    "Send {user} nothing about it. A question only {user} can answer is a gate: take the "
    "default and pipe it to `jbus gate {slug}`."
)
UNWRITTEN = (
    "jbus: {slug} ended with nothing written, and it is this home's to close. {user} is not "
    "asked: it waits on this home.\n\n"
    "It is left because {why}. {pull}.\n"
    "{asked}\n\n"
    "Read `tasks/{slug}.md` and its thread {thread}, then end it one of four ways:\n"
    "- the work is wanted and the thread can go on: send it a message to carry on "
    "(`t3_thread_send`), stopping its turn first if it hung;\n"
    "- the work is wanted and the thread cannot go on: a launched row is {user}'s alone to "
    "remove, so ask for its removal with a gate (`jbus gate {slug}`) whose default is that the "
    "row stays, and once it is removed, queue the work again for a new thread, with a line "
    "`Follows: {slug}` in its brief's head;\n"
    "- the work is already another row's: add the line `Follows: {slug}` to the head of that "
    "row's brief and queue it again, then close this one as below, with "
    "`Outcome: carried by <that row's slug>`;\n"
    "- nothing more is wanted, or it is already done: close it as below, with "
    "`Outcome: dropped, <why>` where it is not wanted, or `Outcome: nothing to change, <why>` "
    "where it is already done.\n\n"
    "To close it, "
    "append a section "
    "`## Result, follow-up (<date>, <the reason>)` to `tasks/{slug}.md` with four lines: "
    "`Status: done`, `Branch: <its branch>   Pull request: none`, `Outcome: <how it ended>` and "
    "`Left: none`. Only those four end it, and the outcome is one of three: "
    "`carried by <slug>`, `nothing to change, <why>` or `dropped, <why>`.\n\n"
    "Send {user} nothing about it. A question only {user} can answer is a gate: take the "
    "default and pipe it to `jbus gate {slug}`."
)

RESUMES = (
    "jbus: {slug} ended with something left on its branch, and it is this home's to see to. "
    "{user} is not asked: it waits on this home.\n\n"
    "{pull}.\n"
    "Left: {left}\n"
    "{asked}\n\n"
    "Its branch {slug} has commits, so it is not carried on under a new brief: jbus launches it "
    "again on its own slug, branch and worktree, with a `Resume:` line in its brief that names "
    "the cause, once for each cause that clears: {waits}a review with findings written after its "
    "last Result, or a new go for its brief.\n\n"
    "Read the last Result of `tasks/{slug}.md` and the answers above, then do one of three:\n"
    "- it waits on one of those: leave it, and write no new brief for it;\n"
    "- it waits on work that must land first and its Result does not name it: append a "
    "section `## Result, follow-up (<date>, <the reason>)` to `tasks/{slug}.md` with "
    "`Status: paused`, `Waits on: <each row's slug, or #<n> for a pull request>`, "
    "`Branch: {slug}   Pull request: none` and "
    "`Left: <what is left>`; where its `Where:` or `Done when:` is too narrow, widen them in "
    "`tasks/{slug}.md`, queue it again with `jbus queue add`, and its new go launches it;\n"
    "- nothing more is wanted, or the rest is somebody's outside the queue: close it, appending "
    "a section `## Result, follow-up (<date>, <the reason>)` to `tasks/{slug}.md` with four "
    "lines: `Status: done`, `Branch: {slug}   Pull request: none`, `Outcome: <how it ended>` "
    "and `Left: none`, the outcome `dropped, <why>` or `nothing to change, <why>`.\n\n"
    "Send {user} nothing about it. A question only {user} can answer is a gate: take the "
    "default and pipe it to `jbus gate {slug}`."
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


def his(record: Record, now: datetime) -> str:
    """Return why a leftover is the user's, or nothing while its home has it."""
    return record.why


def reviewing(run: Pass, world: World, slug: str) -> bool:
    """Say whether a row's crew is still on its way to the pull request it opens after its review.
    It waits on that review (`review.awaited`): jbus has its reviewers to launch or to hear from,
    then tells the crew (`jbus.prereview`). Or the review is written and the crew is opening its
    pull request (`opening`). Such a row is still in flight, whatever its Result leaves: the pass
    judges its pull request `opening` (`work.Pull.OPENING`), so its status is never `left`."""
    brief = brief_of(run, slug)
    result = mirror.last_result(brief)
    return review.awaited(brief, result) or opening(run, world, slug, brief, result)


def opening(run: Pass, world: World, slug: str, brief: str, result: str) -> bool:
    """Say whether a crew whose Result opens its pull request after its review, and whose review
    has run, is opening that pull request now: its thread is at work or was told this pass, or
    jbus sent it `prereviewed` less than `OPENING_MINUTES` ago, the time T3 Code takes to start
    its turn and the crew to open it. A crew that ended past that with no pull request has left
    its row. A row whose pull request is open is `pr`, not `left`, and is never asked."""
    if not review.before_pull(result) or not review.ran(brief):
        return False
    thread = world.thread(slug)
    if thread and (
        at_work([thread], settled_too=True)
        or jsettings.thread_id(thread.get("threadId", "")) in run.told
    ):
        return True
    at = prereview.told_at(run.state, slug)
    return at is not None and (run.now - at).total_seconds() < OPENING_MINUTES * 60


def ended(run: Pass, world: World, rows: list[queue.Row]) -> list[tuple[str, str]]:
    """Return the rows whose Result leaves something and that no thread is at work on, each
    with its `why`, as the status says: a row `left`, or `merged` with a `why`. A row whose crew
    is on its way to its pull request (`reviewing`) is never `left`.

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
    row with no Result has in place of a `Left:` line. A row whose branch has commits of its own
    gets `RESUMES`."""
    if slug not in world.merged and own(run, slug):
        slugs = {row["slug"] for row in queue.load(run.state)}
        named = pausedon.waits_on(run, world, slug, slugs)
        waits = f"`{'`, `'.join(named)}` landing, what its `Waits on:` names, " if named else ""
        return RESUMES.format(
            slug=slug,
            user=run.user.user,
            pull=_pull(world, slug, brief),
            left=note(brief) or why,
            asked=_asked(run, slug),
            waits=waits,
        )
    if not mirror.last_result(brief):
        return UNWRITTEN.format(
            slug=slug,
            user=run.user.user,
            why=why,
            thread=(world.thread(slug) or {}).get("threadId", "not listed"),
            pull=_pull(world, slug, brief),
            asked=_asked(run, slug),
        )
    return MESSAGE.format(
        slug=slug,
        user=run.user.user,
        pull=_pull(world, slug, brief),
        left=note(brief),
        asked=_asked(run, slug),
    )


def key_of(slug: str, left: str) -> str:
    """The key of a leftover's item on the one list: its row and its `Left:` text."""
    return f"left {slug}: {left}"


def _judge(
    run: Pass, world: World, slug: str, brief: str, record: Record, out: set[str] | None
) -> Record:
    """Return a leftover's record after this pass. The record says whether the home or the user
    has the leftover."""
    thread = thread_of(home_of(run.home, brief))
    if not thread:
        return replace(record, why=NO_HOME)
    told = told_to(read_json(run.state / TOLD, {}), thread)
    at = told.get(key_of(slug, record.left), {}).get("at", "")
    if out is None:
        return replace(record, told=at) if at else replace(record, why=UNSEEN)
    if thread not in out:
        return replace(record, why=UNLISTED.format(thread=thread))
    text = message(run, world, slug, brief, record.left)
    return replace(record, thread=thread, told=at, why="", text=text)


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
        record = before if before is not None and before.left == text else Record(text)
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
