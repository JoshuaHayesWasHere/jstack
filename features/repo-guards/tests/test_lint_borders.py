"""`scripts/lint-borders.py [--base <ref>] [--labels a,b] [--hard]` runs the repo standard's
borders guard from the checkout's `.repo-standard.yml`, and prints warnings that GitHub reads as
annotations. It warns for each tracked path with no owner or with two owners, for each tracked path
outside the feature layout and the repo's own paths, and for a manifest that breaks the schema. It
also warns for a diff that touches two features with no `cross-cutting` label. It exits 0 when it
warns, and under `--hard` it exits 1 when it warns. It exits 2 with no config to read. Each test
runs the script in a git repo with jstack's schemas and jstack's `.repo-standard.yml`."""

import json
import os
import shutil
import subprocess
import sys

import pytest

from repo_standard.config import load
from testing.paths import REPO

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


def feature(root, name, **more):
    manifest = {"$schema": "../../schemas/feature.schema.json", "name": name}
    manifest["description"] = f"The {name} feature."
    write(root, f"features/{name}/feature.json", json.dumps(manifest | more))


def commit(root):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "change")


@pytest.fixture
def repo(tmp_path):
    """A repo of two features, alpha and beta, with one commit."""
    root = tmp_path / "repo"
    shutil.copytree(REPO / "schemas", root / "schemas")
    for path in ("plugin.json", "pyproject.toml", ".repo-standard.yml"):
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


def hard(root, *args):
    """What `--hard` exits with, and the files its warnings name."""
    ran = lint(root, "--hard", *args)
    named = [line.split("::")[1].removeprefix("warning file=") for line in ran.stdout.splitlines()]
    return ran.returncode, named


def test_a_diff_across_two_features_fails_hard_unless_it_is_labelled_cross_cutting(repo):
    write(repo, "features/alpha/a.md", "changed\n")
    write(repo, "features/beta/b.md", "changed\n")
    commit(repo)
    (one,) = warnings(lint(repo, "--base", "HEAD^1"))
    assert one.startswith("::warning file=features/alpha/a.md::")
    assert "alpha, beta" in one and "cross-cutting" in one
    assert hard(repo, "--base", "HEAD^1") == (1, ["features/alpha/a.md"])
    assert hard(repo, "--base", "HEAD^1", "--labels", "docs") == (1, ["features/alpha/a.md"])
    assert hard(repo, "--base", "HEAD^1", "--labels", "cross-cutting") == (0, [])
    assert hard(repo, "--base", "HEAD^1", "--labels", "docs,cross-cutting") == (0, [])


def test_a_diff_inside_one_feature_and_the_repos_own_files_passes_hard(repo):
    write(repo, "features/alpha/a.md", "changed\n")
    write(repo, "features/alpha/new.md")
    write(repo, "pyproject.toml", (repo / "pyproject.toml").read_text() + "\n")
    write(repo, "Makefile")
    commit(repo)
    assert hard(repo, "--base", "HEAD^1") == (0, [])


def test_a_root_file_fails_hard_with_or_without_a_base(repo):
    write(repo, "stray.md")
    commit(repo)
    outside, unowned = warnings(lint(repo, "--base", "HEAD^1"))
    assert unowned == "::warning file=stray.md::no owner"
    assert outside.startswith("::warning file=stray.md::") and "at the root" in outside
    assert hard(repo, "--base", "HEAD^1") == (1, ["stray.md", "stray.md"])
    assert hard(repo) == (1, ["stray.md", "stray.md"])


def test_a_file_under_a_root_folder_outside_the_layout_fails_hard(repo):
    write(repo, "src/thing/new.py")
    commit(repo)
    outside, unowned = warnings(lint(repo))
    assert unowned == "::warning file=src/thing/new.py::no owner"
    assert outside.startswith("::warning file=src/thing/new.py::") and "under src/" in outside
    assert hard(repo) == (1, ["src/thing/new.py", "src/thing/new.py"])


def test_an_unowned_file_inside_the_layout_fails_hard(repo):
    write(repo, "scripts/tool.py")
    commit(repo)
    (one,) = warnings(lint(repo))
    assert one == "::warning file=scripts/tool.py::no owner"
    assert hard(repo) == (1, ["scripts/tool.py"])


def test_a_manifest_with_owns_fails_hard(repo):
    feature(repo, "alpha", owns=["stray.md"])
    (one,) = warnings(lint(repo))
    assert one.startswith("::warning file=features/alpha/feature.json::")
    assert one.endswith("/: has owns, which the schema does not allow")
    assert hard(repo) == (1, ["features/alpha/feature.json"])


def test_the_configs_owners_are_the_generators():
    sys.path.insert(0, str(REPO / "scripts"))
    from jtrees.crawl import REPO_OWNERS

    owners = load(REPO).owners
    assert {group: set(globs) for group, globs in owners.items()} == {
        group: set(globs) for group, globs in REPO_OWNERS.items()
    }


def test_jstack_itself_passes_hard():
    assert hard(REPO) == (0, [])


def test_a_checkout_with_no_config_is_refused(repo):
    (repo / ".repo-standard.yml").unlink()
    ran = lint(repo, "--hard")
    assert ran.returncode == 2
    assert ".repo-standard.yml" in ran.stderr


def test_a_base_git_does_not_know_is_refused_with_its_reason(repo):
    ran = lint(repo, "--base", "no-such-ref")
    assert ran.returncode == 2
    assert "no-such-ref" in ran.stderr
