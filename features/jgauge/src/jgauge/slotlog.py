"""A log of every test slot taken and let go, and the report on a span of it.

`jgauge test-slot` appends one row when it takes a slot and one when it lets the slot go, in
both lanes and with or without `--thread`, to `jgauge/slots.jsonl` beside the lock files'
directory: `~/.local/state/jgauge/slots.jsonl`, and with `JGAUGE_LOCKS_DIR` set, as a test or a
sandbox sets it, the log moves with the locks. The holders file (`jgauge.holders`) keeps a run only
until jbus has woken its thread, and only a run with `--thread`, so it holds no history; this
log is the history.

A row is one JSON object:

- `at`, the time, ISO in UTC, and `event`, `take` or `release`;
- `id`, which pairs a take with its release, and `pid`, the `jgauge test-slot` process that
  holds the slot;
- `lane`, `full` or `short`, `slot`, the slot's number, and `slots`, the lane's size as the
  caller counted it, so a run with `--slots 5` shows as one;
- `thread`, the thread id or nothing, `command` and `cwd`, which name the caller, `cwd` empty
  when the caller's directory was removed before the call;
- on a take, `waited`, the seconds the call waited for the slot, and `repo`, the name of the
  directory that holds the git repository `cwd` is in, its main checkout's for a worktree, or
  nothing outside one;
- on a release, `code`, the command's exit code, `hold`, the seconds the slot was held,
  `cpu_user` and `cpu_system`, the CPU seconds every process of the take used, in user and in
  system mode, and `left`, how many of them still ran when the row was written.

The CPU is the take's whole tree, a process the command started and never waited for included:
a test's browser that outlives its runner, or a detached daemon. `getrusage(RUSAGE_CHILDREN)`
saw only the processes the command waited for, and on 2026-11-12 it put robotica's slots at
0.18 cores where they used about 3.4. So a take makes a cgroup of its own, `jgauge-take-<id>`,
under the holder's, and moves the holder into it before the command starts: everything the
command starts is born there, and stays there whoever its parent becomes. The release waits up to
`DRAIN_SECONDS` for every process but the holder to end, reads the cgroup's `cpu.stat`, moves the
holder back and removes the cgroup. That CPU includes the holder's own from the take on, and its
watchdog's, a few hundredths of a second. The drain is short, since the slot is held through it: a
process the command left running holds the slot no more than that. One still running then keeps
the cgroup, is counted only up to the release, and shows in `left`; the next take beside it
removes the cgroup once it is empty. The holder's cgroup is an agent's scope, which systemd
delegates to the user, so the take's cgroup also counts toward the scope and the slices above it,
as before.

Where the take can have no cgroup of its own (cgroup v1, a cgroup the user cannot write, macOS),
the CPU is what the command's waited-for tree used, as `getrusage` says, plus what each process
carrying the take's id in `JGAUGE_TEST_SLOT_TAKE` whose parent is outside the take used, read
from `/proc` every `SAMPLE_SECONDS` and through the drain. A process whose parent left it, and
that ends between two reads, is counted to its last read, and on macOS, with no `/proc`, not at
all.

A row is one `write` with `O_APPEND`, under the lock on the log's directory that `jgauge sample`
also takes. Once the first row is over 30 days old, the writer keeps the last 29 days, as the
load log does.

The report pairs takes with releases into holds. A take with no release is held to the end of
the span while its pid lives, and is counted as lost otherwise: a holder killed outright leaves
no release, and its slot was free once it died. For each lane it prints the holds, the mean
occupancy (slot-seconds held in the span over the span), Little's law from the same holds (takes
per second times the mean hold), and the wait in the call at p50 and p90. It then prints the CPU
seconds of the holds released in the span, by lane and by repo. Then, from jbus's
`slot-wake` events, it prints the mean occupancy over the time a thread of that lane waited for
a slot: with a waiter waiting every slot should be taken, so that share near 100% says the log
sees every holder, and a low one says some holder takes slots this log does not see.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import resource
import secrets
import statistics
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jgauge import sample

KEEP_DAYS = 30
PRUNED_TO_DAYS = 29
CGROUPS = Path("/sys/fs/cgroup")
PROCS = Path("/proc")
DRAIN_SECONDS = 2.0
LOOK_SECONDS = 0.05
SAMPLE_SECONDS = 0.5
TAKE = "JGAUGE_TEST_SLOT_TAKE"
PREFIX = "jgauge-take-"
WAKE = re.compile(r"^slot-wake: woke \S+, a (\w+) slot is free for `[^`]*`, after (\d+) min")


def path(locks: Path) -> Path:
    """The log of the slots whose lock files are in `locks`."""
    return locks.parent / "jgauge" / "slots.jsonl"


def _stamp(now: datetime) -> str:
    return now.astimezone(UTC).isoformat(timespec="milliseconds")


def _prune(log: Path, now: float) -> None:
    since = now - PRUNED_TO_DAYS * sample.DAY
    part = log.with_name(f".{log.name}.part")
    with log.open() as old, part.open("w") as new:
        for line in old:
            try:
                at = datetime.fromisoformat(json.loads(line)["at"]).timestamp()
            except (ValueError, KeyError, TypeError):
                continue
            if at >= since:
                new.write(line)
        new.flush()
        os.fsync(new.fileno())
    part.replace(log)


def _append(log: Path, row: dict) -> None:
    """Append one row. A log that cannot be written stops no test: the slot is the point."""
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        folder = os.open(log.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        fcntl.flock(folder, fcntl.LOCK_EX)
        if log.exists():
            with log.open() as lines:
                first = lines.readline()
            try:
                oldest = datetime.fromisoformat(json.loads(first)["at"]).timestamp()
            except (ValueError, KeyError, TypeError):
                oldest = None
            now = datetime.now(UTC).timestamp()
            if oldest is not None and oldest < now - KEEP_DAYS * sample.DAY:
                _prune(log, now)
        written = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(written, (json.dumps(row) + "\n").encode())
        finally:
            os.close(written)
    except OSError:
        pass
    finally:
        os.close(folder)


class _Cgroup:
    """The take's own cgroup, which the holder is in from the take to the release."""

    def __init__(self, home: Path, own: Path) -> None:
        self.home, self.own = home, own

    @classmethod
    def make(cls, key: str) -> _Cgroup | None:
        """Make the take's cgroup under the holder's and move the holder into it, or None where
        the holder is not in a cgroup v2 one it may write: on cgroup v1 `/proc/self/cgroup` has
        a line for each hierarchy, and on cgroup v2 it has the one, `0::/<the holder's>`."""
        own: Path | None = None
        try:
            (line,) = (PROCS / "self" / "cgroup").read_text().splitlines()
            home = CGROUPS / line.removeprefix("0::/").strip("/")
            for stale in home.glob(f"{PREFIX}*"):
                with contextlib.suppress(OSError):
                    stale.rmdir()
            own = home / f"{PREFIX}{key}"
            own.mkdir()
            (own / "cgroup.procs").write_text(str(os.getpid()))
        except (OSError, ValueError):
            with contextlib.suppress(OSError):
                if own is not None:
                    own.rmdir()
            return None
        return cls(home, own)

    def _others(self) -> int:
        """How many processes of the take there are besides the holder. The cgroup is there to
        read until the release removes it, since the holder is in it till then."""
        listed = (self.own / "cgroup.procs").read_text().split()
        return sum(pid != str(os.getpid()) for pid in listed)

    def end(self) -> tuple[float, float, int]:
        """The take's CPU and how many of its processes are left, raising OSError or ValueError
        where the cgroup cannot be read; the holder goes back to its own cgroup either way."""
        try:
            deadline = time.monotonic() + DRAIN_SECONDS
            while self._others() and time.monotonic() < deadline:
                time.sleep(LOOK_SECONDS)
            left = self._others()
            stat = dict.fromkeys(("user_usec", "system_usec"), "0")
            stat |= {
                key: value
                for key, _, value in (
                    line.partition(" ") for line in (self.own / "cpu.stat").read_text().splitlines()
                )
                if key in stat
            }
            return int(stat["user_usec"]) / 1e6, int(stat["system_usec"]) / 1e6, left
        finally:
            with contextlib.suppress(OSError):
                (self.home / "cgroup.procs").write_text(str(os.getpid()))
            with contextlib.suppress(OSError):
                self.own.rmdir()


