"""The crew skill's generated files: the crewmate regenerates a lock file that a rebase stops on.

The step is `jmerge --remake`, which reads the `Generated:` lines of the notes in the repo's state,
`~/.local/state/home/<main checkout>`. Each test runs the step with a `HOME` of its own, the main
checkout `main`, and the uv cache of the user the tests run as, so `uv lock --offline` still finds
what it needs."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from crew_helpers import GH, STOPPED, PullRequest, asked, git
from crew_helpers import stays as stays_in_the_home
from test_home_merge import uv_cache

UV = """\
#!/bin/sh
if [ "$1 $2" = "run --project" ]; then
    shift 3
    VIRTUAL_ENV={venv}
    PATH="$VIRTUAL_ENV/bin:$PATH"
    export VIRTUAL_ENV PATH
    exec "$@"
fi
exec {uv} "$@"
"""


def notes_of(tmp_path):
    """Where `jmerge` reads the notes of the repo whose main checkout is `main`."""
    return tmp_path / "user" / ".local" / "state" / "home" / "main" / "notes.md"


def venv_of(pr):
    """The venv the stub of `uv run --project` puts first on PATH, with a `python3` of its own."""
    return pr.stub.parent / "jstack-venv"


def stays(pr, about):
    """The step run as `stays` runs it, with the test's own `HOME`. `uv run --project` runs the
    command it is given straight from PATH, since uv would look for its cache in that `HOME`, and
    sets `VIRTUAL_ENV` and puts that venv's bin first on PATH, as uv does."""
    if not (pr.stub / "uv").exists():
        (venv_of(pr) / "bin").mkdir(parents=True)
        (venv_of(pr) / "bin" / "python3").write_text("#!/bin/sh\n")
        (venv_of(pr) / "bin" / "python3").chmod(0o755)
        (pr.stub / "uv").write_text(UV.format(uv=shutil.which("uv"), venv=venv_of(pr)))
        (pr.stub / "uv").chmod(0o755)
    user = pr.stub.parent / "user"
    return stays_in_the_home(
        pr,
        about,
        HOME=str(user),
        JBUS_HOME_DIR=str(user / ".local" / "state" / "home"),
        UV_CACHE_DIR=uv_cache(),
    )


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
    """A pull request and a default branch that each added a dependency and locked it."""

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
        notes_of(tmp_path).parent.mkdir(parents=True)
        notes_of(tmp_path).write_text(f"# notes\n\n- Check command: `true`\n{notes}")
    assert stays(pr, "jmerge --remake") == ["no rebase is stopped here: nothing to make again"]
    assert stays(pr, "mergeable") == [STOPPED, "pyproject.toml", "uv.lock"]
    assert stays(pr, "jmerge --remake") == [
        "resolve these by hand and git add them, then run this again:",
        "pyproject.toml",
    ]
    assert "<<<<<<<" in (pr.work / "uv.lock").read_text()
    (pr.work / "pyproject.toml").write_text(pr.project("ours", "theirs"))
    git(pr.work, "add", "pyproject.toml")
    command = "uv lock --offline" if notes else "uv lock"
    assert stays(pr, "jmerge --remake") == [
        f"made again: uv.lock, by {command} over the base's version"
    ]
    assert stays(pr, "jmerge --remake") == ["nothing is left to resolve: git rebase --continue"]
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
    notes_of(tmp_path).parent.mkdir(parents=True)
    made = "Generated: shared.txt -> echo made from both > shared.txt\n"
    notes_of(tmp_path).write_text(f"# notes\n{made}")
    assert stays(pr, "mergeable") == [STOPPED, "shared.txt"]
    assert stays(pr, "jmerge --remake") == [
        "made again: shared.txt, by echo made from both > shared.txt over the base's version"
    ]
    assert (pr.work / "shared.txt").read_text() == "made from both\n"
    assert git(pr.work, "diff", "--name-only", "--diff-filter=U") == ""


def test_a_generated_file_is_made_outside_the_venv_that_runs_jmerge(tmp_path):
    """The command that makes a generated file finds the tools the worktree's shell finds, not
    the ones in the venv of the `uv run --project` that starts `jmerge --remake`."""
    pr = PullRequest(tmp_path, None, "shared.txt")
    asked(pr, "CONFLICTING")
    notes_of(tmp_path).parent.mkdir(parents=True)
    made = "command -v python3 > shared.txt; echo ${VIRTUAL_ENV-unset} >> shared.txt"
    notes_of(tmp_path).write_text(f"Generated: shared.txt -> {made}\n")
    assert stays(pr, "mergeable") == [STOPPED, "shared.txt"]
    (said,) = stays(pr, "jmerge --remake")
    assert said.startswith("made again: shared.txt, by ")
    found, venv = (pr.work / "shared.txt").read_text().splitlines()
    assert not found.startswith(str(venv_of(pr)))
    assert venv == "unset"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_with_a_line_in_the_notes_a_lock_file_no_line_names_is_resolved_by_hand(tmp_path):
    pr = Locked(tmp_path)
    notes_of(tmp_path).parent.mkdir(parents=True)
    notes_of(tmp_path).write_text("Generated: schema.json -> make schema\n")
    assert stays(pr, "mergeable") == [STOPPED, "pyproject.toml", "uv.lock"]
    assert stays(pr, "jmerge --remake") == [
        "resolve these by hand and git add them, then run this again:",
        "pyproject.toml",
        "uv.lock",
    ]
