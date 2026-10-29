"""The borders check's rule for the view's kept shots (`features/jbus/scripts/kept_shots.py`): a
pull request changes a kept shot only where it changes nothing else, which is the shots row's.

Each test runs the script as borders.yml does, `--base HEAD^1`, in a repo made here that holds the
script and `jbus/shots.py` where the repo has them, over a commit that changes the files a pull
request would."""

import shutil
import subprocess
import sys

import pytest

from jbus import shots
from testing.paths import REPO

SCRIPT = "features/jbus/scripts/kept_shots.py"
RULE = "features/jbus/src/jbus/shots.py"
SHOT = f"{shots.KEPT}/all-390-dark.png"
DRAWN_BY = f"{shots.KEPT}/browser.txt"
CODE = "features/jbus/src/jbus/view/page.js"


def git(repo, *words):
    subprocess.run(["git", "-C", repo, *words], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    made = tmp_path / "repo"
    for path in (SCRIPT, RULE):
        (made / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / path, made / path)
    for path, text in ((SHOT, "old shot"), (DRAWN_BY, "Chrome 1\n"), (CODE, "old code")):
        (made / path).parent.mkdir(parents=True, exist_ok=True)
        (made / path).write_text(text)
    git(made, "init", "-q")
    git(made, "add", ".")
    git(made, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "main")
    return made


def pull(repo, changes, gone=()):
    """Commit `changes`, each path's new text, and delete `gone`, as one pull request's diff, and
    run the borders check's step over it."""
    for path, text in changes.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    for path in gone:
        (repo / path).unlink()
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "pull request")
    return subprocess.run(
        [sys.executable, "-I", repo / SCRIPT, "--base", "HEAD^1"],
        capture_output=True,
        text=True,
        cwd=repo,
    )


def test_a_feature_that_changes_a_kept_shot_fails_with_a_line_for_each_other_file(repo):
    ran = pull(repo, {SHOT: "new shot", CODE: "new code", "README.md": "more"})
    assert ran.returncode == 1
    errors = [line for line in ran.stdout.splitlines() if line.startswith("::error ")]
    assert [line.split("::")[1] for line in errors] == [
        "error file=README.md",
        f"error file={CODE}",
    ]
    assert all("the shots row redraws them" in line for line in errors)


@pytest.mark.parametrize(
    "changes, gone",
    [
        ({DRAWN_BY: "Chrome 2\n", CODE: "new code"}, ()),
        ({CODE: "new code"}, (SHOT,)),
        ({CODE: "new code", f"{shots.KEPT}/new-1440-light.png": "a new shot"}, ()),
    ],
    ids=["its browser.txt", "a shot deleted", "a shot added"],
)
def test_any_change_under_the_kept_shots_beside_another_file_fails(repo, changes, gone):
    assert pull(repo, changes, gone).returncode == 1


def test_a_rename_out_of_the_kept_shots_fails(repo):
    (repo / "elsewhere").mkdir()
    shutil.move(repo / SHOT, repo / "elsewhere" / "all-390-dark.png")
    assert pull(repo, {}).returncode == 1


def test_the_shots_rows_pull_request_changes_only_kept_shots_and_passes(repo):
    ran = pull(repo, {SHOT: "redrawn", DRAWN_BY: "Chrome 2\n"})
    assert (ran.returncode, ran.stdout) == (0, "")


def test_a_feature_that_leaves_the_shots_as_main_has_them_passes(repo):
    ran = pull(repo, {CODE: "new code"})
    assert (ran.returncode, ran.stdout) == (0, "")


def test_a_base_git_cannot_read_ends_2(repo):
    ran = subprocess.run(
        [sys.executable, "-I", repo / SCRIPT, "--base", "no-such-commit"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 2
    assert "git could not read the diff from no-such-commit" in ran.stdout
