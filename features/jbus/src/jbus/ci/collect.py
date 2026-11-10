"""Ask GitHub for a project's Actions jobs and pull requests, and keep them (`jbus.ci.ledger`).

Every call is a read through `gh api`. The collector reads the repo's workflow runs created since a
time and the pull requests updated since then. For each run that completed it reads the jobs the
ledger does not keep yet, with `filter=all` so that it gets every attempt of a rerun. For each
pull request whose update the ledger has not kept, it reads the timeline, where a force-push of its
branch is an event: one the ledger kept at the same update keeps its force-pushes. The pull
requests come a page at a time, the latest update first, and the collector stops at the first page
that reaches back past the time. The annotations of all the jobs it reads are one GraphQL ask
(`NOTES`), which spends none of the core allowance. For a red job, on a local or a hosted runner,
it keeps the step GitHub says failed, and reads the log once, for the failing tests the log names,
the make target that failed and the runner faults the log shows. Each of those reads waits for the
reads of the stage before it and for no other, so a pass's job lists and logs are read side by side
(`jbus.passes.side_by_side`). A red job kept before the collector kept the failed step has no
`step` field: a collect reads its run's jobs and its log again for each such job created since its
time and rewrites the ledger with what it read, and leaves one whose log GitHub did not give as it
was, for the next collect.

`jbus ci` collects the last `days` days (`collect`) and waits for the ledger's lock. Each pass of
jbus collects too (`keep`, from the step in `jbus.ci`): the runs created in the last `PASS_HOURS`
hours, at most `PASS_RUNS` new runs, so that a pass after a gap catches up over a few passes, and
the pull requests updated since the newest update the ledger holds, where that is earlier, back at
most `CATCH_UP`: a pass after a gap keeps every pull request merged in it. It never waits for the
lock: while `jbus ci` holds it, the pass collects nothing. A run that completes more than
`PASS_HOURS` after it was created is kept by the next `jbus ci`.

A pass lists only the runs created since its mark (`MARK`, beside the ledger's lock), where that
is within the `PASS_HOURS`: the creation time of the oldest run the last pass listed and did not
keep, because it had not completed or was past its `PASS_RUNS`, or of the newest run it listed
where it kept them all. So a pass after one that kept everything reads one page of runs, not
every page of the hours. A rerun keeps its run's creation time, so a run kept before the mark is
not listed again when it is rerun: a pass lists all the `PASS_HOURS` again once `SWEEP` has gone
by since the last pass that did, and keeps the rerun's attempt then.

The mark also keeps each run attempt whose jobs a pass read (`read`, each `[run, attempt,
created]`), for the `PASS_HOURS`, and a pass reads no attempt's jobs twice. A run that completed
with no jobs, or a rerun's attempt cancelled before it started a job of its own, adds no job to the
ledger, so without it every pass would read its jobs, and their annotations and logs, again.

The mark keeps the ETag of the runs page and of the first pull requests page a pass read (`tags`),
and the next pass asks each with it (`If-None-Match`): GitHub answers 304, which spends none of the
allowance, where the page has not changed, and the pass reads nothing more of it. A runs page
whose completed runs the pass did not all read keeps no ETag, so the next pass reads it again.

The collector reads a job's telemetry from its check run's annotations. Of a job's own words, the
API returns only its annotations, since the API cannot read a job summary. The telemetry is an
annotation titled `jstack-ci` whose message is a JSON object (`jbus.ci.notice` writes it).

`Gh` is the interface to GitHub: `Cli` asks GitHub through `gh`, by itself or through a pass's
own runner, and a test passes a `Gh` that replays a recording. An answer that is not JSON, or not
the shape the path gives, is `Unavailable`, as a GitHub that does not answer is.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import jsettings
from jbus import locked
from jbus.ci import ledger
from jbus.passes import side_by_side
from jsettings import budget as allowance
from jsettings import proc, store

TITLE = "jstack-ci"
PAGE = 100
PASS_HOURS = 3
PASS_RUNS = 30
CATCH_UP = timedelta(days=14)
SWEEP = timedelta(minutes=15)
MARK = "ci-mark.json"
HOSTED = re.compile(r"^(ubuntu|windows|macos)-")
EVIDENCE = re.compile(r"^(FAILED|ERROR|E  |##\[error\]|make(\[\d+\])?: \*\*\* )")
FAILING = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)")
TARGET = re.compile(r"^make(?:\[\d+\])?: \*\*\* \[(?:[^\]]*: )?([^\]:]+)\] Error")
SIGNS = {
    "bus": re.compile(
        r"(?i)failed to connect to (the |system |user )?bus|DBUS_SESSION_BUS_ADDRESS"
        r"|systemctl --user|systemd-analyze|No medium found|user bus|Failed t\.\.\."
    ),
    "browser": re.compile(
        r"(?i)(chromium|chrome)[^\n]{0,40}(not found|No such file)"
        r"|no (chromium|chrome|browser) (on|in|found)|could not find (chromium|chrome)"
        r"|browser did not finish"
    ),
    "space": re.compile(r"ENOSPC|No space left"),
}
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ")
ESCAPES = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class Unavailable(Exception):
    """GitHub did not answer."""


class Gh(Protocol):
    """A `Gh` asks GitHub. `pages` returns the list GitHub gives for a path over every page, and
    `page` the list of its one page. When each page is an object, the list is under `key` in it.
    `tagged` returns the ETag of a page with its list, or None where GitHub answered 304 to
    `etag`: the page has not changed since. `annotations` returns the annotations of each job's
    check run, by the job's id, for every job it can read them of."""

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]: ...

    def page(self, path: str, key: str | None = None) -> list[dict[str, Any]]: ...

    def tagged(
        self, path: str, key: str | None = None, etag: str = ""
    ) -> tuple[str, list[dict[str, Any]]] | None: ...

    def annotations(self, jobs: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]: ...

    def log(self, repo: str, job: int) -> str: ...


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    done = proc.run(*command, timeout=120)
    if isinstance(done, proc.Unrun):
        raise Unavailable(done.stderr[:200])
    return done


