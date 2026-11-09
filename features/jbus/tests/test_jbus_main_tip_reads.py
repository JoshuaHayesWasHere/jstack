"""What changes only when main moves is read once for each tip of main, not on every pass: main's
newest commits, which `watch.retro` and `jbus.reverts.macos` both read, and the files of
`.github/workflows/`, which `watch.watched` reads. Within one pass, a path GitHub already answered
is not asked again, so `watch._judged` reads a commit's runs and check runs once. A commit that
nothing judges, with no push run and no check run, is read for a quarter hour and then only as
main's tip."""

import json
from collections import Counter
from datetime import timedelta

import pytest

import jbus
from jbus import mainmoved, watch
from jbus.passes import Pass
from test_jbus_kitchen import NOW
from test_jbus_reverts import mac_flow
from test_jbus_watch import main_of

COMMITS = "/commits?sha="
LISTED = "&per_page=50"
WORKFLOWS = ".github/workflows"


def calls(kitchen, now):
    """Run a pass at `now` and return the `gh` calls it made, one line each."""
    log = kitchen.stub / "gh.log"
    before = len(log.read_text().splitlines()) if log.exists() else 0
    kitchen.poll(now)
    return log.read_text().splitlines()[before:]


def tip_reads(asked):
    """The calls for main's newest commits and for the workflow files, by what they read."""
    return Counter(
        "commits" if COMMITS in line and LISTED in line else "workflows"
        for line in asked
        if (COMMITS in line and LISTED in line)
        or (line.startswith("api graphql") and WORKFLOWS in line)
    )


def test_a_second_pass_at_the_same_tip_reads_neither_and_one_after_main_moved_reads_each_once(
    kitchen,
):
    """`watch.retro` and `jbus.reverts.macos`, which reads main's commits where the default branch
    holds macos.yml, share one read of them."""
    mac_flow(kitchen)
    (tip,) = main_of(kitchen, "success")
    first = calls(kitchen, NOW)
    assert tip_reads(first) == {"commits": 1, "workflows": 1}
    assert f"{COMMITS}{tip}{LISTED}" in "\n".join(first)
    assert f"at={tip}:{WORKFLOWS}" in "\n".join(first)
    assert tip_reads(calls(kitchen, NOW + timedelta(minutes=3))) == {}
    moved = "9" * 40
    listed = (kitchen.stub / "commits.json").read_text()
    kitchen.set("commits.json", [kitchen.commit(moved, "feat: moved"), *json.loads(listed)])
    after = calls(kitchen, NOW + timedelta(minutes=6))
    assert tip_reads(after) == {"commits": 1, "workflows": 1}
    assert f"{COMMITS}{moved}{LISTED}" in "\n".join(after)
    assert tip_reads(calls(kitchen, NOW + timedelta(minutes=9))) == {}


def test_a_pass_asks_github_for_a_commits_runs_and_check_runs_once(kitchen):
    """`mainmoved.tell` and `watch.retro` both judge commits of main in one pass, through
    `watch._judged`, and `jbus.reverts.macos` reads the same runs of each commit: each path is
    asked once a pass."""
    mac_flow(kitchen)
    main_of(kitchen, "failure", "success")
    for minutes in (0, 3):
        asked = calls(kitchen, NOW + timedelta(minutes=minutes))
        judged = [line for line in asked if "head_sha=" in line or line.endswith("/check-runs")]
        assert judged
        assert [line for line, n in Counter(judged).items() if n > 1] == []


@pytest.mark.parametrize(("code", "out"), [("1", ""), ("0", "{not json")])
def test_a_failed_or_garbled_answer_is_kept_for_no_tip_and_asked_again(kitchen, code, out):
    """Where GitHub fails or answers what is not JSON, the pass watches the nightlies alone and
    keeps nothing, neither for the tip nor for the pass, so the next ask goes to GitHub."""
    config = jbus.load()
    run = Pass(config, config.projects[0], NOW)
    kitchen.set("gh-down", "")
    kitchen.set("gh-code", code)
    kitchen.set("gh-out", out)
    path = "repos/{owner}/{repo}/commits?sha=main&per_page=50"
    assert watch._api(run, path) is None and path not in run.answers
    assert watch.watched(run) == list(watch.NIGHTLIES)
    assert not (run.state / watch.WORKFLOW_FILES).exists()
    (kitchen.stub / "gh-down").unlink()
    assert watch.watched(run) == list(watch.NIGHTLIES)
    assert json.loads((run.state / watch.WORKFLOW_FILES).read_text())["tip"] == run.tip()


def judged_reads(kitchen, sha, minutes, again=False):
    """Judge `sha` in a pass `minutes` after `NOW`, and return its answer and the reads of its
    runs and check runs that the pass made."""
    log = kitchen.stub / "gh.log"
    before = len(log.read_text().splitlines()) if log.exists() else 0
    config = jbus.load()
    run = Pass(config, config.projects[0], NOW + timedelta(minutes=minutes))
    answer = mainmoved.main_check(run, sha, again=again)
    asked = log.read_text().splitlines()[before:]
    return answer, [line for line in asked if sha in line]


def test_a_commit_nothing_judges_is_read_for_a_quarter_hour_then_only_as_mains_tip(kitchen):
    """cs-shelf's check.yml was disabled, so 17 of its merges had no run at all, and each pass
    read the runs and check runs of each: 35 of a pass's 62 calls to GitHub."""
    sha = "5" * 40
    for minutes in (0, 14, 15):
        answer, reads = judged_reads(kitchen, sha, minutes)
        assert (answer, len(reads)) == ("pending", 2)
    assert judged_reads(kitchen, sha, 16) == ("pending", [])
    answer, reads = judged_reads(kitchen, sha, 17, again=True)
    assert (answer, len(reads)) == ("pending", 2)


def test_a_commit_first_read_before_its_run_is_listed_is_judged_however_late_the_next_read(
    kitchen,
):
    """A pass may read a tip seconds after its push, before GitHub lists its run, and no pass
    may read it again for longer than the quarter hour: only a read that late settles it."""
    sha = "7" * 40
    assert judged_reads(kitchen, sha, 0)[0] == "pending"
    kitchen.set("check-runs.json", {sha: [{"status": "completed", "conclusion": "success"}]})
    answer, reads = judged_reads(kitchen, sha, 60)
    assert (answer, len(reads)) == ("green", 2)


def test_a_commit_whose_run_comes_within_the_quarter_hour_is_judged_and_kept(kitchen):
    sha = "6" * 40
    assert judged_reads(kitchen, sha, 0)[0] == "pending"
    kitchen.set("check-runs.json", {sha: [{"status": "completed", "conclusion": "success"}]})
    answer, reads = judged_reads(kitchen, sha, 5)
    assert (answer, len(reads)) == ("green", 2)
    assert judged_reads(kitchen, sha, 30) == ("green", [])
    assert sha not in jbus.read_json(kitchen.state / mainmoved.UNJUDGED, {})
