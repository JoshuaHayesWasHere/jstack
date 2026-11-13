"""The machine's sizes: the full test slots, the short ones, the workers they share, the crew cap.

Four numbers in jstack are sizes of the machine and not design choices. This module derives
a default for each from whole-machine facts. Each number also has one local home, a file where
the owner may set it:

- `test_slots`, read by `jgauge test-slot` and by `jbus poll` for its waiters, set in
  `~/.config/jstack/machine.toml`;
- `short_slots`, read the same way for the short lane, set in the same file;
- `workers`, the budget: the test workers both lanes' slots may run at once, the processors
  unless the owner sets it in the same file. Both lanes are sized inside it, the short lane
  too, so with every slot taken the slots' workers fit the cores;
- `max_running`, the crew cap that `jbus` reads when it dispatches, set in
  `~/.config/jbus/config.toml`, where it lived before this module. jbus parses that file and
  passes the raw value here, so this module checks the value and gives its default.

Every caller arrives at the same count because the module derives a default from whole-machine
facts only: the `cpuN` lines of `$PROC/stat` and `MemTotal` of `$PROC/meminfo`, or on macOS
`hw.ncpu` and `hw.memsize` from `sysctl`. The module never reads the caller's cgroup quota, its
affinity or `nproc`, which differ between `jbus.service`, a desk shell, an agent's slice and a
CI container on the same machine. The
Makefile does read the quota for its workers, on purpose: it sizes a run's workers to the run,
and this module sizes the machine's slots to the machine.

The module takes the first source that is set, in this order: `--slots` and `TEST_SLOTS` (the
full lane only), the local home, the derivation. `TEST_SLOTS` overrides the count for one run.
Set in a shell profile, it is a count that `jbus.service` does not see, and `jgauge sizes` says
so.

Room's six lines stay in room.sh: they are ratios and floors that mean the same on any machine.
The Makefile keeps its worker share, since CI has no jstack venv.
`features/jgauge/docs/limits.md` lists every limit, with what it protects and the measurement
behind it. No function here writes a file.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

DESK_SHARE = 8
"""A desk run's workers are an eighth of the processors, at least two: the Makefile's
`PER_CORE` of `1 / 8` and its floor of 2, which testing/tests/test_check_command.py holds to this by
running `make`. It was a quarter until sc-short-lane-budget (2026-11-12): the owner's 4 full slots
of 6 workers filled yelena's 24 cores before any short slot, so each full slot now takes 3 and
the 4 of them 12 of the 24. A worker keeps 0.86 of a core busy (yelena, 2026-10-20: 456 to 483 s
of CPU for a 89 to 94 s run at 6 workers)."""

SUITE_GIB = 4
"""Memory a full slot is given room for: a suite peaks at 1.0 to 1.1 GB (yelena, 2026-10-20),
and the rest is left to the crews and the system."""

CREW_GIB = 2
"""Memory a crew is given room for: an agent is 0.3 GB idle, plus the builds, servers and
short runs it starts outside the slots."""

SHORT_WORKERS = 3
"""The workers of a run in the short lane: the Makefile's `SHORT_WORKERS` under
`JGAUGE_TEST_SLOT=short`, and the crew's proved.sh in a short slot, which
testing/tests/test_check_command.py and features/crew/tests/test_crew_proved.py hold to this.
Measured on yelena, 24 processors at load 11 to 27, 2026-11-09: five test files a crew runs
alone (test_docs_tree, test_bash32, test_jbus_telemetry, test_jbus_steps, test_jbus_queue),
5 rounds each, each run in a short slot, the sums of the medians in CPU and wall seconds:
`-n auto` 147.7 and 31.1, 6 workers 87.7 and 33.6, 4 workers 79.9 and 37.9, 3 workers 77.3 and
44.0, 2 workers 74.5 and 57.9, no xdist 71.6 and 100.6. Each worker spends about 3 CPU s
importing and collecting. Three spends 12% less CPU than 6 for 31% more wall time, and 48% less
than `-n auto`; 2 saves 4% more CPU for 32% more wall time again. It was 4 until
sc-short-lane-budget (2026-11-12): at 3 the owner's 4 short slots are 12 workers, half of
yelena's 24 cores."""

