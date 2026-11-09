"""`repo-standard green`: may this checkout deploy? Only a tree that is green main may.

It answers yes, exit 0, only when all three hold:

- the checkout is clean;
- `HEAD` is main on the remote now, as `git ls-remote origin refs/heads/main` gives it, never a
  local `origin/main` a checkout that has not fetched holds stale;
- a run of `check.yml` in this repo passed the tree of `HEAD`.

The third is read from the marker a passing run leaves, the artifact `green-tree-<tree>`
(`jmerge.green.green_run`). Where the marker has expired or was never uploaded, the push run of
`check.yml` on main for `HEAD`'s commit answers, when its conclusion is success. GitHub keeps a
run's record as long as the repo keeps its artifacts and logs, 90 days by default, and the shared
workflow keeps the marker as long, so the run covers a marker whose upload failed and one a run at
an older version of the standard kept 7 days.

It refuses, exit 1, with one line for each of the three that fails and how to fix it. It exits 2
when it cannot ask: `git ls-remote` or GitHub's API, through `gh`, gave no answer, and nothing it
read already refuses.

The lookup is jmerge's: a clone of jstack at a tag has it in `features/jmerge/src`, beside this
feature, and an install of jstack has it as a package.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_standard.tree import Unreadable

_JMERGE = Path(__file__).resolve().parents[3] / "jmerge" / "src"
if _JMERGE.is_dir() and str(_JMERGE) not in sys.path:
    sys.path.append(str(_JMERGE))

marker = importlib.import_module("jmerge.green")

ASK_SECONDS = 30
Ask = Callable[[str], Any]


class CannotAsk(Exception):
    """The remote or GitHub gave no answer."""


@dataclass(frozen=True)
class Read:
    """What the checkout and the remote say. `main` is None where the remote has no main,
    `behind` says whether `HEAD` is an older commit of it, and `unasked` why the remote gave no
    answer, when it gave none."""

    dirty: int
    head: str
    tree: str
    main: str | None
    behind: bool = False
    unasked: str = ""


@dataclass(frozen=True)
class Passed:
    """Where the tree passed, or None, and whether only a fork's run left its marker."""

    run: str | None
    fork: bool = False


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=ASK_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise CannotAsk(f"git {args[0]} took over {ASK_SECONDS}s") from error


def _local(root: Path, *args: str) -> str:
    done = _git(root, *args)
    if done.returncode:
        raise Unreadable(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def read(root: Path) -> Read:
    dirty = _local(root, "status", "--porcelain")
    head = _local(root, "rev-parse", "HEAD")
    tree = _local(root, "rev-parse", "HEAD^{tree}")
    try:
        listed = _git(root, "ls-remote", "origin", "refs/heads/main")
    except CannotAsk as error:
        return Read(len(dirty.splitlines()), head, tree, None, unasked=str(error))
    if listed.returncode:
        said = listed.stderr.strip().splitlines()
        why = f"git ls-remote origin: {said[-1] if said else listed.returncode}"
        return Read(len(dirty.splitlines()), head, tree, None, unasked=why)
    main = listed.stdout.split()[0] if listed.stdout.strip() else None
    behind = bool(
        main
        and main != head
        and _git(root, "merge-base", "--is-ancestor", head, main).returncode == 0
    )
    return Read(len(dirty.splitlines()), head, tree, main, behind)


def gh(root: Path) -> Ask:
    """GitHub's API for the repo of the checkout's origin, through `gh`."""

    def ask(path: str) -> Any:
        try:
            done = subprocess.run(
                ["gh", "api", f"repos/{{owner}}/{{repo}}/{path}"],
                capture_output=True,
                text=True,
                cwd=root,
                timeout=ASK_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CannotAsk(f"gh api {path}: {error}") from error
        if done.returncode:
            said = (done.stderr.strip() or f"gh exited {done.returncode}").splitlines()[0]
            raise CannotAsk(f"gh api {path}: {said}")
        try:
            return json.loads(done.stdout)
        except json.JSONDecodeError as error:
            raise CannotAsk(f"gh api {path}: not JSON: {error.msg}") from error

    return ask


def passed(ask: Ask, tree: str, head: str) -> Passed:
    """Where `tree` passed the check: its marker's run, else main's push run of `head`."""
    try:
        run, fork = marker.green_run(ask, marker.ARTIFACT + tree)
        if run:
            return Passed(run)
        query = f"head_sha={head}&branch=main&event=push&status=success&per_page=100"
        listed = ask(f"actions/workflows/{Path(marker.WORKFLOW).name}/runs?{query}")
        for one in listed.get("workflow_runs", []):
            if (
                one.get("head_sha") == head
                and one.get("head_branch") == "main"
                and one.get("event") == "push"
                and one.get("conclusion") == "success"
                and one.get("path") == marker.WORKFLOW
            ):
                return Passed(one["html_url"])
    except (KeyError, TypeError, AttributeError) as error:
        raise CannotAsk(f"GitHub's answer has no {error}") from error
    return Passed(None, fork)


def judge(said: Read, found: Passed | str) -> tuple[int, list[str]]:
    """The exit code and the lines that say why. `found` is where the tree passed, or why
    GitHub gave no answer."""
    reasons = []
    if said.dirty:
        reasons.append(
            f"the checkout is not clean ({said.dirty} paths changed): commit or drop the changes"
        )
    if said.main is None and not said.unasked:
        reasons.append("origin has no main: push main first")
    elif said.main is not None and said.head != said.main:
        where = "is behind" if said.behind else "is not"
        reasons.append(
            f"HEAD {said.head[:12]} {where} origin's main {said.main[:12]}: "
            "check out origin's main as it is now"
        )
    if isinstance(found, Passed) and found.run is None:
        whose = "only a fork's run left" if found.fork else "no green run of check.yml left"
        reasons.append(
            f"tree {said.tree[:12]} has not passed the check: {whose} "
            f"{marker.ARTIFACT}{said.tree}, and no push run of check.yml on main passed "
            f"{said.head[:12]}: wait for main's run to pass, or start one with "
            "`gh workflow run check.yml --ref main`"
        )
    missing = [said.unasked] if said.unasked else []
    if isinstance(found, str):
        missing.append(found)
    if reasons:
        refused = [f"refused: {one}" for one in reasons]
        return 1, refused + [f"note: no answer: {one}" for one in missing]
    if missing or isinstance(found, str):
        return 2, [f"cannot ask: {one}" for one in missing]
    return 0, [
        f"green: {said.head[:12]} is origin's main, clean, and its tree passed in {found.run}"
    ]


def main(root: Path, ask: Ask | None = None) -> tuple[int, list[str]]:
    """The exit code and the lines `repo-standard green` prints for the checkout at `root`."""
    said = read(root)
    try:
        return judge(said, passed(ask or gh(root), said.tree, said.head))
    except CannotAsk as error:
        return judge(said, str(error))
