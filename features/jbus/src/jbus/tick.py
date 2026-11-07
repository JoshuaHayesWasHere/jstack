"""`jbus tick`: run `jmerge` within seconds of a check ending, apart from the pass.

A green pull request merges on the first run of `jmerge` after its last check ended, and the
pass runs it once a pass, which is a minute or more apart. `jbus-merge.timer` runs a tick every
2 seconds. A tick asks GitHub nothing unless the last pass saw a pull request whose checks were
still going (`PENDING`, written by the pass's step `tick.pending`). For each such project it asks
GitHub for the repo's last completed workflow runs, with the ETag it kept (`SEEN`). GitHub answers
304, which spends none of the API allowance, until a run ends, and then the tick runs `jmerge
--if-free` (`jbus.merge.tick`), whose verdicts restate each pull request's line of `work.json` as
the run ends (`jbus.restated.pulled`). The tick bounds only its own part: it sees a run that
GitHub lists as ended within 2 seconds. GitHub's list can show a run late, and a `jmerge` the pass
holds makes the tick try again, so the end-to-end delay is what
`features/jbus/tests/checks_bound_probe.py` measures live. GitHub tells no one of a run that ended
sooner without a webhook, which jbus does not have.

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

from datetime import datetime
from typing import TYPE_CHECKING

import jbus
from jbus import merge, passes, reload, verbs, watch
from jsettings import budget, store

if TYPE_CHECKING:
    from jbus.poll import Half

PENDING = "checks-pending.json"
"""The open pull requests whose checks the last pass saw still going, by number. Only the pass
writes it."""
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
    """Keep the open pull requests whose checks are still going, for the tick to watch."""
    world = half.seen.world
    assert world is not None
    going = sorted(
        pull["number"] for pull in world.open.values() if watch.checks(pull) == "pending"
    )
    if store.read_json(half.run.state / PENDING, None) != going:
        store.write_json(half.run.state / PENDING, going)


def _ended(run: passes.Pass) -> str | None:
    """Return the ETag of the repo's completed runs where they changed since the tick last ran
    `jmerge`, and None where they did not, or GitHub did not answer."""
    seen = store.read_json(run.state / SEEN, {}).get("etag", "")
    asked = run.run("gh", "api", RUNS, "-i", *(("-H", f"If-None-Match: {seen}") if seen else ()))
    status, *headers = asked.stdout.replace("\r", "").split("\n\n", 1)[0].splitlines() or [""]
    if status.split()[1:2] != [OK]:
        return None
    tags = [line.split(":", 1)[1].strip() for line in headers if line.lower().startswith("etag:")]
    return tags[0] if tags else ""


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
        etag = _ended(run)
        if etag is None:
            continue
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
