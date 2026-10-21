"""`install.sh`: what it puts for Claude, Codex and Grok, what `--check` says of each part and
what `--uninstall` takes away. Every test runs the script, under a temporary `HOME` and with
stand-ins for `uv` and `systemctl`, but for the three that ask the machine a question no
argument of the script reaches."""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

import daemons
import jleak
from jinstall.__main__ import install as run_install
from jinstall.kinds import Units, rewrite
from jinstall.machine import Machine, Moved, Ran

REPO = Path(__file__).parent.parent

INSTALL = REPO / "install.sh"
SYSTEMCTL = REPO / ".cursor" / "skills" / "verify-jstack" / "scripts" / "fake-systemctl"
HARNESS = Path("harness") / "jstack" / "claude-code"
COPY = REPO / HARNESS
SKILLS = sorted(path.parent.name for path in (COPY / "skills").glob("*/SKILL.md"))
ROOTS = (".claude/skills", ".agents/skills", ".codex/skills")
NAMES = list(tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"])
UNITS = [
    "jbus-ci.service",
    "jbus-ci.timer",
    "jbus-failed.service",
    "jbus-relay.service",
    "jbus-snapshot-failed.service",
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
    "jbus-ci.timer",
    "jbus-snapshot.timer",
    "jbus-stale.timer",
    "jbus.timer",
    "jgauge-limits.timer",
    "jgauge-sample.timer",
    "jroles-mirror.timer",
]
SCRUBBED = ("XDG_", "UV_", "JBUS_", "VERIFY_JSTACK_", "LIMITS")


def command(script, checkout=REPO):
    return f"sh '{checkout / HARNESS / 'hooks' / script}' 2>/dev/null || true"


def group(script, matcher="startup", checkout=REPO, refuses=False):
    run = f"sh '{checkout / HARNESS / 'hooks' / script}'" if refuses else command(script, checkout)
    hooks = [{"type": "command", "command": run, "timeout": 30 if refuses else 5}]
    return ({"matcher": matcher} if matcher else {}) | {"hooks": hooks}


START = group("home-start.sh")
TIPS = group("skill-tips.sh", matcher=None)
GAUGE = group("home-gauge.sh", matcher=None)
OUTBOUND = group("outbound-command.sh", matcher="Bash", refuses=True)
STATUS = {"type": "command", "command": f"sh '{COPY / 'hooks' / 'limits.sh'}'"}
CURRENT = "ok hard harness/ is current"
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
""".replace("NAMES", " ".join(NAMES))


class User:
    """One temporary HOME, and beside it what the stand-ins keep: uv's tools and both logs."""

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
        self.units = self.home / ".config" / "systemd" / "user"
        self.patterns = self.home / ".config" / "jstack" / "outbound.toml"
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
        """A PATH of one new directory that holds `dirname` and the stand-ins named."""
        narrow = self.stub.parent / "narrow"
        narrow.mkdir(exist_ok=True)
        (narrow / "dirname").symlink_to(shutil.which("dirname"))
        for name in programs:
            (narrow / name).symlink_to(self.stub / name)
        return str(narrow)

    def links(self):
        return [self.home / root / name for root in ROOTS for name in SKILLS]

    def parts(self):
        return [
            *(f"hard {link}" for link in self.links()),
            f"hard hook {self.settings} SessionStart",
            f"hard hook {self.settings} UserPromptSubmit",
            f"hard hook {self.settings} PostToolUse",
            f"hard hook {self.settings} PreToolUse",
            f"hard hook {self.codex} SessionStart",
            f"optional patterns {self.patterns}",
            f"hard hook {self.settings} PreToolUse",
            "hard commands jstack",
            f"optional statusline {self.settings}",
        ]

    def every(self, state, *more):
        """Each part's line in `state`, under the copy's, which is current in this checkout."""
        return [CURRENT, *(f"{state} {part}" for part in (*self.parts(), *more))]

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

    def tool(self, name, source, names):
        """A tool as uv leaves one: its PEP 610 record, and its commands in the bin directory."""
        site = self.tools / name / "lib" / "python3" / "site-packages" / f"{name}-0.1.0.dist-info"
        self.write(
            site / "direct_url.json", {"url": f"file://{source}", "dir_info": {"editable": True}}
        )
        self.write(self.tools / name / "names", " ".join(names))
        for each in names:
            self.write(self.bin / each, "#!/bin/sh\n")

    def with_jbus(self):
        self.write(self.jbus / "config.toml", "")
        return f"optional units {self.units}"


@pytest.fixture
def user(tmp_path):
    return User(tmp_path)


def line_for(said, part):
    return [line for line in said if f" {part}" in line]


def test_it_puts_every_part_and_says_ok_for_each(user):
    assert len(SKILLS) > 9
    assert user.run() == (0, user.every("ok"))
    for link in user.links():
        assert os.readlink(link) == str(COPY / "skills" / link.name)
    assert json.loads(user.settings.read_text()) == {
        "hooks": {
            "SessionStart": [START],
            "UserPromptSubmit": [TIPS],
            "PostToolUse": [GAUGE],
            "PreToolUse": [GAUGE, OUTBOUND],
        },
        "statusLine": STATUS,
    }
    assert json.loads(user.codex.read_text()) == {"hooks": {"SessionStart": [START]}}
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
        COPY / "skills" / "pr-review"
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
        "hooks": {"SessionStart": [other, START], "Stop": stop}
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
        "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [beside]}, START]}
    }


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
    assert json.loads(user.settings.read_text()) == written | {
        "hooks": {
            "UserPromptSubmit": [TIPS],
            "SessionStart": [START],
            "PostToolUse": [GAUGE],
            "PreToolUse": [GAUGE, OUTBOUND],
        }
    }
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
    assert json.loads(user.codex.read_text()) == {"hooks": {"SessionStart": [START]}}


