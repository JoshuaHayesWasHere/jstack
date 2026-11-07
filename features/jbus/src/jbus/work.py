"""This module works out the state of each piece of work once a pass, in this one place.

`judge` does all of this work. `judge` reads no clock and no file. The pass gives it `Facts`, seven
closed facets of one row of the queue or of one thread that belongs to no row, and `judge` returns
one `State`. The facets are:

- `Row`: whether the queue has the row, and how its go stands.
- `Thread`: the row's thread as T3 Code reports it, with its liveness (`jbus.live`). When T3 Code
  does not list the thread, the facet is `archived` if T3 Code reads the thread back as archived,
  `missing` if T3 Code has no such thread, and `starting` if T3 Code has the thread and does not
  list it yet. So jbus does not lose a launch when the launch's thread leaves the list.
- `Launch`: whether a launch record names a thread.
- `Written`: what the brief's last Result says. For a thread that belongs to no row, it is what
  the thread's role owes: a scout owes its Report, a reviewer its Review, and a home or another
  thread nothing.
- `Pull`: the work's pull request. For an open pull request, the facet is the step that jmerge's
  reason names (`jmerge.judgement.step`), or `other` for a reason that no rule names. A pull
  request stacked on another row's (`jmerge.ready.STACKED_ON`) is `stacked`, held by that row.
- `Question`: whether jbus has a gate open for the work this pass.
- `Answered`: which of T3 Code and GitHub answered this pass.

Each value of `VALUES` but `unknown` is one `Pattern`. A pattern is a set of what each facet may be,
with who holds the work in that state and the one thing the work waits for. No two patterns match
one set of facts. When no pattern matches a set of facts, the state is `unknown` and carries those
facts, so jbus reports a case that no pattern covers as it is. A pattern needs the sources of the
facets that it narrows: T3 Code for `Thread` and `Launch`, and GitHub for `Pull`. While one of those
sources has not answered, `judge` passes over the pattern. When a source has not answered and no
pattern matches, the state is the last state that a pass judged (`Facts.last`), marked not
confirmed.

`status` gives the row's `status` column, one of `queue.STATUSES`, as a projection of the
state, so every reader of the queue still finds the same words as before. `scouting` gives a
scout's row one of queued, scouting and report in, which the sidebar's tree draws. `write` keeps
every state of a pass, whole, in `work.json` in the project's state directory, and the view
draws that file. Between passes, each writer of a row's inputs restates that row's line, judged
again from the facts the last pass kept for it with the facet that writer knows (`restate`): a
write of the queue restates each row's `Row` facet (`queued`, from `queue._changing`), and a run of
`jmerge` restates the `Pull` facet of each pull request it judged (`pulled`, from `merge._sent`).
So the view shows a change within milliseconds, not at the next pass. The pass still judges every
row, keeps a `Pull` facet a later run of `jmerge` restated (`kept`), and logs each line it
corrects as drift (`drift`, from `states.keep_work`). Every writer holds `LOCK`.
"""

from __future__ import annotations

import functools
import itertools
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from jbus import locked, read_json, roles, write_json
from jmerge import ready

NAME = "work.json"
LOCK = "work.lock"
T3, GITHUB = "T3 Code", "GitHub"


class Row(StrEnum):
    ABSENT = "absent"
    REMOVED = "removed"
    UNAPPROVED = "unapproved"
    CHANGED = "brief changed"
    BEHIND = "approved and behind"
    FREE = "approved and free"


class Thread(StrEnum):
    NONE = "none"
    STARTING = "starting"
    MOVING = "moving"
    QUIET = "quiet"
    HUNG = "hung"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    SETTLED = "settled"
    ARCHIVED = "archived"
    MISSING = "missing"


class Launch(StrEnum):
    NONE = "none"
    LAUNCHED = "launched"


class Written(StrEnum):
    NONE = "none"
    CLEAN = "clean"
    LEFTOVER = "leftover"
    MALFORMED = "malformed"


class Pull(StrEnum):
    NONE = "none"
    MERGED = "merged"
    CLOSED = "closed"
    RESULT = "result"
    REVIEW = "review"
    FINDINGS = "findings"
    SECOND = "second"
    CHECK = "check"
    STACKED = "stacked"
    REBASE = "rebase"
    HOLD = "hold"
    OTHER = "other"


