"""A crew thread that ended with no Result is told to carry on: one queued message for each
ended run, at most two for a thread, and then a gate. Run as `tests/test_jbus_queue.py`
runs: the real pass, against the fakes."""

from datetime import timedelta

import pytest

import jbus
from test_jbus_kitchen import NOW, RESULT, TOKEN, sends
from test_jbus_queue import add, gates

THREAD = "mcp:thread-1"


def message(status, k, slug="alpha"):
    return (
        f"jbus: this thread ended ({status}) before writing its Result. Carry on with your "
        f"brief from where you stopped: read `tasks/{slug}.md` and your worktree's `git status` "
        "and `git log` first, keep what is committed, and do not start over. This is carry-on "
        f"{k} of 2."
    )


def crew(kitchen, slug="alpha", status="failed", run="run-1", **more):
    """A thread jbus launched for the slug, whose latest run then ended as told."""
    add(kitchen, slug)
    kitchen.poll(NOW - timedelta(minutes=3))
    thread = kitchen.t3.threads[-1]
    thread.update({"status": status, "latestRunId": run, "snoozed": False, **more})
    return thread


def resumes(kitchen):
    return kitchen.lines("resume")


def test_a_failed_thread_with_no_result_is_told_once_to_carry_on(kitchen):
    crew(kitchen)
    said = kitchen.poll()
    line = "resume alpha: told the crew to carry on (failed, 1 of 2)"
    assert sends(kitchen) == [
        {
            "threadId": THREAD,
            "message": message("failed", 1),
            "mode": "queue",
            "clientRequestId": f"resume|alpha|{THREAD}|run-1",
        }
    ]
    assert resumes(kitchen) == [line] and line in said and gates(kitchen) == []
    assert f"resume|alpha|{THREAD}|run-1" in jbus.read_json(kitchen.state / "sent.json", [])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(sends(kitchen)) == 1 and resumes(kitchen) == [line]


def test_a_second_end_is_the_last_carry_on_and_a_third_is_a_gate(kitchen):
    thread = crew(kitchen)
    kitchen.poll()
    thread.update(status="running", latestRunId="run-2")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(sends(kitchen)) == 1
    thread["status"] = "cancelled"
    kitchen.poll(NOW + timedelta(minutes=6))
    assert [given["message"] for given in sends(kitchen)] == [
        message("failed", 1),
        message("cancelled", 2),
    ]
    assert sends(kitchen)[1]["clientRequestId"] == f"resume|alpha|{THREAD}|run-2"
    assert resumes(kitchen) == [
        "resume alpha: told the crew to carry on (failed, 1 of 2)",
        "resume alpha: told the crew to carry on (cancelled, 2 of 2)",
    ]
    thread.update(status="failed", latestRunId="run-3")
    kitchen.poll(NOW + timedelta(minutes=9))
    kitchen.poll(NOW + timedelta(minutes=12))
    assert len(sends(kitchen)) == 2 and len(resumes(kitchen)) == 2
    assert gates(kitchen) == ["condition alpha: thread ended failed after two carry-ons"]


def test_a_new_thread_for_the_slug_starts_its_own_count(kitchen):
    thread = crew(kitchen)
    kitchen.poll()
    thread["latestRunId"] = "run-2"
    kitchen.poll(NOW + timedelta(minutes=3))
    thread["settled"] = True
    new = kitchen.t3.thread("alpha", "interrupted", latestRunId="run-9", snoozed=False)
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(path.read_text().replace(f"Thread: {THREAD}", f"Thread: {new['threadId']}"))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert sends(kitchen)[2] == {
        "threadId": "mcp:thread-2",
        "message": message("interrupted", 1),
        "mode": "queue",
        "clientRequestId": "resume|alpha|mcp:thread-2|run-9",
    }
    assert gates(kitchen) == []


