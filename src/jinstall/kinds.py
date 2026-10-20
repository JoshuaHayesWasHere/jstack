"""The kinds of need, and what each one's answer rests on.

A Kind is only probed: the doctor says what it found, and the install never writes it. One
that `Asks` gives `--setup` the one command the user runs to mend it. The configs are read
through `jbus.load`, `jsettings.load` and `jroles.read_map`, the loaders the commands use, so
the doctor cannot disagree with them about what is valid. A Seeded kind is a config `--setup`
writes once, where there is no file, and `--uninstall` removes while it is still what was
written (`Machine.seed`). A Carried kind is also put and dropped, and every Carried kind writes
the checkout's path into what it puts, which gives the one ownership rule: a piece is this
checkout's when the piece itself says so.

    ok       exactly what this checkout puts is there, or the program meets its floor
    missing  nothing is there
    old      something is there and it is not that: `detail` says what
"""

import copy
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jbus
import jleak
import jroles
import jsettings
from jbus import t3
from jgauge import limits
from jinstall.machine import Dropped, JsonObject, Machine, Moved, Refused, same_bytes
from jroles.inventory import BUILT_IN, Instance, declared, instances


class State(Enum):
    OK = "ok"
    MISSING = "missing"
    OLD = "old"


@dataclass(frozen=True)
class Found:
    """One probe's answer, built only by the four constructors. `replaceable` is False only
    for `foreign`: something that is not jstack's is where the part goes, and neither install
    nor uninstall touches it."""

    state: State
    detail: str = ""
    replaceable: bool = True

    @classmethod
    def ok(cls, detail: str = "") -> "Found":
        return cls(State.OK, detail)

    @classmethod
    def missing(cls, how: str = "") -> "Found":
        return cls(State.MISSING, how)

    @classmethod
    def old(cls, what: str) -> "Found":
        return cls(State.OLD, what)

    @classmethod
    def foreign(cls, what: str) -> "Found":
        return cls(State.OLD, what, replaceable=False)


class Kind(Protocol):
    def probe(self, machine: Machine) -> Found:
        """Read-only. Never raises: a probe that cannot tell answers old with the reason."""
        ...


@runtime_checkable
class Carried(Kind, Protocol):
    def due(self, machine: Machine) -> bool:
        """Whether this machine asks for the part: read from the machine, never from a flag.
        A part that is not due is not listed and not put. --uninstall drops it all the same."""
        ...

    def put(self, machine: Machine) -> None:
        """Make the probe answer ok. Called only on missing or on a replaceable old.
        Safe to run twice and safe to stop halfway."""
        ...

    def drop(self, machine: Machine) -> Dropped:
        """Remove each piece that is this checkout's and leave every other."""
        ...


@runtime_checkable
class Asks(Kind, Protocol):
    def ask(self, machine: Machine) -> str:
        """The one command that mends what the probe found, for `--setup` to print."""
        ...


@runtime_checkable
class Seeded(Kind, Protocol):
    """A config `--setup` writes, once, at `path` with `mode`, only where probe says missing."""

    path: Path
    mode: int

    def text(self, machine: Machine) -> str:
        """What is written: read from the machine, every value one its loader takes."""
        ...

    def drop(self, machine: Machine) -> Dropped:
        """Remove the file while it is what `--setup` wrote, else keep it, with why."""
        ...


def unseed(machine: Machine, path: Path, word: str) -> Dropped:
    removed = machine.unseed(path)
    if removed is None:
        return Dropped()
    if not removed:
        return Dropped(kept=(f"{word} {path} -> yours, it is not as setup wrote it",))
    return Dropped(removed=(f"{word} {path}",))


SEEDED = "# Written once by install.sh --setup. Edit it: setup never writes over it.\n"


def get(machine: Machine, package: str, command: str) -> str:
    """How to get a program: `yay -S <package>` on Arch (pacman on PATH), else its name."""
    return f"yay -S {package}" if machine.which("pacman") else command


def points_at(path: Path, target: Path) -> bool:
    return path.is_symlink() and os.readlink(path) == str(target)


def dead(path: Path, checkout: Path) -> bool:
    """Whether `path` is a link into the checkout's `skills/` at a skill that is not there."""
    return (
        path.is_symlink()
        and os.readlink(path).startswith(f"{checkout / 'skills'}{os.sep}")
        and not (path / "SKILL.md").is_file()
    )


@dataclass(frozen=True)
class Link:
    """A symlink into the checkout: a skill for an agent.
    old: a link to anywhere else. foreign: `not a link`.
    drop: unlink only when it points at `target`."""

    path: Path
    target: Path

    def probe(self, machine: Machine) -> Found:
        if self.path.is_symlink():
            to = os.readlink(self.path)
            return Found.ok() if to == str(self.target) else Found.old(to)
        return Found.foreign("not a link") if self.path.exists() else Found.missing()

    def due(self, machine: Machine) -> bool:
        return True

    def put(self, machine: Machine) -> None:
        machine.link(self.path, self.target)

    def drop(self, machine: Machine) -> Dropped:
        if not points_at(self.path, self.target):
            return Dropped()
        machine.unlink(self.path)
        return Dropped(removed=(str(self.path),))


