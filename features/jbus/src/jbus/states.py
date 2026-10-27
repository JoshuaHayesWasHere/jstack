"""This module judges the state of each row of the queue once, in the second half of a pass
(`judged`). Three steps then read that state. `derive` rewrites the table's derived columns,
`unplaced` tells the home of each open pull request that is on no step, and `keep_work` writes
`work.json`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jsettings
from jbriefs.home import home_of, thread_of
from jbus import (
    cancelled,
    dispatch,
    leftover,
    merge,
    mirror,
    queue,
    stall,
    threads,
    verbs,
    watch,
    work,
)

if TYPE_CHECKING:
    from jbus.cli import Half


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
    waits = watch.waits(half.shown)
    unread = watch.unread(run, half.read)

    def facts(row: queue.Row) -> queue.Row:
        slug = row["slug"]
        launched = dispatch.launched(run, slug)
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
    run, world, states = half.run, half.seen.world, half.states
    for row in half.table or []:
        slug = row["slug"]
        pull = (world.open if world else {}).get(slug)
        if pull is None:
            continue
        number = str(pull.get("number", ""))
        said = states.seen.said.get(number, "")
        thread = thread_of(home_of(run.home, watch.brief_of(run, slug)))
        merge.unplaced(run, half.client, slug, number, said, thread)


def keep_work(half: Half) -> None:
    """Write `work.json`. The file holds the state of every row, and of every thread out that
    belongs to no row, and says who holds each one (`work.holder`). When the pass has no list of the
    threads out, the file keeps the threads of the last pass, which this pass has not confirmed."""
    run, rows, states = half.run, half.table or [], half.states
    held = leftover.read(run.state)
    listed = []
    for row in rows:
        slug = row["slug"]
        state = states.of(row, dispatch.launched(run, slug))
        record = held.get(slug)
        home = bool(record and not record.busy and not leftover.his(record, run.now))
        after = watch.after_merge(mirror.last_result(watch.brief_of(run, slug)))
        line = work.entry(
            state,
            work.holder(state, home=home, after=after),
            key=slug,
            kind="row",
            slug=slug,
            thread=row.get("thread", ""),
            pr=row.get("pr", ""),
        )
        listed.append(line)
    listed += watch.judged(run, half.out, {row["slug"] for row in rows}, half.answered())
    at = jsettings.stamp(run.now)
    work.write(run.state, at, half.answered(), listed)


STEPS = (
    verbs.Step("derive", 10, "states.judged", judged, ("sight",)),
    verbs.Step("derive", 20, "states.derive", derive, ("client", "world", "rows")),
    verbs.Step("after-derive", 30, "states.unplaced", unplaced, ("client", "world", "rows")),
    verbs.Step("after-derive", 40, "states.keep_work", keep_work, ("rows",)),
)
