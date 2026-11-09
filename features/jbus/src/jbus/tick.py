"""`jbus tick`: restate a pull request's line, and run `jmerge`, within seconds of a check's job
ending, apart from the pass.

A green pull request merges on the first run of `jmerge` after its last check ended, and the pass
runs it once a pass, which starts 10 s after the last one ended. `jbus-merge.timer` runs a tick
every 10 seconds while the last pass saw a row's pull request open or a check going, and the pass
stops it while it saw neither (`_timer`). A tick asks GitHub nothing unless the last pass saw an
open pull request that a row's line names, or another whose checks were still going (`PENDING`,
written by the pass's
step `tick.pending`). It asks GitHub for the check runs at the head of every such pull request at
once, at most `proc.GH_CAP` at a time, so one more pending pull request adds no wait to the
others' reads. It asks for each head as it is now, by the pull request's ref and not by the sha
the pass saw, which are the jobs of its workflow runs (`CHECK_RUNS`), with the ETag it kept
(`SEEN`). GitHub answers 304, which spends none
of the API allowance, until a job at that head changes or a push moves the head. So a head pushed
after the pass's read reaches the next tick at no call of its own, and a head a newer push
superseded is no longer read. A check suite the tick has not seen yet costs one read of the head's
workflow runs (`RUNS_AT`), for the workflow each job belongs to.

On a 200 the tick restates, from that answer and as soon as it lands, not after the project's
other reads, the line of `work.json` of the pull request on the check step (`_verdict`,
`jbus.restated.checked`): failed, with the reason `jmerge` gives a failed check, as soon as any
job of a required check's workflow run failed, such as one shard of eight while the other seven
still run; or passed, for `jmerge` to judge next, once the required check's
own job passed. A required job GitHub does not list yet, as `check` while the shards it needs
run, is still going. It does so before it runs `jmerge`, and also where `jmerge` is busy and does
not run, so the line changes in the milliseconds after GitHub lists the job, not after the whole
workflow run ends. `jmerge` reads a check as failed only once the check's own job ends, so its
verdict that the check is still going does not undo the tick's `failed` at that head
(`restated.stands`). Where a head's verdict is new, the tick then runs `jmerge --if-free`
(`jbus.merge.tick`), whose verdicts restate each pull request's line again
(`jbus.restated.pulled`), and log each one that says otherwise than the tick as drift. The tick
bounds only its own part: it sees a job that GitHub lists as ended within 10 seconds. The
end-to-end delay is what `features/jbus/tests/checks_bound_probe.py` measures live. GitHub tells
no one of a job that ended sooner without a webhook, which jbus does not have.

A round costs the counted calls of its 200s: at most one a tick for each head, and at most one
for each change of a job's status at it (queued, in progress, completed), whichever is fewer,
plus one read of the workflow runs a check suite, and `jmerge`'s own once a verdict is new
(`docs/jbus/the-units.md`). Every other tick answers 304.

The tick keeps a head's ETag with the verdict read under it at once, and the verdict `jmerge` ran
for only once `jmerge` ran to its end, so a tick that dies, a `jmerge` that was busy with the
pass's own run, or one that failed leaves the verdict to the next tick's `jmerge`, and the tick
restates nothing twice. While a run of `jmerge` it started is going, which a merge's guards
make a minute or more (`jmerge.treeguards`), the tick reads on every 10 seconds in its own
process (`tick`), since the timer starts no tick until it ends. The pass runs
`jmerge --if-free` each pass too, so what the tick misses the next pass with the run lock free
does. A merge of the tick's that changed a skill is kept for the next pass's `reload.tell`
before the ETag is (`reload.keep`), since `jmerge` prints its `merged` line once. One run of
`jmerge` runs at a time, by its run lock (`jmerge.lock`). A tick asks GitHub whatever the API
budget says (`jbus.budget`): a 304 spends none of it, and what a job that ended costs is
`jmerge`'s, which the floor is kept for.
"""

from __future__ import annotations

import json
import os
import time
from concurrent import futures
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jbus
from jbus import cancelled, launchd, merge, passes, reload, restated, verbs, watch
from jmerge import ready
from jsettings import proc, store

if TYPE_CHECKING:
    from jbus.poll import Half

