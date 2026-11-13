"""A crewmate that starts a run on GitHub Actions to prove its change registers the wait with
`jbus run-wait` and ends its turn, and jbus wakes it once the run has ended.

macos-red-2026-11-13 and macos-nightly-fits, 2026-11-13: each crew ended its turn on a macOS run
and nothing woke it. The test runs the skill's block as an agent does, with the real `jbus` and a
`uv` stand-in that drops `run --project`, against the kitchen of `test_jbus_kitchen`, whose `gh`
says what `run-view.json` holds of each run."""

import os
import subprocess

import test_room as room
from crew_helpers import block, sections
from test_jbus_run_wake import RUN, github, waiting_crew
from test_jbus_unwritten import lost


def register(kitchen, thread):
    room.uv(kitchen.stub)
    found = block("Do the task", "jbus run-wait")
    ran = subprocess.run(
        ["sh", "-c", found.replace("<run id>", RUN).replace("<thread id>", thread)],
        capture_output=True,
        text=True,
        env={**os.environ, "T": str(kitchen.root / "templates")},
        cwd=kitchen.checkout,
        check=True,
    )
    return ran.stdout.splitlines()


def test_a_crew_that_started_a_run_registers_its_wait_and_is_told_to_end_its_turn(kitchen):
    thread = lost(kitchen, quiet=40)["threadId"]
    github(kitchen, "queued")
    (said,) = register(kitchen, thread)
    assert said.startswith(f"waiting: run {RUN} (macOS nightly) is queued, and jbus wakes {thread}")
    assert said.endswith("end your turn now.")
    text = sections()["Do the task"]
    assert "On `waiting:`, end your turn at once" in text
    assert "Waiting on GitHub run <run id>: jbus will wake this thread when it ends." in text
    assert "macOS nightly" in text and "browser run" in text


def test_the_wake_that_follows_is_the_one_the_skill_says_to_go_on_from(kitchen):
    thread = waiting_crew(kitchen)
    github(kitchen, "completed", "success")
    kitchen.poll()
    sent = [one for one in kitchen.t3.messages.values() if one["threadId"] == thread["threadId"]]
    (wake,) = [one for one in sent if one["clientRequestId"].startswith("run-wake|")]
    assert "has ended: success" in wake["message"]
