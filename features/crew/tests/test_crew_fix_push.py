"""The crew skill's push of a fix: a new commit on the head GitHub has, never a rewrite."""

import os
import shlex
import subprocess
import sys

import test_room as room
from crew_helpers import PullRequest, block, git
from testing.layouts import assembled

ABOUT = "a rebase is not pushed yet"


def pushes(pr):
    """What the block prints in the crewmate's worktree."""
    return subprocess.run(
        ["sh", "-c", block("The review", ABOUT)],
        capture_output=True,
        text=True,
        cwd=pr.work,
        env=os.environ,
    ).stdout


def origin(pr):
    return git(pr.work, "ls-remote", "origin", "a-task").split()[0]


def test_a_new_commit_on_the_pushed_head_is_pushed(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    assert pushes(pr) == f"pushed {pr.head()}\n"
    assert origin(pr) == pr.head()


def test_an_amended_head_is_not_pushed(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    git(pr.work, "commit", "-q", "--amend", "-m", "the task, amended")
    assert pushes(pr) == f"no push: this head does not hold origin's a-task at {was}\n"
    assert origin(pr) == was


def test_a_rebase_nothing_asked_for_is_not_pushed(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "rebase", "-q", "origin/main")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    assert pushes(pr) == f"no push: this head does not hold origin's a-task at {was}\n"
    assert origin(pr) == was


def test_a_rebase_for_a_conflict_is_left_to_its_own_block(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "rebase", "-q", "origin/main")
    (pr.git_dir / "crew-before-rebase").write_text(f"{was} main {was}\n")
    assert (
        pushes(pr) == "no push: a rebase is not pushed yet, push it with the block of A conflict\n"
    )
    assert origin(pr) == was


def test_a_record_left_by_a_rebase_pushed_some_other_way_stops_no_fix(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "rebase", "-q", "origin/main")
    git(
        pr.work,
        "push",
        "-q",
        f"--force-with-lease=refs/heads/a-task:{was}",
        "origin",
        "HEAD:a-task",
    )
    (pr.git_dir / "crew-before-rebase").write_text(f"{was} main {was}\n")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    assert pushes(pr) == f"pushed {pr.head()}\n"


def test_a_head_behind_a_merge_github_made_is_not_pushed_and_merges_it_in(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    other = tmp_path / "other"
    git(other, "fetch", "-q", "origin")
    git(other, "checkout", "-q", "-b", "a-task", "origin/a-task")
    git(other, "merge", "-q", "--no-edit", "origin/main")
    git(other, "push", "-q", "origin", "HEAD:a-task")
    merged = git(other, "rev-parse", "HEAD")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    assert pushes(pr) == f"no push: this head does not hold origin's a-task at {merged}\n"
    git(pr.work, "merge", "-q", "--no-edit", "FETCH_HEAD")
    assert pushes(pr) == f"pushed {pr.head()}\n"


def test_the_way_back_from_an_amend_keeps_the_fix_and_needs_no_force(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    (pr.work / "fix.txt").write_text("the fix\n")
    git(pr.work, "add", "fix.txt")
    git(pr.work, "commit", "-q", "--amend", "-m", "the task, amended")
    pushes(pr)
    git(pr.work, "reset", "-q", "--soft", "FETCH_HEAD")
    git(pr.work, "commit", "-q", "-m", "the fix")
    assert pushes(pr) == f"pushed {pr.head()}\n"
    assert git(pr.work, "show", f"{origin(pr)}:fix.txt") == "the fix"


HOOK = """#!/bin/sh
exec {python} -c '
import sys
from jleak import crewpush
found = crewpush.refused(sys.stdin.read().splitlines())
print("\\n".join(found), file=sys.stderr)
sys.exit(1 if found else 0)'
"""
SELECTOR = "import sys\nassert sys.argv[1:3] in (['--part', 'touched'], ['--part', 'cross'])\n"


def checks(pr, tmp_path, red):
    """Run the check block of "Do the task" in the crewmate's worktree, with a `make` that fails
    the test file CI failed on while `red`, and passes every other step."""
    stub = tmp_path / "check-stub"
    stub.mkdir(exist_ok=True)
    room.uv(stub)
    fails = 'case "$*" in *test_ci.py*) exit 1 ;; esac\n' if red else ""
    (stub / "make").write_text("#!/bin/sh\n" + fails)
    (stub / "make").chmod(0o755)
    script = block("Do the task", "<check command>")
    script = script.replace("<thread id>", "mcp:thread-1").replace("<slug>", "a-task")
    return subprocess.run(
        ["sh", "-c", script],
        capture_output=True,
        text=True,
        cwd=pr.work,
        env={
            **os.environ,
            "HOME": str(tmp_path / "home"),
            "TEST_SLOTS": "3",
            "PATH": f"{stub}:{room.BIN}:{os.environ['PATH']}",
            "T": str(assembled() / "templates"),
            "H": str(tmp_path / "state"),
        },
    ).returncode


def test_a_fix_whose_failed_file_is_still_red_is_not_pushed(tmp_path, monkeypatch):
    """CI failed on `tests/test_ci.py`, which the fix only reaches, and the block of "The failed
    files" kept its name. The check block at the fix head runs it, and while it fails the
    `Checked:` line binds no pass, so jleak's crew rule at `pre-push` (`jleak.crewpush`) refuses
    the fix. Once it passes at the head, the same fix goes out."""
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    homes = tmp_path / "homes"
    monkeypatch.setenv("JBUS_HOME_DIR", str(homes))
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "a-task.md").write_text("# a-task: a task\nThread: mcp:thread-1\n\n## Result\n")
    (homes / "main").mkdir(parents=True)
    (homes / "main" / "tasks").symlink_to(tasks)
    hooks = tmp_path / "main" / ".git" / "hooks"
    (hooks / "pre-push").write_text(HOOK.format(python=shlex.quote(sys.executable)))
    (hooks / "pre-push").chmod(0o755)
    (pr.work / "scripts").mkdir()
    (pr.work / "scripts" / "select_tests.py").write_text(SELECTOR)
    (pr.work / "tests").mkdir()
    (pr.work / "tests" / "test_ci.py").write_text("")
    git(pr.work, "add", "-A")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    (pr.git_dir / "crew-failed-files").write_text("tests/test_ci.py\n")

    assert checks(pr, tmp_path, red=True) == 1
    assert pushes(pr) == "the push was refused: origin did not take a plain push of a-task\n"
    assert origin(pr) == was

    assert checks(pr, tmp_path, red=False) == 0
    assert pushes(pr) == f"pushed {pr.head()}\n"
