"""`jgauge check` and `jgauge proof` start a run in a session of their own, or join one. The crew
and pr-review tests run them through the skills' blocks: these tests drive what those do not."""

import os
import signal
import subprocess

from test_room import BIN


def repo(tmp_path):
    work = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    (work / "tracked").write_text("one\n")
    subprocess.run(["git", "add", "tracked"], cwd=work, check=True)
    return work


def jgauge(tmp_path, work, *args, stdin):
    ran = subprocess.run(
        [str(BIN / "jgauge"), *args],
        cwd=work,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "HOME": str(tmp_path / "home"), "TEST_SLOTS": "2"},
    )
    return ran.stdout.splitlines(), ran.returncode, ran.stderr


def test_the_check_writes_the_worktree_tree_with_an_index_of_its_own(tmp_path):
    work = repo(tmp_path)
    (work / "untracked").write_text("new\n")
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=work, text=True, capture_output=True
    ).stdout
    said, code, _ = jgauge(tmp_path, work, "check", stdin="echo checked\n")
    assert (said[-2:], code) == (["checked", "done: the check exited 0"], 0)
    after = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=work, text=True, capture_output=True
    ).stdout
    assert after == staged == "tracked\n"
    assert sorted(path.name for path in (work / ".git").iterdir() if "index." in path.name) == []
    tree = (work / ".git" / "crew-check" / "tree").read_text().split()
    listed = subprocess.run(
        ["git", "ls-tree", "--name-only", *tree], cwd=work, text=True, capture_output=True
    ).stdout
    assert listed.splitlines() == ["tracked", "untracked"]


def test_a_check_whose_run_dies_while_the_call_waits_is_lost_and_runs_afresh_next(tmp_path):
    work = repo(tmp_path)
    pid_file = work / ".git" / "crew-check" / "pid"
    waiting = subprocess.Popen(
        [str(BIN / "jgauge"), "check", "--wait", "30"],
        cwd=work,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "HOME": str(tmp_path / "home"), "TEST_SLOTS": "2"},
    )
    waiting.stdin.write("sleep 30\n")
    waiting.stdin.close()
    assert waiting.stdout.readline().startswith("started:")
    os.killpg(int(pid_file.read_text()), signal.SIGKILL)
    said = waiting.stdout.read().splitlines()
    assert (said, waiting.wait()) == (
        [
            "lost: the check stopped with no exit code: run this block again,"
            " and it starts the check afresh"
        ],
        0,
    )
    said, code, _ = jgauge(tmp_path, work, "check", stdin="echo again\n")
    assert (said[0].split(":")[0], said[-2:], code) == (
        "started",
        ["again", "done: the check exited 0"],
        0,
    )


def test_a_step_with_no_command_on_stdin_starts_nothing(tmp_path):
    work = repo(tmp_path)
    said, code, err = jgauge(tmp_path, work, "check", stdin="")
    assert (said, code) == ([], 2)
    assert "no command on stdin" in err
    assert not (work / ".git" / "crew-check").exists()
    folder = tmp_path / "review"
    folder.mkdir()
    said, code, err = jgauge(
        tmp_path, work, "proof", "--dir", str(folder), "--kept", "x", stdin="\n"
    )
    assert (said, code, list(folder.iterdir())) == ([], 2, [])


def test_a_repo_with_a_module_named_for_the_stdlib_is_checked_with_the_stdlib(tmp_path):
    work = repo(tmp_path)
    (work / "shutil.py").write_text('raise SystemExit("the repo shadowed the stdlib")\n')
    said, code, _ = jgauge(tmp_path, work, "check", stdin="echo checked\n")
    assert (said[-2:], code) == (["checked", "done: the check exited 0"], 0)