class Question(StrEnum):
    NONE = "none"
    OPEN = "open"


class Answered(StrEnum):
    BOTH = "both"
    T3 = "T3 Code only"
    GITHUB = "GitHub only"
    NEITHER = "neither"


STEPPED = (
    Pull.RESULT,
    Pull.REVIEW,
    Pull.FINDINGS,
    Pull.SECOND,
    Pull.CHECK,
    Pull.STACKED,
    Pull.REBASE,
    Pull.HOLD,
)
OPEN = (*STEPPED, Pull.OTHER)
HEARD = {
    Answered.BOTH: frozenset({T3, GITHUB}),
    Answered.T3: frozenset({T3}),
    Answered.GITHUB: frozenset({GITHUB}),
    Answered.NEITHER: frozenset(),
}
FACETS = {
    "row": Row,
    "thread": Thread,
    "launch": Launch,
    "written": Written,
    "pull": Pull,
    "question": Question,
    "answered": Answered,
}
SOURCE = {"thread": T3, "launch": T3, "pull": GITHUB}


@dataclass(frozen=True)
class Facts:
    """`Facts` are what a pass knows of one piece of work: one value of each facet.

    `last` is no facet: it is the value that the last pass judged, or nothing when no pass did.
    `seen` is no facet either. It is the status that T3 Code gave a thread when jbus does not know
    that status. The thread's `thread` facet is then `none`, and the work's state is `unknown`
    (`unforeseen`)."""

    row: Row
    thread: Thread
    launch: Launch
    written: Written
    pull: Pull
    question: Question
    answered: Answered
    last: str = ""
    seen: str = ""

    def said(self) -> dict[str, str]:
        said = {name: str(getattr(self, name)) for name in FACETS}
        return said | ({"thread": self.seen} if self.seen else {})


@dataclass(frozen=True)
class Pattern:
    """A `Pattern` is one value, the facts that make it, and what it means. A facet the pattern does
    not name may be anything. `lane` is the step of the view's line where the view draws it."""

    value: str
    name: str
    who: str
    waits: str
    lane: str
    row: frozenset[Row] = frozenset(Row) - {Row.REMOVED}
    thread: frozenset[Thread] = frozenset(Thread)
    launch: frozenset[Launch] = frozenset(Launch)
    written: frozenset[Written] = frozenset(Written)
    pull: frozenset[Pull] = frozenset(Pull)
    question: frozenset[Question] = frozenset({Question.NONE})

    def matches(self, facts: Facts) -> bool:
        return all(getattr(facts, name) in getattr(self, name, FACETS[name]) for name in FACETS)

    @functools.cached_property
    def needs(self) -> frozenset[str]:
        """Return the sources of the facets that the pattern narrows, which are the ones that must
        have answered. The property works them out once, since a pass judges every row
        against every pattern."""
        return frozenset(
            source
            for name, source in SOURCE.items()
            if getattr(self, name) != frozenset(FACETS[name])
        )


def _set(*values: Any) -> frozenset[Any]:
    return frozenset(values)


STILL = frozenset(Thread) - {Thread.HUNG, Thread.WAITING}
THERE = STILL - {Thread.NONE, Thread.STARTING}
NOTHING = {"written": _set(Written.NONE), "pull": _set(Pull.NONE)}
UNSTARTED = {"thread": _set(Thread.NONE), "launch": _set(Launch.NONE), "pull": _set(Pull.NONE)}
AGAIN = "your word on what is left: jbus starts no second thread for it"

