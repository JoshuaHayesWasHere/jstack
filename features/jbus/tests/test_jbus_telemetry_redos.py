"""The store joins a merged row to the later row that redoes it (`redos`, `redo_rows`): a follow-up
or a main-red fix whose go names it, a `main-red-<sha12>` fix of the row whose merge commit that
red tip is, and a revert jbus opened of it (`reverts.json`), each within 7 days of its merge, and
the redo rate counts a row redone twice once, of the rows whose 7 days are over."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from test_jbus_telemetry import NOW, SECRET, Machine, dump, iso

OLD = NOW - timedelta(days=14)
"""A merge long enough ago that its 7 days ended before any build."""


@pytest.fixture
def machine(tmp_path, monkeypatch):
    return Machine(tmp_path, monkeypatch)


def merged(machine, project, rows):
    """`merged.json` and `ci-prs.jsonl` for merged rows of (slug, number, merged time, commit)."""
    machine.write(
        project,
        "merged.json",
        {
            slug: {
                "number": number,
                "mergedAt": iso(at),
                "title": SECRET,
                "mergeCommit": {"oid": commit},
                "state": "MERGED",
            }
            for slug, number, at, commit in rows
        },
    )


def queued(project_rows, slug, follows=None, ran_at=None, basis="rule"):
    """A row of `queue.json`, its go by the follow-up rule of `follows` or by the user's word."""
    approval = {"basis": basis, "words": SECRET, "meaning": [[SECRET]]}
    if ran_at is not None:
        approval["ran_at"] = iso(ran_at)
    if follows:
        approval["follows"] = follows
    project_rows.append({"slug": slug, "status": "queued", "approval": approval, "why": SECRET})


def redone(machine):
    with contextlib.closing(machine.store()) as store:
        return store.execute(
            "SELECT slug, judged, redone_by, how FROM redo_rows ORDER BY slug"
        ).fetchall()


def test_a_follow_up_queued_after_its_parent_merged_redoes_it_and_none_before_or_late_does(
    machine,
):
    merged(
        machine,
        "alpha",
        [
            ("fixed", 1, OLD, "a" * 40),
            ("planned", 2, OLD, "b" * 40),
            ("late", 3, OLD, "c" * 40),
        ],
    )
    rows = [{"slug": slug} for slug in ("fixed", "planned", "late")]
    queued(rows, "fix-it", follows="fixed", ran_at=OLD + timedelta(hours=3))
    queued(rows, "next-unit", follows="planned", ran_at=OLD - timedelta(hours=1))
    queued(rows, "much-later", follows="late", ran_at=OLD + timedelta(days=8))
    machine.write("alpha", "queue.json", rows)
    machine.build()

    assert redone(machine) == [
        ("fixed", 1, "fix-it", "follow-up"),
        ("late", 1, None, None),
        ("planned", 1, None, None),
    ]


def test_a_main_red_fix_joins_the_row_its_go_names_or_else_the_row_whose_merge_its_slug_names(
    machine,
):
    merged(
        machine,
        "alpha",
        [
            ("named", 1, OLD, "1" * 40),
            ("at-the-tip", 2, OLD, "abcdef012345" + "9" * 28),
            ("other", 3, OLD, "2" * 40),
        ],
    )
    rows = [{"slug": slug} for slug in ("named", "at-the-tip", "other")]
    queued(rows, f"main-red-{'2' * 12}", follows="named", ran_at=OLD + timedelta(minutes=20))
    queued(rows, "main-red-abcdef012345", ran_at=OLD + timedelta(minutes=30), basis="word")
    queued(rows, "main-red-wake-split", ran_at=OLD + timedelta(minutes=30), basis="word")
    machine.write("alpha", "queue.json", rows)
    machine.build()

    assert redone(machine) == [
        ("at-the-tip", 1, "main-red-abcdef012345", "main-red"),
        ("named", 1, f"main-red-{'2' * 12}", "main-red"),
        ("other", 1, None, None),
    ]


