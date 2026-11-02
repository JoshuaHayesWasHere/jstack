"""An ask the user made in a turn that stopped on a usage limit or an auth error is owed: jbus
keeps it with its cause and sends it again once, when the account frees. The tests run the real
pass against the kitchen's fakes. The thread items take the shapes T3 Code gave the 5 asks of the
week audit (`scouts/week-audit-a-lost-asks.md`), and `test_the_week_audit` replays those 5."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import jbus
from jbus import owed, record
from jroles import ledger
from test_jbus_failover import PRIME, failed_on, pools  # noqa: F401
from test_jbus_kitchen import NOW, sends
from test_jbus_leftover import home

ASK = "where in cloudflare do i make these tokens?"
SESSION = "You've hit your session limit · resets 3:10pm (America/New_York)"
EXPIRED = "Failed to authenticate: OAuth session expired and could not be refreshed"
RESETS = NOW + timedelta(minutes=40)
AFTER = RESETS + timedelta(minutes=1)


def said(text, at=NOW, run="run-1", by="user", item="ask-1", position=1):
    """A message in a thread, typed by the user unless `by` says otherwise."""
    return {
        "position": position,
        "itemId": f"turn-item:message:{item}",
        "messageId": item,
        "runId": run,
        "createdBy": by,
        "creationSource": "web" if by == "user" else "mcp",
        "type": "user_message",
        "status": "completed",
        "text": text,
        "updatedAt": at.isoformat(),
    }


def limit(run="run-1", at=RESETS):
    """The three items a run ends on at a five-hour limit that resets at `at`."""
    stamp = int(at.timestamp())
    return [
        {"runId": run, "itemId": f"{run}:usage-limit:five_hour:{stamp}", "type": "system_notice"},
        {"runId": run, "itemId": f"{run}:said", "type": "assistant_message", "text": SESSION},
        {"runId": run, "itemId": f"{run}:end", "type": "error", "text": "Usage limit reached"},
    ]


def auth(run="run-1"):
    """The two items a run ends on when its session expired."""
    could_not = "Claude could not authenticate. For subscription login, run `claude auth login`."
    return [
        {"runId": run, "itemId": f"{run}:said", "type": "assistant_message", "text": EXPIRED},
        {"runId": run, "itemId": f"{run}:end", "type": "error", "text": could_not},
    ]


def stopped(thread, items, run="run-1", ran_on="claudeAgent", status="failed", older=()):
    """Set what T3 Code shows of a thread whose last run ended on `items`."""
    runs = [
        *older,
        {
            "runId": run,
            "status": status,
            "providerInstanceId": ran_on,
            "completedAt": NOW.isoformat(),
        },
    ]
    thread.update(
        status=status,
        latestRunId=run,
        itemCount=len(items),
        runs=runs,
        read_items=items,
        snoozed=False,
    )


@pytest.fixture
def free(kitchen):
    """A thread of the project that no brief and no home names, as T3 Code lists it."""
    return kitchen.t3.thread("x", "completed", title="Weekly recap", idle=timedelta(minutes=1))


def resent(kitchen):
    return [one for one in sends(kitchen) if one["clientRequestId"].startswith("ask|")]


def asks(kitchen):
    return owed.load(kitchen.state)


def signed_in(at, expires=None):
    """Write the built-in Claude home's credentials at `at`, as a `claude auth login` does."""
    file = Path.home() / ".claude" / ".credentials.json"
    file.parent.mkdir(exist_ok=True)
    lives = (expires or at + timedelta(hours=8)).timestamp() * 1000
    file.write_text(json.dumps({"claudeAiOauth": {"accessToken": "t", "expiresAt": lives}}))
    os.utime(file, (at.timestamp(), at.timestamp()))


