"""A pull request stacked on another's branch by jbus (its brief's `Stacked on:` line) merges only
after its base merged and it was rebased onto main. While the line names its base's branch it
waits, also where GitHub has already based it on main. Once jbus wrote that the base merged as a
commit of main, it waits until its head holds that commit, and then merges as any other.

The tests run the command against `test_jmerge_carried`'s repo: alpha (#7) is built on beta's
head, and delta is a commit on main's side that alpha does not hold."""

import json

import pytest

import test_home_merge as merge
from jmerge import ready
from test_jmerge_carried import brief_of, built_on, listing, rows
from test_jmerge_order import queue_of

__all__ = ["built_on"]


def stacked(built_on, line, base="main"):
    brief_of(built_on.home, "alpha", merge.URL, built_on.head, more=line + "\n")
    queue_of(built_on.home, rows(gamma="merged"))
    listing(built_on, 7)
    listed = json.loads((built_on.home.stub / "list.json").read_text())
    listed[0]["baseRefName"] = base
    (built_on.home.stub / "list.json").write_text(json.dumps(listed))
    return built_on.run("--check")[0]


@pytest.mark.parametrize("base", ["beta", "main"])
def test_a_link_on_its_bases_branch_waits_for_jbus_to_move_it(built_on, base):
    said = stacked(built_on, "Stacked on: beta beta", base=base)
    on = ready.STACKED_ON.format(branch="beta", slug="beta", default="main")
    assert said == f"wait 7 {merge.URL}: {on}"


def test_a_link_whose_head_does_not_hold_its_bases_merge_waits_for_its_rebase(built_on):
    said = stacked(built_on, f"Stacked on: beta main at {built_on.delta}")
    unmoved = ready.STACKED_UNMOVED.format(slug="beta", sha=built_on.delta[:12], default="main")
    assert said == f"wait 7 {merge.URL}: {unmoved}"


def test_a_link_rebased_onto_its_bases_merge_merges_as_any_other(built_on):
    said = stacked(built_on, f"Stacked on: beta main at {built_on.beta}")
    assert said.startswith("ready 7 ")


@pytest.mark.parametrize(
    ("line", "found"),
    [
        ("Stacked on: beta beta", ready.Stacked("beta", "beta")),
        ("Stacked on: beta main at " + "a" * 40, ready.Stacked("beta", "main", "a" * 40)),
        ("Stacked on: beta", None),
        ("Stacked on: beta main at", None),
        ("Stacked on: beta main by " + "a" * 40, None),
    ],
)
def test_the_line_reads_back_as_it_was_written(line, found):
    text = merge.brief(merge.review("clean", "a" * 40), field=line + "\n")
    assert ready.stacked_of(text) == found
    if found is not None:
        assert ready.stacked_line(found) == line
