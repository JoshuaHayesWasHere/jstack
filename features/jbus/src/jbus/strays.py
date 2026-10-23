"""A process a thread left running after its turn is stopped, and the thread's Result says so.

A crew, reviewer or scout thread can start a process that outlives its turn: a `yes` left by a
test, a server in a temporary folder. Once the shell that started it is gone, its parent is 1,
and nothing in T3 Code or jbus stops it. Each pass, `stop` looks for such processes, for each
task whose threads are not at work:

- A crew's and its reviewers' processes are those whose working directory or an argument is under
  the task's worktree, or under a temporary folder (`TEMP`) while the process was started by a
  session of that worktree. The worktree is the one git lists for the task's branch in the main
  checkout, or `WORKTREES/<project>/<slug>`, where T3 Code makes it. A worktree that was removed
  still counts: its processes have a working directory that ends ` (deleted)`. A task counts
  while a thread of it is listed, and while it is a row of the queue, once its row ended too.
- A scout works in the main checkout, beside its home, so a folder alone does not tell its
  processes from the home's. A scout's processes are those under the main checkout or a
  temporary folder that its own session started: a session whose first message from the user
  is `/scout <slug>`. jbus settles a scout once its Report is written, so a scout counts
  whether T3 Code lists it or not, while no thread of that scout is at work.

A session is the process's `CLAUDE_CODE_SESSION_ID`, and its transcript is
`<CLAUDE_CONFIG_DIR>/projects/<the folder, with - for each character that is not a letter or a
digit>/<session>.jsonl`, both read from the process's own environment.

A process is never stopped when its parent is not 1, when it is not the user's, when it is jbus
or one of its ancestors, or when it is T3 Code's or Claude's own (`OWN`). Of those left, it is
stopped only when it used CPU over `GAP` seconds of the pass. `stop` sends each one TERM, and
KILL to one still running `GRACE` seconds later, for a process that has the same start time.

For each task with a process stopped, `stop` says one line, which the unit's journal keeps, with
the count and the commands. It also adds one `Left running:` line to the end of the brief, under
its last Result, or under the scout's last Report. Where there is no Result or Report yet, the
line waits in `left-running.json` and goes in once one is written.
"""

from __future__ import annotations

import json
import os
import re
import signal
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from jbus import read_json, threads, verbs, write_json
from jbus.passes import Pass
from jbus.watch import LIVE

if TYPE_CHECKING:
    from jbus.cli import Half

ROOT = Path("/proc")
WORKTREES = Path.home() / ".t3" / "worktrees"
TEMP = (Path("/tmp"), Path("/var/tmp"))
GAP = 1.0
GRACE = 3.0
NAME = "left-running.json"
OWN = re.compile(r"(^|/)(t3|t3code[^/]*|claude|jbus|jgauge)$|t3code|/claude/versions/")
SHOWN = 3


@dataclass
class Proc:
    """A `Proc` is what `/proc` says of one process: its parent, its start time and CPU time in
    clock ticks, its arguments, its working directory, and its environment."""

    pid: int
    ppid: int
    start: int
    ticks: int
    args: list[str]
    cwd: str
    env: dict[str, str] = field(default_factory=dict)

    @property
    def command(self) -> str:
        return " ".join(self.args)[:80] or "?"

    @property
    def paths(self) -> list[str]:
        return [self.cwd, *(one for one in self.args if one.startswith("/"))]


@dataclass(frozen=True)
class Task:
    """A `Task` is a crew's slug and the folders it and its reviewers work in."""

    slug: str
    folders: tuple[Path, ...]


def _stat(pid: str) -> tuple[int, int, int] | None:
    try:
        text = (ROOT / pid / "stat").read_text()
        fields = text.rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return int(fields[1]), int(fields[19]), int(fields[11]) + int(fields[12])
    except (OSError, IndexError, ValueError):
        return None