class _Carriers:
    """The take's CPU where it has no cgroup: the waited-for tree's by `getrusage`, and that of
    each process carrying the take whose parent is outside it, from `/proc`."""

    def __init__(self, key: str) -> None:
        self.key = f"{TAKE}={key}".encode()
        os.environ[TAKE] = key
        self.used = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.tick = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        self.left: dict[tuple[int, str], tuple[float, float]] = {}
        self.stop = threading.Event()
        self.sampler = threading.Thread(target=self._sample_until_stopped, daemon=True)
        self.sampler.start()

    def _carriers(self) -> dict[int, list[str]]:
        """Each live process that carries the take, by pid, with its `stat` fields from the
        state on."""
        found: dict[int, list[str]] = {}
        for process in PROCS.glob("[0-9]*"):
            with contextlib.suppress(OSError, IndexError):
                if b"\0" + self.key + b"\0" in b"\0" + (process / "environ").read_bytes() + b"\0":
                    found[int(process.name)] = (
                        (process / "stat").read_text().rsplit(")", 1)[1].split()
                    )
        return found

    def _sample(self) -> int:
        """Record the CPU of each carrier whose parent is outside the take, and say how many
        carriers the holder did not start itself."""
        carriers = self._carriers()
        mine = os.getpid()
        self.left |= {
            (pid, fields[19]): (
                (int(fields[11]) + int(fields[13])) / self.tick,
                (int(fields[12]) + int(fields[14])) / self.tick,
            )
            for pid, fields in carriers.items()
            if int(fields[1]) != mine and int(fields[1]) not in carriers
        }
        return sum(int(fields[1]) != mine for fields in carriers.values())

    def _sample_until_stopped(self) -> None:
        stopped = False
        while not stopped:
            self._sample()
            stopped = self.stop.wait(SAMPLE_SECONDS)

    def end(self) -> tuple[float, float, int]:
        self.stop.set()
        self.sampler.join()
        deadline = time.monotonic() + DRAIN_SECONDS
        while (left := self._sample()) and time.monotonic() < deadline:
            time.sleep(LOOK_SECONDS)
        os.environ.pop(TAKE, None)
        used = resource.getrusage(resource.RUSAGE_CHILDREN)
        user = used.ru_utime - self.used.ru_utime + sum(one[0] for one in self.left.values())
        system = used.ru_stime - self.used.ru_stime + sum(one[1] for one in self.left.values())
        return user, system, left


