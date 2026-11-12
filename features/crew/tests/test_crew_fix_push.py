"""The crew skill's push of a fix: a new commit on the head GitHub has, never a rewrite."""

import os
import shlex
import subprocess
import sys

import pytest

import test_room as room
from crew_helpers import PullRequest, block, git
from testing.layouts import assembled

ABOUT = "a rebase is not pushed yet"


def pushed_with(pr):
    """The run of the block in the crewmate's worktree, with what git's hook said."""
    return subprocess.run(
        ["sh", "-c", block("The review", ABOUT)],
        capture_output=True,
        text=True,
        cwd=pr.work,
        env=os.environ,
    )


def pushes(pr):
    """What the block prints in the crewmate's worktree."""
    return pushed_with(pr).stdout


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
SELECTOR = (
    "import sys\n"
    "assert sys.argv[1:3] in (['--part', 'touched'], ['--part', 'cross'], ['--part', 'names'])\n"
)


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


def hooked(pr, tmp_path, monkeypatch, lines=""):
    """Give the crewmate's worktree a brief with a `Thread:` line and `lines`, and jleak's crew
    rule (`jleak.crewpush`) as the `pre-push` hook of its repo. It returns the brief."""
    homes = tmp_path / "homes"
    monkeypatch.setenv("JBUS_HOME_DIR", str(homes))
    tasks = tmp_path / "state" / "tasks"
    tasks.mkdir(parents=True)
    brief = tasks / "a-task.md"
    brief.write_text("# a-task: a task\nThread: mcp:thread-1\n\n## Result\n" + lines)
    (homes / "main").mkdir(parents=True)
    (homes / "main" / "tasks").symlink_to(tasks)
    hooks = tmp_path / "main" / ".git" / "hooks"
    (hooks / "pre-push").write_text(HOOK.format(python=shlex.quote(sys.executable)))
    (hooks / "pre-push").chmod(0o755)
    return brief


def full(head, base="0" * 40):
    return f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"


def light(head, base="0" * 40):
    return f"Checked: make check-fast BASE={base} PART=guards exit 0 at {head}\n"


def test_a_merge_of_the_base_with_the_guards_and_the_lint_is_pushed(tmp_path, monkeypatch):
    """#1729: a pull request in conflict merges main over the head its desk's check passed at.
    That merge is pushed on a `Checked:` line of the guards and the lint alone, and CI runs the
    rest at the pushed head, so a main that moves faster than the whole check cannot outrun it."""
    pr = PullRequest(tmp_path, None, "other.txt")
    checked = pr.head()
    brief = hooked(pr, tmp_path, monkeypatch, full(checked))
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "merge", "-q", "--no-edit", "origin/main")
    with brief.open("a") as lines:
        lines.write(light(pr.head(), pr.landed))
    assert pushes(pr) == f"pushed {pr.head()}\n"
    assert origin(pr) == pr.head()


@pytest.mark.parametrize("merged", [False, True], ids=["a fix", "a merge of the base, then a fix"])
def test_the_guards_and_the_lint_push_no_other_change(merged, tmp_path, monkeypatch):
    """A head that adds a commit of its own over the checked head is more than a merge of the
    base: the guards and the lint do not bind it, and the hook refuses it."""
    pr = PullRequest(tmp_path, None, "other.txt")
    checked = pr.head()
    brief = hooked(pr, tmp_path, monkeypatch, full(checked))
    if merged:
        git(pr.work, "fetch", "-q", "origin")
        git(pr.work, "merge", "-q", "--no-edit", "origin/main")
    pr.commit(pr.work, "fix.txt", "the fix\n", "the fix")
    with brief.open("a") as lines:
        lines.write(light(pr.head(), pr.landed))
    ran = pushed_with(pr)
    assert ran.stdout == "the push was refused: origin did not take a plain push of a-task\n"
    assert f"its last Checked: line, the guards and the lint at {pr.head()[:12]}" in ran.stderr
    assert origin(pr) == checked


def test_the_guards_and_the_lint_alone_push_no_head(tmp_path, monkeypatch):
    """With no line of the desk's whole check before it, a line of the guards and the lint has
    no checked head to be a merge of the base over."""
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    brief = hooked(pr, tmp_path, monkeypatch)
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "merge", "-q", "--no-edit", "origin/main")
    with brief.open("a") as lines:
        lines.write(light(pr.head(), pr.landed))
    ran = pushed_with(pr)
    assert ran.stdout == "the push was refused: origin did not take a plain push of a-task\n"
    assert "no line of the desk's whole check" in ran.stderr
    assert origin(pr) == was


def test_a_fix_whose_failed_file_is_still_red_is_not_pushed(tmp_path, monkeypatch):
    """CI failed on `tests/test_ci.py`, which the fix only reaches, and the block of "The failed
    files" kept its name. The check block at the fix head runs it, and while it fails the
    `Checked:` line binds no pass, so jleak's crew rule at `pre-push` (`jleak.crewpush`) refuses
    the fix. Once it passes at the head, the same fix goes out."""
    pr = PullRequest(tmp_path, None, "other.txt")
    was = pr.head()
    hooked(pr, tmp_path, monkeypatch)
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