SHORT_CEILING = 8
"""The most short slots on any machine: past it a machine's cores go to the full lane."""

SHORT_SHARE = 2
"""The short lane has a half of the budget, and the full lane the rest. On yelena's 24 cores
that is 4 short slots of 3 and 4 full slots of 3, 24 workers: the owner's 4 full slots ("go with
4 full test slots", 2026-11-12, after eleven threads queued on one), and on 2026-11-12, 00:00 to
22:30 UTC, the slot log's releases spent 8.79 cores in the short lane (32,490 takes at 4
workers), 73% of its 12, and 2.92 in the full lane (3,782), 24% of its 12."""

FALLBACK_CORES = 2
"""The processors taken when none can be read: the Makefile's own fallback."""

FALLBACK_GIB = 4
"""The memory taken when `MemTotal` cannot be read: every count it gives is small."""

_CPU = re.compile(r"^cpu\d+\s", re.M)
_TOTAL = re.compile(r"^MemTotal:\s+(\d+)\s+kB", re.M)
KIB_PER_GIB = 1024 * 1024


def online_cores(proc: Path) -> int:
    """The machine's online processors, the `cpuN` lines of `proc`'s `stat`, or 0 where it
    cannot be read. Neither a cgroup's CPU quota nor the caller's affinity changes it, as
    each changes `nproc` and `os.sched_getaffinity`: room.sh counts the same lines."""
    return len(_CPU.findall(_read(proc / "stat")))


class Name(StrEnum):
    """A machine size, by the key it has in its local home."""

    TEST_SLOTS = "test_slots"
    SHORT_SLOTS = "short_slots"
    MAX_RUNNING = "max_running"
    WORKERS = "workers"


IN_FILE = (Name.TEST_SLOTS, Name.SHORT_SLOTS, Name.WORKERS)
"""The keys `machine.toml` may have. `max_running` is not one: its home is jbus's config."""


class From(StrEnum):
    """Where a value came from, in the order `resolve` looks."""

    FLAG = "flag"
    ENV = "env"
    FILE = "file"
    DERIVED = "derived"


class Refused(Exception):
    """A local value that is not a count, or a file that cannot be used. The message is the
    one line to print."""


@dataclass(frozen=True)
class Machine:
    """The whole-machine facts that `derive` computes a default from. `fell_back` names each
    fact that `here` could not read and replaced with its fallback value. A fact that `here`
    could not read never makes a count fail with `Refused`."""

    cores: int
    memory_gib: int
    fell_back: tuple[str, ...] = ()

    @classmethod
    def here(cls, proc: Path | None = None) -> Machine:
        """Read the facts of `proc`, else `$PROC`, else `/proc`, as room.sh reads them. A test
        can then give room.sh and this method the same fake tree. On macOS, which has no
        /proc, read `hw.ncpu` and `hw.memsize` from `sysctl`, unless a /proc is given."""
        if proc is None and from_sysctl():
            cores, memory = sysctl_count("hw.ncpu"), sysctl_count("hw.memsize")
            memory = memory // (KIB_PER_GIB * 1024) if memory else None
        else:
            root = proc or Path(os.environ.get("PROC") or "/proc")
            cores = online_cores(root)
            total = _TOTAL.search(_read(root / "meminfo"))
            memory = int(total[1]) // KIB_PER_GIB if total else None
        fell: list[str] = []
        if not cores:
            fell.append("cores")
            cores = FALLBACK_CORES
        if memory is None:
            fell.append("memory")
            memory = FALLBACK_GIB
        return cls(cores, memory, tuple(fell))

    def says(self) -> str:
        said = f"{self.cores} cores, {self.memory_gib} GiB"
        taken = {"cores": FALLBACK_CORES, "memory": FALLBACK_GIB}
        for fact in self.fell_back:
            said += f" ({fact} not read, taken as {taken[fact]})"
        return said


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def on_darwin() -> bool:
    """Whether this is macOS, which has no /proc. It is read at each call, so a test can set
    `sys.platform`."""
    return sys.platform == "darwin"


def from_sysctl() -> bool:
    """Whether the machine is read from `sysctl` rather than a /proc: on macOS, unless the
    caller names a /proc in `PROC`, as a test's made-up machine does. room.sh decides the same."""
    return on_darwin() and not os.environ.get("PROC")


