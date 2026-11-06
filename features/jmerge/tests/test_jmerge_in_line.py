"""`jmerge` has GitHub merge main into one branch at a time: the pull request it would merge
next, whose only reason to wait is that main moved after its check started. Every other one main
moved past waits in line behind it, and gets no update until its turn, so each merge costs one
rerun, as a merge queue's does (2026-11-03: with about 30 pull requests open, each merge sent
every one of them through CI again, about 80 branch updates in an hour). A pull request whose
check ran over today's main merges as before."""

import json
from datetime import datetime, timedelta

import pytest

import test_home_merge as merge
from jmerge import cli, ready, rejudge
from test_jmerge_fresh import AFTER, LINES, SHARED, STARTED, Kitchen, asked, git, url, write
from test_jmerge_order import queue_of, row


@pytest.fixture
def kitchen(tmp_path):
    files = {"a.txt": LINES, "b.txt": LINES, "c.txt": LINES, "d.txt": LINES}
    return Kitchen(tmp_path, {**files, "Makefile": "check:\n"}, overlap=True)


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


RED = {**merge.FAILED, "startedAt": STARTED["startedAt"]}


def red_asked(number, tip):
    """The line of a pull request whose check failed before main moved to `tip`, once GitHub was
    asked to merge main into its branch."""
    return f"wait {number} {url(number)}: " + ready.BASE_MERGE_ASKED.format(
        base="main", tip=tip[:12]
    )


def test_red_ones_main_moved_past_wait_in_the_same_line_one_update_for_each_merge(kitchen):
    """#1009's probe: one green pull request in line and two red ones whose check failed before
    main moved. GitHub was asked to update all three each time main moved; now a red one takes
    its place in the line, behind the green one at its head, and its update is its turn."""
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES}, checks=(RED,))
    kitchen.crew("four", 9, {"a.txt": "ours\n" + LINES}, checks=(RED,))
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7), behind(9, 7)]
    assert kitchen.updates() == ["7"]

    kitchen.updated("two", AFTER)
    first, second, third = kitchen.run()
    assert first.startswith("merged 7 two ")
    assert (second, third) == (red_asked(8, kitchen.tip()), behind(9, 8))
    assert kitchen.updates() == ["7", "8"]

    kitchen.updated("three", RUNNING)
    assert kitchen.run() == [f"wait 8 {url(8)}: check has not passed", behind(9, 8)]
    assert kitchen.updates() == ["7", "8"]

    kitchen.updated("three", AFTER)
    first, second = kitchen.run()
    assert first.startswith("merged 8 three ")
    assert second == red_asked(9, kitchen.tip())
    assert kitchen.updates() == ["7", "8", "9"]

    kitchen.updated("four", AFTER)
    (said,) = kitchen.run()
    assert said.startswith("merged 9 four ")
    assert kitchen.updates() == ["7", "8", "9"]


def test_a_red_one_whose_check_fails_again_at_its_updated_head_leaves_the_line(kitchen):
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES}, checks=(RED,))
    kitchen.crew("four", 9, {"a.txt": "ours\n" + LINES}, checks=(RED,))
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [red_asked(8, tip), behind(9, 8)]
    kitchen.updated("three", {**merge.FAILED, "startedAt": AFTER["startedAt"]})
    assert kitchen.run() == [f"wait 8 {url(8)}: check has failed", red_asked(9, tip)]
    assert kitchen.updates() == ["8", "9"]


def unrun(kitchen, slug):
    """Its `check` passed before main moved, and `borders`, which the repo requires too, has no
    run at its head."""
    (kitchen.home.state / cli.REQUIRED_CHECKS).write_text("check\nborders\n")
    kitchen.pulls[slug]["statusCheckRollup"] = [STARTED]
    kitchen.brief(slug, kitchen.pulls[slug]["headRefOid"])