PENDING = restated.PENDING
SEEN = "tick.json"
"""What the tick read of each pending pull request (`pulls`, by its number): the ETag of the
check runs at its head (`etag`), the head they named (`head`), the workflow run of each of the
head's check suites (`suites`, each `[name, run id]`), the verdict read under that ETag
(`verdict`), and the verdict `jmerge` last ran to its end for at that head (`ran`). Only the
tick writes it."""
CHECK_RUNS = "repos/{owner}/{repo}/commits/pull/%s/head/check-runs?per_page=100"
"""The check runs at a pull request's head as it is now, the latest of each name, which are the
jobs of its workflow runs. Each names the head it ran at (`head_sha`)."""
RUNS_AT = "repos/{owner}/{repo}/actions/runs?head_sha=%s&per_page=100"
"""A head's workflow runs, asked for only when its check runs name a check suite the tick does
not know the workflow of yet."""
OK = "200"
EVERY = 10
"""The seconds between the tick's reads while a run of `jmerge` it started is still going, the
interval of `jbus-merge.timer`, which starts no tick while one runs."""
TIMER = "JBUS_TICK_TIMER"
"""The variable that names the timer the pass runs the tick by, `jbus-merge.timer`. Only
`jbus.service` sets it, so a pass that a test, a sandbox or a hand starts leaves the machine's
timer as it is."""
PASS = frozenset({"success", "neutral", "skipped"})
"""The conclusions of a required check's own job that pass it, as `jmerge` reads them."""
FAIL = "failure"
"""The conclusion of a job that fails the required check of its workflow: the required job
runs once every job it needs ended, and fails where one of them failed (check.yml, macos.yml)."""


def _pending(half: Half) -> None:
    """Keep, for the tick to watch, each open pull request that a row's line names, whatever its
    checks say, and any other open pull request whose checks are still going, by the head the
    pass saw. The tick reads each one's check runs at its head as it is now, so a head pushed to
    a row's pull request reaches the next tick, within 10 s, however long ago a verdict named the
    end of its last head and whatever its rollup said: no check listed yet, as in the seconds
    after a push, `passed` before a required job that is still to start is in it (#1246), or
    `failed` at a failed shard while the others still run. A row's pull request whose head did
    not change costs the tick a 304 a tick, which spends none of the API allowance."""
    world = half.seen.world
    assert world is not None
    rows = restated.ended(half.run.state)
    going = []
    for pull in world.open.values():
        number, head = pull["number"], pull.get("headRefOid", "")
        if head and (number in rows or watch.checks(pull) == "pending"):
            going.append({"number": number, "head": head})
    going.sort(key=lambda one: one["number"])
    if store.read_json(half.run.state / PENDING, None) != going:
        store.write_json(half.run.state / PENDING, going)


def _timer(half: Half) -> None:
    """Start the tick's timer while some project's `PENDING` names a pull request, a row's open
    one or one whose checks are going, and stop it while none does, so no tick runs while there
    is nothing for it to watch. The pass is the only
    writer of `PENDING`, so the timer changes only here. Each pass sets it from the files as they
    are, whatever started or stopped it before (a boot, an install, a pass that died), and the
    timer's `OnActiveSec=` gives a check the pass just saw going its first tick within 10 s."""
    unit = os.environ.get(TIMER)
    if not unit or launchd.manager() != "systemd":
        return
    config = half.run.config
    going = sum(len(store.read_json(config.state(p) / PENDING, [])) for p in config.projects)
    active = (
        proc.run("systemctl", "--user", "is-active", unit, timeout=60).stdout.strip() == "active"
    )
    if bool(going) == active:
        return
    verb = "start" if going else "stop"
    done = proc.run("systemctl", "--user", verb, unit, timeout=60)
    if done.returncode != 0:
        half.run.say(f"tick: systemctl --user {verb} {unit} failed: {done.stderr.strip()}")
    elif going:
        half.run.say(f"tick: the tick watches {going} pull request(s), so {unit} runs")
    else:
        half.run.say(f"tick: the tick watches no pull request, so {unit} stops")


def _asked(run: passes.Pass, path: str, etag: str = "") -> tuple[str, dict[str, Any]] | None:
    """Return the ETag of GitHub's answer to `path`, with the answer, or None where GitHub
    answered 304 to `etag`, which spends none of the API allowance, or did not answer."""
    asked = run.run("gh", "api", path, "-i", *(("-H", f"If-None-Match: {etag}") if etag else ()))
    head, _, body = asked.stdout.replace("\r", "").partition("\n\n")
    status, *headers = head.splitlines() or [""]
    if status.split()[1:2] != [OK]:
        return None
    tags = [line.split(":", 1)[1].strip() for line in headers if line.lower().startswith("etag:")]
    try:
        given = json.loads(body)
    except ValueError:
        given = {}
    return (tags[0] if tags else ""), given if isinstance(given, dict) else {}


def _suite(job: dict[str, Any]) -> str:
    return str((job.get("check_suite") or {}).get("id", ""))


