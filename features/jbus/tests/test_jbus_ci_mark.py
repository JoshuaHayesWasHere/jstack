"""A pass of jbus lists the workflow runs created since its mark (`jbus.ci.collect.keep`): one
page once the pass before it kept every run, and every run of the pass's hours once
`collect.SWEEP` has gone by, which keeps a rerun's new attempt."""

from datetime import UTC, datetime, timedelta

import jsettings
from jbus.ci import collect, ledger
from jbus.ci.collect import Unavailable

REPO = "JoshuaHayesWasHere/jstack"
NOW = datetime(2026, 10, 17, 22, 15, tzinfo=UTC)


class Window:
    """GitHub's workflow runs, `many` over the pass's hours before `NOW`, each with one green
    job: the list honours its `created` filter and counts each page of `collect.PAGE` it reads."""

    def __init__(self, many):
        span = timedelta(hours=collect.PASS_HOURS) / many
        self.runs = [
            {
                "id": n + 1,
                "run_attempt": 1,
                "status": "completed",
                "event": "push",
                "head_branch": "main",
                "created_at": (NOW - span * (many - n)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            for n in range(many)
        ]
        self.read = 0

    def pages(self, path, key=None):
        if "/actions/runs?" not in path:
            return [
                {
                    "id": run["id"] * 10 + run["run_attempt"],
                    "run_attempt": run["run_attempt"],
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": run["created_at"],
                }
                for run in self.runs
                if path.endswith(f"/runs/{run['id']}/jobs?filter=all")
            ]
        since = jsettings.when(path.rsplit("&created=%3E%3D", 1)[1])
        found = [one for one in self.runs if jsettings.when(one["created_at"]) >= since]
        self.read += max(1, -(-len(found) // collect.PAGE))
        return found[::-1]

    def page(self, path, key=None):
        return []

    def log(self, repo, job):
        raise Unavailable(str(job))


def test_a_pass_after_one_that_kept_every_run_lists_one_page_and_a_run_still_going_is_listed(
    tmp_path,
):
    """A pass lists the runs since the oldest the pass before it did not keep: one page once
    every run is kept, all the hours where one is still going, and each pass until it ends."""
    gh = Window(290)
    going = gh.runs[96]
    going["status"] = "in_progress"
    ledger.rewrite(
        tmp_path / ledger.JOBS,
        [
            {"run": one["id"], "attempt": 1, "job": one["id"] * 10 + 1, "conclusion": "success"}
            for one in gh.runs
            if one is not going
        ],
    )
    kept = collect.keep(gh, REPO, tmp_path, NOW)
    assert (gh.read, kept.runs, kept.jobs) == (3, 290, 0)

    gh.read = 0
    kept = collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=1))
    assert (gh.read, kept.runs, kept.jobs) == (2, 194, 0)

    going["status"] = "completed"
    gh.read = 0
    kept = collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=2))
    assert (gh.read, kept.jobs) == (2, 1)

    gh.read = 0
    kept = collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=3))
    assert (gh.read, kept.runs, kept.jobs) == (1, 1, 0)


def test_a_rerun_of_a_run_kept_before_the_mark_is_kept_by_the_next_pass_that_lists_all_the_hours(
    tmp_path,
):
    """A rerun keeps its run's creation time, so the pass that lists all the pass's hours again
    once `collect.SWEEP` has gone by keeps its new attempt."""
    gh = Window(20)
    assert collect.keep(gh, REPO, tmp_path, NOW).jobs == 20
    gh.runs[10]["run_attempt"] = 2
    gh.read = 0
    soon = NOW + collect.SWEEP - timedelta(minutes=1)
    assert (collect.keep(gh, REPO, tmp_path, soon).jobs, gh.read) == (0, 1)
    assert collect.keep(gh, REPO, tmp_path, NOW + collect.SWEEP).jobs == 1
    assert {(one["run"], one["attempt"]) for one in ledger.read(tmp_path / ledger.JOBS)} >= {
        (11, 1),
        (11, 2),
    }
