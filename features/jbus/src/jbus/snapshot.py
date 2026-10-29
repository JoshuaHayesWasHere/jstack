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
says on stderr which file, project, rule and why, and fails.

A snapshot that did not finish raises its alert itself (`alert.sound`), one for each owner: the
first path segment of each file gitleaks names in its report, or of each refused `standing.md`,
which is a home's directory and so its project (`owners`). A failure that names no file, such as a
push that failed or an error no check foresaw, is the machine's. Each alert goes to its owner's
home alone. A snapshot that did not fail for the machine read the whole stage, so it ends the
alert of each owner it did not fail for (`alert.recover`); one that failed for the machine ends
none, since it may not have read an owner's files.

A snapshot that is killed, as systemd kills one at the unit's `TimeoutStartSec`, never gets to
raise its alert, so each run leaves a mark of its own in the state dir's `RUNS`, holds a lock on it
while it runs, and removes it at its end. A pass that finds a mark nobody holds counts it as a
snapshot of the machine's that did not finish, and removes it (`unfinished`).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
FAILED = "the snapshot of the homes' state tree did not finish"
KILLED = (
    "it was stopped before its end, as the unit's timeout stops one "
    "(journalctl --user -u jbus-snapshot)"
)
RUNS = "snapshot-runs"
_RULE = re.compile(r"(\d+)\. ")
_CODE = re.compile(r"\bCode: ([\w.-]*\w)")
WAIT = 60.0


class Failed(Exception):
    """A snapshot failed: it did not commit what it should have, or did not push what it
    committed. `files` are the files of the tree gitleaks found a secret in."""

    def __init__(self, why: str, files: tuple[str, ...] = ()) -> None:
        super().__init__(why)
        self.files = files


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
    """Commit what is staged, unless gitleaks finds a secret in it or is not on PATH. A secret
    found fails with the files gitleaks names in its report."""
    gitleaks = shutil.which("gitleaks")
    if not gitleaks:
        _git(tree, "reset", "-q")
        raise Failed("no gitleaks to read the changes, nothing committed")
    with tempfile.TemporaryDirectory() as scratch:
        report = Path(scratch) / "report.json"
        scanned = subprocess.run(
            [gitleaks, "protect", "--staged", "--no-banner", "--redact"]
            + ["--report-format", "json", "--report-path", str(report)],
            cwd=tree,
            capture_output=True,
        ).returncode
        found = json.loads(report.read_text() or "[]") if report.exists() else []
    if scanned != 0:
        _git(tree, "reset", "-q")
        files = tuple(sorted({one["File"] for one in found if one.get("File")}))
        named = f" ({', '.join(files)})" if files else ""
        raise Failed(f"gitleaks found a secret in the changes{named}, nothing committed", files)
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


def owners(config: jbus.Config, files: Iterable[str]) -> list[str]:
    """Return the owner of each file of the tree, once each: the project whose home directory
    is the file's first path segment, or that segment where no project's home is it, which
    `jbus.Config.owner` sends to the infra home."""
    names = {project.state: project.name for project in config.projects}
    found = (Path(file).parts[0] for file in files if Path(file).parts)
    return list(dict.fromkeys(names.get(segment, segment) for segment in found))


def snapshot(
    config: jbus.Config,
    now: datetime | None = None,
    say: Callable[[str], None] = print,
    why: str | None = None,
    warn: Callable[[str], None] = _stderr,
) -> int:
    """Take a snapshot (`_snapshot`) under a mark of the run that only its end removes, so that a
    run killed before it is seen by the next pass (`unfinished`). The mark is written under a
    name that starts with a dot, which a pass passes over, and renamed once it is locked."""
    now = now or datetime.now(UTC)
    runs = config.state_dir / RUNS
    runs.mkdir(parents=True, exist_ok=True)
    fd, made = tempfile.mkstemp(prefix=".", dir=runs)
    with os.fdopen(fd, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        mark = runs / Path(made).name.removeprefix(".")
        os.rename(made, mark)
        code = _snapshot(config, now, say, why, warn)
        mark.unlink()
    return code


def unfinished(config: jbus.Config, _: object, now: datetime, say: Callable[[str], None]) -> None:
    """Count each snapshot whose mark no run holds, one that was killed before its end, as a
    failed snapshot of the machine's, and remove its mark. A mark whose run ended between the
    look and the lock is gone from its path by then, and is passed over."""
    runs = config.state_dir / RUNS
    for mark in sorted(runs.glob("[!.]*")) if runs.is_dir() else ():
        try:
            with mark.open() as read:
                fcntl.flock(read, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if os.stat(mark).st_ino != os.fstat(read.fileno()).st_ino:
                    continue
                mark.unlink()
        except (BlockingIOError, FileNotFoundError):
            continue
        alert.sound(config, alert.SNAPSHOT, f"{FAILED}: {KILLED}", AFTER, now, say)


def _snapshot(
    config: jbus.Config,
    now: datetime,
    say: Callable[[str], None],
    why: str | None,
    warn: Callable[[str], None],
) -> int:
    """Take a snapshot of `config.home_dir`, with each refused `standing.md` (`refusals`) left
    out of it and named to `warn`. A snapshot that refused none and succeeds ends the alerts of
    failed ones. One that fails says why to `warn`, and raises an alert for each owner of what
    failed: see the module."""
    refused: dict[Path, str] = {}
    failed: dict[str, str] = {}
    try:
        refused = refusals(config)
        for line in refused.values():
            warn(f"snapshot: refused, left out: {line}")
        say(take(config.home_dir, now, config.user, why, refused))
    except Failed as error:
        warn(f"snapshot: {error}")
        for owner in owners(config, error.files) or [alert.MACHINE]:
            failed[owner] = str(error)
    except Exception as error:
        warn(f"snapshot: {alert.why(error, config)}")
        failed[alert.MACHINE] = alert.why(error, config)
    for path, line in refused.items():
        owner = owners(config, [str(path.relative_to(config.home_dir))])[0]
        failed[owner] = "; ".join(filter(None, (failed.get(owner), f"refused {line}")))
    if alert.MACHINE not in failed:
        for key in alert.streaks(config.state_dir):
            if _owner(key) not in (None, *failed):
                alert.recover(config, key, say)
    for owner, cause in failed.items():
        key = f"{alert.SNAPSHOT} {owner}" if owner else alert.SNAPSHOT
        alert.sound(config, key, f"{FAILED}: {cause}", AFTER, now, say, owner=owner)
    return 1 if failed else 0


def _owner(key: str) -> str | None:
    """Return the owner of a snapshot alert's key, `MACHINE` for `snapshot` alone, or None for a
    key that is no snapshot's."""
    if key == alert.SNAPSHOT:
        return alert.MACHINE
    return key.removeprefix(f"{alert.SNAPSHOT} ") if key.startswith(f"{alert.SNAPSHOT} ") else None


def _arguments(shown: argparse.ArgumentParser) -> None:
    shown.add_argument("--why", help="what changed, put in the commit message after the time")


VERBS = (
    verbs.Verb(
        "snapshot",
        "commit and push the homes' state tree",
        _arguments,
        lambda args, config: snapshot(config, why=args.why),
    ),
)
CHORES = (verbs.Chore(30, "the snapshots that did not reach their end", unfinished),)