PATTERNS = (
    Pattern(
        "removed", "Removed", "ok", "nothing", "", row=_set(Row.REMOVED), question=_set(*Question)
    ),
    Pattern("asking", "Gate", "user", "your answer", "gate", question=_set(Question.OPEN)),
    Pattern("hung", "Hung", "user", "your word on its turn", "running", thread=_set(Thread.HUNG)),
    Pattern(
        "waiting",
        "Waiting",
        "user",
        "an answer to its thread's request",
        "running",
        thread=_set(Thread.WAITING),
    ),
    Pattern(
        "merged",
        "Merged",
        "ok",
        "nothing",
        "merged",
        thread=STILL,
        written=_set(Written.NONE, Written.CLEAN),
        pull=_set(Pull.MERGED),
    ),
    Pattern(
        "leftover",
        "Ended, with a leftover",
        "user",
        "your word on that note",
        "gate",
        thread=THERE,
        written=_set(Written.LEFTOVER, Written.MALFORMED),
        pull=_set(Pull.NONE, Pull.MERGED),
    ),
    Pattern(
        "done",
        "Done",
        "ok",
        "nothing",
        "merged",
        thread=THERE,
        written=_set(Written.CLEAN),
        pull=_set(Pull.NONE),
    ),
    Pattern(
        "closed",
        "Closed",
        "user",
        "your word on how it ends",
        "gate",
        thread=STILL,
        pull=_set(Pull.CLOSED),
    ),
    Pattern(
        "result",
        "Result",
        "crew",
        "a Result in its brief",
        "result",
        thread=STILL,
        pull=_set(Pull.RESULT),
    ),
    Pattern(
        "review", "Review", "rev", "its reviewer", "review", thread=STILL, pull=_set(Pull.REVIEW)
    ),
    Pattern(
        "findings",
        "Findings",
        "crew",
        "its crewmate to handle the findings",
        "findings",
        thread=STILL,
        pull=_set(Pull.FINDINGS),
    ),
    Pattern(
        "second",
        "Second pass",
        "rev",
        "its reviewer",
        "second",
        thread=STILL,
        pull=_set(Pull.SECOND),
    ),
    Pattern(
        "check", "Check", "ci", "the check runner", "check", thread=STILL, pull=_set(Pull.CHECK)
    ),
    Pattern(
        "stacked",
        "Stacked",
        "dep",
        "the row it is stacked on to merge",
        "check",
        thread=STILL,
        pull=_set(Pull.STACKED),
    ),
    Pattern(
        "rebase", "Rebase", "crew", "its crewmate", "rebase", thread=STILL, pull=_set(Pull.REBASE)
    ),
    Pattern("hold", "Needs you", "user", "your word", "hold", thread=STILL, pull=_set(Pull.HOLD)),
    Pattern(
        "launching",
        "Launching",
        "crew",
        "its thread to start",
        "running",
        thread=_set(Thread.STARTING),
        pull=_set(Pull.NONE),
    ),
    Pattern(
        "working",
        "Running",
        "crew",
        "its crewmate",
        "running",
        thread=_set(Thread.MOVING),
        **NOTHING,
    ),
    Pattern(
        "quiet",
        "Quiet",
        "crew",
        "its thread to write again",
        "running",
        thread=_set(Thread.QUIET),
        **NOTHING,
    ),
    Pattern(
        "lost",
        "Lost",
        "user",
        AGAIN,
        "running",
        thread=_set(
            Thread.NONE,
            Thread.COMPLETED,
            Thread.FAILED,
            Thread.SETTLED,
            Thread.ARCHIVED,
            Thread.MISSING,
        ),
        launch=_set(Launch.LAUNCHED),
        **NOTHING,
    ),
    Pattern(
        "unapproved",
        "Not approved",
        "user",
        "your approval",
        "queued",
        row=_set(Row.UNAPPROVED, Row.CHANGED),
        **UNSTARTED,
    ),
    Pattern(
        "behind",
        "Behind",
        "dep",
        "the rows in front of it to merge",
        "queued",
        row=_set(Row.BEHIND),
        **UNSTARTED,
    ),
    Pattern(
        "ready",
        "Ready",
        "bus",
        "the next pass of jbus",
        "queued",
        row=_set(Row.FREE),
        **UNSTARTED,
    ),
)
UNKNOWN = Pattern("unknown", "Unknown", "unknown", "what the view cannot tell", "unknown")
VALUES = (*(pattern.value for pattern in PATTERNS), UNKNOWN.value)
BY_VALUE = {pattern.value: pattern for pattern in (*PATTERNS, UNKNOWN)}