@dataclass(frozen=True)
class GoneLink:
    """A link under a skills root that points into this checkout's `skills/` at a skill the
    checkout no longer has. Listed only when found, old until it is unlinked. put and drop
    unlink it."""

    path: Path

    def _dead(self, machine: Machine) -> bool:
        return dead(self.path, machine.checkout)

    def probe(self, machine: Machine) -> Found:
        if self._dead(machine):
            return Found.old(f"{os.readlink(self.path)}, a skill this checkout no longer has")
        return Found.ok("unlinked")

    def due(self, machine: Machine) -> bool:
        return True

    def put(self, machine: Machine) -> None:
        if self._dead(machine):
            machine.unlink(self.path)

    def drop(self, machine: Machine) -> Dropped:
        if not self._dead(machine):
            return Dropped()
        machine.unlink(self.path)
        return Dropped(removed=(str(self.path),))


def quoted(path: Path) -> str:
    """One shell word, always in single quotes, so the text put is the same on every machine."""
    return "'" + str(path).replace("'", "'\\''") + "'"


def rewrite(machine: Machine, file: Path, change: Callable[[dict], bool]) -> bool:
    """Read `file`, let `change` edit a copy of its object, and write it when `change` says
    it did something. A file that moved under the write is read again, once."""
    for attempt in (1, 2):
        was = machine.read_object(file)
        if not isinstance(was, JsonObject):
            raise Refused(f"{file} is {was.why}")
        value = copy.deepcopy(was.value)
        if not change(value):
            return False
        try:
            machine.write_object(was, value)
        except Moved:
            if attempt == 2:
                raise
        else:
            return True
    return False


@dataclass(frozen=True)
class HookGroup:
    """One group in `.hooks[event]` of ~/.claude/settings.json or ~/.codex/hooks.json:
        {"matcher": <matcher>, "hooks": [{"type": "command",
          "command": "sh '<checkout>/<script>' 2>/dev/null || true", "timeout": 5}]}
    with no `matcher` key when `matcher` is None. With `refuses` the command is
    "sh '<checkout>/<script>'" and nothing after it: the hook's exit code and what it writes
    to stderr are how it refuses a tool call, so neither is thrown away, and its timeout is
    30: it starts Python, and a hook that ran out of time has refused nothing.

    ok: that group is there, and no other command of the event names `/<script>`.
    old: a command names `/<script>` and is not that (another checkout, or the README's
      hand-written `"$HOME/..."` form). put takes each such command out and adds the group.
    foreign: the file is not one JSON object with a hooks object: `not a hooks file`.
    drop: take out only the command that is exactly this checkout's, then each of the group,
      `hooks[event]` and `hooks` that it leaves empty. No other key is touched."""

    file: Path
    event: str
    matcher: str | None
    script: str
    refuses: bool = False

    def _command(self, machine: Machine) -> str:
        run = f"sh {quoted(machine.checkout / self.script)}"
        return run if self.refuses else f"{run} 2>/dev/null || true"

    def _group(self, machine: Machine) -> dict:
        timeout = 30 if self.refuses else 5
        hook = {"type": "command", "command": self._command(machine), "timeout": timeout}
        return ({} if self.matcher is None else {"matcher": self.matcher}) | {"hooks": [hook]}

    def _groups(self, value: dict) -> list | None:
        """The event's groups, or None when `value` is not shaped as a hooks file."""
        hooks = value.get("hooks", {})
        groups = hooks.get(self.event, []) if isinstance(hooks, dict) else None
        shaped = isinstance(groups, list) and all(
            isinstance(group, dict) and isinstance(group.get("hooks", []), list) for group in groups
        )
        return groups if shaped else None

    def _names(self, hook: object) -> bool:
        command = hook.get("command") if isinstance(hook, dict) else None
        return isinstance(command, str) and f"/{self.script}" in command

    def probe(self, machine: Machine) -> Found:
        was = machine.read_object(self.file)
        groups = self._groups(was.value) if isinstance(was, JsonObject) else None
        if groups is None:
            return Found.foreign("not a hooks file")
        named = [
            hook["command"]
            for group in groups
            for hook in group.get("hooks", [])
            if self._names(hook)
        ]
        if self._group(machine) in groups and len(named) == 1:
            return Found.ok()
        return Found.old(named[0]) if named else Found.missing()

    def due(self, machine: Machine) -> bool:
        return True

    def put(self, machine: Machine) -> None:
        def change(value: dict) -> bool:
            groups = self._groups(value)
            if groups is None:
                raise Refused(f"{self.file} is not a hooks file")
            kept = []
            for group in groups:
                if "hooks" in group:
                    group["hooks"] = [hook for hook in group["hooks"] if not self._names(hook)]
                if group.get("hooks") != []:
                    kept.append(group)
            value.setdefault("hooks", {})[self.event] = [*kept, self._group(machine)]
            return True

        rewrite(machine, self.file, change)

    def drop(self, machine: Machine) -> Dropped:
        ours = self._command(machine)

        def change(value: dict) -> bool:
            groups = self._groups(value)
            kept, found = [], False
            for group in groups or []:
                hooks = group.get("hooks", [])
                rest = [
                    hook
                    for hook in hooks
                    if not (isinstance(hook, dict) and hook.get("command") == ours)
                ]
                if len(rest) == len(hooks):
                    kept.append(group)
                    continue
                found = True
                if rest:
                    kept.append(group | {"hooks": rest})
            if not found:
                return False
            value["hooks"][self.event] = kept
            if not kept:
                del value["hooks"][self.event]
            if not value["hooks"]:
                del value["hooks"]
            return True

        if not isinstance(machine.read_object(self.file), JsonObject):
            return Dropped()
        if rewrite(machine, self.file, change):
            return Dropped(removed=(f"hook {self.file} {self.event}",))
        return Dropped()


