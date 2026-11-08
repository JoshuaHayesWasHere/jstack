"""This module restates a row's line of `work.json` as each writer of that row's inputs writes, so
the view shows a change within milliseconds and not at the next pass (`jbus.work`).

A write of the queue restates the `Row` facet of each row it reaches (`queued`, from
`queue._changing`), and a run of `jmerge`, the tick's or the pass's, restates the `Pull` facet
and the `why` of each pull request it judged (`pulled`, from `merge._sent`), each judged again
from the facts the last pass kept (`work.restate`). Before its run of `jmerge`, and also where
`jmerge` is busy, the merge tick restates the `why` of each pull request on the check step whose
required checks ended at its head, from GitHub's list of runs (`checked`, from `jbus.tick`). The
next run of `jmerge` restates that line again, and where it judges otherwise its verdict stands
and the line is logged as drift (`pulled`, `corrects`). The pass still judges every row: it keeps a
`Pull` facet that a later run of `jmerge` restated (`kept`), and logs each line it corrects as
drift (`drift`, from `states.keep_work`). Every writer holds `work.LOCK`.

`jbus follow` restates the `Thread` facet of each line whose thread T3 Code says started, ended,
was settled or was archived (`followed`, from `jbus.follow`). The pass keeps a `Thread` facet an
event after the pass began gave (`heard`), and while the follower has run (`following`) counts a
thread's facet as drift too.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jbus import locked, read_json, write_json
from jbus.work import (
    APPROVED,
    LOCK,
    Answered,
    Facts,
    Launch,
    Pull,
    Question,
    Row,
    Thread,
    Written,
    entry,
    holder,
    judge,
    path,
    read,
    restate,
    scouting,
    stored,
)
from jmerge import ready

SEEN = ("thread", "pr")
"""The columns of a row of the queue that a new row's line carries as they are (`fresh`)."""
PULLED = "pulled"
"""The field of a line that says when a run of `jmerge` last restated its `Pull` facet."""
FOLLOWED = "followed"
"""The field of a line that says when the T3 Code event that `jbus follow` last restated its
`Thread` facet from happened."""
CHECKED = "checked"
"""The field of a line that says the merge tick restated it from a run that ended, before any run
of `jmerge` judged that run: `failed` or `passed` (`checked`). The next run of `jmerge` that
judges the pull request takes it off (`pulled`)."""
FAILED, PASSED = "failed", "passed"
ENDED = "ended"
"""The field of a line that names the head whose required checks a verdict said had ended: the
merge tick's (`checked`), or a run of `jmerge`'s that merged the pull request or judged its
checks ended (`pulled`, `ends`). The pass keeps watching a head whose rollup it reads as ended
until its line names it here (`jbus.tick`): a rollup can say `passed` before a job that is still
to start is in it, and the tick then has a check left to see end (#1246)."""
PENDING = "checks-pending.json"
"""The open pull requests whose checks the last pass saw still going, each by its `number` with
the `head` it saw, for the merge tick to watch (`jbus.tick`). Only the pass writes it."""
ENDS = frozenset(
    reason.code
    for reason in (
        ready.CHECK_FAILED,
        ready.CANCELLED_UNRUN,
        ready.CANCELLED_TWICE,
        ready.UNDECIDED,
    )
)
"""The reasons on the check step that `jmerge` gives only once the checks at the head ended. Every
other reason on it, such as a run still going or one not listed yet, says they may not have."""
PASS_ONLY = frozenset({"lost", "unknown"})
"""The values that only the pass judges: a thread that ended with nothing written is lost only
once the pass finds no wait of jbus's behind it and no pull request owed (`watch.facts`), and a
case no pattern covers is the pass's to report."""
FOLLOW = "follow.json"
"""The record of `jbus follow` in jbus's own state directory: since when it follows T3 Code's
events, how often it found its stream lost, and why it last did."""


def _rewrite(state_dir: Path, change: Callable[[list[Any]], list[Any]]) -> None:
    """Rewrite the lines of `work.json` with what `change` makes of them, under `LOCK`, and
    write nothing where nothing changed. A file that no pass wrote yet is left as it is."""
    with locked(state_dir, LOCK):
        kept = read(state_dir)
        if kept is None:
            return
        work = change(kept["work"])
        if work != kept["work"]:
            write_json(path(state_dir), {**kept, "work": work})


def _is_row(one: Any) -> bool:
    return isinstance(one, dict) and one.get("kind") == "row" and isinstance(one.get("key"), str)


