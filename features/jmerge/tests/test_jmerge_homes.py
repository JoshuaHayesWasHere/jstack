"""jbus runs `jmerge` with no `--home`, and it is the only merger: it merges for every home of the
repo, whatever the repo's `home-thread` switch holds. The pull request of a brief whose `Home:`
line names a scoped home merges by the same rules as the root home's. A home's own run, with
`--home`, merges nothing: it says what it would do of its own pull requests, and another home's
is `another home's` to it alone.

The tests run the command as a jbus pass does, against a real origin and the fake `gh` of
`features/jmerge/tests/test_jmerge_fresh.py`."""

import sys

import pytest

from test_jmerge_fresh import LINES, Kitchen, url

ROOT, SCOPED = "mcp:the-root-home", "mcp:the-flow-home"


@pytest.fixture
def kitchen(tmp_path):
    """A repo with a root home and a scoped home, `flow`, and two ready pull requests: number 6
    of the root home's and number 7 of the scoped home's. Nobody's id is in `home-thread`."""
    kitchen = Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES})
    state = kitchen.home.state
    (state / "home-thread").unlink()
    (state / "home-id").write_text(f"{ROOT}\n")
    (state / "flow").mkdir()
    (state / "flow" / "home-id").write_text(f"{SCOPED}\n")
    kitchen.crew("root-task", 6, {"a.txt": "ours\n" + LINES})
    kitchen.crew("fl-task", 7, {"b.txt": LINES + "ours\n"})
    brief = kitchen.home.tasks / "fl-task.md"
    title, rest = brief.read_text().split("\n", 1)
    brief.write_text(f"{title}\nHome: flow\n{rest}")
    return kitchen


def a_pass(kitchen):
    """What a jbus pass runs: `jmerge` in the main checkout, with no flags."""
    said = kitchen.home.sh(f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge')
    assert (kitchen.home.code, kitchen.home.stderr) == (0, "")
    return said


def test_a_pass_merges_a_scoped_homes_pull_request_as_it_merges_the_root_homes(kitchen):
    first, second = a_pass(kitchen)
    assert first.startswith("merged 6 root-task ") and second.startswith("merged 7 fl-task ")
    logged = (kitchen.home.state / "merge.log").read_text().splitlines()
    assert [line[17:] for line in logged] == [first, second]
    assert kitchen.at_main("b.txt") == (LINES + "ours\n").strip()


def test_with_the_switch_set_a_pass_still_merges_every_homes_pull_request(kitchen):
    (kitchen.home.state / "home-thread").write_text(f"{SCOPED}\n")
    first, second = a_pass(kitchen)
    assert first.startswith("merged 6 root-task ") and second.startswith("merged 7 fl-task ")


def test_a_homes_own_run_merges_nothing_and_leaves_the_other_homes_out(kitchen):
    said = kitchen.home.sh(
        f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge --home {SCOPED}'
    )
    assert (kitchen.home.code, kitchen.home.stderr) == (0, "")
    assert said[0] == f"wait 6 {url(6)}: another home's"
    assert said[1].startswith("ready 7 ")
    assert kitchen.calls() == []
