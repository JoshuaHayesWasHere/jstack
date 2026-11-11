"""The fast guards on a pull request's tree merged over today's base, run before `jmerge` merges
it on its existing check.

Two pull requests can each pass their check alone and break the base together, as #923 and #935
did on 2026-11-03 with two `v007_` migrations. The clash shows on their merged tree. So before a
merge, `jmerge` merges the head over the base's tip with `git merge-tree`, makes it a local
commit whose parents are the tip and the head (as GitHub's merge ref is), pushes nothing, checks
it out in a worktree of its own, and runs the command the state's `merged-tree-guards` file names
there, with `BASE` set to the tip and `MERGE_BASE` to the merge base of the head and the tip.
jstack's names `make check-fast PART=guards`, the lint and the guard tests: the cross-cutting
tests, the catch-all, the changed test files, and the test files of the selection that main
changed or added since the merge base, which the pull request's check, run over it, never saw.
They run inside a full test slot (`run_guards`), and a run that finds none free for
`SLOT_SECONDS` leaves the pull request to the next run.

The guards run only on a tree no green check covers. A repo with no such file runs no guards. A
head that holds the tip already is the tree its check ran on, so nothing is built for it. A merged
tree that a successful check of this repo already tested over the same tip runs nothing either:
CI's check runs a superset of the guards, plus the lint, on GitHub's merge of the head over the
tip, and leaves an artifact named by the two trees (`green.checked`), so the guards would only run
a part of that pass again (58 of 97 guard runs from 2026-11-06 to 11-08).

A pass, a failure, or a stop at the time limit of the guards on a head over a tip is kept in
`merged-trees.json`, so a held pull request is not run again until its head or the tip moves. A
stopped tree is kept too, since running it again on the next run spends that run's time on the
same tree and leaves every other pull request waiting (#1103 on 2026-11-05).
A hold names one guard; its record keeps the last `TAIL` lines the guards printed, which say why.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jgauge import slot
from jmerge import green, ready
from jsettings import store

NAME = "merged-tree-guards"
KEPT = "merged-trees.json"
TREE = "merged-tree"
LIMIT_SECONDS = 600
"""How long the guards may run on one tree before they are stopped, from when they hold a slot."""
SLOT_SECONDS = 15
"""How long the guards wait for a full test slot before the pull request waits for the next run,
which jbus's next pass makes about a minute later (`jbus.tick` runs `jmerge` sooner only when a
check ends): a skip costs a merge about a minute, where a wait in the run would hold every other
merge of it for as long as a full suite holds a slot."""
LOOK_SECONDS = 0.2
RUN_SECONDS = 240
"""The seconds of guards a run may spend before it starts no more: with one more at its limit, a
run stays under the 17 minutes jbus gives `jmerge` (`jbus.wake.JMERGE_TIMEOUT`)."""
UNNAMED = "its guards"
SHA = 12
PASSED = "the guards passed on its tree merged over {base} at {tip} in {seconds} s"
CHECKED = "CI's check passed its tree merged over {base} at {tip} in {run}, so no guards ran"
_IDENTITY = ("-c", "user.name=jmerge", "-c", "user.email=jmerge@localhost")
TAIL = 40
"""The lines of what failed or stopped guards printed that their record keeps."""
PASSED_ON = ("HOME", "USER", "LOGNAME", "LANG", "PATH")
"""The caller's variables the guards see, with their `BASE`, `MERGE_BASE` and their slot's
(`SLOT`): the machine's login, as a desk's shell and CI give it. jbus.service gives `jmerge` its
unit's variables and systemd its own, and a guard test that reads one fails on the merged tree
alone: `JBUS_TICK_TIMER` held #1283, and `INVOCATION_ID` failed #1159's check under a user unit."""
SLOT = (slot.HELD, "TMPDIR", "JGAUGE_LOCKS_DIR", "TEST_SLOTS", "TMPFS")
"""The variables of the test slot the guards run in: the one `jgauge test-slot` gives them, or
the caller holds, and the machine's slots, which a suite the guards start takes from."""


@dataclass(frozen=True)
class Ran:
    """What the guards did: their exit code, None where they were stopped at their time limit,
    the whole seconds they took once they held a slot, what they printed, and the whole seconds
    they waited for the slot."""

    code: int | None
    seconds: int
    said: str
    waited: int = 0