@dataclass(frozen=True)
class Taken:
    """A slot taken, as its take row says, to pass to `release`."""

    log: Path
    at: datetime
    fields: dict
    tree: _Cgroup | _Carriers


def _repo(cwd: str) -> str:
    """The name of the directory that holds the repository `cwd` is in, so every worktree of a
    repository has one name, and nothing outside a repository."""
    if not cwd:
        return ""
    try:
        found = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return Path(found.stdout.strip()).parent.name if found.returncode == 0 else ""


def take(
    log: Path, lane: str, slot: int, slots: int, thread: str, command: list[str], waited: float
) -> Taken:
    now = datetime.now(UTC)
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = ""
    fields = {
        "id": secrets.token_hex(6),
        "pid": os.getpid(),
        "lane": lane,
        "slot": slot,
        "slots": slots,
        "thread": thread,
        "command": command,
        "cwd": cwd,
    }
    row = {"at": _stamp(now), "event": "take", **fields, "waited": round(waited, 3)}
    _append(log, {**row, "repo": _repo(cwd)})
    return Taken(log, now, fields, _Cgroup.make(fields["id"]) or _Carriers(fields["id"]))


def release(taken: Taken, code: int) -> None:
    """Write the release row, with the CPU of every process of the take, once they have ended or
    `DRAIN_SECONDS` have gone by: the sweep runs after the release, and is not counted. A take
    whose CPU cannot be read writes its row with no CPU and no `left`, and stops no run."""
    try:
        user, system, left = taken.tree.end()
    except (OSError, ValueError):
        cpu = {}
    else:
        cpu = {"cpu_user": round(user, 3), "cpu_system": round(system, 3), "left": left}
    now = datetime.now(UTC)
    held = (now - taken.at).total_seconds()
    _append(
        taken.log,
        {
            "at": _stamp(now),
            "event": "release",
            **taken.fields,
            "code": code,
            "hold": round(held, 3),
            **cpu,
        },
    )


@dataclass(frozen=True)
class Hold:
    lane: str
    slots: int
    start: float
    end: float | None
    pid: int
    waited: float
    repo: str = ""
    cpu: tuple[float, float] | None = None


def _rows(log: Path) -> Iterator[dict]:
    """The rows of a JSON lines file, each with its `at` in seconds since the epoch, and none
    of the lines that are not such a row."""
    for line in log.read_text().splitlines():
        try:
            row = json.loads(line)
            row["at"] = datetime.fromisoformat(row["at"]).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        yield row


def holds(log: Path) -> list[Hold]:
    """Every take in the log with the time of its release, or None for a take with none."""
    taken: dict[str, dict] = {}
    ended: dict[str, dict] = {}
    for row in _rows(log):
        if row.get("event") == "take":
            taken[row["id"]] = row
        elif row.get("event") == "release":
            ended[row["id"]] = row
    found = []
    for key, row in taken.items():
        end = ended.get(key, {})
        cpu = (end["cpu_user"], end["cpu_system"]) if "cpu_user" in end else None
        found.append(
            Hold(
                row["lane"],
                row["slots"],
                row["at"],
                end.get("at"),
                row["pid"],
                row["waited"],
                row.get("repo", ""),
                cpu,
            )
        )
    return found


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _held(spans: list[tuple[float, float]], start: float, end: float) -> float:
    return sum(max(0.0, min(b, end) - max(a, start)) for a, b in spans)