@dataclass(frozen=True)
class GitHook:
    """A hook of the checkout's own repo: a link from <checkout>/.git/hooks/<name> to
    <checkout>/<script>. The worktrees of a repo run the hooks of its main checkout, so the
    one link covers every branch that is pushed from this machine.

    due: when `.git` is a directory (the main checkout, not a worktree, whose hooks are not
      its own), and HOME is the account's own or holds the checkout. A run under another
      HOME, a sandbox or a test, leaves a checkout that is outside that HOME as it is.
    old: a link to anywhere else. foreign: `not a link`, a hook of the user's own, and
      `core.hooksPath is set, so git runs no hook of .git/hooks`, which no put mends.
    drop: unlink only when it points at the script."""

    name: str
    script: str

    def _link(self, machine: Machine) -> Link:
        hooks = machine.checkout / ".git" / "hooks"
        return Link(hooks / self.name, machine.checkout / self.script)

    def probe(self, machine: Machine) -> Found:
        elsewhere = machine.run(
            ["git", "-C", str(machine.checkout), "config", "--get", "core.hooksPath"]
        )
        if elsewhere.code == 0 and elsewhere.out.strip():
            return Found.foreign("core.hooksPath is set, so git runs no hook of .git/hooks")
        return self._link(machine).probe(machine)

    def due(self, machine: Machine) -> bool:
        ours = machine.home == machine.account or machine.checkout.is_relative_to(machine.home)
        return ours and (machine.checkout / ".git").is_dir()

    def put(self, machine: Machine) -> None:
        self._link(machine).put(machine)

    def drop(self, machine: Machine) -> Dropped:
        return self._link(machine).drop(machine)


@dataclass(frozen=True)
class Patterns:
    """The private patterns `jleak` reads, ${XDG_CONFIG_HOME:-~/.config}/jstack/outbound.toml,
    read by jleak's own loader. The install makes the file once, as `jleak.example` gives it
    for this HOME, and never writes it again: what the user adds to it is theirs.

    missing: no file. Both hooks refuse until it is there.
    foreign: the loader refuses it, with the loader's reason. It is not written over.
    drop: remove it only while it is still what the install made. A file that was edited is
      kept, with why."""

    path: Path

    def probe(self, machine: Machine) -> Found:
        try:
            jleak.load(self.path)
        except jleak.Missing:
            return Found.missing()
        except jleak.Invalid as error:
            return Found.foreign(str(error).removeprefix(f"{self.path}: "))
        return Found.ok()

    def due(self, machine: Machine) -> bool:
        return True

    def put(self, machine: Machine) -> None:
        if self.path.exists():
            raise Refused(f"{self.path} is there and is not written over")
        machine.write_text(self.path, jleak.example(machine.home))

    def drop(self, machine: Machine) -> Dropped:
        try:
            made = self.path.read_text() == jleak.example(machine.home)
        except FileNotFoundError:
            return Dropped()
        except (OSError, UnicodeDecodeError):
            made = False
        if not made:
            return Dropped(
                kept=(f"patterns {self.path} -> yours, it is not as the install made it",)
            )
        machine.unlink(self.path)
        return Dropped(removed=(f"patterns {self.path}",))


