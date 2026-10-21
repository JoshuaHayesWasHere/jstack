"""The machine's sizes: how many full test slots, how many short ones, and the crew cap.

Three numbers in jstack are sizes of the machine and not design choices. Each has a default,
derived here from whole-machine facts, and one local home where the owner may set it:

- `test_slots`, read by `jgauge test-slot` and by `jbus poll` for its waiters, set in
  `~/.config/jstack/machine.toml`;
- `short_slots`, read the same way for the short lane, set in the same file;
- `max_running`, the crew cap `jbus` dispatch reads, set in `~/.config/jbus/config.toml`, its
  home before this module: jbus parses that file and hands the raw value here, so its check and
  its default are this module's.

Every caller arrives at the same count because a default reads only whole-machine facts: the
`cpuN` lines of `$PROC/stat` and `MemTotal` of `$PROC/meminfo`. Never the caller's cgroup
quota, its affinity or `nproc`, which differ between `jbus.service`, a desk shell, an agent's
slice and a CI container on the same machine. The Makefile's workers do read the quota, on
purpose: a run's workers are sized to the run, and the machine's slots to the machine.

The order, first that is set wins: `--slots` and `TEST_SLOTS` (the full lane only), the local
home, the derivation. `TEST_SLOTS` is an override for one run: set in a shell profile it is a
count `jbus.service` does not see, and `jgauge sizes` says so.

Room's six lines stay in room.sh, ratios and floors that mean the same on any machine, and the
Makefile keeps its worker share, since CI has no jstack venv. `docs/limits.md` lists every
limit, with what it protects and the measurement it rests on. Nothing here writes a file.
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

DESK_SHARE = 4
"""A desk run's workers are a quarter of the processors, at least two: the Makefile's
`PER_CORE` of `1 / 4` and its floor of 2, which tests/test_check_command.py holds to this by
running `make`. A worker keeps 0.86 of a core busy (yelena, 2026-10-20: 456 to 483 s of CPU
for a 89 to 94 s run at 6 workers), so the full slots, counted from this share, fill the
machine once and no more."""

SUITE_GIB = 4
"""Memory a full slot is given room for: a suite peaks at 1.0 to 1.1 GB (yelena, 2026-10-20),
and the rest is left to the crews and the system."""

CREW_GIB = 2
"""Memory a crew is given room for: an agent is 0.3 GB idle, plus the builds, servers and
short runs it starts outside the slots."""

SHORT_PER_CORES = 8
SHORT_FLOOR = 2
SHORT_CEILING = 8

FALLBACK_CORES = 2
"""The processors taken when none can be read: the Makefile's own fallback."""

FALLBACK_GIB = 4
"""The memory taken when `MemTotal` cannot be read: every count it gives is small."""

_CPU = re.compile(r"^cpu\d+\s", re.M)
_TOTAL = re.compile(r"^MemTotal:\s+(\d+)\s+kB", re.M)
KIB_PER_GIB = 1024 * 1024


class Name(StrEnum):
    """A machine size, by the key it has in its local home."""

    TEST_SLOTS = "test_slots"
    SHORT_SLOTS = "short_slots"
    MAX_RUNNING = "max_running"


IN_FILE = (Name.TEST_SLOTS, Name.SHORT_SLOTS)
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
    """The whole-machine facts a default is derived from. `fell_back` names each fact that
    could not be read and was taken as its fallback: a count is never refused for that."""

    cores: int
    memory_gib: int
    fell_back: tuple[str, ...] = ()

    @classmethod
    def here(cls, proc: Path | None = None) -> Machine:
        """The facts of `proc`, else `$PROC`, else `/proc`, as room.sh reads them, so a test
        gives both one fake tree."""
        root = proc or Path(os.environ.get("PROC") or "/proc")
        fell: list[str] = []
        cores = len(_CPU.findall(_read(root / "stat")))
        if not cores:
            fell.append("cores")
            cores = FALLBACK_CORES
        total = _TOTAL.search(_read(root / "meminfo"))
        if total:
            memory = int(total[1]) // KIB_PER_GIB
        else:
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


