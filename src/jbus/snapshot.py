"""`jbus snapshot`: commit the homes' state tree and push it, so every home's state is kept.

The tree is the config's `home_dir`, `~/.local/state/home`, a git repo. A snapshot stages
everything (`git add -A`). With something staged, gitleaks reads it, and one secret in it
unstages it all and commits nothing; otherwise it commits `snapshot <YYYY-MM-DD HH:MM ET>`,
in the user's zone. Then it pushes to `origin` when the repo has one, whether or not it
committed, so a push that failed is made again by the next run.

`jbus-snapshot.timer` runs it at 08:30 and 17:30. A snapshot that did not finish fails
`jbus-snapshot.service`, whose `OnFailure=` runs `jbus snapshot --alarm`: the first failure
alerts the desk and every project, once, and the next snapshot that goes says it recovered
(`alert.sound`, `alert.recover`).
"""

from __future__ import annotations

import argparse
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


def take(tree: Path, now: datetime, user: jsettings.Settings) -> str:
    """Snapshot the tree, and say what was done in one line. `Failed` when it could not."""
    if _git(tree, "rev-parse", "--git-dir").returncode:
        raise Failed(f"{tree} is not a git repo")
    _must(_git(tree, "add", "-A"), "git add")
    staged = _git(tree, "diff", "--cached", "--quiet").returncode != 0
    if staged:
        _commit(tree, now, user)
    done = "committed" if staged else "nothing changed"
    if _git(tree, "remote", "get-url", "origin").returncode:
        return f"snapshot: {done}, no remote to push to"
    _must(_git(tree, "push", "-q", "origin", "HEAD"), "git push")
    return f"snapshot: {done}, pushed"


def _commit(tree: Path, now: datetime, user: jsettings.Settings) -> None:
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
    _must(_git(tree, "commit", "-q", "-m", f"snapshot {user.stamp(now)}"), "git commit")


def snapshot(
    config: jbus.Config, now: datetime | None = None, say: Callable[[str], None] = print
) -> int:
    """Take a snapshot of `config.home_dir`. One that went ends a streak of failed ones, and
    exits 0 even where a project could not be told so: the snapshot is what the unit runs."""
    now = now or datetime.now(UTC)
    try:
        say(take(config.home_dir, now, config.user))
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


def _alarm(shown: argparse.ArgumentParser) -> None:
    shown.add_argument(
        "--alarm", action="store_true", help="count a snapshot that did not finish, and alert"
    )


VERBS = (
    verbs.Verb(
        "snapshot",
        "commit and push the homes' state tree",
        _alarm,
        lambda args, config: (alarm if args.alarm else snapshot)(config),
    ),
)
