"""`jbus forget` deletes a file of the homes' state or of the repo's git dir, and refuses any other
path before it deletes anything. The tests run the command as a skill's step does."""

import os
import subprocess

import pytest


@pytest.fixture
def forget(tmp_path):
    """Run `jbus forget` in a repo of its own, with the homes' state at `state`."""
    state, repo = tmp_path / "state", tmp_path / "repo"
    state.mkdir()
    subprocess.run(["git", "init", "-q", repo], check=True)

    def run(*args, cwd=repo):
        ran = subprocess.run(
            ["jbus", "forget", *map(str, args)],
            cwd=cwd,
            env={**os.environ, "JBUS_HOME_DIR": str(state)},
            capture_output=True,
            text=True,
        )
        return ran.returncode, ran.stdout.splitlines(), ran.stderr.splitlines()

    run.state, run.repo, run.outside = state, repo, tmp_path
    return run


def test_it_deletes_files_of_the_state_and_of_the_git_dir_and_prints_each(forget):
    note, record = forget.state / "home" / "off", forget.repo / ".git" / "crew-before-rebase"
    note.parent.mkdir()
    note.write_text("")
    record.write_text("a b c\n")
    assert forget(note, ".git/crew-before-rebase") == (
        0,
        [str(note), ".git/crew-before-rebase"],
        [],
    )
    assert not note.exists() and not record.exists()


def test_a_path_that_is_not_there_is_no_error(forget):
    assert forget(forget.state / "gone", forget.state / "nor-this" / "file") == (0, [], [])


def test_a_path_outside_is_refused_and_nothing_is_deleted(forget):
    kept, inside = forget.outside / "kept.txt", forget.state / "inside"
    kept.write_text("")
    inside.write_text("")
    code, out, err = forget(inside, kept)
    assert (code, out) == (2, [])
    assert err == [
        f"refused: {kept} is not inside the homes' state or this repo's git dir",
        "nothing is deleted",
    ]
    assert kept.exists() and inside.exists()


@pytest.mark.parametrize(
    "given", ["{state}/../kept.txt", "{state}/link/kept.txt", "{state}", "{repo}/kept.txt"]
)
def test_a_dot_dot_a_link_the_root_itself_or_the_worktree_is_outside(forget, given):
    (forget.outside / "kept.txt").write_text("")
    (forget.repo / "kept.txt").write_text("")
    (forget.state / "link").symlink_to(forget.outside)
    path = given.format(state=forget.state, repo=forget.repo)
    code, _, err = forget("--dir", path)
    assert (code, err[0]) == (
        2,
        f"refused: {path} is not inside the homes' state or this repo's git dir",
    )
    assert (forget.outside / "kept.txt").exists() and (forget.repo / "kept.txt").exists()


def test_a_link_inside_is_removed_and_not_what_it_points_to(forget):
    (forget.outside / "kept.txt").write_text("")
    (forget.state / "link").symlink_to(forget.outside / "kept.txt")
    assert forget(forget.state / "link")[0] == 0
    assert (forget.outside / "kept.txt").exists() and not (forget.state / "link").is_symlink()


def test_a_directory_goes_only_with_dir_and_only_when_empty(forget):
    scope = forget.state / "scope"
    (scope / "plan.md").parent.mkdir()
    (scope / "plan.md").write_text("")
    code, _, err = forget(scope)
    assert (code, err[0]) == (2, f"refused: {scope} is a directory, and only --dir removes one")
    code, out, err = forget("--dir", scope)
    assert (code, out) == (1, []) and err[0].startswith(f"not removed: {scope}: ")
    assert forget("--dir", scope / "plan.md", scope) == (
        0,
        [str(scope / "plan.md"), str(scope)],
        [],
    )
    assert not scope.exists()


def test_outside_a_repo_only_the_state_is_inside(forget):
    (forget.state / "x").write_text("")
    assert forget(forget.state / "x", cwd=forget.outside)[0] == 0
