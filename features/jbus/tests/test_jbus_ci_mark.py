"""A pass of jbus lists the workflow runs created since its mark (`jbus.ci.collect.keep`): one
page once the pass before it kept every run, and every run of the pass's hours once
`collect.SWEEP` has gone by, which keeps a rerun's new attempt."""

from datetime import UTC, datetime, timedelta

import jsettings
from jbus.ci import collect, ledger
from jbus.ci.collect import Unavailable
from jsettings import store

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
        found = self.listed(path)
        self.read += max(1, -(-len(found) // collect.PAGE))
        return found

    def listed(self, path):
        since = jsettings.when(path.rsplit("&created=%3E%3D", 1)[1])
        return [one for one in self.runs if jsettings.when(one["created_at"]) >= since][::-1]

    def page(self, path, key=None):
        """A page of runs after the first, a page read, and of pull requests, none."""
        if "/actions/runs?" not in path:
            return []
        path, number = path.rsplit("&page=", 1)
        self.read += 1
        return self.listed(path)[(int(number) - 1) * collect.PAGE :][: collect.PAGE]

    def tagged(self, path, key=None, etag=""):
        return "", self.page(f"{path}&page=1", key)

    def annotations(self, jobs):
        return {}

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


class Asks(Window):
    """The window, counting every ask: a run in `empty` has no jobs, and an attempt in
    `cancelled` started none of its own, so GitHub lists only its run's earlier attempts' jobs."""

    def __init__(self, many, empty=(), cancelled=()):
        super().__init__(many)
        self.empty, self.cancelled = set(empty), set(cancelled)
        self.asked = []

    def pages(self, path, key=None):
        self.asked.append(path)
        found = super().pages(path, key)
        if "/actions/runs?" in path:
            return found
        run = next(one for one in self.runs if path.endswith(f"/runs/{one['id']}/jobs?filter=all"))
        if run["id"] in self.empty:
            return []
        if (run["id"], run["run_attempt"]) in self.cancelled:
            return [one | {"id": run["id"] * 10 + 1, "run_attempt": 1} for one in found]
        return found

    def page(self, path, key=None):
        self.asked.append(path.split("&page=")[0])
        return super().page(path, key)


def test_a_pass_with_nothing_new_asks_for_no_run_it_has_read(tmp_path):
    """A run that completed with no jobs, and a rerun's attempt that was cancelled before it
    started a job of its own, add no job to the ledger: the pass that read them does not read
    them again, while a run still going keeps the mark back over both."""
    gh = Asks(10, empty={4}, cancelled={(6, 2)})
    gh.runs[1]["status"] = "in_progress"
    gh.runs[5]["run_attempt"] = 2
    first = collect.keep(gh, REPO, tmp_path, NOW)
    assert first.jobs == 8
    gh.asked = []
    again = collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=1))
    assert again.jobs == 0
    assert sorted(path.split("?")[0].rsplit("/", 1)[1] for path in gh.asked) == ["pulls", "runs"]


def test_a_mark_whose_read_list_is_garbled_reads_the_runs_again(tmp_path):
    """An entry of the mark's `read` that is not `[run, attempt, created]` is dropped, and the
    pass reads that run's jobs as if no pass had."""
    gh = Asks(3, empty={2})
    gh.runs[0]["status"] = "in_progress"
    collect.keep(gh, REPO, tmp_path, NOW)
    mark = store.read_dict(tmp_path / collect.MARK)
    others = [one for one in mark["read"] if one[0] != 2]
    store.write_json(tmp_path / collect.MARK, mark | {"read": [[2, 1], *others]})
    gh.asked = []
    collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=1))
    assert [path for path in gh.asked if "/jobs" in path] == [
        f"repos/{REPO}/actions/runs/2/jobs?filter=all"
    ]
