"""This module is an exhaustive check of main.json's red-main contract. It walks every order of
merges, check answers and jbus passes within the bounds below, breadth first. The
model runs the real `jbus.mainmoved.tell` as jbus's step and the real `jmerge.mainjson.read` as what
its readers read. A red main holds no pull request ("Main is not red" in
`features/jmerge/docs/jmerge.md`), so any merge may land at any time, but `jmerge.cli.Repo.again`
and `jbus.watch` still read the record, and each property below is about what they read:

- **S1, a known red is read as red.** Take the newest tip whose check has settled
  (`mainjson.SETTLED`: `green` or `failed`). If that check failed, `read` names a red tip. The harm
  when it breaks: jmerge asks GitHub to merge a red main into each red pull request, and each one
  goes red again, a CI round spent for nothing.
- **S2, no stuck red.** When `read` names a tip, neither that tip nor any tip that landed after it
  has a `green` check. The harm when it breaks: every pull request red over the old red stays red
  after a fix has made main green, and is never judged again.
- **S3, the red tip's own tests.** When the record keeps `failed` beside `broken`, those are the
  tests that failed at that tip. The harm when it breaks: `jbus.reverts` judges a red tip by another
  tip's tests, and a flake's revert or a culprit's escape is a wrong one.

The model has at most `TIPS` tips on main and at most `EVENTS` events. The first tip, M0, is green
and is there from the start. `tell` tells no crew anything, so no open pull request changes what it
writes.

Each kind of step matches the code as follows:

- **pass**: one run of `tell` under the pass lock (`fcntl.flock` in
  `features/jbus/src/jbus/poll.py`). No two passes overlap, so a pass is one indivisible step. A
  merge may come between any two passes, including the one a pass itself runs before `tell`, in the
  `after-expedite` slot (`features/jbus/src/jbus/mainmoved.py`). A reader always reads a whole
  record, never a half-written one, because `write_json` writes a temporary file and `os.replace`s
  it (`write_json` in `features/jbus/src/jbus/__init__.py`).
- **lands**: a merge, by jmerge, by hand or by `--accept`. No read of the record stops one.
- **settles**: a pending tip's check ends with one of the answers of `watch._check`
  (`features/jbus/src/jbus/watch.py`): `green`, `failed`, `cancelled` (a later attempt that
  was cancelled too), `refused` (a run GitHub did not start again), `nojob` (each failed check
  run's job ran no step, `watch.NO_JOB`) or `batched` (a newer push displaced its run before it
  had a job, `watch.BATCHED`). `main_check` asks without `again`
  (`features/jbus/src/jbus/mainmoved.py`). So `cancelled` and `refused` reach `tell` only
  through `checks.json`, where watch's retro writes them (`_check(..., again=True)`). No `settles`
  event reaches a tip whose check never ends, and that tip stays `pending`. A failed push run at
  main's tip is rerun once (`main_check(..., rerun=True)`), and the tip is `pending` until the
  rerun ends: `failed` here is the answer once the rerun failed too, or one that ran no rerun.
- **rerun passes**: the newest tip's check failed, and a rerun of that check on the same tip passes
  with no new commit. From then on, that tip's check is `green`.

The model stubs these, and only these. `mainmoved.main_check` returns the tip's check from the
model, where the real one would ask GitHub. `mainmoved.failed_at` returns the one test that failed
at a red tip (`failing`), where the real one reads the red run's logs. GitHub's list of main's
commits is the model's tips, each the first parent of the next. `account` raises and closes no
gate. `Pass` is a fake with only what `tell` reads. `main.json` is a real file in a temporary state
directory, and the real code writes it.

The model does not cover a record written before `tell` stopped telling crews (`fixed` and `held`
in `main.json`), a remote that cannot be read, `checks.json`'s cache, `jbus.reverts`'s own
rule (`features/jbus/tests/test_jbus_reverts.py`), or more tips or events than the bounds allow. A
walk that passes proves the model within the bounds, not the whole system.

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

from jbus import mainmoved
from jmerge import mainjson

RULE = "features/jmerge/docs/jmerge.md"
TIPS = 4
EVENTS = 10
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
SETTLES = ("green", "failed", "cancelled", "refused", "nojob", "batched")
TEST_FILE = "features/m/tests/test_m.py"


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
    once the last tip's check has settled and a pass has run since."""

    one_at_a_time: bool = False


@dataclass(frozen=True)
class State:
    """`State` is the model's state between two steps. It holds each tip's check, the record
    `tell` keeps, and whether a pass has run since the newest tip settled. Only `one_at_a_time`
    reads `looked`."""

    checks: tuple[str, ...]
    record: str
    looked: bool

    def key(self) -> str:
        return json.dumps([self.checks, self.record, self.looked])


class Asked:
    def __init__(self, stdout: str) -> None:
        self.stdout, self.returncode = stdout, 0


@dataclass
class FakePass:
    """`FakePass` has what `tell` reads of a `jbus.passes.Pass`, over the state of the model:
    `main` is main's tip, as `Pass.tip` gives it, and `answers` what GitHub answered this
    pass, as `Pass.answers` keeps it."""

    state: Path
    checks: dict[str, str]
    main: str
    now: datetime = NOW
    answers: dict[str, Any] = field(default_factory=dict)

    def tip(self) -> str:
        return self.main

    def run(self, *command: str) -> Asked:
        if command[:2] == ("git", "symbolic-ref"):
            return Asked("origin/main\n")
        if command[:2] == ("gh", "api"):
            landed = range(len(self.checks))
            commits = [
                {"sha": sha(n), "parents": [{"sha": sha(n - 1)}] if n else []} for n in landed
            ]
            head = "HTTP/2.0 200 OK\r\n\r\n" if "-i" in command else ""
            return Asked(head + json.dumps(commits[::-1]))
        return Asked(f"{self.main}\trefs/heads/main\n")


