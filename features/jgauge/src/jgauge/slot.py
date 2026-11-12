"""A test slot: run one command while holding one of N lock files, machine-wide.

A slot is a `flock` on `~/.local/state/locks/test-slot.<n>.lock`. This process holds it, not
the command, so the slot is free again when the command ends or when this process dies. Its
command ends with it, however it dies, SIGKILL too: a watchdog (`jgauge.children`) kills the
command and everything under it once this process is gone, so no command runs on in a slot the
next call takes.

There are two lanes. The full lane is for a whole suite and has N slots, `test_slots` in
`jgauge.sizes`. That module derives the count from the machine unless `--slots`, `TEST_SLOTS`
or the local machine file sets it. The short lane is for a run of a second or a minute, such as
a reviewer's proof or a crewmate's targeted tests. It has slots of its own, `short_slots` in the
same module, with the lock files `test-slot-short.<n>.lock`, so it never waits behind a full
suite. This process stops a command in the short lane at its time limit, so a full suite cannot
keep a short slot. A short command runs in a process group of its own, and the stop and every
signal go to the whole group: a `sh -c` wrapper does not leave its pytest running once the slot
is free. Since that group is out of the terminal's group, an interrupt reaches the command only
through this process, which passes it on.

A thread that cannot wait in a call long does not wait long. In the full lane,
`jgauge test-slot --thread <id>` tries once. With every full slot taken, the call registers the
thread as a waiter (`jgauge.waiters`), with the time the call came as its place, and exits with
code 76. `jbus poll` sends the oldest waiter one message when a full slot is free. That wake
claims the slot for the thread for `waiters.HOLDS`, and every other taker of a full slot takes
one only while the free slots outnumber the claims of other threads (`spare`, the count jbus
wakes waiters by too). It counts and takes under the waiters' lock. With none to spare, a thread
with `--thread` registers as a waiter, as it does with every slot taken, and a caller with no
thread, such as a desk's `make check` or `jmerge`'s guards, waits in its call. The woken thread
then runs its command again. That run takes the slot and takes the thread out of the waiters
file, and with it its claim.

In the short lane the call waits for a slot in the call, for up to `SHORT_WAIT_SECONDS`, and
registers nothing. The callers that wait take the slots freed in the order they came (`_line`),
and jbus does not know of them. A short slot is held for seconds, so the wait is short; a call
still waiting at the ceiling ends 76 and says to run the same command again at once, in the same
turn. No model turn is started to hand a thread a short slot. The ceiling, the lane's run
limit, the stop's grace and the sweep's 60 s fit in the 10 minutes the crew skill gives a slot
call.

A run with `--thread` is on record as its thread's while its command runs, and its end is on
record once the command ends, however it ends (`jgauge.holders`). So jbus counts a thread whose
turn ended during its own run as at work, and wakes it once the run ends.

The command runs with `JGAUGE_TEST_SLOT` set to its lane, `full` or `short`, so a run it starts
knows a slot is held: a TLC model check in a suite takes no second slot, and cannot wait on the
one its own suite holds.

Each slot has a temporary directory of its own on disk, under `/var/tmp` (`SLOTS_ROOT`),
`jgauge-<uid>/<hash of the lock directory>/test-slot.<n>` (or `test-slot-short.<n>`), and the
command runs with `TMPDIR` set to it. It is not under `/tmp`, since a suite's basetemp runs to
hundreds of MiB and `/tmp` may be a tmpfs whose per-user quota it fills. It is not beside the
lock file, since a path with a hidden directory in it, such as `~/.local`, makes asar unpack no
native binaries. So pytest's basetemp,
`pytest-of-<user>` under the temporary directory, is the slot's, for the suite and for every
pytest it starts, and nothing goes to the `pytest-of-<user>` in `/tmp` that every worktree's runs
shared. Pytest's own retention did not keep that one small: a run that was killed never cleaned
up, and runs at once shared its numbering. Only the slot's holder writes in the directory. It
removes the directory when it lets the slot go, however the command ended. A holder that dies
cannot, so the next one to take the slot removes what is left before its command starts.

A slot let go then sweeps the shared `pytest-of-<user>` in `/tmp` (`TMPFS`) with room's sweep: the
runs there over 20 minutes old that no live process holds, which runs outside any slot and runs
that were killed leave, go whatever share of the file slots is used.

Every take and every release, in both lanes, appends one row to the slot log (`jgauge.slotlog`):
the lane, the slot, the thread, the command and its directory, the wait in the call, and on a
release the exit code and the CPU seconds the command used. The release row is written before
the lock is let go, so a slot's next take always comes after it in the log.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jgauge import children, holders, sizes, slotlog, waiters
from jsettings import paths

SHORT_LIMIT_SECONDS = 120.0
SHORT_WAIT_SECONDS = 300.0
AGAIN = "run the same command again now, in this turn"
WAIT_FOR = "JGAUGE_SHORT_WAIT_SECONDS"
LINE = "test-slot-short.line"
LOOK_EVERY_SECONDS = 0.2
STOP_GRACE_SECONDS = 5.0
TIMED_OUT = 124
WAITING = 76
HELD = "JGAUGE_TEST_SLOT"
SLOTS_ROOT = Path("/var/tmp")


@dataclass(frozen=True)
class Lane:
    """Which lock files a command takes, how many there are, and how long it may hold one."""

    lock: str
    slots: int
    called: str
    limit: float | None = None


def full(slots: int) -> Lane:
    return Lane("test-slot", slots, f"{slots} slots")


def short() -> Lane:
    slots = sizes.resolve(sizes.Name.SHORT_SLOTS).value
    return Lane("test-slot-short", slots, f"{slots} short slots", SHORT_LIMIT_SECONDS)


class BadCount(Exception):
    """The slot count that `--slots`, `TEST_SLOTS` or the machine file gives is not a valid
    count."""


def count(asked: str | None) -> int:
    """The full lane's slots: `--slots`, else `TEST_SLOTS`, else the machine file, else the
    machine's derived count."""
    try:
        return sizes.resolve(sizes.Name.TEST_SLOTS, flag=asked).value
    except sizes.Refused as error:
        raise BadCount(str(error)) from error


