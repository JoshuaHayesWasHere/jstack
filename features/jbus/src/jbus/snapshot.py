"""`jbus snapshot`: commit the homes' state tree and push it, so every home's state is kept.

The tree is the config's `home_dir`, `~/.local/state/home`, which is a git repo. A snapshot stages
everything (`git add -A`). When something is staged, gitleaks reads it. If gitleaks finds one
secret, the snapshot unstages everything and commits nothing. Otherwise it commits
`snapshot <YYYY-MM-DD HH:MM ET>`, in the user's zone, followed by `: <why>` when `--why` says what
changed. Then it pushes to `origin`, whether or not it committed, so the next run retries a push
that failed. The backup is opt-in: a tree with no `origin` keeps its commit, which an edit can be
undone to, and the snapshot succeeds and says the backup is off. The install enables the timer
only once the tree has an origin and gitleaks is on the machine.

`jbus-snapshot.timer` runs `jbus snapshot` at 08:30 and 17:30. A home runs it with `--why` right
after each edit to a `standing.md`, so that each such edit is a commit of its own and can be undone.
Before it stages anything, a snapshot reads each project's `standing.md`, the home's and each
scoped home's (`refusals`). The file holds at most `CAP` numbered rules, and each rule names
`Code: <slug>`, a row of the project's queue that turns the rule into code. A file that breaks
either is refused: the snapshot leaves it out of the stage, commits and pushes the rest of the tree,
says on stderr which file, project, rule and why, and fails, so the alarm names the refused project.

A snapshot that did not finish fails `jbus-snapshot.service`, whose `OnFailure=` runs
`jbus snapshot --alarm`. The first failure in a row raises an alert, once, to the desk and every
project, and the next snapshot that succeeds reports the recovery (`alert.sound`, `alert.recover`).
"""

from __future__ import annotations

import argparse
import fcntl
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

import jbus
import jsettings
from jbus import alert, queue, verbs
from jsettings import proc

AFTER = 1
CAP = 3
_RULE = re.compile(r"(\d+)\. ")
_CODE = re.compile(r"\bCode: ([\w.-]*\w)")
WAIT = 60.0
ALARM = (
    "the last snapshot of the homes' state tree did not finish "
    "(see journalctl --user -u jbus-snapshot)"
)


class Failed(Exception):
    """A snapshot failed: it did not commit what it should have, or did not push what it
    committed."""


