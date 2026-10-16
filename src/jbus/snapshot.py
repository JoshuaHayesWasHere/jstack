"""`jbus snapshot`: commit the homes' state tree and push it, so every home's state is kept.

The tree is the config's `home_dir`, `~/.local/state/home`, a git repo. A snapshot stages
everything (`git add -A`). With something staged, gitleaks reads it, and one secret in it
unstages it all and commits nothing; otherwise it commits `snapshot <YYYY-MM-DD HH:MM ET>`,
in the user's zone, followed by `: <why>` when `--why` says what changed. Then it pushes to
`origin` when the repo has one, whether or not it committed, so a push that failed is made
again by the next run.

`jbus-snapshot.timer` runs it at 08:30 and 17:30, and a home runs it with `--why` right after
each edit to a `standing.md`, so that edit is a commit of its own and can be undone. A
snapshot that did not finish fails `jbus-snapshot.service`, whose `OnFailure=` runs
`jbus snapshot --alarm`: the first failure alerts the desk and every project, once, and the
next snapshot that goes says it recovered (`alert.sound`, `alert.recover`).
"""

from __future__ import annotations

import argparse
import fcntl
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import jbus
import jsettings
from jbus import alert, verbs

AFTER = 1
ALARM = (
    "the last snapshot of the homes' state tree did not finish "
    "(see journalctl --user -u jbus-snapshot)"
)


class Failed(Exception):
    """A snapshot that committed nothing it should have, or did not push what it committed."""


def _git(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True)


def _must(ran: subprocess.CompletedProcess[str], what: str) -> None:
    if ran.returncode:
        said = " ".join((ran.stderr or ran.stdout).split())
        raise Failed(f"{what} failed: {said or f'exit {ran.returncode}'}")


def take(tree: Path, now: datetime, user: jsettings.Settings, why: str | None = None) -> str:
    """Snapshot the tree, and say what was done in one line. `Failed` when it could not.

    A run holds `jbus-snapshot.lock` in the tree's git dir from `git add` to the push, so the
    homes' runs and the timer's wait for each other and never share an index."""
    found = _git(tree, "rev-parse", "--absolute-git-dir")
    if found.returncode:
        raise Failed(f"{tree} is not a git repo")
    with (Path(found.stdout.strip()) / "jbus-snapshot.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _take(tree, now, user, why)


def _take(tree: Path, now: datetime, user: jsettings.Settings, why: str | None) -> str:
    _must(_git(tree, "add", "-A"), "git add")
    staged = _git(tree, "diff", "--cached", "--quiet").returncode != 0
    if staged:
        _commit(tree, f"snapshot {user.stamp(now)}" + (f": {why}" if why else ""))
    done = "committed" if staged else "nothing changed"
    if _git(tree, "remote", "get-url", "origin").returncode:
        return f"snapshot: {done}, no remote to push to"
    _must(_git(tree, "push", "-q", "origin", "HEAD"), "git push")
    return f"snapshot: {done}, pushed"


def _commit(tree: Path, message: str) -> None:
    """Commit what is staged, unless gitleaks finds a secret in it or is not there to read it."""
    gitleaks = shutil.which("gitleaks")
    scanned = (
        subprocess.run(
            [gitleaks, "protect", "--staged", "--no-banner", "--redact"],
            cwd=tree,
            capture_output=True,
        ).returncode
        if gitleaks
        else None
    )
    if scanned != 0:
        _git(tree, "reset", "-q")
        if scanned is None:
            raise Failed("no gitleaks to read the changes, nothing committed")
        raise Failed("gitleaks found a secret in the changes, nothing committed")
    _must(_git(tree, "commit", "-q", "-m", message), "git commit")


def snapshot(
    config: jbus.Config,
    now: datetime | None = None,
    say: Callable[[str], None] = print,
    why: str | None = None,
) -> int:
    """Take a snapshot of `config.home_dir`. One that went ends a streak of failed ones, and
    exits 0 even where a project could not be told so: the snapshot is what the unit runs."""
    now = now or datetime.now(UTC)
    try:
        say(take(config.home_dir, now, config.user, why))
    except Failed as error:
        say(f"snapshot: {error}")
        return 1
    alert.recover(config, alert.SNAPSHOT, now, say)
    return 0


def alarm(
    config: jbus.Config, now: datetime | None = None, say: Callable[[str], None] = print
) -> int:
    """Count a snapshot that did not finish. The first in a row alerts, once."""
    now = now or datetime.now(UTC)
    say("snapshot failed")
    return alert.sound(config, alert.SNAPSHOT, ALARM, AFTER, now, say)


def _arguments(shown: argparse.ArgumentParser) -> None:
    either = shown.add_mutually_exclusive_group()
    either.add_argument(
        "--alarm", action="store_true", help="count a snapshot that did not finish, and alert"
    )
    either.add_argument("--why", help="what changed, put in the commit message after the time")


VERBS = (
    verbs.Verb(
        "snapshot",
        "commit and push the homes' state tree",
        _arguments,
        lambda args, config: alarm(config) if args.alarm else snapshot(config, why=args.why),
    ),
)
