"""The one list of what a machine needs to run jstack. This module names every need, once,
except the hooks: each feature declares its own, and the install reads them from the source's
skills.json.

To add a need, add one entry to `needs()`, and make no other edit. The doctor then prints it,
and `--setup` says whether it is done, already there, or left for the user to do. When its kind is
Carried, the install also puts, checks and removes it.
"""

import json
import tomllib
from dataclasses import dataclass
from enum import Enum
from importlib import metadata
from pathlib import Path

import jleak
from jinstall import launchd
from jinstall.agents import Agents
from jinstall.harnesses import CLAUDE_CODE, HARNESSES
from jinstall.kinds import (
    Attribution,
    Carried,
    CiReport,
    Commands,
    Generated,
    GhSignIn,
    GoneLink,
    HomeSkills,
    HookGroup,
    JbusConfig,
    JbusSignIn,
    JstackConfig,
    Kind,
    Limits,
    Link,
    Patterns,
    Platform,
    Program,
    RelayKeys,
    RetiredHook,
    Roles,
    StateRepo,
    StatusLine,
    T3Code,
    T3JstackBuild,
    Units,
    claude_homes,
    dead,
    retired,
    templates,
)
from jinstall.layout import (
    UNREADABLE,
    Layout,
    git_hooks,
    hooks,
    project_skills,
    skills,
    status_line,
)
from jinstall.machine import Machine
from jinstall.mirrored import Mirrored
from jinstall.project import ProjectLink, StrayProjectLink, stray
from jinstall.repos import GitHook, checkouts
from jroles import inventory, ledger
from jroles.inventory import claude_instances
from jroles.mirror import mirrors
from jsettings import paths

T3_FLOOR = "0.1.2-nightly.20261022.3526"
CLAUDE_PAGE = "https://code.claude.com/docs/en/setup"
UV_FLOOR: tuple[int, ...] | None = None


class Level(Enum):
    """HARD: jstack does not run without the need, and the doctor exits 1.
    OPTIONAL: a layer is off without the need, and the doctor only says so."""

    HARD = "hard"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class Need:
    """One line of the list. `name` is what the line prints after the level. For a link it
    is a path, and for anything else it is a word and a path, or a program
    (`hook <file> <Event>`, `commands jstack`, `jq`). `fold` names the run of needs that
    `--setup` says in one line while each is done or already there, `skills <harness>` for a
    harness's skill links."""

    name: str
    level: Level
    kind: Kind | Carried
    fold: str = ""


