"""The crew skill's proof block runs the tests a branch changes at its head, then laid over its
merge-base's code, and prints the `Proved:` line `jmerge` reads (`ready.short_on_proved`). A
test that fails without the change proves it; one that passes at the base as well proves nothing,
and the line says so with the base's exit 0. A branch that changes no test gets no run.

The tests run the block in a real repo whose `origin/main` is the base, on macOS's tools
(`bsd_tools`), with a `uv` on PATH that runs pytest on this interpreter, takes the slot by running
the command, and syncs nothing. Each run leaves `git worktree list` as it found it, whether its
tests pass, fail or are cut off, and each that ends leaves no copy of the base in its temp
directory, whether its tests pass, fail, hit the lane's time limit or are stopped with TERM. The
block is one command that runs `$T/proved.sh`, so the command a crew sends holds no `rm`.

A branch that changes only a fork's `packaging/` folder has its tests inside its patches: the
block lays each side's series over its PKGBUILD's tag, here a tarball fetched by `file://` URL whose
package's `test` script passes where the patched code says `new`, with a `vp` that installs
nothing."""

import os
import re
import shlex
import signal
import subprocess
import sys
import tarfile
import time

import pytest

from crew_helpers import block, git
from jbriefs import proved
from test_blocks_command_grep import UGREP
from test_portable_shell import bsd_tools
from testing.layouts import assembled

TIMEOUT = """import os, signal, subprocess, sys
run = subprocess.Popen(sys.argv[2:], process_group=0)
try:
    sys.exit(run.wait(float(sys.argv[1])))
except subprocess.TimeoutExpired:
    os.killpg(run.pid, signal.SIGTERM)
    run.wait()
    sys.exit(124)
"""
"""GNU `timeout`, which macOS lacks: the command in a group of its own, sent TERM at the limit,
exit 124."""
UV = f"""#!/bin/bash
case " $* " in
*" jgauge test-slot "*)
    if [ -n "$SLOTS" ]; then
        taken=$(cat "$TMPDIR/slots-taken" 2> /dev/null || echo 0)
        if [ "$taken" -ge "$SLOTS" ]; then
            echo "every slot of the lane is taken: this thread waits"
            exit 76
        fi
        echo $((taken + 1)) > "$TMPDIR/slots-taken"
    fi
    limit=$FULL_LIMIT
    case " $* " in *" --short "*) limit=$LIMIT ;; esac
    while [ "$1" != -- ]; do shift; done
    shift
    if [ -n "$limit" ]; then exec {sys.executable} -c {shlex.quote(TIMEOUT)} "$limit" "$@"; fi
    exec "$@"
    ;;
*" sync "*) exit 0 ;;
*" run python "*)
    if [ -n "$NO_XDIST" ]; then exit 1; fi
    shift 2
    exec {sys.executable} "$@"
    ;;
*" run pytest "*)
    if [ -n "$STALL" ]; then
        : > "$STALL"
        sleep 60
    fi
    if [ -n "$SLOW" ]; then sleep "$SLOW"; fi
    shift 2
    echo "$*" >> "$TMPDIR/pytest-args"
    exec {sys.executable} -m pytest "$@"
    ;;
esac
exit 64
"""
"""`uv` as the block calls it. A short test-slot run is stopped at `LIMIT` seconds, exit 124, as
the short lane stops one at its limit, and a full one at `FULL_LIMIT` seconds; each pytest run
takes `SLOW` seconds more, `NO_XDIST` stands for a repo whose venv has no pytest-xdist, and with
`SLOTS` set only that many test-slot calls get a slot, and every one after them finds every slot
taken, exit 76."""
BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
OLD_TEST = "from calc import add\n\n\ndef test_zero():\n    assert add(0, 0) == 0\n"
FAILS_AT_BASE = OLD_TEST + "\n\ndef test_two():\n    assert add(2, 2) == 4\n"
PASSES_AT_BASE = OLD_TEST + "\n\ndef test_still_zero():\n    assert add(1, 0) == 1\n"
RESULT = "# a-task: a task\n\n## Result\nStatus: done\n"