def _read(pid: str) -> Proc | None:
    """Return the process, or None when it is gone, is a zombie, or is not the user's."""
    stat = _stat(pid)
    if stat is None or stat[0] != 1:
        return None
    where = ROOT / pid
    try:
        if where.stat().st_uid != os.getuid():
            return None
        args = (where / "cmdline").read_bytes().split(b"\0")
        cwd = os.readlink(where / "cwd").removesuffix(" (deleted)")
        env = (where / "environ").read_bytes().split(b"\0")
    except OSError:
        return None
    pairs = (one.decode(errors="replace").partition("=") for one in env if b"=" in one)
    return Proc(
        int(pid),
        stat[0],
        stat[1],
        stat[2],
        [one.decode(errors="replace") for one in args if one],
        cwd,
        {key: value for key, _, value in pairs},
    )


def _ancestors() -> set[int]:
    found, pid = set(), os.getpid()
    while pid > 1 and pid not in found:
        found.add(pid)
        stat = _stat(str(pid))
        pid = stat[0] if stat else 0
    return found


def orphans() -> list[Proc]:
    """Every process of the user whose parent is 1, but for jbus and T3 Code's and Claude's own."""
    try:
        pids = [one.name for one in ROOT.iterdir() if one.name.isdecimal()]
    except OSError:
        return []
    mine = _ancestors()
    found = [one for one in map(_read, pids) if one is not None and one.pid not in mine]
    return [one for one in found if not any(OWN.search(arg) for arg in one.args[:3])]


def under(path: str, folder: Path) -> bool:
    return path == str(folder) or path.startswith(f"{folder}/")


def transcript(proc: Proc, folder: Path) -> Path | None:
    """The transcript of the session that started the process, where that session worked in
    `folder`."""
    session = proc.env.get("CLAUDE_CODE_SESSION_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9-]+", session):
        return None
    config = Path(proc.env.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    kept = config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(folder)) / f"{session}.jsonl"
    return kept if kept.is_file() else None


def _asked(path: Path) -> str:
    """The text of the first message a user gave the session of a transcript."""
    try:
        with path.open(errors="replace") as lines:
            for _, line in zip(range(40), lines, strict=False):
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "user":
                    continue
                content = (entry.get("message") or {}).get("content")
                if isinstance(content, list):
                    content = " ".join(str(one.get("text", "")) for one in content)
                return str(content or "")
    except OSError:
        pass
    return ""


def scout_of(proc: Proc, checkout: Path) -> str:
    """The slug of the scout whose session started the process under the main checkout or a
    temporary folder, or nothing."""
    places = (checkout, *TEMP)
    if not any(under(one, place) for one in proc.paths for place in places):
        return ""
    kept = transcript(proc, checkout)
    asked = _asked(kept) if kept else ""
    found = re.match(
        r"\s*(?:/scout\s+|<command-message>scout</command-message>\s*"
        r"<command-name>/scout</command-name>\s*<command-args>)([A-Za-z0-9][A-Za-z0-9-]*)",
        asked,
    )
    return found[1] if found else ""


def owns(task: Task, proc: Proc) -> bool:
    """Whether the process is one the task's crew or reviewers left."""
    temp = any(under(one, place) for one in proc.paths for place in TEMP)
    for folder in task.folders:
        if any(under(one, folder) for one in proc.paths):
            return True
        if temp and transcript(proc, folder):
            return True
    return False


def busy(found: Iterable[Proc]) -> list[Proc]:
    """The processes that used CPU over `GAP` seconds."""
    found = list(found)
    if not found:
        return []
    time.sleep(GAP)
    later = {one.pid: _stat(str(one.pid)) for one in found}
    return [
        one
        for one in found
        if (now := later[one.pid]) and now[1] == one.start and now[2] > one.ticks
    ]


def kill(found: list[Proc]) -> None:
    """TERM each process, then KILL each one still running after `GRACE` seconds."""
    for one in found:
        try:
            os.kill(one.pid, signal.SIGTERM)
        except OSError:
            pass
    waited = 0.0
    while waited < GRACE:
        left = [one for one in found if (now := _stat(str(one.pid))) and now[1] == one.start]
        if not left:
            return
        time.sleep(0.1)
        waited += 0.1
    for one in left:
        try:
            os.kill(one.pid, signal.SIGKILL)
        except OSError:
            pass


