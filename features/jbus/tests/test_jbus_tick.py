"""The merge tick reads the check runs of each pending head, restates its pull request's line and
runs `jmerge` a few seconds after a required check fails or ends, apart from the pass, and spends
none of GitHub's API allowance while no job at the head changes (`jbus.tick`). It runs `jmerge
--if-free`, so one merger runs at a time (`features/jmerge/tests/test_jmerge_one_run.py`). It
keeps each head's ETag and verdict as it reads them, and the verdict `jmerge` ran for only once
`jmerge` ran to its end, so a tick that dies or finds `jmerge` busy loses no merge. While its
`jmerge` runs, it reads on every 10 s. The pass runs `jmerge --if-free` too. The tests run the
real tick and pass against the fakes (`test_jbus_kitchen.py`).
"""

import configparser
import itertools
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

import jbus
from jbus import alert, budget, launchd, merge, restated, states, tick, verbs, work
from jmerge import ready
from test_jbus_kitchen import NOW, Kitchen, rate_limit
from test_jbus_merge import LOCKING, held
from test_jbus_queue import add
from test_jbus_row_ends import sends

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


MERGED = "merged 7 alpha abc1234"
HEAD = "c" * 40
PULL = "https://example.test/pull/7"
RUNNING = f"wait 7 {PULL}: {ready.LIVE_RUN.format(check='check', head=HEAD[:12], state='running')}"
FAILED = f"wait: {ready.CHECK_FAILED.format(check='check')}"


def ticks(kitchen):
    said, before = [], len(kitchen.log("jmerge"))
    assert tick.tick(jbus.load(), said.append) == 0
    kitchen.tick_runs = getattr(kitchen, "tick_runs", 0) + len(kitchen.log("jmerge")) - before
    return said


def runs(kitchen):
    """The runs of `jmerge` the ticks started. The pass runs it with `--if-free` too, so the
    args alone do not tell them apart."""
    return getattr(kitchen, "tick_runs", 0)


def asked(kitchen):
    return [call for call in kitchen.log("gh") if call.startswith(f"api {tick.CHECK_RUNS % 7}")]


def going(kitchen, state=None):
    """A pull request whose check is still going (`state` None) or ended, as the pass saw it."""
    kitchen.set("open.json", [kitchen.opened("alpha", 7, state)])
    kitchen.poll()


SUITE = 11
"""The check suite of the workflow run `check` at #7's head."""


def job(name, conclusion=None, second=0, suite=SUITE):
    """A job GitHub lists at #7's head: going while it has no `conclusion`, or ended at `second`
    past the minute."""
    one = {"name": name, "check_suite": {"id": suite}, "status": "in_progress"}
    if conclusion:
        one |= {"status": "completed", "conclusion": conclusion}
        one["completed_at"] = f"2026-01-01T00:00:{second:02d}Z"
    return one


def listed(kitchen, *jobs):
    """GitHub lists `jobs` at #7's head, of the workflow run `check` there."""
    kitchen.set("check-runs.json", {HEAD: list(jobs)})
    kitchen.set("push-runs.json", {HEAD: [{"id": 100, "name": "check", "check_suite_id": SUITE}]})


def ended(kitchen, second):
    """The required check `check` passed at #7's head, its job ending at `second`."""
    listed(kitchen, job("check", "success", second))


@pytest.fixture
def watched(kitchen):
    going(kitchen)
    assert restated.pending(kitchen.state) == {7: HEAD}
    ended(kitchen, 1)
    ticks(kitchen)
    kitchen.set("jmerge.txt", f"{MERGED}\n")
    return kitchen


def test_a_check_that_ends_runs_jmerge_on_the_next_tick_and_sends_its_lines(watched):
    assert runs(watched) == 1
    ended(watched, 2)
    assert ticks(watched) == ["tick demo: a check ended, and jmerge ran"]
    assert runs(watched) == 2
    assert MERGED in watched.lines("jmerge")


def test_a_tick_with_no_check_ended_runs_no_jmerge_and_gets_a_304(watched):
    for _ in range(3):
        assert ticks(watched) == []
    assert runs(watched) == 1
    assert all("If-None-Match: " in call for call in asked(watched)[1:])


def test_with_no_check_going_a_tick_asks_github_nothing(kitchen):
    going(kitchen, "SUCCESS")
    assert json.loads((kitchen.state / tick.PENDING).read_text()) == []
    before = len(kitchen.log("gh"))
    ended(kitchen, 1)
    assert ticks(kitchen) == []
    assert len(kitchen.log("gh")) == before and runs(kitchen) == 0


def test_with_the_budget_held_a_tick_asks_github_as_usual(kitchen, monkeypatch):
    """A held budget leaves the tick as it is: a 304 spends none of the allowance, and a run that
    ended still gets its `jmerge`, which the floor is kept for. Each tick asks, and says nothing
    of the budget."""
    going(kitchen)
    kitchen.set("rate-limit.json", rate_limit(10))
    now = [NOW]
    monkeypatch.setattr(verbs, "clock", lambda: now[0])
    ended(kitchen, 1)
    assert ticks(kitchen) == ["tick demo: a check ended, and jmerge ran"]
    assert (len(asked(kitchen)), runs(kitchen)) == (1, 1)
    now[0] = NOW + timedelta(seconds=1)
    assert ticks(kitchen) == []
    assert len(asked(kitchen)) == 2 and runs(kitchen) == 1


