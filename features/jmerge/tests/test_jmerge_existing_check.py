"""A green pull request whose check main moved past merges on that existing check when its head
merges cleanly over today's main (`jmerge.cli.Repo.over_main`): GitHub is asked for no update of
its branch, no check runs again, and nothing runs on its merged tree (Josh, 2026-11-05: "we
don't need every pr to be up to date"). One that shares a file with main's changes merges alike
(`test_jmerge_over_main.py`).

The tests run the command against a real origin and a fake `gh` (`test_jmerge_fresh.Kitchen`),
with GitHub's strict "up to date" rule off on main, as ruleset 25665226 has it since
2026-11-04."""

import pytest

from jmerge import ready
from test_jmerge_fresh import LINES, Kitchen, url


@pytest.fixture
def kitchen(tmp_path):
    return Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES})


def test_existing_check_with_no_overlap_merges_with_no_update(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.on_main({"a.txt": LINES + "main\n"})
    (said,) = kitchen.run()
    assert said.startswith(f"merged 7 two {kitchen.tip()} ")
    assert kitchen.updates() == []
    assert kitchen.at_main("a.txt").endswith("main")
    assert kitchen.at_main("b.txt").startswith("ours")


def test_existing_check_with_a_clean_merge_that_github_refuses_waits(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.on_main({"a.txt": LINES + "main\n"})
    (kitchen.home.stub / "merge-refused").touch()
    (said,) = kitchen.run()
    assert said.startswith(f"wait 7 {url(7)}: {ready.MERGE_FAILED}: ")
    assert "not mergeable" in said
    assert kitchen.updates() == []
