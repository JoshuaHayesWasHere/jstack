"""A thread whose last turn failed on a usage limit goes on, once, on the other Claude
instance with its model and options, and the reset it read is the instance's capped-until.
Run as `tests/test_jbus_resume.py` runs: the real pass against the fakes, with a clock the
test moves."""

import json
from datetime import timedelta

import jbus
from jroles import failover
from test_jbus_kitchen import NOW, SELECTION, approved, sends
from test_jbus_resume import THREAD, crew

WEEKLY = "You've hit your weekly limit · resets Oct 18, 4pm (America/New_York)"
RESET = "2026-10-18T20:00:00+00:00"
AFTER = NOW + timedelta(days=7)
PRIME = failover.FALLBACK


def failed_on(thread, text, run="run-1", ran_on="claudeAgent", **more):
    """The thread's last turn ended on `text`, as T3 Code shows one: an assistant message
    with the limit, then the error."""
    thread.update(
        status="failed",
        latestRunId=run,
        itemCount=4,
        runs=[{"runId": run, "providerInstanceId": ran_on}],
        read_items=[
            {"runId": run, "type": "assistant_message", "text": text},
            {"runId": run, "type": "error", "text": "Claude API rate limit reached."},
        ],
        **more,
    )


def configures(kitchen):
    return [given for tool, given in kitchen.t3.calls if tool == "t3_thread_configure"]


def failovers(kitchen):
    return kitchen.lines("failover")


def capped(kitchen):
    return failover.load(kitchen.state_dir / failover.FILE)


def test_a_weekly_limit_failure_is_retried_once_on_prime_with_its_model_and_options(kitchen):
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    said = kitchen.poll()
    assert configures(kitchen) == [
        {"threadId": THREAD, "modelSelection": {**SELECTION, "instanceId": PRIME}}
    ]
    (carry,) = sends(kitchen)
    assert carry["threadId"] == THREAD and carry["mode"] == "queue"
    assert carry["clientRequestId"] == f"failover|{THREAD}|run-1"
    assert WEEKLY in carry["message"] and f"now on {PRIME}" in carry["message"]
    assert "read `tasks/alpha.md`" in carry["message"]
    line = (
        f"failover alpha: weekly limit until {RESET}, carry-on on claudeAgent to {PRIME}, "
        "model claude-sonnet-5-5, effort=high, fastMode=True"
    )
    assert failovers(kitchen) == [line] and line in said
    assert capped(kitchen) == {"claudeAgent": failover.datetime.fromisoformat(RESET)}
    assert kitchen.lines("resume") == []


def test_the_same_failure_seen_on_two_passes_retries_once(kitchen):
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert len(sends(kitchen)) == 1 and len(configures(kitchen)) == 1
    assert len(failovers(kitchen)) == 1 and kitchen.lines("resume") == []
    assert thread["selection"]["instanceId"] == PRIME


def test_a_thread_already_on_prime_is_not_moved_again(kitchen):
    thread = crew(kitchen)
    thread["selection"] = {**SELECTION, "instanceId": PRIME}
    failed_on(thread, WEEKLY)
    kitchen.poll()
    assert configures(kitchen) == []
    (carry,) = sends(kitchen)
    assert f"now on {PRIME}" in carry["message"]


def test_a_limit_failure_is_no_carry_on_of_the_resume_path(kitchen):
    """The two carry-ons of a thread are for a thread that ended, not for a capped one."""
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    kitchen.poll()
    failed_on(thread, WEEKLY, run="run-2")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [given["clientRequestId"] for given in sends(kitchen)] == [
        f"failover|{THREAD}|run-1",
        f"failover|{THREAD}|run-2",
    ]
    assert not any(key.startswith("resume|") for key in kitchen.marks())


def test_a_failure_that_is_no_limit_goes_the_way_it_went(kitchen):
    thread = crew(kitchen)
    thread.update(status="failed", latestRunId="run-1", itemCount=2)
    thread["read_items"] = [{"runId": "run-1", "type": "error", "text": "Claude API overloaded"}]
    kitchen.poll()
    assert configures(kitchen) == [] and failovers(kitchen) == []
    assert kitchen.lines("resume") == ["resume alpha: told the crew to carry on (failed, 1 of 2)"]


def test_after_the_reset_the_next_nudge_goes_back_to_claude_agent(kitchen):
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    kitchen.poll()
    assert thread["selection"]["instanceId"] == PRIME
    failed_on(
        thread,
        "You've hit your session limit · resets 11pm (America/New_York)",
        "run-2",
        ran_on=PRIME,
    )
    kitchen.poll(AFTER)
    assert configures(kitchen)[-1]["modelSelection"] == SELECTION | {"instanceId": "claudeAgent"}
    assert sends(kitchen)[-1]["clientRequestId"] == f"failover|{THREAD}|run-2"
    assert failovers(kitchen)[-1].endswith(
        f"carry-on on {PRIME} to claudeAgent, model claude-sonnet-5-5, effort=high, fastMode=True"
    )


