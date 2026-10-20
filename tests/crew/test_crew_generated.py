"""The crew skill's generated files: a lock file a rebase stops on is made again."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from crew.helpers import GH, STOPPED, PullRequest, asked, git, stays

PROJECT = """\
[project]
name = "app"
version = "0"
requires-python = ">=3.12"
dependencies = [
{}]

[tool.uv]
package = false

[tool.uv.sources]
{}"""


SOURCE = '{0} = {{ path = "{0}", package = false }}\n'


LIBRARY = '[project]\nname = "{}"\nversion = "1"\nrequires-python = ">=3.12"\n'


class Locked(PullRequest):
    """A pull request and a default branch that each added a dependency, and locked it."""

    def __init__(self, tmp_path):
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "gh").write_text(GH)
        (self.stub / "gh").chmod(0o755)
        origin, other, main = tmp_path / "origin.git", tmp_path / "other", tmp_path / "main"
        self.work = tmp_path / "trees" / "a-task"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(other))
        for name in ("base", "core", "ours", "theirs"):
            (other / name).mkdir()
            (other / name / "pyproject.toml").write_text(LIBRARY.format(name))
        self.depend(other, "start")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(tmp_path, "clone", "-q", str(origin), str(main))
        git(main, "worktree", "add", "-q", "-b", "a-task", str(self.work))
        self.git_dir = Path(git(self.work, "rev-parse", "--absolute-git-dir"))
        self.depend(self.work, "the task", "ours")
        git(self.work, "push", "-q", "-u", "origin", "a-task")
        self.depend(other, "theirs", "theirs")
        git(other, "push", "-q", "origin", "HEAD:main")
        asked(self, "CONFLICTING")

    @staticmethod
    def project(*names):
        names = ("base", "core", *names)
        listed = "".join(f'    "{name}",\n' for name in names)
        return PROJECT.format(listed, "".join(SOURCE.format(name) for name in names))

    def depend(self, repo, message, *names):
        (repo / "pyproject.toml").write_text(self.project(*names))
        subprocess.run(["uv", "lock", "--offline"], cwd=repo, check=True, capture_output=True)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
@pytest.mark.parametrize("notes", [None, "- Generated: `uv.lock` -> `uv lock --offline`\n"])
def test_a_lock_file_a_rebase_stops_on_is_made_again_from_both_sides(notes, tmp_path):
    pr = Locked(tmp_path)
    if notes:
        (tmp_path / "home").mkdir()
        (tmp_path / "home" / "notes.md").write_text(f"# notes\n\n- Check command: `true`\n{notes}")
    assert stays(pr, "Generated:") == ["no rebase is stopped here: nothing to make again"]
    assert stays(pr, "mergeable") == [STOPPED, "pyproject.toml", "uv.lock"]
    assert stays(pr, "Generated:") == [
        "resolve these by hand and git add them, then run this again:",
        "pyproject.toml",
    ]
    assert "<<<<<<<" in (pr.work / "uv.lock").read_text()
    (pr.work / "pyproject.toml").write_text(pr.project("ours", "theirs"))
    git(pr.work, "add", "pyproject.toml")
    command = "uv lock --offline" if notes else "uv lock"
    assert stays(pr, "Generated:") == [f"made again: uv.lock, by {command} over the base's version"]
    assert stays(pr, "Generated:") == ["nothing is left to resolve: git rebase --continue"]
    git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    assert not pr.rebasing()

    lock = (pr.work / "uv.lock").read_text()
    assert "<<<<<<<" not in lock
    assert 'name = "ours"' in lock
    assert 'name = "theirs"' in lock
    synced = subprocess.run(
        ["uv", "sync", "--locked", "--offline"],
        cwd=pr.work,
        capture_output=True,
        text=True,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(tmp_path / "venv")},
    )
    assert synced.returncode == 0, synced.stderr
    assert git(pr.work, "status", "--porcelain") == ""
    assert stays(pr, "Kept:") == ["Kept: every line, in pyproject.toml uv.lock"]


def test_a_file_the_notes_say_a_command_writes_is_made_by_that_command(tmp_path):
    pr = PullRequest(tmp_path, None, "shared.txt")
    asked(pr, "CONFLICTING")
    (tmp_path / "home").mkdir()
    made = "Generated: shared.txt -> echo made from both > shared.txt\n"
    (tmp_path / "home" / "notes.md").write_text(f"# notes\n{made}")
    assert stays(pr, "mergeable") == [STOPPED, "shared.txt"]
    assert stays(pr, "Generated:") == [
        "made again: shared.txt, by echo made from both > shared.txt over the base's version"
    ]
    assert (pr.work / "shared.txt").read_text() == "made from both\n"
    assert git(pr.work, "diff", "--name-only", "--diff-filter=U") == ""


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_with_a_line_in_the_notes_a_lock_file_no_line_names_is_resolved_by_hand(tmp_path):
    pr = Locked(tmp_path)
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "notes.md").write_text("Generated: schema.json -> make schema\n")
    assert stays(pr, "mergeable") == [STOPPED, "pyproject.toml", "uv.lock"]
    assert stays(pr, "Generated:") == [
        "resolve these by hand and git add them, then run this again:",
        "pyproject.toml",
        "uv.lock",
    ]
