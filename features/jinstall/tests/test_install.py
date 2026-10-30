"""`install.sh`: the layout it assembles for Claude Code, Codex and Cursor, what it puts for
each, what `--check` says of each part, and what `--uninstall` takes away.

Every test runs the script under a temporary `HOME`, with stand-ins for `uv` and `systemctl`.
Three tests are the exception: each gives the code a machine state that no argument of the script
can produce."""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import daemons
import jleak
from jbus.launchd import label
from jinstall import layout
from jinstall.__main__ import install as run_install
from jinstall.harnesses import HARNESSES
from jinstall.kinds import RetiredHook, Units, rewrite, unit_templates
from jinstall.machine import Machine, Moved, Ran
from jinstall.needs import needs
from testing.paths import REPO

INSTALL = REPO / "install.sh"
SYSTEMCTL = REPO / "features" / "verify-jstack" / "project-skill" / "scripts" / "fake-systemctl"
SKILLS = layout.skills(REPO)
ROOTS = tuple(harness.root for harness in HARNESSES)
LAYOUTS = Path(".local") / "share" / "jstack" / "harness"
FLAGGED = {harness.name: len(layout.assemble(REPO, harness).flagged) for harness in HARNESSES}
NAMES = list(tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"])
PACKAGES = tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["hatch"]["build"]
PACKAGE_ROOTS = sorted(
    {str(Path(package).parent) for package in PACKAGES["targets"]["wheel"]["packages"]}
)
PROJECT = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
POINTS = {
    "console_scripts": PROJECT["scripts"],
    **PROJECT.get("entry-points", {}),
}
ENTRY_POINTS = "".join(
    f"[{group}]\n" + "".join(f"{name} = {value}\n" for name, value in points.items()) + "\n"
    for group, points in POINTS.items()
)
"""The entry_points.txt that uv writes when it installs this checkout."""
UNITS = [
    "jbus-ci.service",
    "jbus-ci.timer",
    "jbus-failed.service",
    "jbus-relay.service",
    "jbus-snapshot.service",
    "jbus-snapshot.timer",
    "jbus-stale.service",
    "jbus-stale.timer",
    "jbus-view.service",
    "jbus.service",
    "jbus.timer",
    "jgauge-limits.service",
    "jgauge-limits.timer",
    "jgauge-sample.service",
    "jgauge-sample.timer",
    "jroles-mirror.service",
    "jroles-mirror.timer",
]
TIMERS = [
    "jbus-stale.timer",
    "jbus.timer",
    "jgauge-limits.timer",
    "jgauge-sample.timer",
    "jroles-mirror.timer",
]
OPTED = ["jbus-ci.timer", "jbus-relay.service", "jbus-snapshot.timer"]
"""The units only some machines run: each is enabled once the config that asks for it is
there, and every other timer is enabled on every machine."""
RELAY_KEYS = (
    "RELAY_INBOUND_KEY=an-inbound-key\n"
    "GROK_WEBHOOK_URL=http://127.0.0.1:9/hook\n"
    "GROK_WEBHOOK_KEY=a-webhook-key\n"
    "PAGER_HA_URL=http://127.0.0.1:9\n"
    "PAGER_HA_TOKEN=a-token\n"
    "PAGER_HA_SERVICE=mobile_app_phone\n"
)
SCRUBBED = ("XDG_", "UV_", "JBUS_", "VERIFY_JSTACK_", "LIMITS")
MAC = sys.platform == "darwin"
"""Whether the tests run on a Mac. `install.sh` runs jinstall in a Python of its own, which
takes its platform from the machine the test runs on, and no test can set it there. So a test of
the script expects this platform's output, and a test of systemd's units runs on Linux only,
beside its Darwin case (`linux_only`)."""
UNITS_DIR = Path("Library", "LaunchAgents") if MAC else Path(".config", "systemd", "user")
"""Where the install puts the units, under HOME: launchd's agents on a Mac."""
UNITS_MADE = (
    ["Library", "Library/LaunchAgents", "Library/Logs", "Library/Logs/jstack"]
    if MAC
    else [".config/systemd", ".config/systemd/user", ".config/systemd/user/timers.target.wants"]
)
"""The folders the units take that the install makes, under HOME, beside `.config/jstack`."""
UNITS_PUT = (
    sorted(f"{label(name)}.plist" for name in TIMERS)
    if MAC
    else sorted([*UNITS, "timers.target.wants"])
)
"""What the units folder holds once a machine with jbus and no opted config has its units: a
link to each unit, or on a Mac an agent for each timer."""
T3_GET = "brew install --cask t3-code" if MAC else "yay -S t3code-bin"
"""How setup says to get T3 Code on this platform, on Arch where it is not a Mac."""
T3_WHERE = "on a Mac with Apple Silicon: " + T3_GET if MAC else "on Arch: t3code-bin"
"""Where the doctor says T3 Code comes from on this platform."""


def linux_only(darwin):
    """Mark a test of `install.sh` that holds on Linux only, as systemd's units do. `darwin` is
    the test of its Darwin case, `<file>::<name>` in this folder, which sets the machine's
    platform itself and so runs on every platform."""
    file, name = darwin.split("::")
    assert f"def {name}(" in (Path(__file__).parent / file).read_text(), darwin
    return pytest.mark.skipif(MAC, reason=f"Linux's case: the Darwin case is {darwin}")


def template(name):
    """Where the source keeps the unit `name`."""
    return unit_templates(REPO)[name]


def laid(home, harness="claude-code"):
    """Where the install assembles `harness`'s layout under `home`."""
    return home / LAYOUTS / harness


def group(script, home, matcher="startup", refuses=False, harness="claude-code"):
    run = f"sh '{laid(home, harness) / 'hooks' / script}'"
    command = run if refuses else f"{run} 2>/dev/null || true"
    hooks = [{"type": "command", "command": command, "timeout": 30 if refuses else 5}]
    return ({"matcher": matcher} if matcher else {}) | {"hooks": hooks}


def layouts(home):
    """The part of each harness's layout under `home`, keyed by what its line says when it
    is ok."""
    return {
        f"hard layout {harness.name} {laid(home, harness.name)}": (
            f" -> README.md: {FLAGGED[harness.name]} name what it leaves out"
            if FLAGGED[harness.name]
            else ""
        )
        for harness in HARNESSES
    }


def hook_parts(home, source):
    """The line of each hook entry that the source's skills.json gives, in its order. Each
    line names the file that the entry's harness reads."""
    files = {harness.name: home / harness.hooks for harness in HARNESSES if harness.hooks}
    return [
        f"hard hook {files[one['harness']]} {one['event']}"
        for hook in layout.hooks(source)
        for one in hook["events"]
    ]


def lines_of(state, parts, home):
    """Each part's line in `state`, with what a layout's ok line adds after it."""
    added = layouts(home) if state == "ok" else {}
    return [f"{state} {part}{added.get(part, '')}" for part in parts]


GENERATED = "ok hard generated files are current"
OFF = {"attribution": {"commit": "", "pr": ""}, "includeCoAuthoredBy": False}
CURSOR_OFF = {"attribution": {"attributeCommitsToAgent": False, "attributePRsToAgent": False}}
UV = """#!/bin/sh
echo "$*" >> "$UV_LOG"
tools=$UV_TOOL_DIR
bin=$HOME/.local/bin
case "$1 $2" in
"tool install")
  [ "$3 $5" = "--editable --reinstall" ] || exit 2
  for name in $(cat "$tools/jstack/names" 2>/dev/null); do rm -f "$bin/$name"; done
  for name in NAMES; do
    [ ! -e "$bin/$name" ] || { echo "error: $name is there and --force was not given"; exit 2; }
  done
  site=$tools/jstack/lib/python3/site-packages/jstack-0.1.0.dist-info
  mkdir -p "$site" "$bin"
  printf '{"url": "file://%s", "dir_info": {"editable": true}}' "$4" > "$site/direct_url.json"
  for root in PACKAGE_ROOTS; do echo "$4/$root"; done > "$site/../_editable_impl_jstack.pth"
  cat > "$site/entry_points.txt" << 'ENTRY_POINTS_END'
ENTRY_POINTS
ENTRY_POINTS_END
  for name in NAMES; do echo "#!/bin/sh" > "$bin/$name"; done
  echo "NAMES" > "$tools/jstack/names"
  ;;
"tool uninstall")
  [ -d "$tools/$3" ] || exit 2
  for name in $(cat "$tools/$3/names"); do rm -f "$bin/$name"; done
  rm -rf "$tools/$3"
  ;;
*) exit 2 ;;
esac
""".replace("NAMES", " ".join(NAMES)).replace("PACKAGE_ROOTS", " ".join(PACKAGE_ROOTS))
UV = UV.replace("ENTRY_POINTS\n", ENTRY_POINTS)


class User:
    """One temporary HOME, and beside it what the stand-ins keep: uv's tools and both
    logs."""

    def __init__(self, tmp_path):
        self.home = tmp_path / "user"
        self.stub = tmp_path / "stub"
        self.tools = tmp_path / "uv-tools"
        self.uv_log = tmp_path / "uv.log"
        self.systemctl_log = tmp_path / "systemctl.log"
        self.jbus = tmp_path / "jbus"
        self.settings = self.home / ".claude" / "settings.json"
        self.codex = self.home / ".codex" / "hooks.json"
        self.bin = self.home / ".local" / "bin"
        self.units = self.home / UNITS_DIR
        self.patterns = self.home / ".config" / "jstack" / "outbound.toml"
        self.providers = self.home / ".config" / "jstack" / "providers.json"
        self.cursor = self.home / ".cursor" / "cli-config.json"
        self.layout = laid(self.home)
        self.START = group("home-start.sh", self.home)
        self.CODEX_START = group("home-start.sh", self.home, harness="codex")
        self.GAUGE = group("home-gauge.sh", self.home, matcher=None)
        self.OUTBOUND = group("outbound-command.sh", self.home, matcher="Bash", refuses=True)
        self.TRAILER = group("ai-trailer.sh", self.home, matcher="Bash", refuses=True)
        self.SENDS = group(
            "agent-sends.sh", self.home, matcher="mcp__t3[-_]code__t3_thread_send", refuses=True
        )
        self.INFRA = group(
            "infra-files.sh",
            self.home,
            matcher="Bash|Write|Edit|MultiEdit|NotebookEdit",
            refuses=True,
        )
        self.CODEX_TRAILER = group(
            "ai-trailer.sh", self.home, matcher="Bash", refuses=True, harness="codex"
        )
        limits = self.layout / "hooks" / "limits.sh"
        self.STATUS = {"type": "command", "command": f"sh '{limits}'"}
        self.home.mkdir()
        self.stub.mkdir()
        self.script("uv", UV)
        (self.stub / "systemctl").symlink_to(SYSTEMCTL)

    def script(self, name, text):
        path = self.stub / name
        path.unlink(missing_ok=True)
        path.write_text(text)
        path.chmod(0o755)
        return path

    def start(self, *args, path=None, cwd=None, checkout=REPO):
        env = {k: v for k, v in os.environ.items() if not k.startswith(SCRUBBED)}
        env |= {
            "HOME": str(self.home),
            "PATH": path or f"{self.stub}:{self.bin}:{os.environ['PATH']}",
            "UV_TOOL_DIR": str(self.tools),
            "UV_LOG": str(self.uv_log),
            "FAKE_SYSTEMCTL_LOG": str(self.systemctl_log),
            "JBUS_CONFIG_DIR": str(self.jbus),
        }
        return daemons.start(
            ["/bin/sh", str(checkout / "install.sh"), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            text=True,
        )

    def run_with_stderr(self, *args, path=None):
        done = self.start(*args, path=path)
        out, err = done.communicate()
        return done.returncode, out.splitlines(), err

    def run(self, *args):
        return self.run_with_stderr(*args)[:2]

    def only(self, *programs):
        """A PATH of one new directory that holds `dirname` and the named stand-ins."""
        narrow = self.stub.parent / "narrow"
        narrow.mkdir(exist_ok=True)
        (narrow / "dirname").symlink_to(shutil.which("dirname"))
        for name in programs:
            (narrow / name).symlink_to(self.stub / name)
        return str(narrow)

    def written(self, harness="claude-code"):
        """The groups the install writes in `harness`'s hooks file, by event, as the hooks of
        skills.json give them."""
        found = {}
        for hook in layout.hooks(REPO):
            for one in hook["events"]:
                if one["harness"] == harness:
                    made = group(
                        hook["name"],
                        self.home,
                        matcher=one.get("matcher"),
                        refuses=one.get("refuses", False),
                        harness=harness,
                    )
                    found.setdefault(one["event"], []).append(made)
        return found

    def links(self):
        return [self.home / root / name for root in ROOTS for name in SKILLS]

    def linked(self):
        """Each skill link, keyed by where it points: its skill in the layout of its root's
        harness."""
        return {
            self.home / harness.root / name: laid(self.home, harness.name) / "skills" / name
            for harness in HARNESSES
            for name in SKILLS
        }

    def parts(self):
        return [
            *layouts(self.home),
            *(f"hard {link}" for link in self.links()),
            f"optional patterns {self.patterns}",
            *hook_parts(self.home, REPO),
            "hard commands jstack",
            f"optional statusline {self.settings}",
            f"hard attribution {self.settings}",
        ]

    def every(self, state, *more):
        """The line of each layout and of each part in `state`, after the generated files'
        line. The generated files are current in this checkout."""
        return [GENERATED, *lines_of(state, [*self.parts(), *more], self.home)]

    def listing(self):
        return sorted(str(path.relative_to(self.home)) for path in self.home.rglob("*"))

    def snapshot(self):
        return {
            str(path): os.readlink(path)
            if path.is_symlink()
            else (path.read_text(), path.stat().st_mtime_ns)
            for path in sorted(self.home.rglob("*"))
            if path.is_symlink() or path.is_file()
        }

    def said(self, log):
        return log.read_text().splitlines() if log.exists() else []

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value))

    def tool(self, name, source, names, roots=PACKAGE_ROOTS, points=ENTRY_POINTS):
        """A tool as uv leaves one. It has its PEP 610 record, a path in its .pth file for
        each root in `roots`, its entry_points.txt, and its commands in the bin directory."""
        site = self.tools / name / "lib" / "python3" / "site-packages" / f"{name}-0.1.0.dist-info"
        self.write(
            site / "direct_url.json", {"url": f"file://{source}", "dir_info": {"editable": True}}
        )
        self.write(site / "entry_points.txt", points)
        self.write(self.tools / name / "names", " ".join(names))
        self.write(
            site.parent / f"_editable_impl_{name}.pth",
            "".join(f"{source}/{root}\n" for root in roots),
        )
        for each in names:
            self.write(self.bin / each, "#!/bin/sh\n")

    def removed_units(self):
        """What `--uninstall` says of the units that `with_jbus` puts: each unit, or on a Mac
        each timer's agent."""
        if MAC:
            return [f"removed agent {self.units / f'{label(name)}.plist'}" for name in TIMERS]
        return [f"removed unit {self.units / name}" for name in UNITS]

    def with_jbus(self):
        self.write(self.jbus / "config.toml", "")
        return f"optional units {self.units}"

    def as_owner(self):
        """The owner's machine: a project that asks for the week's CI report, the relay's keys
        under their older names, and a state tree that backs up to a remote. gitleaks is a
        stand-in on PATH."""
        checkout = self.home / "repo"
        checkout.mkdir()
        self.write(
            self.jbus / "config.toml",
            'server = "http://127.0.0.1:1"\n[[project]]\nname = "jstack"\n'
            f'checkout = "{checkout}"\nprojectId = "p"\nci_report = true\n',
        )
        (self.jbus / "config.toml").chmod(0o600)
        self.write(self.relay_env, RELAY_KEYS)
        state = self.home / ".local" / "state" / "home"
        state.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(state)], check=True)
        origin = "https://github.com/someone/state.git"
        subprocess.run(["git", "-C", str(state), "remote", "add", "origin", origin], check=True)
        self.script("gitleaks", "#!/bin/sh\nexit 0\n")
        return f"optional units {self.units}"

    @property
    def relay_env(self):
        return self.home / ".config" / "jbus-relay" / "env"

    def enabled(self, name):
        target = "default.target" if name.endswith(".service") else "timers.target"
        return (self.units / f"{target}.wants" / name).is_symlink()


