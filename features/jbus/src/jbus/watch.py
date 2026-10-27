"""This module asks T3 Code and GitHub for the work that is out, and writes each finding as
one line.

`look` asks once a pass for the project's crewmate threads, its open pull requests and the ones
merged lately. `look` counts the threads of a slug that was removed from the queue, but leaves them
out of its answer, so no pass finds such a thread stale or tells it to carry on. The slug's pull
requests stay in the answer. When only GitHub was silent, the answer from `look` still gives how
many crews are out. The machine has one such count: `jbus poll` adds it up over every project.
`watch` sends a line for what a home would have noticed: a merge; a thread that ran past its
timebox, waits on a request, or ended with no Result; a main branch whose check failed after a
merge; a red run of a nightly workflow (`NIGHTLIES`); and a revert. `watch` names no cause and
changes nothing.
A finding that no rule covers becomes a gate. `status` gives the table's derived column for a slug.
`why` gives the reason the slug's row waits: the line that `jmerge` has for the slug's pull request,
what stopped the slug's launch, or what the slug's Result leaves.

A pull request belongs to the slug whose brief names it on the `Branch:` line of a Result,
and `jmerge` ties the two the same way (`tied`). The name of a pull request's branch gives
its slug only where no brief names the pull request.

`work.judge` judges a row's state once a pass, from the row's `facts`. The facts of a thread out
that belongs to no row are `thread_facts`. A row's status, one of `queue.STATUSES`, is the
projection of the row's state (`work.status`): `gate`, `pr`, `merged`, `done`, `left`, `launched`,
`running`, `waiting`, `stale`, `failed` or `queued`. For a row that merged, ended or left
something, the row's `why` is what its Result leaves. A row is stale when its thread ended or hung
and wrote nothing. Until `UNWRITTEN_MINUTES` after the thread last wrote, jbus keeps resuming the
row's crew. After that, the row is `left` (`unwritten`), its `why` says so, and the slug's home
closes the row (`leftover`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from jbus import Refused, budget, merge, queue, read_json, verbs, work, write_json
from jbus.merge import Said, parse
from jbus.mirror import field as said_on
from jbus.mirror import last_result, sections
from jbus.passes import Changed, Depends, Pass, Slot
from jbus.t3 import Client, T3Error
from jbus.wake import cut
from jgauge import slot, waiters
from jmerge import checks as reading
from jmerge import mainjson
from jmerge import stacked as stacks
from jmerge.asked import Silent
from jmerge.asked import why as asked_why

EVENTS = {"merged": "quiet", "stale": "quiet", "retro": "quiet"}
TITLE = "crew: "
STARTING = ("preparing", "queued", "starting")
LIVE = (*STARTING, "running", "waiting")
ENDED = ("failed", "interrupted", "cancelled")
KNOWN = (*LIVE, *ENDED, "completed")
TIMEBOX_HOURS = 4.0
WAITING_MINUTES = 30
UNWRITTEN_MINUTES = 15
RETRO = timedelta(hours=24)
NOT_RED = ("success", "neutral", "skipped", "cancelled")
NO_JOB = "nojob"
"""What `_check` answers for a commit on main whose failed check runs started no job."""
NIGHTLY_RED = ("failure", "timed_out")
NIGHTLY_WINDOW = timedelta(days=3)
NIGHTLY_GRACE = timedelta(hours=1)
NIGHTLY_RELEASE = ("push", "release")
"""The events of a nightly's run off the default branch that are still filed: a release's tag,
since no nightly runs on a push to a branch (`_nightly_red`)."""
GREEN = "passed"
"""What a nightly's `seen` keeps for a run of it that passed on its `branch`."""
_FAILED_TEST = re.compile(r"\b(?:FAILED|ERROR) (\S+::\S+)")
_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_STAMP = r"^(?:\S+Z )?"
_STEP_COUNT = re.compile(_STAMP + r"(?:##\[warning\]|::warning::).*?\b(\d+) tests? failed\b", re.M)
_STEP_TEST = re.compile(_STAMP + r"FAILED (\S.*?)\s*$", re.M)
_SUMMARY = re.compile(_STAMP + r"=+ (.*\bin [0-9.]+s\b.*?) =+\s*$", re.M)
_SUMMARY_COUNT = re.compile(r"(\d+) (?:failed|errors?)\b")
_TIMEBOX = re.compile(r"^TIMEBOX:\s*(\d+(?:\.\d+)?)\s*(?:h\b|hours?\b)", re.M)
OPEN = "number,url,title,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,isDraft"
NEVER = "neverStarted"
"""The key of an open pull request's failed checks whose job ran no step, as the pass found
them: `checks` reads them as `jmerge --checks` does."""
MERGED = "number,url,title,headRefName,headRefOid,mergeCommit,mergedAt"
GATED = "a gate the Chef has"
OFF, STOP, UNREAD = "dispatch is off", "the stop file is there", "not read in this pass"
AFTER_MERGE = "after the merge"
UNRESOLVED = "Could not resolve to a"
WORDS = 100
_PULL = re.compile(r"^(https?://\S+/pull/(\d+))/?$")
_AGAINST = re.compile(r"^Pull request:[ \t]*open one against (?P<branch>[^\s,;:()`]+)", re.M)


@dataclass
class World:
    """A `World` is one pass's answers. `threads` holds a slug's threads that are not settled.

    T3 Code's list leaves out an archived thread, so `jbus.archived` asks after each launched
    thread that the list does not have. `archived` holds, by slug, the threads that T3 Code
    reports as archived. `missing` holds the slugs whose thread is unknown to T3 Code, and
    `unasked` the slugs for which jbus could not ask T3 Code. `waiting` holds the threads that
    wait on a test slot and are not woken yet (`jgauge.waiters`), which jbus reads once a pass.
    """

    threads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    settled: dict[str, dict[str, Any]] = field(default_factory=dict)
    archived: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing: set[str] = field(default_factory=set)
    unasked: set[str] = field(default_factory=set)
    open: dict[str, dict[str, Any]] = field(default_factory=dict)
    merged: dict[str, dict[str, Any]] = field(default_factory=dict)
    waiting: set[str] = field(default_factory=set)

    def thread(self, slug: str) -> dict[str, Any] | None:
        live = self.threads.get(slug, [])
        if live:
            return live[0] if len(live) == 1 else None
        return self.settled.get(slug) or self.archived.get(slug)

    def live(self) -> tuple[str, ...]:
        """The slug of each crew thread at work, once for each such thread."""
        return tuple(
            slug for slug, found in self.threads.items() for t in found if t["status"] in LIVE
        )

    def stack_on(self, run: Pass, unmet: list[str], brief: str) -> stacks.Stacked | None:
        """The open pull request a row whose depends `unmet` are not over launches stacked on: the
        one row it still waits on, once that row's pull request is open. A stack sits on one
        branch, so a row that waits on two or more rows launches on none, and nor does a row
        whose `brief` goes on another branch than that row's (`against`): a row for a train
        that builds on a row for main waits for it to merge."""
        if len(unmet) != 1 or unmet[0] not in self.open:
            return None
        if against(queue.brief(run.state, unmet[0]) or "") != against(brief):
            return None
        branch = str(self.open[unmet[0]].get("headRefName") or "")
        return stacks.Stacked(unmet[0], branch) if branch else None


@dataclass(frozen=True)
class Waits:
    """A `Waits` is what `jmerge` said of waiting pull requests, by number: `wait: <its reason>`.

    `failed` means `jmerge` did not run to its end here, so the pass knows nothing of a
    number that `said` does not have.
    """

    said: dict[str, str]
    failed: bool = False


