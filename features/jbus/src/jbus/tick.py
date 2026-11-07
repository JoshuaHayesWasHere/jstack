"""`jbus tick`: restate a pull request's line, and run `jmerge`, within seconds of a check's job
ending, apart from the pass.

A green pull request merges on the first run of `jmerge` after its last check ended, and the
pass runs it once a pass, which is a minute or more apart. `jbus-merge.timer` runs a tick every
2 seconds while the last pass saw a check going, and the pass stops it while none is (`_timer`).
A tick asks GitHub nothing unless the last pass saw a pull request whose checks were
still going, or one it watched whose end no verdict has named yet (`PENDING`, written by the
pass's step `tick.pending`). For each such head it asks
GitHub for the head's check runs, which are the jobs of its workflow runs (`CHECK_RUNS`), with
the ETag it kept (`SEEN`). GitHub answers 304, which spends none of the API allowance, until a
job at that head changes. A check suite the tick has not seen yet costs one read of the head's
workflow runs (`RUNS_AT`), for the workflow each job belongs to.

On a 200 the tick restates, from that answer, the line of `work.json` of the pull request on the
check step (`_verdict`, `jbus.restated.checked`): failed, with the reason `jmerge` gives a failed
check, as soon as any job of a required check's workflow run failed, such as one shard of eight
while the other seven still run; or passed, for `jmerge` to judge next, once the required check's
own job passed. A required job GitHub does not list yet, as `check` while the shards it needs
run, is still going. It does so before it runs `jmerge`, and also where `jmerge` is busy and does
not run, so the line changes in the milliseconds after GitHub lists the job, not after the whole
workflow run ends. `jmerge` reads a check as failed only once the check's own job ends, so its
verdict that the check is still going does not undo the tick's `failed` at that head
(`restated.stands`). Where a head's verdict is new, the tick then runs `jmerge --if-free`
(`jbus.merge.tick`), whose verdicts restate each pull request's line again
(`jbus.restated.pulled`), and log each one that says otherwise than the tick as drift. The tick
bounds only its own part: it sees a job that GitHub lists as ended within 2 seconds. The
end-to-end delay is what `features/jbus/tests/checks_bound_probe.py` measures live. GitHub tells
no one of a job that ended sooner without a webhook, which jbus does not have.

A round costs the counted calls of its 200s: at most one a tick for each head, and at most one
for each change of a job's status at it (queued, in progress, completed), whichever is fewer,
plus one read of the workflow runs a check suite, and `jmerge`'s own once a verdict is new
(`docs/jbus/the-units.md`). Every other tick answers 304.

The tick keeps a head's ETag, and the verdict `jmerge` ran for, only once `jmerge` ran to its
end, so a tick that dies, a `jmerge` that was busy with the pass's own run, or one that failed
leaves the change to the next tick, which asks again and restates nothing twice. The pass runs
`jmerge --if-free` each minute too, so what the tick misses the next pass with the run lock free
does. A merge of the tick's that changed a skill is kept for the next pass's `reload.tell`
before the ETag is (`reload.keep`), since `jmerge` prints its `merged` line once. One run of
`jmerge` runs at a time, by its run lock (`jmerge.lock`). A tick reads GitHub's API budget before
it asks GitHub anything. While it is held (`jbus.budget`) the tick backs off to asking once in
`HELD` seconds, the interval the timer had before it ran every 2 seconds, and says so each time
it asks (`BACKOFF`): a 304 still spends nothing, and what a job that ended costs is `jmerge`'s,
which the floor is kept for.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

import jbus
from jbus import cancelled, launchd, merge, passes, reload, restated, verbs, watch
from jmerge import ready
from jsettings import budget, proc, store

if TYPE_CHECKING:
    from jbus.poll import Half

PENDING = restated.PENDING
SEEN = "tick.json"
"""What the tick read of each pending head (`heads`, by its sha): the ETag of its check runs
(`etag`), the workflow run of each of its check suites (`suites`, each `[name, run id]`), and
the verdict `jmerge` last ran to its end for (`ran`). Only the tick writes it."""
CHECK_RUNS = "repos/{owner}/{repo}/commits/%s/check-runs?per_page=100"
"""A head's check runs, the latest of each name, which are the jobs of its workflow runs."""
RUNS_AT = "repos/{owner}/{repo}/actions/runs?head_sha=%s&per_page=100"
"""A head's workflow runs, asked for only when its check runs name a check suite the tick does
not know the workflow of yet."""
OK = "200"
HELD = 5
"""The seconds between the times a tick asks GitHub while its budget is held."""
BACKOFF = "tick-held.json"
"""When a tick last asked GitHub while its budget was held, in jbus's own state directory. Only
the tick writes it, and a stamp it cannot read is one from long ago."""
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
    """Keep the open pull requests whose checks are still going, for the tick to watch, by the
    head the pass saw. A head the tick watched stays while the rollup reads its checks as ended,
    until its row's line names it as one whose end a verdict of the tick's or `jmerge`'s said
    (`restated.ENDED`): the rollup can say `passed` before a required job that is still to start
    is in it (#1246), or `failed` at a failed shard while the others still run, and the tick that
    stopped asking then would miss the end."""
    world = half.seen.world
    assert world is not None
    watched, ended = restated.pending(half.run.state), restated.ended(half.run.state)
    going = []
    for pull in world.open.values():
        number, head = pull["number"], pull.get("headRefOid", "")
        unjudged = bool(head) and watched.get(number) == head and ended.get(number, head) != head
        if watch.checks(pull) == "pending" or unjudged:
            going.append({"number": number, "head": head})
    going.sort(key=lambda one: one["number"])
    if store.read_json(half.run.state / PENDING, None) != going:
        store.write_json(half.run.state / PENDING, going)


