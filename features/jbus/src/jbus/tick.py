"""`jbus tick`: run `jmerge` within seconds of a check ending, apart from the pass.

A green pull request merges on the first run of `jmerge` after its last check ended, and the
pass runs it once a pass, which is a minute or more apart. `jbus-merge.timer` runs a tick every
2 seconds. A tick asks GitHub nothing unless the last pass saw a pull request whose checks were
still going, or one it watched whose end no verdict has named yet (`PENDING`, written by the
pass's step `tick.pending`). For each such project it asks
GitHub for the repo's last completed workflow runs, with the ETag it kept (`SEEN`). GitHub answers
304, which spends none of the API allowance, until a run ends.

On a 200 the tick first restates, from that answer, the line of `work.json` of each pending pull
request on the check step whose required checks ended at its head (`_restate`,
`jbus.restated.checked`): failed, with the reason `jmerge` gives a failed check, or passed, for
`jmerge` to judge next. It does so before it runs `jmerge`, and also where `jmerge` is busy and
does not run, so the line changes in the milliseconds after GitHub lists the run, not after
`jmerge`'s own run of seconds. Then it runs `jmerge --if-free` (`jbus.merge.tick`), whose verdicts
restate each pull request's line again (`jbus.restated.pulled`), and log each one that says
otherwise than the tick as drift. The tick bounds only its own part: it sees a run that GitHub
lists as ended within 2 seconds. GitHub's list shows a run about 2.5 seconds late, so the
end-to-end delay is what `features/jbus/tests/checks_bound_probe.py` measures live. GitHub tells
no one of a run that ended sooner without a webhook, which jbus does not have.

The tick keeps the ETag only once `jmerge` ran to its end, so a tick that dies, a `jmerge` that
was busy with the pass's own run, or one that failed leaves the change to the next tick. The pass
runs `jmerge --if-free` each minute too, so what the tick misses the next pass with the run lock
free does. A merge of the
tick's that changed a skill is kept for the next pass's `reload.tell` before the ETag is
(`reload.keep`), since `jmerge` prints its `merged` line once. One run of `jmerge`
runs at a time, by its run lock (`jmerge.lock`). A tick reads GitHub's API budget before it asks
GitHub anything. While it is held (`jbus.budget`) the tick backs off to asking once in `HELD`
seconds, the interval the timer had before it ran every 2 seconds, and says so each time it asks
(`BACKOFF`): a 304 still spends nothing, and what a run that ended costs is `jmerge`'s, which the
floor is kept for.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jbus
from jbus import cancelled, merge, passes, reload, restated, verbs, watch, work
from jmerge import ready
from jsettings import budget, store

if TYPE_CHECKING:
    from jbus.poll import Half

PENDING = restated.PENDING
SEEN = "tick.json"
"""The ETag of the repo's completed runs when `jmerge` last ran to its end for a tick. Only the
tick writes it."""
RUNS = "repos/{owner}/{repo}/actions/runs?per_page=20&status=completed"
OK = "200"
HELD = 5
"""The seconds between the times a tick asks GitHub while its budget is held."""
BACKOFF = "tick-held.json"
"""When a tick last asked GitHub while its budget was held, in jbus's own state directory. Only
the tick writes it, and a stamp it cannot read is one from long ago."""


def _pending(half: Half) -> None:
    """Keep the open pull requests whose checks are still going, for the tick to watch, by the
    head the pass saw. A head the tick watched stays while the rollup reads its checks as ended,
    until its row's line names it as one whose end a verdict of the tick's or `jmerge`'s said
    (`restated.ENDED`): the rollup can say `passed` before a required job that is still to start
    is in it (#1246), or `failed` at a failed shard while the others still run, and the tick that
    stopped asking then would miss the end."""
    world = half.seen.world
    assert world is not None
    watched, ended = restated.pending(half.run.state), _ended_heads(half.run.state)
    going = []
    for pull in world.open.values():
        number, head = pull["number"], pull.get("headRefOid", "")
        unjudged = bool(head) and watched.get(number) == head and ended.get(number, head) != head
        if watch.checks(pull) == "pending" or unjudged:
            going.append({"number": number, "head": head})
    going.sort(key=lambda one: one["number"])
    if store.read_json(half.run.state / PENDING, None) != going:
        store.write_json(half.run.state / PENDING, going)


def _ended_heads(state: Path) -> dict[int, str]:
    """Return, by number, the head each row's line of a pull request names as one whose checks a
    verdict said ended (`restated.ENDED`), or nothing for a line that names none. A pull request
    with no row's line has nothing on the view to keep right, and is not in it."""
    kept = work.read(state) or {"work": []}
    found = {}
    for one in kept["work"]:
        if not isinstance(one, dict) or one.get("kind") != "row":
            continue
        number = str(one.get("pr", "")).removeprefix("#")
        if number.isdigit():
            found[int(number)] = str(one.get(restated.ENDED, ""))
    return found


def _ended(run: passes.Pass) -> tuple[str, dict[str, Any]] | None:
    """Return the ETag of the repo's completed runs where they changed since the tick last ran
    `jmerge`, with GitHub's answer, and None where they did not, or GitHub did not answer."""
    seen = store.read_json(run.state / SEEN, {}).get("etag", "")
    asked = run.run("gh", "api", RUNS, "-i", *(("-H", f"If-None-Match: {seen}") if seen else ()))
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


OUTCOMES = {"success": restated.PASSED, "failure": restated.FAILED}
"""The conclusions of a run that say how its check ended. Any other, such as `cancelled` or
`skipped`, is `jmerge`'s to read."""


def _restate(run: passes.Pass, given: dict[str, Any]) -> None:
    """Restate the line of each pending pull request whose required checks ended at its head, as
    GitHub's list of runs (`given`) shows them: the first required check, in the order `jmerge`
    reads them, whose run failed gives `failed` and `jmerge`'s reason, and all of them passed give
    `passed`. A required check is a workflow of its name, as `jmerge` reads one. One with no ended
    run in the list, one that ended otherwise, or a run with no time it ended, leaves the pull
    request to `jmerge`."""
    heads = restated.pending(run.state)
    ends: dict[tuple[str, str], dict[str, Any]] = {}
    for one in given.get("workflow_runs") or []:
        if isinstance(one, dict) and (at := _at(one.get("updated_at"))):
            ends.setdefault((str(one.get("head_sha")), str(one.get("name"))), {**one, "at": at})
    names, said = cancelled.required(run), {}
    for number, head in heads.items():
        found = [ends.get((head, name)) for name in names]
        outcomes = [OUTCOMES.get(str((one or {}).get("conclusion"))) for one in found]
        stop = next((n for n, tick in enumerate(outcomes) if tick != restated.PASSED), len(names))
        if stop < len(names) and outcomes[stop] != restated.FAILED:
            continue
        ended = restated.moment(max(one["at"] for one in found[: stop + 1] if one))
        if stop < len(names):
            why = f"wait: {ready.CHECK_FAILED.format(check=names[stop])}"
            said[number] = (restated.FAILED, why, ended, head)
        else:
            why = f"wait: {' and '.join(names)} passed, and jmerge has not judged it yet"
            said[number] = (restated.PASSED, why, ended, head)
    at = restated.moment(verbs.clock())
    for key in restated.checked(run.state, said, at):
        run.say(f"tick {run.project.name}: a run ended, and {key}'s line says its check ended")


def _at(text: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text))
    except ValueError:
        return None


def tick(config: jbus.Config, say=print) -> int:
    """Run one tick over every project: `jmerge` for each whose pending pull request may have a
    check that ended since the last tick."""
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
        ended = _ended(run)
        if ended is None:
            continue
        etag, given = ended
        _restate(run, given)
        said = merge.tick(run)
        reload.keep(run, said)
        if not said.failed:
            store.write_json(run.state / SEEN, {"etag": etag})
            say(f"tick {project.name}: a run ended, and jmerge ran")
        else:
            say(f"tick {project.name}: a run ended, and jmerge did not run to its end")
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


STEPS = (verbs.Step("tellers", 15, "tick.pending", _pending, ("world",)),)
VERBS = (
    verbs.Verb(
        "tick",
        "run jmerge for each project where a check ended since the last tick",
        verbs.nothing,
        lambda _, config: tick(config),
    ),
)
