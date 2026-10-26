"""A pull request stacked on another's branch by jbus (its brief's `Stacked on:` line) merges only
after its base merged and it was rebased onto the branch its base merged into, main or a train.
While the line names its base's branch it waits, also where GitHub has already based it on main.
Once jbus wrote that the base merged as a commit of that branch, it waits until it is based on
that branch and its head holds that commit, and then merges as any other.

The tests run the command against `test_jmerge_carried`'s repo: alpha (#7) is built on beta's
head, and delta is a commit on main's side that alpha does not hold."""

import json

import pytest

import test_home_merge as merge
from jmerge import ready
from jmerge import stacked as stacks
from test_jmerge_carried import brief_of, built_on, listing, rows
from test_jmerge_order import queue_of

__all__ = ["built_on"]


def judged(built_on, line, base="main"):
    brief_of(built_on.home, "alpha", merge.URL, built_on.head, more=line + "\n")
    queue_of(built_on.home, rows(gamma="merged"))
    listing(built_on, 7)
    listed = json.loads((built_on.home.stub / "list.json").read_text())
    listed[0]["baseRefName"] = base
    (built_on.home.stub / "list.json").write_text(json.dumps(listed))
    return built_on.run("--check")[0]


@pytest.mark.parametrize("base", ["beta", "main"])
def test_a_link_on_its_bases_branch_waits_for_jbus_to_move_it(built_on, base):
    said = judged(built_on, "Stacked on: beta beta", base=base)
    on = ready.STACKED_ON.format(branch="beta", slug="beta", default="main")
    assert said == f"wait 7 {merge.URL}: {on}"


def test_a_link_whose_head_does_not_hold_its_bases_merge_waits_for_its_rebase(built_on):
    said = judged(built_on, f"Stacked on: beta main at {built_on.delta}")
    unmoved = ready.STACKED_UNMOVED.format(slug="beta", sha=built_on.delta[:12], default="main")
    assert said == f"wait 7 {merge.URL}: {unmoved}"


def test_a_link_rebased_onto_its_bases_merge_merges_as_any_other(built_on):
    said = judged(built_on, f"Stacked on: beta main at {built_on.beta}")
    assert said.startswith("ready 7 ")


def test_a_link_whose_base_merged_into_a_train_waits_for_its_rebase_onto_the_train(built_on):
    """A base that merged into a train moves its link onto that train, not main: the link waits
    for its head to hold the merge, named on the train, and its base on main is no merge."""
    said = judged(built_on, f"Stacked on: beta train/x at {built_on.delta}", base="train/x")
    unmoved = ready.STACKED_UNMOVED.format(slug="beta", sha=built_on.delta[:12], default="train/x")
    assert said == f"wait 7 {merge.URL}: {unmoved}"
    said = judged(built_on, f"Stacked on: beta train/x at {built_on.beta}", base="main")
    on = ready.STACKED_ON.format(branch="train/x", slug="beta", default="train/x")
    assert said == f"wait 7 {merge.URL}: {on}"


def test_a_link_rebased_onto_its_bases_merge_on_a_train_merges_as_any_other(built_on):
    said = judged(built_on, f"Stacked on: beta train/x at {built_on.beta}", base="train/x")
    assert said.startswith("ready 7 ")


def squash_rebased(built_on, rebase):
    """Squash beta into `train/x`, move alpha's own commit onto it and let `rebase` change the
    moved head; what jmerge says of alpha with `Rebase: patch unchanged` on its brief."""
    home, tree, old = built_on.home, built_on.tree, built_on.head
    merge.git(tree, "switch", "-q", "--detach", built_on.start)
    merge.git(tree, "restore", "--source", built_on.beta, "--", ".")
    merge.git(tree, "add", "-A")
    merge.git(tree, "commit", "-q", "-m", "beta, squashed")
    squash = merge.git(tree, "rev-parse", "HEAD")
    merge.git(tree, "push", "-q", "origin", f"{squash}:refs/heads/train/x")
    merge.git(tree, "cherry-pick", old)
    rebase(tree)
    new = merge.git(tree, "rev-parse", "HEAD")
    merge.git(tree, "push", "-q", "--force", "origin", f"{new}:refs/heads/alpha")
    merge.git(home.main, "fetch", "-q", "origin")
    (home.stub / "head").write_text(f"{new}\n")
    text = merge.brief(
        merge.review("clean", old),
        f"Rebase: patch unchanged, before {old}, head {new}\n",
        f"Stacked on: beta train/x at {squash}\n",
    )
    (home.tasks / "alpha.md").write_text(text)
    queue_of(home, rows(gamma="merged"))
    listing(built_on, 7)
    listed = json.loads((home.stub / "list.json").read_text())
    listed[0].update(baseRefName="train/x", headRefOid=new)
    (home.stub / "list.json").write_text(json.dumps(listed))
    return built_on.run("--check")[0]


def test_a_link_rebased_over_its_bases_squash_on_a_train_with_its_patch_unchanged_merges(built_on):
    """A base squash-merged into a train leaves the link's old head forking from the train before
    the base, so that head's diff from the fork holds the base's commits too. The patch the
    `Rebase:` line speaks of is the link's own commits, and those the rebase left as they were."""
    said = squash_rebased(built_on, lambda tree: None)
    assert said.startswith("ready 7 "), said


def amended(tree):
    (tree / "b.txt").write_text("the cleanup, changed on the rebase\n")
    merge.git(tree, "commit", "-q", "-a", "--amend", "--no-edit")


def one_more(tree):
    (tree / "e.txt").write_text("a commit the rebase added\n")
    merge.git(tree, "add", "e.txt")
    merge.git(tree, "commit", "-q", "-m", "one more")


@pytest.mark.parametrize("rebase", [amended, one_more])
def test_a_link_rebased_over_its_bases_squash_on_a_train_that_changed_its_patch_waits(
    built_on, rebase
):
    """The old head's own commits are cut by a count, and a rebase that changed them, in content
    or in number, is still a changed patch: no cut may make the two sides equal."""
    said = squash_rebased(built_on, rebase)
    assert said == f"wait 7 {merge.URL}: {ready.REBASE_UNTRUE}"


@pytest.mark.parametrize(
    ("line", "found"),
    [
        ("Stacked on: beta beta", stacks.Stacked("beta", "beta")),
        ("Stacked on: beta main at " + "a" * 40, stacks.Stacked("beta", "main", "a" * 40)),
        ("Stacked on: beta", None),
        ("Stacked on: beta main at", None),
        ("Stacked on: beta main by " + "a" * 40, None),
    ],
)
def test_the_line_reads_back_as_it_was_written(line, found):
    text = merge.brief(merge.review("clean", "a" * 40), field=line + "\n")
    assert stacks.of(text) == found
    if found is not None:
        assert stacks.line(found) == line