def test_a_settings_file_that_is_a_link_is_written_where_it_points(user, tmp_path):
    kept = tmp_path / "dotfiles" / "settings.json"
    stop = [{"hooks": [{"type": "command", "command": "echo bye"}]}]
    user.write(kept, {"hooks": {"Stop": stop}})
    user.settings.parent.mkdir(parents=True)
    user.settings.symlink_to(kept)
    assert user.run() == (0, user.every("ok"))
    assert os.readlink(user.settings) == str(kept)
    assert json.loads(kept.read_text()) == {
        "hooks": {
            "Stop": stop,
            "SessionStart": [START],
            "UserPromptSubmit": [TIPS],
            "PostToolUse": [GAUGE],
            "PreToolUse": [GAUGE, OUTBOUND],
        },
        "statusLine": STATUS,
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
    assert json.loads(user.settings.read_text())["statusLine"] == STATUS


def test_a_jgauge_tool_from_this_checkout_is_old_and_is_removed(user):
    user.tool("jgauge", REPO, NAMES[:4])
    code, said = user.run("--check")
    assert line_for(said, "commands") == [
        "old hard commands jstack -> tool jgauge, from before the rename, "
        f"lacks {' '.join(NAMES[4:])}"
    ]
    assert user.run() == (0, user.every("ok"))
    assert user.said(user.uv_log) == [
        "tool uninstall jgauge",
        f"tool install --editable {REPO} --reinstall",
    ]
    assert not (user.tools / "jgauge").exists()


def test_a_tool_that_lacks_a_command_is_old_and_is_installed_again(user):
    user.run()
    (user.bin / NAMES[-1]).unlink()
    (user.tools / "jstack" / "names").write_text(" ".join(NAMES[:-1]))
    assert line_for(user.run("--check")[1], "commands") == [
        f"old hard commands jstack -> lacks {NAMES[-1]}"
    ]
    assert user.run() == (0, user.every("ok"))
    assert (user.bin / NAMES[-1]).exists()


def test_a_program_that_is_not_uvs_is_never_replaced(user):
    theirs = user.bin / NAMES[0]
    user.write(theirs, "theirs\n")
    code, said = user.run()
    assert (code, line_for(said, "commands")) == (1, ["missing hard commands jstack"])
    assert theirs.read_text() == "theirs\n"
    assert user.said(user.uv_log) == [f"tool install --editable {REPO} --reinstall"]


def test_a_tool_from_another_checkout_is_old_and_uninstall_keeps_it(user):
    user.tool("jstack", "/elsewhere/jstack", NAMES)
    assert line_for(user.run("--check")[1], "commands") == [
        "old hard commands jstack -> an install of /elsewhere/jstack"
    ]
    code, said = user.run("--uninstall")
    assert (code, said) == (0, ["kept commands jstack -> an install of /elsewhere/jstack"])
    assert (user.tools / "jstack").is_dir()


def test_a_command_that_another_program_shadows_is_old(user):
    user.run()
    shadow = user.script("jbus", "#!/bin/sh\n")
    code, said = user.run()
    assert code == 1
    assert line_for(said, "commands") == [
        f"old hard commands jstack -> jbus is shadowed by {shadow}"
    ]
    assert len(user.said(user.uv_log)) == 1


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


def test_the_units_are_linked_and_the_timer_enabled_once_jbus_has_a_config(user):
    units = user.with_jbus()
    assert user.run("--check") == (1, user.every("missing", units))
    assert user.run() == (0, user.every("ok", units))
    for name in UNITS:
        assert os.readlink(user.units / name) == str(REPO / "templates" / name)
    for timer in TIMERS:
        wanted = user.units / "timers.target.wants" / timer
        assert os.readlink(wanted) == str(REPO / "templates" / timer)
    ran = [line for line in user.said(user.systemctl_log) if "show" not in line]
    enabled = [f"--user enable --now {timer}" for timer in TIMERS]
    assert ran[: 1 + len(TIMERS)] == ["--user daemon-reload", *enabled]
    before = user.snapshot()
    assert user.run() == (0, user.every("ok", units))
    assert user.snapshot() == before


def test_units_stay_due_after_the_jbus_config_is_gone_and_say_what_they_lack(user):
    units = user.with_jbus()
    user.run()
    (user.jbus / "config.toml").unlink()
    (user.units / "jbus-failed.service").unlink()
    code, said = user.run("--check")
    assert (code, line_for(said, "units")) == (1, [f"old {units} -> lacks jbus-failed.service"])
    assert user.run() == (0, user.every("ok", units))


def test_a_timer_that_is_not_enabled_is_old_and_a_run_enables_it(user):
    units = user.with_jbus()
    user.run()
    (user.units / "timers.target.wants" / "jbus.timer").unlink()
    code, said = user.run("--check")
    assert (code, line_for(said, "units")) == (1, [f"old {units} -> jbus.timer is not enabled"])
    assert user.run() == (0, user.every("ok", units))


def test_a_unit_copied_by_hand_becomes_a_link_and_one_that_differs_is_left_alone(user):
    units = user.with_jbus()
    for name in UNITS:
        user.write(user.units / name, (REPO / "templates" / name).read_text())
    copies = f"old {units} -> {' '.join(UNITS)}: a copy of its template, not a link"
    assert line_for(user.run("--check")[1], "units") == [copies]
    assert user.run() == (0, user.every("ok", units))
    assert all((user.units / name).is_symlink() for name in UNITS)

    edited = user.units / "jbus.service"
    edited.unlink()
    edited.write_text("[Unit]\nDescription=mine\n")
    for args in ((), ("--check",), ("--uninstall",)):
        code, said = user.run(*args)
        if args != ("--uninstall",):
            differs = f"old {units} -> jbus.service -> not a link, differs"
            assert (code, line_for(said, "units")) == (1, [differs])
        assert edited.read_text() == "[Unit]\nDescription=mine\n"


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
            ".config/systemd",
            ".config/systemd/user",
            ".config/systemd/user/timers.target.wants",
            ".local",
            ".local/bin",
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
        *(f"removed unit {user.units / name}" for name in UNITS),
    }
    assert all(line.startswith("removed ") for line in said)
    assert user.listing() == []
    assert {f"--user disable --now {t}" for t in TIMERS} <= set(user.said(user.systemctl_log))
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


