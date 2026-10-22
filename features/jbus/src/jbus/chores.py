"""Run the steps that close a project's pass, before `alert.flush`. A pass in which T3 Code and
GitHub both answered (a pass with a world) records that a whole pass has run (`chores.began`). Then
the pass sends the day's snapshot, and runs the sweep that is due.

Once a day, at or after `wake.SNAPSHOT_AT`, a pass sends the snapshot: the table, and the last
Result of each brief written in `SNAPSHOT_DAYS`. For each pull request that merged
`wake.PRUNE_AFTER` ago, it then prunes the record of what it sent. It forgets the log's lines older
than `wake.LOG_KEEP`. Last, it records that the day's look at what `jmerge` would sweep is due. Each
pass runs that look again until `jmerge` has run.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from jbus import merge, mirror, queue, verbs, wake, watch

if TYPE_CHECKING:
    from jbus.cli import Half

SNAPSHOT_DAYS = 14


def snapshot(run: wake.Pass, rows: list[queue.Row] | None) -> str:
    parts = [queue.render(rows) if rows is not None else "queue.json does not parse\n"]
    since = (run.now - timedelta(days=SNAPSHOT_DAYS)).timestamp()
    briefs = [p for p in (run.home / "tasks").glob("*.md") if p.stat().st_mtime >= since]
    for path in sorted(briefs, key=lambda p: p.stat().st_mtime, reverse=True):
        text = path.read_text(errors="replace")
        title = text.splitlines()[0] if text.strip() else f"# {path.stem}"
        parts.append(f"\n{title}\n{mirror.last_result(text) or 'no Result'}\n")
    return "".join(parts)


def daily(half: Half) -> None:
    """Send the day's snapshot when it is due, then prune and forget."""
    run, world = half.run, half.seen.world
    day = run.box.snapshot_due(run.user.local(run.now))
    if day:
        line = f"snapshot {run.project.name}: {day}"
        run.box.send("", "snapshot", line, snapshot(run, half.table), cap=wake.SNAPSHOT_CAP)
        run.box.snapshot_sent(day)
        if world is not None:
            run.box.prune(
                {
                    slug
                    for slug, pull in world.merged.items()
                    if slug not in world.open
                    and run.now - watch.when(pull["mergedAt"]) >= wake.PRUNE_AFTER
                }
            )
        run.box.forget(run.now - wake.LOG_KEEP)


def sweep(half: Half) -> None:
    """Run the sweep that is due, and record how it went."""
    run = half.run
    owed = run.box.sweep_owed()
    if owed:
        ran, how = merge.sweep(run)
        how = f"{owed}: {how}" if ran else f"{owed}: {how}, retrying next pass"
        if not ran:
            run.say(f"wait {run.project.name}: {how}")
        run.box.swept(how, ran)


STEPS = (
    verbs.Step("close", 40, "chores.began", lambda half: half.run.box.began(), ("world",)),
    verbs.Step("close", 50, "chores.daily", daily),
    verbs.Step("close", 60, "chores.sweep", sweep),
)
