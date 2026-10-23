"""The Units need on macOS: launchd agents made from the unit templates, written to
`~/Library/LaunchAgents`, loaded with `launchctl bootstrap gui/<uid>` and booted out on
uninstall.

Each test runs jinstall's verbs on a machine whose platform is darwin, under a temporary
`HOME`, with verify-jstack's `fake-launchctl` on PATH in place of launchd. That stand-in loads
and boots out as launchd does and runs no agent."""

import os
import plistlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from jbus.launchd import STARTED, TIMED_OUT, label
from jinstall import launchd
from jinstall.__main__ import doctor, install, setup, uninstall
from jinstall.kinds import unit_templates
from jinstall.machine import Machine, Ran
from test_install import TIMERS, User, line_for
from testing.paths import REPO

LAUNCHCTL = REPO / "features" / "verify-jstack" / "project-skill" / "scripts" / "fake-launchctl"
GUI = f"gui/{os.getuid()}"


class Mac(User):
    """A HOME on macOS: the stand-ins of `User`, and `launchctl` in place of `systemctl`."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        (self.stub / "launchctl").symlink_to(LAUNCHCTL)
        self.launchctl_log = tmp_path / "launchctl.log"
        self.loaded = tmp_path / "launchd"
        self.agents = self.home / "Library" / "LaunchAgents"
        self.line = f"units {self.agents}"

    def machine(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "UV_", "JBUS_"))}
        env |= {
            "HOME": str(self.home),
            "PATH": f"{self.stub}:{self.bin}:{os.environ['PATH']}",
            "UV_TOOL_DIR": str(self.tools),
            "UV_LOG": str(self.uv_log),
            "JBUS_CONFIG_DIR": str(self.jbus),
            "FAKE_LAUNCHCTL_LOG": str(self.launchctl_log),
            "FAKE_LAUNCHCTL_LOADED": str(self.loaded),
        }

        def run(args):
            try:
                done = subprocess.run(list(args), env=env, capture_output=True, text=True)
            except OSError:
                return Ran(None, "")
            return Ran(done.returncode, done.stdout + done.stderr)

        account = self.home.parent / "account"
        return Machine(REPO, self.home, env, run, account, platform="darwin")

    def said_by(self, verb, *args):
        """The units line that `verb` prints on this Mac."""
        report = verb(self.machine(), *args)
        return line_for(report.lines, self.line)

    def plist(self, name):
        return self.agents / f"{label(name)}.plist"

    def calls(self, word):
        return [line for line in self.said(self.launchctl_log) if line.startswith(word)]

    def bootstraps(self):
        return sorted(line.split()[-1] for line in self.calls("bootstrap"))


@pytest.fixture
def mac(tmp_path):
    return Mac(tmp_path)


def wanted(mac, names):
    return sorted(str(mac.plist(name)) for name in names)


def test_setup_writes_and_bootstraps_each_agent_and_a_second_run_writes_nothing(mac):
    mac.with_jbus()

    assert line_for(setup(mac.machine()).lines, mac.line) == [f"done {mac.line}"]
    assert sorted(path.name for path in mac.agents.iterdir()) == sorted(
        f"{label(name)}.plist" for name in TIMERS
    )
    assert mac.bootstraps() == wanted(mac, TIMERS)
    assert all(line.split()[1] == GUI for line in mac.calls("bootstrap"))
    for name in TIMERS:
        said = plistlib.loads(mac.plist(name).read_bytes())
        assert said["Label"] == label(name)
        assert launchd.made_from(mac.plist(name).read_text()) == str(REPO)

    before, calls = mac.snapshot(), len(mac.said(mac.launchctl_log))
    assert line_for(setup(mac.machine()).lines, mac.line) == [f"already {mac.line}"]
    assert mac.snapshot() == before
    assert [line.split()[0] for line in mac.said(mac.launchctl_log)[calls:]] == ["print"] * len(
        TIMERS
    )


def test_check_and_the_doctor_read_each_agent_from_launchctl_print(mac):
    mac.with_jbus()
    assert mac.said_by(install, False) == [f"missing optional {mac.line}"]
    setup(mac.machine())
    assert mac.said_by(install, False) == [f"ok optional {mac.line}"]
    assert mac.said_by(doctor) == [f"ok optional {mac.line}"]

    subprocess.run(
        [LAUNCHCTL, "bootout", f"{GUI}/jstack.jgauge-sample"],
        env={**os.environ, "FAKE_LAUNCHCTL_LOG": str(mac.launchctl_log)},
        check=True,
    )
    stopped = [f"old optional {mac.line} -> jstack.jgauge-sample is not loaded"]
    assert mac.said_by(install, False) == stopped
    assert mac.said_by(doctor) == stopped
    assert mac.said_by(install, True) == [f"ok optional {mac.line}"]
    assert mac.bootstraps().count(str(mac.plist("jgauge-sample.timer"))) == 2


def test_a_plist_the_templates_no_longer_make_is_rewritten_and_loaded_again(mac):
    mac.with_jbus()
    setup(mac.machine())
    plist = mac.plist("jbus.timer")
    plist.write_text(plist.read_text().replace("<integer>60</integer>", "<integer>9</integer>"))

    old = f"old optional {mac.line} -> {plist.name} is not as its templates make it"
    assert mac.said_by(install, False) == [old]
    assert mac.said_by(install, True) == [f"ok optional {mac.line}"]
    assert plistlib.loads(plist.read_bytes())["StartInterval"] == 60
    assert f"bootout {GUI}/jstack.jbus" in mac.said(mac.launchctl_log)


def test_uninstall_boots_out_each_agent_and_removes_its_plist(mac):
    mac.with_jbus()
    setup(mac.machine())

    done = uninstall(mac.machine())

    assert [line for line in done.lines if " agent " in line] == [
        f"removed agent {path}" for path in wanted(mac, TIMERS)
    ]
    assert sorted(line.split()[-1] for line in mac.calls("bootout")) == sorted(
        f"{GUI}/{label(name)}" for name in TIMERS
    )
    assert not mac.agents.exists() or not list(mac.agents.iterdir())
    assert not list(mac.loaded.iterdir())
    assert not (mac.home / "Library" / "Logs" / "jstack").exists()
    assert uninstall(mac.machine()).lines == ()


def test_the_owners_mac_runs_the_ci_relay_and_snapshot_agents_and_drops_one_nothing_asks_for(
    mac,
):
    mac.as_owner()
    setup(mac.machine())
    opted = ["jbus-ci.timer", "jbus-relay.service", "jbus-snapshot.timer"]
    assert mac.bootstraps() == wanted(mac, [*TIMERS, *opted])
    relay = plistlib.loads(mac.plist("jbus-relay.service").read_bytes())
    assert (relay["RunAtLoad"], relay["KeepAlive"]) == (True, {"SuccessfulExit": False})

    mac.relay_env.unlink()
    off = f"old optional {mac.line} -> jstack.jbus-relay.plist is there, and nothing asks for it"
    assert mac.said_by(install, False) == [off]
    assert mac.said_by(install, True) == [f"ok optional {mac.line}"]
    assert not mac.plist("jbus-relay.service").exists()
    assert f"bootout {GUI}/jstack.jbus-relay" in mac.said(mac.launchctl_log)


def test_a_plist_no_install_made_is_left_as_it_is(mac):
    mac.with_jbus()
    mine = mac.plist("jbus.timer")
    mac.write(mine, "<plist><dict/></plist>\n")

    for verb in (setup, uninstall):
        verb(mac.machine())
        assert mine.read_text() == "<plist><dict/></plist>\n"
    differs = f"old optional {mac.line} -> {mine.name} -> not jstack's, differs"
    assert mac.said_by(install, False) == [differs]


def test_the_view_gets_no_agent_as_systemd_enables_no_view(mac):
    mac.with_jbus()
    setup(mac.machine())
    assert not mac.plist("jbus-view.service").exists()


def test_a_sandbox_never_runs_the_systems_launchctl(tmp_path, monkeypatch):
    asked = []

    def run(args):
        asked.append(list(args))
        return Ran(0, "")

    sandbox = Machine(REPO, tmp_path / "home", {}, run, tmp_path / "account", platform="darwin")
    monkeypatch.setattr(Machine, "which", lambda self, name: Path("/bin/launchctl"))
    assert sandbox.launchctl("bootstrap", GUI, "x.plist") is None
    assert replace(sandbox, home=sandbox.account).launchctl("print", GUI) is not None
    assert asked == [["launchctl", "print", GUI]]


SCHEDULES = {
    "jbus.timer": {"StartInterval": 60},
    "jbus-stale.timer": {"StartInterval": 900},
    "jgauge-limits.timer": {"StartInterval": 120},
    "jgauge-sample.timer": {"StartInterval": 15},
    "jroles-mirror.timer": {"StartInterval": 300},
    "jbus-ci.timer": {"StartCalendarInterval": [{"Weekday": 1, "Hour": 9, "Minute": 0}]},
    "jbus-snapshot.timer": {
        "StartCalendarInterval": [{"Hour": 8, "Minute": 30}, {"Hour": 17, "Minute": 30}]
    },
    "jbus-relay.service": {"RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False}},
    "jbus-view.service": {"RunAtLoad": True, "KeepAlive": True},
}
"""Each agent's schedule, read from its template by hand."""


