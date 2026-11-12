"""A required run GitHub queued at an open row's head and started no job of is restarted once
for the head (`jbus.cancelled.unqueue`): cancelled where it has not ended, and run again.

The replays are 2026-11-11's. #1695's head got check and borders runs at 20:19:23Z that GitHub
kept `queued` with no jobs for over two hours, so the roll-up listed no check of it. #1691's check
run ended `failure` while its `check` job sat `queued` from 20:29:53Z. No part of jbus acted on
either. Like `test_jbus_github.py`, the tests run the real pass against the fakes."""

from datetime import UTC, datetime

import pytest

from test_jbus_kitchen import Kitchen
from test_jbus_queue import add

DAY = datetime(2026, 11, 11, tzinfo=UTC)
STUCK = "912dad95" + "a" * 32
"""#1695's head, whose runs GitHub queued at 20:19:23Z and started no job of."""
FAILED = "de3d3d27" + "b" * 32
"""#1691's head, whose check run failed with its `check` job queued since 20:29:53Z."""


def at(clock):
    hour, minute, second = (int(part) for part in f"{clock}:00".split(":")[:3])
    return DAY.replace(hour=hour, minute=minute, second=second)


def iso(clock):
    return at(clock).isoformat().replace("+00:00", "Z")


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    """Alpha is a row a first pass launched at 20:00Z, whose thread's turn has ended; its home
    requires check and borders."""
    made = Kitchen(tmp_path, monkeypatch)
    add(made, "alpha")
    assert "launched alpha: mcp:thread-1" in made.poll(at("20:00"))
    for thread in made.t3.threads:
        thread["status"] = "completed"
    (made.home / "required-checks").write_text("check\nborders\n")
    yield made
    made.close()


def opened(kitchen, number, head, rollup):
    made = {**kitchen.opened("alpha", number), "headRefOid": head, "statusCheckRollup": rollup}
    kitchen.set("open.json", [made])


def run(number, name, head, status="queued", conclusion=None, since="20:19:23", attempt=1):
    """A workflow run at `head` as GitHub's REST answer gives it."""
    return {
        "id": number,
        "name": name,
        "head_sha": head,
        "event": "pull_request",
        "status": status,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "created_at": iso("20:19:23"),
        "run_started_at": iso(since),
    }


def job(name, status="completed", conclusion="success", since="20:21:00"):
    return {"name": name, "status": status, "conclusion": conclusion, "created_at": iso(since)}


def no_jobs(kitchen, attempt=1, since="20:19:23"):
    """#1695: its check and borders runs queued since 20:19:23Z, with no jobs."""
    opened(kitchen, 1695, STUCK, [])
    runs = [
        run(101, "check", STUCK, attempt=attempt, since=since),
        run(102, "borders", STUCK, attempt=attempt, since=since),
    ]
    kitchen.set("push-runs.json", {STUCK: runs})
    kitchen.set("run-jobs.json", {"101": [], "102": []})


def check_job_queued(kitchen):
    """#1691: its check run ended `failure`, and the run's `check` job is queued since
    20:29:53Z; its borders passed."""
    url = "https://example.test/o/r/actions/runs/{}/job/{}"
    opened(
        kitchen,
        1691,
        FAILED,
        [
            {
                "name": "check",
                "workflowName": "check",
                "status": "QUEUED",
                "startedAt": iso("20:29:53"),
                "detailsUrl": url.format(43093673718, 9),
            },
            {
                "name": "borders",
                "workflowName": "borders",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "detailsUrl": url.format(43093673719, 10),
            },
        ],
    )
    runs = [
        run(43093673718, "check", FAILED, "completed", "failure", since="20:21:00"),
        run(43093673719, "borders", FAILED, "completed", "success", since="20:21:00"),
    ]
    kitchen.set("push-runs.json", {FAILED: runs})
    shards = [job(f"check {n} of 8") for n in range(1, 9)]
    kitchen.set(
        "run-jobs.json",
        {"43093673718": [*shards, job("check", "queued", None, "20:29:53")]},
    )


def acts(kitchen):
    """The cancels and reruns jbus asked GitHub for."""
    return [line for line in kitchen.log("gh") if line.startswith(("run cancel", "run rerun"))]


def passes(kitchen, *clocks):
    for clock in clocks:
        kitchen.poll(at(clock))


