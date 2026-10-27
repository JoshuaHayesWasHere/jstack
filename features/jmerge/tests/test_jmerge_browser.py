"""A pull request whose own browser run failed does not merge. browser.yml runs on a pull request
into main that changes the view, and is no required check, so `jmerge` waited on no run of it:
#557 (fl-sub-no-steer) merged on 2026-10-27 with its browser run red at 37f2bf8bd433, and main
went red on the browser tests at c05d32d4; #563 merged red on the same tests after it. Since
#538 jbus files no `browser-red-` row for a pull request's run, so that red was nobody's.

`jmerge` now holds a head whose latest browser run ended and failed, with its own reason, which
jbus tells the crew (`jbus.expedite.TABLE`). A head with no browser run, a pull request that
does not touch the view, merges as before, and one whose browser run is still going waits for
it. A red that main's own browser run already has is main's, not the pull request's: it waits
as for a red main.

The tests replay #557 through the kitchen's fakes (`test_jmerge_rejudge.Replay`), with a fake
`gh` that also lists main's browser runs."""

import json

import pytest

import test_home_merge as merge
from jbus import watch
from jmerge import ready, rows
from test_jmerge_fresh import url
from test_jmerge_rejudge import STARTED, Replay

RUNS = """\
    "api repos/{owner}/{repo}/actions/workflows/browser.yml/runs"*)
        echo "$*" >> "$STUB/asked-runs"
        cat "$STUB/browser-runs.json" ;;
"""
CHECKED = {**merge.PASSED, "startedAt": STARTED}
BROWSER_RED = merge.run("FAILURE", "browser")
BROWSER_GREEN = merge.run("SUCCESS", "browser")
BROWSER_RUNNING = merge.run("", "browser", status="IN_PROGRESS")
BROWSER_DRAFT = {**merge.run("SKIPPED", "browser"), "startedAt": "2026-10-23T12:59:00Z"}


@pytest.fixture
def replay(tmp_path):
    replay = Replay(tmp_path, fresh=False)
    gh = replay.kitchen.home.stub / "gh"
    gh.write_text(gh.read_text().replace("    *) exit 64 ;;\n", RUNS + "    *) exit 64 ;;\n"))
    return replay


def main_ran(replay, *runs):
    """GitHub's list of browser.yml's completed runs: each as `(event, branch, conclusion,
    head)`, newest last."""
    listed = [
        {
            "id": number,
            "event": event,
            "head_branch": branch,
            "head_sha": head,
            "status": "completed",
            "conclusion": conclusion,
            "created_at": f"2026-10-27T0{number}:00:00Z",
        }
        for number, (event, branch, conclusion, head) in enumerate(runs, 1)
    ]
    (replay.kitchen.home.stub / "browser-runs.json").write_text(
        json.dumps({"total_count": len(listed), "workflow_runs": listed[::-1]})
    )


def opened(replay, *checks, slug="sub-no-steer", number=557):
    """#557: the change to the view, reviewed clean, its check passed, and `checks` beside it."""
    files = {"features/jbus/src/jbus/view/app.js": "steered\n"}
    return replay.kitchen.crew(slug, number, files, checks=(CHECKED, *checks))


def test_the_replay_of_557_its_own_browser_red_holds_it(replay):
    """#557's rollup: a browser run skipped while it was a draft, then one that failed."""
    main_ran(replay, ("schedule", "main", "success", "1" * 40))
    head = opened(replay, BROWSER_DRAFT, {**BROWSER_RED, "startedAt": STARTED})
    said = replay.run()
    assert said == [f"wait 557 {url(557)}: {ready.BROWSER_RED.format(head=head[:12])}"]
    assert ready.BROWSER_RED.step == "check"
    assert not (replay.kitchen.home.stub / "merged-557").exists()


def test_a_head_with_no_browser_run_merges(replay):
    """A pull request that does not touch the view has no browser run, and never waits for one,
    nor asks GitHub about main's."""
    opened(replay)
    assert [line.split()[:2] for line in replay.run()] == [["merged", "557"]]
    assert not (replay.kitchen.home.stub / "asked-runs").exists()


def test_a_head_whose_browser_run_passed_merges(replay):
    opened(replay, BROWSER_GREEN)
    assert [line.split()[:2] for line in replay.run()] == [["merged", "557"]]


def test_a_browser_run_still_going_is_waited_for_as_any_pending_run(replay):
    opened(replay, BROWSER_RUNNING)
    assert replay.run() == [f"wait 557 {url(557)}: browser has not passed"]


def test_a_red_main_s_own_browser_run_has_is_main_s_and_waits_as_a_red_main(replay):
    red = "2" * 40
    main_ran(
        replay, ("schedule", "main", "success", "1" * 40), ("schedule", "main", "failure", red)
    )
    opened(replay, BROWSER_RED)
    assert replay.run() == [f"wait 557 {url(557)}: {ready.MAIN_RED.format(sha=red[:12])}"]
    (asked,) = (replay.kitchen.home.stub / "asked-runs").read_text().splitlines()
    assert "branch=main" in asked and "status=completed" in asked


def test_main_s_browser_red_that_a_later_run_of_main_ended_is_not_main_s(replay):
    """A pull request's own runs, and a manual run off main, say nothing of main."""
    main_ran(
        replay,
        ("schedule", "main", "failure", "2" * 40),
        ("workflow_dispatch", "main", "success", "3" * 40),
        ("pull_request", "main", "failure", "4" * 40),
        ("workflow_dispatch", "other", "failure", "5" * 40),
    )
    head = opened(replay, BROWSER_RED)
    assert replay.run() == [f"wait 557 {url(557)}: {ready.BROWSER_RED.format(head=head[:12])}"]


def test_the_fix_of_main_s_browser_red_is_held_by_its_own_red(replay):
    """The row jbus files for main's browser red is the fix that merges first: its own red is
    its own, so its crew is told, and it does not wait on itself."""
    main_ran(replay, ("schedule", "main", "failure", "2" * 40))
    head = opened(replay, BROWSER_RED, slug="browser-red-2026-10-27")
    assert replay.run() == [f"wait 557 {url(557)}: {ready.BROWSER_RED.format(head=head[:12])}"]
    assert rows.BROWSER_FIX == watch.BROWSER.prefix


def test_main_s_browser_runs_that_github_does_not_give_leave_the_red_the_pull_request_s(replay):
    head = opened(replay, BROWSER_RED)
    assert replay.run() == [f"wait 557 {url(557)}: {ready.BROWSER_RED.format(head=head[:12])}"]


def test_a_pull_request_short_of_its_review_says_that_first(replay):
    """As for a failed check (#529), a pull request short of something else says that."""
    head = opened(replay, BROWSER_RED)
    replay.kitchen.brief("sub-no-steer", "a" * 40)
    said = replay.run()
    assert said and ready.BROWSER_RED.format(head=head[:12]) not in said[0]
