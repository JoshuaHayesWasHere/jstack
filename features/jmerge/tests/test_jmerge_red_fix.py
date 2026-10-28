"""While main is red, `jmerge` merges its fix and holds the rest. The fix was known only by its
slug, `main-red-<sha12>`, the row jbus files for the red. On 2026-10-27 from 17:28 the code that
fixed main came from two flow rows, #576 and #579 (`fl-`), so both were held, and once the
filed `main-red-` row closed with no pull request, nothing could merge and main could not move.

The fix is now also the pull request whose own check proves it: at a head that contains the red
tip, every check passed, and its jobs' logs say they ran each test that failed there
(`rows.ran_in`, of the tests `main.json` keeps). The slug still makes a fix. A pull request whose
check ran other tests, failed, or ran at a head without the red tip waits as before.

The tests run the command against a real origin and a fake `gh` (`test_jmerge_rejudge.Replay`)
that also gives each job's log."""

import json

import pytest

import test_home_merge as merge
from jmerge import mainjson, ready, rows
from test_jmerge_browser import RUNS, filed, main_ran
from test_jmerge_fresh import git, url, write
from test_jmerge_rejudge import BROKE, STARTED, Replay

LOGS = """\
    "api repos/{owner}/{repo}/actions/jobs/"*)
        job=${2%/logs}
        cat "$STUB/job-${job##*/}.log" ;;
"""
FAILED = "features/a/tests/test_a.py::test_red"
SELECTED = (
    "2026-10-27T17:40:01.1Z + uv run pytest -n 4 --dist worksteal --durations=25 "
    "-m 'not browser' --shard=1/4 features/a/tests/test_a.py features/b/tests/test_b.py\n"
)
OTHER = SELECTED.replace("features/a/tests/test_a.py ", "")
PARTS = "every part passed\n"
WHOLE = 'uv run pytest -n 4 --dist worksteal --durations=25 -m "not browser" --shard=2/4\n'


@pytest.fixture
def replay(tmp_path):
    replay = Replay(tmp_path, fresh=False)
    gh = replay.kitchen.home.stub / "gh"
    gh.write_text(gh.read_text().replace("    *) exit 64 ;;\n", LOGS + "    *) exit 64 ;;\n"))
    return replay


def red_main(replay, failed=(FAILED,)):
    """Main went red at a new tip, and jbus's `main.json` keeps the tests that failed there."""
    tip = replay.main_at({"a.txt": "broken\n"}, BROKE, "failed")
    record = mainjson.record(main=tip, at=BROKE, check="failed", broken=tip, failed=failed)
    (replay.state / mainjson.NAME).write_text(json.dumps(record))
    return tip


def closed_fix_row(replay, tip):
    """The `main-red-` row jbus filed for the red ended with no pull request."""
    row = {"slug": f"{mainjson.FIX}{tip[:12]}", "status": "done"}
    (replay.state / "queue.json").write_text(json.dumps([row]))


def job(number, conclusion="SUCCESS", name="check 1 of 4", log=SELECTED, replay=None):
    """A job of the pull request's check, and its log."""
    if replay is not None:
        (replay.kitchen.home.stub / f"job-{number}.log").write_text(log)
    link = f"https://github.com/someone/repo/actions/runs/5/job/{number}"
    return {**merge.run(conclusion, name), "startedAt": STARTED, "detailsUrl": link}


def flow_fix(replay, *checks, slug="fl-red-fix", number=576):
    """A flow row's pull request, reviewed clean, its check given by `checks`."""
    files = {"features/a/src/a.py": "fixed\n"}
    return replay.kitchen.crew(slug, number, files, checks=checks)


def test_a_flow_row_s_green_pull_request_whose_check_ran_the_failed_test_merges_past_a_red_main(
    replay,
):
    """The replay of #576: an `fl-` row's pull request, green over the red tip, whose check ran
    the file of the test that failed there. The filed `main-red-` row closed with no pull
    request."""
    tip = red_main(replay)
    closed_fix_row(replay, tip)
    flow_fix(replay, job(11, replay=replay), job(12, name="check", log=PARTS, replay=replay))
    assert [line.split()[:2] for line in replay.run()] == [["merged", "576"]]