def needs(machine: Machine) -> tuple[Need, ...]:
    """Every need, in the order the lines print. This function probes nothing. It derives the
    list from the source's skills.json, the units (`templates`), the commands (`_commands`),
    one listing of each skills root for GoneLink, one read of each hooks file for RetiredHook,
    and T3's provider instances (`jroles.inventory`), which name the Claude homes to probe.

    A release has no checkout, so its list has no generated line and no project skill.
    T3 settings that the function cannot read name no instance or home, and `jroles` says
    why. A skills.json that the function cannot read names no skill and no hook, and each
    layout's line says why.

    Needs that the install only probes:
      hard      platform                      Platform, ok on Linux and macOS
      hard      t3                            T3Code(T3_FLOOR)
      optional  t3 jstack build               T3JstackBuild, carried: --setup builds it, on Arch
      hard      claude                        Program("claude", arch="claude-code", ...)
      hard      uv                            Program("uv", floor=UV_FLOOR)
      hard      git                           Program("git", floor=(2, 31))
      hard      jq                            Program("jq", floor=(1, 6))
      hard      gh                            Program("gh", arch="github-cli")
      hard      gh sign-in                    GhSignIn
      optional  jbus config <path>            JbusConfig, seeded
      optional  jbus sign-in <path>           JbusSignIn
      optional  limits <path>                 Limits
      optional  config <path>                 JstackConfig, seeded
      optional  roles <path>                  Roles, seeded
      optional  lavish-axi                    Program("lavish-axi", hint="npm install -g ...")
      optional  state repo <path>             StateRepo, the backup
      optional  ci report <path>              CiReport, of the jbus config
      optional  relay <path>                  RelayKeys, the relay's env file
      hard      skills <home>                 HomeSkills, for each declared Claude home
      optional  mirror <home>                 Mirrored, for each Claude home not ~/.claude

    Carried, in the order the install puts them, and uninstall walks them in reverse. Every
    link and hook command except the git hook points into a harness's layout, which the
    install assembles from the checkout or the release:
      hard      generated files are current   Generated, the generator's --check, in a checkout
      hard      layout <harness> <folder>     Layout, for Claude Code, Codex and Cursor
      hard      ~/.claude/skills/<skill>      Link into Claude Code's layout
      hard      ~/.codex/skills/<skill>       Link into Codex's
      hard      ~/.agents/skills/<skill>      Link into Cursor's, the root Cursor reads
      hard      <root>/<name>                 GoneLink, for each dead link into a layout
      hard      <checkout>/.claude/skills/<name>  ProjectLink, for each project skill of
                                              skills.json, in a checkout, and the same in
                                              <checkout>/.cursor/skills (`Harness.project`)
      hard      <checkout>/<folder>/<name>    StrayProjectLink, for each link there into the
                                              checkout that no feature declares
      optional  patterns <path>               Patterns
      hard      hook <file> <event>           HookGroup, for each entry of each hook of
                                              skills.json, in the file its harness reads
                                              (`Harness.hooks`)
      hard      hook <file> <event> hooks/<name>  RetiredHook, for each hook there that
                                              runs a script of the harness's layout
                                              `hooks/` that skills.json does not declare,
                                              and none while skills.json cannot be read
      hard      hook <repo>/.git/hooks/<name> <name>  GitHook, for each git hook of
                                              skills.json in each repo jstack works in
                                              (`repos.checkouts`): hard in its own checkout,
                                              optional in any other repo
      hard      commands <tool>               Commands
      optional  statusline ~/.claude/settings.json  StatusLine, the status line of skills.json
      hard      attribution <file>            Attribution, the keys that turn off the AI
                                              co-author trailer, in each Claude home's
                                              settings.json (~/.claude and each declared
                                              home) and in each harness's settings file
      optional  units ~/.config/systemd/user  Units, which enables the ci, relay and
                                              snapshot units only while the ci report, relay
                                              and state repo needs above are ok (`OPTED`); on
                                              macOS `units ~/Library/LaunchAgents`, Agents,
                                              the launchd agents made from the same units
    """
    repo, home = machine.checkout, machine.home
    try:
        named, hooked = skills(machine.source), hooks(machine.source)
        line, pushed = status_line(machine.source), git_hooks(machine.source)
        local = project_skills(machine.source)
        read = True
    except UNREADABLE:
        named, hooked, line, pushed, local, read = [], (), None, (), (), False
    roots = {harness: home / harness.root for harness in HARNESSES}
    jbus, limits = _jbus_config(machine), _limits(machine)
    config = machine.config_home() / "jstack" / "config.toml"
    roles = config.with_name("roles")
    state = _state_tree(machine)
    relay = machine.config_home() / "jbus-relay" / "env"
    found = [
        Need("platform", Level.HARD, Platform()),
        Need("t3", Level.HARD, T3Code(T3_FLOOR)),
        *_t3_jstack(machine),
        Need(
            "claude",
            Level.HARD,
            Program("claude", arch="claude-code", brew="--cask claude-code", page=CLAUDE_PAGE),
        ),
        Need("uv", Level.HARD, Program("uv", floor=UV_FLOOR)),
        Need("git", Level.HARD, Program("git", floor=(2, 31))),
        Need("jq", Level.HARD, Program("jq", floor=(1, 6))),
        Need("gh", Level.HARD, Program("gh", arch="github-cli")),
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
        Need(f"ci report {jbus}", Level.OPTIONAL, CiReport(jbus)),
        Need(f"relay {relay}", Level.OPTIONAL, RelayKeys(relay)),
    ]
    providers = inventory.declared(inventory.path(machine.env, home), home)
    providers = {} if isinstance(providers, str) else providers
    found += [
        Need(f"limits {file}", Level.OPTIONAL, Limits(file))
        for file in (ledger.file_of(name, limits) for name in claude_instances(providers, home))
    ]
    found += [
        Need(
            f"skills {each}",
            Level.HARD,
            HomeSkills(each, roots[CLAUDE_CODE], machine.layout(CLAUDE_CODE.name) / "skills"),
        )
        for each in claude_homes(providers, home)
    ]
    found += [
        Need(f"mirror {each.home}", Level.OPTIONAL, Mirrored(each))
        for each in mirrors(providers, home)
    ]
    if repo is not None:
        found.append(Need("generated files are current", Level.HARD, Generated()))
    found += [
        Need(f"layout {harness.name} {machine.layout(harness.name)}", Level.HARD, Layout(harness))
        for harness in HARNESSES
    ]
    found += [
        Need(
            str(root / skill),
            Level.HARD,
            Link(root / skill, machine.layout(harness.name) / "skills" / skill),
            fold=f"skills {harness.name}",
        )
        for harness, root in roots.items()
        for skill in named
    ]
    found += [
        Need(str(path), Level.HARD, GoneLink(path))
        for root in roots.values()
        for path in _listed(root)
        if dead(path, machine) and path.name not in named
    ]
    if repo is not None:
        found += _project(repo, local)
    patterns = jleak.path(machine.config_home())
    found.append(Need(f"patterns {patterns}", Level.OPTIONAL, Patterns(patterns)))
    files = {harness.name: home / harness.hooks for harness in HARNESSES if harness.hooks}
    found += [
        Need(
            f"hook {files[one['harness']]} {one['event']}",
            Level.HARD,
            HookGroup(
                files[one["harness"]],
                one["event"],
                one.get("matcher"),
                f"hooks/{hook['name']}",
                refuses=one.get("refuses", False),
                harness=one["harness"],
            ),
        )
        for hook in hooked
        for one in hook["events"]
    ]
    scripts = frozenset(
        [hook["name"] for hook in hooked] + ([line["name"]] if line is not None else [])
    )
    found += [
        Need(
            f"hook {file} {event} hooks/{name}",
            Level.HARD,
            RetiredHook(file, event, name, harness=harness),
        )
        for harness, file in files.items()
        if read
        for event, name in retired(machine, file, harness, scripts)
    ]
    found += [
        Need(
            f"hook {hook.path()} {hook.name}",
            Level.HARD if each == repo else Level.OPTIONAL,
            hook,
        )
        for each in checkouts(machine, jbus)
        for hook in (GitHook(each, one["name"], one["path"]) for one in pushed)
    ]
    commands = _commands(machine)
    found.append(Need(f"commands {commands.tool}", Level.HARD, commands))
    settings = files[CLAUDE_CODE.name]
    if line is not None:
        found.append(
            Need(
                f"statusline {settings}",
                Level.OPTIONAL,
                StatusLine(settings, f"hooks/{line['name']}"),
            )
        )
    found += [
        Need(f"attribution {file}", Level.HARD, Attribution(file, wanted, made))
        for file, wanted, made in _attribution(home, providers)
    ]
    names = sorted(templates(machine))
    opted = {"jbus-ci.timer": CiReport(jbus), "jbus-relay.service": RelayKeys(relay)}
    opted["jbus-snapshot.timer"] = StateRepo(state)
    timers = tuple(name for name in names if name.endswith(".timer") and name not in opted)
    chosen = tuple((name, need) for name, need in opted.items() if name in names)
    if machine.platform == "darwin":
        made = launchd.agents(templates(machine), home)
        units = Agents(home / "Library" / "LaunchAgents", made, timers, jbus, chosen)
    else:
        systemd = machine.config_home() / "systemd" / "user"
        units = Units(systemd, tuple(names), timers, jbus, chosen)
    found.append(Need(f"units {units.directory}", Level.OPTIONAL, units))
    return tuple(found)