@dataclass
class Look:
    """A `Look` holds what a pass could learn. `world` is set when T3 Code and GitHub both
    answered.

    `out` is the slug of each crew thread that T3 Code lists as live, once for each thread, which
    jbus knows whenever T3 Code answered. A pass counts them by home and by project
    (`dispatch.Caps`). `why` is the reason T3 Code did not answer. `held` is why the pass asked
    GitHub nothing to save its API budget, or why it could not tell what is left of it.
    """

    world: World | None = None
    out: tuple[str, ...] | None = None
    why: str = ""
    held: str = ""


def when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def crew_threads(client: Client, project_id: str, contains: str = TITLE) -> list[dict[str, Any]]:
    found, cursor = [], None
    for _ in range(20):
        asked = {"projectId": project_id, "titleContains": contains, "limit": 100}
        said = client.call("t3_thread_list", {**asked, **({"cursor": cursor} if cursor else {})})
        found += said.get("threads", [])
        cursor = said.get("nextCursor")
        if not cursor:
            break
    return [t for t in found if str(t.get("title", "")).startswith(TITLE)]


def _silent(run: Pass, why: str) -> Look:
    """Record once a day that T3 Code gave no answer. The pass then launches nothing and watches
    nothing."""
    name = run.project.name
    run.say(f"wait {name}: T3 Code could not be asked ({why})")
    day = run.now.date().isoformat()
    run.condition(name, "T3 Code could not be asked", why, key=f"t3 {day}")
    return Look(why=why)


def pulls(run: Pass, state: str, fields: str, *more: str) -> list[dict[str, Any]]:
    """Return the pull requests that `gh` lists, or raise `Silent` if `gh` gave none."""
    asked = run.run("gh", "pr", "list", "--state", state, "--json", fields, *more)
    try:
        pulls = json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        pulls = None
    if not isinstance(pulls, list):
        raise Silent(asked_why(asked))
    return pulls


def _named(run: Pass, url: str) -> list[dict[str, Any]]:
    """Return the pull request at this address if it merged, as a list like the one `pulls`
    returns.

    If GitHub says it cannot resolve the address, `_named` returns no pull request and the
    pass goes on, since a brief may name such an address. If `gh` failed any other way, it
    gave no answer, and `_named` raises `Silent`.
    """
    asked = run.run("gh", "pr", "view", url, "--json", f"{MERGED},state")
    if asked.returncode and UNRESOLVED in asked.stderr:
        return []
    try:
        pull = json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        pull = None
    if not isinstance(pull, dict):
        raise Silent(asked_why(asked))
    return [pull] if pull.get("state") == "MERGED" else []


def named(result: str) -> tuple[str, str]:
    """Return the address and number of the pull request at the end of a Result's `Branch:`
    line."""
    words = said_on(result, "Branch").split()
    found = _PULL.match(words[-1]) if words else None
    return (found[1], found[2]) if found else ("", "")


def tied(run: Pass) -> dict[str, str]:
    """Return the slug of each pull request that a brief names, by its address.

    A brief names a pull request with a `Branch:` line that ends on its address, in any of
    its Results. The first brief with such a line gives the slug, as it does for `jmerge`.
    """
    found: dict[str, str] = {}
    for path in sorted((run.home / "tasks").glob("*.md")):
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            url = named(line)[0] if line.startswith("Branch:") else ""
            if url:
                found.setdefault(url, path.stem)
    return found


def look(run: Pass, client: Client | None, rows: list[dict[str, Any]]) -> Look:
    """Ask T3 Code and GitHub. If either one is silent, there is no world to act on.

    When GitHub is silent, jbus still knows the crews out, and they count toward `max_running`.

    The list of merged pull requests is the last hundred. When the queue names a slug that is
    not in that list, `look` asks GitHub for it by name. `look` keeps any merge that it finds
    that way, so the slug stays merged.

    `look` keeps a pull request under the slug whose brief names it (`tied`), and under the
    name of its branch where no brief does. When a slug's brief names a pull request, `look`
    asks for that pull request by its address.

    First of all, `look` reads GitHub's API budget (`jbus.budget`), and every `Look` it returns
    holds it, T3 Code silent or not: a step that spends the budget needs it. With no answer, or
    with the budget at or under its floor, `look` asks GitHub nothing else, and the pass has no
    world, as when GitHub is silent: no row changes. `jmerge` ran before, so a merge still goes.
    """
    asked = run.run(*budget.ASK)
    left = budget.parse(asked.stdout) if asked.returncode == 0 else None
    held = budget.held(left)
    if client is None:
        return replace(_silent(run, "no token: run `jbus t3 login`"), held=held)
    world = World(waiting={one.thread for one in waiters.read(slot.locks_dir()) if not one.woken})
    slug_of = tied(run)
    url_of = {slug: url for url, slug in slug_of.items()}
    try:
        listed = crew_threads(client, run.project.project_id)
    except T3Error as error:
        return replace(_silent(run, str(error)), held=held)
    for thread in sorted(listed, key=lambda t: t.get("createdAt", "")):
        slug = thread["title"][len(TITLE) :].strip()
        if thread.get("settled"):
            world.settled[slug] = thread
        else:
            world.threads.setdefault(slug, []).append(thread)
    out = world.live()
    for slug in run.removed:
        world.threads.pop(slug, None)
    if left is None:
        run.say(f"wait {run.project.name}: could not ask GitHub{asked_why(asked)}")
        return Look(out=out, held=held)
    if held:
        run.say(f"wait {run.project.name}: GitHub not asked: {held}")
        key = f"budget {left.low.name} {left.low.reset.isoformat()}"
        run.condition(run.project.name, "GitHub's API budget is under the floor", held, key=key)
        return Look(out=out, held=held)
    kept: dict[str, dict[str, Any]] = read_json(run.state / "merged.json", {})
    named = {slug for row in rows for slug in (row["slug"], *row.get("depends", []))}
    try:
        for state, fields, into in (("open", OPEN, world.open), ("merged", MERGED, world.merged)):
            for pull in sorted(
                pulls(run, state, fields, "--limit", "100"), key=lambda p: p.get("mergedAt") or ""
            ):
                if state == "open":
                    rollup = pull.get("statusCheckRollup") or []
                    never = reading.never_started(rollup, lambda *at: job(run, *at))
                    pull[NEVER] = sorted(never)
                into[slug_of.get(pull.get("url", "").rstrip("/"), pull["headRefName"])] = pull
        for slug in sorted(named - set(world.open) - set(world.merged)):
            if slug not in kept:
                if slug in url_of:
                    found = _named(run, url_of[slug])
                else:
                    found = pulls(run, "merged", MERGED, "--head", slug, "--limit", "1")
                if not found:
                    continue
                kept[slug] = found[0]
                write_json(run.state / "merged.json", kept)
            world.merged[slug] = kept[slug]
    except Silent as silent:
        run.say(f"wait {run.project.name}: could not ask GitHub{silent}")
        return Look(out=out)
    return Look(world, out)


def checks(pull: dict[str, Any]) -> str:
    """Return a pull request's checks in one word, as `jmerge --checks` reads them
    (`jmerge.checks`), counting the failed checks that the pass found whose job ran no step
    (`NEVER`). A check that never started, beside checks that passed, gives `failed`, the
    first word that `jmerge --checks` prints for such a check. `jmerge` decides a merge, not
    `checks`. A draft's word is `draft`: CI runs no check on one."""
    rollup, never = pull.get("statusCheckRollup") or [], frozenset(pull.get(NEVER) or ())
    word = reading.checks(rollup, never, bool(pull.get("isDraft")))
    return "failed" if word == "unstarted" else word


