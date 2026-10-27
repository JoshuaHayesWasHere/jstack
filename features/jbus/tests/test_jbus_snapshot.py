"""`jbus snapshot` commits the homes' state tree and pushes it, twice a day, and a snapshot that did
not finish alerts once.

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
import string
import subprocess
import threading
from pathlib import Path

import pytest

import jbus
from jbus import snapshot
from test_jbus_kitchen import NOW, REPO, queued

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


def take(now=NOW):
    said = []
    code = snapshot.snapshot(jbus.load(), now, said.append, warn=said.append)
    return code, said


def alarm():
    said = []
    assert snapshot.alarm(jbus.load(), NOW, said.append) == 0
    return said


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
    assert kitchen.webhook.posts == [] and kitchen.log("notify") == []
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


def test_the_first_failed_snapshot_alerts_once_and_the_next_that_goes_logs_it_recovered(
    kitchen, tree, tmp_path
):
    with_origin(tree, tmp_path)
    assert alarm() == ["snapshot failed", f"demo: {FAILED}", "alert sent: demo"]
    assert alarm() == ["snapshot failed"]
    posted = [event for post in kitchen.webhook.posts for event in post]
    assert [(e["event"], e["line"]) for e in posted] == [("alert", FAILED)]
    assert kitchen.log("notify") == [f"jbus | {FAILED}"]
    (tree / "demo" / "notes.md").write_text("# notes\nback\n")
    code, said = take()
    assert (code, said[0]) == (0, "snapshot: committed, pushed")
    (recovered,) = kitchen.lines("recovered")
    assert recovered.startswith("recovered: snapshot after 2 failures since 11:00 ET")
    assert kitchen.log("notify")[1] == f"jbus | {recovered}"
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
    service, failed = read("jbus-snapshot.service"), read("jbus-snapshot-failed.service")
    assert service["Unit"]["OnFailure"] == "jbus-snapshot-failed.service"
    for unit, words in ((service, ["snapshot"]), (failed, ["snapshot", "--alarm"])):
        command = shlex.split(unit["Service"]["ExecStart"])
        assert (Path(command[0]).name, command[1:]) == ("jbus", words)
        assert unit["Service"]["Type"] == "oneshot"
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


def standing(kitchen, tree, *rules, codes=None, where="demo"):
    """Write a home's standing.md of made-up rules under a heading, one numbered rule each, and
    queue the row each rule's `Code:` line names. Rule n names `rule-<n>` unless `codes` gives
    its slug, and a slug of None leaves its `Code:` line out. A slug in `codes` that starts
    `ghost` names no row."""
    codes = codes or [f"rule-{n}" for n in range(1, len(rules) + 1)]
    have = {row["slug"] for row in jbus.queue.load(kitchen.state)}
    for slug in codes:
        if slug and not slug.startswith("ghost") and slug not in have:
            queued(kitchen, slug)
    lines = [
        f"{n}. {rule}." + (f" Code: {slug}." if slug else "") + "\n  More words of it.\n"
        for n, (rule, slug) in enumerate(zip(rules, codes, strict=True), 1)
    ]
    path = tree / where / "standing.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# demo: standing rules (at most 3)\n\nWhy the cap.\n\n" + "".join(lines))
    return path


def refused(path, *why):
    return (1, [f"snapshot: refused, nothing committed: {path} {'; '.join(why)}"])


def test_three_rules_each_made_code_by_a_queued_row_are_snapshotted(kitchen, tree):
    standing(kitchen, tree, "one", "two", "three")
    standing(kitchen, tree, "a scoped one", where="demo/flow")
    assert take() == (0, [no_remote(tree)])
    shown = git(tree, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert sorted(shown) == ["demo/flow/standing.md", "demo/standing.md"]


def test_a_fourth_rule_is_refused_and_nothing_is_committed_or_left_staged(kitchen, tree):
    before = git(tree, "rev-parse", "HEAD")
    path = standing(kitchen, tree, "one", "two", "three", "four")
    (tree / "demo" / "notes.md").write_text("# notes\nheld back\n")
    assert take() == refused(path, "has 4 rules, and a standing.md holds at most 3")
    assert git(tree, "rev-parse", "HEAD") == before
    assert git(tree, "diff", "--cached", "--name-only") == ""


def test_a_rule_with_no_code_row_is_refused(kitchen, tree):
    before = git(tree, "rev-parse", "HEAD")
    path = standing(kitchen, tree, "one", "two", codes=["rule-1", None])
    assert take() == refused(path, "rule 2 has no Code: <slug>, the queue row that makes it code")
    assert git(tree, "rev-parse", "HEAD") == before


def test_a_code_slug_that_is_in_no_queue_is_refused(kitchen, tree):
    path = standing(kitchen, tree, "one", codes=["ghost-row"])
    assert take() == refused(path, "rule 1 names Code: ghost-row, which is in no queue of demo")


def test_a_scoped_homes_standing_md_is_held_to_the_same_cap(kitchen, tree):
    path = standing(kitchen, tree, "a", "b", "c", "d", codes=["rule-1"] * 4, where="demo/flow")
    assert take() == refused(path, "has 4 rules, and a standing.md holds at most 3")


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file with no read bit")
def test_an_unreadable_standing_md_is_refused_and_the_alarm_still_alerts(kitchen, tree):
    path = standing(kitchen, tree, "one")
    path.chmod(0)
    try:
        assert take() == refused(path, "cannot be read: Permission denied")
        said = alarm()
    finally:
        path.chmod(0o644)
    assert said[1] == f"demo: {FAILED}: {path} cannot be read: Permission denied"


def test_the_verb_says_the_refusal_on_stderr_and_exits_1(kitchen, tree, capsys):
    path = standing(kitchen, tree, "one", codes=[None])
    assert snapshot.snapshot(jbus.load(), NOW, print) == 1
    out, err = capsys.readouterr()
    assert out == ""
    why = "rule 1 has no Code: <slug>, the queue row that makes it code"
    assert err == f"{refused(path, why)[1][0]}\n"


def test_the_alarm_of_a_refused_snapshot_says_which_rule_and_why(kitchen, tree):
    path = standing(kitchen, tree, "one", codes=[None])
    assert take()[0] == 1
    said = alarm()
    why = f"{path} rule 1 has no Code: <slug>, the queue row that makes it code"
    assert said[1] == f"demo: {FAILED}: {why}"


def test_a_refused_standing_md_is_left_out_and_the_rest_of_the_tree_is_committed(kitchen, tree):
    other = kitchen.second()
    kept = "# other: standing rules (at most 3)\n"
    path = tree / other.name / "standing.md"
    path.write_text(kept)
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "other's rules")
    before = git(tree, "rev-parse", "HEAD")
    (tree / "demo" / "notes.md").write_text("# notes\nA's change\n")
    path.write_text(f"{kept}\n1. A rule with no code.\n")
    code, said = take()
    why = f"other: {path} rule 1 has no Code: <slug>, the queue row that makes it code"
    assert (code, said) == (1, [f"snapshot: refused, left out: {why}", no_remote(tree)])
    assert git(tree, "rev-parse", "HEAD~1") == before
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/notes.md"
    assert git(tree, "show", "HEAD:other/standing.md") == kept.strip()
    assert git(tree, "status", "--porcelain") == "M other/standing.md"
    assert f"{FAILED}: {why}" in alarm()[1]


def with_origin(tree, tmp_path):
    bare = tmp_path / "state-tree.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(tree, "remote", "add", "origin", str(bare))
    return bare


def test_an_edit_snapshotted_with_why_is_one_pushed_commit_that_says_why(kitchen, tree, tmp_path):
    bare = with_origin(tree, tmp_path)
    before = git(tree, "rev-parse", "HEAD")
    standing(kitchen, tree, "2026-10-15: a rule")
    assert kitchen.main("snapshot", "--why", "x") == (0, "snapshot: committed, pushed\n")
    assert git(tree, "rev-list", "--count", f"{before}..HEAD") == "1"
    subject = git(tree, "log", "-1", "--format=%s")
    assert subject.startswith("snapshot ") and subject.endswith(" ET: x")
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/standing.md"
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


def test_why_is_not_taken_with_alarm(kitchen, tree):
    code, said = kitchen.main("snapshot", "--alarm", "--why", "x")
    assert code == 2 and "not allowed with argument" in said


def undo_section():
    """Return the shell lines of the section of features/home/docs/state.md that undoes an edit
    to standing.md."""
    text = (REPO / "features" / "home" / "docs" / "state.md").read_text()
    section = text.split("## Undo an edit to standing.md\n", 1)[1].split("\n## ", 1)[0]
    block = section.split("```sh\n", 1)[1].split("```", 1)[0]
    return [line for line in block.splitlines() if line and not line.startswith("#")]


def test_the_documented_undo_brings_back_the_text_before_a_bad_edit(kitchen, tree, tmp_path):
    with_origin(tree, tmp_path)
    kept = standing(kitchen, tree, "keep this").read_text()
    assert kitchen.main("snapshot", "--why", "demo standing rule 1 added")[0] == 0
    path = standing(kitchen, tree, "a bad merge")
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
    assert path.read_text() == kept
    words = shlex.split(run(again))
    assert words[:2] == ["jbus", "snapshot"]
    assert kitchen.main(*words[1:]) == (0, "snapshot: committed, pushed\n")
    assert git(tree, "log", "-1", "--format=%s").endswith(f": demo standing.md, {bad} undone")
    assert git(tree, "show", "--name-only", "--format=", "HEAD") == "demo/standing.md"


def test_the_documented_undo_of_a_commit_that_is_not_there_writes_nothing(kitchen, tree, tmp_path):
    with_origin(tree, tmp_path)
    path = standing(kitchen, tree, "the first rule")
    first = path.read_text()
    assert kitchen.main("snapshot", "--why", "demo standing rule 1 added")[0] == 0
    _, restore, _ = undo_section()
    for commit in ("0123abc", git(tree, "rev-list", "--max-parents=0", "HEAD")):
        line = restore.replace("~/.local/state/home", shlex.quote(str(tree)))
        line = line.replace("<repo>", "demo").replace("<commit>", commit)
        assert subprocess.run(line, shell=True, capture_output=True).returncode != 0
        assert path.read_text() == first


def test_the_documented_undo_of_the_edit_that_made_the_file_removes_it(kitchen, tree, tmp_path):
    with_origin(tree, tmp_path)
    path = standing(kitchen, tree, "the first rule")
    assert kitchen.main("snapshot", "--why", "demo standing rule 1 added")[0] == 0
    made = git(tree, "rev-parse", "HEAD")
    _, restore, _ = undo_section()
    line = restore.replace("~/.local/state/home", shlex.quote(str(tree)))
    line = line.replace("<repo>", "demo").replace("<commit>", made)
    subprocess.run(line, shell=True, check=True)
    assert not path.exists()
    assert kitchen.main("snapshot", "--why", "undone") == (0, "snapshot: committed, pushed\n")
    assert git(tree, "show", "--name-status", "--format=", "HEAD") == "D\tdemo/standing.md"


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
        assert take() == (
            1,
            ["snapshot: another snapshot has run for 0.3 s and holds the lock, nothing committed"],
        )
    assert git(tree, "rev-parse", "HEAD") == before
    assert git(tree, "diff", "--cached", "--name-only") == ""