@pytest.fixture
def repo(tmp_path):
    """A repo whose base commit has a buggy `add` and a test that misses the bug, and ignores
    the bytecode a run leaves, with `origin/main` at that commit, and a home whose brief has a
    Result."""
    tree = tmp_path / "repo"
    tree.mkdir()
    git(tree, "init", "-q", "-b", "main")
    git(tree, "config", "user.email", "crew@example.test")
    git(tree, "config", "user.name", "crew")
    (tree / "calc.py").write_text(BUGGY)
    (tree / "tests").mkdir()
    (tree / "tests" / "test_calc.py").write_text(OLD_TEST)
    (tree / ".gitignore").write_text("__pycache__/\n")
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "base")
    git(tree, "update-ref", "refs/remotes/origin/main", "HEAD")
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "uv").write_text(UV)
    (stub / "uv").chmod(0o755)
    (tmp_path / "home" / "tasks").mkdir(parents=True)
    (tmp_path / "home" / "tasks" / "a-task.md").write_text(RESULT)
    return tree


def commit(tree, files):
    for name, text in files.items():
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        (tree / name).write_text(text)
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "the change")
    return git(tree, "rev-parse", "HEAD")


def script():
    return (
        block("Do the task", "proved.sh")
        .replace("<slug>", "a-task")
        .replace("<thread id>", "mcp:thread-1")
    )


def environ(tree, **more):
    return {
        "PATH": f"{tree.parent / 'stub'}:{bsd_tools(tree.parent / 'bsd')}",
        "HOME": str(tree.parent),
        "H": str(tree.parent / "home"),
        "T": str(assembled() / "templates"),
        "TMPDIR": str(tree.parent),
        "PYTEST_XDIST_AUTO_NUM_WORKERS": "2",
        **more,
    }


def worktrees(tree):
    return git(tree, "worktree", "list", "--porcelain")


def copies(tree):
    return sorted(path.name for kind in ("base", "fork") for path in tree.parent.glob(f"{kind}.*"))


def proof(tree, shell="", **more):
    before = worktrees(tree)
    ran = subprocess.run(
        ["bash", "-c", shell + script()],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=60,
        env=environ(tree, **more),
    )
    assert worktrees(tree) == before
    assert copies(tree) == []
    home = tree.parent / "home"
    return ran.stdout, proved.proved((home / "tasks" / "a-task.md").read_text())


def test_the_proof_block_runs_the_script_by_its_path_and_holds_no_rm(repo):
    """Claude Code holds a command that has `rm` in it for an approval, even in full access, and
    it held the block's `trap 'rm -rf "$tree"' EXIT` ("This shell -c script runs rm and could not
    be checked"): on 2026-11-07 five crews stalled on it for hours, with nothing to wake them. The
    block the crew sends runs `$T/proved.sh` with the brief and the thread, and holds no `rm`."""
    stub = repo.parent / "stub"
    (stub / "bash").write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$TMPDIR/bash-args"\n')
    (stub / "bash").chmod(0o755)
    env = environ(repo)
    subprocess.run(["sh", "-c", script()], cwd=repo, env=env, check=True, timeout=60)
    ran = (repo.parent / "bash-args").read_text().splitlines()
    assert ran == [f"{env['T']}/proved.sh", f"{env['H']}/tasks/a-task.md", "mcp:thread-1"]
    assert not re.search(r"\brm\b", script())


def test_a_test_that_fails_without_the_fix_is_proved(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo)
    assert "head exit 0: 2 passed" in said
    assert "base exit 1: 1 failed, 1 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)


def test_a_test_that_passes_at_the_base_too_is_written_with_its_exit_0(repo):
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": PASSES_AT_BASE})
    _, line = proof(repo)
    assert (line.base_exit, line.head_exit) == (0, 0)


def test_a_test_of_a_name_the_base_lacks_fails_at_the_base_and_is_no_collection_error(repo):
    added = "from calc import times\n\n\ndef test_times():\n    assert times(2, 3) == 6\n"
    times = "\n\ndef times(a, b):\n    return a * b\n"
    commit(repo, {"calc.py": FIXED + times, "tests/test_times.py": added})
    _, line = proof(repo)
    assert (line.tests, line.base_exit, line.head_exit) == (("tests/test_times.py",), 1, 0)


def test_a_change_with_no_test_runs_nothing_and_writes_no_line(repo):
    commit(repo, {"README.md": "how\n"})
    said, line = proof(repo)
    assert said.startswith("no test changed: the Result says Proved: none, <kind>")
    assert line is None


def test_a_test_that_fails_at_the_head_too_leaves_the_worktree_list_as_it_was(repo):
    broken = OLD_TEST + "\n\ndef test_three():\n    assert add(1, 1) == 3\n"
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": broken})
    said, line = proof(repo)
    assert "head exit 1: 1 failed, 1 passed" in said
    assert (line.base_exit, line.head_exit) == (1, 1)