def job(run: Pass, repo: str, number: str) -> dict:
    """Return a job of a workflow run as GitHub gives it, or {} where GitHub gives none."""
    asked = run.run("gh", "api", f"repos/{repo}/actions/jobs/{number}")
    try:
        given = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except ValueError:
        given = {}
    return given if isinstance(given, dict) else {}


def brief_of(run: Pass, slug: str) -> str:
    for path in (run.home / "tasks" / f"{slug}.md", run.state / "briefs" / f"{slug}.md"):
        try:
            return path.read_text(errors="replace")
        except OSError:
            continue
    return ""


def _stale(run: Pass, slug: str, thread: dict[str, Any]) -> str:
    status, text = thread["status"], brief_of(run, slug)
    if status == "running":
        limit = _TIMEBOX.search(text)
        hours = (run.now - when(thread["createdAt"])).total_seconds() / 3600
        if hours > (float(limit[1]) if limit else TIMEBOX_HOURS):
            return f"stale {slug}: running {int(hours)}h, past its TIMEBOX"
    elif status == "waiting":
        minutes = (run.now - when(thread["updatedAt"])).total_seconds() / 60
        if minutes >= WAITING_MINUTES:
            return f"stale {slug}: waiting on a request {int(minutes)} min"
    elif status in (*ENDED, "completed") and not last_result(text):
        return f"stale {slug}: thread {status} with no Result"
    return ""


def left(result: str) -> str:
    """Return, in a few words, what a Result leaves undone. Return nothing when the Result says
    `Status: done` and `Left: none`."""
    status, rest = said_on(result, "Status"), said_on(result, "Left")
    if rest and rest != "none":
        return f"left: {cut(rest, WORDS)}"
    if status != "done":
        return f"status: {cut(status, WORDS)}" if status else "its Result has no Status line"
    return "" if rest else "its Result has no Left line"


def unfinished(result: str) -> str:
    """Return what keeps a Result with no merge from ending its task, or nothing.

    The answer is what the Result leaves, or a `Branch:` line that is missing or that ends on
    an address. An address there means a pull request that is neither open nor merged. This
    function is the one rule for a task that ended with no pull request: `ended` and
    `threads.finished` both call it.
    """
    short, words = left(result), said_on(result, "Branch").split()
    if short:
        return short
    if not words:
        return "its Result has no Branch line"
    if words[-1].startswith("http"):
        number = named(result)[1]
        return f"pull request{f' #{number}' if number else ''} is not open and not merged"
    return ""


def after_merge(result: str) -> bool:
    """Return whether a Result leaves work for after its merge. The pass tells the thread
    about that work."""
    return said_on(result, "Left").lower().startswith(AFTER_MERGE)


@dataclass(frozen=True)
class End:
    """An `End` is the outcome of a row whose thread ended with a Result: `done`, or `left`
    with a `why`."""

    word: str
    why: str = ""


def ended(run: Pass, world: World, slug: str) -> End | None:
    """Return the end of a slug whose thread ended with a Result and no pull request pending.

    The slug's thread has ended when the thread is settled or no longer `LIVE`. If T3 Code lists no
    thread for a slug, the slug has not started, or this pass launched it. A slug with a pull
    request that is open or merged takes its status from that pull request.
    """
    thread = world.thread(slug)
    if slug in world.open or slug in world.merged:
        return None
    if thread is None or (not thread.get("settled") and thread["status"] in LIVE):
        return None
    result = last_result(brief_of(run, slug))
    if not result:
        return None
    short = unfinished(result)
    return End("left", short) if short else End("done")


def gone(run: Pass, world: World, slug: str, launched: str) -> bool:
    """Return whether a slug's thread is gone and wrote nothing. The answer is yes when four
    things hold: jbus launched the slug; T3 Code lists no thread for the slug, not even a
    settled or archived one; no pull request of the slug is open or merged; and the slug's
    brief has no Result.

    `launched` is the thread of the slug's launch record, or nothing for a slug with none. A
    pass calls `gone` before it launches anything, with the answers that it already has from
    T3 Code and GitHub. A thread launched after jbus got those answers appears in neither.
    """
    if not launched or slug in world.threads or slug in world.settled or slug in world.archived:
        return False
    return (
        slug not in world.open and slug not in world.merged and not last_result(brief_of(run, slug))
    )


def written(result: str) -> work.Written:
    """Return what a Result says, as the facet `Written` has it: nothing, `clean` where it
    leaves nothing and has a `Branch:` line, `leftover` where its `Left:` line names something
    or its `Status:` is not `done`, and `malformed` where one of the three lines is missing."""
    if not result:
        return work.Written.NONE
    short = left(result)
    if short.startswith(("left: ", "status: ")):
        return work.Written.LEFTOVER
    if short or not said_on(result, "Branch").split():
        return work.Written.MALFORMED
    return work.Written.CLEAN


def pull(world: World, slug: str, result: str, said: str) -> work.Pull:
    """Return the slug's pull request as the facet `Pull` has it. `said` is what `jmerge`
    last said of an open one (`merge.step`). A `Branch:` line that ends on an address, with
    neither an open nor a merged pull request under the slug, means that pull request closed."""
    if slug in world.open:
        return work.Pull(merge.step(said) or work.Pull.OTHER)
    if slug in world.merged:
        return work.Pull.MERGED
    words = said_on(result, "Branch").split()
    return work.Pull.CLOSED if words and words[-1].startswith("http") else work.Pull.NONE


def thread(found: dict[str, Any] | None, live: str) -> work.Thread | None:
    """Return a thread as the facet `Thread` has it, from its status and its liveness
    (`jbus.live`). A turn whose liveness is not known is `quiet`, and jbus never calls it
    moving. A status jbus does not know gives no facet at all: None."""
    if found is None:
        return work.Thread.NONE
    if found.get("archived"):
        return work.Thread.ARCHIVED
    if found.get("settled"):
        return work.Thread.SETTLED
    status = found.get("status", "")
    if status in STARTING:
        return work.Thread.STARTING
    if status == "waiting":
        return work.Thread.WAITING
    if status == "running":
        return LIVENESS.get(live, work.Thread.QUIET)
    if status in ("completed", "idle"):
        return work.Thread.COMPLETED
    return work.Thread.FAILED if status in (*ENDED, "rolled_back") else None


LIVENESS = {
    "moving": work.Thread.MOVING,
    "quiet": work.Thread.QUIET,
    "hung": work.Thread.HUNG,
    "waiting": work.Thread.WAITING,
}


@dataclass(frozen=True)
class Seen:
    """A `Seen` is what a pass saw besides the world: the threads out (`threads.out`), or None
    where T3 Code did not list them; the slugs whose launched thread is gone with nothing
    written (`gone`); what `jmerge` said of each open pull request by its number; the slugs
    that are merged or done (`final`); and which sources answered."""

    out: list[dict[str, Any]] | None
    gone: frozenset[str]
    said: dict[str, str]
    final: frozenset[str]
    answered: work.Answered = work.Answered.BOTH

    def live(self, thread: str) -> str:
        return next((one["live"] for one in self.out or [] if one["id"] == thread), "")

    def crew(self, slug: str) -> dict[str, Any] | None:
        """Return the one crew thread out for a slug, as it appears in the list of threads out."""
        found = [one for one in self.out or [] if one["role"] == "crew" and one["slug"] == slug]
        return found[0] if len(found) == 1 else None


def row_of(run: Pass, row: dict[str, Any], unmet: list[str]) -> work.Row:
    if not row.get("approved"):
        return work.Row.UNAPPROVED
    brief = queue.brief(run.state, row["slug"])
    if brief is None or not queue.approved_text(row, brief):
        return work.Row.CHANGED
    return work.Row.BEHIND if unmet else work.Row.FREE


