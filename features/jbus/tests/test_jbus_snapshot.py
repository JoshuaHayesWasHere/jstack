"""`jbus snapshot` commits the homes' state tree and pushes it, twice a day, and a snapshot that did
not finish raises its own alert once, for the owner of what failed.

Each test runs the real verb on a real git repo in the kitchen's home tree, and pushes to a bare
repo beside it. It uses the real gitleaks where the machine has one. On a machine with none, a
stand-in that finds nothing reads the changes, and pytest skips the secret test. The tests read the
units as systemd reads them, and with `systemd-analyze verify` where the machine has it.
"""

import configparser
import fcntl
import os
import random
import shlex
import shutil
import signal
import string
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import jbus
from jbus import alert, snapshot
from test_jbus_kitchen import NOW, REPO

UNITS = ("jbus-snapshot.service", "jbus-snapshot.timer")
HASH = "9e6221dd362b652bb22a8bf3570b9c240de3b68d662f05df5e18787994137b9a-"


def failed(cause, owner=""):
    """The alert line of a snapshot that failed for `owner`, a project, or the machine."""
    key = f"snapshot {owner}" if owner else "snapshot"
    return f"alert: {key} failed 1 times in a row since 11:00 ET: {snapshot.FAILED}: {cause}"


def git(tree, *args):
    return subprocess.run(
        ["git", "-C", str(tree), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def tree(kitchen, monkeypatch):
    """Make the homes' state tree a git repo with one commit, and give git a name to commit as.

    On a machine with no gitleaks, such as GitHub's runner, a gitleaks that finds nothing takes its
    place so that a commit can go through. The secret test needs the real one.
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


@pytest.fixture(name="tree")
def tree_fixture(kitchen, monkeypatch):
    return tree(kitchen, monkeypatch)


def take(now=NOW):
    said = []
    code = snapshot.snapshot(jbus.load(), now, said.append, warn=said.append)
    return code, said


def no_remote(tree, done="committed"):
    return f"snapshot: {done}, not pushed: {tree} has no origin, so the backup is off"


def test_a_change_is_committed_as_a_snapshot_at_the_users_time(tree, tmp_path):
    with_origin(tree, tmp_path)
    (tree / "demo" / "tasks" / "a.md").write_text("# a: a task\n")
    assert take() == (0, ["snapshot: committed, pushed"])
    assert git(tree, "log", "-1", "--format=%s") == "snapshot 2026-10-12 11:00 ET"
    assert git(tree, "status", "--porcelain") == ""
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/tasks/a.md"


def test_with_nothing_changed_nothing_is_committed(tree, tmp_path):
    with_origin(tree, tmp_path)
    before = git(tree, "rev-parse", "HEAD")
    assert take() == (0, ["snapshot: nothing changed, pushed"])
    assert git(tree, "rev-parse", "HEAD") == before


def test_with_no_remote_a_change_is_committed_here_and_the_snapshot_succeeds(tree):
    """With no origin the backup is off, and each snapshot is still a commit an edit can be
    undone to."""
    (tree / "demo" / "notes.md").write_text("# notes\nhere only\n")
    assert take() == (0, [no_remote(tree)])
    assert git(tree, "log", "-1", "--format=%s") == "snapshot 2026-10-12 11:00 ET"
    assert git(tree, "status", "--porcelain") == ""
    before = git(tree, "rev-parse", "HEAD")
    assert take() == (0, [no_remote(tree, "nothing changed")])
    assert git(tree, "rev-parse", "HEAD") == before


def test_with_no_remote_nothing_alerts_and_a_remote_set_later_gets_every_commit(
    kitchen, tree, tmp_path
):
    (tree / "demo" / "notes.md").write_text("# notes\nhere only\n")
    assert take() == (0, [no_remote(tree)])
    assert kitchen.wakes.listed == [] and kitchen.log("notify") == []
    bare = with_origin(tree, tmp_path)
    assert take() == (0, ["snapshot: nothing changed, pushed"])
    assert git(bare, "rev-parse", "main") == git(tree, "rev-parse", "HEAD")


def test_the_verb_takes_the_snapshot(kitchen, tree):
    (tree / "demo" / "notes.md").write_text("# notes\nmore\n")
    assert kitchen.main("snapshot") == (0, f"{no_remote(tree)}\n")
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
    code, (said, alerted) = take()
    assert code == 1 and said.startswith("snapshot: git push failed: ")
    assert alerted.startswith("alert: snapshot failed 1 times in a row")


def test_a_commit_whose_push_failed_is_pushed_by_the_next_run_with_nothing_changed(tree, tmp_path):
    git(tree, "remote", "add", "origin", str(tmp_path / "gone.git"))
    (tree / "demo" / "notes.md").write_text("# notes\nbehind\n")
    assert take()[0] == 1
    code, (said,) = take()
    assert code == 1 and said.startswith("snapshot: git push failed: ")
    bare = tmp_path / "gone.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    recovered = "recovered: snapshot after 2 failures since 11:00 ET"
    assert take() == (0, ["snapshot: nothing changed, pushed", recovered])
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
    why = "gitleaks found a secret in the changes (demo/leak.md), nothing committed"
    assert take() == (1, [f"snapshot: {why}", failed(why, "demo")])
    assert git(tree, "rev-parse", "HEAD") == before
    assert git(tree, "diff", "--cached", "--name-only") == ""


CACHE_LOG = "".join(
    f"check 1 of 8\t{step}\t2026-11-08T19:36:04.6132239Z {line}\n"
    for step, line in (
        (
            "Run actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
            "  key: tlc-" + HASH,
        ),
        (
            "Run actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
            "  restore-keys: tlc-" + HASH,
        ),
        (
            "Run actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
            "  restore-key: tlc-" + HASH,
        ),
        (
            "Run actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
            "Cache hit for restore-key: tlc-" + HASH + "8343c21f63409aba",
        ),
        (
            "Run actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
            "Cache restored from key: tlc-" + HASH + "8343c21f63409aba",
        ),
        ("tlc kept", "  KEY: tlc-" + HASH),
        ("tlc kept", "  RESTORED: tlc-" + HASH + "8343c21f63409aba"),
    )
)


@pytest.mark.skipif(not shutil.which("gitleaks"), reason="gitleaks is not installed")
def test_a_ci_log_of_cache_keys_is_committed(tree):
    """actions/cache prints its keys, `<name>-<sha256>-`, which gitleaks' default rules read as an
    API key."""
    (tree / "demo" / "log-1.txt").write_text(CACHE_LOG)
    assert take() == (0, [no_remote(tree)])
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/log-1.txt"


@pytest.mark.skipif(not shutil.which("gitleaks"), reason="gitleaks is not installed")
@pytest.mark.parametrize(
    "leak",
    [
        lambda: "  GITHUB_TOKEN: ghp_" + made_up(36) + "\n",
        lambda: "  AWS_ACCESS_KEY_ID: AKIA" + made_up(16, string.ascii_uppercase + "234567") + "\n",
        lambda: "  key: ghp_" + made_up(36) + "-" + HASH + "\n",
        lambda: "  KEY: AKIA" + made_up(16, string.ascii_uppercase + "234567") + "-" + HASH + "\n",
        lambda: (
            f"check 1 of 8\tRun ghp_{made_up(36)}\t2026-11-08T19:36:04.6132239Z   key: tlc-{HASH}\n"
        ),
    ],
    ids=[
        "github-token",
        "aws-key",
        "github-token-as-a-cache-key",
        "aws-key-as-a-cache-key",
        "github-token-as-a-step",
    ],
)
def test_a_ci_log_of_cache_keys_with_a_secret_in_it_is_refused(tree, leak):
    before = git(tree, "rev-parse", "HEAD")
    (tree / "demo" / "log-1.txt").write_text(CACHE_LOG + leak())
    why = "gitleaks found a secret in the changes (demo/log-1.txt), nothing committed"
    assert take() == (1, [f"snapshot: {why}", failed(why, "demo")])
    assert git(tree, "rev-parse", "HEAD") == before
    assert git(tree, "diff", "--cached", "--name-only") == ""


def made_up(k, alphabet=string.ascii_letters + string.digits):
    return "".join(random.choices(alphabet, k=k))


def secret():
    made_up = "".join(random.choices(string.ascii_letters + string.digits, k=36))
    return f'token = "ghp_{made_up}"\n'


@pytest.mark.skipif(not shutil.which("gitleaks"), reason="gitleaks is not installed")
def test_an_owner_whose_secret_is_gone_has_its_alert_ended_while_another_still_fails(kitchen, tree):
    """The second snapshot reads the whole stage and fails for pantry alone, so demo's file is
    clean and demo's alert ends then, not at a snapshot that fails for nobody."""
    (tree / "demo" / "leak.md").write_text(secret())
    assert take()[0] == 1
    (tree / "demo" / "leak.md").unlink()
    (tree / "pantry").mkdir()
    (tree / "pantry" / "leak.md").write_text(secret())
    code, said = take()
    why = "gitleaks found a secret in the changes (pantry/leak.md), nothing committed"
    assert code == 1 and failed(why, "pantry") in said
    assert any(line.startswith("recovered: snapshot demo after 1 failures") for line in said)
    assert set(jbus.read_json(kitchen.state_dir / "streaks.json", {})) == {"snapshot pantry"}


def test_an_error_no_check_foresaw_is_the_machines_failed_snapshot(tree, monkeypatch):
    def broken(*_):
        raise PermissionError("gitleaks is not executable")

    monkeypatch.setattr(snapshot, "take", broken)
    why = "PermissionError: gitleaks is not executable"
    assert take() == (1, [f"snapshot: {why}", failed(why)])


def test_with_no_gitleaks_nothing_is_committed(tree, monkeypatch):
    monkeypatch.setattr(snapshot.shutil, "which", lambda _: None)
    before = git(tree, "rev-parse", "HEAD")
    (tree / "demo" / "notes.md").write_text("# notes\nunread\n")
    why = "no gitleaks to read the changes, nothing committed"
    assert take() == (1, [f"snapshot: {why}", failed(why)])
    assert git(tree, "rev-parse", "HEAD") == before


def test_the_first_failed_snapshot_alerts_once_and_the_next_that_goes_ends_it(
    kitchen, tree, tmp_path, monkeypatch
):
    with_origin(tree, tmp_path)
    which = snapshot.shutil.which
    monkeypatch.setattr(
        snapshot.shutil, "which", lambda name: None if name == "gitleaks" else which(name)
    )
    why = "no gitleaks to read the changes, nothing committed"
    (tree / "demo" / "notes.md").write_text("# notes\nunread\n")
    assert take() == (1, [f"snapshot: {why}", failed(why)])
    assert take() == (1, [f"snapshot: {why}"])
    assert kitchen.log("notify") == [f"jbus | {failed(why)}"]
    monkeypatch.setattr(snapshot.shutil, "which", which)
    (tree / "demo" / "notes.md").write_text("# notes\nback\n")
    code, said = take()
    assert (code, said[0]) == (0, "snapshot: committed, pushed")
    assert said[1].startswith("recovered: snapshot after 2 failures since 11:00 ET")
    assert jbus.read_json(kitchen.state_dir / "streaks.json", {}) == {}


def killed(kitchen, tree):
    """Run the verb as the unit does, in a process of its own, and stop it as systemd stops a run
    at its `TimeoutStartSec`: a SIGTERM while gitleaks still reads the changes."""
    slow = kitchen.root / "slow-gitleaks"
    slow.mkdir(exist_ok=True)
    reading = kitchen.root / "gitleaks-reading"
    (slow / "gitleaks").write_text(f"#!/bin/sh\ntouch {shlex.quote(str(reading))}\nexec sleep 30\n")
    (slow / "gitleaks").chmod(0o755)
    env = {**os.environ, "PATH": f"{slow}{os.pathsep}{os.environ['PATH']}"}
    (tree / "demo" / "notes.md").write_text("# notes\nkilled\n")
    run = subprocess.Popen(
        [sys.executable, "-m", "jbus", "snapshot"], env=env, start_new_session=True
    )
    for _ in range(300):
        if reading.exists() or run.poll() is not None:
            break
        time.sleep(0.05)
    assert reading.exists(), "the snapshot never reached gitleaks"
    os.killpg(run.pid, signal.SIGTERM)
    assert run.wait(10) == -signal.SIGTERM
    reading.unlink()


def test_a_snapshot_its_timeout_killed_is_raised_once_for_the_machine_by_the_next_pass(
    kitchen, tree
):
    """A kill leaves the run no chance to raise its item, so the next pass sees the run that
    never reached its end and raises it, once for the streak, as the machine's."""
    killed(kitchen, tree)
    assert jbus.read_json(kitchen.state_dir / "streaks.json", {}) == {}
    kitchen.poll()
    item = jbus.read_json(kitchen.state_dir / "streaks.json", {})["snapshot"]
    assert item["alerted"] and item["owner"] == ""
    assert item["line"].startswith("alert: snapshot failed 1 times in a row since 11:00 ET: ")
    assert snapshot.FAILED in item["line"]
    assert [one.key for one in alert.open_items(jbus.load(), NOW)] == ["snapshot"]
    assert kitchen.log("notify") == [f"jbus | {item['line']}"]
    kitchen.poll()
    killed(kitchen, tree)
    kitchen.poll()
    assert kitchen.log("notify") == [f"jbus | {item['line']}"]
    code, said = take()
    assert code == 0 and said[-1].startswith("recovered: snapshot after 2 failures")
    kitchen.poll()
    assert jbus.read_json(kitchen.state_dir / "streaks.json", {}) == {}


def test_a_snapshot_still_running_is_not_raised_by_a_pass(kitchen, tree):
    """A pass that runs while a snapshot waits on gitleaks or on the lock raises nothing."""
    lock = Path(git(tree, "rev-parse", "--absolute-git-dir")) / "jbus-snapshot.lock"
    said = []
    with lock.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        running = threading.Thread(target=lambda: said.append(take()))
        running.start()
        running.join(1)
        assert running.is_alive()
        kitchen.poll()
        assert jbus.read_json(kitchen.state_dir / "streaks.json", {}) == {}
    running.join(10)
    assert said and said[0][0] == 0
    kitchen.poll()
    assert jbus.read_json(kitchen.state_dir / "streaks.json", {}) == {}


def read(name):
    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.optionxform = str
    unit.read(REPO / "features" / "jbus" / "units" / name)
    return unit


def test_the_timer_runs_the_snapshot_at_half_past_eight_twice_a_day_and_catches_up():
    lines = (REPO / "features" / "jbus" / "units" / "jbus-snapshot.timer").read_text().splitlines()
    calendar = [line.split("=", 1)[1] for line in lines if line.startswith("OnCalendar=")]
    assert calendar == ["*-*-* 08:30:00", "*-*-* 17:30:00"]
    timer = read("jbus-snapshot.timer")
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"
    service = read("jbus-snapshot.service")
    assert "OnFailure" not in service["Unit"]
    command = shlex.split(service["Service"]["ExecStart"])
    assert (Path(command[0]).name, command[1:]) == ("jbus", ["snapshot"])
    assert service["Service"]["Type"] == "oneshot"
    for name in UNITS:
        options = [
            line
            for line in (REPO / "features" / "jbus" / "units" / name).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith(("#", ";"))
        ]
        assert options and not [line for line in options if "_exec" in line]


def systemd_manager_answers(env=None):
    """Return whether a systemd manager is reachable: the system bus has its socket, and the user
    manager says what state it is in. A CI job container runs neither."""
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
def test_systemd_reads_the_units_with_no_complaint(tmp_path):
    if not systemd_manager_answers():
        pytest.skip("host-only: needs a systemd manager, which a CI job container does not run")
    jbus_bin = tmp_path / ".local" / "bin" / "jbus"
    jbus_bin.parent.mkdir(parents=True)
    jbus_bin.write_text("#!/bin/sh\n")
    jbus_bin.chmod(0o755)
    ran = subprocess.run(
        [
            "systemd-analyze",
            "--user",
            "verify",
            *(str(REPO / "features" / "jbus" / "units" / u) for u in UNITS),
        ],
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
    (tree / "demo" / "plan.md").write_text("# demo: plan\n")
    assert kitchen.main("snapshot", "--why", "x") == (0, "snapshot: committed, pushed\n")
    assert git(tree, "rev-list", "--count", f"{before}..HEAD") == "1"
    subject = git(tree, "log", "-1", "--format=%s")
    assert subject.startswith("snapshot ") and subject.endswith(" ET: x")
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/plan.md"
    assert git(bare, "rev-parse", "main") == git(tree, "rev-parse", "HEAD")


def test_a_snapshot_with_no_why_says_only_the_time(tree, tmp_path):
    with_origin(tree, tmp_path)
    (tree / "demo" / "standing.md").write_text("1. a rule\n")
    snapshot.take(tree, NOW, jbus.load().user)
    assert git(tree, "log", "-1", "--format=%s") == "snapshot 2026-10-12 11:00 ET"
    (tree / "demo" / "standing.md").write_text("1. a rule\n2. another\n")
    snapshot.take(tree, NOW, jbus.load().user, why="demo standing rule 2 added")
    assert git(tree, "log", "-1", "--format=%s") == (
        "snapshot 2026-10-12 11:00 ET: demo standing rule 2 added"
    )


def test_a_snapshot_waits_for_one_that_is_running(tree, tmp_path):
    """Each home takes a snapshot after an edit, on top of the timer's runs. A second run waits
    and never collides with the first."""
    with_origin(tree, tmp_path)
    (tree / "demo" / "notes.md").write_text("# notes\nwaited\n")
    before = git(tree, "rev-parse", "HEAD")
    lock = Path(git(tree, "rev-parse", "--absolute-git-dir")) / "jbus-snapshot.lock"
    said = []
    with lock.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        second = threading.Thread(target=lambda: said.append(take()))
        second.start()
        second.join(1)
        assert second.is_alive() and said == []
        assert git(tree, "rev-parse", "HEAD") == before
        assert git(tree, "diff", "--cached", "--name-only") == ""
    second.join(10)
    assert said == [(0, ["snapshot: committed, pushed"])]
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/notes.md"


def test_a_snapshot_that_waits_too_long_for_another_fails_and_commits_nothing(tree, monkeypatch):
    monkeypatch.setattr(snapshot, "WAIT", 0.3)
    (tree / "demo" / "notes.md").write_text("# notes\nwaited\n")
    before = git(tree, "rev-parse", "HEAD")
    lock = Path(git(tree, "rev-parse", "--absolute-git-dir")) / "jbus-snapshot.lock"
    with lock.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        why = "another snapshot has run for 0.3 s and holds the lock, nothing committed"
        assert take() == (1, [f"snapshot: {why}", failed(why)])
    assert git(tree, "rev-parse", "HEAD") == before
    assert git(tree, "diff", "--cached", "--name-only") == ""
