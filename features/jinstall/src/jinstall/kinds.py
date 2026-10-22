"""The kinds of need, and what each kind reads to answer its probe.

The install only probes a Kind: the doctor prints what the probe found, and the install never
writes the part. A kind that `Asks` gives `--setup` the one command that the user runs to
repair what the probe found. The kinds
read the configs through `jbus.load`, `jsettings.load` and `jroles.read_map`, the loaders the
commands use, so the doctor cannot disagree with the commands about what is valid.

A Seeded kind is a config that `--setup` writes once, where there is no file. `--uninstall`
removes it while it is still what `--setup` wrote (`Machine.seed`).

The install also puts and drops a Carried kind. Every Carried kind writes the path of a
harness's layout into what it puts (`Machine.layout`, which `jinstall.layout` assembles from a
checkout or a release). That gives the one ownership rule: a piece belongs to this install when
the piece itself names this install's layout.

    ok       exactly what this checkout puts is there, or the program meets its floor
    missing  nothing is there
    old      something is there and differs from what this checkout puts: `detail` names how
"""

import copy
import json
import os
import re
import sys
import tomllib
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
from jinstall.harnesses import HARNESSES
from jinstall.machine import Dropped, JsonObject, Machine, Moved, Refused, same_bytes
from jroles.inventory import BUILT_IN, Instance, declared, instances


class State(Enum):
    OK = "ok"
    MISSING = "missing"
    OLD = "old"


@dataclass(frozen=True)
class Found:
    """One probe's answer, which only the four constructors build. `replaceable` is False
    only for `foreign`, where something that is not jstack's sits where the part goes. Neither
    the install nor the uninstall changes that thing."""

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
        """Read the machine and write nothing. A probe never raises: when it cannot tell, it
        answers old with the reason."""
        ...


@runtime_checkable
class Carried(Kind, Protocol):
    def due(self, machine: Machine) -> bool:
        """Whether this machine needs the part. The answer comes from the machine, never
        from a flag. The install neither lists nor puts a part that is not due, and
        --uninstall drops it all the same."""
        ...

    def put(self, machine: Machine) -> None:
        """Make the probe answer ok. The install calls it only when the probe answers missing,
        or answers an old that is replaceable. It is safe to run twice and safe to stop
        halfway."""
        ...

    def drop(self, machine: Machine) -> Dropped:
        """Remove each piece that is this checkout's, and leave every other piece."""
        ...


@runtime_checkable
class Asks(Kind, Protocol):
    def ask(self, machine: Machine) -> str:
        """The one command that repairs what the probe found, for `--setup` to print."""
        ...


@runtime_checkable
class Seeded(Kind, Protocol):
    """A config that `--setup` writes once, at `path` with `mode`, and only where the probe
    says missing."""

    path: Path
    mode: int

    def text(self, machine: Machine) -> str:
        """The bytes to write. The kind reads them from the machine, and the loader accepts every
        value in them."""
        ...

    def drop(self, machine: Machine) -> Dropped:
        """Remove the file while it is what `--setup` wrote. Otherwise keep it, and say
        why."""
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
    """How to get a program. On Arch, where pacman is on PATH, it is `yay -S <package>`, and
    elsewhere it is the program's name."""
    return f"yay -S {package}" if machine.which("pacman") else command


GENERATE = "scripts/generate-jstack-trees.py"


def points_at(path: Path, target: Path) -> bool:
    return path.is_symlink() and os.readlink(path) == str(target)


BEFORE = ("harness/jstack/claude-code", "claude-code", ".")


def dead(path: Path, machine: Machine) -> bool:
    """Whether `path` is a link to a missing skill. The link points into a layout's `skills/`,
    or into the `skills/` of a place where links pointed before the layouts existed. `BEFORE`
    lists those places under the source: a checkout's committed copy, the copy a release's wheel
    carried, and the checkout itself."""
    layouts = [machine.layout(harness.name) for harness in HARNESSES]
    folders = (*layouts, *(machine.source / before for before in BEFORE))
    return (
        path.is_symlink()
        and os.readlink(path).startswith(tuple(f"{one / 'skills'}{os.sep}" for one in folders))
        and not (path / "SKILL.md").is_file()
    )


