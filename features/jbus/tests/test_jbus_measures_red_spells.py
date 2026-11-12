"""`main-pushes-red` and `red-spells-per-merge` read main's push checks over the same last 72 h, as
`jbus scorecard` shows them: a red main holds no merge, so one long spell is many red pushes and
one spell, and the two reads tell a worse merge rate from one long spell."""

import contextlib
import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from jbus import cli, telemetry
from test_jbus_telemetry import Machine, job, merged_rows

NOW = datetime(2026, 11, 11, 23, 0, tzinfo=UTC)

PUSHES = ("green", *["red"] * 5, "green", "red", "green", "red", "green")
"""Main's pushes in the window, oldest first: one spell of five red pushes and two of one."""


@pytest.fixture
def machine(tmp_path, monkeypatch):
    made = Machine(tmp_path, monkeypatch)
    settings = tmp_path / "x" / "jstack" / "config.toml"
    settings.parent.mkdir(parents=True)
    settings.write_text('timezone = "America/New_York"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(settings.parent.parent))

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)

    monkeypatch.setattr(telemetry, "datetime", Frozen)
    return made


def scorecard(machine) -> dict[str, dict]:
    machine.build()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--project", "alpha", "scorecard", "--json"])
    assert code == 0, out.getvalue()
    return {item["name"]: item for item in json.loads(out.getvalue())}


def test_one_long_spell_is_five_red_pushes_and_one_spell(machine):
    """Eleven merges, each pushed to main, of which seven were red in three spells; a red push
    and its merge four days before, outside the 72 h, count in neither."""
    old = NOW - timedelta(days=4)
    start = NOW - timedelta(hours=6)
    jobs = [job(1, "c1", 1, "failure", old), job(2, "c2", 2, "success", old + timedelta(hours=1))]
    rows = [("row-1", 1, old), ("row-2", 2, old + timedelta(hours=1))]
    for place, state in enumerate(PUSHES, start=3):
        at = start + timedelta(minutes=10 * place)
        conclusion = "failure" if state == "red" else "success"
        jobs.append(job(place, f"c{place}", place, conclusion, at))
        rows.append((f"row-{place}", place, at - timedelta(minutes=1)))
    machine.append("alpha", "ci.jsonl", *jobs)
    merged_rows(machine, "alpha", rows)

    read = scorecard(machine)

    pushes, spells = read["main-pushes-red"], read["red-spells-per-merge"]
    assert (pushes["value"], pushes["n"]) == (pytest.approx(100 * 7 / 11), 11)
    assert pushes["note"] == "7 red pushes in 3 spells"
    assert (spells["value"], spells["n"]) == (pytest.approx(3 / 11), 11)
    assert spells["note"] == "3 spells over 11 merges; 7 red pushes"
