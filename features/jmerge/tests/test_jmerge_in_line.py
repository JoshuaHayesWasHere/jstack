"""`jmerge` has GitHub merge main into one branch at a time: the pull request it would merge
next, whose only reason to wait is that main moved after its check started. Every other one main
moved past waits in line behind it, and gets no update until its turn, so each merge costs one
rerun, as a merge queue's does (2026-11-03: with about 30 pull requests open, each merge sent
every one of them through CI again, about 80 branch updates in an hour). A pull request whose
check ran over today's main merges as before."""

import pytest

import test_home_merge as merge
from jmerge import ready
from test_jmerge_fresh import AFTER, LINES, Kitchen, asked, url


@pytest.fixture
def kitchen(tmp_path):
    files = {"a.txt": LINES, "b.txt": LINES, "c.txt": LINES, "d.txt": LINES}
    return Kitchen(tmp_path, {**files, "Makefile": "check:\n"})


def behind(number, ahead):
    return f"wait {number} {url(number)}: " + ready.IN_LINE.format(number=ahead, base="main")


RUNNING = {**merge.RUNNING, "startedAt": AFTER["startedAt"]}


def test_three_ready_pull_requests_get_one_update_for_each_merge_in_merge_order(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    first, second, third = kitchen.run()
    assert first.startswith("merged 6 one ")
    assert (second, third) == (asked(7, kitchen.tip()), behind(8, 7))
    assert kitchen.updates() == ["7"]

    kitchen.updated("two", RUNNING)
    assert kitchen.run() == [f"wait 7 {url(7)}: check has not passed", behind(8, 7)]
    assert kitchen.updates() == ["7"]

    kitchen.updated("two", AFTER)
    first, second = kitchen.run()
    assert first.startswith("merged 7 two ")
    assert second == asked(8, kitchen.tip())
    assert kitchen.updates() == ["7", "8"]

    kitchen.updated("three", AFTER)
    (said,) = kitchen.run()
    assert said.startswith("merged 8 three ")
    assert kitchen.updates() == ["7", "8"]
    assert kitchen.calls("pr merge") == [
        call for n in (6, 7, 8) for call in kitchen.calls("pr merge") if f" {n} " in call
    ]


def test_the_one_in_line_holds_it_from_one_that_comes_ready_ahead_of_it(kitchen):
    """The line is held by the pull request GitHub was asked to update, whatever its place:
    one ahead of it in merge order that comes ready later waits behind it."""
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    kitchen.pulls["two"]["isDraft"] = True
    kitchen.brief("two", kitchen.pulls["two"]["headRefOid"])
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.HAND_DRAFT}", asked(8, tip)]
    kitchen.pulls["two"]["isDraft"] = False
    kitchen.brief("two", kitchen.pulls["two"]["headRefOid"])
    kitchen.updated("three", RUNNING)
    assert kitchen.run() == [behind(7, 8), f"wait 8 {url(8)}: check has not passed"]
    assert kitchen.updates() == ["8"]


def test_one_whose_check_failed_after_its_update_leaves_the_line_to_the_next(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    kitchen.updated("two", {**merge.FAILED, "startedAt": AFTER["startedAt"]})
    assert kitchen.run() == [f"wait 7 {url(7)}: check has failed", asked(8, tip)]
    assert kitchen.run() == [f"wait 7 {url(7)}: check has failed", asked(8, tip)]
    assert kitchen.updates() == ["7", "8"]


def test_one_whose_check_ran_over_today_s_main_merges_while_others_wait_in_line(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    kitchen.crew("four", 9, {"a.txt": "ours\n" + LINES}, checks=(AFTER,))
    said = kitchen.run()
    assert said[0] == asked(7, tip) and said[1] == behind(8, 7)
    assert said[2].startswith("merged 9 four ")
    assert kitchen.updates() == ["7"]