def _suites(
    run: passes.Pass, head: str, jobs: list[dict[str, Any]], known: dict[str, Any]
) -> dict[str, list[Any]]:
    """Return the workflow run of each check suite of `jobs`, `[name, run id]`, from `known`, and
    where a suite is new, from one read of the head's workflow runs. A suite that read does not
    list yet stays unknown, and its jobs belong to no workflow, until a later 200 asks again: a
    suite's workflow run may reach the runs list after its jobs reach the check runs."""
    suites = {k: list(one) for k, one in known.items() if isinstance(one, list) and len(one) == 2}
    if all(_suite(job) in suites for job in jobs):
        return suites
    asked = _asked(run, RUNS_AT % head)
    listed = (asked[1] if asked else {}).get("workflow_runs") or []
    for one in listed:
        if isinstance(one, dict) and one.get("check_suite_id") is not None:
            suites[str(one["check_suite_id"])] = [str(one.get("name", "")), one.get("id") or 0]
    return suites


Verdict = tuple[str, str, str]
"""What the check runs at a head say of its required checks: `failed` or `passed` with the
`why` `jmerge` would give and when it ended, or `""` for checks that all ended some other way,
which the tick leaves to `jmerge`."""


def _verdict(
    names: tuple[str, ...], jobs: list[dict[str, Any]], suites: dict[str, list[Any]]
) -> Verdict | None:
    """Return what the check runs at a head (`jobs`) say of its required checks `names`, or None
    while one is still going. A required check is the job of its name in the latest workflow run
    of that name, as `jmerge` reads one. The first of them, in the order `jmerge` reads them,
    with a job of that run that failed has failed, at the first such job's end: a shard that
    failed fails the check that needs it, while the other shards still run. Otherwise each has
    ended once its own job did, and passed where each passed. A required job GitHub does not
    list yet, as one waiting on the jobs it needs, is still going."""
    latest: dict[str, Any] = {}
    for name, run_id in suites.values():
        if name and (name not in latest or run_id > latest[name]):
            latest[name] = run_id
    flows: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        name, run_id = suites.get(_suite(job), ["", 0])
        if name and run_id == latest[name]:
            flows.setdefault(name, []).append(job)
    for name in names:
        failed = [
            at
            for job in flows.get(name, [])
            if job.get("status") == "completed" and job.get("conclusion") == FAIL
            if (at := _at(job.get("completed_at")))
        ]
        if failed:
            why = f"wait: {ready.CHECK_FAILED.format(check=name)}"
            return restated.FAILED, why, restated.moment(min(failed))
    own = [job for name in names for job in flows.get(name, []) if job.get("name") == name]
    if {job.get("name") for job in own} != set(names):
        return None
    ends = [_at(job.get("completed_at")) for job in own if job.get("status") == "completed"]
    if len(ends) < len(own) or None in ends:
        return None
    ended = restated.moment(max(at for at in ends if at is not None))
    if all(job.get("conclusion") in PASS for job in own):
        why = f"wait: {' and '.join(names)} passed, and jmerge has not judged it yet"
        return restated.PASSED, why, ended
    return "", "", ended


def _at(text: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text))
    except ValueError:
        return None


Wanted = dict[str, tuple[str, list[Any]]]
"""By a pull request's number, the head and its verdict that a run of `jmerge` is to run for."""


def _reads(run: passes.Pass) -> Wanted:
    """Ask GitHub for the check runs at the head of every pending pull request at once, as it is
    now, each with the ETag the tick kept, at most `proc.GH_CAP` at a time, and keep what the
    tick read of each (`SEEN`). Each pull request's line is restated as soon as its own answer
    lands (`_read`), not after the other reads. Return, by number, the head and its verdict where
    the verdict is new since `jmerge` last ran to its end for that head, so that `jmerge` is to
    run. A verdict is kept with the ETag it was read under, so a 304 to the next read still says
    it. `SEEN` has one writer, this function once every read landed; the lines of `work.json`
    each read writes are kept apart by `work.LOCK`."""
    kept = _pulls(run.state)
    names = cancelled.required(run)
    pending = list(restated.pending(run.state).items())
    pulls = {}
    if pending:
        with futures.ThreadPoolExecutor(max_workers=min(proc.GH_CAP, len(pending))) as pool:
            read = pool.map(
                lambda one: _read(run, names, one[0], one[1], kept.get(str(one[0]))), pending
            )
            pulls = {str(number): one for (number, _), one in zip(pending, read, strict=True)}
    if pulls != kept:
        store.write_json(run.state / SEEN, {"pulls": pulls})
    return {
        key: (one["head"], one["verdict"])
        for key, one in pulls.items()
        if one.get("verdict") is not None and one["verdict"] != one.get("ran")
    }