def test_an_ask_that_stopped_on_a_limit_is_owed_and_sent_when_the_cap_lifts(kitchen, free):
    stopped(free, [said(ASK), *limit()])
    lines = kitchen.poll(NOW)
    assert resent(kitchen) == []
    (ask,) = asks(kitchen)
    assert (ask.state, ask.cause, ask.until) == ("owed", owed.LIMIT, RESETS.isoformat())
    assert ask.text == ASK and ask.line == SESSION and ask.thread == free["threadId"]
    assert any(line.startswith("owed Weekly recap:") for line in lines)
    assert kitchen.lines("ask-owed")
    assert ledger.capped_until(ledger.read(["claudeAgent"]), "claudeAgent", NOW) == RESETS
    kitchen.poll(NOW + timedelta(minutes=3))
    assert resent(kitchen) == []
    kitchen.poll(AFTER)
    (sent,) = resent(kitchen)
    assert sent["threadId"] == free["threadId"] and sent["mode"] == "queue"
    assert sent["message"].endswith(f"\n\n{ASK}")
    assert SESSION in sent["message"]
    assert kitchen.lines("ask-resent")


def test_an_ask_that_stopped_on_an_auth_error_waits_for_the_session_and_is_sent_once(kitchen, free):
    signed_in(NOW - timedelta(hours=1))
    stopped(free, [said(ASK), *auth()])
    lines = kitchen.poll(NOW + timedelta(minutes=1))
    (ask,) = asks(kitchen)
    assert (ask.state, ask.cause, ask.until) == ("owed", owed.AUTH, "")
    assert resent(kitchen) == [] and any("signed in again" in line for line in lines)
    signed_in(NOW + timedelta(minutes=2))
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=4))
    (sent,) = resent(kitchen)
    assert sent["message"].endswith(ASK) and EXPIRED in sent["message"]


def test_credentials_written_again_with_a_dead_token_renew_nothing(kitchen, free):
    stopped(free, [said(ASK), *auth()])
    signed_in(NOW + timedelta(minutes=2), expires=NOW)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert resent(kitchen) == []


def test_a_thread_moved_off_the_signed_out_instance_is_free(kitchen, free):
    signed_in(NOW - timedelta(hours=1))
    free["selection"] = {"model": "m", "instanceId": PRIME}
    stopped(free, [said(ASK), *auth()])
    kitchen.poll(NOW + timedelta(minutes=1))
    assert len(resent(kitchen)) == 1


def test_a_re_send_runs_once_over_passes_and_over_a_crash_before_its_mark(kitchen, free):
    stopped(free, [said(ASK), *limit()])
    kitchen.poll(NOW)
    kitchen.poll(AFTER)
    kitchen.poll(AFTER + timedelta(minutes=2))
    (sent,) = resent(kitchen)
    key = sent["clientRequestId"]
    assert key == f"ask|{free['threadId']}|ask-1|1"
    (kept,) = json.loads((kitchen.state / owed.FILE).read_text())["asks"]
    kept["state"] = "owed"
    (kitchen.state / owed.FILE).write_text(json.dumps({"asks": [kept], "looked": {}}))
    marks = [one for one in json.loads((kitchen.state / "sent.json").read_text()) if one != key]
    (kitchen.state / "sent.json").write_text(json.dumps(marks))
    kitchen.poll(AFTER + timedelta(minutes=4))
    assert [one["clientRequestId"] for one in resent(kitchen)] == [key, key]
    assert list(kitchen.t3.messages).count(key) == 1
    assert [one.state for one in asks(kitchen)] == ["sent"]


@pytest.mark.parametrize("again", [ASK, ASK.upper() + "  ", "Continue where you left off."])
def test_an_ask_the_user_repeated_is_not_sent(kitchen, free, again):
    stopped(free, [said(ASK), *limit()])
    kitchen.poll(NOW)
    later = [said(ASK), *limit(), said(again, run="run-2", item="ask-2", position=5)]
    older = [{"runId": "run-1", "status": "failed"}]
    stopped(free, later, run="run-2", status="completed", older=older)
    kitchen.poll(AFTER)
    assert resent(kitchen) == []
    assert [one.state for one in asks(kitchen)] == ["repeated"]


