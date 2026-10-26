"""A process a thread left running after its turn is stopped, and the thread's Result says so.

A crew, reviewer or scout thread can start a process that outlives its turn: a `yes` left by a
test, a server in a temporary folder. Once the shell that started it is gone, its parent is a
reaper, and nothing in T3 Code or jbus stops it. Each pass, `stop` looks for such processes,
for each task whose threads are not at work:

- A crew's and its reviewers' processes are those whose working directory or an argument is under
  the task's worktree, or under a temporary folder (`TEMP`) while the process was started by a
  session of that worktree. The worktree is the one git lists for the task's branch in the main
  checkout, or `WORKTREES/<project>/<slug>`, where T3 Code makes it. A worktree that was removed
  still counts: its processes have a working directory that ends ` (deleted)`. A task counts
  while a thread of it is listed, and while it is a row of the queue.
- A scout works in the main checkout, beside its home, so a folder alone does not tell its
  processes from the home's. A scout's processes are those under the main checkout or a
  temporary folder that its own session started: a session whose first message from the user
  is `/scout <slug>`. jbus settles a scout once its Report is written, so a scout counts
  whether T3 Code lists it or not, while no thread of that scout is at work.

A session is the process's `queue.SESSION`, and its transcript is `<the agent's config
folder>/projects/<the folder, with - for each character that is not a letter or a
digit>/<session>.jsonl`, both read from the process's own environment. `AGENT` is the agent's
name, which spells the config folder's variable (`CONFIG`) and its default (`KEPT`).

A process is an orphan when its parent is a reaper (`reaper`): 1, or the user's own
`systemd --user`, which adopts what a unit of it left, as it is for jbus, a user service. Where
there is no /proc (`ROOT`), as on macOS, `ps` says what a process is, `lsof` its working directory,
and the one reaper is 1, launchd. There the environment is not read, since macOS's `ps -E` showed
none for the user's own processes on the macOS job: a temporary folder and a scout's session then
tie no process to a task, and only a folder or an argument under a worktree does. `ps` gives the
command line as one string, so its arguments are split at spaces there: a path with a space in it,
as an app bundle's, is read as several arguments. A process is never stopped when its parent is not
a reaper, when it is not the user's, when it is jbus or one of its ancestors, when it is T3 Code's
or the agent's own (`OWN`), or when it or a process under it holds a test slot (`SLOT`): a check or
a proof that still runs. Of those left, a crew's process is stopped busy or idle once the turn that
left it ended, whatever its row waits on: a crew's next turn starts afresh and cannot count on what
it left. A scout's is stopped only when it used CPU over `GAP` seconds of the pass. `stop` sends
each one TERM, and KILL to one still running `GRACE` seconds later, for a process that has the same
start time.

For each task with a process stopped, `stop` says one line, which the unit's journal keeps, with
the count and the commands. It also adds one `Left running:` line at the end of the brief's last
Result, or of the scout's last Report, above a Review or any other section after it. Where there
is no Result or Report yet, the line waits in `left-running.json` and goes in once one is written.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from jbus import queue, read_json, threads, verbs, write_json
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
AGENT = "claude"
CONFIG = f"{AGENT.upper()}_CONFIG_DIR"
KEPT = Path.home() / f".{AGENT}"
OWN = re.compile(rf"(^|/)(t3|t3code[^/]*|{AGENT}|jbus|jgauge)$|t3code|/{AGENT}/versions/")
SHOWN = 3
SLOT = re.compile(r"/test-slot(-short)?\.\d+\.lock$")


@dataclass
class Proc:
    """A `Proc` is what `/proc`, or `ps` where there is none, says of one process: its parent,
    its start time, its CPU time in clock ticks (hundredths of a second from `ps`), its
    arguments, its working directory, its environment, and its owner where `ps` read it (the
    /proc reader keeps only the user's own)."""

    pid: int
    ppid: int
    start: int
    ticks: int
    args: list[str]
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    uid: int | None = None

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


def _run(*argv: str) -> str:
    """What a command prints, in the C locale, or nothing when it cannot be run."""
    try:
        said = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            errors="replace",
            env={**os.environ, "LC_ALL": "C"},
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return said.stdout


def _ticks(text: str) -> int:
    """`ps`'s CPU time, `[days-][hours:]minutes:seconds[.hundredths]`, in hundredths."""
    days, _, clock = text.rpartition("-")
    seconds = 0.0
    for part in clock.split(":"):
        seconds = seconds * 60 + float(part)
    return round((int(days or 0) * 86400 + seconds) * 100)


def _ps(*pids: str) -> dict[int, Proc]:
    """Each of the processes, or each process when none is named, that is not a zombie, as `ps`
    gives it: no working directory or environment yet. `lstart` is a start time to the second,
    which is enough to tell a process from a later one with its pid."""
    which = ("-p", ",".join(pids)) if pids else ("-A",)
    said = _run("ps", "-ww", *which, "-o", "pid=,ppid=,uid=,lstart=,time=,stat=,command=")
    found = {}
    for line in said.splitlines():
        part = line.split(None, 10)
        if len(part) < 10 or part[9].startswith("Z"):
            continue
        try:
            start = time.mktime(time.strptime(" ".join(part[3:8]), "%a %b %d %H:%M:%S %Y"))
            args = part[10].split() if len(part) > 10 else []
            pid, ppid, uid = int(part[0]), int(part[1]), int(part[2])
            found[pid] = Proc(pid, ppid, int(start), _ticks(part[8]), args, "", uid=uid)
        except ValueError:
            continue
    return found


def _stats(pids: Iterable[str]) -> dict[str, tuple[int, int, int] | None]:
    """Each process's parent, start time and CPU time: from /proc, or from one `ps` where there
    is none."""
    pids = list(pids)
    if ROOT.is_dir() or not pids:
        return {pid: _stat(pid) for pid in pids}
    listed = _ps(*pids)
    return {
        pid: (one.ppid, one.start, one.ticks) if (one := listed.get(int(pid))) else None
        for pid in pids
    }


def _stat(pid: str) -> tuple[int, int, int] | None:
    try:
        text = (ROOT / pid / "stat").read_text()
        fields = text.rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return int(fields[1]), int(fields[19]), int(fields[11]) + int(fields[12])
    except (OSError, IndexError, ValueError):
        return None


def _manager(pid: str) -> bool:
    """Whether the process is the user's own service manager, `systemd --user`: /proc does not
    say which process is a child subreaper, so it is known by its place, the `init.scope` of
    the user's `user@<uid>.service`."""
    uid = os.getuid()
    try:
        if (ROOT / pid).stat().st_uid != uid:
            return False
        lines = (ROOT / pid / "cgroup").read_text().splitlines()
    except OSError:
        return False
    return any(one.endswith(f"/user@{uid}.service/init.scope") for one in lines)


def reaper(pid: int) -> bool:
    """Whether the process is one an orphan is handed to: 1, or a user manager, which the
    system's manager, 1, starts."""
    if pid == 1:
        return True
    stat = _stat(str(pid))
    return stat is not None and stat[0] == 1 and _manager(str(pid))


def _read(pid: str, stat: tuple[int, int, int]) -> Proc | None:
    """Return the process, or None when it is gone or is not the user's."""
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


def _located(found: list[Proc]) -> list[Proc]:
    """The processes with the working directory `lsof` gives. A process `lsof` gives no folder
    for has none, and is known by its arguments alone."""
    if not found:
        return []
    pids = ",".join(str(one.pid) for one in found)
    folders, pid = {}, ""
    for line in _run("lsof", "-a", "-d", "cwd", "-Fn", "-p", pids).splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("n") and pid:
            folders[pid] = line[1:].removesuffix(" (deleted)")
    for one in found:
        one.cwd = folders.get(str(one.pid), "")
    return found


def _from_proc() -> tuple[dict[int, int], list[Proc]]:
    """Each process's parent, and the user's processes whose parent is a reaper, from /proc."""
    try:
        pids = [one.name for one in ROOT.iterdir() if one.name.isdecimal()]
    except OSError:
        return {}, []
    stats = {pid: stat for pid in pids if (stat := _stat(pid)) is not None}
    adopting = {ppid for ppid in {stat[0] for stat in stats.values()} if reaper(ppid)}
    left = [_read(pid, stat) for pid, stat in stats.items() if stat[0] in adopting]
    parents = {int(pid): stat[0] for pid, stat in stats.items()}
    return parents, [one for one in left if one is not None]


def _from_ps() -> tuple[dict[int, int], list[Proc]]:
    """The same, from `ps` and `lsof`, where the one reaper is 1, launchd."""
    listed = _ps()
    uid = os.getuid()
    left = [one for one in listed.values() if one.ppid == 1 and one.uid == uid]
    return {pid: one.ppid for pid, one in listed.items()}, _located(left)


def _ancestors(parents: dict[int, int]) -> set[int]:
    found, pid = set(), os.getpid()
    while pid > 1 and pid not in found:
        found.add(pid)
        pid = parents.get(pid, 0)
    return found


def _slotted(pid: int) -> bool:
    """Whether the process holds a test slot: one of its files is a lock of `jgauge.slot`."""
    try:
        files = list((ROOT / str(pid) / "fd").iterdir())
    except OSError:
        return False
    for one in files:
        try:
            if SLOT.search(os.readlink(one)):
                return True
        except OSError:
            continue
    return False


def in_slot(found: Iterable[Proc]) -> set[int]:
    """The processes that hold a test slot, themselves or through a process under them: a check
    or a proof that still runs."""
    found = list(found)
    if not found:
        return set()
    try:
        pids = [one.name for one in ROOT.iterdir() if one.name.isdecimal()]
    except OSError:
        pids = []
    children: dict[int, list[int]] = {}
    for pid in pids:
        if (stat := _stat(pid)) is not None:
            children.setdefault(stat[0], []).append(int(pid))
    return {one.pid for one in found if _holds(one.pid, children)}


def _holds(pid: int, children: dict[int, list[int]]) -> bool:
    seen, left = set(), [pid]
    while left:
        one = left.pop()
        if one in seen:
            continue
        if _slotted(one):
            return True
        seen.add(one)
        left += children.get(one, [])
    return False


def orphans() -> list[Proc]:
    """Every process of the user whose parent is a reaper, but for jbus's, T3 Code's and the
    agent's."""
    parents, left = _from_proc() if ROOT.is_dir() else _from_ps()
    mine = _ancestors(parents)
    found = [one for one in left if one.pid not in mine]
    return [one for one in found if not any(OWN.search(arg) for arg in one.args[:3])]


def under(path: str, folder: Path) -> bool:
    return path == str(folder) or path.startswith(f"{folder}/")


def transcript(proc: Proc, folder: Path) -> Path | None:
    """The transcript of the session that started the process, where that session worked in
    `folder`."""
    session = proc.env.get(queue.SESSION, "")
    if not re.fullmatch(r"[A-Za-z0-9-]+", session):
        return None
    config = Path(proc.env.get(CONFIG) or KEPT)
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
                message = entry.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, list):
                    content = " ".join(
                        str(one.get("text", "")) for one in content if isinstance(one, dict)
                    )
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
    later = _stats(str(one.pid) for one in found)
    return [
        one
        for one in found
        if (now := later[str(one.pid)]) and now[1] == one.start and now[2] > one.ticks
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
        now = _stats(str(one.pid) for one in found)
        left = [one for one in found if (stat := now[str(one.pid)]) and stat[1] == one.start]
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


def tasks(run: Pass, out: list[threads.Out], rows: Iterable[queue.Row]) -> list[Task]:
    """The crews of the project, listed or a row of its queue, whose threads are all done with
    their turn."""
    rows = list(rows)
    listed = run.run("git", "worktree", "list", "--porcelain")
    trees, path = {}, ""
    for line in listed.stdout.splitlines() if listed.returncode == 0 else []:
        if line.startswith("worktree "):
            path = line.removeprefix("worktree ")
        elif line.startswith("branch refs/heads/"):
            trees[line.removeprefix("branch refs/heads/")] = Path(path)
    found = {one["slug"] for one in out if one["role"] in ("crew", "reviewer")}
    found |= {row["slug"] for row in rows}
    busy = working(out)
    made = []
    for slug in sorted(found):
        if not slug or ("crew", slug) in busy:
            continue
        places = [trees.get(slug), WORKTREES / run.project.name / slug]
        places.append(WORKTREES / run.project.checkout.name / slug)
        made.append(Task(slug, tuple(dict.fromkeys(one for one in places if one is not None))))
    return made


def stop(run: Pass, out: list[threads.Out], rows: Iterable[queue.Row]) -> None:
    """Stop what the threads of each task left running, say so, and note it in the task's
    Result or Report."""
    left = orphans()
    if not left:
        _note(run, {})
        return
    claimed: dict[tuple[str, str], list[Proc]] = {}
    for task in tasks(run, out, rows):
        claimed[("crew", task.slug)] = [one for one in left if owns(task, one)]
    taken = {one.pid for found in claimed.values() for one in found}
    at_work = working(out)
    for one in left:
        slug = "" if one.pid in taken else scout_of(one, run.project.checkout)
        if slug and ("scout", slug) not in at_work:
            claimed.setdefault(("scout", slug), []).append(one)
    scouts = (one for (role, _), found in claimed.items() if role == "scout" for one in found)
    every = [one for found in claimed.values() for one in found]
    burning = (taken | {one.pid for one in busy(scouts)}) - in_slot(every)
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
            text = file.read_text(errors="surrogateescape")
        except OSError:
            continue
        found = list(re.finditer(r"^## (Result|Report)", text, re.M))
        if not found:
            kept[name] = line
            continue
        after = re.search(r"^## ", text[found[-1].end() :], re.M)
        end = found[-1].end() + after.start() if after else len(text)
        head, rest = text[:end].rstrip("\n"), text[end:]
        file.write_text(
            f"{head}\n{line}\n" + (f"\n{rest}" if rest else ""), errors="surrogateescape"
        )
    if kept or path.exists():
        write_json(path, kept)


def _stop(half: Half) -> None:
    if half.out is not None and not half.blind:
        stop(half.run, half.out, half.rows or [])


STEPS = (verbs.Step("after-expedite", 5, "strays.stop", _stop, ("client", "world")),)
