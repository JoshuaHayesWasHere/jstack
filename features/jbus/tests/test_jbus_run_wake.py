"""A crew that waits on a GitHub run it started registers the wait, `jbus run-wait <run> --thread
<id>`, and ends its turn. jbus keeps its row waiting on the run, never stale, and wakes its thread
once when the run has ended (`jbus.runwait`).

macos-red-2026-11-13 and macos-nightly-fits, 2026-11-13: each crew ended its turn on a macOS run
of most of an hour, nothing woke it, and its row went stale or stayed not done. Like
`test_jbus_unwritten.py`, the tests run the real verb and the real pass against the kitchen's
fakes, where `run-view.json` is what GitHub says of each run."""

import json
from datetime import timedelta

from jbus import runwaiters, watch
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
    """The runs GitHub was asked about, one line a read."""
    log = kitchen.stub / "run-view.log"
    return log.read_text().splitlines() if log.exists() else []


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


def test_a_wake_that_t3_code_did_not_take_is_sent_again_under_its_key(kitchen):
    thread = waiting_crew(kitchen)
    github(kitchen, "completed", "success")
    kitchen.t3.refuse_send = True
    kitchen.poll(NOW)
    assert len(runwaiters.read(runwaiters.where())) == 1
    kitchen.t3.refuse_send = False
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 2 * MIN)
    tries = told(kitchen, thread["threadId"])
    assert len(tries) == 2 and len({one["clientRequestId"] for one in tries}) == 1
    assert "has ended: success" in tries[-1]["message"]
    assert runwaiters.read(runwaiters.where()) == [] and kitchen.lines("run-wake") != []


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


def test_the_wait_of_a_thread_that_ended_for_good_is_dropped_unasked(kitchen):
    thread = waiting_crew(kitchen)
    thread["status"] = "interrupted"
    kitchen.poll(NOW)
    assert runwaiters.read(runwaiters.where()) == [] and asked(kitchen) == [RUN]