def test_a_repeat_whose_turn_stopped_too_ran_nothing_and_the_ask_stays_owed(kitchen, free):
    stopped(free, [said(ASK), *limit()])
    kitchen.poll(NOW)
    resume = said("Continue where you left off", run="run-2", item="ask-2", position=5)
    later = [said(ASK), *limit(), resume, *limit("run-2")]
    stopped(free, later, run="run-2", older=[{"runId": "run-1", "status": "failed"}])
    kitchen.poll(NOW + timedelta(minutes=1))
    assert [one.state for one in asks(kitchen)] == ["owed"]
    kitchen.poll(AFTER)
    (sent,) = resent(kitchen)
    assert sent["message"].endswith(ASK)


def test_a_later_message_on_something_else_leaves_the_ask_owed(kitchen, free):
    """0f8b3189: a new question answered at once, and the ask behind it done only 3 days later."""
    stopped(free, [said(ASK), *limit()])
    kitchen.poll(NOW)
    other = said("why so many crewmates?", run="run-2", item="ask-2", position=5)
    older = [{"runId": "run-1", "status": "failed"}]
    stopped(free, [said(ASK), *limit(), other], run="run-2", status="completed", older=older)
    kitchen.poll(AFTER)
    (sent,) = resent(kitchen)
    assert sent["message"].endswith(ASK) and "say so in one line" in sent["message"]


def test_what_jbus_or_a_home_sent_is_no_ask_of_the_user_s(kitchen, free):
    stopped(free, [said("jbus: a hold-stall", by="agent"), *limit()])
    kitchen.poll(NOW)
    kitchen.poll(AFTER)
    assert asks(kitchen) == [] and resent(kitchen) == []
    assert ledger.read(["claudeAgent"]) == {}


def test_a_failure_that_is_no_limit_and_no_auth_error_owes_nothing(kitchen, free):
    """051db541: its stream closed, and no item names a limit."""
    closed = "The provider event stream closed unexpectedly. Retry the turn."
    stopped(free, [said(ASK), {"runId": "run-1", "itemId": "e", "type": "error", "text": closed}])
    kitchen.poll(NOW)
    assert asks(kitchen) == []


def test_a_command_that_prints_a_limit_line_is_no_stop(kitchen, free):
    printed = {"runId": "run-1", "itemId": "c", "type": "command_execution", "text": SESSION}
    stopped(free, [said(ASK), printed, {"runId": "run-1", "itemId": "e", "type": "error"}])
    kitchen.poll(NOW)
    assert asks(kitchen) == []


def test_a_settled_thread_owes_nothing(kitchen, free):
    stopped(free, [said(ASK), *limit()])
    kitchen.poll(NOW)
    free["settled"] = True
    kitchen.poll(AFTER)
    assert resent(kitchen) == []
    assert [one.state for one in asks(kitchen)] == ["ended"]


def test_a_deleted_thread_owes_nothing(kitchen, free):
    stopped(free, [said(ASK), *limit()])
    kitchen.poll(NOW)
    kitchen.t3.threads.remove(free)
    kitchen.poll(AFTER)
    assert resent(kitchen) == []
    assert [one.state for one in asks(kitchen)] == ["ended"]


def test_a_re_send_whose_turn_stopped_too_is_owed_again_under_its_next_key(kitchen, free):
    stopped(free, [said(ASK), *limit()])
    kitchen.poll(NOW)
    kitchen.poll(AFTER)
    (first,) = resent(kitchen)
    again = AFTER + timedelta(hours=1)
    ours = said(first["message"], run="run-2", by="agent", item="m2", position=5)
    older = [{"runId": "run-1", "status": "failed"}]
    stopped(free, [said(ASK), *limit(), ours, *limit("run-2", again)], run="run-2", older=older)
    kitchen.poll(AFTER + timedelta(minutes=1))
    assert len(resent(kitchen)) == 1
    (ask,) = asks(kitchen)
    assert (ask.state, ask.tries, ask.until) == ("owed", 2, again.isoformat())
    kitchen.poll(again + timedelta(minutes=1))
    assert [one["clientRequestId"].rsplit("|", 1)[1] for one in resent(kitchen)] == ["1", "2"]