def test_an_interrupted_thread_is_told_to_carry_on(kitchen):
    crew(kitchen, status="interrupted")
    kitchen.poll()
    assert [given["message"] for given in sends(kitchen)] == [message("interrupted", 1)]
    assert resumes(kitchen) == ["resume alpha: told the crew to carry on (interrupted, 1 of 2)"]


@pytest.mark.parametrize("status", ["completed", "running", "waiting"])
def test_a_thread_that_did_not_fail_is_sent_nothing(kitchen, status):
    crew(kitchen, status=status)
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []


def test_a_thread_whose_brief_has_a_result_is_sent_nothing(kitchen):
    crew(kitchen)
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(path.read_text() + RESULT)
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []


@pytest.mark.parametrize("put_away", ["settled", "snoozed"])
def test_a_settled_or_snoozed_thread_is_sent_nothing(kitchen, put_away):
    crew(kitchen, **{put_away: True})
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == [] and gates(kitchen) == []


@pytest.mark.parametrize("state", ["merged", "open"])
def test_a_slug_with_a_pull_request_is_sent_nothing(kitchen, state):
    crew(kitchen)
    pull = kitchen.merged("alpha", 7, "a" * 40) if state == "merged" else kitchen.opened("alpha", 7)
    kitchen.set(f"{state}.json", [pull])
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []


def test_a_slug_with_two_threads_is_the_gate_it_already_was_and_no_send(kitchen):
    crew(kitchen)
    kitchen.t3.thread("alpha", "failed", latestRunId="run-5", snoozed=False)
    kitchen.poll()
    assert sends(kitchen) == [] and gates(kitchen) == ["condition alpha: 2 threads for one slug"]


def test_a_thread_jbus_did_not_launch_is_sent_nothing(kitchen):
    kitchen.brief("alpha", "Thread: mcp:thread-1\n")
    kitchen.t3.thread("alpha", "failed", latestRunId="run-1", snoozed=False)
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []
    assert kitchen.lines("stale") == ["stale alpha: thread failed with no Result"]


def test_a_thread_the_brief_does_not_name_is_sent_nothing(kitchen):
    crew(kitchen)
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(path.read_text().replace(f"Thread: {THREAD}", "Thread: mcp:another"))
    said = kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []
    assert [line for line in said if line.startswith("refused")] == []


def test_a_pass_that_could_not_list_the_threads_sends_nothing(kitchen):
    crew(kitchen)
    stored = kitchen.config_dir / "t3.json"
    kitchen.write(stored, stored.read_text().replace(TOKEN, "a-token-that-ran-out"))
    said = kitchen.poll()
    assert any(line.startswith("wait demo: T3 Code could not be asked") for line in said)
    assert sends(kitchen) == [] and resumes(kitchen) == []


def test_a_pass_with_no_sign_in_sends_nothing(kitchen):
    crew(kitchen)
    (kitchen.config_dir / "t3.json").unlink()
    said = kitchen.poll()
    assert "wait demo: T3 Code could not be asked (no token: run `jbus t3 login`)" in said
    assert sends(kitchen) == [] and resumes(kitchen) == []


def test_a_carry_on_whose_answer_was_lost_is_sent_again_with_the_same_key(kitchen):
    crew(kitchen)
    kitchen.t3.lose_send = True
    said = kitchen.poll()
    assert resumes(kitchen) == []
    wait = "wait alpha: its crew could not be told to carry on"
    assert any(line.startswith(wait) for line in said)
    kitchen.t3.lose_send = False
    kitchen.poll(NOW + timedelta(minutes=3))
    assert list(kitchen.t3.messages) == [f"resume|alpha|{THREAD}|run-1"]
    assert resumes(kitchen) == ["resume alpha: told the crew to carry on (failed, 1 of 2)"]


def test_a_carry_on_t3_code_refuses_is_a_gate_once(kitchen):
    crew(kitchen)
    kitchen.t3.refuse_send = True
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert resumes(kitchen) == [] and kitchen.t3.messages == {}
    assert gates(kitchen) == ["condition alpha: T3 Code refused the carry-on"]