@dataclass(frozen=True)
class State:
    """A `State` is the one state of a piece of work: its value, who holds it, the one thing it
    waits for, whether this pass confirmed it, and the facts from which `judge` judged it."""

    value: str
    who: str
    waits: str
    confirmed: bool
    facts: Facts

    @property
    def pattern(self) -> Pattern:
        return BY_VALUE[self.value]


def matching(facts: Facts) -> list[Pattern]:
    """Return every pattern the facts match, whatever answered. At most one pattern matches,
    as the walk proves."""
    return [pattern for pattern in PATTERNS if pattern.matches(facts)]


def judge(facts: Facts) -> State:
    heard = HEARD[facts.answered]
    found = [pattern for pattern in PATTERNS if pattern.needs <= heard and pattern.matches(facts)]
    if found:
        return _state(found[0], facts, True)
    if heard == HEARD[Answered.BOTH]:
        return _state(UNKNOWN, facts, True)
    return _state(BY_VALUE.get(facts.last, UNKNOWN), facts, False)


def _state(pattern: Pattern, facts: Facts, confirmed: bool) -> State:
    return State(pattern.value, pattern.who, pattern.waits, confirmed, facts)


def every() -> Iterator[Facts]:
    """Yield every set of facts there is, once each, with no last state."""
    for row, thread, launch, written, pull, question, answered in itertools.product(
        Row, Thread, Launch, Written, Pull, Question, Answered
    ):
        yield Facts(row, thread, launch, written, pull, question, answered)


def status(state: State) -> str:
    """Return the row's `status`, one of `queue.STATUSES`, as the state projects it.

    A gate comes first, then the pull request. A row whose pull request is open is `pr`, and one
    whose pull request merged is `merged`, whatever the thread does. A thread in a status that jbus
    does not know makes the row `stale`, for somebody to look at. A hung turn makes the row `stale`
    too. A thread that ended with nothing written makes the row `stale` when it completed or was
    archived, and `failed` when it failed. The row is `launched` while no thread is there for a
    launch, and `queued` once the thread was settled. A thread that left T3 Code's list changes
    nothing for a row that ended: it counts only for a row with nothing written. `status` reads no
    clock. A `stale` row with nothing written becomes `left` once the pass finds the row's thread
    quiet for long enough, which `watch.unwritten` decides.
    """
    facts, value = state.facts, state.value
    if value == "asking":
        return "gate"
    if facts.pull in OPEN:
        return "pr"
    if facts.pull == Pull.MERGED:
        return "merged"
    if value == "done":
        return "done"
    if value in ("leftover", "closed"):
        return "left"
    if facts.seen:
        return "stale"
    if facts.thread in (Thread.NONE, Thread.MISSING) and facts.launch == Launch.LAUNCHED:
        return "launched"
    return _THREAD.get(facts.thread, "queued")


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


_THREAD = {
    Thread.NONE: "queued",
    Thread.STARTING: "launched",
    Thread.MOVING: "running",
    Thread.QUIET: "running",
    Thread.HUNG: "stale",
    Thread.WAITING: "waiting",
    Thread.COMPLETED: "stale",
    Thread.FAILED: "failed",
    Thread.SETTLED: "queued",
    Thread.ARCHIVED: "stale",
}


def without_t3(answered: Answered) -> Answered:
    """Return `answered` with T3 Code taken out. That is what a pass knows when it could not
    ask T3 Code about one row's thread, whatever it knows of the others."""
    return {Answered.BOTH: Answered.GITHUB, Answered.T3: Answered.NEITHER}.get(answered, answered)


def unforeseen(facts: Facts) -> State:
    """Return the state of work whose thread is in a status that jbus does not know. It is
    `unknown`, whatever the other facets say, since the work's `thread` facet is not what T3
    Code said."""
    return _state(UNKNOWN, facts, True)


@dataclass(frozen=True)
class Holder:
    """A `Holder` names who holds a state, the one thing it waits for, and the lane on which
    the view draws it."""

    who: str
    waits: str
    lane: str


def parent(why: str) -> str:
    """Return the row that a row's `why` says it is stacked on (`ready.STACKED_ON`), or nothing
    where it says no such thing. `why` is the queue's, `<word>: <reason>`, as jbus judged it."""
    fields = ready.STACKED_ON.fields(why.partition(": ")[2])
    return fields["slug"] if fields else ""