def test_a_304_to_the_ticks_conditional_read_is_not_counted_against_the_budget(watched):
    """gh exits 1 on a 304, and GitHub counts none of it against the allowance: `jbus budget
    --callers` counts the tick's one read of the head's check runs that changed, and the one read
    of its workflow runs for the suite it had not seen, and its 304s apart, as free."""
    for _ in range(3):
        assert ticks(watched) == []
    since = NOW - timedelta(days=3650)
    lines = budget.callers(watched.state_dir, since).splitlines()
    tick_lines = [line.split() for line in lines if "jbus.tick._asked" in line]
    assert tick_lines == [
        ["1", "jbus.tick._asked", "<", "jbus.tick._read", "(0", "failed)"],
        ["1", "jbus.tick._asked", "<", "jbus.tick._suites", "(0", "failed)"],
        ["3", "jbus.tick._asked", "<", "jbus.tick._read"],
    ]
    assert "and 3 answered 304, which spend nothing:" in lines


def test_a_busy_jmerge_leaves_the_ended_run_to_the_next_tick(watched):
    watched.set("jmerge-busy", "")
    ended(watched, 2)
    assert ticks(watched) == ["tick demo: a check ended, and jmerge did not run to its end"]
    (watched.stub / "jmerge-busy").unlink()
    assert ticks(watched) == ["tick demo: a check ended, and jmerge ran"]
    assert MERGED in watched.lines("jmerge")
    assert ticks(watched) == []


def test_a_jmerge_that_fails_leaves_the_ended_run_to_the_next_tick(watched):
    watched.set("jmerge-says", "wait: could not ask GitHub: HTTP 502")
    ended(watched, 2)
    ticks(watched)
    (watched.stub / "jmerge-says").unlink()
    assert ticks(watched) == ["tick demo: a check ended, and jmerge ran"]


def test_a_tick_that_dies_before_jmerge_ends_loses_no_merge(watched, monkeypatch):
    def dies(run, read):
        raise KeyboardInterrupt

    ran = merge.tick
    monkeypatch.setattr(merge, "tick", dies)
    ended(watched, 2)
    with pytest.raises(KeyboardInterrupt):
        ticks(watched)
    monkeypatch.setattr(merge, "tick", ran)
    assert ticks(watched) == ["tick demo: a check ended, and jmerge ran"]
    assert MERGED in watched.lines("jmerge")


def test_the_pass_runs_jmerge_whatever_the_tick_did(watched):
    """What the tick missed, the next pass does: it runs `jmerge --if-free` itself. Where a run
    of the tick's holds the run lock, the pass does nothing and counts no failure, and the next
    pass that finds it free merges."""
    watched.set("jmerge-busy", "")
    watched.poll()
    assert watched.log("jmerge")[-1] == "--if-free"
    assert MERGED not in watched.lines("jmerge")
    assert alert.jmerge("demo") not in alert.streaks(watched.state_dir)
    (watched.stub / "jmerge-busy").unlink()
    watched.poll()
    assert MERGED in watched.lines("jmerge")


def test_the_tick_leaves_the_jmerge_streak_to_the_pass(watched):
    watched.set("jmerge-dies", "jmerge: gh is not installed")
    for run_id in range(2, 8):
        ended(watched, run_id)
        ticks(watched)
    assert watched.lines("alert") == []


def test_a_tick_whose_jmerge_held_the_lock_past_its_timeout_counts_a_failure(watched, monkeypatch):
    """The pass no longer waits on a tick's run, so it cannot see one that does not end: the
    tick counts its own `jmerge` that held the run lock past `JMERGE_TIMEOUT`, and three in a
    row alert as the pass's do."""
    script = watched.stub / "jmerge"
    script.write_text(LOCKING.format(python=sys.executable, stub=str(watched.stub)))
    watched.set("jmerge-sleep", "5")
    monkeypatch.setattr(merge, "JMERGE_TIMEOUT", 1)
    for run_id in range(2, 5):
        ended(watched, run_id)
        ticks(watched)
    assert alert.streaks(watched.state_dir)[alert.jmerge("demo")]["count"] == 3
    (alerted,) = watched.lines("alert")
    assert alerted.startswith("alert: jmerge demo failed 3 times in a row since ")


def test_a_skill_the_tick_merged_is_told_to_each_thread_out_on_the_next_pass(watched):
    """jmerge prints a `merged` line once, so the tick keeps a merge that changed a skill for
    `reload.tell` (`reload.json`), and the next pass tells each thread out that loaded it."""
    crew = watched.t3.thread("alpha")
    watched.set(
        "jmerge.txt", 'merged 7 alpha abc1234def5 "a skill", skills changed: crew, revert: x\n'
    )
    ended(watched, 2)
    ticks(watched)
    watched.set("jmerge.txt", "")
    watched.poll(NOW + timedelta(minutes=1))
    told = [one for one in sends(watched) if one["threadId"] == crew["threadId"]]
    assert len(told) == 1 and "skills: crew." in told[0]["message"]


