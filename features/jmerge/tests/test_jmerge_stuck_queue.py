"""The pull request at the head of `jmerge`'s line whose required run GitHub queued and never
started is restarted once, by a close and a reopen, which start a new run in the workflow's
concurrency group. Where the new run does not start either, it gives the line up to the next
pull request, as on a failed check. On 2026-11-04 #1028 held the line for over an hour on a macos
job GitHub kept queued, which neither `gh run cancel` nor `gh run rerun` moved, and five pull
requests waited behind it until the flow home closed and reopened it by hand. A run that started
and runs long is no stuck one, and gets no restart."""

import json
from datetime import UTC, datetime, timedelta

import pytest

import test_home_merge as merge
from jmerge import ready, rejudge
from test_jmerge_fresh import AFTER, LINES, Kitchen, asked, url
from test_jmerge_in_line import RUNNING, behind


@pytest.fixture
def kitchen(tmp_path):
    files = {"a.txt": LINES, "b.txt": LINES, "c.txt": LINES, "d.txt": LINES}
    kitchen = Kitchen(tmp_path, {**files, "Makefile": "check:\n"}, overlap=True)
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.crew("three", 8, {"c.txt": "ours\n" + LINES})
    return kitchen


def _ago(minutes):
    return f"{datetime.now(UTC) - timedelta(minutes=minutes):%Y-%m-%dT%H:%M:%SZ}"


def queued(minutes):
    """The check as GitHub lists a run it queued `minutes` ago and started none of: a queued
    check run's `startedAt` is when GitHub queued it."""
    return {**merge.run("", status="QUEUED"), "startedAt": _ago(minutes)}


def restarted(number, head, minutes):
    why = ready.QUEUED_RESTARTED.format(check="check", head=head[:12], minutes=minutes)
    return f"wait {number} {url(number)}: {why}"


def gave_up(number, head):
    why = ready.QUEUED_GAVE_UP.format(check="check", head=head[:12], minutes=ready.QUEUED_MINUTES)
    return f"wait {number} {url(number)}: {why}"


def unclosed(number, head, minutes):
    why = ready.QUEUED_UNCLOSED.format(
        check="check", head=head[:12], minutes=minutes, why="gh: could not close (HTTP 502)"
    )
    return f"wait {number} {url(number)}: {why}"


def aged(kitchen, number, key, minutes):
    """The restart of the pull request kept `key` `minutes` ago: time passing between runs."""
    path = kitchen.home.state / rejudge.NAME
    records = json.loads(path.read_text())
    records[str(number)]["stuck"][key] = (
        datetime.now(UTC) - timedelta(minutes=minutes)
    ).isoformat()
    path.write_text(json.dumps(records))


def listed(kitchen, *numbers):
    """GitHub lists these pull requests as open, and no other."""
    pulls = [one for one in kitchen.pulls.values() if one["number"] in numbers]
    (kitchen.home.stub / "list.json").write_text(json.dumps(pulls))


def held_by_seven(kitchen):
    """Main moves, and #7, first in merge order, takes the head of the line."""
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    assert kitchen.run() == [asked(7, tip), behind(8, 7)]
    return tip


def test_a_run_queued_past_the_bound_is_restarted_once_then_the_line_goes_to_the_next(kitchen):
    tip = held_by_seven(kitchen)
    head = kitchen.updated("two", queued(120))
    assert kitchen.run() == [restarted(7, head, 120), behind(8, 7)]
    assert [call.split()[:3] for call in kitchen.calls("pr close")] == [["pr", "close", "7"]]
    assert [call.split()[:3] for call in kitchen.calls("pr reopen")] == [["pr", "reopen", "7"]]

    kitchen.updated("two", queued(ready.QUEUED_MINUTES + 5))
    assert kitchen.run() == [gave_up(7, head), asked(8, tip)]
    assert kitchen.updates() == ["7", "8"]

    kitchen.updated("three", RUNNING)
    assert kitchen.run() == [gave_up(7, head), f"wait 8 {url(8)}: check has not passed"]
    assert len(kitchen.calls("pr close")) == 1
    assert len(kitchen.calls("pr reopen")) == 1