def queued(
    state_dir: Path,
    rows: list[dict[str, Any]],
    facet: Callable[[dict[str, Any]], Row],
    scout: Callable[[dict[str, Any]], bool],
    moved: set[str],
) -> None:
    """Restate the line of `work.json` of each row of `moved` from the queue as it is now: the
    `Row` facet that `facet` gives the row. A row the queue no longer has loses its line, and a
    row with no line yet gets one judged with nothing launched, written or open (`fresh`), which
    the next pass judges in full. Each write of the queue calls this under the queue's lock once
    it wrote (`queue._changing`), so the view shows a change of the queue at once."""
    by_slug = {row["slug"]: row for row in rows}

    def change(lines: list[Any]) -> list[Any]:
        work, had = [], set()
        for one in lines:
            if _is_row(one):
                row = by_slug.get(one["key"])
                if row is None:
                    continue
                had.add(one["key"])
                if one["key"] not in moved:
                    work.append(one)
                    continue
                one = restate(one, row=facet(row))
            work.append(one)
        at = max((n for n, one in enumerate(work) if _is_row(one)), default=-1) + 1
        work[at:at] = [fresh(row, facet(row), scout(row)) for row in rows if row["slug"] not in had]
        return work

    _rewrite(state_dir, change)


def fresh(row: dict[str, Any], facet: Row, scout: bool) -> dict[str, Any]:
    """Return the line of a row that no pass judged yet: nothing launched, written or open."""
    facts = Facts(
        facet, Thread.NONE, Launch.NONE, Written.NONE, Pull.NONE, Question.NONE, Answered.BOTH
    )
    state = judge(facts)
    slug = row["slug"]
    about = {"key": slug, "kind": "row", "slug": slug, **{name: row.get(name, "") for name in SEEN}}
    said = {"scout": str(scouting(state))} if scout else {}
    return entry(state, holder(state, role="scout" if scout else ""), **about, **said)


def pending(state_dir: Path) -> dict[int, str]:
    """Return the head of each pull request the merge tick watches (`PENDING`), by number."""
    return {
        one["number"]: one["head"]
        for one in read_json(state_dir / PENDING, [])
        if isinstance(one, dict) and isinstance(one.get("number"), int) and one.get("head")
    }


def ended(state_dir: Path) -> dict[int, str]:
    """Return, by number, the head each row's line of a pull request names as one whose checks a
    verdict said ended (`ENDED`), or nothing for a line that names none. A pull request with no
    row's line has nothing on the view to keep right, and is not in it."""
    kept = read(state_dir) or {"work": []}
    found = {}
    for one in kept["work"]:
        number = str(one.get("pr", "")).removeprefix("#") if _is_row(one) else ""
        if number.isdigit():
            found[int(number)] = str(one.get(ENDED, ""))
    return found


def ends(pull: Pull, why: str) -> bool:
    """Whether a run of `jmerge` that judged a pull request `pull` for `why` saw the checks at its
    head end: it merged it, or judged it on the check for a reason only an ended check gives
    (`ENDS`). A verdict on any other step says nothing of them: `jmerge` judges a pull request's
    Result, review and findings before its checks, and a hold may come before or after them, so
    such a head stays watched until the tick's list of runs shows its end (`checked`)."""
    if pull == Pull.MERGED:
        return True
    return pull == Pull.CHECK and ready.code_of(why.partition(": ")[2]) in ENDS


def pulled(state_dir: Path, said: dict[int, tuple[Pull, str]], at: str) -> list[tuple[str, str]]:
    """Restate the `Pull` facet of the line of each pull request that a run of `jmerge` judged,
    by its number, as `jmerge` judged it, with its reason as the line's `why`, and mark the line
    `PULLED` at `at`, when the run ended (`Said.at`). The pass and the merge tick both call this
    as their run of `jmerge` ends (`merge._sent`), so a verdict reaches the view at once. The
    pass keeps a facet that a run after its own restated (`kept`).

    A line the merge tick restated (`CHECKED`) loses the mark, and where the run judged it
    otherwise than the tick (`corrects`), the run's verdict stands and the line is returned by key
    with what was wrong in it, for the caller to log as drift. A line of a pull request the tick
    watches names its head as `ENDED` where the run saw its checks end (`ends`): the run read the
    pull request after the pass that wrote the head, so it judged that head or a later one."""
    drifted: list[tuple[str, str]] = []
    heads = pending(state_dir)

    def change(lines: list[Any]) -> list[Any]:
        work = []
        for one in lines:
            number = str(one.get("pr", "")).removeprefix("#") if _is_row(one) else ""
            if number.isdigit() and int(number) in said:
                pull, why = said[int(number)]
                tick = str(one.get(CHECKED, ""))
                if wrong := corrects(one, tick, pull, why):
                    drifted.append((str(one["key"]), wrong))
                made = restate(one, pull=pull, why=why)
                if made is not one or tick:
                    one = {**{k: v for k, v in made.items() if k != CHECKED}, PULLED: at}
                if (head := heads.get(int(number))) and ends(pull, why):
                    one = {**one, ENDED: head}
            work.append(one)
        return work

    if said:
        _rewrite(state_dir, change)
    return drifted