def test_with_a_manager_that_reads_another_home_only_the_links_are_made_and_removed(user):
    units = user.with_jbus()
    log = user.systemctl_log
    user.script("systemctl", f'#!/bin/sh\necho "$*" >> "{log}"\necho HOME=/another/home\n')
    assert user.run() == (0, user.every("ok", units))
    assert os.readlink(user.units / "jbus.timer") == str(REPO / "templates" / "jbus.timer")
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
    alias.symlink_to(REPO / "skills" / "crew")
    assert user.run("--check") == (0, user.every("ok"))
    user.run("--uninstall")
    assert os.readlink(alias) == str(REPO / "skills" / "crew")


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
    for checkout in (main, linked):
        (checkout / HARNESS / "skills" / "crew").mkdir(parents=True)
        (checkout / HARNESS / "skills" / "crew" / "SKILL.md").write_text("crew\n")
        (checkout / "pyproject.toml").write_text('[project]\nname = "jstack"\nscripts = {}\n')
    return main, linked


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
    assert checked.lines[1] == f"missing hard {home}/.claude/skills/crew"
    in_a_sandbox = run_install(machine(linked, home, account=tmp_path / "account"), write=True)
    assert in_a_sandbox.lines[1] == f"ok hard {home}/.claude/skills/crew"
    assert os.readlink(home / ".claude/skills/crew") == str(linked / HARNESS / "skills" / "crew")