@pytest.fixture
def user(tmp_path):
    return User(tmp_path)


def pre_tool_use(file, script):
    """The one PreToolUse group of `file` whose command runs `script`."""
    groups = json.loads(file.read_text())["hooks"]["PreToolUse"]
    (found,) = [one for one in groups if f"/{script}'" in one["hooks"][0]["command"]]
    return found


def line_for(said, part):
    return [line for line in said if f" {part}" in line]


def test_it_puts_every_part_and_says_ok_for_each(user):
    assert len(SKILLS) > 9
    assert user.run() == (0, user.every("ok"))
    for link, skill in user.linked().items():
        assert os.readlink(link) == str(skill)
    assert json.loads(user.settings.read_text()) == {
        "hooks": user.written(),
        "statusLine": user.STATUS,
        **OFF,
    }
    assert json.loads(user.codex.read_text()) == {"hooks": user.written("codex")}
    assert sorted(path.name for path in user.bin.iterdir()) == sorted(NAMES)
    assert user.said(user.uv_log) == [f"tool install --editable {REPO} --reinstall"]
    assert user.said(user.systemctl_log) == []


def test_every_skill_is_linked_into_codexs_home_beside_what_codex_keeps_there(user):
    system = user.home / ".codex" / "skills" / ".system"
    system.mkdir(parents=True)
    user.run()
    linked = sorted((user.home / ".codex" / "skills").iterdir())
    assert linked == [system, *(user.home / ".codex" / "skills" / name for name in SKILLS)]
    assert os.readlink(user.home / ".codex" / "skills" / "pr-review") == str(
        laid(user.home, "codex") / "skills" / "pr-review"
    )