def _listed(page: Any, key: str | None) -> list[dict[str, Any]]:
    """The list of one page, under `key` where the page is an object."""
    found = (page.get(key) if isinstance(page, dict) else None) if key else page
    if not isinstance(found, list) or not all(isinstance(one, dict) for one in found):
        raise Unavailable("GitHub gave a page of another shape")
    return found


NOTES = (
    "query($ids: [ID!]!) { nodes(ids: $ids) { ... on CheckRun { databaseId"
    " annotations(first: 100) { nodes { title message } } } } }"
)
"""The annotations of check runs by their node ids, in one GraphQL call of up to `PAGE` ids. A
job's `node_id` is its check run's. GitHub keeps at most 50 annotations a job."""


class Cli:
    """Ask GitHub through `gh api`, one call at a time, and only read. `ask` runs the command:
    by itself, or as a pass of jbus runs it, in the project's checkout. A GraphQL call spends the
    GraphQL allowance, and a 304 spends none: neither spends the core allowance."""

    def __init__(self, ask: Callable[[list[str]], subprocess.CompletedProcess[str]] = _run):
        self.ask = ask

    def _said(self, *args: str) -> str:
        return self._given(self.ask(["gh", "api", *args]))

    def _given(self, asked: subprocess.CompletedProcess[str]) -> str:
        if asked.returncode and allowance.refused(asked.stderr):
            raise Unavailable(allowance.named(self.ask(allowance.ASK)))
        if asked.returncode:
            raise Unavailable(" ".join(asked.stderr.split())[:200] or f"gh exit {asked.returncode}")
        return asked.stdout

    def _json(self, *args: str) -> Any:
        try:
            return json.loads(self._said(*args))
        except ValueError as error:
            raise Unavailable("GitHub gave no JSON") from error

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        every = self._json(path, "--paginate", "--slurp")
        if not isinstance(every, list):
            raise Unavailable("GitHub gave no list of pages")
        return [one for page in every for one in _listed(page, key)]

    def page(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        return _listed(self._json(path), key)

    def tagged(
        self, path: str, key: str | None = None, etag: str = ""
    ) -> tuple[str, list[dict[str, Any]]] | None:
        tag = ("-H", f"If-None-Match: {etag}") if etag else ()
        asked = self.ask(["gh", "api", path, "-i", *tag])
        head, _, body = asked.stdout.replace("\r", "").partition("\n\n")
        status, *headers = head.splitlines() or [""]
        if status.split()[1:2] == ["304"]:
            return None
        self._given(asked)
        tags = [
            line.split(":", 1)[1].strip() for line in headers if line.lower().startswith("etag:")
        ]
        try:
            given = json.loads(body)
        except ValueError as error:
            raise Unavailable("GitHub gave no JSON") from error
        return (tags[0] if tags else ""), _listed(given, key)

    def annotations(self, jobs: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        """One GraphQL call for each `PAGE` jobs. GitHub answers a node it cannot read with null
        and an error, and gh then exits 1: the other nodes' annotations still count."""
        ids = [job["node_id"] for job in jobs if job.get("node_id")]
        given: dict[int, list[dict[str, Any]]] = {}
        for at in range(0, len(ids), PAGE):
            fields = [part for one in ids[at : at + PAGE] for part in ("-f", f"ids[]={one}")]
            asked = self.ask(["gh", "api", "graphql", "-f", f"query={NOTES}", *fields])
            try:
                nodes = json.loads(asked.stdout)["data"]["nodes"]
            except (ValueError, KeyError, TypeError):
                nodes = None
            if not isinstance(nodes, list):
                self._given(asked)
                raise Unavailable("GitHub gave no nodes")
            for node in nodes:
                if isinstance(node, dict) and isinstance(node.get("databaseId"), int):
                    found = (node.get("annotations") or {}).get("nodes")
                    given[node["databaseId"]] = _listed(found, None)
        return given

    def log(self, repo: str, job: int) -> str:
        return self._said(f"repos/{repo}/actions/jobs/{job}/logs", "--allow-escape-sequences")


@dataclass(frozen=True)
class Counts:
    runs: int
    jobs: int
    pulls: int


def kind(labels: list[str]) -> str:
    return "hosted" if any(HOSTED.match(one) for one in labels) else "local"


def evidence(log: str) -> list[str]:
    """Return the lines of a job's log that say what failed, with the stamp removed and each
    line cut short."""
    lines = (STAMP.sub("", ESCAPES.sub("", one)).strip() for one in log.splitlines())
    return [one[:200] for one in lines if EVIDENCE.match(one)]


def failing_tests(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        named = FAILING.match(line)
        if named and named[1] not in found:
            found.append(named[1])
    return found


def failed_step(job: dict[str, Any]) -> str | None:
    """Return the name of the first step of a job that GitHub says failed, or None."""
    for one in job.get("steps") or []:
        if isinstance(one, dict) and one.get("conclusion") == "failure":
            return one.get("name")
    return None


def step(name: str | None, lines: list[str]) -> str | None:
    """Return what failed: the step's name, with the make target that failed first where the
    log names one and the name does not end in it (`make check-fast: lint`)."""
    target = next((found[1] for one in lines if (found := TARGET.match(one))), None)
    if not (name and target) or name.split()[-1] == target:
        return name or target
    return f"{name}: {target}"


def signs(lines: list[str]) -> list[str]:
    return [name for name, rule in SIGNS.items() if any(rule.search(one) for one in lines)]


def _time(text: str | None) -> datetime | None:
    return jsettings.when(text) if text else None


def pull_for(run: dict[str, Any], job: dict[str, Any], pulls: list[dict[str, Any]]) -> int | None:
    """Return the pull request a job ran for: the one its run names, the one a push to main
    merged, or the one that was open on the run's branch when GitHub created the job."""
    named = run.get("pull_requests") or []
    if named:
        return int(named[0]["number"])
    branch, made = run.get("head_branch"), _time(job.get("created_at"))
    if run.get("event") == "push" and branch == "main":
        for one in pulls:
            if one.get("merge_commit") and one["merge_commit"] == run.get("head_sha"):
                return int(one["number"])
        return None
    for one in pulls:
        opened, ended = _time(one["created"]), _time(one["merged"] or one["closed"])
        if one["branch"] != branch or not made or not opened or opened > made:
            continue
        if ended is None or made <= ended + timedelta(minutes=5):
            return int(one["number"])
    return None


def notice(found: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the telemetry a job wrote, from its check run's annotations, or nothing where it
    wrote none."""
    given: dict[str, Any] = {}
    for one in found:
        if one.get("title") != TITLE:
            continue
        try:
            said = json.loads(one.get("message") or "")
        except ValueError:
            continue
        if isinstance(said, dict):
            given.update({k: v for k, v in said.items() if k in ledger.TELEMETRY})
    return given


def notes(gh: Gh, jobs: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """Return the annotations of each job that ran a step, read in one ask for them all, or none
    where GitHub did not answer: those jobs are kept with no telemetry."""
    stepped = [job for job in jobs if job.get("steps")]
    try:
        return gh.annotations(stepped) if stepped else {}
    except Unavailable:
        return {}


def row(
    gh: Gh,
    repo: str,
    run: dict[str, Any],
    job: dict[str, Any],
    pulls: list[dict[str, Any]],
    noted: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    labels = job.get("labels") or []
    steps = len(job.get("steps") or [])
    made: dict[str, Any] = {
        "run": run["id"],
        "job": job["id"],
        "attempt": job.get("run_attempt") or run.get("run_attempt") or 1,
        "name": job.get("name"),
        "sha": job.get("head_sha") or run.get("head_sha"),
        "branch": run.get("head_branch"),
        "pr": pull_for(run, job, pulls),
        "event": run.get("event"),
        "created": job.get("created_at"),
        "started": job.get("started_at") if steps else None,
        "completed": job.get("completed_at"),
        "conclusion": job.get("conclusion"),
        "runner": job.get("runner_name") or None,
        "kind": kind(labels),
        "steps": steps,
        "tests": [],
        "step": failed_step(job),
        "signs": [],
        "logged": False,
        **dict.fromkeys(ledger.TELEMETRY),
    }
    if steps:
        made.update(notice(noted.get(job["id"], [])))
    return read_log(gh, repo, made) if unlogged(made) else made


def unlogged(kept: dict[str, Any]) -> bool:
    """Whether a kept job is red, ran a step, and has not had its log read."""
    return kept["conclusion"] == "failure" and bool(kept.get("steps")) and not kept.get("logged")


def read_log(gh: Gh, repo: str, kept: dict[str, Any]) -> dict[str, Any]:
    """Return the kept job with the failing tests, the make target that failed and the runner
    faults of its log, `tests` None where GitHub did not give the log."""
    try:
        lines = evidence(gh.log(repo, kept["job"]))
    except Unavailable:
        return kept | {"tests": None, "signs": [], "logged": True}
    found = {"tests": failing_tests(lines), "step": step(kept["step"], lines)}
    return kept | found | {"signs": signs(lines), "logged": True}


def _pushes(gh: Gh, repo: str, number: int) -> list[str]:
    timeline = gh.pages(f"repos/{repo}/issues/{number}/timeline?per_page=100")
    return sorted(x["created_at"] for x in timeline if x.get("event") == "head_ref_force_pushed")


class Tags:
    """The ETags a pass asks its runs and pull requests pages with (`given`, the last pass's), and
    the ones it keeps for the next (`kept`), by path."""

    def __init__(self, given: Any = None) -> None:
        ok = isinstance(given, dict)
        self.given = {k: v for k, v in given.items() if isinstance(v, str)} if ok else {}
        self.kept: dict[str, str] = {}

    def page(self, gh: Gh, path: str, key: str | None = None) -> list[dict[str, Any]] | None:
        """The list of the one page of `path`, or None where it has not changed since the last
        pass kept its ETag."""
        answer = gh.tagged(path, key, self.given.get(path, ""))
        if answer is None:
            self.kept[path] = self.given[path]
            return None
        etag, found = answer
        if etag:
            self.kept[path] = etag
        return found


def pulls(
    gh: Gh,
    repo: str,
    since: datetime,
    held: dict[int, dict[str, Any]] | None = None,
    tags: Tags | None = None,
) -> list[dict[str, Any]]:
    """Return the pull requests updated since `since`, each with the times someone
    force-pushed its branch. A page at a time, the latest update first, up to the first page
    that reaches back past `since`. One that `held` keeps at the same update keeps its
    force-pushes, and its timeline is not read again. With `tags`, the first page is asked with
    the ETag the last pass kept, and where GitHub answers 304 no pull request was updated since
    that pass, which kept them all: there are none to return."""
    held = held or {}
    kept, number = [], 1
    while True:
        path = f"repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page={PAGE}"
        if tags is not None and number == 1:
            first = tags.page(gh, f"{path}&page=1")
            if first is None:
                return []
            found = first
        else:
            found = gh.page(f"{path}&page={number}")
        for one in found:
            stamp = one.get("updated_at")
            updated = _time(stamp or one.get("created_at"))
            if updated is not None and updated < since:
                continue
            was = held.get(one["number"], {})
            same = bool(stamp) and was.get("updated") == stamp
            kept.append(
                {
                    "number": one["number"],
                    "branch": one["head"]["ref"],
                    "head": one["head"]["sha"],
                    "created": one["created_at"],
                    "updated": stamp,
                    "merged": one.get("merged_at"),
                    "closed": one.get("closed_at"),
                    "merge_commit": one.get("merge_commit_sha") if one.get("merged_at") else None,
                    "pushes": was["pushes"] if same else _pushes(gh, repo, one["number"]),
                }
            )
        last = found[-1] if found else {}
        oldest = _time(last.get("updated_at") or last.get("created_at"))
        if len(found) < PAGE or (oldest is not None and oldest < since):
            return kept
        number += 1


def collect(gh: Gh, repo: str, state: Path, now: datetime, days: int) -> Counts:
    """Add to the ledger the jobs of the last `days` days that it does not have yet. Also keep
    the pull requests. It waits for another collector to end first."""
    with locked(state, ledger.LOCK):
        return _collect(gh, repo, state, now - timedelta(days=days))[0]


def keep(gh: Gh, repo: str, state: Path, now: datetime) -> Counts | None:
    """What a pass collects: the runs of the last `PASS_HOURS` hours created since the mark, all
    of those hours once `SWEEP` has gone by since a pass listed them, at most `PASS_RUNS` new
    ones, and the pull requests updated since then or since the newest update the ledger holds,
    whichever is earlier, back at most `CATCH_UP`. The mark is written once the jobs are kept.
    None where another collector holds the ledger, which the pass does not wait for."""
    try:
        with locked(state, ledger.LOCK, wait=False):
            since = now - timedelta(hours=PASS_HOURS)
            held = store.read_dict(state / MARK)
            mark, swept = _time(held.get("mark")), _time(held.get("swept"))
            sweep = swept is None or now - swept >= SWEEP
            start = since if sweep or mark is None else max(mark, since)
            read = _read(held.get("read"), since)
            tags = Tags(held.get("tags"))
            counts, mark, asked = _collect(
                gh, repo, state, since, PASS_RUNS, now - CATCH_UP, start, read, tags
            )
            swept = now if sweep else swept
            read = [[one, attempt, made] for (one, attempt), made in read.items()]
            store.write_json(
                state / MARK,
                {
                    "mark": _stamp(mark),
                    "swept": _stamp(swept),
                    "read": read + asked,
                    "tags": tags.kept,
                },
            )
            return counts
    except BlockingIOError:
        return None


def _read(given: Any, since: datetime) -> dict[tuple[int, int], str]:
    """The run attempts whose jobs the mark says a pass read, each with its run's creation time,
    of the runs created since `since`."""
    kept: dict[tuple[int, int], str] = {}
    for one in given if isinstance(given, list) else []:
        if not (isinstance(one, list) and len(one) == 3 and isinstance(one[2], str)):
            continue
        made = _time(one[2])
        if made is not None and made >= since:
            kept[(one[0], one[1])] = one[2]
    return kept


def _stamp(when: datetime | None) -> str | None:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if when else None


def _collect(
    gh: Gh,
    repo: str,
    state: Path,
    since: datetime,
    most: int | None = None,
    back: datetime | None = None,
    start: datetime | None = None,
    read: dict[tuple[int, int], str] | None = None,
    tags: Tags | None = None,
) -> tuple[Counts, datetime, list[list[Any]]]:
    """Keep the pull requests and the jobs of the runs created since `start`, or `since` where
    it is None, of at most `most` new runs, and return the mark: the creation time of the oldest
    run listed that was not kept, or of the newest where all were, or `start` where none was,
    and the run attempts whose jobs it read, each `[run, attempt, created]`. It reads no jobs of
    an attempt in `read`.
    With `back`, the pull requests are those updated since the newest update the ledger holds
    where that is earlier than `since`, and not before `back`. The pull requests' file is
    written only where one of them changed. The pull requests and the runs are read side
    by side, then the jobs of every new run, then the annotations of all their jobs in one ask,
    then each red job's log, and the jobs are written once all of them are read: a collector
    stopped half way keeps the pull requests, and the next one reads the jobs again.
    With `tags`, the runs and the pull requests are each asked a page with the ETag the last pass
    kept (`Tags`). A runs page GitHub answers 304 lists nothing new: its ETag is kept only where
    it was one page and the pass left none of its completed runs unread."""
    held = {one["number"]: one for one in ledger.read(state / ledger.PULLS)}
    updated = [when for one in held.values() if (when := _time(one.get("updated")))]
    caught = since if back is None or not updated else max(back, min(since, max(updated)))
    start = start or since
    path = f"repos/{repo}/actions/runs?per_page={PAGE}&created=%3E%3D{_stamp(start)}"
    found, runs = side_by_side(
        lambda ask: ask(),
        [lambda: pulls(gh, repo, caught, held, tags), lambda: _runs(gh, path, tags)],
    )
    now_held = held | {one["number"]: one for one in found}
    everyone = sorted(now_held.values(), key=lambda one: one["number"])
    if now_held != held:
        ledger.rewrite(state / ledger.PULLS, everyone)
    seen = {(one["run"], one["attempt"]) for one in ledger.read(state / ledger.JOBS)}
    seen |= set(read or {})
    unseen = [
        run
        for run in runs
        if run.get("status") == "completed" and (run["id"], run.get("run_attempt") or 1) not in seen
    ]
    new = unseen[:most]
    left = [run for run in runs if run.get("status") != "completed"] + unseen[len(new) :]
    made = [when for run in runs if (when := _time(run.get("created_at")))]
    unkept = [when for run in left if (when := _time(run.get("created_at")))]
    mark = min(unkept) if unkept else max(made, default=start)
    if tags is not None and (len(runs) >= PAGE or len(unseen) > len(new)):
        tags.kept.pop(path, None)
    listed = side_by_side(
        lambda run: gh.pages(f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=all", "jobs"), new
    )
    done = [
        (run, job)
        for run, jobs in zip(new, listed, strict=True)
        for job in jobs
        if job.get("status") == "completed"
    ]
    noted = notes(gh, [job for _, job in done])
    rows = side_by_side(lambda one: row(gh, repo, *one, everyone, noted), done)
    added = ledger.add(state / ledger.JOBS, rows)
    _reread(gh, repo, state, since)
    asked = [[run["id"], run.get("run_attempt") or 1, run.get("created_at")] for run in new]
    return Counts(len(runs), added, len(everyone)), mark, asked


def _runs(gh: Gh, path: str, tags: Tags | None) -> list[dict[str, Any]]:
    """The runs of `path`, over every page. With `tags`, the first page is asked with its ETag, an
    unchanged one is no runs, and the next pages one at a time while the last was full."""
    if tags is None:
        return gh.pages(path, "workflow_runs")
    last = tags.page(gh, path, "workflow_runs")
    if last is None:
        return []
    runs, number = list(last), 1
    while len(last) >= PAGE:
        number += 1
        last = gh.page(f"{path}&page={number}", "workflow_runs")
        runs += last
    return runs


def _steps(gh: Gh, repo: str, run: int) -> dict[int, str | None]:
    """Return the failed step of each job of a run, or none where GitHub did not answer."""
    try:
        jobs = gh.pages(f"repos/{repo}/actions/runs/{run}/jobs?filter=all", "jobs")
    except Unavailable:
        return {}
    return {job["id"]: failed_step(job) for job in jobs}


def _reread(gh: Gh, repo: str, state: Path, since: datetime) -> None:
    """Read again each red job created since `since` that was kept before the collector kept
    the step that failed (it has no `step` field): its run's jobs for the step, and its log for
    the failing tests and the make target. Rewrite the ledger with what was read. A run whose
    jobs or a log GitHub does not give now leaves its job as it was, for the next collect."""
    kept = ledger.read(state / ledger.JOBS)
    older = [
        at
        for at, one in enumerate(kept)
        if "step" not in one
        and one["conclusion"] == "failure"
        and one.get("steps")
        and (_time(one.get("created")) or since) >= since
    ]
    if not older:
        return
    runs = sorted({kept[at]["run"] for at in older})
    named = {
        job: name
        for found in side_by_side(lambda run: _steps(gh, repo, run), runs)
        for job, name in found.items()
    }
    older = [at for at in older if kept[at]["job"] in named]
    read = side_by_side(
        lambda at: read_log(gh, repo, kept[at] | {"step": named[kept[at]["job"]]}), older
    )
    given = [(at, one) for at, one in zip(older, read, strict=True) if one["tests"] is not None]
    if not given:
        return
    for at, one in given:
        kept[at] = one
    ledger.rewrite(state / ledger.JOBS, kept)