@contextmanager
def stubbed() -> Iterator[None]:
    """Put in the four stubs and nothing else: GitHub's two answers, an `account` that raises
    no gate, and an `fsync` that returns at once. A walk
    writes some 14,000 files, and each `fsync` waits behind every other writer of the
    filesystem: in full suites run side by side a walk took 20 to 42 s instead of 2, and 49 s
    beside twelve writers of `/tmp`, against the test's bound of 120 s. The walk checks what
    `tell` writes, not that it reaches the disk."""
    with (
        mock.patch("os.fsync", lambda fd: None),
        mock.patch.object(mainmoved, "main_check", lambda run, at, **_: run.checks[at]),
        mock.patch.object(mainmoved, "failed_at", lambda run, at: [failing(int(at[0]))]),
        mock.patch.object(mainmoved, "account", lambda run, unrun, passed: None),
    ):
        yield


class Files:
    """`Files` is the model's state directory, with `main.json` as a state has it."""

    def __init__(self, root: Path) -> None:
        self.state = root

    def put(self, state: State) -> None:
        path = self.state / mainjson.NAME
        if state.record:
            path.write_text(state.record)
        else:
            path.unlink(missing_ok=True)

    def red(self, state: State) -> str:
        """Return the red tip its readers read, `mainjson.read(state).red`."""
        self.put(state)
        return mainjson.read(self.state).red

    def tell(self, state: State) -> State:
        """Run one pass, the real `tell` over the state's file."""
        self.put(state)
        checks = {sha(tip): check for tip, check in enumerate(state.checks)}
        run = FakePass(self.state, checks, sha(len(state.checks) - 1))
        mainmoved.tell(run)  # type: ignore[arg-type]
        path = self.state / mainjson.NAME
        record = path.read_text() if path.exists() else ""
        return State(state.checks, record, state.checks[-1] != "pending")


def failing(tip: int) -> str:
    """Return the test that failed at a tip whose check failed, as the red run's log names it."""
    return f"{TEST_FILE}::test_M{tip}"


def s1(state: State, files: Files) -> bool:
    """Return whether S1 holds on the state that a pass leaves: a known red main is read as red."""
    settled = [tip for tip, check in enumerate(state.checks) if check in mainjson.SETTLED]
    return not settled or state.checks[settled[-1]] != "failed" or files.red(state) != ""


def s2(state: State, files: Files) -> bool:
    """Return whether S2 holds on the state that a pass leaves."""
    red = files.red(state)
    if not red:
        return True
    tip = next(tip for tip in range(len(state.checks)) if sha(tip) == red)
    return "green" not in state.checks[tip:]


def s3(state: State, files: Files) -> bool:
    """Return whether S3 holds on the state that a pass leaves: the tests kept beside `broken` are
    that tip's own."""
    record = json.loads(state.record) if state.record else {}
    broken, failed = record.get("broken"), record.get("failed")
    return not broken or failed is None or failed == [failing(int(broken[0]))]


PROPERTIES = {"S1": s1, "S2": s2, "S3": s3}


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
        after = State((*state.checks, "pending"), state.record, False)
        yield Step("merge", f"M{landed} lands: a merge", after)
    for tip, check in enumerate(state.checks):
        if check != "pending":
            continue
        for answer in SETTLES:
            checks = (*state.checks[:tip], answer, *state.checks[tip + 1 :])
            looked = state.looked and tip != landed - 1
            after = State(checks, state.record, looked)
            yield Step(f"settles {answer}", f"M{tip}'s check settles: {answer}", after)
    if state.checks[-1] == "failed":
        after = State((*state.checks[:-1], "green"), state.record, False)
        yield Step("rerun passes", f"M{landed - 1}'s check is rerun and passes", after)
    after = files.tell(state)
    main = mainjson.read(files.state)
    written = {key: value for key, value in json.loads(after.record).items() if key != "at"}
    record = name(json.dumps(written, sort_keys=True))
    line = (
        f"pass: tell writes main.json {record}; "
        f"mainjson reads red={name(main.red) or '-'} green={name(main.green) or '-'}"
    )
    yield Step("pass", line, after, passed=True)


@dataclass
class Found:
    """`Found` is what a walk found: the states it reached and, for each property, the states
    that break that property, with the shortest trace to the first of those states."""

    options: Options
    states: int = 0
    broken: dict[str, int] = field(default_factory=lambda: dict.fromkeys(PROPERTIES, 0))
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


def start() -> State:
    return State(("green",), "", True)


@cache
def walk(options: Options) -> Found:
    """Return every state within the bounds, reached breadth first, each state once."""
    began = time.monotonic()
    found = Found(options)
    with tempfile.TemporaryDirectory() as root, stubbed():
        files = Files(Path(root))
        parents: dict[str, tuple[str | None, str]] = {}
        todo: deque[tuple[State, int]] = deque()
        first = start()
        parents[first.key()] = (None, "start: M0 is green, no main.json")
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
    for options in (Options(), Options(one_at_a_time=True)):
        found = walk(options)
        print(f"{options}: {found.states} states in {found.seconds:.1f} s")
        for prop in PROPERTIES:
            print(found.report(prop) if prop in found.traces else f"{prop} holds")
    sys.exit(0)
