"""The red spells of main's push checks and the change failure rate (S6) the store gives of them,
over the records of `ci.jsonl`, `merged.json` and `queue.json` as jbus writes them."""

import contextlib
from datetime import timedelta

from test_jbus_telemetry import NOW, iso, job, machine, merged_rows

__all__ = ["machine"]


def test_spells_restore_and_change_failure_follow_the_push_checks_on_main(machine):
    at = NOW
    machine.append(
        "alpha",
        "ci.jsonl",
        job(1, "c1", 1, "success", at),
        job(2, "c2", 2, "failure", at + timedelta(minutes=10)),
        job(3, "c3", 3, "failure", at + timedelta(minutes=20)),
        job(4, "c4", 4, "failure", at + timedelta(minutes=30)),
        job(4, "c4", 4, "success", at + timedelta(minutes=40), attempt=2),
        job(5, "c5", 5, "failure", at + timedelta(minutes=50)),
        job(5, "c5", 5, "cancelled", at + timedelta(minutes=50), name="full"),
    )
    merged = {
        f"row-{n}": {"number": n, "mergedAt": iso(at + timedelta(minutes=10 * n - 11))}
        for n in range(1, 6)
    }
    machine.write("alpha", "merged.json", merged)
    machine.write("alpha", "queue.json", [{"slug": slug} for slug in merged])
    machine.build()
    with contextlib.closing(machine.store()) as store:
        spells = store.execute(
            "SELECT start_pr, end_sha, minutes_to_green FROM main_spells ORDER BY first_fail_at"
        ).fetchall()
        restore = store.execute(
            "SELECT week, spells, median, most, still_open FROM weekly_restore"
        ).fetchall()
        failure = store.execute(
            "SELECT week, failures, merged FROM weekly_change_failure"
        ).fetchall()
    assert spells == [(2, "c4", 30.0), (5, None, None)]
    assert restore == [("2026-10-25", 2, 30.0, 30.0, 1)]
    assert failure == [("2026-10-25", 2, 5)]


def test_main_checks_reads_the_check_run_over_a_green_macos_run_at_the_same_sha(machine):
    machine.append(
        "alpha",
        "ci.jsonl",
        job(1, "c1", 1, "failure", NOW),
        job(2, "c1", 1, "success", NOW, name="macos"),
    )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        checks = store.execute("SELECT sha, state FROM main_checks").fetchall()
    assert checks == [("c1", "red")]


def test_main_spells_never_end_before_they_open_on_a_quick_green_macos_run(machine):
    quick = {
        **job(3, "c2", 2, "success", NOW + timedelta(minutes=1), name="macos"),
        "completed": iso(NOW + timedelta(minutes=2)),
    }
    machine.append(
        "alpha",
        "ci.jsonl",
        job(1, "c1", 1, "failure", NOW),
        job(2, "c2", 2, "failure", NOW + timedelta(minutes=1)),
        quick,
        job(4, "c3", 3, "success", NOW + timedelta(minutes=20)),
    )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        spells = store.execute(
            "SELECT start_pr, end_sha, minutes_to_green FROM main_spells"
        ).fetchall()
    assert spells == [(1, "c3", 20.0)]


def test_a_merged_row_with_no_push_check_kept_is_a_gap_the_rate_leaves_out(machine):
    gap = NOW - timedelta(days=2)
    machine.append("alpha", "ci.jsonl", job(1, "c1", 1, "success", NOW))
    merged_rows(machine, "alpha", [("a-1", 1, NOW), ("a-0", 9, gap)])
    machine.build()
    with contextlib.closing(machine.store()) as store:
        failure = store.execute(
            "SELECT week, failures, merged FROM weekly_change_failure"
        ).fetchall()
        assert failure == [("2026-10-25", 0, 1)]
        gaps = store.execute("SELECT project, day, week FROM ci_gaps").fetchall()
        assert gaps == [("alpha", "2026-10-26", "2026-10-25")]