def desk_workers(cores: int) -> int:
    """A desk run's workers on `cores` processors, as the Makefile counts them with no quota."""
    return max(2, cores // DESK_SHARE)


def derive(name: Name, machine: Machine) -> int:
    """The default of `name` on `machine`, 1 or more.

    `test_slots`: every full slot at once runs at most one desk worker a processor, and each
    has `SUITE_GIB` of memory; 1, 4, 4, 4, 4 on 2, 8, 12, 24 and 64 cores.
    `short_slots`: one for each `SHORT_PER_CORES` processors, from 2 to 8; a short run holds
    one for at most 120 s, beside the full lane.
    `max_running`: one crew a processor, a crew's heavy work being under the slots, while each
    has `CREW_GIB`; 24 on yelena's 24 cores and 62 GiB.
    """
    cores, memory = machine.cores, machine.memory_gib
    if name is Name.TEST_SLOTS:
        return max(1, min(cores // desk_workers(cores), memory // SUITE_GIB))
    if name is Name.SHORT_SLOTS:
        return min(SHORT_CEILING, max(SHORT_FLOOR, cores // SHORT_PER_CORES))
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
    """`$XDG_CONFIG_HOME/jstack/machine.toml`, `~/.config` with none: beside jsettings' file."""
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "jstack" / "machine.toml"


def count(value: object, said: str, name: Name) -> int:
    """`value` as a count, or `Refused` naming `said`, the flag, variable or file it came from.
    A TOML integer of 1 or more is one, and so is a string of decimal digits, since `--slots`
    and `TEST_SLOTS` arrive as strings. A bool, a float or a word is refused."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    if isinstance(value, str) and value.isdecimal() and int(value) >= 1:
        return int(value)
    raise Refused(f"{said} is {value!r}, and the number of {name} is 1 or more")


def read_file(file: Path | None = None) -> dict[Name, int]:
    """The counts the machine file sets, checked whole, or none where there is no file."""
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
    """The value of `name` and where it came from: the first that is set of `flag` and
    `TEST_SLOTS` (for `test_slots` only), the local home, and `derive`. The local home of the
    slots is `path()`; that of `max_running` is jbus's config, which jbus has parsed: it passes
    the raw value as `written` and the file as `written_in`. Raises `Refused` for a value that
    is set and is not a count, never for a fact it cannot read."""
    machine = machine or Machine.here()
    derived = derive(name, machine)
    env = os.environ if env is None else env
    if name is Name.TEST_SLOTS and flag is not None:
        return Limit(name, count(flag, "--slots", name), From.FLAG, "--slots", derived)
    if name is Name.TEST_SLOTS and env.get("TEST_SLOTS") is not None:
        value = count(env["TEST_SLOTS"], "TEST_SLOTS", name)
        return Limit(name, value, From.ENV, f"TEST_SLOTS={value}", derived)
    if name is Name.MAX_RUNNING:
        if written is not None:
            file = written_in or Path("the jbus config")
            value = count(written, f"max_running in {file}", name)
            return Limit(name, value, From.FILE, str(file), derived)
    else:
        file = path()
        if name in (found := read_file(file)):
            return Limit(name, found[name], From.FILE, str(file), derived)
    return Limit(name, derived, From.DERIVED, f"from {machine.says()}", derived)


def every(jbus_config: Path, env: Mapping[str, str] | None = None) -> tuple[Limit, ...]:
    """The three, each as its own caller gets it: the slots as `jgauge test-slot` sees them in
    `env`, and `max_running` as jbus reads it from `jbus_config` (only that key is read)."""
    machine = Machine.here()
    written = None
    try:
        written = tomllib.loads(jbus_config.read_text()).get("max_running")
    except FileNotFoundError:
        pass
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Refused(f"cannot read max_running from {jbus_config}: {error}") from error
    return (
        resolve(Name.TEST_SLOTS, env=env, machine=machine),
        resolve(Name.SHORT_SLOTS, env=env, machine=machine),
        resolve(Name.MAX_RUNNING, written=written, written_in=jbus_config, machine=machine),
    )