def test_a_second_run_changes_nothing(user):
    user.run()
    before = user.snapshot()
    assert user.run() == (0, user.every("ok"))
    assert user.snapshot() == before
    assert len(user.said(user.uv_log)) == 1


def test_check_changes_nothing_and_says_what_is_missing(user):
    assert user.run("--check") == (1, user.every("missing"))
    assert user.listing() == []
    assert user.said(user.uv_log) == []


@pytest.mark.parametrize("args", [("--stale",), ("--check", "--uninstall"), ("",)])
def test_any_other_argument_is_a_usage_error(user, args):
    assert user.run(*args) == (2, [])
    assert user.listing() == []


def test_check_names_a_broken_link_and_a_run_mends_it(user):
    user.run()
    gone, moved = user.home / ".agents/skills/crew", user.home / ".claude/skills/home"
    gone.unlink()
    moved.unlink()
    moved.symlink_to("/elsewhere/skills/home")
    code, said = user.run("--check")
    assert code == 1
    assert [line for line in said if not line.startswith("ok ")] == [
        f"old hard {moved} -> /elsewhere/skills/home",
        f"missing hard {gone}",
    ]
    assert user.run() == (0, user.every("ok"))
    assert user.run("--check") == (0, user.every("ok"))


def test_a_directory_where_a_link_goes_is_left_alone(user):
    own = user.home / ".claude/skills/crew"
    user.write(own / "SKILL.md", "mine\n")
    code, said = user.run()
    assert code == 1
    assert f"old hard {own} -> not a link" in said
    user.run("--uninstall")
    assert (own / "SKILL.md").read_text() == "mine\n"
    assert not (own / "crew").exists()


def test_a_link_to_a_skill_the_checkout_no_longer_has_is_old_and_a_run_unlinks_it(user):
    user.run()
    dead = user.home / ".claude/skills/retired"
    dead.symlink_to(REPO / "skills" / "retired")
    was = f"{REPO / 'skills' / 'retired'}, a skill this checkout no longer has"
    code, said = user.run("--check")
    assert (code, line_for(said, dead)) == (1, [f"old hard {dead} -> {was}"])
    code, said = user.run()
    assert (code, line_for(said, dead)) == (0, [f"ok hard {dead} -> unlinked"])
    assert not dead.is_symlink()
    assert user.run("--check") == (0, user.every("ok"))


@pytest.mark.parametrize("root", [".claude/skills", ".codex/skills"])
def test_the_retired_deeper_skill_is_unlinked_by_a_run(user, root):
    user.run()
    dead = user.home / root / "deeper"
    dead.symlink_to(REPO / "skills" / "deeper")
    assert not (REPO / "skills" / "deeper").exists()
    code, said = user.run()
    assert (code, line_for(said, dead)) == (0, [f"ok hard {dead} -> unlinked"])
    assert not dead.is_symlink()
    assert line_for(user.run("--check")[1], dead) == []


def test_a_hook_already_in_a_hooks_file_is_kept(user):
    other = {"hooks": [{"type": "command", "command": "echo hello"}]}
    stop = [{"hooks": [{"type": "command", "command": "echo bye"}]}]
    user.write(user.codex, {"hooks": {"SessionStart": [other], "Stop": stop}})
    part = f"hook {user.codex} SessionStart"
    assert line_for(user.run("--check")[1], part) == [f"missing hard {part}"]
    assert user.run() == (0, user.every("ok"))
    assert json.loads(user.codex.read_text()) == {
        "hooks": {
            "SessionStart": [other, user.CODEX_START],
            "Stop": stop,
            "PreToolUse": [user.CODEX_TRAILER],
        }
    }
    before = user.codex.read_text()
    user.run()
    assert user.codex.read_text() == before
    user.run("--uninstall")
    assert json.loads(user.codex.read_text()) == {"hooks": {"SessionStart": [other], "Stop": stop}}


