"""What a pass of jbus spends of GitHub's core allowance to keep the CI ledger
(`jbus.ci.collect.keep`), asked through `jbus.ci.collect.Cli` of a `gh` that answers as GitHub does:
the annotations of a pass's new jobs in one GraphQL ask, which spends none of it, and the runs and
pull requests pages with the ETag the last pass kept, which GitHub answers 304, spending none, where
neither changed."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta

import jsettings
from jbus.ci import collect, ledger

REPO = "JoshuaHayesWasHere/jstack"
NOW = datetime(2026, 11, 9, 22, 0, tzinfo=UTC)


def stamp(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


class GitHub:
    """`gh api` for a repo of `many` workflow runs over the pass's hours, each with two green jobs
    with steps that wrote their telemetry, and two pull requests. `asked` keeps each call, with
    whether it spent the core allowance: a GraphQL call and a 304 do not."""

    def __init__(self, many):
        span = timedelta(hours=collect.PASS_HOURS) / (many + 1)
        self.runs = [
            {
                "id": n + 1,
                "run_attempt": 1,
                "status": "completed",
                "event": "push",
                "head_branch": "main",
                "head_sha": "a" * 40,
                "created_at": stamp(NOW - span * (many - n)),
            }
            for n in range(many)
        ]
        self.pulls = [
            {
                "number": number,
                "head": {"ref": f"pie-{number}", "sha": "b" * 40},
                "created_at": stamp(NOW - timedelta(hours=1)),
                "updated_at": stamp(NOW - timedelta(minutes=30)),
            }
            for number in (7, 8)
        ]
        self.asked = []

    def jobs(self, run):
        return [
            {
                "id": run["id"] * 10 + n,
                "node_id": f"CR_{run['id'] * 10 + n}",
                "run_attempt": run["run_attempt"],
                "name": f"check {n}",
                "status": "completed",
                "conclusion": "success",
                "created_at": run["created_at"],
                "steps": [{"name": "make check", "conclusion": "success"}],
            }
            for n in (1, 2)
        ]

    def note(self, job):
        said = json.dumps({"selection": job, "full": False})
        return [{"title": collect.TITLE, "message": said}]

    def __call__(self, command):
        args = command[2:]
        path = args[0]
        if path == "graphql":
            ids = [one.split("=", 1)[1] for one in args if one.startswith("ids[]=")]
            nodes = [
                {"databaseId": int(one[3:]), "annotations": {"nodes": self.note(int(one[3:]))}}
                for one in ids
            ]
            self.asked.append((path, False))
            return subprocess.CompletedProcess(
                command, 0, json.dumps({"data": {"nodes": nodes}}), ""
            )
        if "/actions/runs?" in path:
            since = jsettings.when(path.rsplit("&created=%3E%3D", 1)[1])
            listed = [one for one in self.runs if jsettings.when(one["created_at"]) >= since]
            given = {"workflow_runs": listed[::-1][: collect.PAGE]}
        elif "/pulls?" in path:
            given = self.pulls if path.endswith("&page=1") else []
        elif "/jobs?filter=all" in path:
            run = next(one for one in self.runs if f"/runs/{one['id']}/jobs" in path)
            given = {"jobs": self.jobs(run)}
        elif "/timeline" in path:
            given = []
        elif "/annotations" in path:
            job = int(path.split("/check-runs/")[1].split("/")[0])
            given = self.note(job)
        else:
            raise AssertionError(path)
        said = json.dumps([given] if "--slurp" in args else given)
        if "-i" not in args:
            self.asked.append((path, True))
            return subprocess.CompletedProcess(command, 0, said, "")
        etag = f'W/"{hashlib.sha256(said.encode()).hexdigest()}"'
        if "-H" in args and args[args.index("-H") + 1] == f"If-None-Match: {etag}":
            self.asked.append((path, False))
            return subprocess.CompletedProcess(
                command, 1, "HTTP/2.0 304 Not Modified\r\n\r\n", "gh: HTTP 304"
            )
        self.asked.append((path, True))
        return subprocess.CompletedProcess(
            command, 0, f"HTTP/2.0 200 OK\r\nEtag: {etag}\r\n\r\n{said}", ""
        )

    def costed(self):
        return [path.split("?")[0].rsplit("/", 1)[1] for path, core in self.asked if core]


def test_a_pass_reads_the_annotations_of_all_its_new_jobs_in_one_ask_that_spends_no_core_call(
    tmp_path,
):
    github = GitHub(3)
    kept = collect.keep(collect.Cli(github), REPO, tmp_path, NOW)
    assert kept.jobs == 6
    assert sorted(github.costed()) == ["jobs", "jobs", "jobs", "pulls", "runs"] + ["timeline"] * 2
    assert [path for path, _ in github.asked].count("graphql") == 1
    rows = ledger.read(tmp_path / ledger.JOBS)
    assert {one["job"]: one["selection"] for one in rows} == {
        one["job"]: one["job"] for one in rows
    }


def test_a_pass_whose_pages_github_answers_304_asks_no_costed_call(tmp_path):
    """The first pass lists all the pass's hours and the second from its mark, so the third asks
    the same two pages as the second, with the ETags it kept, and nothing changed since."""
    github = GitHub(3)
    gh = collect.Cli(github)
    collect.keep(gh, REPO, tmp_path, NOW)
    collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=1))
    github.asked = []
    kept = collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=2))
    assert (kept.jobs, github.costed(), len(github.asked)) == (0, [], 2)
    assert len(ledger.read(tmp_path / ledger.PULLS)) == 2

    github.runs.append(github.runs[-1] | {"id": 4, "created_at": stamp(NOW + timedelta(minutes=2))})
    github.pulls[0]["updated_at"] = stamp(NOW + timedelta(minutes=2))
    kept = collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=3))
    assert kept.jobs == 2
    assert {one["updated"] for one in ledger.read(tmp_path / ledger.PULLS)} >= {
        stamp(NOW + timedelta(minutes=2))
    }


def test_a_page_the_pass_left_runs_of_is_asked_again_without_its_etag(tmp_path):
    """A run still going holds the mark at it, so pass after pass asks the same page: where a pass
    left completed runs past its `PASS_RUNS` unread, the next reads them though the page is the
    same, and does not take a 304 for nothing new."""
    many = collect.PASS_RUNS * 2 + 10
    github = GitHub(many + 1)
    github.runs[0]["status"] = "in_progress"
    gh = collect.Cli(github)
    for minute in range(3):
        collect.keep(gh, REPO, tmp_path, NOW + timedelta(minutes=minute))
    assert len(ledger.read(tmp_path / ledger.JOBS)) == many * 2


class Partly(GitHub):
    """GitHub's GraphQL cannot read the check runs in `lost`: it answers each with null and an
    error, and gh exits 1. With `down`, it answers no GraphQL call at all."""

    def __init__(self, many, lost=(), down=False):
        super().__init__(many)
        self.lost, self.down = set(lost), down

    def __call__(self, command):
        if command[2] != "graphql":
            return super().__call__(command)
        if self.down:
            return subprocess.CompletedProcess(command, 1, "", "gh: Bad Gateway (HTTP 502)")
        said = json.loads(super().__call__(command).stdout)
        nodes = said["data"]["nodes"]
        said["data"]["nodes"] = [None if one["databaseId"] in self.lost else one for one in nodes]
        return subprocess.CompletedProcess(command, 1, json.dumps(said), "gh: Could not resolve")


def test_a_job_whose_annotations_github_does_not_give_is_kept_with_no_telemetry(tmp_path):
    """A check run GitHub's GraphQL cannot read costs that job its telemetry and no other's, and
    a GraphQL that does not answer costs the pass its jobs' telemetry, never the jobs."""
    collect.keep(collect.Cli(Partly(2, lost={11})), REPO, tmp_path / "lost", NOW)
    rows = ledger.read(tmp_path / "lost" / ledger.JOBS)
    assert {one["job"]: one["selection"] for one in rows} == {11: None, 12: 12, 21: 21, 22: 22}

    collect.keep(collect.Cli(Partly(2, down=True)), REPO, tmp_path / "down", NOW)
    rows = ledger.read(tmp_path / "down" / ledger.JOBS)
    assert {one["job"]: one["selection"] for one in rows} == dict.fromkeys((11, 12, 21, 22))
