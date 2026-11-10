"""`pr-checks-failed` reads the check runs on pull requests as jbus records them, `runs.jsonl` each
attempt of a run and `ci.jsonl` each job with the step it failed at, through a build of the store,
and `jbus scorecard --json` shows it: each run once, and a part for each class of failure."""

import contextlib
import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from jbus import cli, telemetry
from test_jbus_telemetry import Machine

NOW = datetime(2026, 11, 9, 21, 20, tzinfo=UTC)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


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


def attempt(machine, run: int, number: int, conclusion: str, sha: str = "", minutes: int = 0):
    """One attempt of a check run on a pull request, created `minutes` after the run's hour."""
    created = iso(NOW - timedelta(hours=2) + timedelta(minutes=run + minutes))
    machine.append(
        "alpha",
        "runs.jsonl",
        {
            "at": created,
            "run": run,
            "attempt": number,
            "workflow": "check",
            "sha": sha or f"sha{run}",
            "branch": f"b{run}",
            "event": "pull_request",
            "pr": run,
            "created": created,
            "started": created,
            "updated": created,
            "conclusion": conclusion,
        },
    )


def job(machine, run: int, number: int, name: str, step: str | None, conclusion="failure"):
    """One job of an attempt of a run, as `jbus.ci.collect.row` writes it to `ci.jsonl`."""
    created = iso(NOW - timedelta(hours=2) + timedelta(minutes=run))
    machine.append(
        "alpha",
        "ci.jsonl",
        {
            "run": run,
            "job": run * 100 + number * 10 + len(name),
            "attempt": number,
            "name": name,
            "sha": f"sha{run}",
            "branch": f"b{run}",
            "pr": run,
            "event": "pull_request",
            "created": created,
            "started": created,
            "completed": created,
            "conclusion": conclusion,
            "kind": "ubuntu",
            "steps": 12,
            "tests": [],
            "step": step,
            "signs": [],
        },
    )


def checks_failed(machine) -> dict:
    machine.build()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--project", "alpha", "scorecard", "--json"])
    assert code == 0, out.getvalue()
    return next(item for item in json.loads(out.getvalue()) if item["name"] == "pr-checks-failed")


def test_the_store_keeps_a_failed_jobs_step(machine):
    """A build keeps the step each failed job failed at and the attempt it was, and a store that
    held the jobs before `jbus.telemetry.migrations.v019_ci_jobs_step`, read to the end of
    `ci.jsonl`, has their steps after its next build, which reads the log again."""
    job(machine, 1, 2, "check 3 of 8", "make test")
    job(machine, 1, 2, "check", "every part passed")
    machine.build()
    with contextlib.closing(machine.store()) as store:
        store.executescript(
            "ALTER TABLE ci_jobs DROP COLUMN step;\n"
            "DELETE FROM migrations WHERE name = 'v019_ci_jobs_step';\n"
        )
    machine.build()
    with contextlib.closing(machine.store()) as store:
        kept = store.execute("SELECT name, attempt, step FROM ci_jobs ORDER BY name").fetchall()
    assert kept == [("check", 2, "every part passed"), ("check 3 of 8", 2, "make test")]


def test_a_rerun_of_one_run_counts_once(machine):
    """A run that failed three attempts is one failed run, and a run whose last attempt was
    cancelled is not counted: 1 of 2, not 3 of 5 attempts."""
    for number in (1, 2, 3):
        attempt(machine, 10, number, "failure")
        job(machine, 10, number, "check 1 of 8", "make test")
    attempt(machine, 11, 1, "success")
    attempt(machine, 12, 1, "cancelled")
    read = checks_failed(machine)
    assert (read["value"], read["n"]) == (50.0, 2)


def test_each_class_of_failure_is_a_part(machine):
    """Seven runs, five failed: a defect of the change; the trailer fetch's crash, which a rerun
    passed and is still the runner's; a test that failed and passed on a rerun; a test that failed
    and passed in a later run at the same head; and a run whose jobs the store does not have,
    which counts in the value and in no part."""
    attempt(machine, 1, 1, "failure")
    job(machine, 1, 1, "check 2 of 8", "make test")
    job(machine, 1, 1, "check", "every part passed")
    attempt(machine, 2, 1, "failure")
    job(machine, 2, 1, "reuse", "no AI co-author trailer")
    job(machine, 2, 1, "check", "every part passed")
    attempt(machine, 2, 2, "success")
    attempt(machine, 3, 1, "failure")
    job(machine, 3, 1, "check 5 of 8", "make check-fast: test")
    attempt(machine, 3, 2, "success")
    attempt(machine, 4, 1, "failure", sha="head")
    job(machine, 4, 1, "check 1 of 8", "make test")
    attempt(machine, 5, 1, "success", sha="head", minutes=5)
    attempt(machine, 6, 1, "failure")
    attempt(machine, 7, 1, "success")
    read = checks_failed(machine)
    assert (round(read["value"], 2), read["n"]) == (71.43, 7)
    parts = {part["label"]: round(part["value"], 2) for part in read["each"]}
    assert parts == {"own defect": 14.29, "runner fault": 14.29, "flake": 28.57}
