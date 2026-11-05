"""A green pull request whose check main moved past merges on that existing check when its
files overlap none of the files main changed since the check started and its head merges
cleanly over today's main (`jmerge.cli.Repo.over_main`): GitHub is asked for no update of its
branch, and no check runs again. The fast guards run on its tree merged over main first
(`test_jmerge_cli_merged_tree.py`), and hold it when the two clash. A pull request that shares
a file with main's changes goes through the one-at-a-time line (`test_jmerge_in_line.py`). A
repo with no guards runs nothing on the merged tree, and merges on the existing check alike.

The tests run the command against a real origin and a fake `gh` (`test_jmerge_fresh.Kitchen`),
with GitHub's strict "up to date" rule off on main, as ruleset 25665226 has it since
2026-11-04."""

import pytest

from jmerge import ready, treeguards
from test_jmerge_cli_merged_tree import MAKEFILE, fails, runs
from test_jmerge_fresh import LINES, Kitchen, asked, url


@pytest.fixture
def kitchen(tmp_path):
    ran = tmp_path / "guards-ran"
    made = Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES, "Makefile": MAKEFILE.format(ran=ran)})
    (made.home.state / treeguards.NAME).write_text("make -s guards\n")
    made.ran = ran
    return made


def test_existing_check_with_no_overlap_merges_with_no_update(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"a.txt": LINES + "main\n"})
    (said,) = kitchen.run()
    assert said.startswith(f"merged 7 two {kitchen.tip()} ")
    assert f"the guards passed on its tree merged over main at {tip[:12]} in " in said
    assert kitchen.updates() == []
    assert runs(kitchen) == 1
    assert kitchen.at_main("a.txt").endswith("main")
    assert kitchen.at_main("b.txt").startswith("ours")


def test_existing_check_with_overlap_goes_through_the_line(kitchen):
    """#7 changes a.txt's first line and main its last: the two merge cleanly, but a file they
    share is one main changed under the check, so GitHub merges main into the branch."""
    kitchen.crew("two", 7, {"a.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"a.txt": LINES.replace("5\n", "five\n")})
    tip = kitchen.on_main({"a.txt": LINES + "main\n"})
    first, second = kitchen.run()
    assert first == asked(7, tip)
    assert second == f"wait 8 {url(8)}: " + ready.IN_LINE.format(number=7, base="main")
    assert kitchen.updates() == ["7"]
    assert kitchen.calls() == []
    assert runs(kitchen) == 0


def test_existing_check_with_no_overlap_merges_beside_one_in_the_line(kitchen):
    """The line holds only those that overlap: #8 merges on its check while #7 waits for its
    check at the head GitHub made."""
    kitchen.crew("two", 7, {"a.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"b.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"a.txt": LINES + "main\n"})
    first, second = kitchen.run()
    assert first == asked(7, tip)
    assert second.startswith("merged 8 three ")
    assert kitchen.updates() == ["7"]


def test_existing_check_with_a_clean_merge_that_github_refuses_waits(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.on_main({"a.txt": LINES + "main\n"})
    (kitchen.home.stub / "merge-refused").touch()
    (said,) = kitchen.run()
    assert said.startswith(f"wait 7 {url(7)}: {ready.MERGE_FAILED}: ")
    assert "not mergeable" in said
    assert kitchen.updates() == []


def test_existing_check_on_a_merged_tree_that_fails_the_guards_is_held(kitchen):
    """#7 adds `mig/v007_two.txt` and main took `mig/v007_one.txt` after #7's check: no file is
    shared, and the two merge cleanly, but their tree has two v007 files."""
    kitchen.crew("two", 7, {"mig/v007_two.txt": "two\n"})
    tip = kitchen.on_main({"mig/v007_one.txt": "one\n"})
    (said,) = kitchen.run()
    assert said == fails(7, tip)
    assert kitchen.calls() == []
    assert kitchen.updates() == []


def test_existing_check_in_a_repo_with_no_guards_merges_with_no_update(kitchen):
    """With no `merged-tree-guards` file, nothing runs on the merged tree, and a pull request
    that overlaps none of main's changes still merges on its existing check: no update of its
    branch, and no rerun (Josh, 2026-11-05: "we don't need every pr to be up to date")."""
    (kitchen.home.state / treeguards.NAME).unlink()
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.on_main({"a.txt": LINES + "main\n"})
    (said,) = kitchen.run()
    assert said.startswith(f"merged 7 two {kitchen.tip()} ")
    assert kitchen.updates() == []
    assert runs(kitchen) == 0
    assert kitchen.at_main("b.txt").startswith("ours")


def test_existing_check_in_a_repo_with_no_guards_and_an_overlap_goes_through_the_line(kitchen):
    (kitchen.home.state / treeguards.NAME).unlink()
    kitchen.crew("two", 7, {"a.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"a.txt": LINES + "main\n"})
    assert kitchen.run() == [asked(7, tip)]
    assert kitchen.updates() == ["7"]