@dataclass(frozen=True)
class Generated:
    """The files the generator writes from the checkout's features, `skills.json` among them.
    The install assembles each layout from `skills.json`, so a skill that is not in it is in
    no layout. `needs()` lists this need only with a checkout, since a release uses what its wheel
    carries.
    ok: the generator's --check passes.
    old: the detail is what the check named first, or why it could not run.
    put writes nothing in the checkout. An install leaves the checkout's files as git has
      them, and the user runs the generator.
    drop removes nothing."""

    def probe(self, machine: Machine) -> Found:
        ran = machine.run([sys.executable, "-I", str(machine.checkout / GENERATE), "--check"])
        if ran.code == 0:
            return Found.ok()
        said = ran.out.splitlines()
        return Found.old(said[0] if said else f"the generator exited {ran.code}")

    def due(self, machine: Machine) -> bool:
        return True

    def ask(self, machine: Machine) -> str:
        return f"python3 {machine.checkout / GENERATE}"

    def put(self, machine: Machine) -> None:
        raise Refused(f"they are not current: run {self.ask(machine)} and commit the result")

    def drop(self, machine: Machine) -> Dropped:
        return Dropped()


@dataclass(frozen=True)
class Link:
    """A symlink into a layout, which gives an agent a skill.
    old: the path is a link to anywhere else.
    foreign: `not a link`.
    drop: unlink the path only when it points at `target`."""

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
    """A link under a skills root to a skill that the source no longer has. It points into a
    layout's `skills/`, or to where links pointed before the layouts. `needs()` lists it only
    when it finds one, and the probe answers old until put or drop unlinks it."""

    path: Path

    def _dead(self, machine: Machine) -> bool:
        return dead(self.path, machine)

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
    """One shell word, always in single quotes, so the install puts the same text on every
    machine."""
    return "'" + str(path).replace("'", "'\\''") + "'"