@pytest.fixture
def on_check(kitchen):
    """The row `alpha`, whose pull request #7 is on the check step while its check runs, as the
    pass judged it."""
    add(kitchen, "alpha")
    kitchen.brief("alpha", f"\n## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n")
    kitchen.t3.thread("alpha", "completed")
    going(kitchen)
    kitchen.set("jmerge.txt", f"{RUNNING}\n")
    kitchen.poll()
    assert line(kitchen)["value"] == "check"
    return kitchen


def line(kitchen, key="alpha"):
    kept = json.loads((kitchen.state / work.NAME).read_text())
    return {one["key"]: one for one in kept["work"]}[key]


def check_ended(kitchen, second, conclusion):
    """GitHub lists the job of the required check `check` at #7's head as ended."""
    listed(kitchen, job("check", conclusion, second))


def before_jmerge(monkeypatch, kitchen):
    """Keep #7's line of `work.json` as it is when the tick starts `jmerge`."""
    seen, ran = [], merge.tick

    def tick_of(run, read):
        seen.append(line(kitchen))
        return ran(run, read)

    monkeypatch.setattr(merge, "tick", tick_of)
    return seen


def test_a_changed_runs_list_restates_the_rows_line_before_jmerge_runs(on_check, monkeypatch):
    """A check that failed reaches #7's line as soon as GitHub lists its run, before the tick's
    `jmerge` runs, with the reason `jmerge` gives it, which `jmerge` then agrees with."""
    seen = before_jmerge(monkeypatch, on_check)
    check_ended(on_check, 1, "failure")
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    assert ticks(on_check) == [
        "tick demo: a check ended, and alpha's line says so",
        "tick demo: a check ended, and jmerge ran",
    ]
    (first,) = seen
    assert (first["value"], first["why"], first[restated.CHECKED]) == ("check", FAILED, "failed")
    assert (line(on_check)["why"], restated.CHECKED in line(on_check)) == (FAILED, False)
    assert on_check.events(states.DRIFT) == []


def test_a_check_that_ends_while_jmerge_lock_is_held_reaches_the_line(on_check):
    """With another run of `jmerge` holding its run lock, the tick's `jmerge` does not run, and
    the line says the check passed all the same. The next tick, still held, writes nothing again,
    and the tick's `jmerge` once free moves the pull request on."""
    script = on_check.stub / "jmerge"
    script.write_text(LOCKING.format(python=sys.executable, stub=str(on_check.stub)))
    check_ended(on_check, 1, "success")
    on_check.set("jmerge.txt", f"{MERGED}\n")
    with held(on_check):
        assert ticks(on_check)[-1] == "tick demo: a check ended, and jmerge did not run to its end"
        said = line(on_check)
        assert said["why"] == "wait: check passed, and jmerge has not judged it yet"
        assert said[restated.CHECKED] == "passed"
        assert ticks(on_check) == ["tick demo: a check ended, and jmerge did not run to its end"]
        assert line(on_check) == said
    assert ticks(on_check) == ["tick demo: a check ended, and jmerge ran"]
    assert line(on_check)["facts"]["pull"] == "merged"
    assert on_check.events(states.DRIFT) == []


def test_a_304_restates_nothing(on_check):
    check_ended(on_check, 1, "failure")
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    assert ticks(on_check)[0] == "tick demo: a check ended, and alpha's line says so"
    assert line(on_check)["why"] == FAILED
    before = (on_check.state / work.NAME).read_bytes()
    assert ticks(on_check) == []
    assert (on_check.state / work.NAME).read_bytes() == before


def test_a_shard_that_failed_while_the_others_run_restates_the_line_as_failed(on_check):
    """One shard of eight failed, and the check's own job `check`, which needs all eight, is not
    listed yet: the line says the check failed now, not when the last shard ends. `jmerge`,
    which reads the check as running until `check` ends, does not undo it, and nor does the
    pass, which runs `jmerge` too."""
    listed(
        on_check,
        job("reuse", "success", 1),
        job("check 1 of 8"),
        job("check 2 of 8", "failure", 9),
        job("check 3 of 8"),
    )
    assert ticks(on_check) == [
        "tick demo: a check ended, and alpha's line says so",
        "tick demo: a check ended, and jmerge ran",
    ]
    said = line(on_check)
    assert (said["value"], said["why"], said[restated.CHECKED]) == ("check", FAILED, "failed")
    on_check.poll()
    assert line(on_check)["why"] == FAILED
    assert on_check.events(states.DRIFT) == []


def test_a_required_job_not_listed_yet_keeps_the_check_going(on_check):
    """Every shard passed, but `check`, which waits on them, is not listed yet: the check is
    still going, so the line says nothing new and `jmerge` does not run."""
    before = line(on_check)
    listed(on_check, *(job(f"check {n} of 8", "success", n) for n in range(1, 9)))
    assert ticks(on_check) == []
    assert line(on_check) == before
    assert runs(on_check) == 0


def test_a_required_job_that_ended_otherwise_leaves_the_line_to_jmerge_and_runs_it(on_check):
    """`check` ended cancelled, neither passed nor failed: the tick says nothing of it on the
    line, and runs `jmerge`, whose reason for it is the line's."""
    before = line(on_check)
    listed(on_check, job("check", "cancelled", 4))
    assert ticks(on_check) == ["tick demo: a check ended, and jmerge ran"]
    assert runs(on_check) == 1
    assert restated.CHECKED not in line(on_check)
    assert line(on_check)["why"] == before["why"]


