"""A pull request stacked on another's branch by jbus (its brief's `Stacked on:` line) merges only
after its base merged and it was rebased onto the branch its base merged into, main or another
branch. While the line names its base's branch it waits, also where GitHub has already
based it on main. Once jbus wrote that the base merged as a commit of that branch, it waits until it
is based on that branch and its head holds that commit, and then merges as any other.

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


def judged(built_on, line, base="main", flags=("--check",), **listed_as):
    """What jmerge says of alpha (#7) under the brief's `line`, based on `base`, run with `flags`,
    with the fields of `listed_as` in what GitHub lists of it."""
    brief_of(built_on.home, "alpha", merge.URL, built_on.head, more=line + "\n")
    queue_of(built_on.home, rows(gamma="merged"))
    listing(built_on, 7)
    listed = json.loads((built_on.home.stub / "list.json").read_text())
    listed[0].update(baseRefName=base, **listed_as)
    (built_on.home.stub / "list.json").write_text(json.dumps(listed))
    return built_on.run(*flags)[0]


def readied(built_on):
    asked = (built_on.home.stub / "calls").read_text().splitlines()
    return [call.split()[2] for call in asked if call.startswith("pr ready")]


@pytest.mark.parametrize("draft", [False, True])
def test_a_reviewed_link_on_its_open_bases_branch_waits_on_its_stack_and_is_never_marked_ready(
    built_on, draft
):
    """A link is checked while it is stacked, beside its base's own check, as any open pull
    request is, so its move onto main adds no round in series. It waits on its stack, a draft
    as well, and it merges only after jbus moved it. jmerge marks no draft ready."""
    said = judged(built_on, "Stacked on: beta beta", "beta", (), isDraft=draft)
    on = ready.STACKED_ON.format(branch="beta", slug="beta", default="main")
    assert said == f"wait 7 {merge.URL}: {on}"
    assert readied(built_on) == []


def test_a_link_whose_base_merged_waits_for_its_move(built_on):
    """Once its base merged, the head on the base's branch is not what merges: it is moved first,
    and the check runs on the moved head."""
    line = f"Stacked on: beta main at {built_on.delta}"
    said = judged(built_on, line, "main", ())
    unmoved = ready.STACKED_UNMOVED.format(slug="beta", sha=built_on.delta[:12], default="main")
    assert said == f"wait 7 {merge.URL}: {unmoved}"
    assert readied(built_on) == []


@pytest.mark.parametrize(
    ("check", "said"),
    [(merge.PASSED, "ready 7 "), (merge.RUNNING, f"wait 7 {merge.URL}: check has not passed")],
)
def test_a_moved_link_merges_on_its_check_at_the_moved_head(built_on, check, said):
    """CI's check at the moved head reuses the stacked run's pass where the two check the same
    trees, and passes at once (`jmerge.reuse`); where they differ it runs the round, and the link
    waits on it."""
    found = judged(
        built_on,
        f"Stacked on: beta main at {built_on.beta}",
        statusCheckRollup=[check, merge.BORDERS],
    )
    assert found.startswith(said), found


@pytest.mark.parametrize("base", ["beta", "main"])
def test_a_link_on_its_bases_branch_waits_for_jbus_to_move_it(built_on, base):
    said = judged(built_on, "Stacked on: beta beta", base=base)
    on = ready.STACKED_ON.format(branch="beta", slug="beta", default="main")
    assert said == f"wait 7 {merge.URL}: {on}"


def test_a_link_whose_base_merged_into_a_branch_waits_for_its_rebase_onto_the_branch(built_on):
    """A base that merged into another branch than main moves its link onto that branch:
    the link waits for its head to hold the merge, named on the branch, and its base on main is
    no merge."""
    said = judged(built_on, f"Stacked on: beta release/x at {built_on.delta}", base="release/x")
    unmoved = ready.STACKED_UNMOVED.format(
        slug="beta", sha=built_on.delta[:12], default="release/x"
    )
    assert said == f"wait 7 {merge.URL}: {unmoved}"
    said = judged(built_on, f"Stacked on: beta release/x at {built_on.beta}", base="main")
    on = ready.STACKED_ON.format(branch="release/x", slug="beta", default="release/x")
    assert said == f"wait 7 {merge.URL}: {on}"


def test_a_link_rebased_onto_its_bases_merge_on_a_branch_merges_as_any_other(built_on):
    said = judged(built_on, f"Stacked on: beta release/x at {built_on.beta}", base="release/x")
    assert said.startswith("ready 7 ")


def squash_rebased(built_on, rebase):
    """Squash beta into `release/x`, move alpha's own commit onto it and let `rebase` change the
    moved head; what jmerge says of alpha, whose brief says nothing of the rebase."""
    home, tree, old = built_on.home, built_on.tree, built_on.head
    merge.git(tree, "switch", "-q", "--detach", built_on.start)
    merge.git(tree, "restore", "--source", built_on.beta, "--", ".")
    merge.git(tree, "add", "-A")
    merge.git(tree, "commit", "-q", "-m", "beta, squashed")
    squash = merge.git(tree, "rev-parse", "HEAD")
    merge.git(tree, "push", "-q", "origin", f"{squash}:refs/heads/release/x")
    merge.git(tree, "cherry-pick", old)
    rebase(tree)
    new = merge.git(tree, "rev-parse", "HEAD")
    merge.git(tree, "push", "-q", "--force", "origin", f"{new}:refs/heads/alpha")
    merge.git(home.main, "fetch", "-q", "origin")
    (home.stub / "head").write_text(f"{new}\n")
    text = merge.brief(
        merge.review("clean", old),
        "",
        f"Stacked on: beta release/x at {squash}\n",
    )
    (home.tasks / "alpha.md").write_text(text)
    queue_of(home, rows(gamma="merged"))
    listing(built_on, 7)
    listed = json.loads((home.stub / "list.json").read_text())
    listed[0].update(baseRefName="release/x", headRefOid=new)
    (home.stub / "list.json").write_text(json.dumps(listed))
    return built_on.run("--check")[0]


def test_a_link_rebased_over_its_bases_squash_on_a_branch_with_its_patch_unchanged_merges(built_on):
    """A base squash-merged into a branch leaves the link's old head forking from the branch before
    the base, so that head's diff from the fork holds the base's commits too. The patch jmerge
    compares is the link's own commits, and those the rebase left as they were."""
    said = squash_rebased(built_on, lambda tree: None)
    assert said.startswith("ready 7 "), said


def amended(tree):
    (tree / "b.txt").write_text("the cleanup, changed on the rebase\n")
    merge.git(tree, "commit", "-q", "-a", "--amend", "--no-edit")


def one_more(tree):
    (tree / "e.py").write_text("ADDED = 'a commit the rebase added, of code'\n")
    merge.git(tree, "add", "e.py")
    merge.git(tree, "commit", "-q", "-m", "one more")


@pytest.mark.parametrize("rebase", [amended, one_more])
def test_a_link_rebased_over_its_bases_squash_on_a_branch_that_changed_its_patch_waits(
    built_on, rebase
):
    """The old head's own commits are cut by a count, and a rebase that changed them, in content
    or in number, is still a changed patch, which waits on its crew or its scoped review: no cut
    may make the two sides equal."""
    said = squash_rebased(built_on, rebase)
    assert said.startswith(f"wait 7 {merge.URL}: the rebase "), said


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
