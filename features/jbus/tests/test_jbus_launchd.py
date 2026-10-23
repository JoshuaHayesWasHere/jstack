"""On macOS, `jbus health` and the view's pulse and checks panels read launchd, where the install
runs jbus as agents (`jinstall.launchd`). Each test puts verify-jstack's `fake-launchctl` on PATH
in place of launchd, and loads the agents into it as the install does."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from jbus import health, launchd
from jbus.view.panels.checks import panel as checks
from jbus.view.panels.pulse import panel as pulse
from testing.paths import REPO

LAUNCHCTL = REPO / "features" / "verify-jstack" / "project-skill" / "scripts" / "fake-launchctl"
GUI = f"gui/{os.getuid()}"


class Launchd:
    """The fake launchd on PATH, and a way to load, start and boot out an agent in it."""

    def __init__(self, tmp_path, monkeypatch):
        stub = tmp_path / "stub"
        stub.mkdir()
        (stub / "launchctl").symlink_to(LAUNCHCTL)
        self.loaded = tmp_path / "launchd"
        monkeypatch.setenv("PATH", f"{stub}:{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_LAUNCHCTL_LOG", str(tmp_path / "launchctl.log"))
        monkeypatch.setenv("FAKE_LAUNCHCTL_LOADED", str(self.loaded))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        self.plists = tmp_path / "LaunchAgents"
        self.plists.mkdir()

    def load(self, label, pid=None):
        plist = self.plists / f"{label}.plist"
        plist.write_text("<plist/>\n")
        subprocess.run([LAUNCHCTL, "bootstrap", GUI, str(plist)], check=True)
        if pid is not None:
            (self.loaded / f"{label}.pid").write_text(f"{pid}\n")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    return Launchd(tmp_path, monkeypatch)


def write_log(unit, lines):
    path = launchd.log(Path.home(), launchd.label(unit))
    path.parent.mkdir(parents=True)
    path.write_text("".join(f"{line}\n" for line in lines))


def test_the_journal_of_jbus_is_its_agents_log_over_the_window(fake):
    now = int(time.time())
    write_log(
        "jbus.service",
        [
            f"{launchd.STARTED}{now - 7200}",
            launchd.TIMED_OUT,
            f"{launchd.STARTED}{now - 60}",
            "wait jstack: jmerge did not run (Command 'jmerge' timed out after 300 seconds)",
            f"{launchd.STARTED}{now - 30}",
            launchd.TIMED_OUT,
        ],
    )
    journal = health.Launchd().journal(health.UNIT, health.TIMEOUT_MINUTES)
    readings = {one.key: one for one in health.timeouts(tuple(journal), "")}
    assert (readings["timeout jbus"].over, readings["timeout jmerge"].over) == (True, True)
    assert "1 times" in readings["timeout jbus"].said


def test_a_journal_with_no_log_could_not_be_read(fake):
    assert health.Launchd().journal(health.UNIT, health.TIMEOUT_MINUTES) is None


@pytest.mark.parametrize(
    ("pid", "loaded", "state", "over"),
    [
        (None, False, "inactive", True),
        (None, True, "not running", True),
        (7, True, "active", False),
    ],
)
def test_the_relay_is_active_while_its_agent_runs(fake, pid, loaded, state, over):
    if loaded:
        fake.load(launchd.label(health.RELAY), pid)
    said = health.Launchd().show(health.RELAY, "ActiveState")
    assert said == state
    (reading, *_) = health.relays(health.Relay(said, None, Path("/nowhere")), health.clock())
    assert reading.over is over


def test_launchd_sets_no_start_timeout(fake):
    assert health.Launchd().show(health.UNIT, "TimeoutStartUSec") == ""


def test_the_pulse_reads_jbus_agent_as_its_timer_and_service(fake):
    assert pulse.launchd(None) == {
        pulse.TIMER: {"Id": "jstack.jbus", "ActiveState": "inactive"},
        pulse.SERVICE: {"Id": "jstack.jbus"},
    }
    fake.load("jstack.jbus")
    said = pulse.launchd(None)
    assert said[pulse.TIMER]["ActiveState"] == "active"
    assert said[pulse.SERVICE] | {"Id": ""} == {
        "Id": "",
        "ActiveState": "inactive",
        "Result": "success",
        "ExecMainStatus": "0",
    }
    (fake.loaded / "jstack.jbus").unlink()
    fake.load("jstack.jbus", pid=99)
    assert pulse.launchd(None)[pulse.SERVICE]["ActiveState"] == "activating"


def test_the_pulse_says_launchd_did_not_answer_when_it_cannot_run(fake, monkeypatch):
    monkeypatch.setenv("PATH", "/nowhere")
    assert pulse.launchd(None) is None


def test_the_runners_are_the_runner_agents_launchd_lists(fake):
    fake.load("actions.runner.me-jstack.mac-1", pid=41)
    fake.load("actions.runner.me-jstack.mac-2")
    fake.load("jstack.jbus", pid=3)
    assert checks.agents(None) == [
        {"unit": "actions.runner.me-jstack.mac-1", "active": "active", "sub": "running"},
        {"unit": "actions.runner.me-jstack.mac-2", "active": "inactive", "sub": "dead"},
    ]


def test_a_reader_keeps_the_runs_of_its_window_by_their_start_markers():
    lines = ["before", f"{launchd.STARTED}100", "old", f"{launchd.STARTED}200", "new", "newer"]
    assert launchd.recent(lines, 150) == ["new", "newer"]
    assert launchd.recent(lines, 50) == ["old", "new", "newer"]
