"""This module is an exhaustive check of main.json's red-main contract. It walks every order of
merges, check answers, T3 Code answers and jbus passes within the bounds below, breadth first. The
model runs the real `jbus.mainmoved.tell` as jbus's step and the real `jmerge.rows.red` as jmerge's
read.

The model checks two properties on the record after every pass. Both come from the rule "Main is not
red" in `features/jmerge/docs/jmerge.md`:

- **S1, no merge onto a known red main.** Take the newest tip whose check has settled
  (`mainjson.SETTLED`: `green` or `failed`). If that check failed, `rows.red` is not empty for a
  slug that is not a fix. The harm when it breaks: jmerge merges pull requests onto a main whose
  check failed, so each one lands on a base whose check failed, and so does every merge after it.
- **S2, no stuck red.** When `rows.red` names a tip, neither that tip nor any tip that landed after
  it has a `green` check. The harm when it breaks: jmerge holds every pull request as "main is red"
  after a fix has made main green, and the queue stops until somebody looks.

The model has at most `TIPS` tips on main, at most `EVENTS` events, and zero or one open red pull
request that jbus launched (`alpha`). The first tip, M0, is green and is there from the start.

Each kind of step matches the code as follows:

- **pass**: one run of `tell` under the pass lock (`features/jbus/src/jbus/cli.py:215-219`). No two
  passes overlap, so a pass is one indivisible step. In a pass, jmerge reads `main.json` before
  `tell` writes it: `features/jbus/src/jbus/cli.py:146` runs `merge.merge`, and `tell` runs later,
  in the `after-expedite` slot (`features/jbus/src/jbus/mainmoved.py:229-237`). So the model writes
  a merge in a pass as the event `lands, jmerge merges` followed by the event `pass`. That merge
  reads the record the last pass wrote, as a merge between passes does.
- **lands, jmerge merges**: a home's own `jmerge`, or the one a pass runs, merges `beta`. This event
  may come between any two passes. The merge always reads a whole record, never a half-written one,
  because `write_json` writes a temporary file and `os.replace`s it
  (`features/jbus/src/jbus/__init__.py:434-444`). The model allows it only where
  `rows.red(mainjson.read(state), "beta")` is empty (`features/jmerge/src/jmerge/rows.py:84-87`).
- **lands, another merge**: a merge that does not ask `rows.red`, such as the fix
  `main-red-<sha12>`, a merge by hand, or `--accept`. The model always allows it.
- **settles**: a pending tip's check ends with one of the answers of `watch._check`
  (`features/jbus/src/jbus/watch.py:797-828`): `green`, `failed`, `cancelled` (a later attempt that
  was cancelled too) or `refused` (a run GitHub did not start again). `main_check` asks without
  `again` (`features/jbus/src/jbus/mainmoved.py:77-86`). So the last two answers reach `tell` only
  through `checks.json`, where watch's retro writes them (`_check(..., again=True)`). No `settles`
  event reaches a tip whose check never ends, and that tip stays `pending`.
- **rerun passes**: the newest tip's check failed, and a rerun of that check on the same tip passes
  with no new commit. From then on, that tip's check is `green`.
- Each pass also chooses T3 Code's answer to a send. T3 Code answers it, loses it (`T3Error`,
  `features/jbus/src/jbus/mainmoved.py:201-204`) or refuses it (`T3Refused`, 196-200).

The model stubs these, and only these. `mainmoved.main_check` returns the tip's check from the
model, where the real one would ask GitHub. GitHub's list of main's commits is the model's tips,
each the first parent of the next. `dispatch.launched` says that jbus launched `alpha`, and
`dispatch.thread_of` gives its thread. `rebase.held` holds back no message, because the crew's turn
has ended. `Pass`, `Client` and `World` are fakes with only what `tell` reads. `sent.json` and
`main.json` are real files in a temporary state directory, and the real code writes them.

The model does not cover a message `rebase.held` keeps back (`held` in `main.json`), a pull request
that conflicts or that GitHub has not judged, more than one open pull request, a red pull request
with no thread (a gate), a remote that cannot be read, `checks.json`'s cache, or more tips or events
than the bounds allow. A walk that passes proves the model within the bounds, not the whole system.

Run it as `uv run pytest features/jbus/tests/test_main_red_model.py -q`, or add `--runxfail` to
print the traces of the findings. `uv run python features/jbus/tests/main_red_model.py` prints every
trace.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any
from unittest import mock

from jbus import dispatch, mainmoved, read_json, rebase, write_json
from jbus.t3 import T3Error, T3Refused
from jbus.watch import World
from jmerge import mainjson, rows

RULE = "features/jmerge/docs/jmerge.md"
TIPS = 4
EVENTS = 10
MERGED = "beta"
RED_PR = "alpha"
THREAD = "mcp:thread-1"
HEAD = "c" * 40
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
SETTLES = ("green", "failed", "cancelled", "refused")
ANSWERS, LOSES, REFUSES = "answers", "loses the send", "refuses the send"


def sha(tip: int) -> str:
    return str(tip) * 40


def name(text: str) -> str:
    """Return a record or a line with each tip's commit written as its name, `M<n>`."""
    for tip in range(TIPS):
        text = text.replace(sha(tip), f"M{tip}").replace(sha(tip)[: mainjson.SHA], f"M{tip}")
    return text


