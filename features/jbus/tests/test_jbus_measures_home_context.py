"""The two reads of a home's context: `home-context`, the mean a home's own call sent over the
last 72 h, and `home-context-peak`, the most one sent, each on the calls of the home's session
and none of its subagents'."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import jsettings
from jbus import telemetry
from jbus.telemetry import measures, values

NOW = datetime(2026, 11, 10, 15, tzinfo=UTC)
USER = jsettings.Settings(zone=ZoneInfo("America/New_York"))


@pytest.fixture
def store(tmp_path):
    connection = telemetry.connect(tmp_path / telemetry.FILE)
    yield connection
    connection.close()


def measure(name: str) -> measures.Measure:
    return next(each for each in measures.MEASURES if each.name == name)


def calls(store, project: str, role: str, session: str, *made, agent: str | None = None) -> None:
    """A session of `role` and its calls, each `(hours ago, tokens of context)` split over the
    three counts of context; `agent` names a subagent of the session whose calls they are."""
    store.execute(
        "insert or ignore into sessions (provider, session, thread, project, role, slug)"
        " values ('claude', ?, ?, ?, ?, ?)",
        (session, f"mcp:{session}", project, role, project),
    )
    for hours, tokens in made:
        at = NOW - timedelta(hours=hours)
        store.execute(
            "insert into calls (provider, call, session, agent, at, model, input, cache_write,"
            " cache_read, output, final, day) values ('claude', ?, ?, ?, ?, 'claude-opus-5-5',"
            " ?, ?, ?, 0, 1, ?)",
            (
                f"{session}.{agent}.{hours}",
                session,
                agent,
                at.strftime(values.STAMP),
                tokens // 10,
                tokens // 10,
                tokens - 2 * (tokens // 10),
                at.date().isoformat(),
            ),
        )


@pytest.fixture
def homes(store):
    """Two home calls in the last 72 h, one of 80 h ago, a subagent of a home, a crew session and
    another project's home. The week began on Sunday 2026-11-08, so the call of 80 h ago is
    before it and the one of 60 h ago is not in the week but is in the 72 h."""
    calls(store, "jstack", "home", "h1", (2, 100_000), (60, 300_000), (80, 900_000))
    calls(store, "jstack", "home", "h1", (1, 700_000), agent="agent-a1")
    calls(store, "jstack", "crew", "c1", (3, 800_000))
    calls(store, "elsewhere", "home", "e1", (4, 600_000))
    return store


def test_home_context_reads_a_homes_own_calls_of_the_last_72_hours(homes):
    context = measure("home-context")
    reading = measures.read(homes, context, "jstack", NOW, USER)
    assert (reading.value, reading.n) == (200, 2)
    assert (context.window, context.baseline) == ("72h", 182)


def test_the_peak_is_the_largest_call_a_home_sent(homes):
    peak = measure("home-context-peak")
    reading = measures.read(homes, peak, "jstack", NOW, USER)
    assert (reading.value, reading.n, reading.state) == (300, 2, "bad")
    calls(homes, "jstack", "home", "h2", (5, 900_000), agent="agent-a2")
    assert measures.read(homes, peak, "jstack", NOW, USER).value == 300
    assert peak.kind == measures.Limit(200, 1)


def test_a_peak_under_its_line_is_ok(store):
    calls(store, "jstack", "home", "h1", (2, 150_000), (3, 120_000))
    reading = measures.read(store, measure("home-context-peak"), "jstack", NOW, USER)
    assert (reading.value, reading.n, reading.state) == (150, 2, "ok")
