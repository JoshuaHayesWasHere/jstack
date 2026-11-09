"""Once `jbus.threads.settle` puts a crew's thread away, `clear_scratch` removes what the crew
left on disk: its scratch folder (`jbus.dispatch.scratch`), the worktrees of the repo it made in
the Claude scratchpad of its own worktree, then the whole Claude scratch folder of that worktree
(`scratchpad`), and prunes the worktrees' registrations.

The Claude scratch folder is in /tmp whatever the crew's `TMPDIR` says, and a crew makes a
"before" worktree there for A/B timing that the door hook will not let it remove, so these stayed
registered and filled the tmpfs quota, as did the folders themselves once their worktrees were
gone. Only the crew's own folder is searched, so another crew's worktrees and T3 Code's own under
`~/.t3/worktrees` are out of reach, and a folder or worktree that holds some process's working
directory stays (`in_use`). Paths are compared resolved, since git lists a worktree at its resolved
path and macOS's /tmp and /var are links into /private.

A launch that `jgauge room` holds back for /tmp (`waiting` reads its line) first gets `sweep`: it
removes the Claude scratch folder of each T3 Code worktree that is gone and is no live row's
(`WORKTREES`), each session folder of a session started in a configured project's main checkout
(a home's, a scout's, the user's own) whose newest entry is older than `IDLE`, and each copy of the
base that `proved.sh` made (`BASE`) and that its run, killed before its EXIT trap, left behind. A
folder a process works in or names stays, so does the session folder of a session a process
resumes (`RESUMES`), however long it sat idle, and so does every copy of the base in a folder
where a `proved.sh` still runs.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from jbus import dispatch
from jbus.passes import Pass
from jsettings import proc

ROOT = Path("/proc")
WORKTREES = Path.home() / ".t3" / "worktrees"
BASE = "base.*"
PROVED = "proved.sh"
IDLE = 12 * 60 * 60
"""Seconds since the newest entry of a main checkout's session folder was written after which
`sweep` takes its session as ended: a session at work writes its task output there."""
RESUMES = ("--resume", "--session-id")
"""The arguments that name the session a Claude process runs, as `--resume=<id>` or `--resume
<id>`: T3 Code runs a session in its checkout and names its folder by no path."""
FULL = (
    (re.compile(r"(\S+) has ([\d.]+) of your ([\d.]+) GB quota used"), "quota", 1.0),
    (re.compile(r"(\S+) has ([\d.]+) GB used of ([\d.]+) GB, 80% of its size"), "size", 0.8),
    (re.compile(r"(\S+) has (\d+) of (\d+) file slots used"), "file slots", 1.0),
)
"""The lines `jgauge room` waits with for a full /tmp, each with what it is full of and the share of
the whole that its second number is."""
WAITING = re.compile(r"waiting: \S+ at \d+% of its (quota|size|file slots)$")


def mangled(path: str | Path) -> str:
    """Return the path with each character that is not a letter or a digit made `-`, as Claude
    Code names a folder for it."""
    return re.sub("[^A-Za-z0-9]", "-", str(path))


def claude_root() -> Path:
    """Return `claude-<uid>` in `CLAUDE_CODE_TMPDIR` or /tmp, where Claude Code keeps the scratch
    folder of each folder a session starts in."""
    return Path(os.environ.get("CLAUDE_CODE_TMPDIR") or "/tmp") / f"claude-{os.getuid()}"


def scratchpad(worktree: str) -> Path:
    """Return the folder Claude Code keeps the scratchpads of a session in `worktree` under."""
    return claude_root() / mangled(worktree)


def waiting(why: str) -> str:
    """Return what a row waits on when `jgauge room` said `why` for a full /tmp, as `waiting: /tmp
    at 81% of its quota`, or nothing for any other wait."""
    for pattern, what, share in FULL:
        if (found := pattern.match(why)) and float(found[3]) > 0:
            used = round(100 * share * float(found[2]) / float(found[3]))
            return f"waiting: {found[1]} at {used}% of its {what}"
    return ""


def in_use() -> set[Path] | None:
    """Return the resolved working directory of each process this user can read: from /proc
    (`ROOT`), or from `lsof` where there is none, as on macOS. None when neither says, since
    this very process works in a folder: then no worktree is known to be idle."""
    if ROOT.is_dir():
        found: set[Path] = set()
        for one in ROOT.glob("[0-9]*"):
            try:
                found.add(Path(os.readlink(one / "cwd")).resolve())
            except OSError:
                continue
    else:
        listed = proc.run(
            "lsof", "-a", "-d", "cwd", "-Fn", "-u", str(os.getuid()), errors="replace", timeout=30
        )
        found = {
            Path(line[1:]).resolve() for line in listed.stdout.splitlines() if line[:2] == "n/"
        }
    return found or None


@dataclass(frozen=True)
class Held:
    """What the user's processes hold: each working directory and each absolute argument
    (`paths`), each session id an argument of `RESUMES` names (`sessions`), and the folder each
    live `proved.sh` makes its copy of the base in (`proving`), None where a `proved.sh` runs and
    its folder is not known."""

    paths: frozenset[Path]
    sessions: frozenset[str]
    proving: frozenset[Path] | None

    def holds(self, folder: Path) -> bool:
        return any(one.is_relative_to(folder) for one in self.paths)

    def proves_in(self, folder: Path) -> bool:
        return self.proving is None or folder in self.proving


def _resolved(paths: Iterable[str]) -> set[Path]:
    return {Path(one).resolve() for one in paths if one.startswith("/")}


def _sessions(args: list[str]) -> set[str]:
    found = set()
    for at, arg in enumerate(args):
        name, equals, value = arg.partition("=")
        if name not in RESUMES:
            continue
        if not equals:
            value = args[at + 1] if at + 1 < len(args) else ""
        if value:
            found.add(value)
    return found


def held() -> Held | None:
    """Return what the user's processes hold, from /proc, or from `in_use` and `ps` where there is
    none. None when no process is known, as `in_use` says."""
    if not ROOT.is_dir():
        cwds = in_use()
        if cwds is None:
            return None
        listed = proc.run("ps", "-A", "-ww", "-o", "command=", errors="replace", timeout=30)
        args = [arg for line in listed.stdout.splitlines() for arg in line.split()]
        running = any(arg.endswith(f"/{PROVED}") for arg in args)
        return Held(
            frozenset(cwds | _resolved(args)),
            frozenset(_sessions(args)),
            None if running else frozenset(),
        )
    paths: set[Path] = set()
    sessions: set[str] = set()
    proving: set[Path] = set()
    for one in ROOT.glob("[0-9]*"):
        try:
            cwd = os.readlink(one / "cwd")
            args = [
                arg.decode(errors="replace") for arg in (one / "cmdline").read_bytes().split(b"\0")
            ]
            env = (one / "environ").read_bytes().split(b"\0")
        except OSError:
            continue
        paths |= _resolved([cwd, *args])
        sessions |= _sessions(args)
        if any(arg.endswith(f"/{PROVED}") or arg == PROVED for arg in args[:3]):
            given = [item.partition(b"=")[2] for item in env if item.startswith(b"TMPDIR=")]
            proving.add(Path(given[0].decode(errors="replace") if given else "/tmp").resolve())
    return Held(frozenset(paths), frozenset(sessions), frozenset(proving)) if paths else None


def newest(folder: Path) -> float:
    """Return the mtime of the newest entry in `folder`, the folder itself counted, or infinity
    for a folder gone before it was read, which is then no candidate. An entry gone while it is
    read is left out."""
    found = []
    for where, dirs, files in os.walk(folder):
        for path in (where, *(os.path.join(where, name) for name in (*dirs, *files))):
            with contextlib.suppress(OSError):
                found.append(os.lstat(path).st_mtime)
    return max(found, default=float("inf"))


def sweep(run: Pass, live: Iterable[Path]) -> list[Path]:
    """Remove what finished crews and ended sessions left in /tmp: the Claude scratch folder of
    each worktree under `WORKTREES` that is gone and is none of `live`, the worktrees of the rows
    still out, each session folder in the Claude scratch folder of a configured project's main
    checkout that nothing wrote in for `IDLE`, and each copy of the base `proved.sh` made in
    `TMPFS` (or /tmp) or in `claude_root`. Keep each that a process holds, each session folder whose
    session a process resumes however old it is, and each copy of the base in a folder where a
    `proved.sh` still runs. Return what went."""
    known = held()
    if known is None:
        return []
    root = claude_root()
    trees = [tree for repo in WORKTREES.glob("*") for tree in repo.glob("*") if tree.is_dir()]
    kept = {mangled(tree) for tree in (*trees, *live)}
    pads = [
        pad
        for pad in root.glob(f"{mangled(WORKTREES)}-*")
        if not any(pad.name == one or pad.name.startswith(f"{one}-") for one in kept)
    ]
    mains = {root / mangled(one.checkout) for one in run.config.projects}
    stale = time.time() - IDLE
    sessions = [
        session
        for main in mains
        for session in main.glob("*")
        if session.is_dir()
        and not session.is_symlink()
        and session.name not in known.sessions
        and newest(session) < stale
    ]
    homes = {Path(os.environ.get("TMPFS") or "/tmp"), root}
    copies = [copy for where in homes for copy in where.glob(BASE)]
    copies = [copy for copy in copies if not known.proves_in(copy.parent.resolve())]
    gone = []
    for folder in sorted({*pads, *sessions, *copies}):
        if folder.is_symlink() or not folder.is_dir() or known.holds(folder.resolve()):
            continue
        shutil.rmtree(folder, ignore_errors=True)
        if not folder.exists():
            gone.append(folder)
    if gone:
        run.run("git", "worktree", "prune")
        ended = sum(folder in sessions for folder in gone)
        shown = ", ".join(map(str, gone[:3]))
        run.say(
            f"cleared /tmp: {len(gone) - ended} folders finished crews left,"
            f" {ended} of sessions ended in a main checkout, {shown}"
        )
    return gone


def clear_scratch(run: Pass, slug: str, worktree: str = "") -> bool:
    """Remove the slug's scratch folder and the worktrees its crew made in the scratchpad of its
    `worktree`, save one in use, then the whole Claude scratch folder of the worktree once nothing
    in it stayed, and prune the worktrees' registrations. Return whether nothing stayed: no
    worktree or folder was kept in use or failed to go, and `in_use` could say which are in use."""
    folder = dispatch.scratch(run, slug)
    cleared, stayed = [], False
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
        cleared.append(f"its scratch folder {folder}")
    busy = in_use() if worktree else set()
    if busy is None:
        stayed = True
    elif worktree:
        pad = scratchpad(worktree).resolve()
        listed = run.run("git", "worktree", "list", "--porcelain").stdout.splitlines()
        for line in listed:
            tree = Path(line.removeprefix("worktree ")).resolve()
            if not line.startswith("worktree ") or not tree.is_relative_to(pad):
                continue
            if any(cwd.is_relative_to(tree) for cwd in busy):
                stayed = True
            elif run.run("git", "worktree", "remove", "--force", str(tree)).returncode == 0:
                cleared.append(f"the worktree {tree}")
            else:
                stayed = True
        if not stayed and pad.is_dir() and not any(cwd.is_relative_to(pad) for cwd in busy):
            shutil.rmtree(pad, ignore_errors=True)
            stayed = pad.exists()
            if not stayed:
                cleared.append(f"its Claude scratch folder {pad}")
    if cleared:
        run.run("git", "worktree", "prune")
        run.say(f"cleared {slug}: {', '.join(cleared)}")
    return not stayed