def test_a_run_cut_off_mid_test_leaves_the_worktree_list_as_it_was(repo):
    """A thread's harness kills a call that runs past its time limit, and the user can stop one:
    nothing after the kill runs, so the block makes nothing it would have to undo."""
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    before = worktrees(repo)
    stalled = repo.parent / "stalled"
    running = subprocess.Popen(
        ["bash", "-c", script()],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environ(repo, STALL=str(stalled)),
        start_new_session=True,
    )
    try:
        waited = time.monotonic() + 30
        while not stalled.exists():
            assert running.poll() is None and time.monotonic() < waited
            time.sleep(0.05)
    finally:
        os.killpg(running.pid, signal.SIGKILL)
        running.wait()
    assert worktrees(repo) == before


def test_a_run_stopped_mid_test_leaves_no_copy_of_the_base(repo):
    """A harness stops a call that runs past its time limit with TERM to its group: the script
    removes its copy of the base as it exits, as after a pass, a failure or a 124."""
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    stalled = repo.parent / "stalled"
    running = subprocess.Popen(
        ["bash", "-c", script()],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environ(repo, STALL=str(stalled)),
        start_new_session=True,
    )
    try:
        waited = time.monotonic() + 30
        while not stalled.exists():
            assert running.poll() is None and time.monotonic() < waited
            time.sleep(0.05)
        assert copies(repo) != []
        os.killpg(running.pid, signal.SIGTERM)
        running.wait(30)
    finally:
        if running.poll() is None:
            os.killpg(running.pid, signal.SIGKILL)
            running.wait()
    assert copies(repo) == []


def test_a_temp_directory_that_is_gone_leaves_the_branch_checked_out(repo):
    """A thread's TMPDIR can be gone, as a settled row's scratch is: no copy of the base can be
    made, and the block says so and leaves the worktree on its branch, never checked out at the
    base in its place."""
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, TMPDIR=str(repo.parent / "gone"))
    assert said.startswith("no proof: no copy of the base could be made in ")
    assert line is None
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "branch", "--show-current") == "main"


def test_a_test_that_reads_git_runs_at_the_base_in_a_repo_of_its_own(repo):
    """A test the change lays over the base may run git in its tree, as one that lists the
    tracked files does: at the base it finds a repository at the base's commit, so it fails
    there only for the change and not for want of a `.git`."""
    reads = (
        "import subprocess\n\n\ndef test_tracked():\n"
        "    said = subprocess.run(\n"
        "        ['git', 'ls-files'], capture_output=True, text=True, check=True\n"
        "    )\n"
        "    assert 'calc.py' in said.stdout.split()\n"
    )
    commit(repo, {"calc.py": FIXED, "tests/test_git.py": reads})
    said, line = proof(repo)
    assert "base exit 0: 1 passed" in said
    assert (line.base_exit, line.head_exit) == (0, 0)


def test_a_branch_that_changes_only_tests_runs_them_at_the_head_alone(repo):
    """A test made faster changes no code: the base's code is the head's own, so the tests pass
    there too and a base run proves nothing. The block runs them at the head and says so."""
    faster = OLD_TEST + "\n\ndef test_one():\n    assert add(1, 0) == 1\n"
    head = commit(repo, {"tests/test_calc.py": faster, "tests/conftest.py": ""})
    said, line = proof(repo)
    assert "tests only: every file the branch changes is a test" in said
    assert "head exit 0: 2 passed" in said
    assert "base exit" not in said
    assert f"Proved: tests/test_calc.py head exit 0 at {head}, tests only\n" in said
    assert line == proved.Proved(("tests/test_calc.py",), head_exit=0, head=head, tests_only=True)


def test_a_branch_that_changes_tests_with_docs_and_config_runs_them_at_the_head_alone(repo):
    """A removal of tests with the doc that named them changes no code either: `jmerge` takes
    the `tests only` line where every other file is of a `jbriefs.proved.EXEMPT` kind, so the
    block prints it for such a branch."""
    head = commit(
        repo,
        {
            "tests/test_calc.py": PASSES_AT_BASE,
            "README.md": "how\n",
            "docs/guide": "why\n",
            "pyproject.toml": "[project]\n",
            ".github/workflows/ci.yml": "on: push\n",
            ".gitignore": "*.pyc\n",
        },
    )
    said, line = proof(repo)
    assert "tests only: every file the branch changes is a test" in said
    assert "base exit" not in said
    assert f"Proved: tests/test_calc.py head exit 0 at {head}, tests only\n" in said
    assert line == proved.Proved(("tests/test_calc.py",), head_exit=0, head=head, tests_only=True)


