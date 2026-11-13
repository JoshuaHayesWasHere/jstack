"""A crew that waits on a GitHub run it started registers the wait, `jbus run-wait <run> --thread
<id>`, and ends its turn. jbus keeps its row waiting on the run, never stale, and wakes its thread
once when the run has ended (`jbus.runwait`).

macos-red-2026-11-13 and macos-nightly-fits, 2026-11-13: each crew ended its turn on a macOS run
of most of an hour, nothing woke it, and its row went stale or stayed not done. Like
`test_jbus_unwritten.py`, the tests run the real verb and the real pass against the kitchen's
fakes, where `run-view.json` is what GitHub says of each run."""

import json
import subprocess
from datetime import timedelta

import pytest

from jbus import runwait, runwaiters, watch
from test_jbus_kitchen import NOW
from test_jbus_leftover import home
from test_jbus_row_ends import column, listed
from test_jbus_unwritten import lost, told

MIN = timedelta(minutes=1)
RUN = "4242"
URL = f"https://example.test/actions/runs/{RUN}"


def github(kitchen, status, conclusion=None, run=RUN):
    """Make GitHub say the run is at `status`, with `conclusion` once it has ended."""
    kept = kitchen.stub / "run-view.json"
    runs = json.loads(kept.read_text()) if kept.exists() else {}
    runs[run] = {"status": status, "conclusion": conclusion, "name": "macOS nightly"}
    runs[run]["html_url"] = f"https://example.test/actions/runs/{run}"
    kept.write_text(json.dumps(runs))


def asked(kitchen):
    """The runs GitHub was asked about, one a read."""
    log = kitchen.stub / "gh.log"
    calls = log.read_text().splitlines() if log.exists() else []
    return [one.split("/actions/runs/")[1].split()[0] for one in calls if "/actions/runs/4" in one]


def waiting_crew(kitchen):
    """A row whose crew started run `RUN`, registered the wait, and ended its turn 40 minutes ago
    with nothing written."""
    thread = lost(kitchen, quiet=40)
    kitchen.brief("alpha", f"Thread: {thread['threadId']}\n")
    github(kitchen, "in_progress")
    code, said = kitchen.main("--project", "demo", "run-wait", RUN, "--thread", thread["threadId"])
    assert code == 0, said
    assert said.startswith(f"waiting: run {RUN} (macOS nightly) is in_progress, and jbus wakes")
    return thread


def test_a_row_whose_crew_waits_on_a_run_reads_as_waiting_on_it_and_never_stale(kitchen):
    thread = waiting_crew(kitchen)
    at = home(kitchen)["threadId"]
    for minutes in (0, watch.UNWRITTEN_MINUTES + 2, 60):
        kitchen.poll(NOW + minutes * MIN)
        assert column(kitchen) == ("running", "", f"waiting on GitHub run {RUN} (macOS nightly)")
    assert kitchen.lines("stale") == [] and listed(kitchen) == []
    assert told(kitchen, at) == [] and told(kitchen, thread["threadId"]) == []
    assert asked(kitchen) == [RUN] * 4


def test_the_runs_end_wakes_the_crew_once_with_its_conclusion(kitchen):
    thread = waiting_crew(kitchen)
    kitchen.poll(NOW)
    github(kitchen, "completed", "failure")
    for minutes in (1, 2, 3):
        kitchen.poll(NOW + minutes * MIN)
    (wake,) = told(kitchen, thread["threadId"])
    assert wake["mode"] == "queue" and wake["clientRequestId"].startswith(
        f"run-wake|{thread['threadId']}|"
    )
    assert f"GitHub run {RUN} (macOS nightly)" in wake["message"]
    assert "has ended: failure" in wake["message"] and URL in wake["message"]
    assert kitchen.lines("run-wake") == [
        f"run-wake: woke {thread['threadId']}, GitHub run {RUN} (macOS nightly) ended failure,"
        " after 1 min"
    ]
    assert runwaiters.read(runwaiters.where()) == []
    assert asked(kitchen) == [RUN] * 3
    assert column(kitchen)[2] != f"waiting on GitHub run {RUN} (macOS nightly)"


def test_a_crew_that_registers_again_keeps_its_one_wait(kitchen):
    thread = waiting_crew(kitchen)
    (first,) = runwaiters.read(runwaiters.where())
    code, said = kitchen.main("--project", "demo", "run-wait", RUN, "--thread", thread["threadId"])
    assert code == 0 and said.startswith("waiting:")
    assert runwaiters.read(runwaiters.where()) == [first]


