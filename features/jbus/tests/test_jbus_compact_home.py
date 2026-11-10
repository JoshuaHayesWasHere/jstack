"""A home's context has a ceiling: once a home's last call sent `compact.CEILING` tokens or more
and its turn has ended, jbus sends its thread `/compact`, once for that call, so a busy home that
never sits idle long enough for T3 Code's own compaction is bounded all the same. A home at work,
one under the ceiling and one the store holds no call of get none, and a home sent `/compact` in a
pass hears its wake on the next pass.

The tests run the real pass against the fakes, as `test_jbus_compact_at_pr.py` does."""

import json
from datetime import timedelta

import pytest

from jbus import compact, telemetry
from jbus.telemetry import migrations
from test_jbus_kitchen import NOW, Kitchen

MIN = timedelta(minutes=1)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    """The root home of the project is a thread whose turn has ended."""
    made = Kitchen(tmp_path, monkeypatch)
    home = made.t3.thread("demo", "completed", title="home: demo")
    (made.home / "home-id").write_text(home["threadId"] + "\n")
    made.thread = home["threadId"]
    yield made
    made.close()


def calls(kitchen, *spoken):
    """Have jbus's telemetry store hold the home's main calls, each (minutes after NOW, tokens)."""
    store = telemetry.connect(kitchen.state_dir / telemetry.FILE)
    store.execute(
        "INSERT OR IGNORE INTO sessions (provider, session, thread, project, role, slug) "
        "VALUES ('claude', 'h1', ?, 'demo', 'home', '')",
        (kitchen.thread,),
    )
    for minutes, tokens in spoken:
        store.execute(
            "INSERT INTO calls (provider, call, session, at, input, cache_write, cache_read, "
            "output, final) VALUES ('claude', ?, 'h1', ?, 2, 1000, ?, 10, 1)",
            (f"h{minutes}", stamp(minutes), tokens - 1002),
        )
    store.commit()
    store.close()


def stamp(minutes):
    """A call's `at`, as the transcripts write it and the store keeps it."""
    return (NOW + minutes * MIN).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sent(kitchen):
    """The `/compact` messages T3 Code was sent, as (thread, key)."""
    return [
        (given["threadId"], given["clientRequestId"])
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send" and given["message"] == "/compact"
    ]


def wakes(kitchen):
    return [
        given
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send" and given["message"].startswith("jbus: ")
    ]


def key(kitchen, minutes):
    return f"compact|home|{kitchen.thread}|{stamp(minutes)}"


def test_an_idle_home_at_the_ceiling_is_compacted_once(kitchen):
    calls(kitchen, (0, compact.CEILING))
    kitchen.poll(NOW + MIN)
    assert sent(kitchen) == [(kitchen.thread, key(kitchen, 0))]
    kitchen.poll(NOW + 4 * MIN)
    assert len(sent(kitchen)) == 1


def test_a_home_at_work_is_compacted_once_its_turn_ends(kitchen):
    calls(kitchen, (0, 300_000))
    (home,) = [one for one in kitchen.t3.threads if one["threadId"] == kitchen.thread]
    home["status"] = "running"
    kitchen.poll(NOW + MIN)
    assert sent(kitchen) == []
    home["status"] = "completed"
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen) == [(kitchen.thread, key(kitchen, 0))]


def test_a_home_under_the_ceiling_is_not_compacted(kitchen):
    calls(kitchen, (0, compact.CEILING - 1))
    kitchen.poll(NOW + MIN)
    assert sent(kitchen) == []


def test_a_home_the_store_holds_no_call_of_is_not_compacted(kitchen):
    kitchen.poll(NOW + MIN)
    assert sent(kitchen) == []


def test_a_compacted_home_that_speaks_small_gets_none(kitchen):
    calls(kitchen, (0, 400_000))
    kitchen.poll(NOW + MIN)
    calls(kitchen, (2, 60_000))
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen) == [(kitchen.thread, key(kitchen, 0))]


def test_a_lost_compaction_is_sent_again_only_after_a_newer_call_at_the_ceiling(kitchen):
    """T3 Code took the message and the home did not shrink: the store's last call is the same
    one, so the next pass sends nothing, and the home's next call at the ceiling is a new key."""
    calls(kitchen, (0, 200_000))
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen) == [(kitchen.thread, key(kitchen, 0))]
    calls(kitchen, (5, 210_000))
    kitchen.poll(NOW + 7 * MIN)
    assert sent(kitchen) == [(kitchen.thread, key(kitchen, 0)), (kitchen.thread, key(kitchen, 5))]


def test_a_send_t3_code_did_not_take_goes_again_at_the_next_pass(kitchen):
    calls(kitchen, (0, 200_000))
    kitchen.t3.lose_send = True
    said = kitchen.poll(NOW + MIN)
    assert any("could not be compacted" in line for line in said)
    kitchen.t3.lose_send = False
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen)[-1] == (kitchen.thread, key(kitchen, 0))


def test_a_home_sent_compact_hears_its_wake_at_the_next_pass(kitchen):
    """A home's wake waits for the pass after its `/compact`, and loses none of its items."""
    (kitchen.home / "notes.md").write_text("# notes\n- 2026-11-02: a rule\n")
    calls(kitchen, (0, 200_000))
    kitchen.poll(NOW + MIN)
    assert sent(kitchen) == [(kitchen.thread, key(kitchen, 0))]
    assert wakes(kitchen) == []
    for one in kitchen.t3.threads:
        one["status"] = "completed"
    kitchen.poll(NOW + 4 * MIN)
    (woke,) = wakes(kitchen)
    assert woke["threadId"] == kitchen.thread
    assert "notes.md" in woke["message"]
    told = json.loads((kitchen.state / "outbox.jsonl").read_text().splitlines()[-1])
    assert told["template"] == "wakes"


def test_a_call_the_store_reads_late_from_before_the_compaction_sends_none_again(kitchen):
    """The store is built by a chore that can trail a pass: a call made before the `/compact`
    went, and read only after, is the same climb and not a new one."""
    calls(kitchen, (0, 200_000))
    kitchen.poll(NOW + 2 * MIN)
    calls(kitchen, (1, 220_000))
    kitchen.poll(NOW + 5 * MIN)
    assert sent(kitchen) == [(kitchen.thread, key(kitchen, 0))]


def test_a_send_t3_code_refused_is_not_sent_again_for_that_call(kitchen):
    calls(kitchen, (0, 200_000))
    kitchen.t3.refuse_send = True
    said = kitchen.poll(NOW + MIN)
    assert any("T3 Code refused" in line for line in said)
    kitchen.t3.refuse_send = False
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen) == [(kitchen.thread, key(kitchen, 0))]


def test_the_last_call_of_a_thread_is_read_through_the_index_of_sessions_by_thread(kitchen):
    """`v018_sessions_thread` adds the index, and the read of `compact.last_call` takes it."""
    assert "sessions_thread" in migrations.MIGRATIONS["v018_sessions_thread"]
    store = telemetry.connect(kitchen.state_dir / telemetry.FILE)
    plan = store.execute("EXPLAIN QUERY PLAN " + compact._LAST, ("mcp:x",)).fetchall()
    store.close()
    assert any("sessions_thread" in str(row[-1]) for row in plan)