def corrects(one: dict[str, Any], tick: str, pull: Pull, why: str) -> str:
    """Return what a run of `jmerge` that judged `pull` for `why` found wrong in the line the
    merge tick restated as `tick`, or nothing where it agrees or the tick did not restate it. A
    check that failed keeps the pull
    request on the check step for the reason the tick gave it. A pass moves it on from the check
    step, to any step `jmerge` judges, so only a verdict that keeps it on the check step says
    otherwise."""
    had = str(one.get("why", ""))
    if not tick:
        return ""
    if tick == FAILED and (pull, why) == (Pull.CHECK, had):
        return ""
    if tick == PASSED and pull != Pull.CHECK:
        return ""
    return f"the tick's check {tick} ({had!r}) for {str(pull)!r} ({why!r})"


def checked(state_dir: Path, said: dict[int, tuple[str, str, str, str]], at: str) -> list[str]:
    """Restate the line of each pull request in `said`, by its number, that is on the check step:
    the `why` a run of `jmerge` would give it now that its required checks ended at `head`, with
    `failed` or `passed` (`CHECKED`), and `ended`, when the last of them ended on GitHub. The line
    names `head` as `ENDED` on any step, so the pass stops watching it. Mark it
    `PULLED` at `at`, so the pass keeps it as a later word than its own run's (`kept`). A line that
    a run of `jmerge` judged after `ended` is left as it is, since that run saw the end, so the
    tick that asks again after a busy `jmerge` writes nothing twice. Return the keys of the lines
    it changed. The merge tick calls this as soon as GitHub lists the runs (`jbus.tick`)."""
    changed: list[str] = []

    def change(lines: list[Any]) -> list[Any]:
        work = []
        for one in lines:
            number = str(one.get("pr", "")).removeprefix("#") if _is_row(one) else ""
            facts = stored(one) if number.isdigit() and int(number) in said else None
            if facts is None:
                work.append(one)
                continue
            tick, why, ended, head = said[int(number)]
            one = one if one.get(ENDED) == head else {**one, ENDED: head}
            if facts.pull == Pull.CHECK and str(one.get(PULLED, "")) <= ended:
                made = restate(one, pull=Pull.CHECK, why=why)
                if made is not one:
                    one = {**made, PULLED: at, CHECKED: tick}
                    changed.append(str(one["key"]))
            work.append(one)
        return work

    _rewrite(state_dir, change)
    return changed


def kept(one: dict[str, Any], was: dict[str, Any] | None, ran: str) -> dict[str, Any]:
    """Return the pass's line `one`, with the `Pull` facet of the file's line `was` where a run of
    `jmerge` that ended after `ran`, when the pass's own run ended, restated it: a merge tick's
    run judged later than the pass's own run, whose verdict the pass's line holds. The line keeps
    that run's `why` too, which names what holds it, such as a stacked line's parent."""
    facts = stored(was) if was is not None and str(was.get(PULLED, "")) > ran else None
    if facts is None or was is None:
        return one
    return {**restate(one, pull=facts.pull, why=str(was.get("why", ""))), PULLED: was[PULLED]}


def followed(state_dir: Path, thread: str, facet: Thread, at: str) -> list[str]:
    """Restate the `Thread` facet of each line of `work.json` whose thread is `thread`, a row's or
    a thread's that belongs to no row, as T3 Code's event at `at` gives it (`jbus.follow`), and
    mark the line `FOLLOWED` at `at`. A line that would turn a value only the pass judges
    (`PASS_ONLY`) is left for the pass, and so is a line marked after `at`, which a later event
    restated. Return the keys of the lines it changed."""
    changed: list[str] = []

    def change(lines: list[Any]) -> list[Any]:
        work = []
        for one in lines:
            if isinstance(one, dict) and one.get("thread") == thread:
                made = restate(one, thread=facet)
                later = str(one.get(FOLLOWED, "")) > at
                if made is not one and made["value"] not in PASS_ONLY and not later:
                    one = {**made, FOLLOWED: at}
                    changed.append(str(one.get("key", "")))
            work.append(one)
        return work

    _rewrite(state_dir, change)
    return changed


