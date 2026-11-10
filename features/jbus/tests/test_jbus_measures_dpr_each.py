"""dollars-per-row shows where a row's dollars go: a part for each role, which sum to the value,
and a part for each class of what woke a crew's runs, from what the store keeps of each run's
trigger (`jbus.spent`, `jgauge.spend.day_lines`).
"""

from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import spent, telemetry
from jbus.telemetry import measures, migrations
from jgauge import spend as jgauge_spend
from test_jbus_scorecard import NOW, USER, calls, measure, queued, stamp
from test_jbus_telemetry import counted, machine
from test_spend import Store

__all__ = ["machine"]


def sent(key: str) -> str:
    """The message id jbus gives a send under `key` (`jgauge.spend.trigger`)."""
    return f"mcp:thread-send:{key}|alpha|0123456789ab"


def test_the_store_keeps_what_woke_each_run(machine, tmp_path):
    """A crew's day: its first run, which no send woke, the prereview's send, a failed check, and
    a word of the user's after them, and on the next day a slot wake. The pass that keeps the
    spend keeps a line for each trigger, and says which runs came after the row's first prereview
    that day, so the telemetry store holds what woke each run."""
    t3 = Store(tmp_path / "statev2.sqlite")
    for hour, message in ((12, ""), (13, sent("prereviewed")), (14, sent("failed")), (15, "")):
        t3.run("crew: alpha", f"2026-10-10T{hour}:00:00Z", project="alpha-id", message=message)
    t3.run("crew: alpha", "2026-10-11T13:00:00Z", project="alpha-id", message=sent("slot-wake"))
    t3.close()

    spent.keep(jbus.load(), datetime(2026, 10, 12, 18, 0, tzinfo=UTC), t3.path)
    machine.build()

    with machine.store() as store:
        kept = store.execute(
            "SELECT spent_on, trigger, reviewed, runs, dollars > 0 FROM spend_rows "
            "WHERE project = 'alpha' AND slug = 'alpha' ORDER BY spent_on, trigger, reviewed"
        ).fetchall()
    assert kept == [
        ("2026-10-10", "", 0, 1, 1),
        ("2026-10-10", "", 1, 1, 1),
        ("2026-10-10", "failed", 1, 1, 1),
        ("2026-10-10", "prereviewed", 0, 1, 1),
        ("2026-10-11", "slot-wake", 0, 1, 1),
    ]


def test_a_line_kept_before_the_trigger_reads_as_unknown(machine):
    """A store built before `jbus.telemetry.migrations.v020_spend_trigger` gains the trigger, the
    `reviewed` flag and the dollars on its next build, and a line `jbus.spent` kept before them
    holds none of the three, where a line kept since holds a trigger, "" for a run no send woke."""
    counted(
        machine.state_dir / telemetry.FILE, list(migrations.MIGRATIONS).index("v020_spend_trigger")
    )
    line = {"day": "2026-10-10", "at": "2026-10-11T12:00:00Z", "role": "crew", "slug": "alpha"}
    machine.append(
        "alpha",
        spent.ROWS,
        line | {"units": 5, "runs": 1},
        line | {"units": 7, "runs": 2, "trigger": "", "reviewed": False, "dollars": 1.25},
    )
    machine.build()
    with machine.store() as store:
        kept = store.execute(
            "SELECT runs, trigger, reviewed, dollars FROM spend_rows ORDER BY runs"
        ).fetchall()
    assert kept == [(1, None, None, None), (2, "", 0, 1.25)]


@pytest.fixture
def store(tmp_path):
    connection = telemetry.connect(tmp_path / telemetry.FILE)
    yield connection
    connection.close()


def crew_line(store, day: str, woke: str | None, reviewed: int | None, dollars: float) -> None:
    store.execute(
        "INSERT INTO spend_rows (project, key, at, spent_on, role, slug, trigger, reviewed,"
        " dollars, day) VALUES ('jstack', ?, ?, ?, 'crew', 'row-a', ?, ?, ?, ?)",
        (f"{day}/{woke}/{reviewed}", f"{day}T23:00:00.000000Z", day, woke, reviewed, dollars, day),
    )


def test_the_parts_of_a_row_sum_to_its_dollars(store):
    """The week's one merged row spent on its crew, its reviewer, the home that queued it and its
    scout. Each role is a part, in dollars a row, and the roles sum to the value. The crew's
    dollars split by what woke each run: its build before the first prereview, the fix the
    prereview woke, a failed check and a slot wake after it, and a run no send woke on a later
    day, which is other; each class is its share of the crew's spend times the crew's part."""
    monday = datetime(2026, 11, 9, tzinfo=UTC)
    calls(
        store, "jstack", "home", "jstack", "h1", "mcp:home", (monday + timedelta(hours=12), 1_000)
    )
    queued(store, "row-a", "scout-x", monday + timedelta(hours=13))
    calls(store, "jstack", "scout", "scout-x", "s1", "mcp:s1", (monday + timedelta(hours=5), 2_000))
    calls(store, "jstack", "crew", "row-a", "c1", "mcp:c1", (monday + timedelta(hours=14), 60_000))
    calls(
        store, "jstack", "reviewer", "row-a", "r1", "mcp:r1", (monday + timedelta(hours=15), 7_000)
    )
    store.execute(
        "INSERT INTO transitions (project, key, at, slug, from_status, to_status, day)"
        " VALUES ('jstack', 't1', ?, 'row-a', 'pr', 'merged', '2026-11-09')",
        (stamp(monday + timedelta(hours=18)),),
    )
    crew_line(store, "2026-11-08", "", 0, 3.0)
    crew_line(store, "2026-11-08", "prereviewed", 0, 1.0)
    crew_line(store, "2026-11-08", "failed", 1, 0.5)
    crew_line(store, "2026-11-08", "slot-wake", 1, 0.5)
    crew_line(store, "2026-11-09", "", 0, 1.0)

    reading = measures.read(store, measure("dollars-per-row"), "jstack", NOW, USER)

    opus = jgauge_spend.PRICES["claude-opus-5-5"].plain / 1e6
    parts = {part.label: part.value for part in reading.each}
    roles = {"crew": 60_000, "reviewer": 7_000, "home": 1_000, "scout": 2_000}
    assert {label: parts[label] for label in roles} == {
        label: pytest.approx(tokens * opus) for label, tokens in roles.items()
    }
    assert sum(parts[label] for label in roles) == pytest.approx(reading.value)
    crew = parts["crew"]
    assert {label: value for label, value in parts.items() if label.startswith("crew: ")} == {
        "crew: build": pytest.approx(crew * 3 / 6),
        "crew: prereview fix": pytest.approx(crew * 1 / 6),
        "crew: failed check": pytest.approx(crew * 0.5 / 6),
        "crew: wake": pytest.approx(crew * 0.5 / 6),
        "crew: other": pytest.approx(crew * 1 / 6),
    }
