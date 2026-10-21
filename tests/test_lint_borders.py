"""`scripts/lint-borders.py [--base <ref>] [--labels a,b] [--hard]`: a warning, as GitHub reads
one, for each tracked path with no owner or two, each path a diff adds outside the feature
layout, and a diff that touches two features with no `cross-cutting` label. It exits 0 with
warnings, and 1 with them under `--hard`. Each test runs the script in a git repo."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "lint-borders.py"
GIT = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def lint(root, *args):
    return subprocess.run(
        [sys.executable, "-I", SCRIPT, *args], cwd=root, capture_output=True, text=True
    )


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=os.environ | GIT)


def write(root, path, text="x\n"):
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)


def feature(root, name, owns=()):
    manifest = {"name": name, "description": f"The {name} feature."}
    write(root, f"features/{name}/feature.json", json.dumps(manifest | {"owns": list(owns)}))


def commit(root):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "change")


@pytest.fixture
def repo(tmp_path):
    """A repo of two features, alpha and beta, with one commit."""
    root = tmp_path / "repo"
    shutil.copytree(REPO / "schemas", root / "schemas")
    for path in ("plugin.json", "pyproject.toml"):
        shutil.copy2(REPO / path, root / path)
    feature(root, "alpha")
    feature(root, "beta")
    write(root, "features/alpha/a.md")
    write(root, "features/beta/b.md")
    git(root, "init", "-q")
    commit(root)
    return root


def warnings(ran):
    assert ran.returncode == 0, ran.stderr
    return [line for line in ran.stdout.splitlines() if line.startswith("::warning")]


def test_this_checkout_prints_no_warning():
    ran = lint(REPO)
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "", "")


def test_a_diff_across_two_features_warns_once_unless_it_is_labelled_cross_cutting(repo):
    write(repo, "features/alpha/a.md", "changed\n")
    write(repo, "features/beta/b.md", "changed\n")
    commit(repo)
    (one,) = warnings(lint(repo, "--base", "HEAD^1"))
    assert one.startswith("::warning file=features/alpha/a.md::")
    assert "alpha, beta" in one and "cross-cutting" in one
    assert warnings(lint(repo, "--base", "HEAD^1", "--labels", "cross-cutting")) == []
    assert warnings(lint(repo, "--base", "HEAD^1", "--labels", "docs,cross-cutting")) == []
    assert len(warnings(lint(repo, "--base", "HEAD^1", "--labels", "docs"))) == 1


def test_a_diff_inside_one_feature_and_the_repos_own_files_does_not_warn(repo):
    write(repo, "features/alpha/a.md", "changed\n")
    write(repo, "features/alpha/new.md")
    write(repo, "scripts/tool.py")
    write(repo, "pyproject.toml", (repo / "pyproject.toml").read_text() + "\n")
    feature(repo, "alpha", owns=["scripts/tool.py"])
    commit(repo)
    assert warnings(lint(repo, "--base", "HEAD^1")) == []


def test_a_new_root_file_warns_once_whether_or_not_a_feature_owns_it(repo):
    write(repo, "stray.md")
    commit(repo)
    (one,) = warnings(lint(repo, "--base", "HEAD^1"))
    assert one.startswith("::warning file=stray.md::")
    assert "no owner" in one and "root" in one
    feature(repo, "alpha", owns=["stray.md"])
    commit(repo)
    (one,) = warnings(lint(repo, "--base", "HEAD^2"))
    assert one.startswith("::warning file=stray.md::")
    assert "no owner" not in one


def test_a_new_file_under_a_root_folder_outside_the_layout_warns_and_infra_does_not(repo):
    write(repo, "src/thing/new.py")
    feature(repo, "alpha", owns=["src/thing/**"])
    write(repo, "Makefile")
    commit(repo)
    (one,) = warnings(lint(repo, "--base", "HEAD^1"))
    assert one.startswith("::warning file=src/thing/new.py::")
    assert "src/" in one


def test_a_path_with_two_owners_warns_with_both_and_no_base_still_reads_ownership(repo):
    feature(repo, "beta", owns=["features/alpha/a.md"])
    commit(repo)
    (one,) = warnings(lint(repo))
    assert one == "::warning file=features/alpha/a.md::owned twice, by alpha and beta"


def test_hard_exits_1_on_a_warning_and_0_with_none(repo):
    assert lint(repo, "--hard").returncode == 0
    write(repo, "stray.md")
    ran = lint(repo, "--hard")
    assert ran.returncode == 1
    assert ran.stdout.startswith("::warning file=stray.md::")


def test_a_base_git_does_not_know_is_refused_with_its_reason(repo):
    ran = lint(repo, "--base", "no-such-ref")
    assert ran.returncode == 2
    assert "no-such-ref" in ran.stderr