def sysctl(name: str) -> str:
    """What macOS's `sysctl -n <name>` prints, stripped, or "" when it cannot run or fails.
    room.sh reads the same names."""
    try:
        ran = subprocess.run(
            ["sysctl", "-n", name], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return ran.stdout.strip() if ran.returncode == 0 else ""


def sysctl_count(name: str) -> int | None:
    """`sysctl -n <name>` as a count of 1 or more, or None."""
    said = sysctl(name)
    return int(said) if said.isdecimal() and int(said) > 0 else None


def desk_workers(cores: int) -> int:
    """A desk run's workers on `cores` processors, as the Makefile counts them with no quota."""
    return max(2, cores // DESK_SHARE)


def derive(
    name: Name, machine: Machine, *, workers: int | None = None, short: int | None = None
) -> int:
    """The default of `name` on `machine`, 1 or more.

    `workers`: the budget, the test workers every slot of both lanes may run at once. It is the
    processors, since a worker keeps 0.86 of a core busy. The owner may set another in
    `machine.toml`, and `workers` here is that value.
    `short_slots`: what the budget's `SHORT_SHARE` holds at `SHORT_WORKERS` a slot, from 1 to
    `SHORT_CEILING`.
    `test_slots`: what the budget holds after the short lane, given as `short` where the owner
    sets it, at the desk's workers a slot, from 1, and `SUITE_GIB` of memory a slot.
    That gives 4 full and 4 short slots on 24 cores, 24 workers; 2 and 1 on 8, 7 workers; 5 and
    8 on 64, 64 workers. On 2 cores the floors of one slot a lane give 5 workers, over the
    budget, and `jgauge sizes` says so.
    `max_running`: one crew for each processor, as long as each crew has `CREW_GIB` of memory.
    One crew per processor is enough because a crew's heavy work runs under the slots. That
    gives 24 on yelena's 24 cores and 62 GiB.
    """
    cores, memory = machine.cores, machine.memory_gib
    budget = workers or cores
    desk = desk_workers(cores)
    if name is Name.WORKERS:
        return cores
    if name is Name.SHORT_SLOTS:
        return min(SHORT_CEILING, max(1, budget // SHORT_SHARE // SHORT_WORKERS))
    if name is Name.TEST_SLOTS:
        short = short or derive(Name.SHORT_SLOTS, machine, workers=budget)
        return max(1, min((budget - short * SHORT_WORKERS) // desk, memory // SUITE_GIB))
    return max(1, min(cores, memory // CREW_GIB))


@dataclass(frozen=True)
class Limit:
    """One machine size as a caller gets it: the value, where it came from, and the derived
    value beside it, which is the value itself when nothing overrides it."""

    name: Name
    value: int
    came_from: From
    where: str
    derived: int = field(compare=False)

    def line(self) -> str:
        said = f"{self.name:<12} {self.value:>3}  {self.came_from} {self.where}"
        if self.came_from is not From.DERIVED:
            said += f" (derived: {self.derived})"
        return said


def path() -> Path:
    """`$XDG_CONFIG_HOME/jstack/machine.toml`, or under `~/.config` when that variable is not
    set. The file is beside jsettings' file."""
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "jstack" / "machine.toml"


def count(value: object, said: str, name: Name) -> int:
    """`value` as a count. Otherwise the function raises `Refused`, which names `said`: the
    flag, variable or file that `value` came from.
    A TOML integer of 1 or more is a valid count, and so is a string of decimal digits, since
    `--slots` and `TEST_SLOTS` arrive as strings. The function refuses a bool, a float or a word."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    if isinstance(value, str) and value.isdecimal() and int(value) >= 1:
        return int(value)
    raise Refused(f"{said} is {value!r}, and the number of {name} is 1 or more")


def read_file(file: Path | None = None) -> dict[Name, int]:
    """The counts that the machine file sets, or none where there is no file. The function
    checks the whole file before it returns any count."""
    file = file or path()
    try:
        raw = tomllib.loads(file.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) else "it is not UTF-8"
        raise Refused(f"cannot read {file}: {reason}") from error
    except tomllib.TOMLDecodeError as error:
        raise Refused(f"{file} does not parse: {error}") from error
    unknown = [key for key in raw if key not in IN_FILE]
    if unknown:
        raise Refused(f"{file} has the key {unknown[0]}, not one of {', '.join(IN_FILE)}")
    return {Name(key): count(value, f"{key} in {file}", Name(key)) for key, value in raw.items()}


def resolve(
    name: Name,
    *,
    flag: str | None = None,
    env: Mapping[str, str] | None = None,
    written: object = None,
    written_in: Path | None = None,
    machine: Machine | None = None,
) -> Limit:
    """The value of `name` and where it came from. The first of these that is set wins: `flag`
    and `TEST_SLOTS` (for `test_slots` only), the local home, and `derive`. The local home of
    the slots and of `workers` is `path()`, and the slots are derived inside the `workers` it
    sets. The local home of `max_running` is jbus's config, which jbus has already parsed: jbus
    passes the raw value as `written` and the file as `written_in`. Raises `Refused` for a value
    that is set and is not a count, never for a fact it cannot read."""
    machine = machine or Machine.here()
    env = os.environ if env is None else env
    file, found, unread = path(), {}, None
    if name is not Name.MAX_RUNNING:
        try:
            found = read_file(file)
        except Refused as error:
            unread = error
    derived = derive(
        name, machine, workers=found.get(Name.WORKERS), short=found.get(Name.SHORT_SLOTS)
    )
    if name is Name.TEST_SLOTS and flag is not None:
        return Limit(name, count(flag, "--slots", name), From.FLAG, "--slots", derived)
    if name is Name.TEST_SLOTS and env.get("TEST_SLOTS") is not None:
        value = count(env["TEST_SLOTS"], "TEST_SLOTS", name)
        return Limit(name, value, From.ENV, f"TEST_SLOTS={value}", derived)
    if unread:
        raise unread
    if name is Name.MAX_RUNNING:
        if written is not None:
            file = written_in or Path("the jbus config")
            value = count(written, f"max_running in {file}", name)
            return Limit(name, value, From.FILE, str(file), derived)
    elif name in found:
        return Limit(name, found[name], From.FILE, str(file), derived)
    return Limit(name, derived, From.DERIVED, f"from {machine.says()}", derived)


@dataclass(frozen=True)
class Budget:
    """The test workers both lanes run with every slot taken: each full slot at the desk's
    workers and each short slot at `SHORT_WORKERS`, against `workers`, the budget."""

    full: int
    full_workers: int
    short: int
    workers: Limit

    @property
    def total(self) -> int:
        return self.full * self.full_workers + self.short * SHORT_WORKERS

    def line(self) -> str:
        said = (
            f"{'total':<12} {self.total:>3}  {self.full} full x {self.full_workers}"
            f" + {self.short} short x {SHORT_WORKERS} workers"
        )
        over = self.total - self.workers.value
        if over <= 0:
            return f"{said}, within workers {self.workers.value}"
        return (
            f"{said}, over workers {self.workers.value} by {over}: lower test_slots or"
            f" short_slots, or raise workers, in {path()}"
        )


def every(jbus_config: Path, env: Mapping[str, str] | None = None) -> tuple[Limit | Budget, ...]:
    """The sizes, each as its own caller gets it: the slots as `jgauge test-slot` sees them in
    `env`, and `max_running` as jbus reads it from `jbus_config`, of which the function reads
    only that key. Then the budget and the workers the slots take of it."""
    machine = Machine.here()
    written = None
    try:
        written = tomllib.loads(jbus_config.read_text()).get("max_running")
    except FileNotFoundError:
        pass
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Refused(f"cannot read max_running from {jbus_config}: {error}") from error
    full = resolve(Name.TEST_SLOTS, env=env, machine=machine)
    short = resolve(Name.SHORT_SLOTS, env=env, machine=machine)
    workers = resolve(Name.WORKERS, env=env, machine=machine)
    return (
        full,
        short,
        resolve(Name.MAX_RUNNING, written=written, written_in=jbus_config, machine=machine),
        workers,
        Budget(full.value, desk_workers(machine.cores), short.value, workers),
    )