def test_a_plain_install_from_the_main_checkout_under_the_accounts_own_home_runs(tmp_path):
    main, linked = worktree(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    done = run_install(machine(main, home, account=home), write=True)

    assert done.lines[1] == f"ok hard {home}/.claude/skills/crew"


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
    _, written = json.loads(user.settings.read_text())["hooks"]["PreToolUse"]
    assert written == OUTBOUND
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


def test_the_gauge_hook_the_install_writes_denies_a_tool_call_past_the_ceiling(user, tmp_path):
    user.run()
    written, _ = json.loads(user.settings.read_text())["hooks"]["PreToolUse"]
    assert written == GAUGE
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
        f" Only the handoff runs now: read {COPY.resolve() / 'skills' / 'handoff' / 'SKILL.md'}"
        " and do its steps.",
    }


def test_a_machine_with_the_gauge_only_after_a_tool_call_gets_it_before_one_too(user):
    user.run()
    written = json.loads(user.settings.read_text())
    written["hooks"]["PreToolUse"] = [OUTBOUND]
    user.settings.write_text(json.dumps(written))
    part = f"hook {user.settings} PreToolUse"
    code, said = user.run("--check")
    assert (code, line_for(said, part)) == (1, [f"missing hard {part}", f"ok hard {part}"])
    assert user.run() == (0, user.every("ok"))
    assert json.loads(user.settings.read_text())["hooks"]["PreToolUse"] == [OUTBOUND, GAUGE]
    assert user.run("--check") == (0, user.every("ok"))


def checkout_under(user):
    """A main checkout inside the user's HOME, with this one's installer, hooks and source."""
    checkout = user.home / "repos" / "jstack"
    checkout.mkdir(parents=True)
    for name in ("install.sh", "pyproject.toml"):
        shutil.copy(REPO / name, checkout / name)
    for name in ("src", "hooks", "templates", "harness"):
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
    assert os.readlink(link) == str(checkout / "hooks" / "pre-push.sh")
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
    assert line_for(said, "pre-push") == [f"old {part} -> not a link"]
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
    assert line_for(said, "pre-push") == [
        f"old hard hook {main / '.git' / 'hooks' / 'pre-push'} pre-push"
        " -> core.hooksPath is set, so git runs no hook of .git/hooks"
    ]
    assert not (main / ".git" / "hooks" / "pre-push").is_symlink()


def test_a_skill_edited_after_the_copy_was_made_makes_the_harness_line_old(user, tmp_path):
    checkout = tmp_path / "checkout"
    listed = subprocess.run(
        ["git", "-C", REPO, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    )
    for name in filter(None, listed.stdout.decode().split("\0")):
        if (REPO / name).exists():
            (checkout / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, checkout / name, follow_symlinks=False)
    skill = checkout / "skills" / "bro" / "SKILL.md"
    skill.write_text(skill.read_text() + "\nOne more line.\n")
    stale = f"stale: {HARNESS}/skills/bro/SKILL.md"

    def first(*args):
        done = user.start(*args, checkout=checkout)
        out, err = done.communicate()
        return done.returncode, out.splitlines()[0], err

    assert first("--check")[:2] == (1, f"old hard harness/ is current -> {stale}")
    code, line, err = first()
    assert (code, line) == (1, f"old hard harness/ is current -> {stale}")
    generate = checkout / "scripts" / "generate-jstack-trees.py"
    assert f"run python3 {generate} and commit the result" in err
    subprocess.run([sys.executable, "-I", generate], check=True, capture_output=True)
    assert first("--check")[1] == CURRENT


# A release: the wheel `uv build` makes from this checkout, installed by uv into a tool
# directory of its own under the test's temporary directory, so no checkout of jstack is on
# any parent path of the tool, its copy or the HOME it runs under.

PACKAGES = ("jbriefs", "jbus", "jdrift", "jgauge", "jinstall", "jleak", "jmerge", "jpack")
PACKAGES += ("jroles", "jsettings")


def no_checkout_above(path):
    return not any((up / "pyproject.toml").is_file() for up in path.parents)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    built = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out), str(REPO)],
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr
    (found,) = out.glob("*.whl")
    return found