def test_a_run_github_does_not_answer_for_in_a_pass_is_asked_again_on_the_next(kitchen):
    thread = waiting_crew(kitchen)
    (kitchen.stub / "run-view.json").write_text("{}")
    said = kitchen.poll(NOW)
    assert any(f"GitHub run {RUN} could not be read (gh: Not Found" in line for line in said)
    assert len(runwaiters.read(runwaiters.where())) == 1
    github(kitchen, "completed", "success")
    kitchen.poll(NOW + MIN)
    assert len(told(kitchen, thread["threadId"])) == 1
    assert runwaiters.read(runwaiters.where()) == [] and asked(kitchen) == [RUN] * 3


@pytest.mark.parametrize("how", ["refuse_send", "lose_send"])
def test_a_wake_that_t3_code_did_not_take_is_sent_again_under_its_key(kitchen, how):
    thread = waiting_crew(kitchen)
    github(kitchen, "completed", "success")
    setattr(kitchen.t3, how, True)
    said = kitchen.poll(NOW)
    assert any(f"could not be told run {RUN} ended" in line for line in said)
    assert len(runwaiters.read(runwaiters.where())) == 1
    setattr(kitchen.t3, how, False)
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 2 * MIN)
    tries = told(kitchen, thread["threadId"])
    assert len(tries) == 2
    assert len({one["clientRequestId"] for one in tries}) == 1
    assert "has ended: success" in tries[-1]["message"]
    assert runwaiters.read(runwaiters.where()) == [] and kitchen.lines("run-wake") != []


def test_a_wake_held_while_the_thread_has_a_turn_running_goes_once_the_turn_ends(kitchen):
    thread = waiting_crew(kitchen)
    github(kitchen, "completed", "success")
    thread["status"] = "running"
    kitchen.poll(NOW)
    assert told(kitchen, thread["threadId"]) == []
    assert len(runwaiters.read(runwaiters.where())) == 1
    thread["status"] = "idle"
    kitchen.poll(NOW + MIN)
    assert len(told(kitchen, thread["threadId"])) == 1
    assert runwaiters.read(runwaiters.where()) == []


def test_a_wake_t3_code_says_has_no_thread_to_go_to_drops_the_wait(kitchen):
    thread = waiting_crew(kitchen)
    github(kitchen, "completed", "success")
    kitchen.t3.lose_read = True
    kitchen.t3.forgot.add(thread["threadId"])
    said = kitchen.poll(NOW)
    assert any("its run wait is dropped, its thread is gone" in line for line in said)
    assert runwaiters.read(runwaiters.where()) == [] and kitchen.lines("run-wake") == []


def test_a_run_that_has_ended_already_registers_nothing(kitchen):
    github(kitchen, "completed", "success")
    code, said = kitchen.main("--project", "demo", "run-wait", RUN, "--thread", "mcp:someone")
    assert code == 0
    assert said.startswith(f"ended: run {RUN} (macOS nightly) has ended already, success: {URL}")
    assert runwaiters.read(runwaiters.where()) == []


def test_a_run_github_does_not_know_is_refused(kitchen):
    code, said = kitchen.main("--project", "demo", "run-wait", "77", "--thread", "mcp:someone")
    assert code != 0
    assert said.startswith("refused: GitHub gives no run 77 for demo: gh: Not Found (HTTP 404)")
    assert runwaiters.read(runwaiters.where()) == []


@pytest.mark.parametrize("how", ["interrupted", "gone"])
def test_the_wait_of_a_thread_that_ended_for_good_is_dropped_unasked(kitchen, how):
    thread = waiting_crew(kitchen)
    if how == "gone":
        kitchen.t3.threads.remove(thread)
    else:
        thread["status"] = how
    kitchen.poll(NOW)
    assert runwaiters.read(runwaiters.where()) == [] and asked(kitchen) == [RUN]


def gh(code, out="", error=""):
    def call(*args, **kwargs):
        if code is None:
            raise FileNotFoundError(2, "No such file or directory", "gh")
        return subprocess.CompletedProcess(args, code, out, error)

    return call


@pytest.mark.parametrize(
    ("call", "why"),
    [
        (gh(None), "No such file or directory"),
        (gh(0, "<html>rate limited</html>"), "gh gave no run: <html>rate limited</html>"),
        (gh(0, '["a list"]'), 'gh gave no run: ["a list"]'),
        (gh(1), "gh ended 1"),
    ],
)
def test_a_gh_that_gives_no_run_says_why_and_raises_nothing(call, why):
    assert why in runwait.ask(RUN, call)