def holder(
    state: State, role: str = "", home: bool = False, busy: bool = False, why: str = ""
) -> Holder:
    """Return who holds a state, which is its pattern's holder except in four cases.

    A stacked row is held by the row it is stacked on, which its `why` names (`parent`): it
    waits for that row to merge, and no check runner or crewmate moves it.

    `role` is the role of a thread that belongs to no row. When such a thread is at work, the
    holder is that role, not a crewmate, and the state is on no lane of the line. A leftover or
    a closed pull request is the user's, with two exceptions. When `leftover.json` says that the
    pull request's home has it (`home`), the home holds the state. When its record says a thread
    is at work on the leftover (`busy`), the crewmate holds the state. Either holder is on the lane
    of work that is running.

    A role's holder is in `roles.ROLES`.
    """
    pattern = state.pattern
    if role:
        if pattern.who != "crew":
            return Holder(state.who, state.waits, "")
        waits = "its thread" if state.waits == "its crewmate" else state.waits
        held = next((one.holder for one in roles.ROLES if one.name == role), roles.OTHER)
        return Holder(held, waits, "")
    if state.value == "stacked" and (above := parent(why)):
        return Holder(above, f"{above} to merge", pattern.lane)
    if state.value not in ("leftover", "closed"):
        return Holder(state.who, state.waits, pattern.lane)
    if busy and state.value == "leftover":
        return Holder("crew", "its crewmate", "running")
    if home:
        return Holder("home", "its home", "running")
    return Holder(state.who, state.waits, pattern.lane)


def entry(state: State, held: Holder | None = None, **about: Any) -> dict[str, Any]:
    """Return one line of `work.json`: what the work is (`about`), its state, and who holds it
    (`holder`)."""
    held = held or holder(state)
    return {
        **about,
        "value": state.value,
        "name": state.pattern.name,
        "who": held.who,
        "waits": held.waits,
        "lane": held.lane,
        "confirmed": state.confirmed,
        "facts": state.facts.said(),
    }


APPROVED = frozenset({Row.BEHIND, Row.FREE})


def stored(one: dict[str, Any]) -> Facts | None:
    """Return the facts a line of `work.json` was judged from, with its value as `last`, or None
    for a line whose facts do not parse. A thread status that jbus does not know is `seen`."""
    said = one.get("facts")
    if not isinstance(said, dict) or one.get("value") not in VALUES:
        return None
    thread = str(said.get("thread", ""))
    known = thread in set(Thread)
    try:
        return Facts(
            row=Row(said["row"]),
            thread=Thread(thread) if known else Thread.NONE,
            launch=Launch(said["launch"]),
            written=Written(said["written"]),
            pull=Pull(said["pull"]),
            question=Question(said["question"]),
            answered=Answered(said["answered"]),
            last=one["value"],
            seen="" if known else thread,
        )
    except (KeyError, ValueError):
        return None


def restate(
    one: dict[str, Any], row: Row | None = None, pull: Pull | None = None
) -> dict[str, Any]:
    """Return a row's line of `work.json` judged again from its stored facts, with `row` as the
    new `Row` facet and `pull` as the new `Pull` facet where given, as the writer of that input
    knows it. A new approved facet beside an approved one is the pass's to tell apart, since only
    the pass sees which depends merged; and a state that keeps its value keeps its holder and its
    `why`, which the pass worked out from more than the facts. A state whose value changed has no
    `why` until the next pass judges one, since the one it had was judged for the old state. A
    line restated with the facets it has comes back as it is, so a writer that runs twice writes
    nothing the second time."""
    facts = stored(one)
    if facts is None:
        return one
    made = facts
    if row is not None and not {facts.row, row} <= APPROVED:
        made = replace(made, row=row)
    if pull is not None:
        made = replace(made, pull=pull)
    if made == facts:
        return one
    asked = made.question == Question.OPEN
    state = unforeseen(made) if made.seen and not asked else judge(made)
    if state.value == one["value"]:
        return {**one, "confirmed": state.confirmed, "facts": state.facts.said()}
    about = {name: value for name, value in one.items() if name not in _JUDGED}
    if "why" in about:
        about["why"] = ""
    role = "scout" if "scout" in one else ""
    scout = {"scout": str(scouting(state))} if role else {}
    return entry(state, holder(state, role=role), **about, **scout)


