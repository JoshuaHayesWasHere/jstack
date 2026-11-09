"""`repo-standard green`, `repo_standard.green`, lets only a tree that is green main deploy.

Each case is a clone of a bare origin, and a `gh` on the path stands in for GitHub: it answers the
artifacts lookup, a run by its id, and the list of check.yml's runs from files the case writes,
and fails where the case gives it no answer. The cases run the command's entry point and read
its exit code and what it printed.
"""

import json
import os
import shutil
import subprocess

import pytest

from repo_standard import green as green_module
from repo_standard.cli import main

STUB = """\
#!/usr/bin/env bash
path=$2
dir=$GH_STUB
case $path in
*actions/artifacts\\?*) file=artifacts.json ;;
*actions/workflows/check.yml/runs\\?*) file=runs.json ;;
*actions/runs/*) file=run-${path##*/}.json ;;
*) file=none ;;
esac
echo "$path" >> "$dir/asked"
[ -f "$dir/$file" ] || { echo "HTTP 502: no answer for $path" >&2; exit 1; }
cat "$dir/$file"
"""
REPO_ID = 7


def git(root, *args):
    command = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    root = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(root)], check=True)
    git(root, "checkout", "-q", "-b", "main")
    (root / "app.txt").write_text("one\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "one")
    git(root, "push", "-q", "origin", "main")
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "gh").write_text(STUB)
    (stub / "gh").chmod(0o755)
    answers = tmp_path / "answers"
    answers.mkdir()
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GH_STUB", str(answers))
    return root, answers


def answer(answers, name, body):
    (answers / name).write_text(json.dumps(body))


def no_marker_no_run(answers):
    answer(answers, "artifacts.json", {"artifacts": []})
    answer(answers, "runs.json", {"workflow_runs": []})


def marker(answers, root, *, expired=False):
    tree = git(root, "rev-parse", "HEAD^{tree}")
    run = {"id": 41, "repository_id": REPO_ID, "head_repository_id": REPO_ID}
    found = {"name": f"green-tree-{tree}", "expired": expired, "workflow_run": run}
    answer(answers, "artifacts.json", {"artifacts": [found]})
    answer(
        answers,
        "run-41.json",
        {
            "repository": {"id": REPO_ID},
            "head_repository": {"id": REPO_ID},
            "conclusion": "success",
            "path": ".github/workflows/check.yml",
            "html_url": "https://github.com/o/r/actions/runs/41",
        },
    )


def main_run(answers, root, conclusion="success"):
    run = {
        "head_sha": git(root, "rev-parse", "HEAD"),
        "head_branch": "main",
        "event": "push",
        "conclusion": conclusion,
        "path": ".github/workflows/check.yml",
        "html_url": "https://github.com/o/r/actions/runs/52",
    }
    answer(answers, "runs.json", {"workflow_runs": [run]})


def green(root, capsys):
    code = main(["green", "--root", str(root)])
    return code, capsys.readouterr().out


def test_a_clean_checkout_of_origins_main_whose_tree_left_a_marker_is_green(checkout, capsys):
    root, answers = checkout
    marker(answers, root)
    code, out = green(root, capsys)
    assert code == 0, out
    assert "is origin's main, clean, and its tree passed in" in out
    assert "actions/runs/41" in out


def test_a_green_tree_whose_marker_expired_passes_through_mains_push_run(checkout, capsys):
    root, answers = checkout
    marker(answers, root, expired=True)
    main_run(answers, root)
    code, out = green(root, capsys)
    assert code == 0, out
    assert "actions/runs/52" in out


def test_a_tree_no_run_passed_is_refused(checkout, capsys):
    root, answers = checkout
    no_marker_no_run(answers)
    main_run(answers, root, conclusion="failure")
    code, out = green(root, capsys)
    assert code == 1, out
    tree = git(root, "rev-parse", "HEAD^{tree}")
    assert f"refused: tree {tree[:12]} has not passed the check" in out
    assert f"green-tree-{tree}" in out