def test_runs_queued_with_no_jobs_are_cancelled_and_run_again_once_at_30_minutes(kitchen):
    """#1695: the roll-up lists no check, so the head's runs are read from GitHub's runs."""
    no_jobs(kitchen)
    passes(kitchen, "20:48:30")
    assert acts(kitchen) == []
    passes(kitchen, "20:49:30")
    assert acts(kitchen) == [
        "run cancel 101",
        "run rerun 101",
        "run cancel 102",
        "run rerun 102",
    ]
    passes(kitchen, "20:52", "20:55")
    assert len(acts(kitchen)) == 4
    assert kitchen.lines("queued") == [
        "queued alpha: GitHub queued #1695's check and borders runs at 912dad95aaaa 30 minutes "
        "ago and started no job: cancelled them and ran them again"
    ]


def test_a_check_job_queued_in_a_run_that_ended_is_run_again_once_at_30_minutes(kitchen):
    """#1691: the run ended, so it is not cancelled, only run again."""
    check_job_queued(kitchen)
    passes(kitchen, "20:59:30")
    assert acts(kitchen) == []
    passes(kitchen, "21:00")
    assert acts(kitchen) == ["run rerun 43093673718"]
    passes(kitchen, "21:03", "21:06")
    assert acts(kitchen) == ["run rerun 43093673718"]
    assert kitchen.lines("queued") == [
        "queued alpha: GitHub queued #1691's check run at de3d3d27bbbb 30 minutes ago and "
        "started no job: ran it again"
    ]


def test_a_second_stuck_run_on_the_same_head_is_logged_once_and_not_restarted(kitchen):
    """The restart is spent for the head: what GitHub queues again there waits for the home."""
    no_jobs(kitchen)
    passes(kitchen, "20:49:30")
    no_jobs(kitchen, attempt=2, since="20:49:40")
    passes(kitchen, "21:20", "21:23", "21:26")
    assert len(acts(kitchen)) == 4
    assert kitchen.lines("queued")[1:] == [
        "queued alpha: GitHub queued #1695's check and borders runs at 912dad95aaaa again after "
        "jbus ran them again, and started no job in 30 minutes: jbus restarts no run twice at a "
        "head"
    ]


def test_a_rerun_github_refuses_while_the_cancel_ends_is_asked_again_and_the_cancel_not(
    kitchen,
):
    """GitHub ends a cancel after it answers, and refuses to run again a run it has not ended."""
    no_jobs(kitchen)
    kitchen.set("gh-no-rerun", "")
    passes(kitchen, "20:49:30")
    assert acts(kitchen) == ["run cancel 101", "run rerun 101", "run cancel 102", "run rerun 102"]
    assert kitchen.lines("queued") == []
    (kitchen.stub / "gh-no-rerun").unlink()
    cancelled = [
        run(101, "check", STUCK, "completed", "cancelled"),
        run(102, "borders", STUCK, "completed", "cancelled"),
    ]
    kitchen.set("push-runs.json", {STUCK: cancelled})
    passes(kitchen, "20:50:30", "20:53")
    assert acts(kitchen)[4:] == ["run rerun 101", "run rerun 102"]
    assert len(kitchen.lines("queued")) == 1


def test_a_rerun_github_refuses_for_ten_minutes_is_given_up_and_logged_once(kitchen):
    no_jobs(kitchen)
    kitchen.set("gh-no-rerun", "")
    passes(kitchen, "20:49:30", "20:55", "21:00", "21:03")
    assert [line for line in acts(kitchen) if line.startswith("run rerun")] == [
        "run rerun 101",
        "run rerun 102",
    ] * 2
    assert kitchen.lines("queued") == [
        "queued alpha: GitHub queued #1695's check and borders runs at 912dad95aaaa 30 minutes "
        "ago and started no job, and did not run them again in 10 minutes of tries: run cannot "
        "be rerun"
    ]


def test_a_pull_request_of_no_row_is_left_alone(kitchen):
    """Only an open row's pull request is restarted: one of no row is not jbus's."""
    no_jobs(kitchen)
    made = {**kitchen.opened("beta", 1695), "headRefOid": STUCK, "statusCheckRollup": []}
    kitchen.set("open.json", [made])
    passes(kitchen, "20:49:30")
    assert acts(kitchen) == [] and kitchen.lines("queued") == []