@pytest.mark.parametrize(
    "other",
    [
        ready.LIVE_RUN.format(check="check", head="d" * 12, state="running"),
        ready.NOT_PASSED.format(check="check"),
    ],
    ids=["running-at-another-head", "not-passed"],
)
def test_jmerge_that_judges_the_check_otherwise_corrects_the_line_and_logs_drift(on_check, other):
    """The tick's word is the check runs at the head it read; `jmerge`'s is the pull request's
    checks. Where `jmerge`, run after the tick restated the line, finds the check running at
    another head, as after a push, or not passed, a verdict that names no head, its verdict
    stands, and the line is logged as drift, quietly."""
    check_ended(on_check, 1, "failure")
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {other}\n")
    ticks(on_check)
    assert line(on_check)["why"] == f"wait: {other}"
    (drift,) = [one["line"] for one in on_check.events(states.DRIFT)]
    assert drift.startswith("work-drift alpha: the tick's check failed (")


def test_a_check_suite_the_runs_list_does_not_show_yet_is_asked_of_again_on_the_next_200(
    on_check,
):
    """GitHub lists `check`'s job, failed, before its workflow run reaches the head's runs list:
    the job belongs to no workflow yet, so the line says nothing new. Once the check runs change
    and the runs list shows the run, the next tick asks the runs list again, and the line says
    the check failed."""
    late = SUITE + 1
    before = line(on_check)
    on_check.set("check-runs.json", {HEAD: [job("check", "failure", 1, suite=late)]})
    on_check.set("push-runs.json", {HEAD: [{"id": 100, "name": "other", "check_suite_id": SUITE}]})
    assert ticks(on_check) == []
    assert line(on_check) == before
    on_check.set(
        "check-runs.json",
        {HEAD: [job("check", "failure", 1, suite=late), job("other", "success", 0)]},
    )
    on_check.set(
        "push-runs.json",
        {
            HEAD: [
                {"id": 100, "name": "other", "check_suite_id": SUITE},
                {"id": 101, "name": "check", "check_suite_id": late},
            ]
        },
    )
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    assert ticks(on_check)[0] == "tick demo: a check ended, and alpha's line says so"
    assert line(on_check)["why"] == FAILED


def test_a_job_with_no_time_it_ended_leaves_the_line_to_jmerge(on_check):
    """A job GitHub gives no time it ended restates nothing and runs no `jmerge`: the pass's run
    judges the line."""
    listed(on_check, {"name": "check", "check_suite": {"id": SUITE}, "conclusion": "failure"})
    before = line(on_check)
    assert ticks(on_check) == []
    assert line(on_check)["why"] == before["why"]


def watching(kitchen):
    """The pull requests the tick watches, each by its number and the head the pass saw."""
    kept = json.loads((kitchen.state / tick.PENDING).read_text())
    return [{"number": one["number"], "head": one["head"]} for one in kept]


def test_a_rollup_that_says_passed_before_its_check_appears_keeps_the_pull_request_pending(
    on_check,
):
    """#1246: the pass read #7's rollup before its job `check` was in it, so the rollup said
    `passed` while `jmerge` still saw `check` running. The pass keeps #7's head for the tick,
    which asks GitHub and restates the line once the run ends."""
    on_check.set("open.json", [on_check.opened("alpha", 7, "SUCCESS")])
    on_check.poll()
    assert restated.pending(on_check.state) == {7: HEAD}
    check_ended(on_check, 1, "success")
    before = len(asked(on_check))
    assert ticks(on_check)[0] == "tick demo: a check ended, and alpha's line says so"
    assert len(asked(on_check)) == before + 1


def test_a_rows_pull_request_stays_watched_after_its_verdict_so_a_later_push_reaches_the_tick(
    on_check,
):
    """#7's check failed, and the tick and `jmerge` both said so. The pass after keeps watching
    #7 all the same, since a row's line names it: while nothing changes at its head a tick costs
    a 304 and runs no `jmerge`. A head pushed later reaches the next tick, with no pass
    between."""
    check_ended(on_check, 1, "failure")
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    ticks(on_check)
    on_check.set("open.json", [on_check.opened("alpha", 7, "FAILURE")])
    on_check.poll()
    assert restated.pending(on_check.state) == {7: HEAD}
    ran = runs(on_check)
    assert ticks(on_check) == []
    assert runs(on_check) == ran and "If-None-Match: " in asked(on_check)[-1]
    later = "d" * 40
    on_check.set("open.json", [{**on_check.opened("alpha", 7, None), "headRefOid": later}])
    on_check.set("push-runs.json", {later: [{"id": 101, "name": "check", "check_suite_id": 12}]})
    on_check.set("check-runs.json", {later: [job("check", "failure", 30, suite=12)]})
    assert ticks(on_check)[-1] == "tick demo: a check ended, and jmerge ran"
    assert (line(on_check)["why"], line(on_check)[restated.ENDED]) == (FAILED, later)