def test_a_home_s_carry_on_quotes_the_ask_and_nothing_goes_twice(kitchen):
    desk = home(kitchen, idle=timedelta(minutes=1))
    stopped(desk, [said(ASK), *limit()], ran_on="claudeAgent")
    kitchen.poll(NOW)
    (carry,) = [one for one in sends(kitchen) if one["clientRequestId"].startswith("failover|")]
    assert carry["message"].endswith(ASK) and "usage limit" in carry["message"]
    assert resent(kitchen) == []
    assert [one.state for one in asks(kitchen)] == ["sent"]
    kitchen.poll(AFTER)
    assert resent(kitchen) == []


def test_a_home_that_a_wake_took_off_failed_still_gets_its_ask(kitchen):
    """The home of 2026-10-26: a message started a new turn before the reset, so `failover` never
    saw it failed again, and the ask went with it."""
    desk = home(kitchen, idle=timedelta(minutes=1))
    stopped(desk, [said(ASK), *limit()])
    every = {"model": "m", "instanceId": "claudeAgent"}
    desk["selection"] = every
    ledger.write(ledger.Record(PRIME, "five_hour", 100, int(RESETS.timestamp())))
    kitchen.poll(NOW)
    assert resent(kitchen) == [] and [one.state for one in asks(kitchen)] == ["owed"]
    wake = said("jbus: a wake", run="run-2", by="agent", item="m2", position=5)
    stopped(desk, [said(ASK), *limit(), wake], run="run-2", status="completed")
    kitchen.poll(AFTER)
    (sent,) = resent(kitchen)
    assert sent["message"].endswith(ASK)


def test_jbus_status_shows_what_a_cap_holds_with_its_cause_and_when_it_frees(kitchen, free):
    config = jbus.load()
    stopped(free, [said(ASK), *limit()])
    kitchen.poll(NOW)
    (ask,) = record.status(config, NOW)["projects"]["demo"]["capped"]
    assert ask["row"] == "Weekly recap" and ask["cause"] == SESSION
    assert ask["frees"] == config.user.stamp(RESETS)
    kitchen.poll(AFTER)
    assert record.status(config, AFTER)["projects"]["demo"]["capped"] == []


def test_jbus_status_shows_a_held_message_and_a_launch_held_by_a_cap(kitchen):
    state, config = kitchen.state, jbus.load()
    state.mkdir(parents=True, exist_ok=True)
    until = RESETS.isoformat()
    line = {
        "row": "alpha",
        "template": "rebase",
        "key": "k",
        "went": "held",
        "rule": f"cap: until {until}",
    }
    (state / "outbox.jsonl").write_text(json.dumps(line) + "\n")
    (state / "sent.json").write_text(json.dumps([f"stall|beta|capped {until}"]))
    rows = record.status(config, NOW)["projects"]["demo"]["capped"]
    assert {(one["row"], one["cause"], one["frees"]) for one in rows} == {
        ("alpha", "usage cap", config.user.stamp(RESETS)),
        ("beta", "usage cap", config.user.stamp(RESETS)),
    }
    assert record.status(config, AFTER)["projects"]["demo"]["capped"] == []


WEEK_AUDIT = {
    "62108874": (auth(), owed.AUTH, ""),
    "0f8b3189": (limit(at=datetime.fromtimestamp(1793044800, UTC)), owed.LIMIT, "1793044800"),
    "a7e76e2d": (limit(at=datetime.fromtimestamp(1793387400, UTC)), owed.LIMIT, "1793387400"),
    "08f6bf1c": (limit(at=datetime.fromtimestamp(1793387400, UTC)), owed.LIMIT, "1793387400"),
}


@pytest.mark.parametrize("ask", WEEK_AUDIT)
def test_the_week_audit(ask):
    """Four of the five asks stopped on what `stop_of` reads. The fifth is above: its stream
    closed."""
    items, cause, resets = WEEK_AUDIT[ask]
    found = owed.stop_of(items, datetime(2026, 10, 19, tzinfo=UTC))
    assert found.cause == cause
    if resets:
        assert int(found.cap.resets.timestamp()) == int(resets)