def test_one_with_a_check_that_has_no_run_waits_in_the_same_line(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    unrun(kitchen, "three")
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    kitchen.updated("two", AFTER)
    first, second = kitchen.run()
    assert first.startswith("merged 7 two ")
    assert second == asked(8, kitchen.tip())
    assert kitchen.updates() == ["7", "8"]


def into(kitchen, slug, number, files, base):
    """A crewmate's pull request into `base`, a branch on the origin cut from main."""
    if base != "main":
        git(kitchen.home.main, "push", "-q", "origin", f"main:refs/heads/{base}")
    kitchen.crew(slug, number, files)
    kitchen.pulls[slug]["baseRefName"] = base
    kitchen.brief(slug, kitchen.pulls[slug]["headRefOid"])


def moves(kitchen, base, files):
    """A commit to `base` on the origin now, after every check that started in 2000."""
    if base == "main":
        return kitchen.on_main(files)
    tree = kitchen.tmp / "trees" / f"on-{base}"
    if not tree.exists():
        git(kitchen.home.main, "worktree", "add", "-q", "--detach", str(tree), f"origin/{base}")
    shared = (tree / SHARED).read_text().split("\n")
    shared[1] = base
    write(tree, {SHARED: "\n".join(shared), **files})
    git(tree, "commit", "-q", "-m", f"on {base}")
    git(tree, "push", "-q", "origin", f"HEAD:refs/heads/{base}")
    return git(tree, "rev-parse", "HEAD")


def asked_into(number, base, tip):
    return f"wait {number} {url(number)}: " + ready.BASE_MOVED_ASKED.format(base=base, tip=tip[:12])


@pytest.mark.parametrize("first", ["main", "side"])
def test_a_pull_request_into_one_base_holds_no_line_for_those_into_another(kitchen, first):
    """A stack branch whose base moved holds the line of its own base: every pull request into
    main does not wait behind it, nor it behind one into main."""
    second = "side" if first == "main" else "main"
    rows = [row(slug, pr=f"#{n}") for slug, n in (("two", 7), ("three", 8), ("four", 9))]
    queue_of(kitchen.home, rows, 'merge_bases = ["side"]\n')
    into(kitchen, "two", 7, {"b.txt": "ours\n" + LINES}, first)
    into(kitchen, "three", 8, {"c.txt": "ours\n" + LINES}, second)
    into(kitchen, "four", 9, {"a.txt": "ours\n" + LINES}, second)
    tips = {base: moves(kitchen, base, {"d.txt": f"{base}\n"}) for base in ("main", "side")}
    expected = [asked_into(7, first, tips[first]), asked_into(8, second, tips[second])]
    behind = f"wait 9 {url(9)}: " + ready.IN_LINE.format(number=8, base=second)
    assert kitchen.run() == [*expected, behind]
    assert kitchen.updates() == ["7", "8"]


def aged(kitchen, number, by):
    """The record of the pull request's update in `base-merges.json`, kept `by` ago."""
    path = kitchen.home.state / rejudge.NAME
    records = json.loads(path.read_text())
    at = datetime.now().astimezone() - by
    records[str(number)]["at"] = f"{at:%Y-%m-%dT%H:%M:%S%z}"
    path.write_text(json.dumps(records))


def test_one_whose_head_github_never_moved_gives_the_line_up_after_a_while(kitchen):
    """GitHub took the update and made no new head: no check is coming to end the wait, so the
    one in line holds the line only `rejudge.HELD` after GitHub took it."""
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    aged(kitchen, 7, rejudge.HELD - timedelta(minutes=1))
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    aged(kitchen, 7, rejudge.HELD)
    assert kitchen.run() == [asked(7, tip), asked(8, tip)]
    assert kitchen.run() == [behind(7, 8), asked(8, tip)]
    assert kitchen.updates() == ["7", "8"]


def test_one_whose_new_head_s_check_runs_keeps_the_line_past_that_while(kitchen):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    kitchen.updated("two", RUNNING)
    aged(kitchen, 7, rejudge.HELD * 3)
    assert kitchen.run() == [f"wait 7 {url(7)}: check has not passed", behind(8, 7)]
    assert kitchen.updates() == ["7"]


@pytest.mark.parametrize("wait", ["findings", "hold"])
def test_one_that_waits_on_its_crew_or_the_user_gives_the_line_up(kitchen, wait):
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    head = kitchen.updated("two", AFTER)
    if wait == "findings":
        kitchen.brief("two", head, verdict="findings")
    else:
        kitchen.pulls["two"]["files"].append(merge.file("secrets/prod.json"))
        kitchen.brief("two", head)
    first, second = kitchen.run()
    assert first.startswith(f"{'hold' if wait == 'hold' else 'wait'} 7 ")
    assert second == asked(8, tip)
    assert kitchen.updates() == ["7", "8"]