def test_a_verdict_jmerge_gives_before_it_reads_the_checks_keeps_the_head(on_check):
    """`jmerge` judges a pull request's review before its checks, so a `jmerge` that waits on
    #7's review says nothing of them: with a rollup that says `passed` too early, the pass keeps
    #7's head for the tick."""
    on_check.set("open.json", [on_check.opened("alpha", 7, "SUCCESS")])
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.NO_REVIEW}\n")
    on_check.poll()
    assert restated.pending(on_check.state) == {7: HEAD}


MOVING = "e" * 40
"""The head of #8, a pull request whose checks change while #7's do not."""


def asks(kitchen, number):
    path = tick.CHECK_RUNS % number
    return sum(call.startswith(f"api {path}") for call in kitchen.log("gh"))


@pytest.fixture
def settled(kitchen, monkeypatch):
    """#7, whose check has run for 16 minutes with nothing new at its head, and #8, opened beside
    it, whose check lists a new job on each tick. Both were read once 16 minutes ago. The clock
    is the test's: `at(seconds)` sets it that long past 16 minutes after `NOW`."""
    moving = {**kitchen.opened("beta", 8, None), "headRefOid": MOVING}
    kitchen.set("open.json", [kitchen.opened("alpha", 7, None), moving])
    kitchen.poll()
    now = [NOW]
    monkeypatch.setattr(verbs, "clock", lambda: now[0])
    listed(kitchen, job("check"))
    ticks(kitchen)
    kitchen.at = lambda seconds: now.__setitem__(0, NOW + timedelta(minutes=16, seconds=seconds))
    kitchen.set("jmerge.txt", f"{MERGED}\n")
    return kitchen


def moved(kitchen, step):
    """#8's check lists one more job, as its shards start one by one."""
    runs = json.loads((kitchen.stub / "check-runs.json").read_text())
    runs[MOVING] = [job(f"check {n} of 10", suite=SUITE + 1) for n in range(step + 1)]
    kitchen.set("check-runs.json", runs)


def test_a_settled_head_is_asked_about_once_a_minute_and_a_moving_one_every_tick(settled):
    """Ten ticks 10 s apart: #7, whose head and checks have not changed for 15 minutes, is asked
    about on the first and on the one a minute after it; #8, whose checks change, on each."""
    before = {7: asks(settled, 7), 8: asks(settled, 8)}
    for step in range(10):
        settled.at(10 * step)
        moved(settled, step)
        ticks(settled)
    assert (asks(settled, 7) - before[7], asks(settled, 8) - before[8]) == (2, 10)


def pushed(kitchen):
    later = "d" * 40
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7, None), "headRefOid": later}])
    kitchen.set("check-runs.json", {later: [job("check", suite=12)]})


def check_run(kitchen):
    """A second check run at #7's head, one that passed, beside the one still going."""
    pull = kitchen.opened("alpha", 7, None)
    done = {"status": "COMPLETED", "conclusion": "SUCCESS"}
    kitchen.set("open.json", [{**pull, "statusCheckRollup": [*pull["statusCheckRollup"], done]}])


def main_merged(kitchen):
    kitchen.set("commits.json", [kitchen.commit("f" * 40)])


@pytest.mark.parametrize("change", [pushed, check_run, main_merged])
def test_any_change_the_pass_sees_has_a_settled_head_asked_about_every_tick_again(settled, change):
    """The pass sees #7's head pushed, its checks change, or main move: from the next tick on, #7
    is asked about every 10 s again, though GitHub's answer for its check runs is the same."""
    settled.at(0)
    ticks(settled)
    settled.at(10)
    before = asks(settled, 7)
    ticks(settled)
    assert asks(settled, 7) == before
    change(settled)
    settled.poll(NOW + timedelta(minutes=16, seconds=15))
    for step in (20, 30, 40):
        settled.at(step)
        ticks(settled)
    assert asks(settled, 7) == before + 3


def test_a_settled_pull_request_that_turns_green_merges_within_a_minute(settled):
    """#7's check passes a second after the tick asked about it: with no pass between, a tick
    within the next minute asks again, reads it, and runs `jmerge`, which merges #7."""
    settled.at(0)
    ticks(settled)
    ended(settled, 1)
    for step in range(1, 7):
        settled.at(10 * step)
        if ticks(settled) == ["tick demo: a check ended, and jmerge ran"]:
            break
    assert 10 * step <= 60 and MERGED in settled.lines("jmerge")


MANAGER = """#!/bin/sh
echo "$*" >> "{stub}/systemctl.log"
if [ "$2" != is-active ] && [ -f "{stub}/refused.txt" ]; then
    cat "{stub}/refused.txt" >&2
    exit 1
fi
case "$2" in
is-active) cat "{stub}/timer.txt"; [ "$(cat "{stub}/timer.txt")" = active ] ;;
start) echo active > "{stub}/timer.txt" ;;
stop) echo inactive > "{stub}/timer.txt" ;;
*) exit 1 ;;
esac
"""
"""A user manager with the one timer the pass starts and stops, active as the install leaves it
(`enable --now`), which refuses to start or stop it while `refused.txt` says why. The machine is
one whose units systemd runs, on macOS too, where `launchd.manager()` would say launchd."""


@pytest.fixture
def manager(kitchen, monkeypatch):
    monkeypatch.setattr(launchd, "manager", lambda: "systemd")
    stand_in = kitchen.stub / "systemctl"
    stand_in.write_text(MANAGER.format(stub=kitchen.stub))
    stand_in.chmod(0o755)
    (kitchen.stub / "timer.txt").write_text("active\n")
    return kitchen


