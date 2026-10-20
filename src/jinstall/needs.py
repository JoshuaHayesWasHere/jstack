"""The one list of what a machine needs to run jstack. Written once, here.

Adding a need is one entry in `needs()`: the doctor then prints it, `--setup` says whether it
is done, already there, or the user's to do, and when its kind is Carried the install also
puts, checks and removes it, with no other edit.
"""

import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import jleak
from jinstall.kinds import (
    Carried,
    Commands,
    GhSignIn,
    GitHook,
    GoneLink,
    HomeSkills,
    HookGroup,
    JbusConfig,
    JbusSignIn,
    JstackConfig,
    Kind,
    Limits,
    Link,
    Linux,
    Patterns,
    Program,
    ProviderInstance,
    ProviderInventory,
    Roles,
    StateRepo,
    StatusLine,
    T3Nightly,
    Units,
    claude_homes,
    dead,
    declared,
)
from jinstall.machine import Machine
from jinstall.mirrored import Mirrored
from jinstall.mirrored import declared as mirrors
from jroles import ledger
from jroles.inventory import claude_instances

T3_FLOOR: str | None = None
UV_FLOOR: tuple[int, ...] | None = None


class Level(Enum):
    """HARD: jstack does not run without it, and the doctor exits 1.
    OPTIONAL: a layer is off without it, and the doctor only says so."""

    HARD = "hard"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class Need:
    """One line. `name` is what is printed after the level: a path for a link, else a word
    and a path or a program (`hook <file> <Event>`, `commands jstack`, `jq`)."""

    name: str
    level: Level
    kind: Kind | Carried