def test_the_new_run_gets_the_bound_of_its_own_and_no_second_restart(kitchen):
    held_by_seven(kitchen)
    head = kitchen.updated("two", queued(45))
    assert kitchen.run() == [restarted(7, head, 45), behind(8, 7)]
    kitchen.updated("two", queued(2))
    assert kitchen.run() == [f"wait 7 {url(7)}: check has not passed", behind(8, 7)]
    kitchen.updated("two", {**RUNNING, "startedAt": _ago(1)})
    assert kitchen.run() == [f"wait 7 {url(7)}: check has not passed", behind(8, 7)]
    assert len(kitchen.calls("pr close")) == 1

    kitchen.updated("two", AFTER)
    first, second = kitchen.run()
    assert first.startswith("merged 7 two ")
    assert second.startswith(f"wait 8 {url(8)}: GitHub was asked to merge main")


def test_a_run_that_started_and_runs_long_is_not_restarted(kitchen):
    held_by_seven(kitchen)
    kitchen.updated("two", {**RUNNING, "startedAt": _ago(240)})
    for _ in range(2):
        assert kitchen.run() == [f"wait 7 {url(7)}: check has not passed", behind(8, 7)]
    assert kitchen.calls("pr close") == kitchen.calls("pr reopen") == []


def test_a_run_queued_inside_the_bound_waits(kitchen):
    held_by_seven(kitchen)
    kitchen.updated("two", queued(ready.QUEUED_MINUTES - 5))
    assert kitchen.run() == [f"wait 7 {url(7)}: check has not passed", behind(8, 7)]
    assert kitchen.calls("pr close") == []


def test_a_reopen_that_failed_is_asked_again_on_the_next_run(kitchen):
    """A close that took and a reopen that did not leaves the pull request closed, and so off
    GitHub's list of open ones: the next run reopens it, once."""
    held_by_seven(kitchen)
    head = kitchen.updated("two", queued(120))
    (kitchen.home.stub / "no-reopen").write_text("")
    said = kitchen.run()
    why = ready.QUEUED_UNOPENED.format(
        check="check", head=head[:12], minutes=120, why="gh: could not reopen (HTTP 502)"
    )
    assert said == [f"wait 7 {url(7)}: {why}", behind(8, 7)]

    (kitchen.home.stub / "no-reopen").unlink()
    listed(kitchen, 8)
    assert kitchen.run()[0].startswith(f"wait 8 {url(8)}: GitHub was asked to merge main")
    assert len(kitchen.calls("pr reopen")) == 2
    listed(kitchen, 7, 8)
    kitchen.run()
    assert len(kitchen.calls("pr reopen")) == 2
    assert len(kitchen.calls("pr close")) == 1


def test_a_close_that_failed_leaves_the_restart_unspent(kitchen):
    """GitHub refused the close, so no new run started: the next run tries the restart again,
    and the line stays with the pull request, rather than going to the next as if it took."""
    held_by_seven(kitchen)
    head = kitchen.updated("two", queued(120))
    (kitchen.home.stub / "no-close").write_text("")
    assert kitchen.run() == [unclosed(7, head, 120), behind(8, 7)]
    assert kitchen.calls("pr reopen") == []

    (kitchen.home.stub / "no-close").unlink()
    assert kitchen.run() == [restarted(7, head, 120), behind(8, 7)]
    assert len(kitchen.calls("pr close")) == 2
    assert len(kitchen.calls("pr reopen")) == 1


def test_a_close_that_fails_for_the_restart_minutes_gives_the_line_up_and_says_why(kitchen):
    tip = held_by_seven(kitchen)
    head = kitchen.updated("two", queued(120))
    (kitchen.home.stub / "no-close").write_text("")
    kitchen.run()
    aged(kitchen, 7, "asked", ready.RESTART_MINUTES)
    why = ready.QUEUED_UNRESTARTED.format(
        check="check",
        head=head[:12],
        minutes=ready.RESTART_MINUTES,
        why="gh: could not close (HTTP 502)",
    )
    assert kitchen.run() == [f"wait 7 {url(7)}: {why}", asked(8, tip)]
    assert len(kitchen.calls("pr close")) == 1
    assert ready.code_of(why) == "queued-unrestarted"