@dataclass(frozen=True)
class StatusLine:
    """`statusLine` of ~/.claude/settings.json as
    {"type": "command", "command": "sh '<checkout>/hooks/limits.sh'"}.
    due: only when the key is absent or its command names `/hooks/limits.sh`. A status line
      of the user's own is not due and gets no line.
    old: limits.sh of another checkout. drop: delete the key only when it is exactly ours."""

    file: Path
    script: str = "hooks/limits.sh"

    def _ours(self, machine: Machine) -> dict:
        return {"type": "command", "command": f"sh {quoted(machine.checkout / self.script)}"}

    def _there(self, machine: Machine) -> tuple[bool, object]:
        """Whether the file can be read as an object, and its `statusLine`, None when absent."""
        was = machine.read_object(self.file)
        return isinstance(was, JsonObject), was.value.get("statusLine") if isinstance(
            was, JsonObject
        ) else None

    def _names(self, line: object) -> bool:
        command = line.get("command") if isinstance(line, dict) else None
        return isinstance(command, str) and f"/{self.script}" in command

    def probe(self, machine: Machine) -> Found:
        readable, line = self._there(machine)
        if not readable:
            return Found.foreign("not a settings file")
        if line is None:
            return Found.missing()
        if line == self._ours(machine):
            return Found.ok()
        if self._names(line):
            return Found.old(line["command"])
        return Found.foreign("a status line of your own")

    def due(self, machine: Machine) -> bool:
        readable, line = self._there(machine)
        return readable and (line is None or self._names(line))

    def put(self, machine: Machine) -> None:
        def change(value: dict) -> bool:
            value["statusLine"] = self._ours(machine)
            return True

        rewrite(machine, self.file, change)

    def drop(self, machine: Machine) -> Dropped:
        def change(value: dict) -> bool:
            return value.pop("statusLine", None) == self._ours(machine)

        if self._there(machine)[1] != self._ours(machine):
            return Dropped()
        if rewrite(machine, self.file, change):
            return Dropped(removed=(f"statusline {self.file}",))
        return Dropped()


@dataclass(frozen=True)
class Commands:
    """The commands on PATH. `tool` and `names` come from pyproject.toml (`[project].name`
    and the keys of `[project.scripts]`), `was` is the tool's name before the rename.

    ok: `machine.tool_source(tool)` is this checkout, each name is in `machine.tool_bin()`,
      and typing each name runs that file or the one in <checkout>/.venv/bin.
    old: `lacks jdrift jroles` (installed before they were added); `tool jgauge, from before
      the rename`; `an install of <other path>`.
    foreign, since no put mends it: `<name> is shadowed by <path>`, `<name> is not on PATH`.
    missing: no tool of either name.
    foreign: a tool of either name that is no editable install of a checkout (from an index
      or a git url): `tool jstack is not an editable install of a checkout`. It is not put
      over and not dropped.
    put: `uv tool uninstall <was>` when its source is this checkout, then
      `uv tool install --editable <checkout> --reinstall`. Never --force.
    drop: `uv tool uninstall` of `tool`, and of `was`, each only when its source is this
      checkout. Else kept, with the path it is an install of."""

    tool: str
    names: tuple[str, ...]
    was: str = "jgauge"

    def _lacks(self, machine: Machine) -> str:
        lacking = [name for name in self.names if not (machine.tool_bin() / name).exists()]
        return f"lacks {' '.join(lacking)}" if lacking else ""

    def probe(self, machine: Machine) -> Found:
        source, before = machine.tool_source(self.tool), machine.tool_source(self.was)
        renamed = f"tool {self.was}, from before the rename"
        for tool, of in ((self.tool, source), (self.was, before)):
            if of is None and machine.has_tool(tool):
                return Found.foreign(f"tool {tool} is not an editable install of a checkout")
        if source is None and before is None:
            return Found.missing()
        if source is None and before != machine.checkout:
            return Found.foreign(f"tool {self.was}, an install of {before}")
        if source is None:
            return Found.old(", ".join(filter(None, [renamed, self._lacks(machine)])))
        if source != machine.checkout:
            return Found.old(f"an install of {source}")
        if before == machine.checkout:
            return Found.old(f"{renamed}, is still installed")
        if self._lacks(machine):
            return Found.old(self._lacks(machine))
        for name in self.names:
            typed = machine.which(name)
            if typed is None:
                return Found.foreign(f"{name} is not on PATH: {machine.tool_bin()} is not in it")
            if typed not in (machine.tool_bin() / name, machine.checkout / ".venv" / "bin" / name):
                return Found.foreign(f"{name} is shadowed by {typed}")
        return Found.ok()

    def due(self, machine: Machine) -> bool:
        return True

    def _uv(self, machine: Machine, *args: str) -> None:
        ran = machine.uv(*args)
        if ran.code != 0:
            said = ran.out.strip().splitlines()
            raise Refused(f"uv {' '.join(args)}: {said[-1] if said else 'uv is not on PATH'}")

    def put(self, machine: Machine) -> None:
        if machine.tool_source(self.was) == machine.checkout:
            self._uv(machine, "tool", "uninstall", self.was)
        self._uv(machine, "tool", "install", "--editable", str(machine.checkout), "--reinstall")

    def drop(self, machine: Machine) -> Dropped:
        removed, kept = [], []
        for tool in (self.tool, self.was):
            source = machine.tool_source(tool)
            if source == machine.checkout:
                self._uv(machine, "tool", "uninstall", tool)
                removed.append(f"commands {tool}")
            elif source is not None:
                kept.append(f"commands {tool} -> an install of {source}")
            elif machine.has_tool(tool):
                kept.append(f"commands {tool} -> not an editable install of a checkout")
        return Dropped(tuple(removed), tuple(kept))


