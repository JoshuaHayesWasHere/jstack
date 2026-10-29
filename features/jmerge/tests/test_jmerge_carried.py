"""A pull request built on another open pull request's branch carries that pull request's
commits, so a merge of it lands them too. `jmerge` holds such a pull request to the order of
the one it carries: while the carried row merges after a row that is not merged or done, the
pull request waits as if its own row named that row.

The tests run the command as `test_home_merge` runs it, against its fake `gh` and a real
origin. `alpha` (#7) is built on `beta` (#8): alpha's head has beta's head under it. beta's
row merges after `gamma` (#9), which has a row and no branch here. beta is a draft, so it
never merges in these tests and stays open. `delta` (#10) is built on main and carries
nothing."""

import json

import pytest

import test_home_merge as merge
from jmerge import judgement, ready
from test_jmerge_order import BETA_URL, merged_numbers, queue_of, row

DELTA_URL = "https://example.test/pull/10"


def brief_of(home, slug, url, head, more=""):
    (home.tasks / f"{slug}.md").write_text(
        merge.brief(merge.review("clean", head), field=more)
        .replace(merge.URL, url)
        .replace("# alpha", f"# {slug}")
        .replace("Branch: alpha", f"Branch: {slug}")
    )


@pytest.fixture
def built_on(merged):
    """`beta` is the commit `merged` pushed for alpha, and alpha gets one more commit on top
    of it. `delta` is one commit on main."""
    home, tree = merged.home, merged.tree
    beta = merged.head
    merge.git(tree, "branch", "beta", beta)
    merge.git(tree, "push", "-q", "origin", "beta")
    (tree / "b.txt").write_text("the cleanup\n")
    merge.git(tree, "add", "b.txt")
    merge.git(tree, "commit", "-q", "-m", "the cleanup")
    merge.git(tree, "push", "-q", "origin", "alpha")
    merged.head = merge.git(tree, "rev-parse", "HEAD")
    (home.stub / "head").write_text(f"{merged.head}\n")
    merge.git(home.main, "fetch", "-q", "origin")
    merge.git(tree, "switch", "-q", "--detach", merged.start)
    (tree / "d.txt").write_text("the other task\n")
    merge.git(tree, "add", "d.txt")
    merge.git(tree, "commit", "-q", "-m", "the other task")
    delta = merge.git(tree, "rev-parse", "HEAD")
    merge.git(tree, "push", "-q", "origin", f"{delta}:refs/heads/delta")
    merge.git(tree, "switch", "-q", "alpha")
    brief_of(home, "alpha", merge.URL, merged.head)
    brief_of(home, "beta", BETA_URL, beta)
    brief_of(home, "delta", DELTA_URL, delta)
    merged.beta, merged.delta = beta, delta
    return merged


def listing(merged, *numbers):
    """What GitHub lists of the open pull requests `numbers`, beta as a draft."""
    template = json.loads((merged.home.stub / "list.json").read_text())[0]
    pulls = {
        7: {"headRefOid": merged.head},
        8: {"url": BETA_URL, "headRefName": "beta", "headRefOid": merged.beta, "isDraft": True},
        10: {"url": DELTA_URL, "headRefName": "delta", "headRefOid": merged.delta},
    }
    listed = [{**template, "number": number, **pulls[number]} for number in numbers]
    (merged.home.stub / "list.json").write_text(json.dumps(listed))


CARRIED = (
    f"wait 7 {merge.URL}: carries beta's commits (#8), which merges after gamma (#9), "
    "not merged yet"
)


def rows(gamma="pr"):
    return [
        row("alpha", pr="#7"),
        row("beta", pr="#8", merge_after=["gamma"]),
        row("gamma", status=gamma, pr="#9"),
        row("delta", pr="#10"),
    ]


def test_a_pull_request_built_on_another_waits_on_that_ones_order(built_on):
    queue_of(built_on.home, rows())
    listing(built_on, 7, 8, 10)
    said = built_on.run("--check")
    assert said[0] == CARRIED
    assert said[2].startswith("ready 10 ")
    listing(built_on, 7, 8)
    after = f"wait 8 {BETA_URL}: merges after gamma (#9), not merged yet"
    assert built_on.run() == [CARRIED, after]
    asked = (built_on.home.stub / "calls").read_text().splitlines()
    assert not [call for call in asked if call.startswith("pr ready")]
    assert built_on.on_main() == (built_on.start, built_on.start)


@pytest.mark.parametrize("over", ["merged", "done"])
def test_it_merges_once_the_row_the_carried_one_waits_on_is_over(built_on, over):
    queue_of(built_on.home, rows(gamma=over))
    listing(built_on, 7, 8)
    assert merged_numbers(built_on.run()) == [7]


def test_a_carried_pull_request_whose_row_is_over_holds_nothing_back(built_on):
    table = rows()
    table[1]["status"] = "done"
    queue_of(built_on.home, table)
    listing(built_on, 7, 8)
    assert built_on.run("--check")[0].startswith("ready 7 ")


def test_a_head_that_cannot_be_read_waits_rather_than_merge_what_it_may_carry(built_on):
    queue_of(built_on.home, rows())
    listing(built_on, 7, 8)
    listed = json.loads((built_on.home.stub / "list.json").read_text())
    listed[1]["headRefOid"] = "f" * 40
    (built_on.home.stub / "list.json").write_text(json.dumps(listed))
    unknown = ready.CARRIES_UNKNOWN.format(carried="beta", number=8)
    assert built_on.run("--check")[0] == f"wait 7 {merge.URL}: {unknown}"


@pytest.mark.parametrize(
    "reason",
    [
        ready.CARRIES_AFTER.format(carried="beta", number=8, slug="gamma", open="#9"),
        ready.CARRIES_UNKNOWN.format(carried="beta", number=8),
    ],
)
def test_each_carried_wait_lands_on_the_check_step_and_not_in_unknown(reason):
    assert judgement.step(f"wait: {reason}") == "check"