def test_both_capped_waits_for_the_earlier_reset_and_says_so_once(kitchen):
    thread = crew(kitchen)
    file = kitchen.state_dir / failover.FILE
    failover.mark(file, PRIME, failover.read_limit(WEEKLY, NOW), NOW)
    failed_on(thread, "You've hit your weekly limit · resets Oct 20, 4pm (America/New_York)")
    for minutes in (0, 3, 6, 9):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert sends(kitchen) == [] and configures(kitchen) == []
    (alert,) = kitchen.lines("stall")
    assert alert == (
        f"capped alpha: claudeAgent and {PRIME} are both capped until {RESET}; "
        "it is sent on at the earlier reset"
    )
    assert kitchen.lines("resume") == []
    kitchen.poll(AFTER)
    assert len(sends(kitchen)) == 1 and len(configures(kitchen)) == 1
    assert configures(kitchen)[0]["modelSelection"]["instanceId"] == PRIME
    assert len(kitchen.lines("stall")) == 1


def test_a_home_thread_is_moved_and_told_to_carry_on_from_its_handoff(kitchen):
    home = kitchen.t3.thread("home", "failed", title="home: demo")
    (kitchen.home / "home-id").write_text(f"{home['threadId']} 2026-10-12\n")
    failed_on(home, WEEKLY)
    kitchen.poll()
    (given,) = configures(kitchen)
    assert given["threadId"] == home["threadId"]
    assert given["modelSelection"]["instanceId"] == PRIME
    (carry,) = sends(kitchen)
    assert "read your handoff" in carry["message"]


def test_a_thread_no_brief_and_no_home_names_is_left_alone(kitchen):
    other = kitchen.t3.thread("stray", "failed", title="a chat")
    failed_on(other, WEEKLY)
    kitchen.poll()
    assert configures(kitchen) == [] and sends(kitchen) == [] and capped(kitchen) == {}


def test_a_failure_of_a_thread_on_another_provider_marks_nothing(kitchen):
    thread = crew(kitchen)
    thread["selection"] = {"instanceId": "grok", "model": "grok-build"}
    failed_on(thread, WEEKLY)
    kitchen.poll()
    assert capped(kitchen) == {} and configures(kitchen) == []


def test_capped_json_keeps_the_later_reset_and_holds_a_blind_limit_for_an_hour(tmp_path):
    file = tmp_path / failover.FILE
    late = failover.read_limit(WEEKLY, NOW)
    soon = failover.read_limit("You've hit your 5-hour limit", NOW)
    assert failover.mark(file, "claudeAgent", late, NOW)
    assert not failover.mark(file, "claudeAgent", soon, NOW)
    assert not failover.mark(file, "claudeAgent", late, NOW)
    assert json.loads(file.read_text())["claudeAgent"]["until"] == RESET
    assert soon.until == NOW + failover.BLIND
    assert failover.read_limit("Claude API rate limit reached.", NOW) is None
    assert jbus.read_json(file, {})["claudeAgent"]["kind"] == "weekly"


CHOSEN = {"instanceId": "claudeAgent", "model": "claude-sonnet-5-5"}


def cap(kitchen, instance, text=WEEKLY):
    failover.mark(kitchen.state_dir / failover.FILE, instance, failover.read_limit(text, NOW), NOW)


def test_a_launch_while_claude_agent_is_capped_starts_on_prime_and_says_why(kitchen):
    kitchen.config(modelSelection=CHOSEN)
    cap(kitchen, "claudeAgent")
    approved(kitchen, "alpha")
    said = kitchen.poll()
    (given,) = kitchen.t3.launches
    assert given["modelSelection"] == {**CHOSEN, "instanceId": PRIME}
    (line,) = [line for line in said if line.startswith("launched alpha")]
    assert line.endswith(f" on {PRIME}, claudeAgent is capped until {RESET}")


def test_a_launch_after_the_reset_goes_back_to_claude_agent(kitchen):
    kitchen.config(modelSelection=CHOSEN)
    cap(kitchen, "claudeAgent")
    kitchen.config(modelSelection=CHOSEN, max_running=2)
    approved(kitchen, "alpha")
    kitchen.poll()
    approved(kitchen, "beta", priority=2)
    kitchen.poll(AFTER)
    chosen = [given["modelSelection"]["instanceId"] for given in kitchen.t3.launches]
    assert chosen == [PRIME, "claudeAgent"]


def test_a_launch_with_both_capped_waits_and_says_so_once(kitchen):
    kitchen.config(modelSelection=CHOSEN)
    cap(kitchen, "claudeAgent")
    cap(kitchen, PRIME, "You've hit your weekly limit · resets Oct 20, 4pm (America/New_York)")
    approved(kitchen, "alpha")
    first = kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kitchen.t3.launches == []
    assert [line for line in first if line.startswith("wait alpha")] == [
        f"wait alpha: no launch: claudeAgent and {PRIME} are both capped until {RESET}"
    ]
    assert len(kitchen.lines("stall")) == 1
    kitchen.poll(AFTER)
    assert [given["modelSelection"]["instanceId"] for given in kitchen.t3.launches] == [
        "claudeAgent"
    ]
