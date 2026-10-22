"""jbus tells a crew thread that ended with no Result to carry on. It queues one message for each
ended run, at most two for a thread, and then a gate. Like `test_jbus_queue.py`, the tests run
the real pass against the fakes."""

from datetime import timedelta
from pathlib import Path

import pytest

import jbus
from jbus import threads
from test_jbus_kitchen import NOW, RESULT, TOKEN, sends
from test_jbus_queue import add, gates
from testing.paths import skills

THREAD = "mcp:thread-1"


SKILLS = {"crew: alpha": "crew", "review: alpha, scoped": "pr-review", "scout: alpha": "scout"}


def skill_file(name):
    """Return the checkout's own skill file, which this finds from the path of this test file and
    not from jbus."""
    return skills()[name] / "SKILL.md"


HOME = Path("/state/home/demo")


def reads(name, slug="alpha", home=HOME):
    return (
        f" Your role's skill is not loaded in this thread and the Skill tool cannot load it: "
        f"read `{skill_file(name)}` from the file and follow it from where your work stands. "
        f"Run `jbriefs --skills {home / ('scouts' if name == 'scout' else 'tasks') / slug}.md` "
        "for the brief's Skills line and read what "
        "it prints."
    )


def message(home, status, k, slug="alpha"):
    return (
        f"jbus: this thread ended ({status}) before writing its Result. Carry on with your "
        f"brief from where you stopped: read `tasks/{slug}.md` and your worktree's `git status` "
        "and `git log` first, keep what is committed, and do not start over. This is carry-on "
        f"{k} of 2." + reads("crew", slug, home)
    )


def crew(kitchen, slug="alpha", status="failed", run="run-1", **more):
    """Make a thread that jbus launched for the slug, whose latest run then ended as told."""
    add(kitchen, slug)
    kitchen.poll(NOW - timedelta(minutes=3))
    thread = kitchen.t3.threads[-1]
    thread.update({"status": status, "latestRunId": run, "snoozed": False, **more})
    return thread


BASE = threads.CARRY_ON.format(status="failed", slug="alpha", k=1, most=2)


@pytest.mark.parametrize(("title", "name"), SKILLS.items())
def test_every_role_with_a_skill_is_told_to_read_it_from_its_file_after_a_failed_run(title, name):
    given = threads.resume_message(
        threads.CARRY_ON, title, HOME, status="failed", slug="alpha", k=1, most=2
    )
    assert skill_file(name).is_file()
    ends = " " + jbus.END_TURN if name == "pr-review" else ""
    assert given == BASE + reads(name) + ends
    merged = threads.resume_message(threads.MERGED, title, HOME, number=7, slug="alpha")
    assert merged == threads.MERGED.format(number=7, slug="alpha") + reads(name) + ends


def test_a_reviewer_is_told_to_end_its_turn_only_once_its_own_proof_has_ended():
    given = threads.resume_message(
        threads.CARRY_ON, "review: alpha", HOME, status="failed", slug="alpha", k=1, most=2
    )
    assert given.endswith(jbus.END_TURN)
    assert "proof" in jbus.END_TURN and "wait for one that runs, in this turn" in jbus.END_TURN


@pytest.mark.parametrize("title", ["home: demo", "something else", "crewish: alpha"])
def test_a_thread_with_no_role_skill_is_sent_the_message_as_it_was(title):
    given = threads.resume_message(
        threads.CARRY_ON, title, HOME, status="failed", slug="alpha", k=1, most=2
    )
    assert given == BASE


def test_the_skill_files_named_are_this_checkouts_and_exist():
    for name in SKILLS.values():
        assert threads.skill_file(name) == skill_file(name)
        assert skill_file(name).is_file()


def resumes(kitchen):
    return kitchen.lines("resume")


def test_a_failed_thread_with_no_result_is_told_once_to_carry_on(kitchen):
    crew(kitchen)
    said = kitchen.poll()
    line = "resume alpha: told the crew to carry on (failed, 1 of 2)"
    assert sends(kitchen) == [
        {
            "threadId": THREAD,
            "message": message(kitchen.home, "failed", 1),
            "mode": "queue",
            "clientRequestId": f"resume|alpha|{THREAD}|run-1",
        }
    ]
    assert resumes(kitchen) == [line] and line in said and gates(kitchen) == []
    assert (kitchen.home / "tasks" / "alpha.md").is_file()
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
        message(kitchen.home, "failed", 1),
        message(kitchen.home, "cancelled", 2),
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
        "message": message(kitchen.home, "interrupted", 1),
        "mode": "queue",
        "clientRequestId": "resume|alpha|mcp:thread-2|run-9",
    }
    assert gates(kitchen) == []


def test_an_interrupted_thread_is_told_to_carry_on(kitchen):
    crew(kitchen, status="interrupted")
    kitchen.poll()
    assert [given["message"] for given in sends(kitchen)] == [
        message(kitchen.home, "interrupted", 1)
    ]
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


def test_a_crew_told_of_its_merge_is_told_to_read_its_skill_file_too(kitchen):
    crew(kitchen, status="completed")
    path = kitchen.home / "tasks" / "alpha.md"
    left = "\n## Result\nStatus: done\nBranch: alpha   Pull request: none\n"
    path.write_text(path.read_text() + left + "Left: after the merge, run the migration\n")
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll()
    (given,) = sends(kitchen)
    assert given["threadId"] == THREAD
    assert given["message"] == threads.MERGED.format(number=7, slug="alpha") + reads(
        "crew", home=kitchen.home
    )