@dataclass(frozen=True)
class Units:
    """The jbus units: a link from ~/.config/systemd/user/<name> to
    <checkout>/templates/<name> for each of `names` (every templates/*.service and *.timer),
    and each of `timers` enabled.

    due: when jbus is set up (its config is there), or a unit of this checkout's is there.
    ok: every link points at its template, ~/.local/bin/jbus is there (the units run it),
      and, when the manager reads this HOME, each timer is enabled and no reload is due.
      With a manager that reads another HOME (a sandbox) the links alone decide. Under the
      account's own HOME a manager that does not answer is old: nothing enabled the timer.
    old: the detail names the first piece that is not so: `lacks jbus-failed.service`,
      `jbus.timer is not enabled`, `needs daemon-reload`. A regular
      file whose bytes equal its template is a copy made by hand from the README: replaceable.
    foreign: a file that differs from its template: `jbus.service -> not a link, differs`.
      Also what no put mends: `no ~/.local/bin/jbus`, and a manager that did not answer.
    put: refused with no ~/.local/bin/jbus, so no timer is started on a missing program.
      Else make `timers.target.wants` through the machine, link, daemon-reload, enable --now.
    drop: disable --now each timer whose link is ours, unlink each link that points at its
      template, daemon-reload. systemd's disable unlinks a linked unit by itself, and the
      links it left are unlinked here.
    Each systemctl step is `machine.systemctl`, so with a manager that reads another HOME
    only the links are made, checked and removed."""

    directory: Path
    names: tuple[str, ...]
    timers: tuple[str, ...]
    config: Path

    def _template(self, machine: Machine, name: str) -> Path:
        return machine.checkout / "templates" / name

    def _ours(self, machine: Machine) -> list[str]:
        return [
            name
            for name in self.names
            if points_at(self.directory / name, self._template(machine, name))
        ]

    def _wanted(self, timer: str) -> Path:
        return self.directory / "timers.target.wants" / timer

    def due(self, machine: Machine) -> bool:
        return self.config.is_file() or bool(self._ours(machine))

    def probe(self, machine: Machine) -> Found:
        lacking, elsewhere, copies = [], [], []
        for name in self.names:
            path, template = self.directory / name, self._template(machine, name)
            if points_at(path, template):
                continue
            if path.is_symlink():
                elsewhere.append(f"{name} -> {os.readlink(path)}")
            elif not path.exists():
                lacking.append(name)
            elif path.is_file() and same_bytes(path, template):
                copies.append(name)
            else:
                return Found.foreign(f"{name} -> not a link, differs")
        if len(lacking) == len(self.names):
            return Found.missing()
        if lacking:
            return Found.old(f"lacks {' '.join(lacking)}")
        if elsewhere:
            return Found.old(elsewhere[0])
        if copies:
            return Found.old(f"{' '.join(copies)}: a copy of its template, not a link")
        if not (machine.home / ".local" / "bin" / "jbus").exists():
            return Found.foreign("no ~/.local/bin/jbus")
        for timer in self.timers:
            enabled = machine.systemctl("is-enabled", timer)
            if enabled is None and machine.home == machine.account:
                return Found.foreign(f"systemctl --user did not answer, so {timer} is not enabled")
            if enabled is None:
                return Found.ok()
            if enabled.out.strip() != "enabled":
                return Found.old(f"{timer} is not enabled")
        reload = machine.systemctl("show", "--property", "NeedDaemonReload", "--value", *self.names)
        if reload is not None and "yes" in reload.out.split():
            return Found.old("needs daemon-reload")
        return Found.ok()

    def _systemctl(self, machine: Machine, *args: str) -> None:
        ran = machine.systemctl(*args)
        if ran is not None and ran.code != 0:
            said = ran.out.strip().splitlines()
            raise Refused(f"systemctl --user {' '.join(args)}: {said[-1] if said else ran.code}")

    def put(self, machine: Machine) -> None:
        if not (machine.home / ".local" / "bin" / "jbus").exists():
            raise Refused("no ~/.local/bin/jbus for the units to run, so none is linked")
        if self.timers:
            machine.make_dirs(self._wanted(self.timers[0]).parent)
        for name in self.names:
            machine.link(self.directory / name, self._template(machine, name))
        self._systemctl(machine, "daemon-reload")
        for timer in self.timers:
            self._systemctl(machine, "enable", "--now", timer)

    def drop(self, machine: Machine) -> Dropped:
        ours = self._ours(machine)
        if not ours:
            return Dropped()
        for timer in self.timers:
            if timer in ours:
                self._systemctl(machine, "disable", "--now", timer)
                if points_at(self._wanted(timer), self._template(machine, timer)):
                    machine.unlink(self._wanted(timer))
        for name in ours:
            if points_at(self.directory / name, self._template(machine, name)):
                machine.unlink(self.directory / name)
        self._systemctl(machine, "daemon-reload")
        return Dropped(removed=tuple(f"unit {self.directory / name}" for name in ours))