def test_an_entry_for_another_checkout_is_old_and_replaced(user):
    was = "sh /old/jstack/hooks/home-start.sh"
    beside = {"type": "command", "command": "echo hello"}
    entry = {"matcher": "startup", "hooks": [beside, {"type": "command", "command": was}]}
    user.write(user.codex, {"hooks": {"SessionStart": [entry]}})
    part = f"hook {user.codex} SessionStart"
    assert line_for(user.run("--check")[1], part) == [f"old hard {part} -> {was}"]
    assert user.run()[0] == 0
    assert json.loads(user.codex.read_text()) == {
        "hooks": {
            "SessionStart": [{"matcher": "startup", "hooks": [beside]}, user.CODEX_START],
            "PreToolUse": [user.CODEX_TRAILER],
        }
    }


def test_a_hook_whose_script_no_feature_declares_is_old_and_taken_out(user):
    retired = group("retired-gauge.sh", user.home, matcher=None)
    mine = {"hooks": [{"type": "command", "command": "sh /mine/hooks/retired-gauge.sh"}]}
    beside = {"type": "command", "command": "echo hello"}
    shared = {"matcher": "Bash", "hooks": [beside, *retired["hooks"]]}
    user.write(
        user.settings,
        {"model": "one", "hooks": {"PreToolUse": [retired, mine], "PostToolUse": [shared]}},
    )
    command = retired["hooks"][0]["command"]
    pre = f"hook {user.settings} PreToolUse hooks/retired-gauge.sh"
    post = f"hook {user.settings} PostToolUse hooks/retired-gauge.sh"
    said = user.run("--check")[1]
    assert line_for(said, pre) == [f"old hard {pre} -> {command}, a script no feature declares"]
    assert line_for(said, post) == [f"old hard {post} -> {command}, a script no feature declares"]
    code, said = user.run()
    assert (code, line_for(said, pre)) == (0, [f"ok hard {pre} -> taken out"])
    assert line_for(said, post) == [f"ok hard {post} -> taken out"]
    hooks = user.written()
    hooks["PreToolUse"] = [mine, *hooks["PreToolUse"]]
    hooks["PostToolUse"] = [{"matcher": "Bash", "hooks": [beside]}, *hooks.get("PostToolUse", [])]
    wanted = {"model": "one", "hooks": hooks, "statusLine": user.STATUS} | OFF
    assert json.loads(user.settings.read_text()) == wanted
    assert user.run("--check") == (0, user.every("ok"))


def test_a_hand_written_claude_hook_is_old_and_replaced_and_no_other_key_is_touched(user):
    by_hand = 'sh "$HOME/repos/jstack/hooks/skill-tips.sh" 2>/dev/null || true'
    written = {
        "model": "one",
        "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": by_hand}]}]},
        "statusLine": {"type": "command", "command": "sh /mine/line.sh"},
    }
    user.write(user.settings, written)
    part = f"hook {user.settings} UserPromptSubmit"
    code, said = user.run("--check")
    assert line_for(said, part) == [f"old hard {part} -> {by_hand}"]
    assert line_for(said, "statusline") == []
    assert user.run()[0] == 0
    assert json.loads(user.settings.read_text()) == written | {"hooks": user.written()} | OFF
    assert user.run("--uninstall")[0] == 0
    assert json.loads(user.settings.read_text()) == {
        "model": "one",
        "statusLine": written["statusLine"],
    }


@pytest.mark.parametrize(
    "written",
    [
        "{ not json",
        "[]",
        "{} {}",
        '{"hooks": []}',
        '{"hooks": {"SessionStart": {"matcher": "startup"}}}',
        '{"hooks": {"SessionStart": ["echo hello"]}}',
        '{"hooks": {"SessionStart": [{"hooks": "echo hello"}]}}',
    ],
)
def test_a_file_that_is_no_hooks_file_is_left_alone(user, written):
    user.write(user.codex, written)
    part = f"hook {user.codex} SessionStart"
    for args in ((), ("--check",), ("--uninstall",)):
        code, said = user.run(*args)
        if args != ("--uninstall",):
            assert (code, line_for(said, part)) == (1, [f"old hard {part} -> not a hooks file"])
        assert user.codex.read_text() == written


@pytest.mark.parametrize("written", ["", "\n"])
def test_an_empty_hooks_file_is_missing_the_entry_and_gets_it(user, written):
    user.write(user.codex, written)
    assert user.run("--check") == (1, user.every("missing"))
    assert user.run() == (0, user.every("ok"))
    assert json.loads(user.codex.read_text()) == {"hooks": user.written("codex")}


def test_a_settings_file_that_is_a_link_is_written_where_it_points(user, tmp_path):
    kept = tmp_path / "dotfiles" / "settings.json"
    stop = [{"hooks": [{"type": "command", "command": "echo bye"}]}]
    user.write(kept, {"hooks": {"Stop": stop}})
    user.settings.parent.mkdir(parents=True)
    user.settings.symlink_to(kept)
    assert user.run() == (0, user.every("ok"))
    assert os.readlink(user.settings) == str(kept)
    assert json.loads(kept.read_text()) == {
        "hooks": {"Stop": stop, **user.written()},
        "statusLine": user.STATUS,
        **OFF,
    }
    assert sorted(path.name for path in kept.parent.iterdir()) == ["settings.json"]
    assert user.run("--uninstall")[0] == 0
    assert os.readlink(user.settings) == str(kept)
    assert json.loads(kept.read_text()) == {"hooks": {"Stop": stop}}


def test_the_limits_writer_of_another_checkout_is_old_and_replaced(user):
    was = "sh '/old/jstack/hooks/limits.sh'"
    user.write(user.settings, {"statusLine": {"type": "command", "command": was}})
    part = f"statusline {user.settings}"
    assert line_for(user.run("--check")[1], part) == [f"old optional {part} -> {was}"]
    assert user.run() == (0, user.every("ok"))
    assert json.loads(user.settings.read_text())["statusLine"] == user.STATUS


def test_the_units_are_not_linked_while_the_commands_could_not_be_put(user):
    units = user.with_jbus()
    user.write(user.bin / NAMES[0], "theirs\n")

    code, said, err = user.run_with_stderr()

    assert (code, line_for(said, "units")) == (1, [f"missing {units}"])
    assert f"install.sh: units {user.units}: no ~/.local/bin/jbus" in err
    assert not user.units.exists()
    assert user.said(user.systemctl_log) == []


def test_a_module_in_the_directory_it_is_run_from_is_not_imported(user, tmp_path):
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "json.py").write_text("raise SystemExit(9)\n")

    done = user.start("--check", cwd=planted)
    out, _ = done.communicate()

    assert (done.returncode, out.splitlines()) == (1, user.every("missing"))