class Release:
    """The wheel as `uv tool install <wheel>` leaves it, and a HOME to run its commands under."""

    def __init__(self, root, wheel):
        self.root, self.tools, self.bin = root, root / "tools", root / "bin"
        env = {k: v for k, v in os.environ.items() if not k.startswith(SCRUBBED)}
        self.uv_env = env | {"UV_TOOL_DIR": str(self.tools), "UV_TOOL_BIN_DIR": str(self.bin)}
        done = subprocess.run(
            ["uv", "tool", "install", str(wheel)], env=self.uv_env, capture_output=True, text=True
        )
        assert done.returncode == 0, done.stderr
        self.copy = self.tools / "jstack" / "share" / "jstack" / "claude-code"
        assert no_checkout_above(self.copy)

    def run(self, home, *args, **env):
        home.mkdir(exist_ok=True)
        path = f"{self.bin}:{os.environ['PATH']}"
        return subprocess.run(
            [str(self.bin / args[0]), *args[1:]],
            env=self.uv_env | {"HOME": str(home), "PATH": path} | env,
            cwd=home,
            capture_output=True,
            text=True,
        )


@pytest.fixture(scope="module")
def released(wheel, tmp_path_factory):
    return Release(tmp_path_factory.mktemp("release"), wheel)


def test_the_wheel_carries_every_package_the_copy_whole_and_the_jinstall_command(wheel):
    with zipfile.ZipFile(wheel) as built:
        names = set(built.namelist())
        (points,) = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        scripts = built.read(points).decode()
    for package in PACKAGES:
        assert f"{package}/__init__.py" in names, package
    data = next(name.split("/")[0] for name in names if ".data/" in name)
    shared = f"{data}/data/share/jstack/claude-code"
    copied = {
        f"{shared}/{path.relative_to(COPY).as_posix()}"
        for path in COPY.rglob("*")
        if path.is_file()
    }
    assert copied <= names, sorted(copied - names)[:5]
    for part in (
        "skills/crew/SKILL.md",
        "playbooks/feature.md",
        "principles/principle-prove-it-works.md",
        "templates/jbus.timer",
        "templates/result.md",
        "hooks/outbound-command.sh",
        "plugin.json",
        "skills.json",
    ):
        assert f"{shared}/{part}" in names, part
    assert "jinstall = jinstall.cli:main" in scripts.splitlines()


def test_with_no_checkout_above_it_a_release_reads_its_playbooks_and_skills_from_the_copy(
    released, tmp_path
):
    home = tmp_path / "home"
    asked = tmp_path / "req.md"
    asked.write_text("Playbook: investigation\nSkills: tdd\n")
    opened = released.run(home, "jbus", "playbook", "scout", str(asked))
    assert opened.returncode == 0, opened.stderr
    assert opened.stdout.splitlines()[0] == str(released.copy / "playbooks" / "investigation.md")
    loaded = released.run(home, "jbriefs", "--skills", str(asked))
    assert loaded.returncode == 0, loaded.stderr
    assert loaded.stdout.splitlines()[0].startswith("loaded: tdd")
    assert "==> skills/tdd/SKILL.md <==" in loaded.stdout


def release_parts(home, copy):
    settings = home / ".claude" / "settings.json"
    names = sorted(path.parent.name for path in (copy / "skills").glob("*/SKILL.md"))
    return [
        *(f"hard {home / root / name}" for root in ROOTS for name in names),
        f"hard hook {settings} SessionStart",
        f"hard hook {settings} UserPromptSubmit",
        f"hard hook {settings} PostToolUse",
        f"hard hook {settings} PreToolUse",
        f"hard hook {home / '.codex' / 'hooks.json'} SessionStart",
        f"optional patterns {home / '.config' / 'jstack' / 'outbound.toml'}",
        f"hard hook {settings} PreToolUse",
        "hard commands jstack",
        f"optional statusline {settings}",
    ]