def _numbers(text: str) -> tuple[int, ...]:
    return tuple(int(number) for number in re.findall(r"[0-9]+", text))


@dataclass(frozen=True)
class Program:
    """A program on PATH. missing: not there (detail: `hint`). old: its version is below
    `floor`, or cannot be read. With `floor` None there is no old and the program is not run."""

    command: str
    version: tuple[str, ...] = ("--version",)
    floor: tuple[int, ...] | None = None
    hint: str = ""
    package: str = ""

    def ask(self, machine: Machine) -> str:
        """The hint where there is one, else the Arch package, which is the command's name
        unless `package` says otherwise."""
        return self.hint or get(machine, self.package or self.command, self.command)

    def probe(self, machine: Machine) -> Found:
        if machine.which(self.command) is None:
            return Found.missing(self.hint)
        if self.floor is None:
            return Found.ok()
        said = re.search(r"[0-9]+(\.[0-9]+)+", machine.run([self.command, *self.version]).out)
        if said is None:
            return Found.old("its version could not be read")
        if _numbers(said[0]) < self.floor:
            return Found.old(f"{said[0]}, needs {'.'.join(map(str, self.floor))} or newer")
        return Found.ok(said[0])


@dataclass(frozen=True)
class T3Nightly:
    """T3 Code, asked through the `t3` command the app writes into ~/.t3/bin, else the one on
    PATH. missing: neither is there. old: the stable build, a command that does not answer,
    or a nightly before `floor`, the oldest nightly with every MCP tool jstack calls. `floor`
    is None until that build is written down, and old then means only `not the nightly build`."""

    floor: str | None
    hint: str = "the nightly build (on Arch: t3code-nightly-bin)"

    def ask(self, machine: Machine) -> str:
        return get(machine, "t3code-nightly-bin", "t3")

    def probe(self, machine: Machine) -> Found:
        written = machine.home / ".t3" / "bin" / "t3"
        command = written if os.access(written, os.X_OK) else machine.which("t3")
        if command is None:
            return Found.missing(self.hint)
        ran = machine.run([str(command), "--version"])
        said = re.search(r"[0-9]+(\.[0-9]+)+(-nightly[.0-9]*)?", ran.out)
        if ran.code != 0 or said is None:
            return Found.old("t3 --version did not answer: open the app once")
        if said[2] is None:
            return Found.old(f"{said[0]} is the stable build, needs {self.hint}")
        if self.floor is not None and _numbers(said[0]) < _numbers(self.floor):
            return Found.old(f"{said[0]}, needs {self.floor} or newer")
        return Found.ok(said[0])


@dataclass(frozen=True)
class GhSignIn:
    """missing: `gh auth token` exits non-zero. No network call, and what it prints is not
    read. Never old."""

    def ask(self, machine: Machine) -> str:
        return "gh auth login"

    def probe(self, machine: Machine) -> Found:
        if machine.run(["gh", "auth", "token"]).code == 0:
            return Found.ok()
        return Found.missing("gh auth login")


@dataclass(frozen=True)
class Linux:
    """ok on Linux. missing anywhere else, with the platform as the detail."""

    platform: str = sys.platform

    def probe(self, machine: Machine) -> Found:
        if self.platform.startswith("linux"):
            return Found.ok()
        return Found.missing(f"this is {self.platform}")


def _said(error: Exception) -> str:
    """Why jbus does not take a file: its own refusal, in its words. Anything else its code
    raised is named by its kind alone, since such a message can quote a value of the file."""
    if isinstance(error, jbus.Refused):
        return str(error).removeprefix("refused: ")
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return f"jbus cannot read it: {type(error).__name__}"


@dataclass(frozen=True)
class JbusConfig:
    """jbus's config.toml, read by jbus's own loader. old: the loader refuses it, as it does
    one that group or others can read. The install never writes it: it holds a key.
    Seeded, mode 600, with no project and no key: `server` as the T3 sign-in beside it names
    it, else T3 Code's own address, and `dispatch = false`, so jbus launches nothing until
    the user says. `jbus t3 login` reads the server from it, so it comes first."""

    path: Path
    mode: int = 0o600
    server: str = "http://127.0.0.1:3773"

    def text(self, machine: Machine) -> str:
        try:
            named = json.loads(self.path.with_name("t3.json").read_text()).get("server")
        except (OSError, ValueError, AttributeError):
            named = None
        server = named if isinstance(named, str) and named.startswith("http") else self.server
        return f"{SEEDED}server = {json.dumps(server)}\ndispatch = false\n"

    def drop(self, machine: Machine) -> Dropped:
        return unseed(machine, self.path, "jbus config")

    def probe(self, machine: Machine) -> Found:
        if not self.path.is_file():
            return Found.missing("jbus does not run without it")
        try:
            jbus.load(self.path.parent)
        except Exception as error:
            return Found.old(_said(error))
        return Found.ok()


