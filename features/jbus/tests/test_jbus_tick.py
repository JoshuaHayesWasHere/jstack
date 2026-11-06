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
from jbus import alert, merge, tick
from test_jbus_kitchen import NOW, Kitchen, rate_limit
from test_jbus_merge import LOCKING
from test_jbus_row_ends import sends


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


MERGED = "merged 7 alpha abc1234"


def ticks(kitchen):
    said = []
    assert tick.tick(jbus.load(), said.append) == 0
    return said


def runs(kitchen):
    return kitchen.log("jmerge").count("--if-free")


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
    assert json.loads((kitchen.state / tick.PENDING).read_text()) == [7]
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


def test_with_the_budget_held_a_tick_asks_github_nothing_more_and_runs_no_jmerge(kitchen):
    going(kitchen)
    kitchen.set("rate-limit.json", rate_limit(10))
    ended(kitchen, 1)
    (said,) = ticks(kitchen)
    assert said.startswith("tick: GitHub not asked: ")
    assert asked(kitchen) == [] and runs(kitchen) == 0


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
    assert alert.jmerge("demo") not in watched.status()["streaks"]
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
    assert watched.status()["streaks"][alert.jmerge("demo")]["count"] == 3
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