def needs(machine: Machine) -> tuple[Need, ...]:
    """Every need, in the order printed. Nothing is probed here: the list is derived from the
    checkout (skills/*/SKILL.md, templates/*.service and *.timer, pyproject.toml), from
    one listing of each skills root for GoneLink, and from the provider inventory, which
    names the instances and the Claude homes to probe. An inventory that cannot be taken
    names none, and its own line says why.

    Only probed:
      hard      linux                         Linux
      hard      t3                            T3Nightly(T3_FLOOR)
      hard      claude                        Program("claude", package="claude-code")
      hard      uv                            Program("uv", floor=UV_FLOOR)
      hard      git                           Program("git", floor=(2, 31))
      hard      jq                            Program("jq", floor=(1, 6))
      hard      gh                            Program("gh", package="github-cli")
      hard      gh sign-in                    GhSignIn
      optional  jbus config <path>            JbusConfig, seeded
      optional  jbus sign-in <path>           JbusSignIn
      optional  limits <path>                 Limits
      optional  config <path>                 JstackConfig, seeded
      optional  roles <path>                  Roles, seeded
      optional  lavish-axi                    Program("lavish-axi", hint="npm install -g ...")
      optional  state repo <path>             StateRepo
      optional  provider inventory            ProviderInventory
      hard      provider <id>                 ProviderInstance, for each declared instance
      hard      skills <home>                 HomeSkills, for each declared Claude home
      optional  mirror <home>                 Mirrored, for each Claude home not ~/.claude

    Carried, in the order they are put. Uninstall walks them backwards:
      hard      ~/.claude/skills/<skill>      Link
      hard      ~/.agents/skills/<skill>      Link, the root Cursor reads beside ~/.claude/skills
      hard      ~/.codex/skills/<skill>       Link
      hard      <root>/<name>                 GoneLink, for each dead link into this checkout
      hard      hook ~/.claude/settings.json SessionStart      HookGroup("startup", home-start)
      hard      hook ~/.claude/settings.json UserPromptSubmit  HookGroup(None, skill-tips)
      hard      hook ~/.claude/settings.json PostToolUse       HookGroup(None, home-gauge)
      hard      hook ~/.claude/settings.json PreToolUse        HookGroup(None, home-gauge)
      hard      hook ~/.codex/hooks.json SessionStart          HookGroup("startup", home-start)
      optional  patterns <path>               Patterns
      hard      hook ~/.claude/settings.json PreToolUse        HookGroup("Bash", outbound-command)
      hard      hook <checkout>/.git/hooks/pre-push pre-push   GitHook, in a main checkout
      hard      commands <tool>               Commands
      optional  statusline ~/.claude/settings.json             StatusLine
      optional  units ~/.config/systemd/user  Units
    """
    repo, home = machine.checkout, machine.home
    skills = sorted(path.parent.name for path in (repo / "skills").glob("*/SKILL.md"))
    roots = (home / ".claude" / "skills", home / ".agents" / "skills", home / ".codex" / "skills")
    jbus, limits = _jbus_config(machine), _limits(machine)
    config = machine.config_home() / "jstack" / "config.toml"
    roles = config.with_name("roles")
    state = _state_tree(machine)
    found = [
        Need("linux", Level.HARD, Linux()),
        Need("t3", Level.HARD, T3Nightly(T3_FLOOR)),
        Need("claude", Level.HARD, Program("claude", package="claude-code")),
        Need("uv", Level.HARD, Program("uv", floor=UV_FLOOR)),
        Need("git", Level.HARD, Program("git", floor=(2, 31))),
        Need("jq", Level.HARD, Program("jq", floor=(1, 6))),
        Need("gh", Level.HARD, Program("gh", package="github-cli")),
        Need("gh sign-in", Level.HARD, GhSignIn()),
        Need(f"jbus config {jbus}", Level.OPTIONAL, JbusConfig(jbus)),
        Need(
            f"jbus sign-in {jbus.with_name('t3.json')}",
            Level.OPTIONAL,
            JbusSignIn(jbus.with_name("t3.json")),
        ),
        Need(f"config {config}", Level.OPTIONAL, JstackConfig(config)),
        Need(f"roles {roles}", Level.OPTIONAL, Roles(roles)),
        Need("lavish-axi", Level.OPTIONAL, Program("lavish-axi", hint="npm install -g lavish-axi")),
        Need(f"state repo {state}", Level.OPTIONAL, StateRepo(state)),
    ]
    inventory = machine.config_home() / "jstack" / "providers.json"
    providers = declared(inventory, home)
    providers = {} if isinstance(providers, str) else providers
    t3 = home / ".t3" / "userdata" / "settings.json"
    found.append(Need("provider inventory", Level.OPTIONAL, ProviderInventory(inventory)))
    found += [
        Need(f"limits {file}", Level.OPTIONAL, Limits(file))
        for file in (ledger.file_of(name, limits) for name in claude_instances(providers, home))
    ]
    found += [
        Need(f"provider {name}", Level.HARD, ProviderInstance(name, instance, t3))
        for name, instance in providers.items()
    ]
    found += [
        Need(f"skills {each}", Level.HARD, HomeSkills(each, roots[0], repo / "skills"))
        for each in claude_homes(providers, home)
    ]
    found += [
        Need(f"mirror {each.home}", Level.OPTIONAL, Mirrored(each))
        for each in mirrors(inventory, home)
    ]
    found += [
        Need(str(root / skill), Level.HARD, Link(root / skill, repo / "skills" / skill))
        for root in roots
        for skill in skills
    ]
    found += [
        Need(str(path), Level.HARD, GoneLink(path))
        for root in roots
        for path in _listed(root)
        if dead(path, repo)
    ]
    settings, codex = home / ".claude" / "settings.json", home / ".codex" / "hooks.json"
    found += [
        Need(f"hook {file} {event}", Level.HARD, HookGroup(file, event, matcher, script))
        for file, event, matcher, script in (
            (settings, "SessionStart", "startup", "hooks/home-start.sh"),
            (settings, "UserPromptSubmit", None, "hooks/skill-tips.sh"),
            (settings, "PostToolUse", None, "hooks/home-gauge.sh"),
            (settings, "PreToolUse", None, "hooks/home-gauge.sh"),
            (codex, "SessionStart", "startup", "hooks/home-start.sh"),
        )
    ]
    patterns, pushed = jleak.path(machine.config_home()), GitHook("pre-push", "hooks/pre-push.sh")
    found += [
        Need(f"patterns {patterns}", Level.OPTIONAL, Patterns(patterns)),
        Need(
            f"hook {settings} PreToolUse",
            Level.HARD,
            HookGroup(settings, "PreToolUse", "Bash", "hooks/outbound-command.sh", refuses=True),
        ),
        Need(f"hook {repo / '.git' / 'hooks' / pushed.name} {pushed.name}", Level.HARD, pushed),
    ]
    project = tomllib.loads((repo / "pyproject.toml").read_text())["project"]
    commands = Commands(project["name"], tuple(project["scripts"]))
    found.append(Need(f"commands {commands.tool}", Level.HARD, commands))
    found.append(Need(f"statusline {settings}", Level.OPTIONAL, StatusLine(settings)))
    templates = sorted(
        path.name for kind in ("*.service", "*.timer") for path in (repo / "templates").glob(kind)
    )
    units = Units(
        machine.config_home() / "systemd" / "user",
        tuple(templates),
        tuple(name for name in templates if name.endswith(".timer")),
        jbus,
    )
    found.append(Need(f"units {units.directory}", Level.OPTIONAL, units))
    return tuple(found)


def _jbus_config(machine: Machine) -> Path:
    """Where jbus reads its config, as `jbus.config_dir` finds it."""
    named = machine.env.get("JBUS_CONFIG_DIR")
    return (Path(named) if named else machine.home / ".config" / "jbus") / "config.toml"


def _state_tree(machine: Machine) -> Path:
    """The homes' state tree, as `jbus.load` finds its `home_dir`."""
    named = machine.env.get("JBUS_HOME_DIR")
    return Path(named) if named else machine.home / ".local" / "state" / "home"


def _limits(machine: Machine) -> Path:
    """Where `jgauge room` reads the plan's limits, as `room.sh` finds it."""
    named = machine.env.get("LIMITS")
    return Path(named) if named else machine.home / ".local" / "state" / "claude" / "limits"


def _listed(root: Path) -> list[Path]:
    try:
        return sorted(root.iterdir())
    except OSError:
        return []