def _attribution(home: Path, providers: dict) -> list[tuple[Path, dict, bool]]:
    """Each settings file that gets the keys that turn off the AI co-author trailer, with the
    keys and whether the install makes the file when it is not there. Every Claude home gets
    Claude Code's keys: `~/.claude`, made, and each home T3's settings list, only while its
    settings.json is there. A home whose settings.json is a link to `~/.claude`'s, as
    `jroles mirror` makes it, reads and writes that one file."""
    found = []
    for harness in HARNESSES:
        if not harness.attribution:
            continue
        files = [home / harness.settings]
        if harness is CLAUDE_CODE:
            files += [each / "settings.json" for each in claude_homes(providers, home)]
        made = harness is CLAUDE_CODE
        found += [
            (file, harness.attribution, made and file == files[0]) for file in dict.fromkeys(files)
        ]
    return found


def _project(repo: Path, local: tuple[dict, ...]) -> list[Need]:
    """The needs of the checkout's project folders. Each project skill gets a link in each
    harness's project folder. Each link already there that points into the checkout, under a
    name no feature declares, gets a stray need."""
    roots = [repo / harness.project for harness in HARNESSES if harness.project]
    declared = frozenset(one["name"] for one in local)
    found = [
        Need(
            str(root / one["name"]), Level.HARD, ProjectLink(root / one["name"], repo / one["path"])
        )
        for root in roots
        for one in local
    ]
    found += [
        Need(str(path), Level.HARD, StrayProjectLink(path, declared))
        for root in roots
        for path in _listed(root)
        if stray(path, repo, declared)
    ]
    return found


