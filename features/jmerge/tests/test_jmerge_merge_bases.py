"""A project can name merge bases besides the default branch (`jbus project add-base`), as jstack
names `t3code-jstack`, the branch the sidebar's pull requests go on. `jmerge` merges a pull
request into a named base on the rules of one into main: its review written and answered, its
required checks green, and not a draft. A base the project does not name is still held, and
main's red holds no pull request into another branch.

The tests run the command as `test_home_merge` runs it, against its fake `gh` and a real origin
that has a `side` branch, with a jbus config whose project is this checkout."""

import pytest

import test_home_merge as merge
from jmerge import ready
from test_jmerge_order import RED, main_says, merged_numbers, queue_of, row

SIDE = 'merge_bases = ["side"]\n'


@pytest.fixture
def side(merged):
    """The origin has a `side` branch at main's commit, and the pull request goes on it."""
    merge.git(merged.tree, "push", "-q", "origin", f"{merged.start}:refs/heads/side")
    merged.home.open_pull_request(merged.head, base="side")
    (merged.home.stub / "merge-base").write_text("side\n")
    return merged


def merges(merged):
    calls = (merged.home.stub / "calls").read_text().splitlines()
    return [call for call in calls if call.startswith(("pr merge", "pr ready"))]


def test_a_reviewed_green_pull_request_into_a_named_base_merges_into_it(side):
    queue_of(side.home, [row("alpha", pr="#7")], SIDE)
    (said,) = side.run()
    assert said.startswith("merged 7 alpha ")
    onto = merge.git(side.origin, "rev-parse", "side")
    assert merge.git(side.origin, "rev-parse", f"{onto}^") == side.start
    assert merge.git(side.origin, "rev-parse", "main") == side.start
    assert not side.tree.exists()


def test_a_pull_request_into_a_named_base_waits_on_its_review_as_one_into_main(side):
    queue_of(side.home, [row("alpha", pr="#7")], SIDE)
    (side.home.tasks / "alpha.md").write_text(merge.brief())
    assert side.run() == [f"wait 7 {merge.URL}: {ready.NO_REVIEW}"]
    (side.home.tasks / "alpha.md").write_text(merge.brief(merge.review("findings", side.head)))
    assert side.run() == [f"wait 7 {merge.URL}: {ready.NO_FIXED}"]
    assert merges(side) == []


def test_a_pull_request_into_a_named_base_waits_on_its_required_checks(side):
    queue_of(side.home, [row("alpha", pr="#7")], SIDE)
    side.home.open_pull_request(side.head, base="side", checks=(merge.run("FAILURE"),))
    (said,) = side.run()
    assert said.startswith(f"wait 7 {merge.URL}: ") and "check" in said
    assert merges(side) == []


@pytest.mark.parametrize(
    "config",
    [
        pytest.param("", id="the project names no merge base"),
        pytest.param('merge_bases = ["other"]\n', id="it names another branch"),
    ],
)
def test_a_base_the_project_does_not_name_is_held_as_before(side, config):
    queue_of(side.home, [row("alpha", pr="#7")], config)
    assert side.run() == [f"wait 7 {merge.URL}: its base is side, not main"]
    assert merges(side) == []
    assert merge.git(side.origin, "rev-parse", "side") == side.start


def test_a_config_that_does_not_load_names_no_merge_base(side):
    path = queue_of(side.home, [row("alpha", pr="#7")], SIDE)
    (side.home.user / ".config" / "jbus" / "config.toml").chmod(0o644)
    assert path.exists()
    (said,) = side.home.run()
    assert said == f"wait 7 {merge.URL}: its base is side, not main"


def test_a_draft_into_a_named_base_is_never_merged(side):
    queue_of(side.home, [row("alpha", pr="#7")], SIDE)
    side.home.open_pull_request(side.head, base="side", draft=True)
    assert side.run("--check") == [merge.DRAFT]
    assert side.run() == [merge.READIED + side.head]
    assert [call.split()[:2] for call in merges(side)] == [["pr", "ready"]]
    assert merge.git(side.origin, "rev-parse", "side") == side.start


def test_the_integration_draft_into_main_with_no_brief_is_never_merged_or_marked_ready(merged):
    """#739 is the draft of `t3code-jstack` into main, and no brief names it: it waits as a
    draft whatever merge bases the project names, and nothing marks it ready."""
    queue_of(merged.home, [], 'merge_bases = ["t3code-jstack"]\n')
    (merged.home.tasks / "alpha.md").unlink()
    merged.home.open_pull_request(merged.head, draft=True)
    assert merged.run() == [merge.DRAFT]
    assert merged.run() == [merge.DRAFT]
    assert merges(merged) == []
    assert merged.untouched()


def test_a_red_main_holds_no_pull_request_into_a_named_base(side):
    queue_of(side.home, [row("alpha", pr="#7")], SIDE)
    main_says(side.home, red=RED, green="a" * 40)
    assert merged_numbers(side.run()) == [7]


def test_a_red_main_still_holds_a_pull_request_into_main(merged):
    queue_of(merged.home, [row("alpha", pr="#7")], SIDE)
    main_says(merged.home, red=RED, green="a" * 40)
    (said,) = merged.run()
    assert said == f"wait 7 {merge.URL}: main is red at {RED[:12]}, its fix merges first"


def test_a_sweep_keeps_a_branch_that_is_a_merge_base(side):
    """A brief whose branch is a merge base, as the integration branch's would be, is never
    swept: the branch is where other rows merge."""
    queue_of(side.home, [], SIDE)
    text = merge.brief().replace("Branch: alpha", "Branch: side").replace("# alpha", "# side")
    (side.home.tasks / "side.md").write_text(text)
    said = side.home.run("--sweep", "--check")
    assert "kept side: it is a merge base of the project" in said