def test_a_branch_that_changes_a_test_docs_and_any_other_file_runs_it_at_the_base_too(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"tests/test_calc.py": PASSES_AT_BASE, "README.md": "how\n", "util.py": ""})
    said, line = proof(repo)
    assert "tests only" not in said
    assert "base exit 0: 2 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 0, base, 0, head)


def test_a_change_to_source_and_tests_runs_at_the_base_where_grep_is_claude_codes_ugrep(repo):
    """In a Claude Code agent shell `grep` is a function that runs its embedded ugrep, which
    answered `grep -qvE` with no line kept where grep kept one: the block said "tests only" for
    a change to `calc.py`. `UGREP` stands in for it."""
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, shell=UGREP + "export -f grep\n")
    assert "tests only" not in said
    assert "base exit 1: 1 failed, 1 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)


def test_a_slow_test_file_is_proved_where_the_head_and_the_base_each_fit_the_lane(repo):
    """A test file that takes over half the short lane's limit, as
    `testing/tests/test_select_tests.py` did before its tests of the real tree moved out, fits it
    at the head and at the base, but not both in one run: the side the lane's limit cuts runs
    again alone in a full slot, and the block still writes one `Proved:` line."""
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, LIMIT="7", SLOW="4")
    assert "no proof" not in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)


def test_a_side_the_short_lane_stops_is_proved_alone_in_a_full_slot(repo):
    """A head run of browser page tests took 226 s, and the short lane stopped it at its 120 s
    four times, so its branch could never be proved: a side that ends 124 in the short lane runs
    again alone in a full slot, as the check block's steps do, and the `Proved:` line is that
    run's."""
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, LIMIT="1", SLOW="3")
    stopped = (
        "head: stopped at the short lane's limit, no verdict: it runs again alone in a full slot"
    )
    assert stopped in said
    assert "head exit 0: 2 passed" in said
    assert "base exit 1: 1 failed, 1 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)


def test_a_run_that_hits_a_full_slots_limit_too_leaves_no_copy_of_the_base(repo):
    """A slot's run that ends 124 in the full slot as well reaches no verdict, and the block
    goes on to print no proof: the copy of the base it made goes with it, as after a pass or a
    failure."""
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, LIMIT="1", FULL_LIMIT="1", SLOW="5")
    assert "no proof: the slot's run ended 124" in said
    assert line is None


def test_the_head_and_the_base_run_on_pytests_workers_where_the_repo_has_them(repo):
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    proof(repo)
    runs = (repo.parent / "pytest-args").read_text().splitlines()
    assert len(runs) == 2
    assert all("-n auto" in run for run in runs)


def test_a_repo_without_pytest_xdist_is_proved_on_one_process(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, NO_XDIST="1")
    assert "base exit 1: 1 failed, 1 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)
    runs = (repo.parent / "pytest-args").read_text().splitlines()
    assert not any("-n " in run for run in runs)


def test_one_free_slot_runs_the_head_side_and_the_base_side(repo):
    """On a busy machine a wake frees one slot: the block took it for the head side, gave it
    back and asked again for the base side, which found every slot taken, so gs-scratch-prune's
    proof ran its head side four wakes in a row and never its base side. Both sides run in the
    one slot the block gets."""
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, SLOTS="1")
    assert "head exit 0: 2 passed" in said
    assert "base exit 1: 1 failed, 1 passed" in said
    assert "no proof" not in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)


def test_no_free_slot_runs_no_side_and_ends_76(repo):
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, SLOTS="0")
    assert "exit" not in said.replace("ended 76", "")
    assert "no proof: the slot's run ended 76" in said
    assert line is None
    assert not (repo.parent / "pytest-args").exists()


def test_a_wake_after_the_base_side_waited_runs_the_base_side_alone(repo):
    """A base side the short lane's limit cut asks for a full slot, and on a busy machine finds
    every one taken. A side that exited 0 at a head and base is kept, and the run after the wait
    runs only the side still owed."""
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    said, line = proof(repo, SLOTS="1", LIMIT="5", SLOW="3")
    assert "head exit 0: 2 passed" in said
    assert "base: stopped at the short lane's limit" in said
    assert "no proof: the slot's run ended 76" in said
    assert line is None
    said, line = proof(repo)
    assert "head: exited 0 at this head and base already" in said
    assert "base exit 1: 1 failed, 1 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)
    assert len((repo.parent / "pytest-args").read_text().splitlines()) == 2