def test_every_template_has_its_schedule_carried_over(tmp_path):
    made = launchd.agents(unit_templates(REPO), tmp_path)
    assert sorted(made) == sorted(SCHEDULES)
    for name, agent in made.items():
        schedule = {k: v for k, v in agent.schedule.items() if k != "ThrottleInterval"}
        assert schedule == SCHEDULES[name], name
        path = f"{tmp_path}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        assert agent.environment == {"PATH": path}


def agent_runs(tmp_path, name, programs):
    """Run the agent of unit `name` as launchd would, with `programs` as the commands in
    ~/.local/bin, each a line of sh. Return its exit code and what each command was asked."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    calls = tmp_path / "calls"
    for program, line in programs.items():
        path = home / ".local" / "bin" / program
        path.write_text(f'#!/bin/sh\necho "{program} $*" >> {calls}\n{line}\n')
        path.chmod(0o755)
    agent = launchd.agents(unit_templates(REPO), home)[name]
    said = plistlib.loads(launchd.text(agent, home, REPO).encode())
    done = subprocess.run(
        said["ProgramArguments"],
        env={**said["EnvironmentVariables"], "HOME": str(home)},
        capture_output=True,
        text=True,
    )
    return done.returncode, done.stdout, calls.read_text().splitlines() if calls.exists() else []


def test_a_pass_that_fails_tells_the_chef_as_its_on_failure_unit_does(tmp_path):
    code, out, asked = agent_runs(tmp_path, "jbus.timer", {"jbus": '[ "$1" = alarm ] || exit 3'})
    assert (code, asked) == (3, ["jbus poll", "jbus alarm"])
    assert out.startswith(STARTED)


def test_a_pass_that_ends_well_tells_nobody(tmp_path):
    code, _, asked = agent_runs(tmp_path, "jbus.timer", {"jbus": "exit 0"})
    assert (code, asked) == (0, ["jbus poll"])


@pytest.mark.parametrize(("exit", "code"), [(2, 0), (1, 1)])
def test_the_relay_reads_its_env_file_and_an_exit_2_is_no_failure_to_restart(tmp_path, exit, code):
    env = tmp_path / "home" / ".config" / "jbus-relay" / "env"
    env.parent.mkdir(parents=True)
    env.write_text("RELAY_PORT=4999\n")
    line = f'echo "port $RELAY_PORT" >> {tmp_path}/calls; exit {exit}'
    assert agent_runs(tmp_path, "jbus-relay.service", {"jbus": line})[::2] == (
        code,
        ["jbus relay", "port 4999"],
    )


def test_a_command_past_its_start_timeout_is_stopped_and_says_so_as_systemd_does(tmp_path):
    units = tmp_path / "units"
    units.mkdir()
    (units / "slow.timer").write_text("[Timer]\nOnUnitActiveSec=1min\n")
    (units / "slow.service").write_text(
        "[Unit]\nOnFailure=told.service\n\n[Service]\nTimeoutStartSec=1s\nExecStart=/bin/sleep 30\n"
    )
    (units / "told.service").write_text("[Service]\nExecStart=/bin/sh -c 'echo told'\n")
    templates = {path.name: path for path in units.iterdir()}
    agent = launchd.agents(templates, tmp_path)["slow.timer"]
    done = subprocess.run(
        ["/bin/sh", "-c", agent.script], capture_output=True, text=True, timeout=10
    )
    assert done.returncode != 0
    assert done.stdout.splitlines()[1:] == [TIMED_OUT, "told"]
    assert "Failed with result 'timeout'" in TIMED_OUT


def test_a_unit_key_with_no_launchd_form_is_refused(tmp_path):
    unit = tmp_path / "x.service"
    unit.write_text("[Service]\nExecStart=/bin/true\nMemoryMax=1G\n")
    with pytest.raises(ValueError, match="MemoryMax"):
        launchd.read_unit(unit)
