"""A pass starts its run of `jmerge` and does not wait for it: the run is a process of its own, and
the first pass after it ended reads what it printed, once (`jbus.merge.merge`). The kitchen runs
`jmerge` inside the pass (`merge_in_pass.py`), so these tests put the real start back, and
the kitchen's `jmerge` runs as a command on PATH, sleeping as long as `jmerge-sleep` says.
"""

import time
from datetime import UTC, datetime, timedelta

import pytest

import jbus
import jbus.passes
from jbus import alert, merge, restated, states, verbs
from jbus.merge import start
from jmerge import ready
from test_jbus_kitchen import NOW
from test_jbus_queue import add
from test_jbus_row_ends import PULL
from test_jbus_tick import RUNNING, going, line

LINE = f"wait 7 {PULL}: it has no review yet"


@pytest.fixture
def off(kitchen, monkeypatch):
    """The kitchen, with the pass's run of `jmerge` started as a pass run by hand starts it."""
    kitchen.quiet()
    (kitchen.stub / "jmerge.log").unlink(missing_ok=True)
    monkeypatch.setattr(merge, "start", start)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    kitchen.set("jmerge.txt", f"{LINE}\n")
    yield kitchen
    ended(kitchen)


def a_pass(kitchen):
    config = jbus.load()
    return jbus.passes.Pass(config, config.project("demo"), datetime.now(UTC))


def ended(kitchen, within=20.0):
    """Wait for the run under way to end, as the record it leaves shows."""
    runs = kitchen.state / merge.RUNS
    until = time.monotonic() + within
    while time.monotonic() < until:
        if not (runs / merge.STARTED).exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"the run of jmerge did not end within {within} s")


def started(kitchen, within=10.0):
    """Wait until the run's `jmerge` has begun, as its log shows."""
    until = time.monotonic() + within
    while time.monotonic() < until:
        if kitchen.log("jmerge"):
            return kitchen.log("jmerge")
        time.sleep(0.05)
    raise AssertionError(f"jmerge did not start within {within} s")


def test_a_pass_returns_while_jmerge_still_runs(off):
    """With `jmerge` sleeping 5 s, the pass that starts it ends well before it, and has no line of
    it yet."""
    off.set("jmerge-sleep", "5")
    began = time.monotonic()
    off.poll()
    assert time.monotonic() - began < 4
    assert started(off) == ["--if-free"]
    assert (off.state / merge.RUNS / merge.STARTED).exists()
    assert off.lines("jmerge") == []


def test_the_next_pass_reads_a_finished_runs_lines_once(off):
    """Passes while the run goes start no second one and read nothing. The first pass after it
    ended reads its line, once, at the moment it ended, and starts the next run."""
    off.set("jmerge-sleep", "1")
    run = a_pass(off)
    assert merge.merge(run) == [] and started(off) == ["--if-free"]
    going = merge.merge(run)
    assert (going, going.failed, off.log("jmerge")) == ([], True, ["--if-free"])
    ended(off)
    off.set("jmerge.txt", "")
    said = merge.merge(run)
    assert (said, said.failed) == ([LINE], False)
    assert said.at > restated.moment(NOW)
    assert off.lines("jmerge") == [LINE]
    ended(off)
    again = merge.merge(run)
    assert (again, again.failed) == ([], False) and again.at > said.at
    ended(off)
    assert off.log("jmerge") == ["--if-free"] * 3


def test_a_run_that_ended_with_no_record_counts_as_a_failure(off):
    """A run whose process died before it kept a record, as one systemd stopped, is a failure of
    the `jmerge` streak, said with the last line it printed, and the next pass starts another."""
    runs = off.state / merge.RUNS
    runs.mkdir(parents=True, exist_ok=True)
    (runs / merge.STARTED).write_text("")
    (runs / merge.CHILD_LOG).write_text("Traceback\nImportError: no jbus\n")
    printed = off.poll()
    why = "its run ended with no record: ImportError: no jbus"
    assert f"wait demo: jmerge did not run ({why})" in printed
    assert off.status()["streaks"][alert.jmerge("demo")]["count"] == 1
    assert started(off) == ["--if-free"]


@pytest.fixture
def checking(kitchen):
    """The row `alpha`, whose pull request #7 is on the check step while its check runs, as a
    pass read it from a run of `jmerge` (`test_jbus_tick.on_check`)."""
    add(kitchen, "alpha")
    kitchen.brief("alpha", f"\n## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n")
    kitchen.t3.thread("alpha", "completed")
    going(kitchen)
    kitchen.set("jmerge.txt", f"{RUNNING}\n")
    kitchen.poll()
    assert line(kitchen)["value"] == "check"
    return kitchen


def test_a_tick_that_judged_after_the_run_ended_keeps_its_verdict_over_the_read(
    checking, monkeypatch
):
    """The pass's run judged #7 and ended, and before a pass read it a merge tick's run judged #7
    otherwise. The pass that reads the older run leaves #7's line as the tick wrote it, and logs
    no drift."""
    older = f"wait 7 {PULL}: {ready.CHECK_FAILED.format(check='check')}"
    monkeypatch.setattr(verbs, "clock", lambda: NOW + timedelta(seconds=1))
    checking.set("jmerge.txt", f"{older}\n")
    merge.keep(checking.state / merge.RUNS, checking.checkout)
    monkeypatch.setattr(verbs, "clock", lambda: NOW + timedelta(seconds=2))
    checking.set("jmerge.txt", f"{LINE}\n")
    merge.tick(a_pass(checking), {})
    ticked = line(checking)
    assert ticked["why"] == "wait: it has no review yet"
    monkeypatch.setattr(merge, "start", lambda run: "")
    assert merge.merge(a_pass(checking)) == [older]
    assert line(checking) == ticked
    assert checking.events(states.DRIFT) == []