def test_the_units_are_not_due_on_a_machine_with_no_jbus_config(user):
    user.run()
    assert not user.units.exists()
    assert line_for(user.run("--check")[1], "units") == []


def record(user):
    created = user.home / ".local" / "state" / "jstack" / "created"
    return sorted(
        str(Path(line).relative_to(user.home)) for line in created.read_text().splitlines()
    )


def test_the_record_holds_the_containers_the_install_created_and_nothing_else(user):
    (user.home / ".claude").mkdir()
    user.with_jbus()
    user.run()
    assert record(user) == sorted(
        [
            ".agents",
            ".agents/skills",
            ".claude/settings.json",
            ".claude/skills",
            ".codex",
            ".codex/hooks.json",
            ".codex/skills",
            ".config",
            ".config/jstack",
            *UNITS_MADE,
            ".local",
            ".local/bin",
            ".local/share",
            ".local/share/jstack",
            ".local/share/jstack/harness",
            *(f".local/share/jstack/harness/{harness.name}" for harness in HARNESSES),
            ".local/state",
        ]
    )


def test_uninstall_leaves_a_new_home_as_it_was_and_a_second_one_prints_nothing(user):
    user.with_jbus()
    user.run()
    code, said = user.run("--uninstall")
    assert code == 0
    assert set(said) >= {
        *(f"removed {link}" for link in user.links()),
        f"removed hook {user.settings} SessionStart",
        f"removed hook {user.settings} UserPromptSubmit",
        f"removed hook {user.settings} PostToolUse",
        f"removed hook {user.codex} SessionStart",
        f"removed patterns {user.patterns}",
        f"removed hook {user.settings} PreToolUse",
        f"removed statusline {user.settings}",
        "removed commands jstack",
        *user.removed_units(),
    }
    assert all(line.startswith("removed ") for line in said)
    assert user.listing() == []
    if not MAC:
        disabled = {f"--user disable --now {t}" for t in [*TIMERS, *OPTED]}
        assert disabled <= set(user.said(user.systemctl_log))
    assert user.said(user.uv_log)[-1] == "tool uninstall jstack"
    assert user.run("--uninstall") == (0, [])
    assert user.listing() == []


def test_uninstall_removes_only_what_names_this_checkout(user):
    theirs = user.home / ".claude/skills/theirs"
    theirs.mkdir(parents=True)
    user.write(user.home / ".local/bin/theirs", "#!/bin/sh\n")
    user.run()
    elsewhere = user.home / ".claude/skills/home"
    elsewhere.unlink()
    elsewhere.symlink_to("/elsewhere/skills/home")
    code, said = user.run("--uninstall")
    assert code == 0
    assert f"removed {elsewhere}" not in said
    assert user.listing() == [
        ".claude",
        ".claude/skills",
        ".claude/skills/home",
        ".claude/skills/theirs",
        ".local",
        ".local/bin",
        ".local/bin/theirs",
    ]
    assert os.readlink(elsewhere) == "/elsewhere/skills/home"


@linux_only("test_launchd.py::test_a_sandbox_never_runs_the_systems_launchctl")
def test_with_a_manager_that_reads_another_home_only_the_links_are_made_and_removed(user):
    units = user.with_jbus()
    log = user.systemctl_log
    user.script("systemctl", f'#!/bin/sh\necho "$*" >> "{log}"\necho HOME=/another/home\n')
    assert user.run() == (0, user.every("ok", units))
    assert os.readlink(user.units / "jbus.timer") == str(
        REPO / "features" / "jbus" / "units" / "jbus.timer"
    )
    assert user.run("--uninstall")[0] == 0
    assert user.listing() == []
    assert set(user.said(log)) == {"--user show-environment"}


def test_a_tool_that_is_no_editable_install_is_not_put_over_and_uninstall_keeps_it(user):
    user.write(user.tools / "jstack" / "names", " ".join(NAMES))
    not_ours = (
        "tool jstack is installed from a release or an index, "
        "not as an editable install of this checkout"
    )
    for args in ((), ("--check",)):
        code, said = user.run(*args)
        assert (code, line_for(said, "commands")) == (
            1,
            [f"old hard commands jstack -> {not_ours}"],
        )
    assert user.said(user.uv_log) == []
    code, said = user.run("--uninstall")
    assert code == 0
    assert line_for(said, "commands") == [
        "kept commands jstack -> not an editable install of a checkout"
    ]
    assert (user.tools / "jstack").is_dir()


def test_a_link_by_another_name_to_a_skill_the_checkout_has_is_not_this_installs(user):
    user.run()
    alias = user.home / ".claude/skills/alias"
    alias.symlink_to(REPO / "features" / "crew")
    assert user.run("--check") == (0, user.every("ok"))
    user.run("--uninstall")
    assert os.readlink(alias) == str(REPO / "features" / "crew")


def test_uninstall_keeps_a_container_it_made_while_something_else_is_in_it(user):
    user.run()
    mine = user.home / ".agents" / "mine.txt"
    mine.write_text("mine\n")
    settings = json.loads(user.settings.read_text())
    user.settings.write_text(json.dumps(settings | {"model": "one"}))

    code, said = user.run("--uninstall")

    assert code == 0
    assert f"removed {user.home / '.agents'}" not in said
    assert f"removed {user.settings}" not in said
    assert json.loads(user.settings.read_text()) == {"model": "one"}
    assert record(user) == [".agents", ".claude", ".claude/settings.json", ".local", ".local/state"]
    assert user.run("--uninstall") == (0, [])

    mine.unlink()
    user.settings.write_text("{}\n")
    code, said = user.run("--uninstall")
    assert sorted(said) == sorted(
        f"removed {user.home / path}"
        for path in (".agents", ".claude", ".claude/settings.json", ".local", ".local/state")
    )
    assert user.listing() == []


def test_a_second_run_waits_for_the_one_that_holds_the_homes_lock(user):
    held = os.open(user.home, os.O_RDONLY)
    fcntl.flock(held, fcntl.LOCK_EX)
    waiting = user.start()
    with pytest.raises(subprocess.TimeoutExpired):
        waiting.wait(timeout=1)
    assert user.listing() == []
    assert user.run("--check")[0] == 1
    os.close(held)
    out, _ = waiting.communicate(timeout=60)
    assert (waiting.returncode, out.splitlines()) == (0, user.every("ok"))
    assert [path for path in user.listing() if path.endswith(".new")] == []


def test_with_no_python_3_12_the_shim_runs_jinstall_through_uv(user):
    user.script("python3", "#!/bin/sh\nexit 1\n")
    (user.stub / "python").symlink_to(user.stub / "python3")
    through_uv = f'[ "$1" != run ] || {{ shift 5; exec "{sys.executable}" "$@"; }}\n'
    user.script("uv", UV.replace("#!/bin/sh\n", "#!/bin/sh\n" + through_uv, 1))
    path = user.only("python3", "python", "uv")

    code, said, _ = user.run_with_stderr("--check", path=path)

    assert (code, said) == (1, user.every("missing"))


def test_with_no_python_3_12_and_no_uv_the_shim_says_so(user):
    user.script("python3", "#!/bin/sh\nexit 1\n")

    code, said, _ = user.run_with_stderr(path=user.only("python3"))

    assert code == 1
    assert said == ["missing hard python -> 3.12 or newer, or uv, which brings one"]
    assert user.listing() == []


