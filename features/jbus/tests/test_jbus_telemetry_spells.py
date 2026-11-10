"""The red spells of main's push checks and the change failure rate (S6) the store gives of them,
over the records of `ci.jsonl`, `merged.json` and `queue.json` as jbus writes them, and over
`main-reds.jsonl`, why main went red, as the real `jbus.mainmoved.tell` writes it and
`jbus.telemetry.records.main_reds` reads it into the table that
`jbus.telemetry.migrations.v018_main_reds` makes."""

import contextlib
import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from jbus import mainmoved
from jmerge import mainjson
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


GREEN, TESTED, LINTED = "a" * 40, "b" * 40, "c" * 40
LOGS = {
    101: "FAILED features/m/tests/test_m.py::test_one - assert 1 == 2\n"
    "===== 1 failed, 9 passed in 1.0s =====\nmake: *** [Makefile:85: test] Error 1\n",
    102: "make: *** [Makefile:40: lint] Error 1\n",
}
STEPS = {101: "make test", 102: "make lint"}


@dataclass
class Asked:
    stdout: str
    returncode: int = 0


@dataclass
class GitHub:
    """A pass as `tell` reads it, over GitHub's answers: main went from GREEN to TESTED, whose
    check failed a test, to LINTED, whose check failed the lint. TESTED's pull request is in
    `merged.json`; LINTED's only in its commit's subject."""

    state: Path
    now: Any = NOW
    answers: dict[str, Any] = field(default_factory=dict)
    world: Any = None

    def tip(self) -> str:
        return LINTED

    def run(self, *command: str) -> Asked:
        path = command[2] if command[:2] == ("gh", "api") else ""
        commits = [
            {"sha": LINTED, "parents": [{"sha": TESTED}], "commit": {"message": "fix: x (#12)"}},
            {"sha": TESTED, "parents": [{"sha": GREEN}], "commit": {"message": "feat: y"}},
            {"sha": GREEN, "parents": [], "commit": {"message": "z"}},
        ]
        part = {TESTED: (101, "check 1 of 8"), LINTED: (102, "lint")}
        if "/commits?sha=" in path:
            at = path.split("sha=")[1].split("&")[0]
            return Asked(json.dumps(commits[[c["sha"] for c in commits].index(at) :]))
        if "/actions/runs?head_sha=" in path:
            runs = [{"event": "push", "head_branch": "main", "check_suite_id": 1}]
            return Asked(json.dumps({"workflow_runs": runs}))
        if path.endswith("/check-runs"):
            number, name = part[path.split("/commits/")[1].split("/")[0]]
            run = {"id": number, "name": name, "status": "completed", "conclusion": "failure"}
            return Asked(json.dumps({"check_runs": [{**run, "check_suite": {"id": 1}}]}))
        if path.endswith("/logs"):
            return Asked(LOGS[int(path.split("/")[-2])])
        if "/actions/jobs/" in path:
            number = int(path.split("/")[-1])
            return Asked(json.dumps({"steps": [{"name": STEPS[number], "conclusion": "failure"}]}))
        if command[:2] == ("git", "symbolic-ref"):
            return Asked("origin/main\n")
        return Asked("", 1)


def test_tell_writes_why_main_went_red_once_and_the_store_reads_it_as_the_spells_cause(
    machine, monkeypatch
):
    state = machine.state("alpha")
    record = mainjson.record(main=GREEN, at=iso(NOW), check="green", broken="", green=GREEN)
    (state / mainjson.NAME).write_text(json.dumps(record))
    pull = {"number": 11, "headRefName": "row-11", "mergeCommit": {"oid": TESTED}}
    (state / "merged.json").write_text(json.dumps({"row-11": pull}))
    said = {GREEN: "green", TESTED: "failed", LINTED: "failed"}
    monkeypatch.setattr(mainmoved, "main_check", lambda run, at, **_: said[at])
    for _ in range(2):
        mainmoved.tell(GitHub(state))
    lines = [json.loads(line) for line in (state / mainmoved.REDS).read_text().splitlines()]
    assert [{k: v for k, v in line.items() if k != "at"} for line in lines] == [
        {
            "sha": TESTED,
            "prs": [11],
            "step": "make test",
            "failed": ["features/m/tests/test_m.py::test_one"],
            "verdict": "change",
        },
        {"sha": LINTED, "prs": [11, 12], "step": "make lint", "failed": [], "verdict": "change"},
    ]
    machine.append(
        "alpha",
        "ci.jsonl",
        job(1, GREEN, 10, "success", NOW),
        job(2, TESTED, 11, "failure", NOW + timedelta(minutes=10)),
    )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        spells = store.execute("SELECT start_pr, cause FROM main_spells").fetchall()
    assert spells == [(11, "change")]