def test_a_run_just_after_a_restart_that_took_keeps_the_line_till_github_lists_the_new_run(kitchen):
    """GitHub lists the new run seconds after the reopen, so the next run of `jmerge` can still
    see the old one: it keeps the line for `ready.RESTART_MINUTES`, and gives it up after."""
    tip = held_by_seven(kitchen)
    head = kitchen.updated("two", queued(120))
    assert kitchen.run() == [restarted(7, head, 120), behind(8, 7)]
    assert kitchen.run() == [restarted(7, head, 120), behind(8, 7)]
    assert len(kitchen.calls("pr close")) == 1

    aged(kitchen, 7, "took", ready.RESTART_MINUTES)
    assert kitchen.run() == [gave_up(7, head), asked(8, tip)]
    assert len(kitchen.calls("pr close")) == 1


def test_a_reopen_that_keeps_failing_stops_after_the_restart_minutes_and_says_so(kitchen):
    """The pull request stays closed: `jmerge` says on each run that its reopen is owed, and once
    it has tried for `ready.RESTART_MINUTES` it asks no more, a wait jbus raises to the home."""
    held_by_seven(kitchen)
    head = kitchen.updated("two", queued(120))
    (kitchen.home.stub / "no-reopen").write_text("")
    kitchen.run()
    listed(kitchen, 8)
    owed = ready.QUEUED_UNOPENED.format(
        check="check", head=head[:12], minutes=120, why="gh: could not reopen (HTTP 502)"
    )
    assert kitchen.run()[-1] == f"wait 7 {url(7)}: {owed}"
    assert len(kitchen.calls("pr reopen")) == 2

    aged(kitchen, 7, "asked", ready.RESTART_MINUTES)
    gone = ready.QUEUED_UNREOPENED.format(
        check="check",
        head=head[:12],
        minutes=ready.RESTART_MINUTES,
        why="gh: could not reopen (HTTP 502)",
    )
    for _ in range(2):
        assert kitchen.run()[-1] == f"wait 7 {url(7)}: {gone}"
    assert len(kitchen.calls("pr reopen")) == 2
    assert ready.code_of(gone) == "queued-unreopened"

    (kitchen.home.stub / "no-reopen").unlink()
    listed(kitchen, 7, 8)
    kitchen.updated("two", queued(ready.QUEUED_MINUTES - 5))
    assert not any(line.endswith(gone) for line in kitchen.run())
    assert len(kitchen.calls("pr close")) == 1


def _job(name, workflow, status, minutes):
    return {
        "__typename": "CheckRun",
        "name": name,
        "workflowName": workflow,
        "status": status,
        "conclusion": "SUCCESS" if status == "COMPLETED" else "",
        "startedAt": _ago(minutes),
    }


def _at(minutes):
    return datetime.fromisoformat(_ago(minutes).replace("Z", "+00:00"))


MACOS = ("check", "borders", "macos")


def test_queued_reads_a_macos_run_queued_after_its_select_job_ended():
    rollup = [
        _job("check", "check", "COMPLETED", 50),
        _job("borders", "borders", "COMPLETED", 50),
        _job("macos-select", "macos", "COMPLETED", 49),
        _job("macos", "macos", "QUEUED", 45),
    ]
    assert ready.queued(rollup, MACOS) == (("macos", _at(45)),)


def test_queued_reads_no_macos_run_while_its_select_job_runs():
    rollup = [_job("macos-select", "macos", "IN_PROGRESS", 3), _job("macos", "macos", "QUEUED", 1)]
    assert ready.queued(rollup, MACOS) == ()


def test_queued_falls_back_on_the_jobs_of_the_workflow_where_the_check_is_not_listed():
    """GitHub lists the job named `check` only once its shards end: shards all queued are a
    queued check, from the latest of them, and one shard at work is a run going."""
    shards = [_job(f"check {n} of 4", "check", "QUEUED", 40 - n) for n in range(1, 5)]
    assert ready.queued(shards) == (("check", _at(36)),)
    shards[0] = {**shards[0], "status": "IN_PROGRESS"}
    assert ready.queued(shards) == ()
    ended = [{**one, "status": "COMPLETED"} for one in shards]
    assert ready.queued(ended) == ()