def test_with_no_uv_the_commands_stay_missing_and_the_reason_is_on_stderr(user):
    user.script("python3", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')

    code, said, err = user.run_with_stderr(path=user.only("python3"))

    assert (code, line_for(said, "commands")) == (1, ["missing hard commands jstack"])
    reason = f"uv tool install --editable {REPO} --reinstall: uv is not on PATH"
    assert f"install.sh: commands jstack: {reason}" in err.splitlines()


def test_a_file_that_changes_under_a_write_is_read_again_once(tmp_path):
    file = tmp_path / "settings.json"
    file.write_text("{}")
    there = machine(tmp_path, tmp_path, tmp_path)
    times = []

    def change(value):
        times.append(dict(value))
        if len(times) == 1:
            file.write_text('{"theirs": 1}')
        value["ours"] = 1
        return True

    assert rewrite(there, file, change) is True
    assert times == [{}, {"theirs": 1}]
    assert json.loads(file.read_text()) == {"theirs": 1, "ours": 1}


def test_a_file_that_changes_under_both_writes_is_left_as_the_other_writer_has_it(tmp_path):
    file = tmp_path / "settings.json"
    file.write_text("{}")
    there = machine(tmp_path, tmp_path, tmp_path)
    times = []

    def change(value):
        times.append(1)
        file.write_text(json.dumps({"theirs": len(times)}))
        value["ours"] = 1
        return True

    with pytest.raises(Moved):
        rewrite(there, file, change)
    assert json.loads(file.read_text()) == {"theirs": 2}
    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.json"]


@pytest.mark.parametrize(
    ("account", "line"),
    [
        ("home", "old: systemctl --user did not answer, so jbus.timer is not enabled"),
        ("account", "ok: "),
    ],
)
def test_linked_units_are_old_under_the_accounts_own_home_when_no_manager_answers(
    tmp_path, account, line
):
    home, checkout = tmp_path / "home", tmp_path / "checkout"
    units = Units(home / "units", ("jbus.timer",), ("jbus.timer",), home / "config.toml")
    (checkout / "templates").mkdir(parents=True)
    (checkout / "templates" / "jbus.timer").write_text("[Timer]\n")
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "jbus").write_text("")
    there = machine(checkout, home, tmp_path / account, lambda args: Ran(1, ""))
    units.put(there)

    found = units.probe(there)

    assert f"{found.state.value}: {found.detail}" == line


def machine(checkout, home, account, run=lambda args: Ran(None, "")):
    return Machine(checkout, home, {"PATH": ""}, run, account)


@pytest.mark.parametrize("answer", [Ran(0, "HOME=/another/home\n"), Ran(1, ""), Ran(None, "")])
def test_systemctl_runs_nothing_against_a_manager_whose_home_is_not_this_one(tmp_path, answer):
    asked = []

    def run(args):
        asked.append(list(args))
        return answer

    there = machine(tmp_path, tmp_path / "home", tmp_path / "home", run)

    assert there.systemctl("enable", "--now", "jbus.timer") is None
    assert there.systemctl("disable", "--now", "jbus.timer") is None
    assert asked == [["systemctl", "--user", "show-environment"]] * 2


def test_systemctl_runs_against_the_manager_that_reads_this_home(tmp_path):
    asked = []

    def run(args):
        asked.append(list(args))
        return Ran(0, f"LANG=C\nHOME={tmp_path / 'home'}\n")

    there = machine(tmp_path, tmp_path / "home", tmp_path / "home", run)

    assert there.systemctl("daemon-reload") is not None
    assert asked[-1] == ["systemctl", "--user", "daemon-reload"]


def worktree(tmp_path):
    main, linked = tmp_path / "main", tmp_path / "linked"
    subprocess.run(["git", "init", "-q", main], check=True)
    commit = ["-c", "user.name=a", "-c", "user.email=a@example.test", "commit", "-q"]
    subprocess.run(["git", "-C", main, *commit, "--allow-empty", "-m", "start"], check=True)
    subprocess.run(["git", "-C", main, "worktree", "add", "-q", linked], check=True)
    item = {"name": "crew", "kind": "skill", "path": "skills/crew/SKILL.md"}
    plugin = {"repository": "https://example.test/jstack"}
    for checkout in (main, linked):
        (checkout / "skills" / "crew").mkdir(parents=True)
        (checkout / "skills" / "crew" / "SKILL.md").write_text("crew\n")
        pushed = {"name": "pre-push", "path": "features/jleak/hooks/pre-push.sh"}
        listed = {"items": [item], "gitHooks": [pushed]}
        (checkout / "skills.json").write_text(json.dumps(listed))
        (checkout / "plugin.json").write_text(json.dumps(plugin))
        (checkout / "pyproject.toml").write_text('[project]\nname = "jstack"\nscripts = {}\n')
    return main, linked


def test_no_hook_is_retired_while_skills_json_cannot_be_read(tmp_path):
    main, _ = worktree(tmp_path)
    (main / "skills.json").write_text("{")
    home = tmp_path / "home"
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"hooks": {"SessionStart": [group("home-start.sh", home)]}}))

    listed = needs(machine(main, home, account=tmp_path / "account"))

    assert [need.name for need in listed if isinstance(need.kind, RetiredHook)] == []


