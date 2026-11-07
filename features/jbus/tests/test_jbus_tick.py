"""The merge tick runs `jmerge` a few seconds after a check ends, apart from the pass, and spends
none of GitHub's API allowance while no check ends (`jbus.tick`). It runs `jmerge --if-free`, so
one merger runs at a time (`features/jmerge/tests/test_jmerge_one_run.py`), and it keeps what it
saw only once `jmerge` ran to its end, so a tick that dies or finds `jmerge` busy loses no merge.
The pass runs `jmerge --if-free` too. The tests run the real tick and pass against the fakes
(`test_jbus_kitchen.py`).
"""

import configparser
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

import jbus
from jbus import alert, budget, merge, tick, verbs
from test_jbus_kitchen import NOW, Kitchen, rate_limit
from test_jbus_merge import LOCKING
from test_jbus_row_ends import sends

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


MERGED = "merged 7 alpha abc1234"


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


MANAGER = """#!/bin/sh
echo "$*" >> "{stub}/systemctl.log"
case "$2" in
is-active) cat "{stub}/timer.txt"; [ "$(cat "{stub}/timer.txt")" = active ] ;;
start) echo active > "{stub}/timer.txt" ;;
stop) echo inactive > "{stub}/timer.txt" ;;
*) exit 1 ;;
esac
"""
"""A user manager with the one timer the pass starts and stops, active as the install leaves it
(`enable --now`)."""


@pytest.fixture
def manager(kitchen):
    stand_in = kitchen.stub / "systemctl"
    stand_in.write_text(MANAGER.format(stub=kitchen.stub))
    stand_in.chmod(0o755)
    (kitchen.stub / "timer.txt").write_text("active\n")
    return kitchen


def timer(kitchen):
    return (kitchen.stub / "timer.txt").read_text().strip()


def switched(kitchen):
    return [call for call in kitchen.log("systemctl") if "jbus-merge.timer" in call]


def test_the_tick_runs_only_while_a_pass_saw_a_check_going_and_starts_within_2_s(
    manager, monkeypatch
):
    """The install leaves `jbus-merge.timer` running. A pass of `jbus.service`, which names the
    timer, stops it while no project's `checks-pending.json` holds a pull request, so no tick
    starts, and starts it once one does. The timer's first tick then comes `OnActiveSec=` after
    the start, within 2 s, and the next ones every 2 s. A pass that changes nothing leaves it."""
    kitchen = manager
    monkeypatch.setenv(tick.TIMER, "jbus-merge.timer")
    said = kitchen.poll()
    assert json.loads((kitchen.state / tick.PENDING).read_text()) == []
    assert timer(kitchen) == "inactive"
    assert "tick: no pull request has checks going, so jbus-merge.timer stops" in said
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
    assert unit["Timer"]["OnActiveSec"] == unit["Timer"]["OnUnitActiveSec"] == "2s"
    service = (REPO / "features" / "jbus" / "units" / "jbus.service").read_text()
    assert f"Environment={tick.TIMER}=jbus-merge.timer" in service.splitlines()


def test_a_pass_that_no_unit_started_leaves_the_machines_timer_as_it_is(manager):
    """A pass that a test, a sandbox or a hand starts has no `JBUS_TICK_TIMER`, which only
    `jbus.service` sets, so it asks the user manager nothing of the timer."""
    going(manager)
    going(manager, "SUCCESS")
    assert switched(manager) == []
    assert timer(manager) == "active"