def against(brief: str) -> str:
    """The branch a brief's `Pull request:` line opens its pull request against, a train's, or
    empty for the default branch."""
    named = _AGAINST.search(brief.split("\n## ", 1)[0])
    return named["branch"] if named else ""


def unmet(run: Pass, world: World | None, row: dict[str, Any], final: frozenset[str]) -> list[str]:
    """The depends that hold back a row's launch: none for a row that launches stacked on the one
    it waits on (`World.stack_on`)."""
    left = [one for one in row.get("depends", []) if one not in final]
    brief = queue.brief(run.state, row["slug"]) or ""
    return [] if world is not None and world.stack_on(run, left, brief) else left


def final(run: Pass, world: World | None, rows: list[dict[str, Any]]) -> frozenset[str]:
    """Return the slugs that no longer hold back a row that depends on them. Those are the
    slugs that merged, or that ended `done` under the rule that `dispatch` uses to launch.
    With no world, jbus takes them from the rows' own status."""
    if world is None:
        return frozenset(row["slug"] for row in rows if row.get("status") in queue.FINAL)
    merged = set(world.merged) - set(world.open)
    return frozenset(
        merged | {row["slug"] for row in rows if ended(run, world, row["slug"]) == End("done")}
    )


def facts(
    run: Pass, world: World | None, row: dict[str, Any], seen: Seen, launched: str, last: str = ""
) -> tuple[work.Facts, bool]:
    """Return the facts of one row of the queue, and whether its thread is in a status jbus
    does not know. The row's launch record names the thread `launched`, or none. With no
    world, the thread is the one in the list of threads out, and jbus does not know what
    GitHub would say: its facet is `none`, and `judge` passes over every pattern that
    narrows it."""
    slug = row["slug"]
    result = last_result(brief_of(run, slug))
    if world is not None:
        found = world.thread(slug)
        said = thread(found, seen.live((found or {}).get("threadId", "")))
    else:
        found = seen.crew(slug)
        said = thread(found, str((found or {}).get("live", "")))
    answered = seen.answered
    if world is not None and found is None and launched:
        if slug in world.missing:
            said = work.Thread.MISSING
        elif slug in world.unasked:
            said, answered = work.Thread.STARTING, work.without_t3(answered)
        elif slug not in seen.gone:
            said = work.Thread.STARTING
    number = str((world.open.get(slug) or {}).get("number", "")) if world else ""
    made = work.Facts(
        row=row_of(run, row, unmet(run, world, row, seen.final)),
        thread=said or work.Thread.NONE,
        seen="" if said else str((found or {}).get("status", "")),
        launch=work.Launch.LAUNCHED if launched else work.Launch.NONE,
        written=written(result),
        pull=pull(world, slug, result, seen.said.get(number, "")) if world else work.Pull.NONE,
        question=work.Question.OPEN if slug in run.gated else work.Question.NONE,
        answered=answered,
        last=last,
    )
    return made, said is None


class Judging:
    """A `Judging` holds the state of each row of a pass, judged once, when a caller first
    asks for it. A row added to the queue after the pass read it is judged as the others are.
    A running thread whose liveness the pass could not read, since T3 Code did not list the
    threads out, is `quiet` and not confirmed."""

    def __init__(self, run: Pass, world: World | None, seen: Seen, last: dict[str, str]):
        self.run, self.world, self.seen, self.last = run, world, seen, last
        self.states: dict[str, work.State] = {}

    def of(self, row: dict[str, Any], launched: str) -> work.State:
        slug = row["slug"]
        if slug not in self.states:
            made, strange = facts(
                self.run, self.world, row, self.seen, launched, self.last.get(slug, "")
            )
            asked = made.question == work.Question.OPEN
            state = work.unforeseen(made) if strange and not asked else work.judge(made)
            found = self.world.thread(slug) if self.world is not None else None
            if self.seen.out is None and (found or {}).get("status") == "running":
                state = replace(state, confirmed=False)
            self.states[slug] = state
        return self.states[slug]


OVER = (work.Thread.COMPLETED, work.Thread.FAILED)


def owed(run: Pass, role: str, slug: str) -> work.Written:
    """Return what a thread that belongs to no row has written of the output that its role
    owes.
    A scout owes its last Report, which jbus reads as it reads a Result. A reviewer owes a
    Review with a verdict in the brief. A home or any other thread owes nothing, so it has
    always written all it owes."""
    if role == "scout":
        text = _read(run.home / "scouts" / f"{slug}.md")
        reports = [body for head, body in sections(text, gates_inside=True) if head == "## Report"]
        if not reports:
            return work.Written.NONE
        status = said_on(reports[-1], "Status")
        if not status:
            return work.Written.MALFORMED
        return work.Written.CLEAN if status == "done" else work.Written.LEFTOVER
    if role == "reviewer":
        text = _read(run.home / "tasks" / f"{slug}.md")
        verdicts = [
            said_on(body, "Verdict") for head, body in sections(text) if head == "## Review"
        ]
        return work.Written.CLEAN if any(verdicts) else work.Written.NONE
    if role == "crew":
        return written(last_result(brief_of(run, slug)))
    return work.Written.CLEAN


def _read(path: Any) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def thread_facts(run: Pass, one: dict[str, Any], answered: work.Answered, last: str) -> work.Facts:
    """Return the facts of a thread out that belongs to no row, one of `threads.out`. The
    thread counts as its own launch. What it wrote counts once its turn is over, since a turn
    under way still writes."""
    said = thread(one, str(one.get("live", "")))
    slug = str(one.get("slug") or "")
    return work.Facts(
        row=work.Row.REMOVED if slug and slug in run.removed else work.Row.ABSENT,
        thread=said or work.Thread.NONE,
        seen="" if said else str(one.get("status", "")),
        launch=work.Launch.LAUNCHED,
        written=owed(run, str(one.get("role", "")), slug) if said in OVER else work.Written.NONE,
        pull=work.Pull.NONE,
        question=work.Question.NONE,
        answered=answered,
        last=last,
    )


def judged(
    run: Pass, out: list[dict[str, Any]] | None, rows: set[str], answered: work.Answered
) -> list[dict[str, Any]]:
    """Return the `work.json` lines of every thread out that belongs to no row: a scout, a
    reviewer, a home, another, and a crew whose slug has no row. With no list of them, return
    the last pass's lines, not confirmed."""
    kept = work.read(run.state) or {"work": []}
    if out is None:
        return [
            {**one, "confirmed": False}
            for one in kept["work"]
            if isinstance(one, dict) and one.get("kind") == "thread"
        ]
    last = work.last(run.state)
    found = []
    for one in out:
        if one.get("role") == "crew" and one.get("slug") in rows:
            continue
        made = thread_facts(run, one, answered, last.get(one["id"], ""))
        state = work.unforeseen(made) if made.seen else work.judge(made)
        role = str(one.get("role") or "other")
        about = {"key": one["id"], "kind": "thread", "slug": one.get("slug") or ""}
        about |= {"thread": one["id"], "role": role, "title": one.get("title", "")}
        found.append(work.entry(state, work.holder(state, role=role), **about))
    return found