def test_a_plain_install_from_a_linked_worktree_under_the_accounts_own_home_is_refused(tmp_path):
    main, linked = worktree(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    refused = run_install(machine(linked, home, account=home), write=True)

    assert (refused.lines, refused.code) == ((), 1)
    assert refused.note == (
        f"install.sh: {linked} is a linked worktree, and HOME is your own: "
        "install from the main checkout"
    )
    assert list(home.iterdir()) == []
    checked = run_install(machine(linked, home, account=home), write=False)
    crew = f"{home}/.claude/skills/crew"
    assert line_for(checked.lines, crew) == [f"missing hard {crew}"]
    in_a_sandbox = run_install(machine(linked, home, account=tmp_path / "account"), write=True)
    assert line_for(in_a_sandbox.lines, crew) == [f"ok hard {crew}"]
    assert os.readlink(crew) == str(laid(home) / "skills" / "crew")
    assert os.readlink(laid(home) / "skills" / "crew" / "SKILL.md") == str(
        linked / "skills" / "crew" / "SKILL.md"
    )


def test_a_plain_install_from_the_main_checkout_under_the_accounts_own_home_runs(tmp_path):
    main, linked = worktree(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    done = run_install(machine(main, home, account=home), write=True)

    crew = f"{home}/.claude/skills/crew"
    assert line_for(done.lines, crew) == [f"ok hard {crew}"]


def test_the_private_patterns_are_made_once_and_never_written_again(user):
    part = f"optional patterns {user.patterns}"
    assert line_for(user.run("--check")[1], "patterns") == [f"missing {part}"]
    assert not user.patterns.exists()
    user.run()
    made = user.patterns.read_text()
    assert f"home-path = '{re.escape(str(user.home))}(?![\\w-])'" in made.splitlines()
    assert [pattern.name for pattern in jleak.load(user.patterns)][:2] == ["home-path", "thread-id"]
    mine = made + "codename = 'zorblat'\n"
    user.patterns.write_text(mine)
    assert user.run() == (0, user.every("ok"))
    assert user.patterns.read_text() == mine


def test_private_patterns_jleak_cannot_read_are_old_and_left_as_they_are(user):
    user.write(user.patterns, "[patterns]\ncodename = '(unclosed'\n")
    code, said = user.run()
    assert code == 1
    assert line_for(said, "patterns") == [
        f"old optional patterns {user.patterns} -> patterns.codename: not a regular expression"
    ]
    assert user.patterns.read_text() == "[patterns]\ncodename = '(unclosed'\n"


def test_uninstall_keeps_private_patterns_the_user_added_to(user):
    user.run()
    user.patterns.write_text(user.patterns.read_text() + "codename = 'zorblat'\n")
    code, said = user.run("--uninstall")
    kept = f"kept patterns {user.patterns} -> yours, it is not as the install made it"
    assert (code, [line for line in said if line.startswith("kept ")]) == (0, [kept])
    assert "codename = 'zorblat'" in user.patterns.read_text().splitlines()
    assert not user.settings.exists()


def test_the_command_hook_the_install_writes_refuses_through_its_exit_code(user):
    user.run()
    written = pre_tool_use(user.settings, "outbound-command.sh")
    assert written == user.OUTBOUND
    asked = {"tool_name": "Bash", "tool_input": {"command": "git push --no-verify"}, "cwd": "/"}
    done = subprocess.run(
        written["hooks"][0]["command"],
        shell=True,
        input=json.dumps(asked),
        capture_output=True,
        text=True,
        env=os.environ | {"XDG_CONFIG_HOME": str(user.home / ".config")},
    )
    assert done.returncode == 2
    assert done.stderr.splitlines()[0] == "command:1: push-no-verify"


@pytest.mark.parametrize("harness", ["claude-code", "codex"])
def test_the_trailer_hook_the_install_writes_for_each_harness_refuses_an_ai_trailer(user, harness):
    user.run()
    file = user.settings if harness == "claude-code" else user.codex
    written = pre_tool_use(file, "ai-trailer.sh")
    assert written == (user.TRAILER if harness == "claude-code" else user.CODEX_TRAILER)
    trailer = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    for command, code in ((f"git commit -m x -m '{trailer}'", 2), ("git commit -m x", 0)):
        asked = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/"}
        done = subprocess.run(
            written["hooks"][0]["command"],
            shell=True,
            input=json.dumps(asked),
            capture_output=True,
            text=True,
        )
        assert done.returncode == code, done.stderr


def test_the_gauge_hook_the_install_writes_denies_a_tool_call_past_the_ceiling(user, tmp_path):
    user.run()
    written = pre_tool_use(user.settings, "home-gauge.sh")
    assert written == user.GAUGE
    main, transcript = tmp_path / "demo", tmp_path / "session-1.jsonl"
    subprocess.run(["git", "init", "-q", main], check=True)
    usage = {"input_tokens": 350000}
    message = {"id": "m1", "model": "claude-x", "usage": usage}
    transcript.write_text(json.dumps({"type": "assistant", "message": message}) + "\n")
    asked = {
        "session_id": "session-1",
        "transcript_path": str(transcript),
        "cwd": str(main),
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {},
    }
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    done = subprocess.run(
        written["hooks"][0]["command"],
        shell=True,
        input=json.dumps(asked),
        capture_output=True,
        text=True,
        env=env | {"HOME": str(user.home), "T3_MCP_BEARER_TOKEN": "x"},
    )
    assert (done.returncode, done.stderr) == (0, "")
    assert json.loads(done.stdout)["hookSpecificOutput"] == {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "context: 350000 tokens, over this home's ceiling of 350000."
        f" Only the handoff runs now: read {user.layout / 'skills' / 'handoff' / 'SKILL.md'}"
        " and do its steps.",
    }


def test_a_machine_with_the_gauge_only_after_a_tool_call_gets_it_before_one_too(user):
    user.run()
    written = json.loads(user.settings.read_text())
    written["hooks"]["PreToolUse"] = [user.OUTBOUND]
    user.settings.write_text(json.dumps(written))
    part = f"hook {user.settings} PreToolUse"
    code, said = user.run("--check")
    assert (code, line_for(said, part)) == (
        1,
        [*[f"missing hard {part}"] * 4, f"ok hard {part}"],
    )
    assert user.run() == (0, user.every("ok"))
    assert json.loads(user.settings.read_text())["hooks"]["PreToolUse"] == [
        user.OUTBOUND,
        user.SENDS,
        user.TRAILER,
        user.GAUGE,
        user.INFRA,
    ]
    assert user.run("--check") == (0, user.every("ok"))


def checkout_under(user):
    """A main checkout inside the user's HOME. It has this checkout's installer, hooks and
    code, and the source of its layouts."""
    checkout = user.home / "repos" / "jstack"
    checkout.mkdir(parents=True)
    for name in ("install.sh", "pyproject.toml", "skills.json", "plugin.json"):
        shutil.copy(REPO / name, checkout / name)
    for name in ("features",):
        shutil.copytree(REPO / name, checkout / name, ignore=shutil.ignore_patterns("__pycache__"))
    subprocess.run(["git", "init", "-q", checkout], check=True)
    return checkout, f"hard hook {checkout / '.git' / 'hooks' / 'pre-push'} pre-push"


def test_the_push_hook_is_linked_in_a_main_checkout_that_the_home_holds(user):
    checkout, part = checkout_under(user)
    link = checkout / ".git" / "hooks" / "pre-push"

    def run(*args):
        said = user.start(*args, checkout=checkout).communicate()[0]
        return [line for line in said.splitlines() if "pre-push" in line]

    assert run("--check") == [f"missing {part}"]
    assert run() == [f"ok {part}"]
    assert os.readlink(link) == str(checkout / "features" / "jleak" / "hooks" / "pre-push.sh")
    assert os.access(link, os.X_OK)
    assert run("--check") == [f"ok {part}"]
    assert run("--uninstall") == [f"removed {link}"]
    assert not link.is_symlink()


def test_a_push_hook_of_the_users_own_is_left_alone(user):
    checkout, part = checkout_under(user)
    own = checkout / ".git" / "hooks" / "pre-push"
    own.write_text("#!/bin/sh\n")
    done = user.start(checkout=checkout)
    said = done.communicate()[0].splitlines()
    script = checkout / "features" / "jleak" / "hooks" / "pre-push.sh"
    assert line_for(said, "pre-push") == [
        f"old {part} -> a hook of the repo's own, which the install does not write over: "
        f"to run jstack's as well, add sh '{script}' \"$@\" to it"
    ]
    user.start("--uninstall", checkout=checkout).wait()
    assert own.read_text() == "#!/bin/sh\n"


def test_a_checkout_outside_a_sandboxed_home_and_a_worktree_get_no_push_hook(tmp_path):
    main, linked = worktree(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    for checkout, account, due in (
        (main, home, True),
        (main, tmp_path / "account", False),
        (linked, tmp_path / "account", False),
    ):
        said = run_install(machine(checkout, home, account=account), write=False).lines
        assert bool(line_for(said, "pre-push")) is due, (checkout, account)
    assert not (main / ".git" / "hooks" / "pre-push").exists()


def test_a_repo_that_points_git_at_other_hooks_is_told_so(tmp_path):
    main, _ = worktree(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    def run(args):
        return Ran(0, "/elsewhere/hooks\n") if "core.hooksPath" in args else Ran(None, "")

    said = run_install(machine(main, home, account=home, run=run), write=True).lines
    script = main / "features" / "jleak" / "hooks" / "pre-push.sh"
    assert line_for(said, "pre-push") == [
        f"old hard hook {main / '.git' / 'hooks' / 'pre-push'} pre-push"
        " -> core.hooksPath is set, so git runs /elsewhere/hooks/pre-push, which the install"
        f" does not write over: to run jstack's as well, add sh '{script}' \"$@\" to it"
    ]
    assert not (main / ".git" / "hooks" / "pre-push").is_symlink()


def releasing(tmp_path, plugin=None):
    """A clean main that is origin/main, and a bare origin. The main has this checkout's
    Makefile, pyproject.toml and plugin.json, with the plugin.json at `plugin` when the
    caller gives one."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git = ["git", "-C", str(work)]
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    for name in ("Makefile", "pyproject.toml", "plugin.json"):
        shutil.copy(REPO / name, work / name)
    if plugin is not None:
        made = json.loads((work / "plugin.json").read_text()) | {"version": plugin}
        (work / "plugin.json").write_text(json.dumps(made))
    for step in (
        ["config", "user.name", "jstack"],
        ["config", "user.email", "jstack@example.invalid"],
        ["add", "-A"],
        ["commit", "-qm", "main"],
        ["remote", "add", "origin", str(origin)],
        ["push", "-q", "origin", "main"],
    ):
        subprocess.run([*git, *step], check=True)
    return origin, work


def tags(where):
    found = subprocess.run(["git", "-C", str(where), "tag", "-l"], capture_output=True, text=True)
    return found.stdout.split()


def release(work):
    return subprocess.run(["make", "-s", "release"], cwd=work, capture_output=True, text=True)


def test_make_release_tags_nothing_when_plugin_json_has_another_version(tmp_path):
    origin, work = releasing(tmp_path, plugin="9.9.9")
    made = release(work)
    assert made.returncode != 0
    assert "plugin.json's" in made.stdout
    assert (tags(work), tags(origin)) == ([], [])


def test_a_push_that_fails_leaves_no_tag_and_a_second_make_release_pushes_it(tmp_path):
    origin, work = releasing(tmp_path)
    hook = origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    assert release(work).returncode != 0
    assert (tags(work), tags(origin)) == ([], [])
    hook.unlink()
    assert release(work).returncode == 0
    version = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    assert tags(work) == tags(origin) == [f"v{version}"]


def test_a_settings_file_with_no_attribution_gets_it_and_keeps_every_other_key(user):
    written = {"model": "one", "env": {"A": "1"}, "permissions": {"allow": ["Bash(ls)"]}}
    user.write(user.settings, written)
    part = f"attribution {user.settings}"
    assert line_for(user.run("--check")[1], part) == [f"missing hard {part}"]
    assert line_for(user.run()[1], part) == [f"ok hard {part}"]
    assert (
        json.loads(user.settings.read_text())
        == written
        | {
            "hooks": user.written(),
            "statusLine": user.STATUS,
        }
        | OFF
    )


@pytest.mark.parametrize(
    ("there", "detail"),
    [
        (
            {"attribution": {"commit": "", "pr": ""}, "includeCoAuthoredBy": None},
            "includeCoAuthoredBy is null",
        ),
        (
            {"attribution": {"commit": "Co-Authored-By: Claude"}},
            'attribution is {"commit": "Co-Authored-By: Claude"}',
        ),
        ({"includeCoAuthoredBy": True}, "attribution is not set"),
    ],
)
def test_a_differing_value_is_reported_by_check_and_set_by_a_run(user, there, detail):
    user.write(user.settings, {"model": "one", **there})
    part = f"attribution {user.settings}"
    code, said = user.run("--check")
    assert (code, line_for(said, part)) == (1, [f"old hard {part} -> {detail}"])
    assert json.loads(user.settings.read_text()) == {"model": "one", **there}
    assert line_for(user.run()[1], part) == [f"ok hard {part}"]
    value = json.loads(user.settings.read_text())
    assert (value["model"], value["attribution"], value["includeCoAuthoredBy"]) == (
        "one",
        OFF["attribution"],
        False,
    )


def test_uninstall_takes_out_only_the_attribution_the_install_set(user):
    user.write(user.settings, {"attribution": {"commit": "mine", "pr": ""}})
    user.run()
    user.write(user.settings, json.loads(user.settings.read_text()) | {"includeCoAuthoredBy": True})
    assert user.run("--uninstall")[0] == 0
    assert json.loads(user.settings.read_text()) == {"includeCoAuthoredBy": True}


def declare(user, home):
    user.write(
        user.providers,
        {
            "claudeAgent": {"driver": "claudeAgent", "enabled": True},
            "prime": {"driver": "claudeAgent", "enabled": True, "config": {"homePath": home}},
        },
    )


def test_a_declared_claude_home_with_its_own_settings_gets_the_attribution_too(user):
    declare(user, "~/.claude_prime")
    prime = user.home / ".claude_prime" / "settings.json"
    user.write(prime, {"model": "two"})
    part = f"attribution {prime}"
    assert line_for(user.run("--check")[1], part) == [f"missing hard {part}"]
    assert line_for(user.run()[1], part) == [f"ok hard {part}"]
    assert json.loads(prime.read_text()) == {"model": "two", **OFF}


def test_a_declared_home_whose_settings_link_to_the_main_ones_shares_that_one_file(user):
    declare(user, "~/.claude_prime")
    prime = user.home / ".claude_prime" / "settings.json"
    prime.parent.mkdir(parents=True)
    prime.symlink_to(user.settings)
    user.run()
    assert line_for(user.run("--check")[1], f"attribution {prime}") == [
        f"ok hard attribution {prime}"
    ]
    assert prime.is_symlink()
    assert json.loads(user.settings.read_text())["attribution"] == OFF["attribution"]


def test_a_declared_home_with_no_settings_yet_is_left_to_the_mirror(user):
    declare(user, "~/.claude_prime")
    (user.home / ".claude_prime").mkdir()
    assert line_for(user.run()[1], ".claude_prime") == []
    assert not (user.home / ".claude_prime" / "settings.json").exists()


def test_cursors_cli_config_gets_its_attribution_only_once_cursor_has_made_it(user):
    assert line_for(user.run()[1], f"attribution {user.cursor}") == []
    assert not user.cursor.exists()
    mine = {"permissions": {"allow": ["Shell(ls)"], "deny": []}, "editor": {"vimMode": True}}
    user.write(user.cursor, mine)
    part = f"attribution {user.cursor}"
    assert line_for(user.run("--check")[1], part) == [f"missing hard {part}"]
    assert line_for(user.run()[1], part) == [f"ok hard {part}"]
    assert json.loads(user.cursor.read_text()) == mine | CURSOR_OFF