PASSES = "passed"
FAILS = "failed"
STOPPED = "stopped"
NO_SLOT = "no slot"
UNRUN = ("no time", "unbuilt")
"""What `Guards.on_batch` says where it ran no guards: the run spent `RUN_SECONDS`, or the
worktree could not be made. Neither is evidence against a member."""


@dataclass(frozen=True)
class Tried:
    """What the guards did on a batch's tree: `PASSES`, `FAILS`, `STOPPED`, `NO_SLOT`, or one of
    `UNRUN` with why; and the whole seconds they took in their slot, or waited for none."""

    outcome: str
    seconds: int
    why: str = ""


def guard(said: str) -> str:
    """The guard that failed, as the output names it: the first test pytest calls FAILED, else
    the first target make stopped in (the innermost, as make prints it first), else the last
    line printed."""
    lines = [line.strip() for line in said.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("FAILED "):
            return line.split()[1]
    for line in lines:
        if "*** [" in line and "]" in line:
            target = line.split("*** [", 1)[1].split("]", 1)[0]
            return target.rsplit(": ", 1)[-1]
    return lines[-1][:120] if lines else UNNAMED


def run_guards(command: str, cwd: Path, env: dict[str, str], timeout: float) -> Ran | str | None:
    """Run `command` in `cwd` inside a full test slot, in a session of its own, so a stop at
    `timeout` stops the processes it started too, which would outlive `sh` and hold the tree.
    The session also ends with this process, however it ends: `_TIED` reads a pipe only this
    process writes to, and stops the session at its end. jbus kills `jmerge` alone at its
    `JMERGE_TIMEOUT`, and the guards would otherwise run on beside the next `jmerge`. The
    worktree such a stop leaves is the next run's to clear (`Guards.in_tree`).

    The guards are a suite at `-n 6`, so they take a slot as every other suite on the machine
    does: through `jgauge test-slot`, or the caller's own where it holds one already
    (`JGAUGE_TEST_SLOT` set), since a second would wait on its own. `timeout` and the seconds
    of the `Ran` count from the slot, not the wait for it. The wait is at most `SLOT_SECONDS`:
    with every slot still taken it returns None, and a slot taken, why the guards did not start
    where `jgauge test-slot` ended before they did.

    `sh` runs it as a login shell, so the guards see the machine's PATH as a desk's shell and CI
    do, after the few entries jbus's unit gives `jmerge`: Arch keeps `shasum` in
    /usr/bin/core_perl, which only /etc/profile adds. Of the caller's environment they see only
    `PASSED_ON` and `SLOT`, with `env` over them."""
    with (
        tempfile.TemporaryDirectory(prefix="jmerge-slot-") as scratch,
        contextlib.ExitStack() as held,
    ):
        started = Path(scratch) / "started"
        argv = ["sh", "-lc", command]
        if not os.environ.get(slot.HELD):
            argv = [sys.executable, "-m", "jgauge", "test-slot", "--", "sh", "-c", _MARK]
            argv += [str(started), command]
        alive, tie = os.pipe()
        held.callback(os.close, tie)
        with open(alive, "rb") as reading:
            process = subprocess.Popen(
                ["sh", "-c", _TIED, "sh", *argv],
                cwd=cwd,
                env={
                    **{name: os.environ[name] for name in PASSED_ON + SLOT if name in os.environ},
                    **env,
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=reading,
                text=True,
                start_new_session=True,
            )
        try:
            asked = time.monotonic()
            if argv[0] == sys.executable and not _slotted(process, started):
                _stop(process.pid)
                said, _ = process.communicate()
                if process.returncode < 0:
                    return None
                lines = (said or "").strip().splitlines()
                return lines[-1] if lines else f"jgauge test-slot exited {process.returncode}"
            began = time.monotonic()
            code: int | None
            try:
                said, _ = process.communicate(timeout=timeout)
                code = process.returncode
            except subprocess.TimeoutExpired:
                _stop(process.pid)
                said, _ = process.communicate()
                code = None
        finally:
            _stop(process.pid)
    return Ran(code, round(time.monotonic() - began), said or "", round(began - asked))


_TIED = (
    "exec 3<&0; { cat <&3 > /dev/null; kill -s KILL 0; } < /dev/null > /dev/null 2>&1 & "
    'exec 3<&-; exec "$@" < /dev/null'
)
"""What the session runs first: a watcher that kills the session's group once its stdin, the
pipe `run_guards` holds open, ends, and in its place the guards, with nothing to read."""
_MARK = ': > "$0" && exec sh -lc "$1"'
"""What runs inside the slot: it marks that the slot is held, then becomes the guards."""


def _slotted(process: subprocess.Popen, started: Path) -> bool:
    """Wait until the guards start inside their slot, and say whether they did within
    `SLOT_SECONDS`. A `jgauge test-slot` that ends first did not start them."""
    until = time.monotonic() + SLOT_SECONDS
    while not started.exists():
        if process.poll() is not None or time.monotonic() >= until:
            return started.exists()
        time.sleep(LOOK_SECONDS)
    return True


def _stop(group: int) -> None:
    """Kill the group. A group already gone gives ESRCH on Linux, and EPERM on Darwin once it
    holds only zombies, as it does after the stop at the time limit, when `finally` stops it
    again."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(group, signal.SIGKILL)


def command_of(state: Path) -> str:
    """The first line of the state's `merged-tree-guards` that is not blank, or nothing."""
    try:
        text = (state / NAME).read_text(encoding="utf-8")
    except OSError:
        return ""
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    lines = (ran.stderr or ran.stdout).strip().splitlines()
    return lines[-1] if lines else f"git exited {ran.returncode}"


class Guards:
    """The guards of one `jmerge` run, and the record of what they said of each pull request's
    head over a tip (`KEPT`). `run` is False for `--check`, which runs no guards and keeps
    nothing, but reads what a run kept. `ask` answers a GitHub API path of this repo, as
    `green.green_run` asks it."""

    def __init__(self, main: Path, state: Path, run: bool, ask: green.Ask) -> None:
        self.main = main
        self.state = state
        self.ask = ask
        self.path = state / KEPT
        self.run = run
        self.command = command_of(state)
        self.spent = 0
        self.slotless = False
        self.records: dict | None = None

    def known(self) -> dict:
        if self.records is None:
            self.records = store.read_dict(self.path)
        return self.records

    def was(self, one: ready.PullRequest, tip: str) -> dict | None:
        was = self.known().get(str(one.number))
        if isinstance(was, dict) and (was.get("head"), was.get("tip")) == (one.head, tip):
            return was
        return None

    def kept(self, one: ready.PullRequest, tip: str) -> str:
        """Why the pull request waits on the guards a run already ran on its head over `tip`, or
        nothing where they passed or have not run there."""
        if not self.command:
            return ""
        was = self.was(one, tip) or {}
        said = was.get("said")
        return said if isinstance(said, str) else ""

    def keep(self, one: ready.PullRequest, tip: str, said: str, note: str, tail: str = "") -> None:
        now = datetime.now().astimezone()
        record = {"head": one.head, "tip": tip, "said": said, "note": note}
        if tail:
            record["tail"] = tail
        record["at"] = f"{now:%Y-%m-%dT%H:%M:%S%z}"
        self.records = {**self.known(), str(one.number): record}
        if self.run:
            store.write_json(self.path, self.records)

    def open_only(self, numbers: set[str] | dict[str, str]) -> None:
        """Drop the record of each pull request that is no longer open."""
        known = self.known()
        kept = {number: was for number, was in known.items() if number in numbers}
        if kept != known:
            self.records = kept
            if self.run:
                store.write_json(self.path, kept)

    def of(self, one: ready.PullRequest, tip: str) -> tuple[str, str]:
        """Why the pull request waits on the guards on its head merged over `tip`, or nothing, and
        the note a merge line gives where they passed. Guards that passed while the base moved
        past `tip` pass a tree that is no longer the one to merge: it waits for the next run."""
        if not self.command or not tip:
            return "", ""
        if not _git(self.main, "merge-base", "--is-ancestor", tip, one.head).returncode:
            return "", ""
        was = self.was(one, tip)
        if was is not None:
            return str(was.get("said") or ""), str(was.get("note") or "")
        values = {"base": one.base, "tip": tip[:SHA]}
        merged = _git(self.main, "merge-tree", "--write-tree", tip, one.head)
        tree = merged.stdout.split()[:1]
        if merged.returncode == 1 and tree:
            return ready.FRESH_CONFLICT, ""
        if merged.returncode or not tree:
            return ready.MERGED_TREE_UNBUILT.format(**values, why=_said(merged)), ""
        if run := self.checked(tip, tree[0]):
            note = CHECKED.format(**values, run=run)
            self.keep(one, tip, "", note)
            return "", note
        if self.spent >= RUN_SECONDS:
            return ready.MERGED_TREE_NO_TIME.format(**values), ""
        if self.slotless:
            return ready.MERGED_TREE_NO_SLOT.format(**values, seconds=SLOT_SECONDS), ""
        message = f"jmerge: #{one.number} merged over {one.base} at {tip[:SHA]}"
        made = _git(
            self.main, *_IDENTITY, "commit-tree", tree[0], "-p", tip, "-p", one.head, "-m", message
        )
        ran = self.in_tree(made.stdout.strip(), tip, one.head)
        if ran is None:
            self.slotless = True
            self.spent += SLOT_SECONDS
            return ready.MERGED_TREE_NO_SLOT.format(**values, seconds=SLOT_SECONDS), ""
        if isinstance(ran, str):
            return ready.MERGED_TREE_UNBUILT.format(**values, why=ran), ""
        self.spent += ran.waited + ran.seconds
        said, note = "", ""
        if ran.code is None:
            said = ready.MERGED_TREE_UNENDED.format(**values, minutes=LIMIT_SECONDS // 60)
        elif ran.code:
            said = ready.MERGED_TREE_FAILS.format(**values, guard=guard(ran.said))
        else:
            note = PASSED.format(**values, seconds=ran.seconds)
        tail = "\n".join(ran.said.rstrip().splitlines()[-TAIL:]) if said else ""
        self.keep(one, tip, said, note, tail)
        at = _git(self.main, "ls-remote", "origin", f"refs/heads/{one.base}").stdout.split()
        if not said and at[:1] != [tip]:
            return ready.MAIN_MOVED.format(base=one.base), ""
        return said, note

    def on_batch(self, commit: str, tip: str) -> Tried:
        """Run the guards once on a batch's `commit` over `tip`, under the rules of `of`: none
        once the run spent `RUN_SECONDS`, none after a wait for a slot found none, and the
        seconds spent count toward the run's. Nothing is kept in `KEPT`: a member's record there
        is of its own tree, which the single path runs where the batch did not pass, and the
        batch's pass is no proof of that tree."""
        if self.spent >= RUN_SECONDS:
            return Tried(UNRUN[0], 0, f"the run spent its {RUN_SECONDS} s of guards")
        if self.slotless:
            return Tried(NO_SLOT, 0)
        ran = self.in_tree(commit, tip)
        if ran is None:
            self.slotless = True
            self.spent += SLOT_SECONDS
            return Tried(NO_SLOT, SLOT_SECONDS)
        if isinstance(ran, str):
            return Tried(UNRUN[1], 0, ran)
        self.spent += ran.waited + ran.seconds
        outcome = STOPPED if ran.code is None else FAILS if ran.code else PASSES
        return Tried(outcome, ran.seconds)

    def checked(self, tip: str, tree: str) -> str | None:
        """The address of a successful check of this repo that tested `tree` over `tip`, by the
        artifact it left for the two trees, or None. A lookup that fails finds none, and the
        guards run."""
        base = _git(self.main, "rev-parse", f"{tip}^{{tree}}").stdout.strip()
        try:
            run, _ = green.green_run(self.ask, green.checked(base, tree))
        except Exception:
            return None
        return run

    def in_tree(self, commit: str, tip: str, head: str) -> Ran | str | None:
        """Run the guards in a worktree of `commit` at the state's `TREE`, and remove it after,
        with `BASE` the tip and `MERGE_BASE` the merge base of `head` and the tip: the commit the
        pull request's check ran over, so the guards also run what main changed since then.
        One a run that was stopped left behind is removed first. Return why the worktree could
        not be made or the guards not started, where they could not, and None where no full test
        slot came free for them (`run_guards`)."""
        path = self.state / TREE
        self.clear(path)
        added = _git(self.main, "worktree", "add", "--detach", "-q", str(path), commit)
        if added.returncode:
            return _said(added)
        try:
            merge_base = _git(self.main, "merge-base", tip, head).stdout.strip()
            env = {"BASE": tip, "MERGE_BASE": merge_base}
            return run_guards(self.command, path, env, LIMIT_SECONDS)
        finally:
            self.clear(path)

    def clear(self, path: Path) -> None:
        _git(self.main, "worktree", "remove", "--force", str(path))
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        _git(self.main, "worktree", "prune")