def _git(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return proc.git(tree, *args)


def _must(ran: subprocess.CompletedProcess[str], what: str) -> None:
    if ran.returncode:
        said = " ".join((ran.stderr or ran.stdout).split())
        raise Failed(f"{what} failed: {said or f'exit {ran.returncode}'}")


def take(
    tree: Path,
    now: datetime,
    user: jsettings.Settings,
    why: str | None = None,
    held: Iterable[Path] = (),
) -> str:
    """Snapshot the tree, but for the files `held` names, and return one line that says what
    `take` did. Raise `Failed` when `take` cannot finish the snapshot.

    A run holds `jbus-snapshot.lock` in the tree's git dir from `git add` to the push. So the
    runs of the homes and the timer wait for each other and never share an index. A run that
    has waited `WAIT` seconds for the lock fails, so a push that hangs cannot hold up an
    edit's snapshot without anyone seeing it."""
    found = _git(tree, "rev-parse", "--absolute-git-dir")
    if found.returncode:
        raise Failed(f"{tree} is not a git repo")
    with (Path(found.stdout.strip()) / "jbus-snapshot.lock").open("a") as lock:
        _hold(lock)
        return _take(tree, now, user, why, [str(path.relative_to(tree)) for path in held])


def _hold(lock: IO[str]) -> None:
    deadline = time.monotonic() + WAIT
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise Failed(
                    f"another snapshot has run for {WAIT:g} s and holds the lock, nothing committed"
                ) from None
            time.sleep(0.1)


def _take(
    tree: Path, now: datetime, user: jsettings.Settings, why: str | None, held: list[str]
) -> str:
    _must(
        _git(tree, "add", "-A", "--", ".", *(f":(exclude,literal){path}" for path in held)),
        "git add",
    )
    if held:
        _must(_git(tree, "reset", "-q", "--", *(f":(literal){path}" for path in held)), "git reset")
    staged = _git(tree, "diff", "--cached", "--quiet").returncode != 0
    if staged:
        _commit(tree, f"snapshot {user.stamp(now)}" + (f": {why}" if why else ""))
    done = "committed" if staged else "nothing changed"
    if _git(tree, "remote", "get-url", "origin").returncode:
        return f"snapshot: {done}, not pushed: {tree} has no origin, so the backup is off"
    _must(_git(tree, "push", "-q", "origin", "HEAD"), "git push")
    return f"snapshot: {done}, pushed"


def _commit(tree: Path, message: str) -> None:
    """Commit what is staged, unless gitleaks finds a secret in it or is not on PATH."""
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


def _rules(text: str) -> list[tuple[str, str]]:
    """Return each numbered rule of a `standing.md`, its number and its words. A rule runs from
    its numbered line to the next numbered line or heading, as `queue.rule` reads it."""
    rules: list[tuple[str, str]] = []
    inside = False
    for line in text.splitlines():
        numbered = _RULE.match(line)
        if numbered:
            rules.append((numbered[1], line))
            inside = True
        elif line.startswith("#"):
            inside = False
        elif inside:
            rules[-1] = (rules[-1][0], f"{rules[-1][1]}\n{line}")
    return rules


def refusals(config: jbus.Config) -> dict[Path, str]:
    """Return each `standing.md` of a project's home or scoped home that breaks the cap, with one
    line that names its project and the file, then each reason, which names the rule."""
    lines: dict[Path, str] = {}
    for project in config.projects:
        home = config.home(project)
        try:
            slugs = {row["slug"] for row in queue.load(config.state(project))}
        except queue.Unparsable:
            slugs = set()
        for standing in sorted({home / "standing.md", *home.glob("*/standing.md")}):
            if not standing.is_file():
                continue
            try:
                rules = _rules(standing.read_text(errors="replace"))
            except OSError as error:
                lines[standing] = (
                    f"{project.name}: {standing} cannot be read: {error.strerror or error}"
                )
                continue
            why = []
            if len(rules) > CAP:
                why.append(f"has {len(rules)} rules, and a standing.md holds at most {CAP}")
            for number, words in rules:
                code = _CODE.search(words)
                if not code:
                    why.append(
                        f"rule {number} has no Code: <slug>, the queue row that makes it code"
                    )
                elif code[1] not in slugs:
                    why.append(
                        f"rule {number} names Code: {code[1]}, "
                        f"which is in no queue of {project.name}"
                    )
            if why:
                lines[standing] = f"{project.name}: {standing} {'; '.join(why)}"
    return lines


def _stderr(line: str) -> None:
    print(line, file=sys.stderr)


def snapshot(
    config: jbus.Config,
    now: datetime | None = None,
    say: Callable[[str], None] = print,
    why: str | None = None,
    warn: Callable[[str], None] = _stderr,
) -> int:
    """Take a snapshot of `config.home_dir`, with each refused `standing.md` (`refusals`) left
    out of it and named to `warn`. A snapshot that refused none and succeeds ends a streak of
    failed ones, and one that fails says why to `warn`. `snapshot` returns 0 even when jbus could
    not tell a project that snapshots recovered, because the unit runs the snapshot, not the
    telling."""
    now = now or datetime.now(UTC)
    refused = refusals(config)
    for line in refused.values():
        warn(f"snapshot: refused, left out: {line}")
    try:
        say(take(config.home_dir, now, config.user, why, refused))
    except Failed as error:
        warn(f"snapshot: {error}")
        return 1
    if refused:
        return 1
    alert.recover(config, alert.SNAPSHOT, now, say)
    return 0


def alarm(
    config: jbus.Config, now: datetime | None = None, say: Callable[[str], None] = print
) -> int:
    """Count a snapshot that did not finish. The first failure in a row raises an alert, once,
    and it names each refused `standing.md` with its rule and why."""
    now = now or datetime.now(UTC)
    say("snapshot failed")
    refused = refusals(config)
    cause = f"{ALARM}: {'; '.join(refused.values())}" if refused else ALARM
    return alert.sound(config, alert.SNAPSHOT, cause, AFTER, now, say)


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
