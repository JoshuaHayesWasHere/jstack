"""The state each row of the queue is in, judged once in a pass's second half (`judged`),
and the steps that read it: the table's derived columns (`derive`), the home told of each
open pull request on no step (`unplaced`), and `work.json` (`keep_work`).
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

from jbus import dispatch, leftover, merge, mirror, queue, stall, threads, verbs, watch, word, work

if TYPE_CHECKING:
    from jbus.cli import Half


def judged(half: Half) -> None:
    """The state of each row of the queue, judged once (`work.judge`). A row waits on
    another until that one is merged or ended `done`, by the rule `dispatch` launches by
    (`watch.final`).

    With GitHub silent and T3 Code answering, the steps that list the threads out did not
    run, since they act on a world: the threads out are listed here as that step lists them,
    and `stall.hung` reads them, so a thread's liveness is still judged and a hang told.
    """
    run, world, rows, client = half.run, half.seen.world, half.rows, half.client
    if rows is None:
        return
    if world is None and half.out is None and half.seen.out is not None and client is not None:
        half.out = threads.out(run, client, stall.watched(run))
        stall.hung(run, half.out)
    said = dict(watch.waits(run, half.said, merge.home_thread(run)).said) if world else {}
    if half.said.failed:
        for row in rows:
            number = str(row.get("pr", "")).removeprefix("#")
            if row.get("status") == "pr" and number and number not in said:
                said[number] = row.get("why", "")
    last = work.last(run.state)
    seen = watch.Seen(half.out, half.gone, said, watch.final(run, world, rows), half.answered())
    half.states = watch.Judging(run, world, seen, last)


def derive(half: Half) -> None:
    """Rewrite the table's derived columns (`queue.derive`), and say that it changed."""
    run, world, states = half.run, half.seen.world, half.states
    waits = watch.waits(run, half.said, merge.home_thread(run))
    unread = watch.unread(run, half.read)

    def facts(row: queue.Row) -> queue.Row:
        slug = row["slug"]
        launched = dispatch.launched(run, slug)
        found = watch.status(run, world, slug, states.of(row, launched), launched)
        return {**found, "why": watch.why(run, row, found, waits, unread)}

    at = run.now.astimezone(UTC).isoformat(timespec="seconds")
    half.table, half.changed = queue.derive(run.state, facts, run.user.stamp(run.now), at)
    if half.changed:
        line = f"queue {run.project.name}: the table changed"
        run.box.send("", "queue", line, queue.changes(half.changed))


def unplaced(half: Half) -> None:
    """Tell the home of each row whose pull request is open and on no step (`merge.unplaced`),
    by what `jmerge` said of it in this pass."""
    run, world, states = half.run, half.seen.world, half.states
    for row in half.table or []:
        slug = row["slug"]
        pull = (world.open if world else {}).get(slug)
        if pull is None:
            continue
        number = str(pull.get("number", ""))
        said = states.seen.said.get(number, "")
        home = leftover.home_of(run.home, watch.brief_of(run, slug))
        merge.unplaced(run, half.client, slug, number, said, word.home(home))


def keep_work(half: Half) -> None:
    """Write `work.json`: the state of every row, and of every thread out that is no row's,
    each with who holds it (`work.holder`). With no list of the threads out, the threads are
    the last pass's, not confirmed."""
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
    at = run.now.astimezone(UTC).isoformat(timespec="seconds")
    work.write(run.state, at, half.answered(), listed)


STEPS = (
    verbs.Step("derive", 10, "states.judged", judged, ("sight",)),
    verbs.Step("derive", 20, "states.derive", derive, ("client", "world", "rows")),
    verbs.Step("after-derive", 30, "states.unplaced", unplaced, ("client", "world", "rows")),
    verbs.Step("after-derive", 40, "states.keep_work", keep_work, ("rows",)),
)
