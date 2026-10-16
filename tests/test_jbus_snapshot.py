"""`jbus snapshot` commits the homes' state tree and pushes it, twice a day, and a snapshot that
did not finish alerts once.

Each test runs the real verb on a real git repo in the kitchen's home tree, and pushes to a
bare repo beside it. It uses the real gitleaks where the machine has one; on a machine with
none, a stand-in that finds nothing reads the changes and the secret test is skipped. The
units are read as systemd reads them, and by `systemd-analyze verify` where the machine has it.
"""

import configparser
import os
import random
import shlex
import shutil
import string
import subprocess
from pathlib import Path

import pytest

import jbus
from jbus import snapshot
from test_jbus_kitchen import NOW, REPO

UNITS = ("jbus-snapshot.service", "jbus-snapshot.timer", "jbus-snapshot-failed.service")
FAILED = (
    "alert: snapshot failed 1 times in a row since 11:00 ET: "
    "the last snapshot of the homes' state tree did not finish "
    "(see journalctl --user -u jbus-snapshot)"
)


def git(tree, *args):
    return subprocess.run(
        ["git", "-C", str(tree), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def tree(kitchen, monkeypatch):
    """The homes' state tree as a git repo with one commit, and a git that knows who commits.

    On a machine with no gitleaks, as GitHub's runner is, a gitleaks that finds nothing
    stands in for it, so a commit can be made: the secret test needs the real one.
    """
    for name in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{name}_NAME", "t")
        monkeypatch.setenv(f"GIT_{name}_EMAIL", "t@example.com")
    if not shutil.which("gitleaks"):
        stand_in = kitchen.root / "gitleaks-bin"
        stand_in.mkdir()
        (stand_in / "gitleaks").write_text("#!/bin/sh\nexit 0\n")
        (stand_in / "gitleaks").chmod(0o755)
        monkeypatch.setenv("PATH", f"{stand_in}{os.pathsep}{os.environ['PATH']}")
    root = kitchen.home.parent
    git(root, "init", "-q", "-b", "main")
    (root / "demo" / "notes.md").write_text("# notes\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "first")
    return root


def take(now=NOW):
    said = []
    code = snapshot.snapshot(jbus.load(), now, said.append)
    return code, said


def alarm():
    said = []
    assert snapshot.alarm(jbus.load(), NOW, said.append) == 0
    return said


def test_a_change_is_committed_as_a_snapshot_at_the_users_time(tree):
    (tree / "demo" / "tasks" / "a.md").write_text("# a: a task\n")
    assert take() == (0, ["snapshot: committed, no remote to push to"])
    assert git(tree, "log", "-1", "--format=%s") == "snapshot 2026-10-12 11:00 ET"
    assert git(tree, "status", "--porcelain") == ""
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/tasks/a.md"


def test_with_nothing_changed_nothing_is_committed(tree):
    before = git(tree, "rev-parse", "HEAD")
    assert take() == (0, ["snapshot: nothing changed, no remote to push to"])
    assert git(tree, "rev-parse", "HEAD") == before


def test_the_verb_takes_the_snapshot(kitchen, tree):
    (tree / "demo" / "notes.md").write_text("# notes\nmore\n")
    assert kitchen.main("snapshot") == (0, "snapshot: committed, no remote to push to\n")
    assert git(tree, "log", "-1", "--format=%s").startswith("snapshot ")


def test_a_commit_is_pushed_to_the_origin(tree, tmp_path):
    bare = tmp_path / "exeggutor.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(tree, "remote", "add", "origin", str(bare))
    (tree / "demo" / "notes.md").write_text("# notes\npushed\n")
    assert take() == (0, ["snapshot: committed, pushed"])
    assert git(bare, "rev-parse", "main") == git(tree, "rev-parse", "HEAD")


def test_a_push_that_fails_is_a_failed_snapshot(tree, tmp_path):
    git(tree, "remote", "add", "origin", str(tmp_path / "gone.git"))
    (tree / "demo" / "notes.md").write_text("# notes\nnowhere\n")
    code, (said,) = take()
    assert code == 1 and said.startswith("snapshot: git push failed: ")


def test_a_commit_whose_push_failed_is_pushed_by_the_next_run_with_nothing_changed(tree, tmp_path):
    git(tree, "remote", "add", "origin", str(tmp_path / "gone.git"))
    (tree / "demo" / "notes.md").write_text("# notes\nbehind\n")
    assert take()[0] == 1
    code, (said,) = take()
    assert code == 1 and said.startswith("snapshot: git push failed: ")
    bare = tmp_path / "gone.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    assert take() == (0, ["snapshot: nothing changed, pushed"])
    caught_up = git(tree, "rev-parse", "HEAD")
    assert git(bare, "rev-parse", "main") == caught_up
    assert take() == (0, ["snapshot: nothing changed, pushed"])
    assert git(bare, "rev-parse", "main") == git(tree, "rev-parse", "HEAD") == caught_up


@pytest.mark.skipif(not shutil.which("gitleaks"), reason="gitleaks is not installed")
def test_a_staged_secret_is_refused_and_nothing_is_committed_or_left_staged(tree):
    before = git(tree, "rev-parse", "HEAD")
    made_up = "".join(random.choices(string.ascii_letters + string.digits, k=36))
    (tree / "demo" / "leak.md").write_text(f'token = "ghp_{made_up}"\n')
    (tree / "demo" / "notes.md").write_text("# notes\nfine\n")
    assert take() == (
        1,
        ["snapshot: gitleaks found a secret in the changes, nothing committed"],
    )
    assert git(tree, "rev-parse", "HEAD") == before
    assert git(tree, "diff", "--cached", "--name-only") == ""


def test_with_no_gitleaks_nothing_is_committed(tree, monkeypatch):
    monkeypatch.setattr(snapshot.shutil, "which", lambda _: None)
    before = git(tree, "rev-parse", "HEAD")
    (tree / "demo" / "notes.md").write_text("# notes\nunread\n")
    assert take() == (1, ["snapshot: no gitleaks to read the changes, nothing committed"])
    assert git(tree, "rev-parse", "HEAD") == before


def test_the_first_failed_snapshot_alerts_once_and_the_next_that_goes_says_recovered(kitchen, tree):
    assert alarm() == ["snapshot failed", "alert sent: demo"]
    assert alarm() == ["snapshot failed"]
    posted = [event for post in kitchen.webhook.posts for event in post]
    assert [(e["event"], e["line"]) for e in posted] == [("alert", FAILED)]
    assert kitchen.log("notify") == [f"jbus | {FAILED}"]
    (tree / "demo" / "notes.md").write_text("# notes\nback\n")
    code, said = take()
    assert (code, said[0]) == (0, "snapshot: committed, no remote to push to")
    (recovered,) = [line for line in kitchen.lines("alert") if line.startswith("recovered")]
    assert recovered.startswith("recovered: snapshot after 2 failures since 11:00 ET")
    assert kitchen.log("notify")[1] == f"jbus | {recovered}"
    assert jbus.read_json(kitchen.state_dir / "streaks.json", {}) == {}


def read(name):
    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.optionxform = str
    unit.read(REPO / "templates" / name)
    return unit


def test_the_timer_runs_the_snapshot_at_half_past_eight_twice_a_day_and_catches_up():
    lines = (REPO / "templates" / "jbus-snapshot.timer").read_text().splitlines()
    calendar = [line.split("=", 1)[1] for line in lines if line.startswith("OnCalendar=")]
    assert calendar == ["*-*-* 08:30:00", "*-*-* 17:30:00"]
    timer = read("jbus-snapshot.timer")
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"
    service, failed = read("jbus-snapshot.service"), read("jbus-snapshot-failed.service")
    assert service["Unit"]["OnFailure"] == "jbus-snapshot-failed.service"
    for unit, words in ((service, ["snapshot"]), (failed, ["snapshot", "--alarm"])):
        command = shlex.split(unit["Service"]["ExecStart"])
        assert (Path(command[0]).name, command[1:]) == ("jbus", words)
        assert unit["Service"]["Type"] == "oneshot"
    for name in UNITS:
        options = [
            line
            for line in (REPO / "templates" / name).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith(("#", ";"))
        ]
        assert options and not [line for line in options if "_exec" in line]


def systemd_manager_answers(env=None):
    """A systemd manager is reachable: the system bus has its socket and the user manager says
    what state it is in. A CI job container runs neither."""
    if not (shutil.which("systemctl") and Path("/run/dbus/system_bus_socket").exists()):
        return False
    try:
        said = subprocess.run(
            ["systemctl", "--user", "is-system-running"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False
    return said.stdout.strip() not in ("", "offline", "unknown")


@pytest.mark.skipif(not shutil.which("systemctl"), reason="no systemctl")
def test_a_user_manager_out_of_reach_does_not_answer():
    away = {
        k: v
        for k, v in os.environ.items()
        if k not in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
    }
    assert not systemd_manager_answers(away)


@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="no systemd-analyze")
@pytest.mark.skipif(
    not systemd_manager_answers(),
    reason="host-only: needs a systemd manager, which a CI job container does not run",
)
def test_systemd_reads_the_units_with_no_complaint(tmp_path):
    jbus_bin = tmp_path / ".local" / "bin" / "jbus"
    jbus_bin.parent.mkdir(parents=True)
    jbus_bin.write_text("#!/bin/sh\n")
    jbus_bin.chmod(0o755)
    ran = subprocess.run(
        ["systemd-analyze", "--user", "verify", *(str(REPO / "templates" / u) for u in UNITS)],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    assert (ran.returncode, ran.stdout + ran.stderr) == (0, "")


def with_origin(tree, tmp_path):
    bare = tmp_path / "state-tree.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(tree, "remote", "add", "origin", str(bare))
    return bare


def test_an_edit_snapshotted_with_why_is_one_pushed_commit_that_says_why(kitchen, tree, tmp_path):
    bare = with_origin(tree, tmp_path)
    before = git(tree, "rev-parse", "HEAD")
    (tree / "demo" / "standing.md").write_text("1. 2026-10-15: a rule\n")
    assert kitchen.main("snapshot", "--why", "x") == (0, "snapshot: committed, pushed\n")
    assert git(tree, "rev-list", "--count", f"{before}..HEAD") == "1"
    subject = git(tree, "log", "-1", "--format=%s")
    assert subject.startswith("snapshot ") and subject.endswith(" ET: x")
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/standing.md"
    assert git(bare, "rev-parse", "main") == git(tree, "rev-parse", "HEAD")


def test_a_snapshot_with_no_why_says_only_the_time(tree):
    (tree / "demo" / "standing.md").write_text("1. a rule\n")
    snapshot.take(tree, NOW, jbus.load().user)
    assert git(tree, "log", "-1", "--format=%s") == "snapshot 2026-10-12 11:00 ET"
    (tree / "demo" / "standing.md").write_text("1. a rule\n2. another\n")
    snapshot.take(tree, NOW, jbus.load().user, why="demo standing rule 2 added")
    assert git(tree, "log", "-1", "--format=%s") == (
        "snapshot 2026-10-12 11:00 ET: demo standing rule 2 added"
    )


def test_why_is_not_taken_with_alarm(kitchen, tree):
    code, said = kitchen.main("snapshot", "--alarm", "--why", "x")
    assert code == 2 and "not allowed with argument" in said


def undo_section():
    """The shell lines of the section of docs/state.md that undoes an edit to standing.md."""
    text = (REPO / "docs" / "state.md").read_text()
    section = text.split("## Undo an edit to standing.md\n", 1)[1].split("\n## ", 1)[0]
    block = section.split("```sh\n", 1)[1].split("```", 1)[0]
    return [line for line in block.splitlines() if line and not line.startswith("#")]


def test_the_documented_undo_brings_back_the_text_before_a_bad_edit(kitchen, tree, tmp_path):
    with_origin(tree, tmp_path)
    standing = tree / "demo" / "standing.md"
    standing.write_text("1. keep this\n")
    assert kitchen.main("snapshot", "--why", "demo standing rule 1 added")[0] == 0
    standing.write_text("1. a bad merge\n")
    assert kitchen.main("snapshot", "--why", "demo standing rule 1 merged")[0] == 0
    bad = git(tree, "rev-parse", "HEAD")
    find, restore, again = undo_section()

    def run(line):
        line = line.replace("~/.local/state/home", shlex.quote(str(tree)))
        line = line.replace("<repo>", "demo").replace("<commit>", bad)
        return line

    found = subprocess.run(run(find), shell=True, capture_output=True, text=True, check=True)
    assert bad in found.stdout and "+1. a bad merge" in found.stdout
    subprocess.run(run(restore), shell=True, check=True)
    assert standing.read_text() == "1. keep this\n"
    words = shlex.split(run(again))
    assert words[:2] == ["jbus", "snapshot"]
    assert kitchen.main(*words[1:]) == (0, "snapshot: committed, pushed\n")
    assert git(tree, "log", "-1", "--format=%s").endswith(f": demo standing.md, {bad} undone")
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/standing.md"
