"""This module judges the state of each row of the queue once, in the second half of a pass
(`judged`). Three steps then read that state. `derive` rewrites the table's derived columns,
`unplaced` tells the home of each open pull request that is on no step, and `keep_work` writes
`work.json`.

Each writer of a row's inputs restates that row's line of `work.json` as it writes
(`restated.queued`, `restated.pulled`), so the pass is no longer how a change reaches the view.
The pass still judges every row from all it saw, and `keep_work` logs each row's line it finds
otherwise in the file as a quiet `work-drift` event, which tells nobody. A thread's facet is such
a line while `jbus follow` follows T3 Code's events (`restated.following`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import jsettings
from jbriefs.home import home_of, thread_of
from jbus import (
    blockers,
    cancelled,
    dispatch,
    leftover,
    locked,
    merge,
    mirror,
    queue,
    restated,
    review,
    stall,
    threads,
    verbs,
    watch,
    work,
)

if TYPE_CHECKING:
    from jbus.passes import Pass
    from jbus.poll import Half

DRIFT = "work-drift"
EVENTS = {"work-drift": "quiet"}


def judged(half: Half) -> None:
    """Judge the state of each row of the queue, once (`work.judge`). A row waits on another row
    until that row is merged or ended `done`. `dispatch` uses the same rule to decide what to launch
    (`watch.final`).

    When GitHub is silent and T3 Code answers, the steps that list the threads out did not run,
    since those steps need a world and the pass has none. This function then lists the threads out
    the way those steps do, and `stall.hung` reads the list. So the pass still judges whether each
    thread is alive, and still tells of a hang.
    """
    run, world, rows, client = half.run, half.seen.world, half.rows, half.client
    if rows is None:
        return
    if world is None and half.out is None and half.seen.out is not None and client is not None:
        half.out = threads.out(run, client, stall.watched(run))
        stall.hung(run, half.out)
    said = dict(watch.waits(half.shown).said) if world else {}
    if half.shown.failed:
        for row in rows:
            number = str(row.get("pr", "")).removeprefix("#")
            if row.get("status") == "pr" and number and number not in said:
                said[number] = row.get("why", "")
    last = work.last(run.state)
    seen = watch.Seen(half.out, half.gone, said, watch.final(run, world, rows), half.answered())
    half.states = watch.Judging(run, world, seen, last)


def derive(half: Half) -> None:
    """Rewrite the table's derived columns (`queue.derive`), and say whether the table changed."""
    run, world, states = half.run, half.seen.world, half.states
    if world is None or states is None:
        return
    waits = watch.waits(half.shown)
    unread = watch.unread(run, half.read)

    def facts(row: queue.Row) -> queue.Row:
        slug = row["slug"]
        launched = dispatch.launched(run, slug, queue.role(row))
        found = watch.status(run, world, slug, states.of(row, launched), launched)
        said = cancelled.why(run, slug) if found["status"] == "pr" else ""
        return {**found, "why": said or watch.why(run, row, found, waits, unread)}

    at = jsettings.stamp(run.now)
    half.table, half.changed = queue.derive(run.state, facts, run.user.stamp(run.now), at)
    if half.changed:
        line = f"queue {run.project.name}: the table changed"
        run.box.send("", "queue", line, queue.changes(half.changed))


def unplaced(half: Half) -> None:
    """Tell the home of each row whose pull request is open and on no step (`merge.unplaced`).
    `unplaced` uses what `jmerge` said of that pull request in this pass."""
    run, world, states, client = half.run, half.seen.world, half.states, half.client
    if states is None or client is None:
        return
    for row in half.table or []:
        slug = row["slug"]
        pull = (world.open if world else {}).get(slug)
        if pull is None:
            continue
        number = str(pull.get("number", ""))
        said = states.seen.said.get(number, "")
        thread = thread_of(home_of(run.home, watch.brief_of(run, slug)))
        merge.unplaced(run, client, slug, number, said, thread)