def unwritten(
    run: Pass, thread: dict[str, Any] | None, state: work.State, waiting: set[str]
) -> str:
    """Return why a `stale` row has nobody on it, or nothing while its crew is still on it.

    A thread that ended or hung with nothing written is `stale` for as long as jbus keeps
    resuming the row's crew (`threads.resume`). Once `UNWRITTEN_MINUTES` have passed since the
    thread last wrote, or at once for a hung turn, the row is a leftover, and jbus sends the row
    to the slug's home to close (`leftover`). The row stays `left` until the home ends it, the
    thread goes on, or the row leaves the queue.

    If a thread ended its turn to wait on a test slot, so that it is one of `waiting`, its row
    is never `left`, however long the thread is quiet: jbus wakes the thread when a slot is
    free (`slotwait`). After that, the rule above counts again from the thread's last write.
    """
    if state.value not in ("lost", "hung") or state.facts.written != work.Written.NONE:
        return ""
    if state.value == "hung":
        return "its turn hung with nothing written"
    if thread is None:
        return "its thread is gone and nothing is written"
    if waiters.thread_id(str(thread.get("threadId", ""))) in waiting:
        return ""
    quiet = (run.now - when(thread["updatedAt"])).total_seconds() / 60
    if quiet < UNWRITTEN_MINUTES:
        return ""
    return f"its thread {thread['status']} with nothing written"


def status(
    run: Pass, world: World, slug: str, state: work.State, launched: str = ""
) -> dict[str, str]:
    """Return a row's derived columns. The row's status is the projection of the row's state
    (`work.status`). `why` holds the reason that comes with the status itself: what a Result
    leaves.

    `launched` is the thread id of the slug's launch record.
    """
    found = world.thread(slug)
    pull = world.open.get(slug) or world.merged.get(slug)
    word = work.status(state)
    reason = ""
    if word == "stale" and (why := unwritten(run, found, state, world.waiting)):
        word, reason = "left", why
    elif word in ("merged", "left", "done"):
        result = last_result(brief_of(run, slug))
        reason = (left(result) if word == "merged" else unfinished(result)) if result else ""
    return {
        "thread": (found or {}).get("threadId") or launched,
        "pr": f"#{pull['number']}" if pull else "",
        "checks": checks(pull) if slug in world.open else "",
        "status": word,
        "why": reason,
    }


def waits(pulls: Said) -> Waits:
    """Return what `jmerge` waits for or holds, by the pull request's number.

    `pulls` is what `jmerge` said in this pass (`merge.shown`), also where the home merges.
    """
    found = (parse(line) for line in pulls if isinstance(line, str))
    by_number = {
        str(line.number): f"{line.word}: {line.reason}"
        for line in found
        if line and line.word in ("wait", "hold") and line.reason
    }
    return Waits(by_number, failed=pulls.failed)


def unread(run: Pass, read: bool) -> str:
    """Return why `dispatch` read no row of the queue this pass, or nothing if it `read` them.

    `UNREAD` means the pass did not get to the launches: a project raised, or T3 Code,
    GitHub or the queue gave no answer, so nothing could launch.
    """
    if read:
        return ""
    if not run.config.dispatch:
        return OFF
    return STOP if run.config.stop_path.exists() else UNREAD


def why(run: Pass, row: dict[str, Any], found: dict[str, str], waits: Waits, unread: str) -> str:
    """Return why a row waits, or nothing. `found` is its derived columns, as `status` gave them.

    A row with a pull request waits for what `jmerge` says of it. A row that was not launched waits
    for what `dispatch` recorded (`Pass.reasons`), or for its approval. Where `dispatch` read no
    row, it recorded nothing, and an approved row waits for what is `unread`: dispatch that is off,
    or the stop file. A pass that is `UNREAD` says nothing of the row, so the row's stored reason
    stays, unless the row has got its approval since. The same holds for a pass in which `jmerge`
    failed and printed no line for the pull request. A row that ended, or that merged with work left
    for after it, takes its reason from `status`.
    """
    if found.get("why"):
        return found["why"]
    if found["status"] == "pr":
        said = waits.said.get(found["pr"].removeprefix("#"))
        if said is None and waits.failed and row.get("status") == "pr":
            return row.get("why", "")
        return said or ""
    if found["status"] not in ("queued", "gate"):
        return ""
    match run.reasons.get(row["slug"]):
        case Changed(sha):
            return f"brief changed after approval, now {sha}"
        case Depends(slugs):
            return f"depends on {', '.join(slugs)}"
        case Slot():
            return "no slot"
    if found["status"] == "gate":
        return GATED
    if not row.get("approved"):
        return "not approved"
    if unread != UNREAD:
        return unread
    kept = row.get("why", "") if row.get("status") in ("queued", "gate") else ""
    return "" if kept == "not approved" else kept


def watch(run: Pass, world: World, rows: list[dict[str, Any]]) -> None:
    """Send a line for each thing a home would have noticed, and a gate for what no rule covers.

    The thread of a queue row that completed with a Result is no gate: its row says how it
    ended (`ended`).
    """
    queued = {row["slug"] for row in rows}
    for slug, live in world.threads.items():
        if len(live) > 1:
            run.gate(
                slug, f"{len(live)} threads for one slug", "\n".join(t["threadId"] for t in live)
            )
        elif live[0]["status"] not in KNOWN:
            run.gate(slug, f"thread state {live[0]['status']} jbus does not know")
    for branch, pull in world.open.items():
        if not brief_of(run, branch):
            run.gate(branch, f"pull request #{pull['number']} has no brief", pull.get("url", ""))
    for slug, live in world.threads.items():
        if slug in run.gated:
            continue
        thread, line = live[0], _stale(run, slug, live[0])
        if line:
            fact = thread["updatedAt"] if thread["status"] == "waiting" else thread["status"]
            run.find(slug, "stale", line, key=f"{thread['threadId']} {fact}")
        elif thread["status"] == "completed" and slug not in {*world.open, *world.merged, *queued}:
            run.gate(slug, "thread completed with a Result and no pull request")
    for slug, thread in world.archived.items():
        taken = slug in world.open or slug in world.merged
        if slug in queued and slug not in run.gated and not taken:
            if not last_result(brief_of(run, slug)):
                line = f"stale {slug}: thread {thread['threadId']} is archived with no Result"
                run.find(slug, "stale", line, key=f"{thread['threadId']} archived")
    for slug, pull in world.merged.items():
        if slug in run.gated or not brief_of(run, slug):
            continue
        commit = (pull.get("mergeCommit") or {}).get("oid", "")
        line = f"merged {slug} #{pull['number']} {commit[:12]}"
        result = last_result(brief_of(run, slug))
        run.find(slug, "merged", line, result, key=f"#{pull['number']}", past=True)
    _retro(run, world, rows)
    for nightly in NIGHTLIES:
        _nightly_red(run, nightly)


def _api(run: Pass, path: str) -> Any:
    asked = run.run("gh", "api", path)
    try:
        return json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        return None