def _timer(half: Half) -> None:
    """Start the tick's timer while some project's pull request has its checks going, and stop it
    while none has, so no tick runs while there is nothing for it to watch. The pass is the only
    writer of `PENDING`, so the timer changes only here. Each pass sets it from the files as they
    are, whatever started or stopped it before (a boot, an install, a pass that died), and the
    timer's `OnActiveSec=` gives a check the pass just saw going its first tick within 2 s."""
    unit = os.environ.get(TIMER)
    if not unit or launchd.manager() != "systemd":
        return
    config = half.run.config
    going = sum(len(store.read_json(config.state(p) / PENDING, [])) for p in config.projects)
    active = proc.run("systemctl", "--user", "is-active", unit).stdout.strip() == "active"
    if bool(going) == active:
        return
    verb = "start" if going else "stop"
    done = proc.run("systemctl", "--user", verb, unit)
    if done.returncode != 0:
        half.run.say(f"tick: systemctl --user {verb} {unit} failed: {done.stderr.strip()}")
    elif going:
        half.run.say(f"tick: checks are going on {going} pull request(s), so {unit} runs")
    else:
        half.run.say(f"tick: no pull request has checks going, so {unit} stops")


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


def _read(run: passes.Pass) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], bool]:
    """Ask GitHub for the check runs of each pending head, with the ETag the tick kept, and
    restate the line of each pull request whose head's required checks failed or ended
    (`restated.checked`). Return what the tick read of each head as it is to be kept once
    `jmerge` ran to its end, as it is to be kept where `jmerge` did not, and whether a head's
    verdict is new since `jmerge` last ran to its end for it, so that `jmerge` is to run."""
    kept = store.read_json(run.state / SEEN, {}).get("heads")
    kept = kept if isinstance(kept, dict) else {}
    pending = restated.pending(run.state)
    names = cancelled.required(run)
    after, before, said = {}, {}, {}
    for number, head in pending.items():
        found = kept.get(head)
        was: dict[str, Any] = found if isinstance(found, dict) else {}
        before[head] = after[head] = was
        asked = _asked(run, CHECK_RUNS % head, str(was.get("etag", "")))
        if asked is None:
            continue
        etag, given = asked
        jobs = [job for job in given.get("check_runs") or [] if isinstance(job, dict)]
        suites = _suites(run, head, jobs, was.get("suites") or {})
        verdict = _verdict(names, jobs, suites)
        after[head] = before[head] = {"etag": etag, "suites": suites, "ran": was.get("ran")}
        if verdict is not None and list(verdict) != was.get("ran"):
            before[head] = {**was, "suites": suites}
            after[head] = {**after[head], "ran": list(verdict)}
        if verdict is not None and verdict[0]:
            said[number] = (*verdict, head)
    at = restated.moment(verbs.clock())
    for key in restated.checked(run.state, said, at):
        run.say(f"tick {run.project.name}: a check ended, and {key}'s line says so")
    return after, before, after != before


def tick(config: jbus.Config, say=print) -> int:
    """Run one tick over every project: read the check runs of each pending head, restate the
    line of each pull request whose required checks failed or ended, and run `jmerge` where one
    did since `jmerge` last ran for it."""
    watched = [p for p in config.projects if store.read_json(config.state(p) / PENDING, [])]
    if not watched:
        return 0
    held = budget.held(budget.read())
    if held:
        if not _due(config, verbs.clock()):
            return 0
        say(f"tick: the budget is held, so the tick asks GitHub once in {HELD} s, not 2 s: {held}")
    for project in watched:
        run = passes.Pass(config, project, verbs.clock(), say)
        after, before, due = _read(run)
        if not due:
            if after != store.read_json(run.state / SEEN, {}).get("heads"):
                store.write_json(run.state / SEEN, {"heads": after})
            continue
        said = merge.tick(run)
        reload.keep(run, said)
        if not said.failed:
            store.write_json(run.state / SEEN, {"heads": after})
            say(f"tick {project.name}: a check ended, and jmerge ran")
        else:
            store.write_json(run.state / SEEN, {"heads": before})
            say(f"tick {project.name}: a check ended, and jmerge did not run to its end")
    return 0


def _due(config: jbus.Config, now: datetime) -> bool:
    """Whether a tick may ask GitHub while its budget is held: once `HELD` seconds passed since
    the last such tick asked, which this one then stamps as asked (`BACKOFF`)."""
    where = config.state_dir / BACKOFF
    kept = store.read_json(where, {})
    try:
        since = (now - datetime.fromisoformat(kept["asked"])).total_seconds()
    except (ValueError, TypeError, KeyError):
        since = None
    if since is not None and 0 <= since < HELD:
        return False
    store.write_json(where, {"asked": now.isoformat()})
    return True


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