def stand_ins(tmp_path):
    """A directory with the fake systemctl, for a release's commands to find first on PATH."""
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "systemctl").symlink_to(SYSTEMCTL)
    return {"PATH": f"{stub}:{os.environ['PATH']}", "FAKE_SYSTEMCTL_LOG": str(tmp_path / "log")}


def test_a_release_links_every_skill_hook_and_status_line_into_its_copy_and_checks_ok(
    released, tmp_path
):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    put = released.run(home, "jinstall", **env)
    assert (put.returncode, put.stderr) == (0, "")
    assert put.stdout.splitlines() == [f"ok {part}" for part in release_parts(home, released.copy)]
    checked = released.run(home, "jinstall", "--check", **env)
    assert (checked.returncode, checked.stdout) == (0, put.stdout)
    links = [path for root in ROOTS for path in (home / root).iterdir()]
    assert len(links) == 3 * len(list((released.copy / "skills").iterdir()))
    for link in links:
        assert os.readlink(link) == str(released.copy / "skills" / link.name)
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"]
        for groups in settings["hooks"].values()
        for group in groups
        for hook in group["hooks"]
    ]
    assert all(f"sh '{released.copy}/hooks/" in command for command in commands), commands
    assert settings["statusLine"]["command"] == f"sh '{released.copy / 'hooks' / 'limits.sh'}'"
    assert not line_for(put.stdout.splitlines(), "pre-push")


def test_a_release_with_jbus_set_up_links_its_units_into_the_copy(released, tmp_path):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    (home / ".config" / "jbus").mkdir(parents=True)
    (home / ".config" / "jbus" / "config.toml").write_text("")
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "jbus").symlink_to(released.bin / "jbus")
    put = released.run(home, "jinstall", **env)
    assert put.stdout.splitlines()[-1] == f"ok optional units {home / '.config/systemd/user'}"
    unit = home / ".config" / "systemd" / "user" / "jbus.timer"
    assert os.readlink(unit) == str(released.copy / "templates" / "jbus.timer")


def test_a_release_whose_version_is_not_its_copys_is_told_so_and_not_put_over(released, tmp_path):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    plugin = json.loads((released.copy / "plugin.json").read_text())
    metadata = next(released.tools.glob("jstack/lib/python*/site-packages/jstack-*.dist-info"))
    said = (metadata / "METADATA").read_text()
    (metadata / "METADATA").write_text(said.replace(f"Version: {plugin['version']}", "Version: 9"))
    try:
        checked = released.run(home, "jinstall", "--check", **env)
    finally:
        (metadata / "METADATA").write_text(said)
    assert checked.returncode == 1
    assert line_for(checked.stdout.splitlines(), "commands") == [
        f"old hard commands jstack -> tool jstack is 9, and its copy is {plugin['version']}"
    ]


def test_uninstall_from_a_release_removes_what_it_put_and_keeps_the_tool_it_runs_from(
    released, tmp_path
):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    assert released.run(home, "jinstall", **env).returncode == 0
    gone = released.run(home, "jinstall", "--uninstall", **env)
    assert gone.returncode == 0, gone.stderr
    assert "kept commands jstack -> the release this jinstall runs from" in gone.stdout
    assert not any((home / root).exists() for root in ROOTS)
    assert (released.bin / "jinstall").exists()


def test_a_releases_outbound_hook_checks_a_push_on_the_tools_own_python_with_no_python_on_path(
    released, tmp_path
):
    home = tmp_path / "home"
    env = stand_ins(tmp_path)
    env["PATH"] = f"{released.bin}:{env['PATH']}"
    assert released.run(home, "jinstall", **env).returncode == 0
    narrow = tmp_path / "narrow"
    narrow.mkdir()
    for program in ("dirname", "readlink", "cat"):
        (narrow / program).symlink_to(shutil.which(program))
    hook = released.copy / "hooks" / "outbound-command.sh"

    def told(command):
        said = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return subprocess.run(
            ["/bin/sh", str(hook)],
            input=said,
            env={"HOME": str(home), "PATH": str(narrow)},
            capture_output=True,
            text=True,
        )

    clean = told("git push origin a-branch")
    assert (clean.returncode, clean.stderr) == (0, "")
    leaked = told(f"gh pr create --body 'see {home}/notes'")
    assert leaked.returncode == 2
    assert "home-path" in leaked.stderr
