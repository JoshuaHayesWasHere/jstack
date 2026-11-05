"""The fast guards on a pull request's tree merged over today's base, run before `jmerge` merges
it on its existing check.

Two pull requests can each pass their check alone and break the base together, as #923 and #935
did on 2026-11-03 with two `v007_` migrations. The clash shows on their merged tree. So before a
merge, `jmerge` merges the head over the base's tip with `git merge-tree`, makes it a local
commit whose parents are the tip and the head (as GitHub's merge ref is), pushes nothing, checks
it out in a worktree of its own, and runs the command the state's `merged-tree-guards` file names
there, with `BASE` set to the tip. jstack's names `make check-fast PART=guards`, the lint and the
guard tests a desk runs first.

A repo with no such file runs no guards. A head that holds the tip already is the tree its check
ran on, so nothing is built for it. A pass or a failure of the guards on a head over a tip is kept
in `merged-trees.json`, so a held pull request is not run again until its head or the tip moves.
Guards stopped at their time limit keep nothing: the pull request waits for this run alone, and
the next run tries them again.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jmerge import ready
from jsettings import store

NAME = "merged-tree-guards"
KEPT = "merged-trees.json"
TREE = "merged-tree"
LIMIT_SECONDS = 600
"""How long the guards may run on one tree before they are stopped."""
RUN_SECONDS = 240
"""The seconds of guards a run may spend before it starts no more: with one more at its limit, a
run stays under the 17 minutes jbus gives `jmerge` (`jbus.wake.JMERGE_TIMEOUT`)."""
UNNAMED = "its guards"
SHA = 12
PASSED = "the guards passed on its tree merged over {base} at {tip} in {seconds} s"
_IDENTITY = ("-c", "user.name=jmerge", "-c", "user.email=jmerge@localhost")


@dataclass(frozen=True)
class Ran:
    """What the guards did: their exit code, None where they were stopped at their time limit,
    the whole seconds they took, and what they printed."""

    code: int | None
    seconds: int
    said: str


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


def run_guards(command: str, cwd: Path, env: dict[str, str], timeout: float) -> Ran:
    """Run `command` in `cwd` in a session of its own, so a stop at `timeout` stops the
    processes it started too, which would outlive `sh` and hold the tree."""
    began = time.monotonic()
    process = subprocess.Popen(
        ["sh", "-c", command],
        cwd=cwd,
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
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
    return Ran(code, round(time.monotonic() - began), said or "")


def _stop(group: int) -> None:
    with contextlib.suppress(ProcessLookupError):
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
    nothing, but reads what a run kept."""

    def __init__(self, main: Path, state: Path, run: bool) -> None:
        self.main = main
        self.state = state
        self.path = state / KEPT
        self.run = run
        self.command = command_of(state)
        self.spent = 0
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

    def keep(self, one: ready.PullRequest, tip: str, said: str, note: str) -> None:
        now = datetime.now().astimezone()
        record = {"head": one.head, "tip": tip, "said": said, "note": note}
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
        if self.spent >= RUN_SECONDS:
            return ready.MERGED_TREE_NO_TIME.format(**values), ""
        merged = _git(self.main, "merge-tree", "--write-tree", tip, one.head)
        tree = merged.stdout.split()[:1]
        if merged.returncode == 1 and tree:
            return ready.FRESH_CONFLICT, ""
        if merged.returncode or not tree:
            return ready.MERGED_TREE_UNBUILT.format(**values, why=_said(merged)), ""
        message = f"jmerge: #{one.number} merged over {one.base} at {tip[:SHA]}"
        made = _git(
            self.main, *_IDENTITY, "commit-tree", tree[0], "-p", tip, "-p", one.head, "-m", message
        )
        ran = self.in_tree(made.stdout.strip(), tip)
        if isinstance(ran, str):
            return ready.MERGED_TREE_UNBUILT.format(**values, why=ran), ""
        self.spent += ran.seconds
        if ran.code is None:
            return ready.MERGED_TREE_UNENDED.format(**values, minutes=LIMIT_SECONDS // 60), ""
        said, note = "", ""
        if ran.code:
            said = ready.MERGED_TREE_FAILS.format(**values, guard=guard(ran.said))
        else:
            note = PASSED.format(**values, seconds=ran.seconds)
        self.keep(one, tip, said, note)
        at = _git(self.main, "ls-remote", "origin", f"refs/heads/{one.base}").stdout.split()
        if not said and at[:1] != [tip]:
            return ready.MAIN_MOVED.format(base=one.base), ""
        return said, note

    def in_tree(self, commit: str, tip: str) -> Ran | str:
        """Run the guards in a worktree of `commit` at the state's `TREE`, and remove it after.
        One a run that was stopped left behind is removed first. Return why the worktree could
        not be made, where it could not."""
        path = self.state / TREE
        self.clear(path)
        added = _git(self.main, "worktree", "add", "--detach", "-q", str(path), commit)
        if added.returncode:
            return _said(added)
        try:
            return run_guards(self.command, path, {"BASE": tip}, LIMIT_SECONDS)
        finally:
            self.clear(path)

    def clear(self, path: Path) -> None:
        _git(self.main, "worktree", "remove", "--force", str(path))
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        _git(self.main, "worktree", "prune")