@dataclass(frozen=True)
class JbusSignIn:
    """t3.json beside the config. missing: `run jbus t3 login`. old: readable by others, or
    past the expiry jbus reads from it, on the day the jstack config's time zone gives it."""

    path: Path

    def ask(self, machine: Machine) -> str:
        return "jbus t3 login"

    def probe(self, machine: Machine) -> Found:
        if not self.path.is_file():
            return Found.missing("run jbus t3 login")
        try:
            jbus.private(self.path)
            expires = t3.expiry(self.path)
        except Exception as error:
            return Found.old(_said(error))
        if expires is None:
            return Found.old("holds no token, run jbus t3 login")
        if expires <= datetime.now(UTC):
            try:
                user = jsettings.load()
            except jsettings.Invalid:
                user = jsettings.DEFAULTS
            return Found.old(f"expired {user.day(expires)}, run jbus t3 login")
        return Found.ok()


@dataclass(frozen=True)
class Limits:
    """One instance's file of the ledger, which `jgauge room` and `jroles` read and the
    `jgauge-limits.timer` keeps fresh, every two minutes.
    missing: no file, nothing read that account yet.
    old: it cannot be read, or it was last written 15 min ago or more, so the reader stopped."""

    path: Path

    def ask(self, machine: Machine) -> str:
        """The timer runs it; one run writes every account's file."""
        return "jgauge limits"

    def probe(self, machine: Machine) -> Found:
        if self.path.is_dir():
            return Found.old("it cannot be read")
        if not self.path.exists():
            return Found.missing("jgauge limits writes it, every 2 min")
        why = limits.stale(self.path, datetime.now(UTC))
        return Found.old(f"{why}: run jgauge limits") if why else Found.ok()


@dataclass(frozen=True)
class StateRepo:
    """The homes' state tree, which `jbus snapshot` commits and pushes to its `origin`.
    ok: a git repo whose top is this directory, with an origin, named in the detail with
    any credentials taken out of it. missing: not a git repo, or no origin to push to."""

    path: Path

    def ask(self, machine: Machine) -> str:
        """The url is the user's own private repository: the command names where it goes."""
        add = f"git -C {self.path} remote add origin <url>"
        if self.probe(machine).detail == "not a git repo":
            return f"git init {self.path} && {add}"
        return add

    def probe(self, machine: Machine) -> Found:
        top = machine.run(["git", "-C", str(self.path), "rev-parse", "--show-toplevel"])
        if top.code != 0 or Path(top.out.strip()).resolve() != self.path.resolve():
            return Found.missing("not a git repo")
        origin = machine.run(["git", "-C", str(self.path), "remote", "get-url", "origin"])
        if origin.code != 0 or not origin.out.strip():
            return Found.missing("no remote")
        return Found.ok(re.sub(r"//[^/@]*@", "//", origin.out.strip()))


@dataclass(frozen=True)
class JstackConfig:
    """${XDG_CONFIG_HOME:-~/.config}/jstack/config.toml, read by the loader the commands use.
    The install never creates it. missing: no file, the commands run on their defaults
    (the detail names each key that has one). old: the loader refuses it.
    Seeded with `user`, the first word of `git config user.name`, and `timezone`, the
    machine's own zone. A value the loader would not take is left out, so its default holds."""

    path: Path
    mode: int = 0o644

    def text(self, machine: Machine) -> str:
        lines = [SEEDED]
        named = machine.run(["git", "config", "user.name"])
        word = (named.out.split() or [""])[0].strip(",") if named.code == 0 else ""
        if word and "," not in word:
            lines.append(f"user = {json.dumps(word)}\n")
        zone = machine.zone()
        try:
            known = zone is not None and str(ZoneInfo(zone)) == zone
        except (ZoneInfoNotFoundError, ValueError, OSError):
            known = False
        if known:
            lines.append(f"timezone = {json.dumps(zone)}\n")
        return "".join(lines)

    def drop(self, machine: Machine) -> Dropped:
        return unseed(machine, self.path, "config")

    def probe(self, machine: Machine) -> Found:
        if not self.path.exists():
            return Found.missing(f"defaults are used: {', '.join(jsettings.KEYS)}")
        try:
            jsettings.load(self.path)
        except jsettings.Invalid as error:
            return Found.old(str(error))
        return Found.ok()