def timer(kitchen):
    return (kitchen.stub / "timer.txt").read_text().strip()


def switched(kitchen):
    return [call for call in kitchen.log("systemctl") if "jbus-merge.timer" in call]


def test_the_tick_runs_only_while_a_pass_saw_a_check_going_and_starts_within_10_s(
    manager, monkeypatch
):
    """The install leaves `jbus-merge.timer` running. A pass of `jbus.service`, which names the
    timer, stops it while no project's `checks-pending.json` holds a pull request, so no tick
    starts, and starts it once one does. The timer's first tick then comes `OnActiveSec=` after
    the start, within 10 s, and the next ones every 10 s. A pass that changes nothing leaves it."""
    kitchen = manager
    monkeypatch.setenv(tick.TIMER, "jbus-merge.timer")
    said = kitchen.poll()
    assert json.loads((kitchen.state / tick.PENDING).read_text()) == []
    assert timer(kitchen) == "inactive"
    assert "tick: the tick watches no pull request, so jbus-merge.timer stops" in said
    kitchen.poll()
    assert [call for call in switched(kitchen) if "is-active" not in call] == [
        "--user stop jbus-merge.timer"
    ]
    going(kitchen)
    assert timer(kitchen) == "active"
    going(kitchen)
    going(kitchen, "SUCCESS")
    assert json.loads((kitchen.state / tick.PENDING).read_text()) == []
    assert timer(kitchen) == "inactive"
    assert [call for call in switched(kitchen) if "is-active" not in call] == [
        f"--user {verb} jbus-merge.timer" for verb in ("stop", "start", "stop")
    ]
    unit = configparser.ConfigParser(interpolation=None)
    unit.optionxform = str
    unit.read(REPO / "features" / "jbus" / "units" / "jbus-merge.timer")
    assert unit["Timer"]["OnActiveSec"] == unit["Timer"]["OnUnitActiveSec"] == "10s"
    service = (REPO / "features" / "jbus" / "units" / "jbus.service").read_text()
    assert f"Environment={tick.TIMER}=jbus-merge.timer" in service.splitlines()


def test_a_pass_that_no_unit_started_leaves_the_machines_timer_as_it_is(manager):
    """A pass that a test, a sandbox or a hand starts has no `JBUS_TICK_TIMER`, which only
    `jbus.service` sets, so it asks the user manager nothing of the timer."""
    going(manager)
    going(manager, "SUCCESS")
    assert switched(manager) == []
    assert timer(manager) == "active"


def test_a_pass_whose_stop_the_manager_refuses_says_so_and_the_next_pass_stops_it(
    manager, monkeypatch
):
    """The user manager refuses the stop: the pass says why in its log and the timer runs on.
    The next pass finds it running with nothing pending, and stops it."""
    monkeypatch.setenv(tick.TIMER, "jbus-merge.timer")
    (manager.stub / "refused.txt").write_text("Failed to connect to bus\n")
    said = manager.poll()
    assert "tick: systemctl --user stop jbus-merge.timer failed: Failed to connect to bus" in said
    assert timer(manager) == "active"
    (manager.stub / "refused.txt").unlink()
    assert "tick: the tick watches no pull request, so jbus-merge.timer stops" in manager.poll()
    assert timer(manager) == "inactive"


@pytest.fixture
def pushed(kitchen):
    """The row `alpha`, whose pull request #7 the last pass saw on the check step at an older
    head. #7's head `HEAD` is then pushed, and its check fails, between that pass and the next."""
    add(kitchen, "alpha")
    kitchen.brief("alpha", f"\n## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n")
    kitchen.t3.thread("alpha", "completed")
    older = {**kitchen.opened("alpha", 7, None), "headRefOid": "b" * 40}
    kitchen.set("open.json", [older])
    kitchen.set("jmerge.txt", f"{RUNNING}\n")
    kitchen.poll()
    assert watching(kitchen) == [{"number": 7, "head": "b" * 40}]
    check_ended(kitchen, 1, "failure")
    kitchen.set("open.json", [kitchen.opened("alpha", 7, "FAILURE")])
    return kitchen


def test_a_head_pushed_and_failed_between_two_passes_gets_the_ticks_failed(pushed, monkeypatch):
    """The pass never saw #7's head `HEAD` going: it was pushed, and its check failed, between two
    passes, and the pass's own `jmerge` was busy. The pass keeps the head for the tick all the
    same, since #7's line names no verdict at it, and the tick's next read puts `failed` on the
    line before its `jmerge` runs, and the pass keeps watching #7, a row's pull request."""
    pushed.set("jmerge-busy", "")
    pushed.poll()
    assert watching(pushed) == [{"number": 7, "head": HEAD}]
    (pushed.stub / "jmerge-busy").unlink()
    seen = before_jmerge(monkeypatch, pushed)
    pushed.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    assert ticks(pushed)[0] == "tick demo: a check ended, and alpha's line says so"
    (first,) = seen
    said = (first["why"], first[restated.CHECKED], first[restated.ENDED])
    assert said == (FAILED, "failed", HEAD)
    assert (line(pushed)["why"], line(pushed)[restated.ENDED]) == (FAILED, HEAD)
    pushed.poll()
    assert watching(pushed) == [{"number": 7, "head": HEAD}]