_JUDGED = frozenset({"value", "name", "who", "waits", "lane", "confirmed", "facts", "scout"})
SEEN = ("thread", "pr")
"""The columns of a row of the queue that its line of `work.json` carries as they are."""
PULLED = "pulled"
"""The field of a line that says when a run of `jmerge` last restated its `Pull` facet."""


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
    `Row` facet that `facet` gives the row, and its `SEEN` columns. A row the queue no longer has
    loses its line, and a row with no line yet gets one judged with nothing launched, written or
    open (`fresh`), which the next pass judges in full. Each write of the queue calls this under
    the queue's lock once it wrote (`queue._changing`), so the view shows a change of the queue at
    once."""
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
                seen = {name: row.get(name, "") for name in SEEN}
                if any(one.get(name) != value for name, value in seen.items()):
                    one = {**one, **seen}
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


def pulled(state_dir: Path, said: dict[int, Pull], at: str) -> None:
    """Restate the `Pull` facet of the line of each pull request that a run of `jmerge` judged,
    by its number, as `jmerge` judged it, and mark the line `PULLED` at `at`, when the run ended
    (`Said.at`). The pass and the
    merge tick both call this as their run of `jmerge` ends (`merge._sent`), so a verdict reaches
    the view at once. The pass keeps a facet that a run after its own restated (`kept`)."""
    if not said:
        return

    def change(lines: list[Any]) -> list[Any]:
        work = []
        for one in lines:
            number = str(one.get("pr", "")).removeprefix("#") if _is_row(one) else ""
            if number.isdigit() and int(number) in said:
                made = restate(one, pull=said[int(number)])
                if made is not one:
                    one = {**made, PULLED: at}
            work.append(one)
        return work

    _rewrite(state_dir, change)


def kept(one: dict[str, Any], was: dict[str, Any] | None, ran: str) -> dict[str, Any]:
    """Return the pass's line `one`, with the `Pull` facet of the file's line `was` where a run of
    `jmerge` that ended after `ran`, when the pass's own run ended, restated it: a merge tick's
    run judged later than the pass's own run, whose verdict the pass's line holds."""
    facts = stored(was) if was is not None and str(was.get(PULLED, "")) > ran else None
    if facts is None or was is None:
        return one
    return {**restate(one, pull=facts.pull), PULLED: was[PULLED]}


def drift(before: list[Any], after: list[Any]) -> list[tuple[str, str]]:
    """Return each row's line that the pass corrects and that a writer should have kept right, by
    key, with what was wrong in it: a line for a row the queue no longer has, no line for a row it
    has, a `Row` facet the queue gave otherwise (a move between `APPROVED` facets is the pass's to
    judge, as `restate` says), a `Pull` facet that a run of `jmerge` restated (`PULLED`) and that
    the pass, with GitHub's answer, judges otherwise for the same pull request, or a value that does
    not follow from the line's own facts, which no writer restates since its facts are right.

    The facets the pass alone sees, a thread's and what was written, and a pull request no run of
    `jmerge` restated on the line yet, are no drift. The writers run in the pass too, before it
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
        elif off := _off(old, new):
            found.append((key, ", ".join(off)))
    return found


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


def path(state_dir: Path) -> Path:
    return state_dir / NAME


def last(state_dir: Path) -> dict[str, str]:
    """Return the value that the last pass judged for each key of `work.json`."""
    kept = read(state_dir)
    return {
        one["key"]: one["value"]
        for one in (kept["work"] if kept else [])
        if isinstance(one, dict) and isinstance(one.get("key"), str) and one.get("value") in VALUES
    }


def write(state_dir: Path, at: str, answered: Answered, work: list[dict[str, Any]]) -> None:
    """Write the whole file. The caller holds `LOCK`, so no act's `update` falls between."""
    write_json(path(state_dir), {"at": at, "answered": str(answered), "work": work})


def read(state_dir: Path) -> dict[str, Any] | None:
    kept = read_json(path(state_dir), None)
    return kept if isinstance(kept, dict) and isinstance(kept.get("work"), list) else None
