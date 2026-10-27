"""The crew labels its own pull request `cross-cutting` when it opens it: the block under the base
runs the repo's borders check over the diff from the base, and a diff that touches two features
opens with the label, which the borders check asks for."""

import json
import os
import shutil
import subprocess

import pytest

from crew_helpers import block, git
from testing.paths import REPO


def write(root, path, text="x\n"):
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)


def feature(root, name):
    manifest = {"$schema": "../../schemas/feature.schema.json", "name": name}
    write(root, f"features/{name}/feature.json", json.dumps(manifest | {"description": name}))


@pytest.fixture
def work(tmp_path):
    """A clone of a repo of two features, alpha and beta, on a branch `task` off `main`, with
    the repo's own borders check."""
    origin, root = tmp_path / "origin.git", tmp_path / "work"
    shutil.copytree(REPO / "schemas", root / "schemas")
    shutil.copytree(REPO / "scripts" / "jtrees", root / "scripts" / "jtrees")
    for path in ("plugin.json", "pyproject.toml", "scripts/lint-borders.py"):
        shutil.copy2(REPO / path, root / path)
    for name in ("alpha", "beta"):
        feature(root, name)
        write(root, f"features/{name}/{name}.md")
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "origin", "main")
    git(root, "switch", "-q", "-c", "task")
    return root


def label(root, *changed):
    for path in changed:
        write(root, path, "changed\n")
    git(root, "commit", "-q", "-am", "change")
    script = block("Do the task", "label it cross-cutting").replace("<branch>", "main")
    ran = subprocess.run(
        ["sh", "-c", script], capture_output=True, text=True, cwd=root, env=os.environ, check=True
    )
    (line,) = ran.stdout.splitlines()
    return line


def test_a_diff_that_touches_two_features_opens_with_the_cross_cutting_label(work):
    said = label(work, "features/alpha/alpha.md", "features/beta/beta.md")
    assert said == "label cross-cutting: the diff touches two features"


def test_a_diff_that_touches_one_feature_opens_with_no_label(work):
    said = label(work, "features/alpha/alpha.md")
    assert said == "no label: the diff touches one feature at most"


def test_a_repo_with_no_borders_check_opens_with_no_label(work):
    (work / "scripts" / "lint-borders.py").unlink()
    said = label(work, "features/alpha/alpha.md", "features/beta/beta.md")
    assert said == "no label: this repo has no scripts/lint-borders.py"
