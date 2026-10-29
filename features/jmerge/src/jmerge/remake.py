"""`jmerge --remake`: make each generated file of a stopped rebase again, from both sides.

A file a command writes is never resolved by hand. The repo's `[[project]]` table in jbus's config
names each one in its key `generated`, as `"<file> -> <command>"`, and where it names none `uv.lock`
is made by `uv lock`.
While a rebase is stopped, each file it stopped on that no line names is to resolve by hand, and
those are named first. Once only generated files are left, each one takes the base's version
(during a rebase, `--ours` is the base being rebased onto) and its command runs at the top of the
worktree, so the file is made from what both sides now ask for. The crew skill's "A conflict" runs
it each time the rebase stops.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import jbus
from jsettings import paths, proc

DEFAULT = "uv.lock -> uv lock"


def outside_venv() -> dict[str, str]:
    """This environment as a shell outside the venv `jmerge` runs in has it: `uv run --project`
    sets `VIRTUAL_ENV` and puts that venv's bin first on PATH, and both are taken out, so a bare
    `python3` or `uv` is the one the repo's own shell finds."""
    env = dict(os.environ)
    venv = env.pop("VIRTUAL_ENV", "")
    if venv:
        bin_dir = os.path.join(venv, "bin")
        env["PATH"] = os.pathsep.join(
            one for one in env.get("PATH", "").split(os.pathsep) if one != bin_dir
        )
    return env


def table(main: Path) -> list[str]:
    """The `generated` lines of the project whose main checkout is `main`, or the default line
    where jbus's config names none, or cannot be read."""
    try:
        config = jbus.load()
    except jbus.Refused:
        return [DEFAULT]
    project = next(
        (one for one in config.projects if one.checkout.resolve() == main.resolve()), None
    )
    return list(project.generated) if project and project.generated else [DEFAULT]


def made_by(lines: list[str], file: str) -> str | None:
    """The command the table gives for a file, from its first line that names it."""
    for line in lines:
        name, arrow, command = line.partition(" -> ")
        if arrow and name == file:
            return command
    return None


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return proc.git(cwd, *args)


def remake() -> list[str]:
    """What the run did, a line each, as the crew skill reads it."""
    here = Path.cwd()
    asked = _git(here, "rev-parse", "--path-format=absolute", "--git-dir")
    git_dir = Path(asked.stdout.strip())
    if asked.returncode or not any(
        (git_dir / one).is_dir() for one in ("rebase-merge", "rebase-apply")
    ):
        return ["no rebase is stopped here: nothing to make again"]
    top = _git(here, "rev-parse", "--show-toplevel")
    if top.returncode:
        return ["could not go to the top of the worktree: nothing made again"]
    top_dir = Path(top.stdout.strip())
    lines = table(paths.main_checkout(here) or Path())
    diff = _git(top_dir, "-c", "core.quotePath=false", "diff", "--name-only", "--diff-filter=U")
    stopped = [one for one in diff.stdout.splitlines() if one]
    by_hand = [one for one in stopped if made_by(lines, one) is None]
    if not stopped:
        return ["nothing is left to resolve: git rebase --continue"]
    if by_hand:
        return ["resolve these by hand and git add them, then run this again:", *by_hand]
    said = []
    for file in stopped:
        command = made_by(lines, file) or ""
        made = (
            not _git(top_dir, "checkout", "-q", "--ours", "--", file).returncode
            and not subprocess.run(
                ["sh", "-c", command],
                cwd=top_dir,
                env=outside_venv(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            and not _git(top_dir, "add", "--", file).returncode
        )
        if made:
            said.append(f"made again: {file}, by {command} over the base's version")
        else:
            said.append(
                f"not made: {command} did not write {file} over the base's version, "
                "so it is still to resolve"
            )
    return said
