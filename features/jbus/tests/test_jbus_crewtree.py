"""`jbus.crewtree` makes a crew's worktree before its launch, or says why it cannot, and launches
nothing then. A dropped launch is tried again only into the worktree it left as it was. The tests
run the real pass against the kitchen's fakes and its real git."""

import json
import os
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from crew_branches import git_said
from test_jbus_kitchen import NOW, approved

GATE = "condition alpha: the crew's worktree could not be made"
THERE = "condition alpha: branch alpha is there with no launch record"


def tree_of(kitchen, slug="alpha"):
    return Path(os.environ["T3CODE_HOME"]) / "worktrees" / kitchen.checkout.name / slug


def branches(kitchen, slug="alpha"):
    return git_said(kitchen, "branch", "--list", "--format=%(refname)", slug)


def dropped(kitchen):
    """Launch alpha with a connection that drops before any reply: T3 Code made no thread, and
    the next pass tries it once more."""
    approved(kitchen, "alpha")
    kitchen.t3.lose = "before"
    kitchen.poll()
    kitchen.t3.lose = None
    assert len(kitchen.t3.launches) == 1 and tree_of(kitchen).is_dir()


def test_a_retry_whose_branch_moved_is_a_gate_and_launches_nothing(kitchen):
    dropped(kitchen)
    (tree_of(kitchen) / "notes.md").write_text("a note\n")
    git_said(kitchen, "-C", str(tree_of(kitchen)), "add", "notes.md")
    git_said(kitchen, "-C", str(tree_of(kitchen)), "commit", "-q", "-m", "a note")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(kitchen.t3.launches) == 1
    assert kitchen.lines("condition") == [THERE]


def test_a_retry_whose_worktree_is_gone_is_a_gate_and_launches_nothing(kitchen):
    dropped(kitchen)
    git_said(kitchen, "worktree", "remove", "--force", str(tree_of(kitchen)))
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(kitchen.t3.launches) == 1
    assert kitchen.lines("condition") == [THERE]


def test_a_folder_in_the_worktrees_place_is_a_gate_and_leaves_no_branch(kitchen):
    tree_of(kitchen).mkdir(parents=True)
    (tree_of(kitchen) / "left.txt").write_text("not a worktree\n")
    approved(kitchen, "alpha")
    kitchen.poll()
    assert kitchen.t3.launches == [] and kitchen.lines("condition") == [GATE]
    assert branches(kitchen) == ""
    assert (tree_of(kitchen) / "left.txt").read_text() == "not a worktree\n"


def test_settings_jroles_refuses_are_a_gate_and_leave_no_worktree(kitchen, tmp_path, monkeypatch):
    """`~/.claude/settings.json` whose permissions are no object: `jroles` cannot build the
    crew's settings from it."""
    home = tmp_path / "user"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(json.dumps({"permissions": ["Bash"]}))
    monkeypatch.setenv("HOME", str(home))
    approved(kitchen, "alpha")
    kitchen.poll()
    assert kitchen.t3.launches == [] and kitchen.lines("condition") == [GATE]
    assert branches(kitchen) == "" and not tree_of(kitchen).exists()


@pytest.mark.parametrize("tracked", [".claude/settings.json", ".claude/.gitignore"])
def test_a_base_that_tracks_one_of_the_two_files_is_a_gate(kitchen, tracked):
    """A project that commits its own `.claude/settings.json` would see jbus's file as a change
    in the crew's worktree, which the crew could commit: jbus launches no crew there."""
    clone = kitchen.root / "elsewhere"
    git_said(kitchen, "clone", "-q", str(kitchen.origin), str(clone))
    (clone / tracked).parent.mkdir(parents=True, exist_ok=True)
    (clone / tracked).write_text("the project's own\n")
    git_said(kitchen, "-C", str(clone), "add", "-f", tracked)
    git_said(kitchen, "-C", str(clone), "commit", "-q", "-m", "its own settings")
    git_said(kitchen, "-C", str(clone), "push", "-q", "origin", "main")
    shutil.rmtree(clone)
    approved(kitchen, "alpha")
    kitchen.poll()
    assert kitchen.t3.launches == [] and kitchen.lines("condition") == [GATE]
    assert branches(kitchen) == "" and not tree_of(kitchen).exists()