def test_a_check_that_ran_the_whole_suite_proves_the_fix(replay):
    red_main(replay)
    flow_fix(
        replay, job(11, log=WHOLE, replay=replay), job(12, name="check", log=PARTS, replay=replay)
    )
    assert [line.split()[:2] for line in replay.run()] == [["merged", "576"]]


def test_a_check_that_ran_other_tests_does_not_prove_the_fix(replay):
    tip = red_main(replay)
    flow_fix(
        replay, job(11, log=OTHER, replay=replay), job(12, name="check", log=PARTS, replay=replay)
    )
    assert replay.run() == [f"wait 576 {url(576)}: {ready.MAIN_RED.format(sha=tip[:12])}"]


NARROWED = [
    WHOLE.replace("--shard=2/4", "--ignore features/a/tests"),
    WHOLE.replace("--shard=2/4", "--ignore=features/a/tests"),
    WHOLE.replace("--shard=2/4", "--collect-only"),
    WHOLE.replace('-m "not browser"', "-m slow"),
]
"""Commands that run less than the suite, or none of it, with options other than by name."""


@pytest.mark.parametrize("log", NARROWED)
def test_a_check_whose_command_leaves_out_or_stops_tests_does_not_prove_the_fix(replay, log):
    """A changed Makefile `PYTEST` or workflow may run the check so: an option jmerge does not
    know may narrow the run, so the command proves nothing."""
    tip = red_main(replay)
    flow_fix(
        replay, job(11, log=log, replay=replay), job(12, name="check", log=PARTS, replay=replay)
    )
    assert replay.run() == [f"wait 576 {url(576)}: {ready.MAIN_RED.format(sha=tip[:12])}"]


def test_a_passed_browser_run_does_not_prove_the_fix_its_check_did_not(replay):
    """The browser run's `pytest -m browser` names no path, but it ran only the browser tests:
    only the check's own parts say what ran of the rest."""
    tip = red_main(replay)
    browser = "2026-10-27T17:41:00Z uv run pytest -m browser\n"
    flow_fix(
        replay,
        job(11, log=OTHER, replay=replay),
        job(12, name="check", log=PARTS, replay=replay),
        job(14, name="browser", log=browser, replay=replay),
    )
    assert replay.run() == [f"wait 576 {url(576)}: {ready.MAIN_RED.format(sha=tip[:12])}"]


def test_a_check_whose_part_failed_does_not_prove_the_fix(replay):
    """A part that failed may have stopped before it ran the red test, so its check proves
    nothing, though another part's log names that test's file."""
    tip = red_main(replay)
    flow_fix(replay, job(11, replay=replay), job(13, "FAILURE", "check 3 of 4", replay=replay))
    assert replay.run() == [f"wait 576 {url(576)}: {ready.MAIN_RED.format(sha=tip[:12])}"]


def test_a_head_without_the_red_tip_does_not_prove_the_fix(replay):
    """Its check ran over a main before the red: it says nothing of the red."""
    flow_fix(replay, job(11, replay=replay), job(12, name="check", log=PARTS, replay=replay))
    tip = red_main(replay)
    assert replay.run() == [f"wait 576 {url(576)}: {ready.MAIN_RED.format(sha=tip[:12])}"]


def test_a_red_main_whose_failed_tests_are_not_known_lets_only_its_fix_row_through(replay):
    tip = red_main(replay, failed=())
    flow_fix(
        replay, job(11, log=WHOLE, replay=replay), job(12, name="check", log=PARTS, replay=replay)
    )
    assert replay.run() == [f"wait 576 {url(576)}: {ready.MAIN_RED.format(sha=tip[:12])}"]


def test_the_filed_fix_row_still_merges_by_its_slug(replay):
    tip = red_main(replay, failed=())
    flow_fix(replay, merge.PASSED | {"startedAt": STARTED}, slug=f"{mainjson.FIX}{tip[:12]}")
    assert [line.split()[:2] for line in replay.run()] == [["merged", "576"]]


@pytest.mark.parametrize(
    "log",
    [
        SELECTED,
        SELECTED.replace("-m 'not browser'", "-m not browser"),
        "\x1b[36;1m" + WHOLE + "\x1b[0m",
    ],
)
def test_a_log_s_one_pytest_command_says_what_ran(log):
    """bash's trace quotes, dash's does not, and make echoes the command it runs."""
    ran = rows.ran_in(log)
    assert ran is not None
    assert ran.covers(FAILED) == ("--shard=2/4" in log or "test_a.py" in log)
    assert not ran.covers("features/c/tests/test_c.py::test_other") or ran.every


