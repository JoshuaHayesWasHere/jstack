"""The merge tick runs `jmerge` a few seconds after a check ends, apart from the pass, and spends
none of GitHub's API allowance while no check ends (`jbus.tick`). It runs `jmerge --if-free`, so
one merger runs at a time (`features/jmerge/tests/test_jmerge_one_run.py`), and it keeps what it
saw only once `jmerge` ran to its end, so a tick that dies or finds `jmerge` busy loses no merge.
The pass runs `jmerge --if-free` too. The tests run the real tick and pass against the fakes
(`test_jbus_kitchen.py`).
"""

import json
import sys
from datetime import timedelta

import pytest

import jbus
from jbus import alert, budget, merge, restated, states, tick, verbs, work
from jmerge import ready
from test_jbus_kitchen import NOW, Kitchen, rate_limit
from test_jbus_merge import LOCKING, held
from test_jbus_queue import add
from test_jbus_row_ends import sends


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
    return [call for call in kitchen.log("gh") if call.startswith(f"api {tick.RUNS}")]


def going(kitchen, state=None):
    """A pull request whose check is still going (`state` None) or ended, as the pass saw it."""
    kitchen.set("open.json", [kitchen.opened("alpha", 7, state)])
    kitchen.poll()


def ended(kitchen, run_id):
    kitchen.set("runs.json", {"workflow_runs": [{"id": run_id, "status": "completed"}]})


@pytest.fixture
def watched(kitchen):
    going(kitchen)
    assert json.loads((kitchen.state / tick.PENDING).read_text()) == [{"number": 7, "head": HEAD}]
    ended(kitchen, 1)
    ticks(kitchen)
    kitchen.set("jmerge.txt", f"{MERGED}\n")
    return kitchen


def test_a_check_that_ends_runs_jmerge_on_the_next_tick_and_sends_its_lines(watched):
    assert runs(watched) == 1
    ended(watched, 2)
    assert ticks(watched) == ["tick demo: a run ended, and jmerge ran"]
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


def test_with_the_budget_held_a_tick_backs_off_to_asking_once_in_5_s_and_says_so(
    kitchen, monkeypatch
):
    """A held budget slows the tick to the 5 s it ran at before, not to nothing: a 304 still
    spends nothing, and a run that ended still gets its `jmerge`, which the floor is kept for."""
    going(kitchen)
    kitchen.set("rate-limit.json", rate_limit(10))
    now = [NOW]
    monkeypatch.setattr(verbs, "clock", lambda: now[0])
    ended(kitchen, 1)
    (said, ran) = ticks(kitchen)
    assert said.startswith(
        "tick: the budget is held, so the tick asks GitHub once in 5 s, not 2 s: "
    )
    assert ran == "tick demo: a run ended, and jmerge ran"
    assert (len(asked(kitchen)), runs(kitchen)) == (1, 1)
    for seconds in (2, 4):
        now[0] = NOW + timedelta(seconds=seconds)
        assert ticks(kitchen) == []
    assert len(asked(kitchen)) == 1
    now[0] = NOW + timedelta(seconds=5)
    (said,) = ticks(kitchen)
    assert said.startswith("tick: the budget is held")
    assert len(asked(kitchen)) == 2 and runs(kitchen) == 1


def test_a_304_to_the_ticks_conditional_read_is_not_counted_against_the_budget(watched):
    """gh exits 1 on a 304, and GitHub counts none of it against the allowance: `jbus budget
    --callers` counts the tick's one read that changed, and its 304s apart, as free."""
    for _ in range(3):
        assert ticks(watched) == []
    since = NOW - timedelta(days=3650)
    lines = budget.callers(watched.state_dir, since).splitlines()
    tick_lines = [line for line in lines if "jbus.tick._ended" in line]
    assert tick_lines[0].split() == [
        "1",
        "jbus.tick._ended",
        "<",
        "jbus.tick.tick",
        "(0",
        "failed)",
    ]
    assert "and 3 answered 304, which spend nothing:" in lines
    assert tick_lines[1].split() == ["3", "jbus.tick._ended", "<", "jbus.tick.tick"]


def test_a_busy_jmerge_leaves_the_ended_run_to_the_next_tick(watched):
    watched.set("jmerge-busy", "")
    ended(watched, 2)
    assert ticks(watched) == ["tick demo: a run ended, and jmerge did not run to its end"]
    (watched.stub / "jmerge-busy").unlink()
    assert ticks(watched) == ["tick demo: a run ended, and jmerge ran"]
    assert MERGED in watched.lines("jmerge")
    assert ticks(watched) == []


def test_a_jmerge_that_fails_leaves_the_ended_run_to_the_next_tick(watched):
    watched.set("jmerge-says", "wait: could not ask GitHub: HTTP 502")
    ended(watched, 2)
    ticks(watched)
    (watched.stub / "jmerge-says").unlink()
    assert ticks(watched) == ["tick demo: a run ended, and jmerge ran"]


def test_a_tick_that_dies_before_jmerge_ends_loses_no_merge(watched, monkeypatch):
    def dies(run):
        raise KeyboardInterrupt

    ran = merge.tick
    monkeypatch.setattr(merge, "tick", dies)
    ended(watched, 2)
    with pytest.raises(KeyboardInterrupt):
        ticks(watched)
    monkeypatch.setattr(merge, "tick", ran)
    assert ticks(watched) == ["tick demo: a run ended, and jmerge ran"]
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


def line(kitchen):
    kept = json.loads((kitchen.state / work.NAME).read_text())
    return {one["key"]: one for one in kept["work"]}["alpha"]