def test_a_branch_is_refused_as_not_origins_main(checkout, capsys):
    root, answers = checkout
    marker(answers, root)
    git(root, "checkout", "-q", "-b", "feature")
    (root / "app.txt").write_text("two\n")
    git(root, "commit", "-qam", "two")
    code, out = green(root, capsys)
    assert code == 1, out
    assert "is not origin's main" in out


def test_a_dirty_checkout_is_refused(checkout, capsys):
    root, answers = checkout
    marker(answers, root)
    (root / "app.txt").write_text("edited\n")
    code, out = green(root, capsys)
    assert code == 1, out
    assert "refused: the checkout is not clean (1 paths changed)" in out


def test_a_head_behind_origins_main_now_is_refused_though_its_origin_main_is_stale(
    checkout, capsys
):
    root, answers = checkout
    marker(answers, root)
    git(root, "commit", "-q", "--allow-empty", "-m", "later")
    git(root, "push", "-q", "origin", "main")
    git(root, "reset", "-q", "--hard", "HEAD~1")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    code, out = green(root, capsys)
    assert code == 1, out
    assert "is behind origin's main" in out


def test_no_answer_from_github_exits_2(checkout, capsys):
    root, _ = checkout
    code, out = green(root, capsys)
    assert code == 2, out
    assert "cannot ask: gh api actions/artifacts?name=green-tree-" in out


def test_a_refusal_holds_when_github_gives_no_answer(checkout, capsys):
    root, _ = checkout
    (root / "app.txt").write_text("edited\n")
    code, out = green(root, capsys)
    assert code == 1, out
    assert "refused: the checkout is not clean" in out
    assert "note: no answer: gh api" in out


def test_an_origin_that_cannot_be_reached_exits_2(checkout, capsys):
    root, answers = checkout
    marker(answers, root)
    git(root, "remote", "set-url", "origin", str(root.parent / "gone.git"))
    code, out = green(root, capsys)
    assert code == 2, out
    assert "cannot ask: git ls-remote origin:" in out


def test_an_origin_that_does_not_answer_in_time_exits_2(checkout, capsys, monkeypatch):
    root, answers = checkout
    marker(answers, root)
    git(root, "remote", "set-url", "origin", "ssh://git.invalid/repo.git")
    monkeypatch.setenv("GIT_SSH_COMMAND", "sleep 5; :")
    monkeypatch.setattr(green_module, "ASK_SECONDS", 0.5)
    code, out = green(root, capsys)
    assert code == 2, out
    assert "cannot ask: git ls-remote origin took over 0.5s" in out


def test_an_origin_with_no_main_is_refused(checkout, capsys):
    root, answers = checkout
    marker(answers, root)
    other = root.parent / "trunk.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "trunk", str(other)], check=True)
    git(root, "remote", "set-url", "origin", str(other))
    git(root, "push", "-q", "origin", "main:trunk")
    code, out = green(root, capsys)
    assert code == 1, out
    assert "refused: origin has no main: push main first" in out


def test_a_folder_that_is_no_git_checkout_exits_2(tmp_path, capsys):
    code = main(["green", "--root", str(tmp_path)])
    said = capsys.readouterr()
    assert code == 2
    assert "repo_standard green: git status --porcelain:" in said.err


def test_no_gh_on_the_path_exits_2(checkout, capsys, monkeypatch):
    root, _ = checkout
    only = root.parent / "only-git"
    only.mkdir()
    (only / "git").symlink_to(shutil.which("git"))
    monkeypatch.setenv("PATH", str(only))
    code, out = green(root, capsys)
    assert code == 2, out
    assert "cannot ask: gh api actions/artifacts?name=green-tree-" in out


@pytest.mark.parametrize(
    ("body", "said"),
    [("not json", "not JSON"), ("{}", "GitHub's answer has no 'artifacts'")],
)
def test_an_answer_github_did_not_give_in_its_shape_exits_2(checkout, capsys, body, said):
    root, answers = checkout
    (answers / "artifacts.json").write_text(body)
    code, out = green(root, capsys)
    assert code == 2, out
    assert said in out