def _read(
    run: passes.Pass, names: tuple[str, ...], number: int, seen: str, found: Any
) -> dict[str, Any]:
    """Read the check runs at pull request `number`'s head with the ETag the tick kept (`found`),
    restate its line at once where its required checks failed or ended (`restated.checked`), and
    return what the tick keeps of it. A read GitHub answered 304, or did not answer, keeps what
    the tick had."""
    was: dict[str, Any] = found if isinstance(found, dict) else {}
    asked = _asked(run, CHECK_RUNS % number, str(was.get("etag", "")))
    if asked is None:
        return was
    etag, given = asked
    jobs = [job for job in given.get("check_runs") or [] if isinstance(job, dict)]
    head = next((str(job["head_sha"]) for job in jobs if job.get("head_sha")), seen)
    jobs = [job for job in jobs if job.get("head_sha", head) == head]
    same = was if was.get("head") == head else {}
    suites = _suites(run, head, jobs, same.get("suites") or {})
    verdict = _verdict(names, jobs, suites)
    if verdict is not None and verdict[0]:
        at = restated.moment(verbs.clock())
        for key in restated.checked(run.state, {number: (*verdict, head)}, at):
            run.say(f"tick {run.project.name}: a check ended, and {key}'s line says so")
    return {
        "etag": etag,
        "head": head,
        "suites": suites,
        "verdict": None if verdict is None else list(verdict),
        "ran": same.get("ran"),
    }


def _pulls(state: Path) -> dict[str, Any]:
    kept = store.read_json(state / SEEN, {}).get("pulls")
    return kept if isinstance(kept, dict) else {}


def _ran(run: passes.Pass, wanted: Wanted, said: merge.Said) -> None:
    """Keep what a run of `jmerge` the tick started said, and, once it ran to its end, the
    verdicts it ran for (`wanted`), as `ran` of each pull request still kept at the same head."""
    reload.keep(run, said)
    name = run.project.name
    if said.failed:
        run.say(f"tick {name}: a check ended, and jmerge did not run to its end")
        return
    pulls = _pulls(run.state)
    for key, (head, verdict) in wanted.items():
        if isinstance(pulls.get(key), dict) and pulls[key].get("head") == head:
            pulls[key] = {**pulls[key], "ran": verdict}
    store.write_json(run.state / SEEN, {"pulls": pulls})
    run.say(f"tick {name}: a check ended, and jmerge ran")


def _watched(config: jbus.Config) -> list[jbus.Project]:
    return [p for p in config.projects if store.read_json(config.state(p) / PENDING, [])]


def tick(config: jbus.Config, say=print) -> int:
    """Run one tick over every project: read the check runs at each pending pull request's head,
    restate the line of each pull request whose required checks failed or ended, and run
    `jmerge` where one did since `jmerge` last ran for it.

    Each `jmerge` runs on a thread of its own, and while one runs the tick reads every `EVERY`
    seconds on, and restates what it reads, until each has ended. A `jmerge` that merges runs the
    merged-tree guards first (`jmerge.treeguards`), 68 to 86 s on 2026-11-08, and the timer starts
    no tick while one runs. A verdict that is new in a read after the first is left to the next
    tick's `jmerge`, so a tick runs `jmerge` at most once a project, whatever its run said. A read
    that fails still lets each run under way end and be kept, since `jmerge` prints its `merged`
    line once (`reload.keep`), before the failure goes on."""
    watched = _watched(config)
    if not watched:
        return 0
    going: dict[futures.Future[merge.Said], tuple[passes.Pass, Wanted]] = {}
    with futures.ThreadPoolExecutor() as pool:
        try:
            for project in watched:
                run = passes.Pass(config, project, verbs.clock(), say)
                wanted = _reads(run)
                if wanted:
                    read = {int(key): head for key, (head, _) in wanted.items()}
                    going[pool.submit(merge.tick, run, read)] = (run, wanted)
            due = time.monotonic() + EVERY
            while going:
                ended, _ = futures.wait(
                    going,
                    timeout=max(0.0, due - time.monotonic()),
                    return_when=futures.FIRST_COMPLETED,
                )
                for one in ended:
                    _ran(*going.pop(one), one.result())
                if going and time.monotonic() >= due:
                    for project in _watched(config):
                        _reads(passes.Pass(config, project, verbs.clock(), say))
                    due = time.monotonic() + EVERY
        except Exception:
            for one in futures.as_completed(going):
                _ran(*going[one], one.result())
            raise
    return 0


STEPS = (
    verbs.Step("tellers", 15, "tick.pending", _pending, ("world",)),
    verbs.Step("tellers", 17, "tick.timer", _timer, (), shared=True),
)
VERBS = (
    verbs.Verb(
        "tick",
        "run jmerge for each project where a check ended since the last tick",
        verbs.nothing,
        lambda _, config: tick(config),
    ),
)
