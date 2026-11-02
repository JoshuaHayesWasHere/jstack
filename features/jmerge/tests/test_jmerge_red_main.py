"""A red main holds no pull request (red-main-no-hold, Josh's pick of 2026-11-02, "Yes,
guess-free reverts"). Until then every pull request into main waited as `main is red at <sha12>,
its fix merges first` while jbus's `main.json` named a red tip: 4.7% of the PR-hours of the
merge-velocity audit, and the replayed p90 went from 304 to 203 minutes without it. A pull request
red at its own head is still held by its own checks, and jbus reverts the one clear culprit of a
red main (`jbus.reverts`), whose pull request merges here by the normal path with no review
(`jmerge.reverts`).

What a job's log says it ran (`rows.ran_in`) and the tests a red run failed
(`mainjson.failures`) still tell a pull request's own browser red from main's.

The tests run the command against a real origin and a fake `gh` (`test_jmerge_rejudge.Replay`)
that also gives each job's log."""

import json

import pytest

import test_home_merge as merge
from jmerge import mainjson, ready, reverts, rows
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
    replay = Replay(tmp_path)
    gh = replay.kitchen.home.stub / "gh"
    gh.write_text(gh.read_text().replace("    *) exit 64 ;;\n", LOGS + "    *) exit 64 ;;\n"))
    return replay


def red_main(replay, failed=(FAILED,)):
    """Main went red at a new tip, and jbus's `main.json` keeps the tests that failed there."""
    tip = replay.main_at({"a.txt": "broken\n"}, BROKE, "failed")
    record = mainjson.record(main=tip, at=BROKE, check="failed", broken=tip, failed=failed)
    (replay.state / mainjson.NAME).write_text(json.dumps(record))
    return tip


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


def test_a_green_pull_request_merges_while_main_is_red(replay):
    """Its check ran no test that failed at the red tip, and no `main-red-` row is open: it
    merged all the same, since main's red is not its own."""
    red_main(replay)
    flow_fix(
        replay, job(11, log=OTHER, replay=replay), job(12, name="check", log=PARTS, replay=replay)
    )
    assert [line.split()[:2] for line in replay.run()] == [["merged", "576"]]


def test_a_pull_request_red_at_its_own_head_is_still_held_while_main_is_red(replay):
    red_main(replay)
    flow_fix(replay, job(13, "FAILURE", "check", replay=replay))
    (said,) = replay.run()
    assert said.startswith(f"wait 576 {url(576)}: ") and "has failed" in said
    assert "main is red" not in said


def revert_pull(replay, recorded=True, number=900):
    """The pull request jbus opened to revert the culprit of a red main: green, with a brief that
    names it and no review. `reverts.json` keeps it where `recorded`."""
    branch = f"revert-576-fl-red-{number}"
    head = replay.kitchen.crew(branch, number, {"a.txt": "back\n"}, checks=(merge.PASSED,))
    pull = url(number)
    (replay.kitchen.home.tasks / f"{branch}.md").write_text(
        f"# {branch}: revert #576, which turned main red\nTask: jbus reverts it\n"
        f"Pull request: opened by jbus\n\n## Result\nStatus: done\n"
        f"Branch: {branch}   Pull request: {pull}\n"
    )
    if recorded:
        made = reverts.Revert("r" * 40, "fl-red", branch, head, pull)
        (replay.state / reverts.NAME).write_text(json.dumps({made.red: reverts.record(made)}))
    return head


def test_the_revert_jbus_opened_merges_by_the_normal_path_with_no_review(replay):
    red_main(replay)
    revert_pull(replay)
    said = replay.run()
    assert [line.split()[:2] for line in said] == [["merged", "900"]], said


def test_a_pull_request_on_a_revert_s_branch_that_jbus_did_not_open_waits_for_its_review(replay):
    red_main(replay)
    revert_pull(replay, recorded=False)
    assert replay.run() == [f"wait 900 {url(900)}: {ready.NO_REVIEW}"]


def test_a_revert_pushed_to_since_jbus_opened_it_waits_for_its_review(replay):
    red_main(replay)
    revert_pull(replay)
    made = reverts.read(replay.state)["r" * 40]
    moved = reverts.Revert(made.red, made.slug, made.branch, "e" * 40, made.pull)
    (replay.state / reverts.NAME).write_text(json.dumps({moved.red: reverts.record(moved)}))
    (said,) = replay.run()
    assert said.startswith(f"wait 900 {url(900)}: ")


NARROWED = [
    WHOLE.replace("--shard=2/4", "--ignore features/a/tests"),
    WHOLE.replace("--shard=2/4", "--ignore=features/a/tests"),
    WHOLE.replace("--shard=2/4", "--collect-only"),
    WHOLE.replace('-m "not browser"', "-m slow"),
    WHOLE.replace('-m "not browser"', "-m browser"),
]
"""Commands that run less than the suite, or none of it, with options other than by name."""


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
    ran = rows.ran_in(log, rows.CHECK)
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
    assert rows.ran_in(log, rows.CHECK) is None


def test_a_run_is_read_for_the_marker_its_caller_expects():
    """The check's `not browser` ran none of the browser tests, and the browser run's `browser`
    none of the rest, so each says nothing to the other's reader."""
    browser = "2026-10-27T17:41:00Z uv run pytest -m browser\n"
    assert rows.ran_in(browser, rows.BROWSER) == rows.Ran(every=True)
    assert rows.ran_in(browser, rows.CHECK) is None
    assert rows.ran_in(WHOLE, rows.BROWSER) is None


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
    whatever its slug: it is held by its own red only. One that failed it too is held by its
    own red as main's, and says so."""
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
    main_red = ready.MAIN_BROWSER_RED.format(head=head[:12], sha=red[:12])
    expected = own_red if fails != BROWSER_FAILED else main_red
    assert browser.run() == [f"wait 576 {url(576)}: {expected}"]