def _quantile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def _waits(start: float, end: float) -> dict[str, list[tuple[float, float]]]:
    """The spans in which a thread waited for a slot of each lane, from jbus's `slot-wake`
    events: each ends at its wake and began its minutes before."""
    found: dict[str, list[tuple[float, float]]] = {}
    for events in sorted(sample.jbus_state().glob("*/events.jsonl")):
        for row in _rows(events):
            said = WAKE.match(str(row.get("line") or ""))
            if row.get("event") != "slot-wake" or not said:
                continue
            woke = row["at"]
            began = woke - 60 * int(said[2])
            if woke > start and began < end and woke > began:
                found.setdefault(said[1], []).append((max(began, start), min(woke, end)))
    return found


def _union(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def _cpu(released: list[Hold], span: float) -> list[str]:
    """The CPU seconds of the holds released in the span, by lane and by repo, each with the mean
    cores it comes to over the span. A release written before the log had the CPU has none, and
    is counted apart, and a span with no release that has the CPU prints no CPU lines."""
    measured = [(one, one.cpu) for one in released if one.cpu is not None]
    if not measured:
        return []
    lines = [
        f"  CPU of the {len(measured)} holds released in the span, user + system seconds, and the"
        " mean cores over the span:"
    ]
    if len(measured) < len(released):
        lines[0] += f" ({len(released) - len(measured)} more released with no CPU on record)"
    for by, key in (("lane", lambda one: one.lane), ("repo", lambda one: one.repo or "(none)")):
        totals: dict[str, list[float]] = {}
        for one, (user, system) in measured:
            total = totals.setdefault(key(one), [0.0, 0.0])
            total[0] += user
            total[1] += system
        ranked = sorted(totals.items(), key=lambda item: -sum(item[1]))
        lines += [
            f"    {by} {name}: {user + system:.1f} s ({user:.1f} + {system:.1f}),"
            f" {(user + system) / span:.2f} cores"
            for name, (user, system) in ranked
        ]
    return lines


def report(log: Path, start: float | None, until: float | None, now: float) -> list[str]:
    """The slot section of `jgauge sample --report`, and nothing when there is no log."""
    if not log.exists():
        return []
    every = holds(log)
    if not every:
        return [f"test slots: no holds in {log}"]
    start = min(one.start for one in every) if start is None else start
    end = now if until is None else min(until, now)
    if end <= start:
        return [f"test slots: the span is empty in {log}"]
    span = end - start
    lines = [
        f"test slots, from {log}, {datetime.fromtimestamp(start):%Y-%m-%d %H:%M:%S}"
        f" to {datetime.fromtimestamp(end):%Y-%m-%d %H:%M:%S} ({span / 3600:.2f} h):"
    ]
    waited_for = _waits(start, end)
    for lane in ("full", "short"):
        mine = [one for one in every if one.lane == lane]
        if not mine:
            continue
        alive = [one for one in mine if one.end is None and _alive(one.pid)]
        spans = [(one.start, one.end) for one in mine if one.end is not None]
        spans += [(one.start, end) for one in alive]
        inside = [one for one in mine if start <= one.start < end]
        lost = sum(one.end is None and one not in alive for one in inside)
        held = _held(spans, start, end)
        size = max(one.slots for one in inside or mine)
        done = [one.end - one.start for one in inside if one.end is not None]
        little = len(inside) / span * statistics.fmean(done) if done else 0.0
        waits = [one.waited for one in inside]
        wait = (
            f"wait in the call p50 {_quantile(waits, 0.5):.1f} s, p90 {_quantile(waits, 0.9):.1f} s"
            if waits
            else "no wait"
        )
        lines.append(
            f"  {lane}: {len(inside)} holds, {lost} lost; mean occupancy"
            f" {held / span:.3f} of {size} slots; Little's law (takes/s x mean hold)"
            f" {little:.3f}; {wait}"
        )
        waiting = _union(waited_for.get(lane, []))
        if waiting:
            length = sum(b - a for a, b in waiting)
            occupied = sum(_held(spans, a, b) for a, b in waiting) / length
            share = f" ({100 * occupied / size:.0f}% of {size})" if size else ""
            lines.append(
                f"  {lane}, while a thread waited for a slot ({length / 3600:.2f} h, from"
                f" {len(waited_for[lane])} slot-wake events): mean occupancy"
                f" {occupied:.2f}{share}"
            )
    released = [one for one in every if one.end is not None and start <= one.end < end]
    if released:
        lines += _cpu(released, span)
    return lines
