"""A required check with no run at the head is told apart from one still running (D1 of
day-audit-1026-3). On 2026-10-26 macos became a required check at 18:59:51Z, but macos.yml reached
main only at 19:11Z, so five pull requests had heads with no macos run, and `jmerge` said "macos
has not passed" of each for an hour, as of a run at work. A check with no run at the head gets its
own reason, and where it is the only thing held against the pull request and the base moved since
its check started, `jmerge` asks GitHub to merge the base into the branch, once for a head and a
base tip, as for a base that moved under a green pull request. Then GitHub runs the new workflow
at the updated head. A hold on that reason is no wait on the merge runner, so it wakes its home
(`clock.held`).

A required check that waits on other jobs of its workflow, as `check` waits on its four shards, is
not listed at the head until they end, while GitHub runs them (merge-wait-1, 2026-10-28: #610's
`check has no run at ebd54cb4de4e` while its shards ran 14:06:50 to 14:15:01Z). It waits on that
run, queued or running, and not as a check with no run: no base merge is asked, and the hold is a
wait on the runner.

The tests run the command as `test_jmerge_rejudge` does, against a real origin and a fake `gh`."""

import json

from jmerge import ready
from test_home_merge import BORDERS, PASSED, RUNNING, run
from test_jbus_held import Held
from test_jmerge_fresh import git, url
from test_jmerge_rejudge import FIXED, STARTED, Replay

REQUIRED = "check\nborders\nmacos\n"
CHECKED = {**PASSED, "startedAt": STARTED}
MOVED = "GitHub was asked to merge main at {tip} into it: main moved after its check started"


def replay_of(tmp_path, *checks):
    """A pull request whose check and borders passed, and whose rollup has `checks` beside them,
    in a repo that requires check, borders and macos."""
    replay = Replay(tmp_path, fresh=False)
    (replay.kitchen.home.state / "required-checks").write_text(REQUIRED)
    head = replay.kitchen.crew("one", 479, {"one.txt": "ours\n"}, checks=(CHECKED, *checks))
    (replay.kitchen.home.stub / "branch-479").write_text("one")
    return replay, head


def listed(replay, head, checks):
    """GitHub's listing once the pull request is at `head`, with `checks`."""
    pull = replay.kitchen.pulls["one"]
    pull |= {"headRefOid": head, "statusCheckRollup": list(checks)}
    (replay.kitchen.home.stub / "list.json").write_text(json.dumps([pull]))


def test_a_required_check_with_no_run_asks_github_to_update_the_branch_once_for_a_head(tmp_path):
    replay, head = replay_of(tmp_path)
    tip = replay.main_at({".github/workflows/macos.yml": "on: pull_request\n"}, FIXED, "green")
    said = replay.run()
    assert said == [f"wait 479 {url(479)}: {MOVED.format(tip=tip[:12])}"]
    assert not any("macos has not passed" in line for line in said)
    assert replay.updated() == ["479"]
    assert replay.run() == said
    assert replay.updated() == ["479"]
    updated = git(replay.kitchen.origin, "rev-parse", "refs/heads/one")
    assert updated != head
    listed(replay, updated, (PASSED, BORDERS, run("SUCCESS", "macos")))
    (merged,) = replay.run()
    assert merged.startswith("merged 479 ")


def test_with_the_base_unmoved_it_waits_on_its_own_reason_and_asks_nothing(tmp_path):
    replay, head = replay_of(tmp_path)
    said = replay.run()
    assert said == [f"wait 479 {url(479)}: macos has no run at {head[:12]}"]
    assert replay.updated() == []


def test_a_running_macos_still_waits_as_today_and_asks_nothing(tmp_path):
    replay, _ = replay_of(tmp_path, {**RUNNING, "name": "macos"})
    replay.main_at({"main.txt": "theirs\n"}, FIXED, "green")
    assert replay.run() == [f"wait 479 {url(479)}: macos has not passed"]
    assert replay.updated() == []


def shard(status):
    """A shard of the check workflow, which GitHub lists before the job named `check` exists."""
    return {**run("", "check 1 of 4", status), "workflowName": "check"}


def live_of(tmp_path, status):
    """A pull request whose borders and macos passed, and whose check workflow is at work with
    no job named `check` listed yet, in a repo whose main moved since."""
    replay = Replay(tmp_path, fresh=False)
    (replay.kitchen.home.state / "required-checks").write_text(REQUIRED)
    checks = (BORDERS, {**run("SUCCESS", "macos"), "startedAt": STARTED}, shard(status))
    head = replay.kitchen.crew("one", 479, {"one.txt": "ours\n"}, checks=checks)
    (replay.kitchen.home.stub / "branch-479").write_text("one")
    replay.main_at({"main.txt": "theirs\n"}, FIXED, "green")
    return replay, head


def test_a_check_whose_workflow_runs_reads_as_running_and_asks_nothing(tmp_path):
    replay, head = live_of(tmp_path, "IN_PROGRESS")
    said = replay.run()
    assert said == [f"wait 479 {url(479)}: check's run at {head[:12]} is running"]
    assert ready.code_of(said[0].split(": ", 1)[1]) == "live-run"
    assert replay.updated() == []


def test_a_check_whose_workflow_is_queued_reads_as_queued(tmp_path):
    replay, head = live_of(tmp_path, "QUEUED")
    assert replay.run() == [f"wait 479 {url(479)}: check's run at {head[:12]} is queued"]
    assert replay.updated() == []


def test_a_check_whose_workflow_ended_with_no_check_job_has_no_run(tmp_path):
    """With nothing of its workflow at work, GitHub has no run of the check at the head."""
    replay, head = live_of(tmp_path, "COMPLETED")
    assert replay.run() == [f"wait 479 {url(479)}: check has no run at {head[:12]}"]


def test_rows_waiting_on_a_running_check_are_no_hold(kitchen):
    """A runner is at work on the run, so the rows wait on the merge runner and wake nobody."""
    held = Held(kitchen, ready.LIVE_RUN.format(check="check", head="abcdef123456", state="running"))
    held.until(31)
    assert held.told() == []


def test_rows_held_on_a_check_with_no_run_wake_their_home_after_the_hold_minutes(kitchen):
    """No runner is at work on a check that has no run, so the rows are a hold of their own."""
    held = Held(kitchen, ready.NO_RUN.format(check="macos", head="abcdef123456"))
    held.until(31)
    (told,) = held.told()
    assert "macos has no run at abcdef123456" in told