def heard(one: dict[str, Any], was: dict[str, Any] | None, began: str) -> dict[str, Any]:
    """Return the pass's line `one`, with the `Thread` facet of the file's line `was` where `jbus
    follow` restated it from a T3 Code event that happened after `began`, when the pass began: the
    pass may have read T3 Code before that event, and the event is the later word. A value only
    the pass judges stays the pass's."""
    facts = stored(was) if was is not None and str(was.get(FOLLOWED, "")) > began else None
    if facts is None or was is None or one.get("thread") != was.get("thread"):
        return one
    made = restate(one, thread=facts.thread)
    return one if made["value"] in PASS_ONLY else {**made, FOLLOWED: was[FOLLOWED]}


def following(top: Path) -> bool:
    """Say whether `jbus follow` follows T3 Code's events for the machine whose jbus state
    directory is `top`: it wrote its record (`FOLLOW`)."""
    return isinstance(read_json(top / FOLLOW, None), dict)


def drift(before: list[Any], after: list[Any], following: bool = False) -> list[tuple[str, str]]:
    """Return each row's line that the pass corrects and that a writer should have kept right, by
    key, with what was wrong in it: a line for a row the queue no longer has, no line for a row it
    has, a `Row` facet the queue gave otherwise (a move between `APPROVED` facets is the pass's to
    judge, as `restate` says), a `Pull` facet that a run of `jmerge` restated (`PULLED`) and that
    the pass, with GitHub's answer, judges otherwise for the same pull request, or a value that does
    not follow from the line's own facts, which no writer restates since its facts are right.
    While `jbus follow` follows T3 Code (`following`), a thread's facet is drift too where it put
    the line in another value than the pass's, and its thread under way, ended, settled or archived
    otherwise than the pass: an event the follower missed, as when its stream was lost. A thread's
    liveness, which only the pass reads, and a value only the pass judges (`PASS_ONLY`) are not.

    What was written, and a pull request no run of `jmerge` restated on the line yet, are no
    drift. The writers run in the pass too, before it
    writes, so a facet broken in the file is most often put right by one of them first, and the
    pass then finds nothing of it to correct."""
    was = {one["key"]: one for one in before if _is_row(one)}
    now = {one["key"]: one for one in after if _is_row(one)}
    found = []
    for key in sorted(was.keys() | now.keys()):
        old, new = was.get(key), now.get(key)
        if old is None:
            found.append((key, "no line"))
        elif new is None:
            found.append((key, "a line for a row the queue does not have"))
        elif off := _off(old, new) + (_unheard(old, new) if following else []):
            found.append((key, ", ".join(off)))
    return found


_PHASE: dict[str, str] = {
    **dict.fromkeys(
        (Thread.STARTING, Thread.MOVING, Thread.QUIET, Thread.HUNG, Thread.WAITING), "under way"
    ),
    **dict.fromkeys((Thread.COMPLETED, Thread.FAILED), "ended"),
}
FOLLOWS = frozenset({"under way", "ended", str(Thread.SETTLED), str(Thread.ARCHIVED)})
"""The phases a thread's events move it between. A launch, which moves a line from no thread to
one, and a thread that left T3 Code's list are the pass's to see."""


def phase(facet: str) -> str:
    """Return where a thread is as `jbus follow` sees it: under way, ended, settled, archived,
    or the facet itself for one it never writes."""
    return _PHASE.get(facet, facet)


def _unheard(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    threads = ((old.get("facts") or {}).get("thread"), (new.get("facts") or {}).get("thread"))
    if old.get("thread") != new.get("thread") or new.get("value") in PASS_ONLY:
        return []
    phases = (phase(threads[0] or ""), phase(threads[1] or ""))
    if old.get("value") == new.get("value") or phases[0] == phases[1]:
        return []
    if not set(phases) <= FOLLOWS:
        return []
    return [f"thread {threads[0]!r} for {threads[1]!r}"]


def _off(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    facts = (old.get("facts") or {}, new.get("facts") or {})
    rows = (facts[0].get("row"), facts[1].get("row"))
    pulls = (facts[0].get("pull"), facts[1].get("pull"))
    off = []
    if rows[0] != rows[1] and not set(rows) <= set(APPROVED):
        off.append(f"row {rows[0]!r} for {rows[1]!r}")
    heard = facts[1].get("answered") in (Answered.BOTH, Answered.GITHUB)
    if pulls[0] != pulls[1] and PULLED in old and old.get("pr") == new.get("pr") and heard:
        off.append(f"pull {pulls[0]!r} for {pulls[1]!r}")
    if facts[0] == facts[1] and old.get("value") != new.get("value"):
        off.append(f"value {old.get('value')!r} for {new.get('value')!r}")
    return off


def moment(at: datetime) -> str:
    """Return `at` as `PULLED` keeps it: in UTC to the microsecond, so stamps compare as text."""
    return at.astimezone(UTC).isoformat(timespec="microseconds")