def locks_dir() -> Path:
    """`JGAUGE_LOCKS_DIR`, else `~/.local/state/locks`. While a test runs it refuses the
    machine's own (`jsettings.paths.RealDir`), as jbus's dirs do: a test's take or wait never
    lands on the machine's slots or its waiters file."""
    return paths._own("JGAUGE_LOCKS_DIR", ".local/state/locks")


def name(lane: Lane) -> str:
    return "short" if lane.limit is not None else "full"


def lane_of(kind: str, slots: int) -> Lane:
    return short() if kind == "short" else full(slots)


def free(lane: Lane) -> int:
    """How many slots of the lane no one holds now. The function tries each slot's lock and lets
    it go at once, and a lock file that is not there is a slot no one has taken."""
    locks, found = locks_dir(), 0
    for n in range(1, lane.slots + 1):
        try:
            held = os.open(locks / f"{lane.lock}.{n}.lock", os.O_RDWR)
        except FileNotFoundError:
            found += 1
            continue
        except OSError:
            continue
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            found += 1
        finally:
            os.close(held)
    return found


def _first_free(locks: Path, lane: Lane) -> tuple[int, Path] | None:
    for n in range(1, lane.slots + 1):
        lock = locks / f"{lane.lock}.{n}.lock"
        held = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(held)
        else:
            return held, lock
    return None


def spare(lane: Lane, held: list[waiters.Waiter], now: datetime, but: str = "") -> int:
    """How many free slots of the lane no woken wait in `held` of a thread other than `but`
    claims. Below zero when more waits claim a slot than are free. `jbus` wakes this many
    waiters, and a take finds a slot only while it is above zero."""
    return free(lane) - waiters.claims(held, name(lane), but, now)


def _claim(locks: Path, lane: Lane, thread: str) -> tuple[tuple[int, Path] | None, bool]:
    """A free slot of the full lane that no woken waiter of another thread claims, taken, and
    whether any slot was free at all. Every taker of the lane comes here, a caller with no
    thread too, and counts and takes under the waiters' lock, so no wake and no other take
    comes between the two. A thread that takes one is no longer a waiter."""
    with waiters.locked(locks) as held:
        room = spare(lane, held, datetime.now(UTC), thread)
        got = _first_free(locks, lane) if room > 0 else None
        any_free = room > 0 or free(lane) > 0
    if got is not None and thread:
        waiters.drop(locks, thread)
    return got, any_free


def _free_for(locks: Path, lane: Lane) -> tuple[int, Path] | None:
    """A slot taken for a caller with no thread, or None: in the full lane only one no woken
    waiter claims (`_claim`), and in the short lane, which has no waiters, any free one."""
    if lane.limit is None:
        return _claim(locks, lane, "")[0]
    return _first_free(locks, lane)