@dataclass(frozen=True)
class Options:
    """`Options` says which environments the walk covers. With `one_at_a_time`, a tip lands only
    once the last tip's check has settled and a pass has run since. `lost_sends` lets T3 Code
    lose a send."""

    one_at_a_time: bool = False
    lost_sends: bool = True


@dataclass(frozen=True)
class State:
    """`State` is the model's state between two steps. It holds each tip's check, the two files
    `tell` keeps, whether the red pull request is open, and whether a pass has run since the
    newest tip settled. A pass sets `looked` even when it still owes a send because T3 Code lost
    one. So with `one_at_a_time`, a tip may land after such a pass. Only `one_at_a_time` reads
    `looked`."""

    checks: tuple[str, ...]
    record: str
    sent: str
    pull: bool
    looked: bool

    def key(self) -> str:
        return json.dumps([self.checks, self.record, self.sent, self.pull, self.looked])


@dataclass
class Box:
    state: Path

    def mark(self, key: str) -> None:
        sent = read_json(self.state / "sent.json", [])
        if key not in sent:
            write_json(self.state / "sent.json", [*sent, key])


class Asked:
    def __init__(self, stdout: str) -> None:
        self.stdout, self.returncode = stdout, 0


@dataclass
class FakePass:
    """`FakePass` has what `tell` reads of a `jbus.passes.Pass`, over the state of the model."""

    state: Path
    checks: dict[str, str]
    tip: str
    now: datetime = NOW
    told: set[str] = field(default_factory=set)
    said: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.home = self.state / "home"
        self.box = Box(self.state)

    def run(self, *command: str) -> Asked:
        if command[:2] == ("git", "symbolic-ref"):
            return Asked("origin/main\n")
        if command[:2] == ("gh", "api"):
            landed = range(len(self.checks))
            commits = [
                {"sha": sha(n), "parents": [{"sha": sha(n - 1)}] if n else []} for n in landed
            ]
            return Asked(json.dumps(commits[::-1]))
        return Asked(f"{self.tip}\trefs/heads/main\n")

    def gate(self, slug: str, what: str, text: str = "", *, key: str = "") -> None:
        self.said.append(f"gate {slug}: {what}")

    def find(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def say(self, line: str) -> None:
        self.said.append(line)


class FakeClient:
    def __init__(self, answer: str) -> None:
        self.answer, self.recipients, self.calls = answer, frozenset(), 0

    def call(self, tool: str, given: dict[str, Any]) -> Any:
        self.calls += 1
        if self.answer == LOSES:
            raise T3Error("the reply was lost")
        if self.answer == REFUSES:
            raise T3Refused("no")
        return {}


def red_pull() -> dict[str, Any]:
    failed = [{"status": "COMPLETED", "conclusion": "FAILURE"}]
    return {"number": 7, "headRefOid": HEAD, "mergeable": "MERGEABLE", "statusCheckRollup": failed}


@contextmanager
def stubbed() -> Iterator[None]:
    """Put in the four stubs and nothing else: GitHub's answer, the launch record, the brief's
    thread, and a crew whose turn has ended."""
    with (
        mock.patch.object(mainmoved, "main_check", lambda run, at, again=False: run.checks[at]),
        mock.patch.object(dispatch, "launched", lambda run, slug: THREAD if slug == RED_PR else ""),
        mock.patch.object(dispatch, "thread_of", lambda brief: THREAD),
        mock.patch.object(rebase, "held", lambda *args: False),
    ):
        yield


class Files:
    """`Files` is the model's state directory, with `main.json` and `sent.json` as a state has
    them."""

    def __init__(self, root: Path) -> None:
        self.state = root

    def put(self, state: State) -> None:
        path = self.state / mainjson.NAME
        if state.record:
            path.write_text(state.record)
        else:
            path.unlink(missing_ok=True)
        (self.state / "sent.json").write_text(state.sent)

    def red(self, state: State) -> str:
        """Return jmerge's read, `rows.red(mainjson.read(state), slug)`, for a slug that is no
        fix."""
        self.put(state)
        return rows.red(mainjson.read(self.state), MERGED)

    def tell(self, state: State, answer: str) -> tuple[State, bool]:
        """Run one pass, the real `tell` over the state's files. Also return whether a send went
        out."""
        self.put(state)
        checks = {sha(tip): check for tip, check in enumerate(state.checks)}
        run = FakePass(self.state, checks, sha(len(state.checks) - 1))
        client = FakeClient(answer)
        world = World(open={RED_PR: red_pull()} if state.pull else {})
        mainmoved.tell(run, client, world)  # type: ignore[arg-type]
        path = self.state / mainjson.NAME
        record = path.read_text() if path.exists() else ""
        sent = (self.state / "sent.json").read_text()
        looked = state.checks[-1] != "pending"
        return State(state.checks, record, sent, state.pull, looked), client.calls > 0


def s1(state: State, files: Files) -> bool:
    """Return whether S1 holds on the state that a pass leaves."""
    settled = [check for check in state.checks if check in mainjson.SETTLED]
    return not settled or settled[-1] != "failed" or files.red(state) != ""


def s2(state: State, files: Files) -> bool:
    """Return whether S2 holds on the state that a pass leaves."""
    if not files.red(state):
        return True
    red = mainjson.read(files.state).red
    tip = next(tip for tip in range(len(state.checks)) if sha(tip) == red)
    return "green" not in state.checks[tip:]


PROPERTIES = {"S1": s1, "S2": s2}


@dataclass(frozen=True)
class Step:
    """A `Step` is one event. It has its sort, its words in a trace, the state after it, and
    whether it was a pass. The walk checks the properties after each pass."""

    kind: str
    line: str
    after: State
    passed: bool = False


def steps(state: State, files: Files, options: Options) -> Iterator[Step]:
    """Yield each event that the state allows."""
    landed = len(state.checks)
    ready = not options.one_at_a_time or (state.checks[-1] != "pending" and state.looked)
    if landed < TIPS and ready:
        after = State((*state.checks, "pending"), state.record, state.sent, state.pull, False)
        held = files.red(state)
        if not held:
            yield Step("jmerge merges", f"M{landed} lands: jmerge merges {MERGED}", after)
        else:
            yield Step("jmerge holds", f"jmerge holds {MERGED}: {held}", state)
        yield Step("another merge", f"M{landed} lands: another merge (the fix, or by hand)", after)
    for tip, check in enumerate(state.checks):
        if check != "pending":
            continue
        for answer in SETTLES:
            checks = (*state.checks[:tip], answer, *state.checks[tip + 1 :])
            looked = state.looked and tip != landed - 1
            after = State(checks, state.record, state.sent, state.pull, looked)
            yield Step(f"settles {answer}", f"M{tip}'s check settles: {answer}", after)
    if state.checks[-1] == "failed":
        after = State((*state.checks[:-1], "green"), state.record, state.sent, state.pull, False)
        yield Step("rerun passes", f"M{landed - 1}'s check is rerun and passes", after)
    answers = (ANSWERS, LOSES, REFUSES) if options.lost_sends else (ANSWERS, REFUSES)
    for answer in answers:
        after, sent = files.tell(state, answer)
        main = mainjson.read(files.state)
        written = {key: value for key, value in json.loads(after.record).items() if key != "at"}
        record = name(json.dumps(written, sort_keys=True))
        words = f"T3 Code {answer}" if sent else "no send"
        line = (
            f"pass ({words}): tell writes main.json {record}; "
            f"mainjson reads red={name(main.red) or '-'} green={name(main.green) or '-'}"
        )
        yield Step(words, line, after, passed=True)
        if not sent:
            break


@dataclass
class Found:
    """`Found` is what a walk found: the states it reached and, for each property, the states
    that break that property, with the shortest trace to the first of those states."""

    options: Options
    states: int = 0
    broken: dict[str, int] = field(default_factory=lambda: {prop: 0 for prop in PROPERTIES})
    traces: dict[str, list[str]] = field(default_factory=dict)
    events: set[str] = field(default_factory=set)
    seconds: float = 0.0

    def report(self, prop: str) -> str:
        lines = [
            f"{prop} breaks in {self.broken[prop]} of {self.states} states ({self.options}), "
            f'against "Main is not red" in {RULE}'
        ]
        lines += [f"  {step}. {line}" for step, line in enumerate(self.traces[prop], 1)]
        return "\n".join(lines)


def start(pull: bool) -> State:
    return State(("green",), "", "[]", pull, True)


@cache
def walk(options: Options) -> Found:
    """Return every state within the bounds, reached breadth first, each state once."""
    began = time.monotonic()
    found = Found(options)
    with tempfile.TemporaryDirectory() as root, stubbed():
        files = Files(Path(root))
        parents: dict[str, tuple[str | None, str]] = {}
        todo: deque[tuple[State, int]] = deque()
        for pull in (False, True):
            first = start(pull)
            line = f"start: M0 is green, no main.json, {'one' if pull else 'no'} red pull request"
            parents[first.key()] = (None, line)
            todo.append((first, 0))
        while todo:
            state, depth = todo.popleft()
            if depth == EVENTS:
                continue
            for step in steps(state, files, options):
                found.events.add(step.kind)
                key = step.after.key()
                if key in parents:
                    continue
                parents[key] = (state.key(), step.line)
                todo.append((step.after, depth + 1))
                if not step.passed:
                    continue
                for prop, holds in PROPERTIES.items():
                    if holds(step.after, files):
                        continue
                    found.broken[prop] += 1
                    if prop not in found.traces:
                        found.traces[prop] = trace(parents, key)
        found.states = len(parents)
    found.seconds = time.monotonic() - began
    return found


def trace(parents: dict[str, tuple[str | None, str]], key: str | None) -> list[str]:
    """Return the lines from a start to the state `key`. Each state keeps its parent and the line
    of the step to it. A start keeps no parent, and keeps its own start line instead."""
    lines = []
    while key is not None:
        key, line = parents[key]
        lines.append(line)
    return lines[::-1]


if __name__ == "__main__":
    for options in (
        Options(),
        Options(one_at_a_time=True),
        Options(lost_sends=False),
        Options(one_at_a_time=True, lost_sends=False),
    ):
        found = walk(options)
        print(f"{options}: {found.states} states in {found.seconds:.1f} s")
        for prop in PROPERTIES:
            print(found.report(prop) if prop in found.traces else f"{prop} holds")
    sys.exit(0)