def test_a_drafts_head_pushed_and_failed_between_two_passes_gets_the_ticks_verdict(pushed):
    """#7 is a draft, which `jmerge` holds on the Result step whatever its checks say, so no run of
    `jmerge` names their end on its line. The pass that first sees the failed head keeps it for the
    tick, whose read of the failed job names the head as ended on the line, and the pass keeps
    watching #7, a row's pull request."""
    pushed.set("jmerge.txt", f"wait 7 {PULL}: {ready.HAND_DRAFT}\n")
    pushed.poll()
    assert watching(pushed) == [{"number": 7, "head": HEAD}]
    assert restated.ENDED not in line(pushed)
    ticks(pushed)
    assert (line(pushed)["facts"]["pull"], line(pushed)[restated.ENDED]) == ("result", HEAD)
    pushed.poll()
    assert watching(pushed) == [{"number": 7, "head": HEAD}]


OTHER = "e" * 40
"""The head of #8, a second pull request on the check step."""


@pytest.fixture
def two_on_check(on_check):
    """The rows `alpha` (#7) and `beta` (#8), both on the check step while their checks run."""
    add(on_check, "beta")
    other = "https://example.test/pull/8"
    on_check.brief("beta", f"\n## Result\nStatus: done\nBranch: beta   Pull request: {other}\n")
    on_check.t3.thread("beta", "completed")
    beta = {**on_check.opened("beta", 8, None), "headRefOid": OTHER}
    on_check.set("open.json", [on_check.opened("alpha", 7, None), beta])
    running = ready.LIVE_RUN.format(check="check", head=OTHER[:12], state="running")
    on_check.set("jmerge.txt", f"{RUNNING}\nwait 8 {other}: {running}\n")
    on_check.poll()
    assert watching(on_check) == [{"number": 7, "head": HEAD}, {"number": 8, "head": OTHER}]
    assert line(on_check, "beta")["value"] == "check"
    return on_check


def at_both(kitchen, mine, other):
    """GitHub lists `mine` at #7's head and `other` at #8's, each of its own run of `check`."""
    kitchen.set("check-runs.json", {HEAD: mine, OTHER: other})
    kitchen.set(
        "push-runs.json",
        {
            HEAD: [{"id": 100, "name": "check", "check_suite_id": SUITE}],
            OTHER: [{"id": 101, "name": "check", "check_suite_id": SUITE + 1}],
        },
    )


def test_the_tick_reads_on_while_its_jmerge_runs(two_on_check, monkeypatch):
    """sa-tick-jmerge-apart: a `jmerge` that merges first runs the merged-tree guards, which took
    68 to 86 s on 2026-11-08, and the tick read nothing for as long. #7's check passed, so the
    tick runs `jmerge`; #8's check fails while that run is still going. The tick reads on every
    10 s (`EVERY`, short here), so #8's line says it failed before #7's `jmerge` ends."""
    monkeypatch.setattr(tick, "EVERY", 0.05, raising=False)
    at_both(two_on_check, [job("check", "success", 1)], [job("check", suite=SUITE + 1)])
    seen, ran = [], merge.tick

    def slow(run, read):
        at_both(
            two_on_check,
            [job("check", "success", 1)],
            [job("check", "failure", 3, suite=SUITE + 1)],
        )
        until = time.monotonic() + 5
        while line(two_on_check, "beta")["why"] != FAILED and time.monotonic() < until:
            time.sleep(0.05)
        seen.append(line(two_on_check, "beta")["why"])
        return ran(run, read)

    monkeypatch.setattr(merge, "tick", slow)
    two_on_check.set("jmerge.txt", f"{MERGED}\n")
    said = ticks(two_on_check)
    assert seen == [FAILED]
    assert "tick demo: a check ended, and beta's line says so" in said
    assert said[-1] == "tick demo: a check ended, and jmerge ran"


def test_a_read_that_fails_while_jmerge_runs_still_keeps_that_runs_merge(two_on_check, monkeypatch):
    """A read of the tick's fails while its `jmerge` runs: the tick lets that run end and keeps
    what it said before the failure goes on, since `jmerge` prints its `merged` line once, so a
    merge that changed a skill still reaches the next pass's `reload.tell`."""
    monkeypatch.setattr(tick, "EVERY", 0.05)
    at_both(two_on_check, [job("check", "success", 1)], [job("check", suite=SUITE + 1)])
    crew = two_on_check.t3.thread("alpha")
    failed, ran, read = [], merge.tick, tick._reads

    def fails(run):
        failed.append(run)
        raise OSError("tick.json: no space left on device")

    def slow(run, heads):
        monkeypatch.setattr(tick, "_reads", fails)
        until = time.monotonic() + 5
        while not failed and time.monotonic() < until:
            time.sleep(0.05)
        return ran(run, heads)

    monkeypatch.setattr(merge, "tick", slow)
    two_on_check.set(
        "jmerge.txt", 'merged 7 alpha abc1234def5 "a skill", skills changed: crew, revert: x\n'
    )
    said = []
    with pytest.raises(OSError, match="no space left"):
        tick.tick(jbus.load(), said.append)
    assert failed and said[-1] == "tick demo: a check ended, and jmerge ran"
    monkeypatch.setattr(tick, "_reads", read)
    two_on_check.set("jmerge.txt", "")
    two_on_check.poll(NOW + timedelta(minutes=1))
    told = [one for one in sends(two_on_check) if one["threadId"] == crew["threadId"]]
    assert len(told) == 1 and "skills: crew." in told[0]["message"]