def working(out: list[threads.Out]) -> set[tuple[str, str]]:
    """The tasks with a thread at work, as a role, `crew` or `scout`, and a slug."""
    roles = {"crew": "crew", "reviewer": "crew", "scout": "scout"}
    return {
        (roles[one["role"]], one["slug"])
        for one in out
        if one["role"] in roles and one["status"] in LIVE
    }


def tasks(run: Pass, out: list[threads.Out], slugs: Iterable[str]) -> list[Task]:
    """The crews of the project, listed or a row of its queue, whose threads are all done with
    their turn."""
    listed = run.run("git", "worktree", "list", "--porcelain")
    trees, path = {}, ""
    for line in listed.stdout.splitlines() if listed.returncode == 0 else []:
        if line.startswith("worktree "):
            path = line.removeprefix("worktree ")
        elif line.startswith("branch refs/heads/"):
            trees[line.removeprefix("branch refs/heads/")] = Path(path)
    found = {one["slug"] for one in out if one["role"] in ("crew", "reviewer")} | set(slugs)
    busy = working(out)
    made = []
    for slug in sorted(found):
        if not slug or ("crew", slug) in busy:
            continue
        places = [trees.get(slug), WORKTREES / run.project.name / slug]
        places.append(WORKTREES / run.project.checkout.name / slug)
        made.append(Task(slug, tuple(dict.fromkeys(one for one in places if one is not None))))
    return made


def stop(run: Pass, out: list[threads.Out], slugs: Iterable[str]) -> None:
    """Stop what the threads of each task left running, say so, and note it in the task's
    Result or Report."""
    left = orphans()
    if not left:
        _note(run, {})
        return
    claimed: dict[tuple[str, str], list[Proc]] = {}
    for task in tasks(run, out, slugs):
        claimed[("crew", task.slug)] = [one for one in left if owns(task, one)]
    taken = {one.pid for found in claimed.values() for one in found}
    at_work = working(out)
    for one in left:
        slug = "" if one.pid in taken else scout_of(one, run.project.checkout)
        if slug and ("scout", slug) not in at_work:
            claimed.setdefault(("scout", slug), []).append(one)
    burning = {one.pid for one in busy(one for found in claimed.values() for one in found)}
    notes = {}
    for (role, slug), found in sorted(claimed.items()):
        found = [one for one in found if one.pid in burning]
        if not found:
            continue
        kill(found)
        commands = ", ".join(f"{one.command} in {one.cwd}" for one in found[:SHOWN])
        more = f", and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
        run.say(f"left running {role} {slug}: stopped {len(found)}: {commands}{more}")
        file = run.home / ("scouts" if role == "scout" else "tasks") / f"{slug}.md"
        stamp = run.user.stamp(run.now)
        notes[str(file)] = f"Left running: {len(found)} stopped by jbus {stamp}: {commands}{more}"
    _note(run, notes)


def _note(run: Pass, notes: dict[str, str]) -> None:
    """Add each line to the end of its file once the file has a Result or a Report, and keep
    the rest for a later pass."""
    path = run.state / NAME
    waiting = {**read_json(path, {}), **notes}
    kept = {}
    for name, line in waiting.items():
        file = Path(name)
        try:
            text = file.read_text()
        except OSError:
            continue
        if not re.search(r"^## (Result|Report)", text, re.M):
            kept[name] = line
            continue
        file.write_text(text + ("" if text.endswith("\n") else "\n") + line + "\n")
    if kept or path.exists():
        write_json(path, kept)


def _stop(half: Half) -> None:
    if half.out is not None and not half.blind:
        stop(half.run, half.out, [row["slug"] for row in half.rows or []])


STEPS = (verbs.Step("after-expedite", 5, "strays.stop", _stop, ("client", "world")),)