def rewrite(machine: Machine, file: Path, change: Callable[[dict], bool]) -> bool:
    """Read `file`, let `change` edit a copy of its object, and write the copy when `change`
    returns True. When the file changes before the write, read it again, once."""
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
          "command": "sh '<layout>/<script>' 2>/dev/null || true", "timeout": 5}]}
    with no `matcher` key when `matcher` is None.

    With `refuses`, the command is "sh '<layout>/<script>'" with nothing after it. Such a hook
    refuses a tool call through its exit code and what it writes to stderr, so the command
    discards neither. Its timeout is 30 rather than 5, because it starts Python, and a hook that
    ran out of time has refused nothing.

    `<layout>` is the layout of `harness`, the harness whose agent reads the file.
    ok: that group is there, and no other command of the event names `/<script>`.
    old: a command names `/<script>` and differs from that one (another layout or copy, or
      the README's hand-written `"$HOME/..."` form). put takes each such command out and adds
      the group.
    foreign: the file is not one JSON object with a hooks object, and the detail is
      `not a hooks file`.
    drop: take out only the command that is exactly this layout's. Then take out the group
      if the removal leaves it empty, and do the same for `hooks[event]`, then for `hooks`.
      Touch no other key."""

    file: Path
    event: str
    matcher: str | None
    script: str
    refuses: bool = False
    harness: str = "claude-code"

    def _command(self, machine: Machine) -> str:
        run = f"sh {quoted(machine.layout(self.harness) / self.script)}"
        return run if self.refuses else f"{run} 2>/dev/null || true"

    def _group(self, machine: Machine) -> dict:
        timeout = 30 if self.refuses else 5
        hook = {"type": "command", "command": self._command(machine), "timeout": timeout}
        return ({} if self.matcher is None else {"matcher": self.matcher}) | {"hooks": [hook]}

    def _groups(self, value: dict) -> list | None:
        """The event's groups, or None when `value` does not have the shape of a hooks file: a
        `hooks` object whose every event is a list of groups, each with a list of hooks."""
        hooks = value.get("hooks", {})
        if not isinstance(hooks, dict):
            return None
        shaped = all(
            isinstance(groups, list)
            and all(
                isinstance(group, dict) and isinstance(group.get("hooks", []), list)
                for group in groups
            )
            for groups in hooks.values()
        )
        return hooks.get(self.event, []) if shaped else None

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
    """A hook of the checkout's own repo, a link from <checkout>/.git/hooks/<name> to
    <checkout>/<script>. The worktrees of a repo run the hooks of its main checkout, so the
    one link covers every branch that this machine sends to a remote.

    `needs()` lists this need only with a checkout, since a release has no repo of its own.
    due: `.git` is a directory, and HOME is the account's own or holds the checkout. A
      directory `.git` means the main checkout, since a linked worktree runs the hooks of its
      main checkout. When a sandbox or a test runs the install under another HOME, the run
      leaves a checkout outside that HOME as it is.
    old: the path is a link to anywhere else.
    foreign: the path is a hook of the user's own, and the detail is `not a link`. Or git
      runs no hook from the folder, and the detail is
      `core.hooksPath is set, so git runs no hook of .git/hooks`. A put repairs neither case.
    drop: unlink the path only when it points at the script."""

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
        checkout = machine.checkout
        if checkout is None:
            return False
        ours = machine.home == machine.account or checkout.is_relative_to(machine.home)
        return ours and (checkout / ".git").is_dir()

    def put(self, machine: Machine) -> None:
        self._link(machine).put(machine)

    def drop(self, machine: Machine) -> Dropped:
        return self._link(machine).drop(machine)


@dataclass(frozen=True)
class Patterns:
    """The private patterns that `jleak` reads, at
    ${XDG_CONFIG_HOME:-~/.config}/jstack/outbound.toml, through jleak's own loader. The install
    makes the file once, as `jleak.example` gives it for this HOME, and never writes it again.
    What the user adds to it is theirs.

    missing: there is no file, and both hooks refuse until it is there.
    foreign: the loader refuses the file, with the loader's reason. The install does not write
      over it.
    drop: remove the file only while it is still what the install made. Keep a file that the
      user edited, and say why."""

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
    {"type": "command", "command": "sh '<layout>/hooks/limits.sh'"}, in Claude Code's layout.
    due: only when the key is absent or its command names `/hooks/limits.sh`. A status line
      of the user's own is not due and gets no line.
    old: the command runs limits.sh of another layout or copy.
    drop: delete the key only when it is exactly the install's."""

    file: Path
    script: str = "hooks/limits.sh"

    def _ours(self, machine: Machine) -> dict:
        script = machine.layout("claude-code") / self.script
        return {"type": "command", "command": f"sh {quoted(script)}"}

    def _there(self, machine: Machine) -> tuple[bool, object]:
        """Two values: whether the method can read the file as an object, and the file's
        `statusLine`, which is None when the key is absent."""
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
class Attribution:
    """The keys of a harness's settings file that turn off its AI co-author trailer, as the
    harness's row gives them (`Harness.attribution`). The install sets these keys and touches
    no other key of the file.
    due: the file is there, or `made`, which the main Claude home's settings.json is. Another
      Claude home with no settings.json is a mirror that `jroles mirror` has not linked yet, and
      a machine with no `~/.cursor/cli-config.json` has not run Cursor's CLI.
    missing: none of the keys is in the file.
    old: a key is not set, or is set to another value: the detail names the first.
    foreign: the file is not one JSON object, and the detail is `not a settings file`.
    drop: take out each key that holds exactly the install's value."""

    file: Path
    wanted: dict
    made: bool = False

    def _there(self, machine: Machine) -> dict | None:
        was = machine.read_object(self.file)
        return was.value if isinstance(was, JsonObject) else None

    def probe(self, machine: Machine) -> Found:
        value = self._there(machine)
        if value is None:
            return Found.foreign("not a settings file")
        if not any(key in value for key in self.wanted):
            return Found.missing()
        for key, want in self.wanted.items():
            if key not in value:
                return Found.old(f"{key} is not set")
            if value[key] != want:
                return Found.old(f"{key} is {json.dumps(value[key])}")
        return Found.ok()

    def due(self, machine: Machine) -> bool:
        return self.made or self.file.exists()

    def put(self, machine: Machine) -> None:
        def change(value: dict) -> bool:
            value.update(copy.deepcopy(self.wanted))
            return True

        rewrite(machine, self.file, change)

    def drop(self, machine: Machine) -> Dropped:
        def change(value: dict) -> bool:
            ours = [key for key, want in self.wanted.items() if value.get(key, None) == want]
            for key in ours:
                del value[key]
            return bool(ours)

        if self._there(machine) is None:
            return Dropped()
        if rewrite(machine, self.file, change):
            return Dropped(removed=(f"attribution {self.file}",))
        return Dropped()


@dataclass(frozen=True)
class Commands:
    """The commands on PATH. In a checkout, `tool` and `names` come from pyproject.toml
    (`[project].name` and the keys of `[project.scripts]`). In a release, they come from the
    release's plugin.json and the installed package's entry points, and `version` is the
    plugin's. `was` is the tool's name before the rename.

    With a checkout:
    ok: `machine.tool_source(tool)` is this checkout, each name is in `machine.tool_bin()`,
      and typing each name runs that file or the one in <checkout>/.venv/bin.
    old: `lacks jdrift jroles` (an install from before the repo added them);
      `tool jgauge, from before the rename`; `an install of <other path>`; or
      `stale: its editable paths lack <root>`.
      The last one names a package root that pyproject.toml lists
      (`[tool.hatch.build.targets.wheel].packages`) and the install's `.pth` lacks. The
      package moved after uv built the install.
    foreign, since no put repairs it: `<name> is shadowed by <path>`, `<name> is not on PATH`.
    missing: there is no tool of either name.
    foreign: a tool of either name that is not an editable install of a checkout (a release,
      or a tool from an index or a git url). The install neither puts over it nor drops it.
    put: run `uv tool uninstall <was>` when its source is this checkout, then
      `uv tool install --editable <checkout> --reinstall`. Never use --force.
    drop: run `uv tool uninstall` on `tool`, and on `was`, each only when its source is this
      checkout. Otherwise keep it, and name the path it is an install of.

    With no checkout, the tool is a release. The jinstall that runs is one of the release's
    commands, so this need installs and removes nothing.
    ok: uv has the tool as an install that is not editable, its version is the plugin's, and each
      name is in `machine.tool_bin()` and is what typing the name runs.
    old: `tool jstack is 0.1.0, and its plugin is 0.2.0`, `lacks jinstall`, or an editable
      install.
    foreign: a name is shadowed, or not on PATH.
    missing: uv has no such tool, as when someone ran jinstall by hand.
    put: refuse, and give the command that installs a release.
    drop: keep the tool, and give the command that removes it."""

    tool: str
    names: tuple[str, ...]
    was: str = "jgauge"
    version: str = ""
    _install = "uv tool install <the release's wheel> --reinstall"

    def _lacks(self, machine: Machine) -> str:
        lacking = [name for name in self.names if not (machine.tool_bin() / name).exists()]
        return f"lacks {' '.join(lacking)}" if lacking else ""

    def _stale(self, machine: Machine, checkout: Path) -> list[str]:
        """Each package root in the checkout's pyproject.toml that the tool's paths lack."""
        try:
            wheel = tomllib.loads((checkout / "pyproject.toml").read_text())["tool"]["hatch"]
            listed = wheel["build"]["targets"]["wheel"]["packages"]
        except (OSError, ValueError, KeyError, TypeError):
            return []
        roots = sorted({checkout / Path(package).parent for package in listed})
        paths = machine.tool_paths(self.tool)
        return [str(root) for root in roots if root not in paths]

    def _typed(self, machine: Machine, *also: Path) -> Found:
        """The probe answers ok when typing each name runs the file in `tool_bin()` or in one
        of `also`. Otherwise it answers foreign: the name is not on PATH, or another file
        shadows it."""
        for name in self.names:
            typed = machine.which(name)
            if typed is None:
                return Found.foreign(f"{name} is not on PATH: {machine.tool_bin()} is not in it")
            if typed not in (machine.tool_bin() / name, *(one / name for one in also)):
                return Found.foreign(f"{name} is shadowed by {typed}")
        return Found.ok()

    def _released(self, machine: Machine) -> Found:
        if not machine.has_tool(self.tool):
            return Found.missing(f"uv has no tool {self.tool}: {self._install}")
        source = machine.tool_source(self.tool)
        if source is not None:
            return Found.old(f"tool {self.tool} is an editable install of {source}")
        version = machine.tool_version(self.tool)
        if version != self.version:
            return Found.old(f"tool {self.tool} is {version}, and its plugin is {self.version}")
        return Found.old(self._lacks(machine)) if self._lacks(machine) else self._typed(machine)

    def probe(self, machine: Machine) -> Found:
        if machine.checkout is None:
            return self._released(machine)
        source, before = machine.tool_source(self.tool), machine.tool_source(self.was)
        renamed = f"tool {self.was}, from before the rename"
        for tool, of in ((self.tool, source), (self.was, before)):
            if of is None and machine.has_tool(tool):
                return Found.foreign(
                    f"tool {tool} is installed from a release or an index, "
                    "not as an editable install of this checkout"
                )
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
        if lacking := self._stale(machine, machine.checkout):
            return Found.old(f"stale: its editable paths lack {' '.join(lacking)}")
        if self._lacks(machine):
            return Found.old(self._lacks(machine))
        return self._typed(machine, machine.checkout / ".venv" / "bin")

    def due(self, machine: Machine) -> bool:
        return True

    def _uv(self, machine: Machine, *args: str) -> None:
        ran = machine.uv(*args)
        if ran.code != 0:
            said = ran.out.strip().splitlines()
            raise Refused(f"uv {' '.join(args)}: {said[-1] if said else 'uv is not on PATH'}")

    def put(self, machine: Machine) -> None:
        if machine.checkout is None:
            raise Refused(f"a release's commands are uv's to install: {self._install}")
        if machine.tool_source(self.was) == machine.checkout:
            self._uv(machine, "tool", "uninstall", self.was)
        self._uv(machine, "tool", "install", "--editable", str(machine.checkout), "--reinstall")

    def drop(self, machine: Machine) -> Dropped:
        if machine.checkout is None:
            if not machine.has_tool(self.tool):
                return Dropped()
            why = f"the release this jinstall runs from: uv tool uninstall {self.tool}"
            return Dropped(kept=(f"commands {self.tool} -> {why}",))
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


UNIT_FOLDERS = ("templates", "features/*/units")
"""Where the source keeps the units the install links: its `templates/`, and the `units/` of
each feature whose units have moved there."""


def unit_templates(source: Path) -> dict[str, Path]:
    """Each unit under `source`, by name: every *.service and *.timer of `UNIT_FOLDERS`.
    The function raises ValueError for a name that two folders hold, so neither unit shadows
    the other."""
    found: dict[str, Path] = {}
    for folder in UNIT_FOLDERS:
        for path in sorted(source.glob(f"{folder}/*")):
            if path.suffix not in (".service", ".timer"):
                continue
            if path.name in found:
                both = " and ".join(str(p.relative_to(source)) for p in (found[path.name], path))
                raise ValueError(f"the unit {path.name} is in two folders: {both}")
            found[path.name] = path
    return found


def templates(machine: Machine) -> dict[str, Path]:
    """Each unit the install links, by name, in the source, which is a checkout's or a
    release's."""
    return unit_templates(machine.source)


@dataclass(frozen=True)
class Units:
    """The jbus units. For each of `names` (every unit `templates(machine)` finds), the
    install links ~/.config/systemd/user/<name> to its template, and it enables each of
    `timers`. The template is the checkout's, or else the release's. The checkout's template is
    the file that the links pointed at before the release's copy, and that systemd's own links under
    `timers.target.wants` still point at.

    due: jbus is set up (its config is there), or a unit of this checkout's is there.
    ok: every link points at its template, and ~/.local/bin/jbus is there, since the units run
      it. When the manager reads this HOME, each timer is also enabled and no reload is due.
      With a manager that reads another HOME (a sandbox), the probe checks only the links. Under
      the account's own HOME, a manager that does not answer makes the need old, since nothing
      enabled the timer.
    old: the detail names the first piece that is not so: `lacks jbus-failed.service`,
      `jbus.timer is not enabled`, `needs daemon-reload`. A regular file whose bytes equal
      its template is a copy that someone made by hand from the README, and the install may
      replace it.
    foreign: a file that differs from its template, `jbus.service -> not a link, differs`.
      The need is also foreign for two cases that no put repairs: `no ~/.local/bin/jbus`,
      and a manager that did not answer.
    put: refuse when there is no ~/.local/bin/jbus, so no timer starts on a missing program.
      Otherwise make `timers.target.wants` through the machine, link each unit to its
      template, run daemon-reload, and run enable --now.
    drop: run disable --now on each timer whose link is the install's, unlink each link that
      points at its template, and run daemon-reload. systemd's disable unlinks a linked unit
      by itself, and drop unlinks the links that it leaves.
    Each systemctl step goes through `machine.systemctl`. So with a manager that reads
    another HOME, the need only makes, checks and removes the links."""

    directory: Path
    names: tuple[str, ...]
    timers: tuple[str, ...]
    config: Path

    def _template(self, machine: Machine, name: str) -> Path:
        return templates(machine)[name]

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
    """A program on PATH.
    missing: the program is not there, and the detail is `hint`.
    old: its version is below `floor`, or the probe cannot read the version. When `floor` is
      None, the probe never answers old and does not run the program."""

    command: str
    version: tuple[str, ...] = ("--version",)
    floor: tuple[int, ...] | None = None
    hint: str = ""
    package: str = ""

    def ask(self, machine: Machine) -> str:
        """The hint where there is one, or else the Arch package. The package is the
        command's name unless `package` names another."""
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
    """T3 Code, which the probe asks through the `t3` command that the app writes into
    ~/.t3/bin, or else through the one on PATH.
    missing: neither command is there.
    old: the stable build, a command that does not answer, or a nightly before `floor`.
      `floor` is the oldest nightly with every MCP tool that jstack calls. It is None until
      someone writes that build down. While it is None, old means only
      `not the nightly build`."""

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
    """missing: `gh auth token` exits non-zero. The probe makes no network call and does not
    read what the command prints. It never answers old."""

    def ask(self, machine: Machine) -> str:
        return "gh auth login"

    def probe(self, machine: Machine) -> Found:
        if machine.run(["gh", "auth", "token"]).code == 0:
            return Found.ok()
        return Found.missing("gh auth login")


@dataclass(frozen=True)
class Linux:
    """The probe answers ok on Linux. Anywhere else it answers missing, with the platform as
    the detail."""

    platform: str = sys.platform

    def probe(self, machine: Machine) -> Found:
        if self.platform.startswith("linux"):
            return Found.ok()
        return Found.missing(f"this is {self.platform}")


def _said(error: Exception) -> str:
    """Why jbus does not accept a file: jbus's own refusal, in its words. For anything else
    that its code raised, the reason names only the exception's type, since such a message can
    quote a value of the file."""
    if isinstance(error, jbus.Refused):
        return str(error).removeprefix("refused: ")
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return f"jbus cannot read it: {type(error).__name__}"


@dataclass(frozen=True)
class JbusConfig:
    """jbus's config.toml, which jbus's own loader reads.
    old: the loader refuses the file, as it refuses one that group or others can read. The
      install never writes over the file, since it holds a key.
    Setup seeds it with mode 600, no project and no key. The seed sets `server` to the server
    that the T3 sign-in beside it names, or else to T3 Code's own address. It sets
    `dispatch = false`, so jbus launches nothing until the user turns dispatch on.
    `jbus t3 login` reads the server from this file, so this need comes first."""

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
    """t3.json beside the config.
    missing: `run jbus t3 login`.
    old: others can read the file, or its expiry has passed. jbus reads the expiry from the
      file, and the probe dates it in the jstack config's time zone."""

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
    """One instance's file of the ledger. `jgauge room` and `jroles` read it, and
    `jgauge-limits.timer` rewrites it every two minutes.
    missing: there is no file, since nothing has read that account yet.
    old: the probe cannot read the file, or its last write was 15 minutes ago or more, so the reader
      has stopped."""

    path: Path

    def ask(self, machine: Machine) -> str:
        """The timer runs the reader, and one run writes every account's file."""
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
    """The homes' state tree, which `jbus snapshot` commits and sends to its `origin`.
    ok: the directory is the top of a git repo with an origin. The detail names the origin,
      with any credentials taken out of it.
    missing: the directory is not a git repo, or the repo has no origin."""

    path: Path

    def ask(self, machine: Machine) -> str:
        """The url is the user's own private repository, so the command says where the
        snapshots go."""
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
    """${XDG_CONFIG_HOME:-~/.config}/jstack/config.toml, which the commands' own loader
    reads. The install never creates it.
    missing: there is no file, so the commands run on their defaults. The detail names each
      key that has a default.
    old: the loader refuses the file.
    Setup seeds it with `user`, the first word of `git config user.name`, and `timezone`, the
    machine's own zone. The seed leaves out a value that the loader would not accept, so that
    key keeps its default."""

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
    """${XDG_CONFIG_HOME:-~/.config}/jstack/roles, the role map that `jroles` reads.
    missing: there is no file, so every role inherits.
    old: `jroles.read_map` refuses the file, and the detail gives its lines.
    Setup seeds it with every role set to `inherit`, which names no effort, so the seed sets
    nothing above medium."""

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
    """The home of each declared Claude instance, once each. An instance that names no home
    has `~/.claude`."""
    homes = [each.home or home / ".claude" for each in declared.values() if each.driver == BUILT_IN]
    return list(dict.fromkeys(homes))


@dataclass(frozen=True)
class ProviderInventory:
    """${XDG_CONFIG_HOME:-~/.config}/jstack/providers.json, the provider instances that this
    machine should run, in T3's `providerInstances` shape. infra's install links the file
    there, and jstack only reads it.
    missing: there is no file, so the machine declares no instance.
    old: the file does not have that shape."""

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
    """One declared instance, compared with T3's own settings, which the probe only reads.
    ok: T3 lists the instance with the declared driver, enabled and homePath. Or it is T3's
      built-in `claudeAgent`, declared with no other home, and T3 does not list it.
    missing: T3 does not list the instance.
    old: T3 lists it otherwise, or the probe cannot read T3's settings."""

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
    """A Claude home's `skills`, which must be the central jstack skills. Either it is the
    same directory as `central` (~/.claude/skills), or each of its entries resolves into
    the folder that the field `skills` names. Hidden entries are the agent's own, and the
    probe does not count them.
    missing: the home has no skills.
    old: the detail is where a linked `skills` points, or else the first entry that points
      elsewhere."""

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