def test_a_side_kept_at_one_head_runs_again_at_another(repo):
    commit(repo, {"calc.py": FIXED, "tests/test_calc.py": FAILS_AT_BASE})
    proof(repo, SLOTS="1", LIMIT="5", SLOW="3")
    base = git(repo, "rev-parse", "HEAD~1")
    head = commit(repo, {"util.py": ""})
    said, line = proof(repo)
    assert "already" not in said
    assert "head exit 0: 2 passed" in said
    assert line == proved.Proved(("tests/test_calc.py",), 1, base, 0, head)
    assert len((repo.parent / "pytest-args").read_text().splitlines()) == 3


PACKAGING = "features/fork/packaging"
FORK_PATCH = """diff --git a/pkg/lib.txt b/pkg/lib.txt
--- a/pkg/lib.txt
+++ b/pkg/lib.txt
@@ -1 +1 @@
-old
+new
diff --git a/pkg/a.test.ts b/pkg/a.test.ts
new file mode 100644
--- /dev/null
+++ b/pkg/a.test.ts
@@ -0,0 +1 @@
+it says new
"""
NO_TEST_PATCH = FORK_PATCH.split("diff --git a/pkg/a.test.ts")[0]


def pkgbuild(tarball, *patches):
    return (
        '_tag="${T3CODE_JSTACK_TAG:-v1}"\n'
        f"_patches=({' '.join(patches)})\n"
        f'source=("up.tar.gz::file://{tarball}" "${{_patches[@]}}")\n'
    )


def forked(repo):
    """The repo with a fork at `origin/main`: its PKGBUILD names a tag, a tarball whose package's
    tests pass only where its `lib.txt` says `new`, and no patch. Returns the tarball."""
    upstream = repo.parent / "up"
    (upstream / "pkg").mkdir(parents=True)
    (upstream / "pkg" / "lib.txt").write_text("old\n")
    (upstream / "pkg" / "check.sh").write_text('test -f "$1" && grep -q new lib.txt\n')
    (upstream / "pkg" / "package.json").write_text('{"scripts": {"test": "sh check.sh"}}\n')
    tarball = repo.parent / "up.tar.gz"
    with tarfile.open(tarball, "w:gz") as made:
        made.add(upstream, arcname="up-1")
    stub = repo.parent / "stub"
    (stub / "vp").write_text('#!/bin/sh\n[ "$1" = i ] || exit 64\n')
    (stub / "vp").chmod(0o755)
    commit(repo, {f"{PACKAGING}/PKGBUILD": pkgbuild(tarball)})
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tarball


def test_a_fork_patch_is_proved_by_its_own_test_failing_over_the_base_s_series(repo):
    """sidebar-home-start-says changed only patch 0030 and the PKGBUILD, with its tests inside
    the patch, and the block said no test changed. It now runs the test the patch adds with the
    head's series, then over the base's, and writes the `fork patches` line."""
    tarball = forked(repo)
    base = git(repo, "rev-parse", "HEAD")
    head = commit(
        repo,
        {
            f"{PACKAGING}/0001-new.patch": FORK_PATCH,
            f"{PACKAGING}/PKGBUILD": pkgbuild(tarball, "0001-new.patch"),
        },
    )
    said, line = proof(repo)
    assert "head exit 0" in said
    assert "base exit 1" in said
    assert (
        f"Proved: pkg/a.test.ts base exit 1 at {base}, head exit 0 at {head}, fork patches\n"
        in said
    )
    assert line == proved.Proved(("pkg/a.test.ts",), 1, base, 0, head, fork=True)


def test_a_fork_patch_that_adds_no_test_is_not_proved(repo):
    tarball = forked(repo)
    commit(
        repo,
        {
            f"{PACKAGING}/0001-new.patch": NO_TEST_PATCH,
            f"{PACKAGING}/PKGBUILD": pkgbuild(tarball, "0001-new.patch"),
        },
    )
    said, line = proof(repo)
    assert said.startswith("no proof: the fork patches it changes add or change no vitest file")
    assert line is None


def test_a_fork_patch_with_a_change_to_other_code_is_no_fork_proof(repo):
    tarball = forked(repo)
    commit(
        repo,
        {
            f"{PACKAGING}/0001-new.patch": FORK_PATCH,
            f"{PACKAGING}/PKGBUILD": pkgbuild(tarball, "0001-new.patch"),
            "util.py": "",
        },
    )
    said, line = proof(repo)
    assert said.startswith("no test changed")
    assert line is None