def _ahead(line: Path, ticket: str) -> bool:
    """Whether a caller that came before `ticket` still waits in the line. A ticket whose lock
    no one holds is a caller that died or one that has just gone, and goes."""
    for other in sorted(line.iterdir()):
        if other.name.startswith(".") or other.name == ticket:
            continue
        if other.name > ticket:
            return False
        fd = os.open(other, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            other.unlink(missing_ok=True)
        finally:
            os.close(fd)
    return False


@contextlib.contextmanager
def _line(locks: Path) -> Iterator[Callable[[], bool]]:
    """A place in the line of the callers that wait in the call: a file under `LINE` named for
    the time it came, held with a lock while the caller waits. The file is locked under a
    hidden name and then renamed, so no caller takes a live place for a dead one's. Yields a
    function that says whether this caller is first."""
    line = locks / LINE
    line.mkdir(exist_ok=True)
    ticket = f"{time.time_ns():020d}.{os.getpid()}"
    hidden = line / f".{ticket}"
    fd = os.open(hidden, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        hidden.rename(line / ticket)
        yield lambda: not _ahead(line, ticket)
    finally:
        (line / ticket).unlink(missing_ok=True)
        hidden.unlink(missing_ok=True)
        os.close(fd)


def _ceiling() -> float:
    return float(os.environ.get(WAIT_FOR) or SHORT_WAIT_SECONDS)


def _wait_in_call(locks: Path, lane: Lane, limit: float) -> tuple[int, Path] | None:
    """Wait in the line for up to `limit` for a slot of the lane, and take it. Only the first
    caller in the line takes a slot, so the slots freed go in the order the calls came."""
    until = time.monotonic() + limit
    said = False
    with _line(locks) as first:
        while True:
            if first() and (held := _first_free(locks, lane)) is not None:
                return held
            if time.monotonic() >= until:
                return None
            if not said:
                print(
                    f"test-slot: waiting up to {limit:g} s for one of {lane.called}",
                    file=sys.stderr,
                    flush=True,
                )
                said = True
            time.sleep(LOOK_EVERY_SECONDS)


def take(lane: Lane, thread: str = "", command: list[str] | None = None) -> tuple[int, Path] | None:
    """Wait for a slot and take it, and give the held lock and its file. With a `thread`, the
    short lane waits in the call for up to its ceiling and, with no slot by then, says in one
    line to run the command again now and takes none. The full lane leaves the free slots that
    woken waiters of other threads claim to them, with a thread or with none (`_claim`). With a
    thread it waits for none: with no slot free for it, it registers the thread as a waiter,
    says so in one line, and takes none. A thread that takes a full slot is no longer a waiter.
    With no thread, a call waits in the call until a slot is free for it."""
    locks = locks_dir()
    locks.mkdir(parents=True, exist_ok=True)
    if thread and lane.limit is not None:
        limit = _ceiling()
        held = _wait_in_call(locks, lane, limit)
        if held is None:
            print(
                f"test-slot: every one of {lane.called} was still taken after {limit:g} s and"
                f" nothing ran: {AGAIN}.",
                flush=True,
            )
        return held
    if thread:
        now = datetime.now(UTC)
        held, any_free = _claim(locks, lane, thread)
        if held is not None:
            return held
        waiters.register(locks, thread, name(lane), lane.slots, command or [], now)
        why = (
            f"the free ones of {lane.called} are held for woken waiters"
            if any_free
            else f"every one of {lane.called} is taken"
        )
        print(
            f"test-slot: {why}; {thread} is registered as a waiter"
            " and jbus will wake it when one is free. End your turn.",
            flush=True,
        )
        return None
    said = False
    while (held := _free_for(locks, lane)) is None:
        if not said:
            print(f"test-slot: waiting for one of {lane.called}", file=sys.stderr, flush=True)
            said = True
        time.sleep(LOOK_EVERY_SECONDS)
    return held


def _temporary(lock: Path) -> Path:
    """The temporary directory of the slot whose lock file is `lock`, emptied of what a holder
    that died left in it. The lock files' directory is in its name, so a sandbox's HOME on the
    same machine has one of its own."""
    mine = SLOTS_ROOT / f"jgauge-{os.getuid()}"
    mine.mkdir(mode=0o700, exist_ok=True)
    of = hashlib.sha256(str(lock.parent).encode()).hexdigest()[:12]
    own = mine / of / lock.stem
    shutil.rmtree(own, ignore_errors=True)
    own.mkdir(mode=0o700, parents=True, exist_ok=True)
    return own


def _sweep() -> None:
    """Remove the pytest runs under `/tmp/pytest-of-<user>` that are over 20 minutes old and that
    no live process holds, with room's own sweep, and say how many went. A run outside any slot,
    or one that was killed, leaves its basetemp there, and pytest's retention keeps a killed run's
    for days. A sweep that fails stops nothing: the slot is already let go. The signals go back
    to their defaults first, so a stop told now ends `test-slot` and is not passed to a command
    that has already ended."""
    for told in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(told, signal.SIG_DFL)
    try:
        swept = subprocess.run(
            ["sh", str(Path(__file__).with_name("room.sh")), "sweep"],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    removed = swept.stdout.decode(errors="replace").strip()
    if removed.isdecimal() and int(removed):
        where = os.environ.get("TMPFS") or "/tmp"
        print(
            f"test-slot: removed {removed} stale pytest directories under {where}", file=sys.stderr
        )


def _signal(child: subprocess.Popen, number: int, lane: Lane) -> None:
    """Send the signal to the command, and in the short lane to every process it started, which
    is its process group. A group with no process left to signal is no fault: Linux says ESRCH,
    and macOS says EPERM while a zombie of the group waits to be reaped, as an orphan does until
    launchd gets to it."""
    if lane.limit is None:
        child.send_signal(number)
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(child.pid, number)


def _stop(child: subprocess.Popen, program: str, lane: Lane) -> int:
    print(
        f"test-slot: stopped {program} at {lane.limit:g} s, the short lane's limit",
        file=sys.stderr,
        flush=True,
    )
    _signal(child, signal.SIGTERM, lane)
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.wait(timeout=STOP_GRACE_SECONDS)
    _signal(child, signal.SIGKILL, lane)
    child.wait()
    return TIMED_OUT


def run(command: list[str], lane: Lane, thread: str = "", wake: list[str] | None = None) -> int:
    """Run `command` under a slot of `lane`. A waiter of the full lane registers `wake`, what the
    thread runs again once jbus wakes it, which is `command` itself unless the caller names
    another."""
    asked = time.monotonic()
    took = take(lane, thread, wake or command)
    if took is None:
        return WAITING
    held, lock = took
    logged = slotlog.take(
        slotlog.path(lock.parent),
        name(lane),
        int(lock.name.split(".")[-2]),
        lane.slots,
        thread,
        command,
        time.monotonic() - asked,
    )
    own = _temporary(lock)
    child: subprocess.Popen | None = None
    mine: holders.Holder | None = None
    code: int | None = None
    early: list[int] = []

    def pass_on(number: int, _frame: object) -> None:
        if child is None:
            early.append(number)
        else:
            _signal(child, number, lane)

    def drop(_number: int, _frame: object) -> None:
        """In the default lane an interrupt is the command's to take, and the holder waits for it
        to end. A handler and not SIG_IGN, set before the command starts: the command would
        inherit SIG_IGN, and an interrupt that came while it started would end the holder."""

    for told in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(told, pass_on)
    signal.signal(signal.SIGINT, drop if lane.limit is None else pass_on)
    watch = children.Watch(group=lane.limit is not None)
    try:
        child = subprocess.Popen(
            command,
            env={**os.environ, HELD: name(lane), "TMPDIR": str(own)},
            process_group=None if lane.limit is None else 0,
            preexec_fn=watch.announce,
        )
    except OSError as error:
        print(f"test-slot: {command[0]}: {error.strerror}", file=sys.stderr)
        code = 126 if isinstance(error, PermissionError) else 127
        return code
    else:
        for number in early:
            _signal(child, number, lane)
        if thread:
            mine = holders.hold(
                lock.parent, thread, name(lane), child.pid, command, datetime.now(UTC)
            )
        try:
            code = child.wait(timeout=lane.limit)
        except subprocess.TimeoutExpired:
            code = _stop(child, command[0], lane)
        else:
            code = code if code >= 0 else 128 - code
        return code
    finally:
        watch.done()
        if mine is not None:
            holders.end(lock.parent, mine.id, 1 if code is None else code, datetime.now(UTC))
        shutil.rmtree(own, ignore_errors=True)
        slotlog.release(logged, 1 if code is None else code)
        watch.reap()
        os.close(held)
        _sweep()