def keep_work(half: Half) -> None:
    """Write `work.json`. The file holds the state of every row, and of every thread out that
    belongs to no row, and says who holds each one (`work.holder`). When the pass has no list of the
    threads out, the file keeps the threads of the last pass, which this pass has not confirmed."""
    run, rows, states = half.run, half.table or [], half.states
    if states is None:
        return
    held, gated = leftover.read(run.state), blockers.holding(run)
    listed = []
    for row in rows:
        slug = row["slug"]
        state = states.of(row, dispatch.launched(run, slug, queue.role(row)))
        record = held.get(slug)
        role = "scout" if queue.role(row) == queue.SCOUT else ""
        scout = {"scout": str(work.scouting(state))} if role else {}
        why = str(row.get("why", ""))
        unhomed = leftover.his(record, run.now) if record else ""
        line = work.entry(
            state,
            work.holder(state, role, why, _closer(run, slug, record, gated), unhomed),
            key=slug,
            kind="row",
            slug=slug,
            thread=row.get("thread", ""),
            pr=row.get("pr", ""),
            why=why,
            **scout,
        )
        listed.append(line)
    mine = {(queue.role(row), row["slug"]) for row in rows}
    listed += watch.judged(run, half.out, mine, half.answered())
    at = jsettings.stamp(run.now)
    with locked(run.state, work.LOCK):
        was = work.read(run.state)
        before = was["work"] if was else []
        written = _since(run, _pulled(run, listed, before, half.said.at))
        work.write(run.state, at, half.answered(), written)
    following = restated.following(run.config.state_dir)
    for key, what in restated.drift(before, written, following) if was else []:
        run.box.send(key, DRIFT, f"{DRIFT} {key}: {what}")


def _closer(
    run: Pass, slug: str, record: leftover.Record | None, gated: frozenset[str]
) -> work.Closer:
    """Return who closes a row where its facts alone do not say (`work.Closer`)."""
    if slug in gated:
        return work.Closer.USER
    brief = watch.brief_of(run, slug)
    if review.awaited(brief, mirror.last_result(brief)):
        return work.Closer.REVIEW
    if record and record.busy:
        return work.Closer.BUSY
    return work.Closer.HOME


def _pulled(
    run: Pass, listed: list[dict[str, Any]], before: list[Any], ran: str
) -> list[dict[str, Any]]:
    """Return the pass's lines, each row's with the `Pull` facet that a run of `jmerge` which
    ended after the pass's own run (`ran`) restated in the file (`restated.kept`), such as a merge
    tick's. A tick that held the run lock while the pass's run found it busy ends after it too.
    Each line keeps the `Thread` facet that `jbus follow` restated from a T3 Code event after the
    pass began (`restated.heard`)."""
    was = {one.get("key"): one for one in before if isinstance(one, dict)}
    ended, began = ran or restated.moment(run.now), restated.moment(run.now)
    return [
        restated.heard(
            restated.kept(one, was.get(one["key"]), ended) if one.get("kind") == "row" else one,
            was.get(one["key"]),
            began,
        )
        for one in listed
    ]


def _since(run: Pass, listed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the pass's lines with each row's go as the queue has it now. A write of the queue
    between the pass's read of the table and this write changed a row's go or took the row out,
    and that write's own restate already says so (`queue._changing`): the pass keeps it, and does
    not write the row as it was."""
    try:
        rows = queue.load(run.state)
    except queue.Unparsable:
        return listed
    now = {row["slug"]: row for row in rows}
    done = queue.final(rows)
    kept = []
    for one in listed:
        if one.get("kind") == "row":
            row = now.get(one["slug"])
            if row is None:
                continue
            one = work.restate(one, row=queue.standing(run.state, row, done))
        kept.append(one)
    return kept


STEPS = (
    verbs.Step("derive", 10, "states.judged", judged, ("sight",)),
    verbs.Step("derive", 20, "states.derive", derive, ("client", "world", "rows")),
    verbs.Step("after-derive", 30, "states.unplaced", unplaced, ("client", "world", "rows")),
    verbs.Step("after-derive", 40, "states.keep_work", keep_work, ("rows",)),
)
