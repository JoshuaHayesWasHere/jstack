"""A crew's context has a ceiling of 180k and a scout's of 330k: once such a thread's last call
sent its ceiling or more and its turn has ended, `jbus.compact` sends its thread `/compact`, once
for that call, so a crew or a scout that waits between turns (on a review, a check or an answer) is
not woken with its whole context. A thread under its ceiling, one at work, one T3 Code archived and
one of another role get none, and a crew compacted at its pull request is not compacted again for
the same call.

The tests run the real pass against the fakes, as `test_jbus_compact_home.py` does."""

from datetime import timedelta

import pytest

from jbus import telemetry
from test_jbus_kitchen import NOW, PROJECT, Kitchen
from test_jbus_queue import add

MIN = timedelta(minutes=1)
URL = "https://example.test/pull/7"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def thread(kitchen, title, status="completed", **more):
    """A thread of the project, as T3 Code lists it, whose turn has ended."""
    return kitchen.t3.thread(title.split(": ")[-1], status, title=title, **more)["threadId"]


def calls(kitchen, at, *spoken):
    """Have jbus's telemetry store hold the thread's main calls, each (minutes after NOW,
    tokens)."""
    store = telemetry.connect(kitchen.state_dir / telemetry.FILE)
    store.execute(
        "INSERT OR IGNORE INTO sessions (provider, session, thread, project, role, slug) "
        "VALUES ('claude', ?, ?, 'demo', '', '')",
        (f"s-{at}", at),
    )
    for minutes, tokens in spoken:
        store.execute(
            "INSERT INTO calls (provider, call, session, at, input, cache_write, cache_read, "
            "output, final) VALUES ('claude', ?, ?, ?, 2, 1000, ?, 10, 1)",
            (f"{at}-{minutes}", f"s-{at}", stamp(minutes), tokens - 1002),
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


@pytest.mark.parametrize(
    ("title", "role", "ceiling"),
    [
        ("crew: alpha", "crew", 180_000),
        ("scout: probe", "scout", 330_000),
    ],
)
def test_an_idle_thread_at_its_roles_ceiling_is_compacted_once_for_that_call(
    kitchen, title, role, ceiling
):
    at = thread(kitchen, title)
    calls(kitchen, at, (0, ceiling))
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen) == [(at, f"compact|{role}|{at}|{stamp(0)}")]


@pytest.mark.parametrize(
    ("title", "tokens"),
    [
        ("crew: alpha", 179_999),
        ("scout: probe", 329_999),
        ("review: alpha", 600_000),
    ],
)
def test_a_thread_under_its_ceiling_or_of_a_role_with_none_is_not_compacted(kitchen, title, tokens):
    at = thread(kitchen, title)
    calls(kitchen, at, (0, tokens))
    kitchen.poll(NOW + MIN)
    assert sent(kitchen) == []


def test_a_scout_at_work_is_compacted_once_its_turn_ends(kitchen):
    at = thread(kitchen, "scout: probe", "running")
    calls(kitchen, at, (0, 400_000))
    kitchen.poll(NOW + MIN)
    assert sent(kitchen) == []
    (scout,) = [one for one in kitchen.t3.threads if one["threadId"] == at]
    scout["status"] = "completed"
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen) == [(at, f"compact|scout|{at}|{stamp(0)}")]


def test_an_archived_thread_is_not_compacted(kitchen):
    """T3 Code archives the thread of a finished task, which is woken no more."""
    at = thread(kitchen, "crew: alpha", archived=True)
    calls(kitchen, at, (0, 400_000))
    kitchen.poll(NOW + MIN)
    assert sent(kitchen) == []


def test_a_crew_climbs_again_after_its_compaction_and_is_compacted_again(kitchen):
    at = thread(kitchen, "crew: alpha")
    calls(kitchen, at, (0, 200_000))
    kitchen.poll(NOW + MIN)
    calls(kitchen, at, (2, 60_000))
    kitchen.poll(NOW + 4 * MIN)
    calls(kitchen, at, (5, 190_000))
    kitchen.poll(NOW + 7 * MIN)
    assert sent(kitchen) == [
        (at, f"compact|crew|{at}|{stamp(0)}"),
        (at, f"compact|crew|{at}|{stamp(5)}"),
    ]


def test_a_crew_compacted_at_its_pull_request_is_not_compacted_again_for_that_call(kitchen):
    """Both rules see the same call: the one at the pull request sends, the ceiling's waits a
    pass behind it (the thread was told something this pass), and the next pass sees the call is
    older than that `/compact`."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - 30 * MIN)
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    brief = kitchen.home / "tasks" / "alpha.md"
    brief.write_text(
        brief.read_text() + f"\n## Result\nStatus: done\nBranch: alpha   Pull request: {URL}\n"
    )
    for one in kitchen.t3.threads:
        one["status"] = "completed"
    calls(kitchen, "mcp:thread-1", (0, 200_000))
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen) == [("mcp:thread-1", "compact|alpha")]
    calls(kitchen, "mcp:thread-1", (5, 190_000))
    kitchen.poll(NOW + 7 * MIN)
    assert sent(kitchen) == [
        ("mcp:thread-1", "compact|alpha"),
        ("mcp:thread-1", f"compact|crew|mcp:thread-1|{stamp(5)}"),
    ]


def test_a_list_t3_code_did_not_give_sends_none_and_the_next_pass_sends_it(kitchen):
    at = thread(kitchen, "scout: probe")
    calls(kitchen, at, (0, 400_000))

    def every_thread_unanswered():
        asked = kitchen.t3.calls[-1][1]
        if set(asked) == {"projectId", "limit"}:
            kitchen.t3.down.add(PROJECT)
        else:
            kitchen.t3.down.discard(PROJECT)

    kitchen.t3.on_list = every_thread_unanswered
    said = kitchen.poll(NOW + MIN)
    assert sent(kitchen) == []
    assert any("did not list its crew and scout threads" in line for line in said)
    kitchen.t3.on_list = None
    kitchen.t3.down.discard(PROJECT)
    kitchen.poll(NOW + 4 * MIN)
    assert sent(kitchen) == [(at, f"compact|scout|{at}|{stamp(0)}")]