def test_a_head_pushed_after_the_passs_read_is_read_by_the_next_tick(pushed):
    """The pass read #7 at an older head, and kept it for the tick. `HEAD` is pushed after that
    read, and its check fails before the next pass. The tick, which the timer runs every 10 s
    while #7 is pending, asks for the check runs at #7's head as it is now, not at the head the
    pass saw, so its next read puts `failed` on the line at `HEAD`, with no pass between."""
    pushed.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    assert ticks(pushed)[0] == "tick demo: a check ended, and alpha's line says so"
    assert (line(pushed)["why"], line(pushed)[restated.ENDED]) == (FAILED, HEAD)


def test_a_head_whose_rollup_lists_no_checks_yet_stays_pending(on_check):
    """#7's head was just pushed, and GitHub lists no check at it yet: the pass keeps it for the
    tick, which reads its first job within 10 s of GitHub listing it."""
    on_check.set("open.json", [{**on_check.opened("alpha", 7), "statusCheckRollup": []}])
    on_check.poll()
    assert restated.pending(on_check.state) == {7: HEAD}
    assert ticks(on_check) == []
    check_ended(on_check, 1, "failure")
    assert ticks(on_check)[0] == "tick demo: a check ended, and alpha's line says so"


NINE = range(8, 17)
"""Nine pull requests besides #7 whose checks are still going, each at a head of its own and of
a run of `check` of its own."""


def head_of(number):
    return f"{number:040x}"


@pytest.fixture
def ten_pending(on_check):
    """#7, a row's pull request on the check step, and nine others, #8 to #16, all pending, each
    with its required job `check` still going."""
    others = [{**on_check.opened(f"other{n}", n, None), "headRefOid": head_of(n)} for n in NINE]
    on_check.set("open.json", [on_check.opened("alpha", 7, None), *others])
    on_check.poll()
    assert [one["number"] for one in watching(on_check)] == [7, *NINE]
    on_check.set(
        "check-runs.json",
        {HEAD: [job("check")], **{head_of(n): [job("check", suite=100 + n)] for n in NINE}},
    )
    on_check.set(
        "push-runs.json",
        {
            HEAD: [{"id": 100, "name": "check", "check_suite_id": SUITE}],
            **{
                head_of(n): [{"id": 200 + n, "name": "check", "check_suite_id": 100 + n}]
                for n in NINE
            },
        },
    )
    return on_check


def test_a_check_that_ends_reaches_its_line_before_the_other_reads_answer(ten_pending, monkeypatch):
    """sa-tick-reads-apart: ten pull requests are pending, and #7's check failed. GitHub holds
    its answer to each of the other nine reads until #7's line says so, or for 3 s. The tick
    asks for all ten at once and writes #7's line as its own answer lands, so each of the nine
    answers comes back with #7's line already written, not after them."""
    ten_pending.set(
        "check-runs.json",
        {
            **json.loads((ten_pending.stub / "check-runs.json").read_text()),
            HEAD: [job("check", "failure", 1)],
        },
    )
    ten_pending.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    others = {tick.CHECK_RUNS % n for n in NINE}
    written, asked_of, until = {}, tick._asked, time.monotonic() + 3

    def held(run, path, etag=""):
        if path in others:
            while line(ten_pending)["why"] != FAILED and time.monotonic() < until:
                time.sleep(0.02)
            written[path] = line(ten_pending)["why"] == FAILED
        return asked_of(run, path, etag)

    monkeypatch.setattr(tick, "_asked", held)
    said = ticks(ten_pending)
    assert "tick demo: a check ended, and alpha's line says so" in said
    assert written == dict.fromkeys(others, True)


def test_reads_of_one_pull_request_are_at_most_every_plus_1_s_apart_with_10_pending(
    ten_pending, monkeypatch
):
    """sa-checks-bound-measure-9 read #7 every 4 to 5 s with ten pull requests pending, since the
    tick asked for them one at a time. GitHub answers each read here in 0.4 s, and the timer
    starts a tick every `EVERY` seconds, or as soon as the last one ended where it ran longer:
    #7's reads are at most `EVERY` plus 1 s apart. `EVERY` is short here, since the 1 s is the
    tick's own part."""
    monkeypatch.setattr(tick, "EVERY", 1)
    read, asked_of = [], tick._asked

    def slow(run, path, etag=""):
        time.sleep(0.4)
        if path == tick.CHECK_RUNS % 7:
            read.append(time.monotonic())
        return asked_of(run, path, etag)

    monkeypatch.setattr(tick, "_asked", slow)
    for _ in range(3):
        started = time.monotonic()
        assert ticks(ten_pending) == []
        time.sleep(max(0.0, started + tick.EVERY - time.monotonic()))
    apart = [later - earlier for earlier, later in itertools.pairwise(read)]
    assert len(read) == 3 and max(apart) <= tick.EVERY + 1, apart
