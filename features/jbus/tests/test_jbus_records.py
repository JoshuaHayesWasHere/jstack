"""jbus keeps an append-only record of what its snapshots overwrite (`jbus.history`,
`jbus.spent`): each version of a brief, each pull request of a row, each attempt of a workflow run
of every project, and one line of spend a day.

Each test drives the writer as jbus does, through a queue verb, a pass of the kitchen or the
pass's chore, and reads the log it leaves. Each log only grows: a later write leaves every byte
before it as it was, and a write run again adds nothing twice. The pass asks GitHub nothing more
for them: it keeps runs from the answer it already asked for.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import history, queue, spent
from jmerge import judgement
from test_jbus_github import launched
from test_jbus_kitchen import NOW, Kitchen, iso
from test_jbus_queue import add, brief, widened
from test_jbus_queue_remove import remove
from test_spend import Store

__all__ = ["launched"]


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class Grows:
    """A log that is only appended to: each read checks the bytes read before are still its
    start."""

    def __init__(self, path):
        self.path, self.before = path, b""

    def read(self):
        now = self.path.read_bytes() if self.path.exists() else b""
        assert now.startswith(self.before), f"{self.path.name} was rewritten, not appended to"
        self.before = now
        return [json.loads(line) for line in now.decode().splitlines()]


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def test_each_version_of_a_brief_is_kept_once_with_its_text_beside_the_log(kitchen):
    log = Grows(kitchen.state / history.BRIEFS)
    add(kitchen, "alpha", approve=False)
    add(kitchen, "alpha", approve=False)
    first = log.read()
    add(kitchen, "alpha", approve=False, text=widened("alpha"))
    add(kitchen, "alpha", approve=False, text=widened("alpha"))
    found = log.read()

    one, two = judgement.brief_sha(brief("alpha")), judgement.brief_sha(widened("alpha"))
    assert [(line["slug"], line["was"], line["sha"]) for line in found] == [
        ("alpha", "", one),
        ("alpha", one, two),
    ]
    assert found[: len(first)] == first
    assert found[1]["bytes"] == len(widened("alpha").encode())
    kept = kitchen.state / history.KEPT
    assert (kept / f"{one}.md").read_text() == brief("alpha")
    assert (kept / f"{two}.md").read_text() == widened("alpha")


def test_a_removed_brief_is_a_version_with_no_sha_and_its_text_stays_kept(kitchen):
    log = Grows(kitchen.state / history.BRIEFS)
    add(kitchen, "alpha", approve=False)
    kitchen.monkeypatch.setattr(queue, "clock", lambda: NOW)
    code, said = remove(kitchen, "alpha")
    assert code == 0, said
    one = judgement.brief_sha(brief("alpha"))
    assert [(line["was"], line["sha"]) for line in log.read()] == [("", one), (one, "")]
    assert (kitchen.state / history.KEPT / f"{one}.md").exists()


def test_every_pull_request_a_row_has_is_kept_open_and_merged_once_each(launched):
    log = Grows(launched.state / history.PULLS)
    launched.set("open.json", [launched.opened("alpha", 7)])
    launched.poll(NOW)
    launched.poll(NOW + timedelta(minutes=1))
    assert [(one["slug"], one["number"], one["state"]) for one in log.read()] == [
        ("alpha", 7, "open")
    ]

    launched.set("open.json", [launched.opened("alpha", 8)])
    launched.poll(NOW + timedelta(minutes=2))
    launched.set("open.json", [])
    launched.set("merged.json", [launched.merged("alpha", 8, "e" * 40)])
    launched.poll(NOW + timedelta(minutes=3))
    launched.poll(NOW + timedelta(minutes=4))

    found = log.read()
    assert [(one["slug"], one["number"], one["state"]) for one in found] == [
        ("alpha", 7, "open"),
        ("alpha", 8, "open"),
        ("alpha", 8, "merged"),
    ]
    assert found[-1]["merged_at"] == iso(NOW - timedelta(minutes=10))


def workflow_run(number, attempt, conclusion, status="completed", sha="c" * 40):
    return {
        "id": number,
        "run_attempt": attempt,
        "name": "check",
        "head_sha": sha,
        "head_branch": "alpha",
        "event": "pull_request",
        "pull_requests": [{"number": 7}],
        "status": status,
        "conclusion": conclusion,
        "created_at": iso(NOW - timedelta(minutes=20)),
        "run_started_at": iso(NOW - timedelta(minutes=19 - attempt)),
        "updated_at": iso(NOW - timedelta(minutes=10 - attempt)),
        "html_url": f"https://example.test/o/r/actions/runs/{number}",
    }


def asked_for_runs(kitchen):
    return [line for line in kitchen.log("gh") if "/actions/runs?per_page=" in line]


def test_every_attempt_of_a_run_is_kept_from_the_list_the_pass_already_asks_for(launched):
    other = launched.second()
    launched.config()
    log, theirs = Grows(launched.state / history.RUNS), Grows(other.state / history.RUNS)
    launched.set(
        "runs.json",
        {"workflow_runs": [workflow_run(501, 1, "failure"), workflow_run(502, 1, None, "queued")]},
    )
    asked = len(asked_for_runs(launched))
    launched.poll(NOW)
    per_pass = len(asked_for_runs(launched)) - asked
    launched.poll(NOW + timedelta(minutes=1))
    launched.set(
        "runs.json",
        {"workflow_runs": [workflow_run(501, 2, "success"), workflow_run(502, 1, "success")]},
    )
    launched.poll(NOW + timedelta(minutes=2))
    launched.poll(NOW + timedelta(minutes=3))

    found = log.read()
    assert [(one["run"], one["attempt"], one["conclusion"]) for one in found] == [
        (501, 1, "failure"),
        (502, 1, "success"),
        (501, 2, "success"),
    ]
    assert found[0] | {"at": None} == {
        "at": None,
        "run": 501,
        "attempt": 1,
        "workflow": "check",
        "sha": "c" * 40,
        "branch": "alpha",
        "event": "pull_request",
        "pr": 7,
        "created": iso(NOW - timedelta(minutes=20)),
        "started": iso(NOW - timedelta(minutes=18)),
        "updated": iso(NOW - timedelta(minutes=9)),
        "conclusion": "failure",
    }
    assert [(one["run"], one["attempt"]) for one in theirs.read()] == [(501, 1), (502, 1), (501, 2)]
    assert per_pass == len(jbus.load().projects)
    assert len(asked_for_runs(launched)) - asked == 4 * per_pass


@pytest.fixture
def t3(tmp_path):
    made = Store(tmp_path / "statev2.sqlite")
    yield made
    made.db.close()


def test_one_line_of_spend_a_day_is_kept_once_the_day_has_settled(kitchen, t3):
    """The kitchen's user is in New York: 12:00Z is 08:00 that day, and 11:00Z is 07:00."""
    project = jbus.load().projects[0]
    t3.run("crew: alpha", "2026-10-10T12:00:00Z", project=project.project_id)
    t3.run("review: alpha", "2026-10-10T13:00:00Z", project=project.project_id)
    t3.run("my own words", "2026-10-10T14:00:00Z", project=project.project_id, ordinal=2)
    t3.run("crew: elsewhere", "2026-10-10T12:00:00Z", project="another-project")
    t3.run("crew: beta", "2026-10-11T23:30:00Z", project=project.project_id)
    t3.close()
    days, rows = Grows(kitchen.state / spent.FILE), Grows(kitchen.state / spent.ROWS)
    config = jbus.load()

    assert spent.keep(config, datetime(2026, 10, 12, 11, 0, tzinfo=UTC), t3.path) == 30
    first = days.read()
    assert [one["day"] for one in first][-2:] == ["2026-10-10", "2026-10-11"]
    assert len(first) == 30
    ten = [one for one in first if one["day"] == "2026-10-10"][0]
    assert (ten["runs"], ten["units"]) == (3, round(3 * 2_800_000))
    assert (ten["first"], ten["reviews"], ten["sends"]) == (2_800_000, 2_800_000, 2_800_000)
    assert [(one["role"], one["slug"], one["runs"]) for one in rows.read()] == [
        ("crew", "alpha", 1),
        ("other", "", 1),
        ("review", "alpha", 1),
        ("crew", "beta", 1),
    ]

    assert spent.keep(config, datetime(2026, 10, 12, 12, 0, tzinfo=UTC), t3.path) == 0
    assert spent.keep(config, datetime(2026, 10, 13, 11, 0, tzinfo=UTC), t3.path) == 1
    assert [one["day"] for one in days.read()][-1] == "2026-10-12"
    assert "my own words" not in (kitchen.state / spent.ROWS).read_text()


def test_with_no_store_of_t3_code_no_spend_is_kept(kitchen, tmp_path):
    assert spent.keep(jbus.load(), NOW, tmp_path / "none.sqlite") == 0
    assert not (kitchen.state / spent.FILE).exists()