def check_ended(kitchen, run_id, conclusion):
    """GitHub lists the run of the required check `check` at #7's head as ended."""
    one = {"id": run_id, "status": "completed", "name": "check", "head_sha": HEAD}
    one |= {"conclusion": conclusion, "updated_at": "2026-01-01T00:00:00Z"}
    kitchen.set("runs.json", {"workflow_runs": [one]})


def before_jmerge(monkeypatch, kitchen):
    """Keep #7's line of `work.json` as it is when the tick starts `jmerge`."""
    seen, ran = [], merge.tick

    def tick_of(run):
        seen.append(line(kitchen))
        return ran(run)

    monkeypatch.setattr(merge, "tick", tick_of)
    return seen


def test_a_changed_runs_list_restates_the_rows_line_before_jmerge_runs(on_check, monkeypatch):
    """A check that failed reaches #7's line as soon as GitHub lists its run, before the tick's
    `jmerge` runs, with the reason `jmerge` gives it, which `jmerge` then agrees with."""
    seen = before_jmerge(monkeypatch, on_check)
    check_ended(on_check, 1, "failure")
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    assert ticks(on_check) == [
        "tick demo: a run ended, and alpha's line says its check ended",
        "tick demo: a run ended, and jmerge ran",
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
        assert ticks(on_check)[-1] == "tick demo: a run ended, and jmerge did not run to its end"
        said = line(on_check)
        assert said["why"] == "wait: check passed, and jmerge has not judged it yet"
        assert said[restated.CHECKED] == "passed"
        assert ticks(on_check) == ["tick demo: a run ended, and jmerge did not run to its end"]
        assert line(on_check) == said
    assert ticks(on_check) == ["tick demo: a run ended, and jmerge ran"]
    assert line(on_check)["facts"]["pull"] == "merged"
    assert on_check.events(states.DRIFT) == []


def test_a_304_restates_nothing(on_check):
    check_ended(on_check, 1, "failure")
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    assert ticks(on_check)[0] == "tick demo: a run ended, and alpha's line says its check ended"
    assert line(on_check)["why"] == FAILED
    before = (on_check.state / work.NAME).read_bytes()
    assert ticks(on_check) == []
    assert (on_check.state / work.NAME).read_bytes() == before


def test_jmerge_that_judges_the_check_otherwise_corrects_the_line_and_logs_drift(on_check):
    """The tick's word is the list of runs; `jmerge`'s is the pull request's checks. Where
    `jmerge`, run after the tick restated the line, still finds the check running, its verdict
    stands, and the line is logged as drift, quietly."""
    check_ended(on_check, 1, "failure")
    ticks(on_check)
    assert line(on_check)["why"] != FAILED
    (drift,) = [one["line"] for one in on_check.events(states.DRIFT)]
    assert drift.startswith("work-drift alpha: the tick's check failed (")


@pytest.mark.parametrize(
    "given",
    [
        "a page that is no JSON",
        {"workflow_runs": [{"name": "check", "head_sha": HEAD, "conclusion": "failure"}]},
    ],
)
def test_a_list_of_runs_the_tick_cannot_read_leaves_the_line_to_jmerge(on_check, given):
    """An answer that is no JSON, or a run with no time it ended, restates nothing: the tick's
    `jmerge` runs as before and judges the line."""
    on_check.set("runs.json", given)
    before = line(on_check)
    assert ticks(on_check) == ["tick demo: a run ended, and jmerge ran"]
    assert line(on_check)["why"] == before["why"]


def watching(kitchen):
    return json.loads((kitchen.state / tick.PENDING).read_text())


def test_a_rollup_that_says_passed_before_its_check_appears_keeps_the_pull_request_pending(
    on_check,
):
    """#1246: the pass read #7's rollup before its job `check` was in it, so the rollup said
    `passed` while `jmerge` still saw `check` running. The pass keeps #7's head for the tick,
    which asks GitHub and restates the line once the run ends."""
    on_check.set("open.json", [on_check.opened("alpha", 7, "SUCCESS")])
    on_check.poll()
    assert watching(on_check) == [{"number": 7, "head": HEAD}]
    check_ended(on_check, 1, "success")
    before = len(asked(on_check))
    assert ticks(on_check)[0] == "tick demo: a run ended, and alpha's line says its check ended"
    assert len(asked(on_check)) == before + 1


def test_the_pass_drops_a_head_once_the_tick_had_its_verdict(on_check):
    check_ended(on_check, 1, "failure")
    on_check.set("jmerge.txt", f"{RUNNING}\n")
    ticks(on_check)
    on_check.set("open.json", [on_check.opened("alpha", 7, "FAILURE")])
    on_check.poll()
    assert watching(on_check) == []


def test_the_pass_drops_a_head_once_jmerge_had_its_verdict(on_check):
    """The pass runs `jmerge` before it reads the rollup, so a `jmerge` that saw the check fail
    lets the same pass stop watching #7, and one that still sees it running keeps it."""
    on_check.set("open.json", [on_check.opened("alpha", 7, "FAILURE")])
    on_check.poll()
    assert watching(on_check) == [{"number": 7, "head": HEAD}]
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}\n")
    on_check.poll()
    assert watching(on_check) == []


def test_a_verdict_jmerge_gives_before_it_reads_the_checks_keeps_the_head(on_check):
    """`jmerge` judges a pull request's review before its checks, so a `jmerge` that waits on
    #7's review says nothing of them: with a rollup that says `passed` too early, the pass keeps
    #7's head for the tick."""
    on_check.set("open.json", [on_check.opened("alpha", 7, "SUCCESS")])
    on_check.set("jmerge.txt", f"wait 7 {PULL}: {ready.NO_REVIEW}\n")
    on_check.poll()
    assert watching(on_check) == [{"number": 7, "head": HEAD}]
