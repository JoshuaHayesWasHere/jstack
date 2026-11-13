"""Where a scout's row stands, as T3 Code's tree draws it from the `scout` of its line of
`work.json`: queued, scouting or report in (`scouting`), or none for a row that leaves the tree
(`scouted`). Every writer of the file gives a scout's row its `scout` from here: the pass
(`states.keep_work`) and each restate between passes (`restated.restate`, `restated.fresh`)."""

from __future__ import annotations

from enum import StrEnum

from jbus.work import Launch, State, Thread, Written


class Scouting(StrEnum):
    QUEUED = "queued"
    SCOUTING = "scouting"
    REPORT_IN = "report in"


def scouting(state: State) -> Scouting:
    """Return where a scout's row stands, as the tree's diamond draws it. The row's report is in
    once its last Report says `Status: done`, whether or not its thread was settled. It is queued
    while no thread was launched for it, and scouting otherwise: a thread starting, at work, or
    ended with no Report that says done. A row taken over by a crewmate's brief is no scout's
    row, and has no such state."""
    facts = state.facts
    if facts.written == Written.CLEAN:
        return Scouting.REPORT_IN
    if facts.thread == Thread.NONE and not facts.seen and facts.launch == Launch.NONE:
        return Scouting.QUEUED
    return Scouting.SCOUTING


def scouted(state: State, thread: str) -> dict[str, str]:
    """Return the `scout` a scout's row of `work.json` carries (`scouting`), as every writer of
    the file gives it. A row at done that names no thread, as one is once its request file went
    with a closed home and its thread was archived, has none: T3 Code's tree shows any row with a
    `scout` and lets a scout's go once its thread is archived, and this row has no thread to
    archive, so with no `scout` it leaves the tree as a done crew row does."""
    if state.value == "done" and not thread:
        return {}
    return {"scout": str(scouting(state))}