@pytest.mark.parametrize(
    "log",
    [
        "no tests here\n",
        SELECTED + SELECTED,
        WHOLE.replace("--shard", "-k red --shard"),
        WHOLE.replace("--shard=2/4", "--deselect=x.py::y"),
        WHOLE.replace("--shard=2/4", "--lf"),
        *NARROWED,
    ],
)
def test_a_log_with_no_command_two_or_one_that_narrows_says_nothing(log):
    assert rows.ran_in(log) is None


def test_a_folder_covers_the_tests_under_it_and_a_failed_test_is_not_covered():
    ran = rows.Ran(over="r", paths=frozenset({"features/a/"}), failed=frozenset({FAILED}))
    assert ran.covers("features/a/tests/test_a.py::test_green")
    assert not ran.covers(FAILED)
    assert not ran.covers("features/ab/tests/test_ab.py::test_green")


def test_the_failed_tests_of_a_run_skip_the_job_that_gathers_its_parts():
    jobs = [("full 1 of 4", (FAILED,), 1), ("full", (), 0), ("full 2 of 4", ("b.py::t",), 1)]
    assert mainjson.failures(jobs) == [FAILED, "b.py::t"]


@pytest.mark.parametrize(
    "jobs",
    [
        [("full 1 of 4", (FAILED,), 1), ("full 3 of 4", (), 0)],
        [("full 1 of 4", (FAILED,), 3)],
        [("lint", (), 0)],
    ],
)
def test_a_run_with_a_failure_no_test_names_is_not_known_by_its_tests(jobs):
    assert mainjson.failures(jobs) == []


RUN_JOBS = """\
    "api repos/{owner}/{repo}/actions/runs/"*"/jobs"*)
        cat "$STUB/run-jobs.json" ;;
"""
BROWSER_FAILED = "features/jbus/tests/view/test_shots.py::test_moved"
BROWSER_LOG = (
    "2026-10-27T07:01:00Z uv run pytest -m browser\n"
    "FAILED {failed} - shots differ\n= 1 failed, 40 passed in 60.0s =\n"
)


@pytest.fixture
def browser(replay):
    gh = replay.kitchen.home.stub / "gh"
    stubbed = gh.read_text().replace("    *) exit 64 ;;\n", RUNS + RUN_JOBS + "    *) exit 64 ;;\n")
    gh.write_text(stubbed)
    return replay


@pytest.mark.parametrize("fails", [BROWSER_FAILED, "features/jbus/tests/view/test_app.py::test_x"])
def test_a_browser_run_that_passed_main_s_failed_browser_test_is_held_by_its_own_red(
    browser, fails
):
    """Main's last browser run failed a shot test, and the row jbus filed for it is open. A flow
    row's browser run that ran every browser test and passed that one is the fix of main's red,
    whatever its slug: it is held by its own red only. One that failed it too waits as for a red
    main."""
    main = browser.kitchen.home.main
    git(main, "pull", "-q", "--ff-only")
    write(main, {"b.txt": "red\n"})
    git(main, "commit", "-q", "-m", "red", at=BROKE)
    git(main, "push", "-q")
    red = git(main, "rev-parse", "HEAD")
    main_ran(browser, ("schedule", "main", "failure", red))
    filed(browser, 1)
    stub = browser.kitchen.home.stub
    (stub / "run-jobs.json").write_text(
        json.dumps({"jobs": [{"id": 31, "name": "browser", "conclusion": "failure"}]})
    )
    (stub / "job-31.log").write_text(BROWSER_LOG.format(failed=BROWSER_FAILED))
    own = job(32, "FAILURE", "browser", BROWSER_LOG.format(failed=fails), browser)
    head = flow_fix(browser, job(12, name="check", log=PARTS, replay=browser), own)
    own_red = ready.BROWSER_RED.format(head=head[:12])
    main_red = ready.MAIN_RED.format(sha=red[:12])
    expected = own_red if fails != BROWSER_FAILED else main_red
    assert browser.run() == [f"wait 576 {url(576)}: {expected}"]
