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
  reason names (`merge.step`), or `other` for a reason that no rule names.
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
state, so every reader of the queue still finds the same words as before. `write` keeps
every state of a pass, whole, in `work.json` in the project's state directory, and the view
draws that file.
"""

from __future__ import annotations

import functools
import itertools
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from jbus import read_json, roles, write_json

NAME = "work.json"
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
    for values in itertools.product(*FACETS.values()):
        yield Facts(*values)


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


AT_WORK = (Thread.STARTING, Thread.MOVING, Thread.QUIET)


@dataclass(frozen=True)
class Holder:
    """A `Holder` names who holds a state, the one thing it waits for, and the lane on which
    the view draws it."""

    who: str
    waits: str
    lane: str


def holder(state: State, role: str = "", home: bool = False, after: bool = False) -> Holder:
    """Return who holds a state, which is its pattern's holder except in three cases.

    `role` is the role of a thread that belongs to no row. When such a thread is at work, the
    holder is that role, not a crewmate, and the state is on no lane of the line. A leftover or
    a closed pull request is the user's, with two exceptions. When `leftover.json` says that the
    pull request's home has it (`home`), the home holds the state. When a merged pull request's
    `Left:` line is for after the merge (`after`) and a thread is at work on it, the crewmate
    holds the state. Either holder is on the lane of work that is running.

    A role's holder is in `roles.ROLES`.
    """
    pattern = state.pattern
    if role:
        if pattern.who != "crew":
            return Holder(state.who, state.waits, "")
        waits = "its thread" if state.waits == "its crewmate" else state.waits
        held = next((one.holder for one in roles.ROLES if one.name == role), roles.OTHER)
        return Holder(held, waits, "")
    if state.value not in ("leftover", "closed"):
        return Holder(state.who, state.waits, pattern.lane)
    merged = state.facts.pull == Pull.MERGED
    if after and merged and state.value == "leftover" and state.facts.thread in AT_WORK:
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
    write_json(path(state_dir), {"at": at, "answered": str(answered), "work": work})


def read(state_dir: Path) -> dict[str, Any] | None:
    kept = read_json(path(state_dir), None)
    return kept if isinstance(kept, dict) and isinstance(kept.get("work"), list) else None