def _commands(machine: Machine) -> Commands:
    """The tool and its commands. For a checkout, the function reads them from its
    pyproject.toml. For a release, it reads the name and the version from the release's
    plugin.json, and they match the package's. It reads the commands from what the installed
    package declares, and there are none when the package is not installed."""
    if machine.checkout is not None:
        project = tomllib.loads((machine.checkout / "pyproject.toml").read_text())["project"]
        return Commands(project["name"], tuple(project["scripts"]))
    plugin = json.loads((machine.source / "plugin.json").read_text())
    try:
        points = metadata.distribution(plugin["name"]).entry_points
    except metadata.PackageNotFoundError:
        points = metadata.EntryPoints(())
    names = sorted(one.name for one in points if one.group == "console_scripts")
    return Commands(plugin["name"], tuple(names), version=plugin["version"])


def _t3_jstack(machine: Machine) -> list[Need]:
    """The jstack build's need, listed only on Arch, since its PKGBUILD builds for no other
    machine. It is due only where T3 Code is a nightly, which the build replaces."""
    if not machine.which("pacman"):
        return []
    packaging = machine.source / "features" / "t3code-jstack" / "packaging"
    return [Need("t3 jstack build", Level.OPTIONAL, T3JstackBuild(packaging))]


def _jbus_config(machine: Machine) -> Path:
    """Where jbus reads its config, as `jbus.config_dir` finds it."""
    named = machine.env.get("JBUS_CONFIG_DIR")
    return (Path(named) if named else machine.home / ".config" / "jbus") / "config.toml"


def _state_tree(machine: Machine) -> Path:
    """The homes' state tree, as `jbus.load` finds its `home_dir`."""
    return paths.homes_dir(machine.env, machine.home)


def _limits(machine: Machine) -> Path:
    """Where `jgauge room` reads the plan's limits, as `room.sh` finds it."""
    named = machine.env.get("LIMITS")
    return Path(named) if named else machine.home / ".local" / "state" / "claude" / "limits"


def _listed(root: Path) -> list[Path]:
    try:
        return sorted(root.iterdir())
    except OSError:
        return []
