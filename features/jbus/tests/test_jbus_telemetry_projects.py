"""Each `weekly_*` view of the telemetry store gives a row per project and week, so a week of
one project counts no other's.

The test writes two projects' records as jbus writes them, builds the store with the real
`jbus telemetry`, builds a second store from one project's records alone, and reads both with
`sqlite3` as any reader would. It reads every `jbus.telemetry.views.weekly_*` module's view, among
them `jbus.telemetry.views.weekly_merges`, whose counts it asserts, and
`jbus.telemetry.views.weekly_needs_asks`."""

import contextlib
import sqlite3
from datetime import timedelta

import pytest

from jbus import telemetry
from test_jbus_telemetry import NOW, Machine, records, snapshots


@pytest.fixture
def machine(tmp_path, monkeypatch):
    return Machine(tmp_path, monkeypatch)


WEEKLY = sorted(name for name, _ in telemetry.views.VIEWS if name.startswith("weekly_"))


def test_each_weekly_view_gives_a_project_only_its_own_rows(machine, tmp_path):
    """Two projects merge rows in one week: each weekly view's rows for `alpha` are those of a
    store built from `alpha`'s records alone, so a week of one project counts no other's."""
    records(machine, "alpha", NOW, "alpha-one", 10)
    records(machine, "alpha", NOW + timedelta(hours=2), "alpha-two", 12)
    snapshots(
        machine,
        "alpha",
        [
            ("alpha-one", 10, NOW + timedelta(hours=1)),
            ("alpha-two", 12, NOW + timedelta(hours=5)),
        ],
    )
    records(machine, "beta", NOW, "beta-one", 11)
    snapshots(machine, "beta", [("beta-one", 11, NOW + timedelta(hours=9))])
    machine.build()
    for kept in (machine.state_dir, machine.home_dir):
        (kept / "beta").rename(tmp_path / f"beta-{kept.name}")
        (kept / "beta").mkdir()
    alone = tmp_path / "alpha-alone.sqlite"
    code, out = machine.run("--rebuild", str(alone))
    assert code == 0, out

    def of_alpha(path, view):
        with contextlib.closing(sqlite3.connect(path)) as store:
            names = [
                name for (name,) in store.execute(f"SELECT name FROM pragma_table_info('{view}')")
            ]
            assert "project" in names, f"{view} has no project column: {names}"
            return sorted(
                store.execute(f"SELECT * FROM {view} WHERE project = 'alpha'").fetchall(), key=repr
            )

    both = machine.state_dir / telemetry.FILE
    assert {view: of_alpha(both, view) for view in WEEKLY} == {
        view: of_alpha(alone, view) for view in WEEKLY
    }
    with contextlib.closing(sqlite3.connect(both)) as store:
        merged = store.execute(
            "SELECT project, week, merged FROM weekly_merges ORDER BY 1"
        ).fetchall()
    assert merged == [("alpha", "2026-10-25", 2), ("beta", "2026-10-25", 1)]