@dataclass(frozen=True)
class Roles:
    """${XDG_CONFIG_HOME:-~/.config}/jstack/roles, the role map `jroles` reads.
    missing: no file, every role inherits. old: `jroles.read_map` refuses it, with its lines.
    Seeded with every role `inherit`, which names no effort: nothing is seeded above medium."""

    path: Path
    mode: int = 0o644

    def probe(self, machine: Machine) -> Found:
        try:
            text = self.path.read_text()
        except FileNotFoundError:
            return Found.missing("every role inherits the model of the thread that launches it")
        except (OSError, UnicodeDecodeError):
            return Found.old("it cannot be read")
        try:
            jroles.read_map(text, jroles.ROLES[0])
        except jroles.Refused as error:
            return Found.old("; ".join(str(error).splitlines()))
        return Found.ok()

    def text(self, machine: Machine) -> str:
        return SEEDED + "".join(f"{role}: {jroles.INHERIT}\n" for role in jroles.ROLES)

    def drop(self, machine: Machine) -> Dropped:
        return unseed(machine, self.path, "roles")


def claude_homes(declared: dict[str, Instance], home: Path) -> list[Path]:
    """The home of each declared Claude instance, `~/.claude` for none, each once."""
    homes = [each.home or home / ".claude" for each in declared.values() if each.driver == BUILT_IN]
    return list(dict.fromkeys(homes))


@dataclass(frozen=True)
class ProviderInventory:
    """${XDG_CONFIG_HOME:-~/.config}/jstack/providers.json, the provider instances this
    machine should run, in T3's `providerInstances` shape. infra's install links it there;
    jstack only reads it. missing: no file, so nothing is declared. old: not that shape."""

    path: Path

    def ask(self, machine: Machine) -> str:
        """infra declares the instances, and its install links the file here."""
        return "run infra's install"

    def probe(self, machine: Machine) -> Found:
        if not self.path.exists():
            return Found.missing(str(self.path))
        found = declared(self.path, machine.home)
        if isinstance(found, str):
            return Found.old(found)
        return Found.ok(f"{len(found)} declared")


@dataclass(frozen=True)
class ProviderInstance:
    """One declared instance against T3's own settings, which are only read.
    ok: T3 lists it with the declared driver, enabled and homePath, or it is T3's built-in
    `claudeAgent`, declared with no other home and not listed. missing: T3 does not list it.
    old: T3 lists it otherwise, or its settings cannot be read."""

    name: str
    instance: Instance
    settings: Path

    def probe(self, machine: Machine) -> Found:
        try:
            listed = json.loads(self.settings.read_text()).get("providerInstances", {})
        except FileNotFoundError:
            listed = {}
        except (OSError, UnicodeDecodeError, ValueError, AttributeError):
            return Found.old(f"T3's settings cannot be read: {self.settings}")
        if not isinstance(listed, dict):
            return Found.old("T3's settings: providerInstances is not an object")
        found = instances(
            {self.name: listed[self.name]} if self.name in listed else {}, machine.home
        )
        if isinstance(found, str):
            return Found.old(f"T3's settings: {found}")
        want = self.instance
        if self.name not in found:
            central = want.home in (None, machine.home / ".claude")
            if self.name == BUILT_IN and want.driver == BUILT_IN and want.enabled and central:
                return Found.ok("T3's built-in instance")
            return Found.missing("T3 does not list it")
        there = found[self.name]
        if there.driver != want.driver:
            return Found.old(f"T3's driver is {there.driver}, declared {want.driver}")
        if there.enabled != want.enabled:
            return Found.old(f"T3 lists it {'enabled' if there.enabled else 'disabled'}")
        if there.home != want.home:
            said, meant = _short(there.home, machine), _short(want.home, machine)
            return Found.old(f"T3's homePath is {said}, declared {meant}")
        return Found.ok()


def _short(path: Path | None, machine: Machine) -> str:
    if path is None:
        return "none"
    if path.is_relative_to(machine.home):
        return f"~/{path.relative_to(machine.home)}"
    return str(path)


@dataclass(frozen=True)
class HomeSkills:
    """A Claude home's `skills`, which must be the central jstack skills: the same directory
    as `central` (~/.claude/skills), or entries each of which resolves into `skills`, the
    checkout's. Hidden entries are the agent's own and are not counted. missing: no skills
    there. old: where a linked `skills` points, else the first entry that points elsewhere."""

    home: Path
    central: Path
    skills: Path

    def probe(self, machine: Machine) -> Found:
        path = self.home / "skills"
        if not path.exists():
            return Found.missing(f"link it to {self.central}")
        if self.central.exists() and os.path.samefile(path, self.central):
            return Found.ok()
        if not path.is_dir():
            return Found.old(f"{os.path.realpath(path)} is not a directory")
        ours = os.path.realpath(self.skills)
        try:
            entries = sorted(each for each in path.iterdir() if not each.name.startswith("."))
        except OSError:
            return Found.old("it cannot be listed")
        stray = next(
            (each for each in entries if os.path.dirname(os.path.realpath(each)) != ours), None
        )
        if entries and stray is None:
            return Found.ok()
        if path.is_symlink() or stray is None:
            return Found.old(os.path.realpath(path))
        return Found.old(f"{stray} points at {os.path.realpath(stray)}")
