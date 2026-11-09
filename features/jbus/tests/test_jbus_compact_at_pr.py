"""Once a crew's Result names its pull request and the crew's turn has ended, jbus sends its thread
`/compact`, once for the row, so the crew waits on its checks with a small context and not the one
its work built up. A thread at work, a thread whose last call was small or is not in jbus's
telemetry store yet, and a pull request that is no longer open get none.

The tests run the real pass against the fakes, as `test_jbus_github.py` does."""

import json
from datetime import timedelta

import pytest

from jbus import telemetry
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add

URL = "https://example.test/pull/7"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    """Alpha is a row that a first pass launched, its thread at work."""
    made = Kitchen(tmp_path, monkeypatch)
    add(made, "alpha")
    assert "launched alpha: mcp:thread-1" in made.poll(NOW - timedelta(minutes=30))
    yield made
    made.close()


def opened(kitchen, url=URL):
    """Open alpha's pull request, and append the Result that names it."""
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    brief = kitchen.home / "tasks" / "alpha.md"
    result = f"\n## Result\nStatus: done\nBranch: alpha   Pull request: {url}\n"
    brief.write_text(brief.read_text() + result)


def ends(kitchen):
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"


def compacts(kitchen):
    """The `compact` lines of the outbox, as (went, rule)."""
    path = kitchen.state / "outbox.jsonl"
    lines = [json.loads(one) for one in path.read_text().splitlines()] if path.exists() else []
    return [(one["went"], one["rule"]) for one in lines if one["template"] == "compact"]


def sent(kitchen):
    return [
        given
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send" and given["message"] == "/compact"
    ]


def last_call(kitchen, thread, tokens):
    """Have jbus's telemetry store hold one call of the thread's session, of `tokens` sent."""
    store = telemetry.connect(kitchen.state_dir / telemetry.FILE)
    store.execute(
        "INSERT INTO sessions (provider, session, thread, project, role, slug) "
        "VALUES ('claude', 's1', ?, 'demo', 'crew', 'alpha')",
        (thread,),
    )
    store.execute(
        "INSERT INTO calls (provider, call, session, at, input, cache_write, cache_read, output, "
        "final) VALUES ('claude', 'c1', 's1', ?, 2, 1000, ?, 10, 1)",
        (NOW.isoformat(), tokens - 1002),
    )
    store.close()


def test_an_idle_crew_with_its_pull_request_open_is_compacted_once(kitchen):
    opened(kitchen)
    ends(kitchen)
    last_call(kitchen, "mcp:thread-1", 160_000)
    kitchen.poll(NOW)
    assert compacts(kitchen) == [("sent", "")]
    assert [(one["threadId"], one["clientRequestId"]) for one in sent(kitchen)] == [
        ("mcp:thread-1", "compact|alpha")
    ]
    kitchen.poll(NOW + timedelta(minutes=3))
    assert compacts(kitchen) == [("sent", "")]
    assert len(sent(kitchen)) == 1


def test_a_crew_at_work_is_not_compacted_until_its_turn_ends(kitchen):
    opened(kitchen)
    last_call(kitchen, "mcp:thread-1", 160_000)
    kitchen.poll(NOW)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert compacts(kitchen) == []
    assert sent(kitchen) == []
    ends(kitchen)
    kitchen.poll(NOW + timedelta(minutes=6))
    assert compacts(kitchen) == [("sent", "")]


def test_a_crew_whose_last_call_was_small_is_not_compacted(kitchen):
    opened(kitchen)
    ends(kitchen)
    last_call(kitchen, "mcp:thread-1", 99_000)
    kitchen.poll(NOW)
    assert compacts(kitchen) == []
    assert sent(kitchen) == []


def test_a_crew_whose_last_call_is_not_in_the_store_yet_is_not_compacted(kitchen):
    opened(kitchen)
    ends(kitchen)
    kitchen.poll(NOW)
    assert compacts(kitchen) == []
    assert sent(kitchen) == []


def test_a_pull_request_no_longer_open_gets_none(kitchen):
    opened(kitchen)
    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "c" * 40)])
    ends(kitchen)
    last_call(kitchen, "mcp:thread-1", 160_000)
    kitchen.poll(NOW)
    assert compacts(kitchen) == []
    assert sent(kitchen) == []


def test_a_result_that_names_no_pull_request_gets_none(kitchen):
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    brief = kitchen.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text() + "\n## Result\nStatus: done\nPull request: after the review\n")
    ends(kitchen)
    last_call(kitchen, "mcp:thread-1", 160_000)
    kitchen.poll(NOW)
    assert compacts(kitchen) == []