def test_a_revert_jbus_opened_redoes_its_culprit_with_or_without_its_pull_request_kept(machine):
    merged(
        machine,
        "alpha",
        [("culprit", 1, OLD, "d" * 40), ("unkept", 2, OLD, "e" * 40), ("green", 3, OLD, "f" * 40)],
    )
    machine.write("alpha", "queue.json", [{"slug": s} for s in ("culprit", "unkept", "green")])
    machine.write(
        "alpha",
        "reverts.json",
        {
            "d" * 40: {
                "slug": "culprit",
                "branch": "revert-1-culprit",
                "head": "0" * 40,
                "pull": "https://example.test/pull/7",
            },
            "e" * 40: {
                "slug": "unkept",
                "branch": "revert-2-unkept",
                "head": "0" * 40,
                "pull": "https://example.test/pull/8",
            },
        },
    )
    (machine.state("alpha") / "ci-prs.jsonl").write_text(
        json.dumps({"number": 7, "branch": "revert-1-culprit", "created": iso(OLD), "pushes": []})
        + "\n"
    )
    machine.build()

    assert redone(machine) == [
        ("culprit", 1, "revert-1-culprit", "revert"),
        ("green", 1, None, None),
        ("unkept", 1, "revert-2-unkept", "revert"),
    ]
    with contextlib.closing(machine.store()) as store:
        assert store.execute(
            "SELECT redoer, how, slug, at FROM redos ORDER BY redoer"
        ).fetchall() == [
            ("revert-1-culprit", "revert", "culprit", OLD.strftime("%Y-%m-%dT%H:%M:%S.%fZ")),
            ("revert-2-unkept", "revert", "unkept", None),
        ]


def test_a_row_redone_twice_counts_once_and_a_row_too_new_to_judge_waits(machine):
    fresh = datetime.now(UTC) - timedelta(days=2)
    merged(
        machine,
        "alpha",
        [
            ("twice", 1, OLD, "a" * 40),
            ("clean", 2, OLD + timedelta(hours=1), "b" * 40),
            ("new", 3, fresh, "c" * 40),
        ],
    )
    rows = [{"slug": slug} for slug in ("twice", "clean", "new")]
    queued(rows, f"main-red-{'a' * 12}", follows="twice", ran_at=OLD + timedelta(minutes=30))
    queued(rows, "new-fix", follows="new", ran_at=fresh + timedelta(hours=1))
    machine.write("alpha", "queue.json", rows)
    machine.write(
        "alpha",
        "reverts.json",
        {"a" * 40: {"slug": "twice", "branch": "revert-1-twice", "head": "0", "pull": "#9"}},
    )
    machine.build()

    assert redone(machine) == [
        ("clean", 1, None, None),
        ("new", 0, "new-fix", "follow-up"),
        ("twice", 1, f"main-red-{'a' * 12}", "main-red"),
    ]
    with contextlib.closing(machine.store()) as store:
        weeks = store.execute(
            "SELECT week, redone, judged, waiting, rate FROM weekly_redo ORDER BY week"
        ).fetchall()
    assert weeks[0] == ("2026-10-18", 1, 2, 0, 50.0)
    assert weeks[-1][1:] == (0, 0, 1, None)


def test_the_redo_records_read_on_from_the_last_build_equal_a_store_built_from_nothing(machine):
    merged(machine, "alpha", [("one", 1, OLD, "a" * 40)])
    rows = [{"slug": "one"}]
    machine.write("alpha", "queue.json", rows)
    machine.build()
    queued(rows, "fix-one", follows="one", ran_at=OLD + timedelta(hours=1))
    machine.write("alpha", "queue.json", rows)
    machine.write(
        "alpha",
        "reverts.json",
        {"a" * 40: {"slug": "one", "branch": "revert-1-one", "head": "0", "pull": "#2"}},
    )
    machine.build()

    code, out = machine.run("--rebuild", str(machine.root / "again.sqlite"))
    assert code == 0, out
    tables = ("queue", "reverts")
    built, again = dump(machine.state_dir / "telemetry.sqlite"), dump(machine.root / "again.sqlite")
    assert {t: built[t] for t in tables} == {t: again[t] for t in tables}
    assert redone(machine) == [("one", 1, "fix-one", "follow-up")]
    assert SECRET.encode() not in (machine.state_dir / "telemetry.sqlite").read_bytes()