def _check(run: Pass, known: dict[str, str], sha: str, again: bool = False) -> str:
    """Return whether the check runs of a commit on main passed. `_check` asks GitHub once
    for a final answer, and keeps it in `known`.

    A cancelled run is no failed check: a later run displaced it or someone stopped it, and a push
    run cancelled before it had a job leaves the commit with no check run at all. With `again`,
    `_check` reruns a cancelled run that is at its first attempt, and the commit is `pending` until
    the rerun ends. GitHub's `run_attempt` says whether the run ran again: `cancelled` is a later
    attempt that was cancelled too, and `refused` a run that GitHub did not start again.

    A commit whose every failed check run has a job that ran no step, and no check run of which
    passed, is `NO_JOB`, not `failed`: GitHub started no job, as on a spent Actions limit or a
    failed payment, so no code was judged. A run that passed shows that GitHub starts jobs, so a
    run beside it that started none is a failed check. A check run whose job GitHub does not give
    counts as one that ran, as in `never_started`.
    """
    if sha in known:
        return known[sha]
    said = _api(run, f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs")
    runs = (said or {}).get("check_runs") or []
    ended = [r.get("conclusion") for r in runs if r.get("status") == "completed"]
    if len(ended) < len(runs):
        return "pending"
    failed = [r for r in runs if r.get("conclusion") not in NOT_RED]
    unrun = (job(run, "{owner}/{repo}", str(r.get("id"))).get("steps") == [] for r in failed)
    if failed and "success" not in ended and all(unrun):
        known[sha] = NO_JOB
        return NO_JOB
    bad = bool(failed)
    if bad or (runs and "cancelled" not in ended):
        known[sha] = "failed" if bad else "green"
        return known[sha]
    said = _api(run, f"repos/{{owner}}/{{repo}}/actions/runs?head_sha={sha}&event=push")
    pushed = (said or {}).get("workflow_runs") or []
    stopped = [r for r in pushed if r.get("conclusion") == "cancelled"]
    if not stopped or any(r.get("status") != "completed" for r in pushed):
        return "pending"
    if any((r.get("run_attempt") or 1) > 1 for r in stopped):
        known[sha] = "cancelled"
    elif again and any(
        run.run("gh", "run", "rerun", str(r["id"])).returncode != 0 for r in stopped
    ):
        known[sha] = "refused"
    return known.get(sha, "pending")


@dataclass(frozen=True)
class Failed:
    """The tests a job's log reports as failed: `tests` their ids, in order, and `count` how many
    failed, more than the ids where the log counts failures it does not name."""

    tests: tuple[str, ...] = ()
    count: int = 0


def failed_in(log: str) -> Failed:
    """Return the failed tests a job's log reports. A step that prints a warning `<n> tests
    failed` and then a `FAILED <id>` line for each (macos-nightly.yml's "failed tests") names them
    whole. Where it names none, the ids are pytest's summary lines. The count is the largest of
    the step's, the ids' and pytest's last line's failed plus errors."""
    log = _ESCAPE.sub("", log)
    steps = list(_STEP_COUNT.finditer(log))
    tests = _STEP_TEST.findall(log, steps[-1].end()) if steps else []
    count = int(steps[-1][1]) if steps else 0
    tests = tests or _FAILED_TEST.findall(log)
    summaries = _SUMMARY.findall(log)
    if summaries:
        count = max(count, sum(int(n) for n in _SUMMARY_COUNT.findall(summaries[-1])))
    named = tuple(dict.fromkeys(tests))
    return Failed(named, max(count, len(named)))


def job_log(run: Pass, repo: str, job: object) -> str | None:
    """Return a job's log, or None where GitHub did not give it. GitHub's log has escape
    sequences in it, which gh 2.102 gives only when asked to."""
    path = f"repos/{repo}/actions/jobs/{job}/logs"
    log = run.run("gh", "api", path, "--allow-escape-sequences")
    return log.stdout if log.returncode == 0 else None


def _log_failed(run: Pass, job: object) -> Failed | None:
    """Return the tests that a job's log reports as failed, or None where jbus could not read
    the log."""
    log = job_log(run, "{owner}/{repo}", job)
    return None if log is None else failed_in(log)


def _failed_tests(run: Pass, job: object) -> list[str]:
    return list((_log_failed(run, job) or Failed()).tests)


def tests_said(jobs: list[tuple[str, str, Failed]]) -> str:
    """Return how many tests the failed jobs report, and how many of them they name."""
    count = sum(failed.count for _, _, failed in jobs)
    named = sum(len(failed.tests) for _, _, failed in jobs)
    tests = f"{count} test{'' if count == 1 else 's'}"
    if count == named:
        return f"{tests} named"
    return f"{tests} failed, {named or 'none'} named"


def red_brief(
    slug: str,
    sha: str,
    jobs: list[tuple[str, str, list[str]]],
    red: list[dict],
    changed: list[str],
) -> str:
    """Return the brief for the fix of a red main at `sha`, in the shape of
    `features/jbriefs/templates/brief.md`. `jobs` is each failed check run's name, URL and
    failed tests. `red` is the commits from `sha` down to the last green one, not including
    it. `changed` is the files those commits changed. `slug` is the briefed merge before the
    red, or empty where none came in the day before it: the fix is a follow-up of that row, and
    a pass approves it on the row's go (`queue.follow_ups`)."""
    tests = [test for _, _, failed in jobs for test in failed]
    files = list(dict.fromkeys([*changed, *(test.split("::")[0] for test in tests)]))
    where = (
        ", ".join(f"`{file}`" for file in files)
        or "`.` (the whole repo: the merges since the last green changed files nobody listed)"
    )
    read = [
        f"- the job `{name}`, {url or 'with no URL'}: "
        + (", ".join(f"`{test}`" for test in failed) or "its log names no failed test, read it")
        for name, url, failed in jobs
    ]
    read += [
        f"- the merge {commit['sha'][:12]} {commit['commit']['message'].splitlines()[0]}"
        for commit in red
    ]
    return "\n".join(
        [
            f"# {mainjson.FIX}{sha[:12]}: main's check failed at {sha[:12]}, "
            + (f"after {slug} merged" if slug else "with no briefed merge in the day before it"),
            f'Task: "main check failed at {sha[:12]}, {len(red)} merges since the last green" '
            + (f"(jbus, the retro of {slug})" if slug else "(jbus, the retro of main's tip)"),
            "Done when:",
            "- each failed test named under Read passes on main, and the failed job passes at "
            "the commit that merges the fix",
            "- the Result names the cause: the merge that broke main, or a flake with its evidence",
            "Proves it: CI's check on main passes at the commit that merges the fix",
            "Size: S",
            f"Where: {where}",
            "Do not touch: .github/workflows/, the ruleset",
            "Decisions: none, jbus filed this from a red main and the user has not seen it",
            "Design: none, a fix to what the failed run names",
            "Pull request: open one when done",
            "Review: review",
            "Playbook: bug-fix",
            *([f"Follows: {slug}"] if slug else []),
            "Read:",
            *read,
            "",
        ]
    )


def _changed(run: Pass, red: list[dict]) -> list[str]:
    """Return the files the commits changed, as GitHub lists them for each."""
    files = []
    for commit in red:
        said = _api(run, f"repos/{{owner}}/{{repo}}/commits/{commit['sha']}")
        listed = said.get("files") if isinstance(said, dict) else None
        files += [one.get("filename", "") for one in listed or []]
    return [file for file in dict.fromkeys(files) if file]


def _file(run: Pass, slug: str, sha: str, red: list[dict]) -> None:
    """Write the brief for the fix of a red main to the home's `tasks/`, and queue it with no
    approval. Where a briefed merge turned main red, the brief follows that row and a pass
    approves it on the row's go; otherwise the user approves it like any other row. Its priority
    is one above the first row of the queue, so once approved it is the next launch there.
    `_file` writes the brief whenever the queue has no row for it. So if a pass stopped before
    it added the row, the next pass files the brief again. If the queue refuses the brief, that
    is a condition."""
    name = f"{mainjson.FIX}{sha[:12]}"
    if name in run.removed or queue.fresh(run.state, name) is not None:
        return
    said = _api(run, f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs")
    jobs = [
        (r.get("name") or "?", r.get("html_url") or "", _failed_tests(run, r.get("id")))
        for r in (said if isinstance(said, dict) else {}).get("check_runs") or []
        if r.get("status") == "completed" and r.get("conclusion") not in NOT_RED
    ]
    text = red_brief(slug, sha, jobs, red, _changed(run, red))
    (run.home / "tasks").mkdir(parents=True, exist_ok=True)
    (run.home / "tasks" / f"{name}.md").write_text(text)
    try:
        top = min((row.get("priority", 0) for row in queue.load(run.state)), default=1) - 1
        queue.add(run.state, name, top, [], text)
    except (Refused, queue.Unparsable) as refused:
        run.condition(name, f"its brief was not queued: {refused}")


def _default_branch(run: Pass) -> str:
    default = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    return default.stdout.strip().removeprefix("origin/") or "main"


@dataclass(frozen=True)
class Nightly:
    """A workflow that no required check runs, whose red run on the default branch, or of a
    release, jbus files a fix brief for. Its run for a pull request, or by hand on another branch,
    files nothing (`_nightly_red`).

    `file` is the workflow's file, `prefix` the slug's start before the day, `seen` the file in
    the project's state that keeps the runs jbus has seen, and `run` how the run is named. The
    rest are the brief's own lines: `failed` what failed, `where` its `Where:` when the log
    names no test, `done` and `proves` how the fix is shown, `pull` its `Pull request:`, and
    `home` the scoped home it is filed under, or an empty string for the root home. `title`,
    where it is set, is the title of the runs jbus files for: a run of the workflow with any
    other title checked out another ref, and is that ref's concern. `branch`, where it is set, is
    the integration branch those runs check out: until one run of it there has passed, its red
    runs are that branch's known work, which its home's plan holds, and file no row.
    """

    file: str
    prefix: str
    seen: str
    run: str
    failed: str
    where: str
    done: str
    proves: str
    pull: str = "open one when done"
    home: str = ""
    title: str = ""
    branch: str = ""


BROWSER = Nightly(
    file="browser.yml",
    prefix="browser-red-",
    seen="browser-runs.json",
    run="the browser run",
    failed="the browser tests failed",
    where="the tests marked `browser`",
    done="each failed test named under Read passes under `make check-browser`",
    proves="`make check-browser` passes, and so does a manual run of browser.yml "
    "(workflow_dispatch) on the fix's branch",
)
MACOS = Nightly(
    file="macos-nightly.yml",
    prefix="macos-red-",
    seen="macos-nightly-runs.json",
    run="the macOS nightly run",
    failed="the macOS suite failed",
    where="the tests the macOS nightly runs on main, under `features/` and `testing/`",
    done="each failed test named under Read passes on macOS, in a manual run of "
    "macos-nightly.yml with `ref` set to the fix's branch",
    proves="`make check-fast BASE=origin/main` passes, and so does a manual run of "
    "macos-nightly.yml (`gh workflow run macos-nightly.yml -f ref=<the fix's branch>`)",
    pull="open one when done",
    home="macos",
    title="macos-nightly on main",
    branch="main",
)
NIGHTLIES = (BROWSER, MACOS)
"""The nightly workflows, each with its own rule for a red run (`_nightly_red`)."""


def nightly_red_brief(
    nightly: Nightly,
    name: str,
    day: str,
    one: dict[str, Any],
    jobs: list[tuple[str, str, Failed]],
) -> str:
    """Return the brief for the fix of a red run of a nightly workflow, in the shape of
    `features/jbriefs/templates/brief.md`. `one` is the run as GitHub lists it, and `jobs`
    is each failed job's name, URL and failed tests."""
    tests = [test for _, _, failed in jobs for test in failed.tests]
    files = list(dict.fromkeys(test.split("::")[0] for test in tests))
    where = ", ".join(f"`{file}`" for file in files) or nightly.where
    number, event = one.get("id"), one.get("event") or "an event"
    read = [
        f"- the job `{job}`, {url or 'with no URL'}: "
        + (
            ", ".join(f"`{test}`" for test in failed.tests)
            or "its log names no failed test, read it"
        )
        for job, url, failed in jobs
    ]
    read += [f"- the run {one.get('html_url') or number}, from {event}, at {one.get('head_sha')}"]
    return "\n".join(
        [
            f"# {name}: {nightly.failed} on {day}",
            f'Task: "{nightly.run} {number} failed on {day}, {tests_said(jobs)}" '
            f"(jbus, from {nightly.file})",
            "Done when:",
            f"- {nightly.done}",
            "- the Result names the cause: the merge that broke it, or a flake with its evidence",
            f"Proves it: {nightly.proves}",
            "Size: S",
            f"Where: {where}",
            "Do not touch: .github/workflows/, the ruleset",
            "Decisions: none, jbus filed this from a red nightly run and the user has not seen it",
            "Design: none, a fix to what the failed run names",
            f"Pull request: {nightly.pull}",
            "Review: review",
            "Playbook: bug-fix",
            *([f"Home: {nightly.home}"] if nightly.home else []),
            "Read:",
            *read,
            "",
        ]
    )


def _nightly_name(nightly: Nightly, day: str, taken: set[str]) -> str:
    """Return `<prefix><day>`, with `-2`, `-3` for each further red run of the same day."""
    name, more = f"{nightly.prefix}{day}", 1
    while name in taken:
        more += 1
        name = f"{nightly.prefix}{day}-{more}"
    return name


def _nightly_red(run: Pass, nightly: Nightly) -> None:
    """File the brief for the fix of a red run of a nightly workflow, and queue the brief
    unapproved, once per run. jbus records each run that it has seen in the nightly's `seen`
    file, so it files no brief again for a run whose row was removed. On a project's first
    pass, jbus only records the runs that it sees.

    A red run is one that failed or timed out, and ended within `NIGHTLY_WINDOW`. Where GitHub
    would not give the run's jobs, or a failed job's log, the next pass asks about the run
    again. Once the run ended `NIGHTLY_GRACE` ago, jbus files the brief without the test
    names. jbus files nothing for a pull request's run, nor for a manual run on a branch other
    than the default, and marks it seen: that run is the pull request's or the branch's concern,
    and a red one is no red on main. A release's run, a pushed tag or a published release, is
    filed. A run of macos-nightly.yml is on the default branch whatever it checks
    out, so a nightly with a `title` files only for the runs that carry it.

    A nightly with a `branch` files a row only for a red run after a run that passed: jbus keeps
    each run that passed as `GREEN` in `seen`, since GitHub lists only the last 20. A red run
    before any is one quiet line, under the workflow's name, and no row asks the user anything.
    """
    said = _api(
        run,
        f"repos/{{owner}}/{{repo}}/actions/workflows/{nightly.file}/runs"
        "?status=completed&per_page=20",
    )
    runs = said.get("workflow_runs") if isinstance(said, dict) else None
    if not isinstance(runs, list):
        return
    seen: dict[str, str] = read_json(run.state / nightly.seen, {})
    default = _default_branch(run)
    green = GREEN in seen.values()
    for one in sorted(runs, key=lambda r: r.get("created_at") or ""):
        number = str(one.get("id"))
        ended = when(one.get("updated_at") or one["created_at"])
        stale = run.now - ended > NIGHTLY_WINDOW
        event, off = one.get("event"), one.get("head_branch") != default
        if event == "pull_request" or (off and event not in NIGHTLY_RELEASE):
            seen.setdefault(number, "")
            continue
        if nightly.title and one.get("display_title") != nightly.title:
            continue
        if nightly.branch and one.get("conclusion") == "success":
            green, seen[number] = True, GREEN
            continue
        if number in seen or one.get("conclusion") not in NIGHTLY_RED or stale:
            continue
        day = run.user.day(when(one["created_at"]))
        if nightly.branch and not green:
            line = (
                f"retro {nightly.file.removesuffix('.yml')}: {nightly.run} {number} failed on "
                f"{day}, and no run of it on {nightly.branch} has passed yet, so no row is filed"
            )
            run.find(nightly.file.removesuffix(".yml"), "retro", line, key=number, past=True)
            seen[number] = ""
            continue
        if run.first:
            seen[number] = ""
            continue
        name = _nightly_name(nightly, day, {*seen.values(), *run.removed})
        if queue.fresh(run.state, name) is None:
            asked = _api(run, f"repos/{{owner}}/{{repo}}/actions/runs/{number}/jobs?per_page=100")
            if not isinstance(asked, dict):
                if run.now - ended < NIGHTLY_GRACE:
                    continue
                asked = {}
            red = [
                j
                for j in asked.get("jobs") or []
                if j.get("status") == "completed" and j.get("conclusion") not in NOT_RED
            ]
            logs = [_log_failed(run, j.get("id")) for j in red]
            if None in logs and run.now - ended < NIGHTLY_GRACE:
                continue
            jobs = [
                (j.get("name") or "?", j.get("html_url") or "", failed or Failed())
                for j, failed in zip(red, logs, strict=True)
            ]
            text = nightly_red_brief(nightly, name, day, one, jobs)
            (run.home / "tasks").mkdir(parents=True, exist_ok=True)
            (run.home / "tasks" / f"{name}.md").write_text(text)
            try:
                queue.add(run.state, name, 0, [], text)
            except Refused as refused:
                run.condition(name, f"its brief was not queued: {refused}")
                continue
            line = f"retro {name}: {nightly.run} {number} failed on {day}, {tests_said(jobs)}"
            run.find(name, "retro", line, key=f"{nightly.file} {number}", past=True)
        seen[number] = name
        write_json(run.state / nightly.seen, seen)
    write_json(run.state / nightly.seen, seen)


def _withdraw(run: Pass, fixes: list[dict[str, Any]], green: str, branch: str = "main") -> None:
    """Withdraw each fix row filed for a red (its slug ends in the red's commit) that the tip of
    `branch`, main or a train, `green`, has since passed: a fix for a problem already gone is no
    decision. A row that never launched is taken out (`queue.withdraw`), with why in its record.
    A row that launched is left to its crew and its pull request, since its fix may still be
    needed for a test that turned green by chance, and the home hears of it once. The line that
    says a row is withdrawn is sent once the row is out, and a withdrawn row is never one of
    `fixes` again. A row filed for `green` itself, whose check passed on a rerun, is left as it
    is, and the home hears of that once too. A row with a launch record is left for the pass that
    reads T3 Code's answer. It imports `dispatch` here, since `dispatch` imports this module."""
    from jbus import dispatch

    for row in fixes:
        name = row["slug"]
        if green.startswith(name.rsplit("-", 1)[-1]):
            line = f"retro {name}: {branch} is green again at {green[:12]}, and its row is left"
            line += " as it is"
            run.find(name, "retro", line, key=f"green {name}", past=True)
            continue
        if row.get("thread") or row.get("status") not in queue.UNLAUNCHED:
            line = (
                f"retro {name}: {branch} is green again at {green[:12]}, and its row launched, so "
                "it is left to its crew and its pull request"
            )
            run.find(name, "retro", line, key=f"launched {name}", past=True)
            continue
        if dispatch.records(run, name):
            continue
        why = f"{branch} is green at {green[:12]}, a later commit than the red it was filed for"
        try:
            said = queue.withdraw(run.state, name, why, run.user.stamp(run.now))
        except (Refused, queue.Unparsable) as refused:
            run.condition(name, f"its row was not withdrawn: {refused}")
            continue
        line = f"retro {name}: {branch} is green again at {green[:12]}, and its row is withdrawn"
        run.box.send(name, "retro", line)
        run.box.send(name, "queue", f"queue {run.project.name}: {said}", queue.render([row]))
        run.say(said)


def _retro(run: Pass, world: World, rows: list[dict[str, Any]]) -> None:
    """Report a red main within a day of a merge, and a revert of one. Both lines name the
    merged slug. A red tip of main with no briefed merge in the day before it is reported too,
    under the name of its fix row: `jmerge` holds every merge on it all the same.

    A main whose run was cancelled is not red: `_retro` asks for its run again, and reports
    only a second cancelled run, or a run GitHub would not start again. It reports a red main
    once for each commit. `_retro` files and queues a brief for the fix once, and only for
    main's tip as this pass reads it (`_file`). A red commit that a later commit superseded
    is no longer main, so there is nothing to fix. Once main's tip is green at a later commit
    than the one a fix row was filed for, the red is gone: `_withdraw` takes out a row that never
    launched, and reports once a row that did, which its crew and pull request keep. With no
    briefed merge and no open fix row, `_retro` asks GitHub nothing until `main.json` keeps a
    red tip.
    """
    slugs = sorted(
        (s for s in world.merged if brief_of(run, s) and s not in run.gated),
        key=lambda s: world.merged[s]["mergedAt"],
    )
    fixes = [
        row for row in rows if mainjson.fix_of(row["slug"]) and row.get("status") not in queue.FINAL
    ]
    if not slugs and not fixes and not mainjson.read(run.state).red:
        return
    merges = [world.merged[slug] for slug in slugs]
    slug_of = {pull["number"]: slug for slug, pull in world.merged.items()}
    branch = _default_branch(run)
    commits = _api(run, f"repos/{{owner}}/{{repo}}/commits?sha={branch}&per_page=50")
    if not isinstance(commits, list):
        return
    known: dict[str, str] = read_json(run.state / "checks.json", {})
    tip = commits[0]["sha"] if commits else ""
    if fixes and _check(run, known, tip) == "green":
        _withdraw(run, fixes, tip)
    by_commit = {(p.get("mergeCommit") or {}).get("oid"): p for p in merges}
    for place, commit in enumerate(commits):
        sha, message = commit["sha"], commit["commit"]["message"]
        for pull in merges:
            merge = (pull.get("mergeCommit") or {}).get("oid") or ""
            named = bool(merge) and (merge in message or merge[:12] in message)
            if sha != merge and (named or f'Revert "{pull["title"]}' in message):
                slug = slug_of[pull["number"]]
                line = f"retro {slug}: reverted by {sha[:12]}"
                run.find(slug, "retro", line, key=f"revert {sha}", past=True)
        date = when(commit["commit"]["committer"]["date"])
        before = [p for p in merges if timedelta(0) <= date - when(p["mergedAt"]) <= RETRO]
        pull = by_commit.get(sha) or (before[-1] if before else None)
        if pull is None or run.now - date > RETRO:
            pull = None
            if place != 0:
                continue
        slug = slug_of[pull["number"]] if pull else ""
        answer = _check(run, known, sha, again=bool(slug))
        if slug and answer in ("cancelled", "refused"):
            twice = f"main check cancelled twice at {sha[:12]}"
            unasked = f"main check cancelled at {sha[:12]}, and GitHub did not run it again"
            line = f"retro {slug}: {twice if answer == 'cancelled' else unasked}"
            run.find(slug, "retro", line, key=f"cancelled {sha}", past=True)
        if answer != "failed":
            continue
        since = 1
        for older in commits[place + 1 : place + 20]:
            if _check(run, known, older["sha"]) == "green":
                break
            since += 1
        owner = slug or f"{mainjson.FIX}{sha[:12]}"
        line = (
            f"retro {owner}: main check failed at {sha[:12]}, {since} merges since the last green"
        )
        line += "" if slug else ", and no briefed merge came in the day before it"
        run.find(owner, "retro", line, key=f"red {sha}", past=True)
        if place == 0 and not run.first and slug not in run.removed:
            _file(run, slug, sha, commits[place : place + since])
    write_json(run.state / "checks.json", known)


STEPS = (
    verbs.Step(
        "tellers",
        40,
        "watch.watch",
        lambda half: watch(half.run, half.seen.world, half.rows or []),
        ("client", "world"),
    ),
)
