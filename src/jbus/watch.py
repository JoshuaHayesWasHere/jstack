"""What is out, read from T3 Code and GitHub, and the one line each finding is.

`look` asks once a pass: the project's crewmate threads, its open pull requests and the
ones merged lately. The threads of a slug that was removed from the queue are counted and
then left out, so none is found stale or told to carry on. Its pull requests stay. What
`look` answers keeps how many crews are out when only GitHub was silent: the count is one
for the machine, and `jbus poll` adds it up over every project. `watch`
sends a line for what a home would have noticed: a merge, a thread that ran past its
timebox, waits on a request, or ended with no Result, a main branch whose check failed
after a merge, a red run of the browser workflow, and a revert. It names no cause and changes
nothing. What no rule covers is a gate. `status` is the table's derived column for a slug,
and `why` is the reason its row waits: the line `jmerge` has for its pull request, what
stopped its launch, or what its Result leaves.

A pull request belongs to the slug whose brief names it, on the `Branch:` line of a Result,
which is how `jmerge` ties the two (`tied`). The name of its branch says whose it is only
where no brief names it.

A row's state is judged once a pass, from its `facts` (`work.judge`), and the facts of a
thread out that is no row's are `thread_facts`. A row's status, one of `queue.STATUSES`,
is the projection of its state (`work.status`): `gate`, `pr`, `merged`, `done`, `left`,
`launched`, `running`, `waiting`, `stale`, `failed` or `queued`. Its `why` is what a Result
leaves, for a row that merged, ended or left something. A row stale with nothing written,
its thread ended or hung, is `left` once its crew had `UNWRITTEN_MINUTES` to be carried on
(`unwritten`), and its `why` says so: its home closes it (`leftover`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from jbus import Refused, mainstate, merge, queue, read_json, verbs, work, write_json
from jbus.merge import Said, parse
from jbus.mirror import field as said_on
from jbus.mirror import last_result, sections
from jbus.t3 import Client, T3Error
from jbus.wake import Changed, Depends, Pass, Slot, cut
from jgauge import slot, waiters
from jmerge import checks as reading
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
BROWSER = "browser.yml"
BROWSER_RED = ("failure", "timed_out")
BROWSER_WINDOW = timedelta(days=3)
BROWSER_GRACE = timedelta(hours=1)
_FAILED_TEST = re.compile(r"\b(?:FAILED|ERROR) (\S+::\S+)")
_TIMEBOX = re.compile(r"^TIMEBOX:\s*(\d+(?:\.\d+)?)\s*(?:h\b|hours?\b)", re.M)
OPEN = "number,url,title,headRefName,headRefOid,mergeable,statusCheckRollup"
MERGED = "number,url,title,headRefName,mergeCommit,mergedAt"
GATED = "a gate the Chef has"
OFF, STOP, UNREAD = "dispatch is off", "the stop file is there", "not read in this pass"
AFTER_MERGE = "after the merge"
UNRESOLVED = "Could not resolve to a"
WORDS = 100
_PULL = re.compile(r"^(https?://\S+/pull/(\d+))/?$")


@dataclass
class World:
    """One pass's answers. `threads` holds a slug's threads that are not settled.

    T3 Code's list leaves out an archived thread, so `jbus.archived` asks after a launched
    thread the list does not have: `archived` holds those that read back archived, by slug,
    `missing` the slugs whose thread T3 Code has no record of, and `unasked` those it could
    not be asked about. `waiting` holds the threads that wait on a test slot and are not woken
    yet (`jgauge.waiters`), read once a pass.
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

    def live(self) -> int:
        return sum(t["status"] in LIVE for found in self.threads.values() for t in found)


@dataclass(frozen=True)
class Waits:
    """What `jmerge` said of the pull requests that wait, by number: `wait: <its reason>`.

    `failed` is a `jmerge` that did not run to its end here: of a number that `said` does
    not have, the pass knows nothing.
    """

    said: dict[str, str]
    failed: bool = False


@dataclass
class Look:
    """What a pass could ask. `world` is there when T3 Code and GitHub both answered.

    `out` is the crews T3 Code lists as live, known whenever it answered, and `why` is why
    it did not.
    """

    world: World | None = None
    out: int | None = None
    why: str = ""


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
    """T3 Code gave no answer, so nothing is launched or watched. It is recorded once a day."""
    name = run.project.name
    run.say(f"wait {name}: T3 Code could not be asked ({why})")
    day = run.now.date().isoformat()
    run.condition(name, "T3 Code could not be asked", why, key=f"t3 {day}")
    return Look(why=why)


def pulls(run: Pass, state: str, fields: str, *more: str) -> list[dict[str, Any]]:
    """The pull requests `gh` lists. A `gh` that gave none raises `Silent`."""
    asked = run.run("gh", "pr", "list", "--state", state, "--json", fields, *more)
    try:
        pulls = json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        pulls = None
    if not isinstance(pulls, list):
        raise Silent(asked_why(asked))
    return pulls


def _named(run: Pass, url: str) -> list[dict[str, Any]]:
    """The pull request at this address where it merged, as `pulls` gives a list.

    An address GitHub says it cannot resolve is no pull request, and stops no pass: a brief
    may name one. A `gh` that failed any other way gave no answer, and `Silent` is raised.
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
    """The address and the number of the pull request a Result's `Branch:` line ends on."""
    words = said_on(result, "Branch").split()
    found = _PULL.match(words[-1]) if words else None
    return (found[1], found[2]) if found else ("", "")


def tied(run: Pass) -> dict[str, str]:
    """The slug of each pull request a brief names, by its address.

    It is named by a `Branch:` line that ends on its address, in any Result of the brief:
    the first brief that has one is its slug, as it is for `jmerge`.
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
    """Ask T3 Code and GitHub. With either one silent there is no world to act on.

    With GitHub silent the crews out are still known: they count toward `max_running`.

    The list of merged pull requests is the last hundred. A slug the queue names that is
    not in it is asked for by name, and a merge found that way is kept: it stays merged.

    A pull request is kept under the slug whose brief names it (`tied`), and under the name
    of its branch where none does. A slug whose brief names one is asked for by that address.
    """
    if client is None:
        return _silent(run, "no token: run `jbus t3 login`")
    world = World(waiting={one.thread for one in waiters.read(slot.locks_dir()) if not one.woken})
    slug_of = tied(run)
    url_of = {slug: url for url, slug in slug_of.items()}
    try:
        listed = crew_threads(client, run.project.project_id)
    except T3Error as error:
        return _silent(run, str(error))
    for thread in sorted(listed, key=lambda t: t.get("createdAt", "")):
        slug = thread["title"][len(TITLE) :].strip()
        if thread.get("settled"):
            world.settled[slug] = thread
        else:
            world.threads.setdefault(slug, []).append(thread)
    out = world.live()
    for slug in run.removed:
        world.threads.pop(slug, None)
    kept: dict[str, dict[str, Any]] = read_json(run.state / "merged.json", {})
    named = {slug for row in rows for slug in (row["slug"], *row.get("depends", []))}
    try:
        for state, fields, into in (("open", OPEN, world.open), ("merged", MERGED, world.merged)):
            for pull in sorted(
                pulls(run, state, fields, "--limit", "100"), key=lambda p: p.get("mergedAt") or ""
            ):
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
    """A pull request's checks in one word, `jmerge --checks`'s reading (`jmerge.checks`), with
    no job asked for: a check that never started reads as failed here. `jmerge` is what
    decides a merge, not this."""
    return reading.checks(pull.get("statusCheckRollup") or [])


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
    """What a Result leaves, in a few words, or nothing: `Status: done` and `Left: none`."""
    status, rest = said_on(result, "Status"), said_on(result, "Left")
    if rest and rest != "none":
        return f"left: {cut(rest, WORDS)}"
    if status != "done":
        return f"status: {cut(status, WORDS)}" if status else "its Result has no Status line"
    return "" if rest else "its Result has no Left line"


def unfinished(result: str) -> str:
    """What keeps a Result with no merge from being the end of its task, or nothing.

    It is what the Result leaves, or a `Branch:` line that is missing or that ends on an
    address: a pull request that is neither open nor merged. It is the one rule for a task
    that ended with no pull request: `ended` and `threads.finished` both read it.
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
    """Whether a Result leaves work for after its pull request merged: its thread is told."""
    return said_on(result, "Left").lower().startswith(AFTER_MERGE)


@dataclass(frozen=True)
class End:
    """How a row whose thread ended with a Result stands: `done`, or `left` and `why`."""

    word: str
    why: str = ""


def ended(run: Pass, world: World, slug: str) -> End | None:
    """The end of a slug whose thread has ended with a Result and no pull request to wait for.

    Its thread has ended when it is settled or no longer `LIVE`. A slug T3 Code lists no
    thread for has not started, or was launched in this pass, and one with a pull request
    that is open or merged has its status from that.
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
    """Whether a slug's thread is gone and wrote nothing: it was launched, T3 Code lists no
    thread for it, a settled or archived one included, no pull request of its is open or
    merged, and its brief has no Result.

    `launched` is the thread of its launch record, or nothing for a slug with none. It is
    asked before a pass launches anything, of the answers that pass got: a thread launched
    after them is in neither.
    """
    if not launched or slug in world.threads or slug in world.settled or slug in world.archived:
        return False
    return (
        slug not in world.open and slug not in world.merged and not last_result(brief_of(run, slug))
    )


def written(result: str) -> work.Written:
    """What a Result says, as the facet `Written` has it: nothing, `clean` where it leaves
    nothing and has a `Branch:` line, `leftover` where its `Left:` line names something or
    its `Status:` is not `done`, and `malformed` where a line of the three is missing."""
    if not result:
        return work.Written.NONE
    short = left(result)
    if short.startswith(("left: ", "status: ")):
        return work.Written.LEFTOVER
    if short or not said_on(result, "Branch").split():
        return work.Written.MALFORMED
    return work.Written.CLEAN


def pull(world: World, slug: str, result: str, said: str) -> work.Pull:
    """The slug's pull request as the facet `Pull` has it. `said` is what `jmerge` last said
    of one that is open (`merge.step`), and a `Branch:` line that ends on an address with
    neither an open nor a merged pull request under the slug is one that was closed."""
    if slug in world.open:
        return work.Pull(merge.step(said) or work.Pull.OTHER)
    if slug in world.merged:
        return work.Pull.MERGED
    words = said_on(result, "Branch").split()
    return work.Pull.CLOSED if words and words[-1].startswith("http") else work.Pull.NONE


def thread(found: dict[str, Any] | None, live: str) -> work.Thread | None:
    """A thread as the facet `Thread` has it, from its status and its liveness (`jbus.live`).
    A turn whose liveness is not known is `quiet`: it is never said to be moving. A status
    jbus does not know is no facet at all: None."""
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
    """What a pass saw besides the world: the threads out (`threads.out`), or None where T3
    Code did not list them, the slugs whose launched thread is gone with nothing written
    (`gone`), what `jmerge` said of each open pull request by its number, the slugs that are
    merged or done (`final`), and which sources answered."""

    out: list[dict[str, Any]] | None
    gone: frozenset[str]
    said: dict[str, str]
    final: frozenset[str]
    answered: work.Answered = work.Answered.BOTH

    def live(self, thread: str) -> str:
        return next((one["live"] for one in self.out or [] if one["id"] == thread), "")

    def crew(self, slug: str) -> dict[str, Any] | None:
        """The one crew thread out for a slug, as the list of threads out has it."""
        found = [one for one in self.out or [] if one["role"] == "crew" and one["slug"] == slug]
        return found[0] if len(found) == 1 else None


def row_of(run: Pass, row: dict[str, Any], unmet: list[str]) -> work.Row:
    if not row.get("approved"):
        return work.Row.UNAPPROVED
    brief = queue.brief(run.state, row["slug"])
    if brief is None or not queue.approved_text(row, brief):
        return work.Row.CHANGED
    return work.Row.BEHIND if unmet else work.Row.FREE


def final(run: Pass, world: World | None, rows: list[dict[str, Any]]) -> frozenset[str]:
    """The slugs a row that depends on them no longer waits for: merged, or ended `done`,
    by the rule `dispatch` launches by. With no world, the rows' own status says it."""
    if world is None:
        return frozenset(row["slug"] for row in rows if row.get("status") in queue.FINAL)
    merged = set(world.merged) - set(world.open)
    return frozenset(
        merged | {row["slug"] for row in rows if ended(run, world, row["slug"]) == End("done")}
    )


def facts(
    run: Pass, world: World | None, row: dict[str, Any], seen: Seen, launched: str, last: str = ""
) -> tuple[work.Facts, bool]:
    """The facts of one row of the queue, whose launch record names the thread `launched`,
    or none, and whether its thread is in a status jbus does not know. With no world, the
    thread is the one the list of threads out has, and what GitHub would say is not known:
    its facet is `none`, and `judge` passes over every pattern that narrows it."""
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
        row=row_of(run, row, [one for one in row.get("depends", []) if one not in seen.final]),
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
    """The state of each row of a pass, judged once, when it is first asked for: a row added
    to the queue after the pass read it is judged as the others are. A running thread whose
    liveness the pass could not read, since T3 Code did not list the threads out, is `quiet`
    and not confirmed."""

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
    """What a thread that is no row's has written of what its role owes: a scout its last
    Report, read as a Result is, and a reviewer a Review with a verdict in the brief. A home
    or another thread owes nothing, so it has written all it owes."""
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
    """The facts of a thread out that is no row's, one of `threads.out`. Its thread is its
    own launch, and what it wrote counts once its turn is over: a turn under way writes."""
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
    """The `work.json` lines of every thread out that is no row's: a scout, a reviewer, a
    home, another, and a crew whose slug has no row. With no list of them, the last pass's
    lines, not confirmed."""
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
    """Why a `stale` row has nobody on it, or nothing while its crew still has it.

    A thread that ended or hung with nothing written is `stale` for as long as jbus carries
    its crew on (`threads.resume`). From `UNWRITTEN_MINUTES` after its thread last wrote, or
    at once for a hung turn, the row is a leftover, sent to its home to close (`leftover`),
    and it is `left` until its home ends it, the thread goes on, or the row is removed.

    A thread that ended its turn to wait on a test slot, and is one of `waiting`, is not left
    however long it is quiet: jbus wakes it when a slot is free (`slotwait`). Once woken, the
    rule above counts from its thread's last write again.
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
    """A row's derived columns: its status is the projection of its state (`work.status`),
    and under `why` is the reason its status itself carries, what a Result leaves.

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


def waits(run: Pass, pulls: Said, home: str) -> Waits:
    """What `jmerge` waits for or holds, by the pull request's number.

    `pulls` is what `jmerge` printed in this pass. Where the `home` merges, `jmerge` did
    not run here, and the lines are the last ones it logged, in `merge.log.last`. That
    file is read in no other case: it keeps a line after its pull request stopped waiting.
    """
    said: list[Any] = pulls
    if home:
        last = read_json(run.home / "merge.log.last", {})
        said = list(last.values()) if isinstance(last, dict) else []
    found = (parse(line) for line in said if isinstance(line, str))
    by_number = {
        str(line.number): f"{line.word}: {line.reason}"
        for line in found
        if line and line.word in ("wait", "hold") and line.reason
    }
    return Waits(by_number, failed=not home and pulls.failed)


def unread(run: Pass, read: bool) -> str:
    """Why `dispatch` read no row of the queue in this pass, or nothing when it `read` them.

    `UNREAD` is a pass that did not get to the launches: a project raised, or T3 Code,
    GitHub or the queue gave no answer to launch by.
    """
    if read:
        return ""
    if not run.config.dispatch:
        return OFF
    return STOP if run.config.stop_path.exists() else UNREAD


def why(run: Pass, row: dict[str, Any], found: dict[str, str], waits: Waits, unread: str) -> str:
    """Why a row waits, or nothing: `found` is its derived columns, as `status` gave them.

    A row with a pull request waits for what `jmerge` says of it. A row that was not
    launched waits for what `dispatch` recorded (`Pass.reasons`), or for its approval.
    Where `dispatch` read no row there is nothing recorded, and an approved row waits for
    what is `unread`: dispatch that is off, or the stop file. A pass that is `UNREAD` says
    nothing of the row, so its stored reason stays, but for an approval it has since got.
    So does a pass in which `jmerge` failed, for a pull request it had no line for.
    A row that ended, or that merged with work left for after it, has its reason from
    `status`.
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

    A thread of a row of the queue that completed with a Result is no gate: its row says
    how it ended (`ended`).
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
    _browser_red(run)


def _api(run: Pass, path: str) -> Any:
    asked = run.run("gh", "api", path)
    try:
        return json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        return None


def _check(run: Pass, known: dict[str, str], sha: str, again: bool = False) -> str:
    """Whether the check runs of a commit on main passed. A final answer is asked for once.

    A cancelled run is no failed check: it was displaced or stopped, and a push run that was
    cancelled before it had a job leaves the commit with no check run at all. With `again`,
    such a run at its first attempt is run again, and the commit is `pending` until that
    ends. GitHub's `run_attempt` says whether it was: `cancelled` is a later attempt that was
    cancelled too, and `refused` a run that GitHub did not start again.
    """
    if sha in known:
        return known[sha]
    said = _api(run, f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs")
    runs = (said or {}).get("check_runs") or []
    ended = [r.get("conclusion") for r in runs if r.get("status") == "completed"]
    if len(ended) < len(runs):
        return "pending"
    bad = any(c not in NOT_RED for c in ended)
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


def _log_failed(run: Pass, job: object) -> list[str] | None:
    """The ids of the tests a job's log says failed, from pytest's summary, in order; None
    where the log could not be read."""
    log = run.run("gh", "api", f"repos/{{owner}}/{{repo}}/actions/jobs/{job}/logs")
    return list(dict.fromkeys(_FAILED_TEST.findall(log.stdout))) if log.returncode == 0 else None


def _failed_tests(run: Pass, job: object) -> list[str]:
    return _log_failed(run, job) or []


def red_brief(
    slug: str,
    sha: str,
    jobs: list[tuple[str, str, list[str]]],
    red: list[dict],
    changed: list[str],
) -> str:
    """The brief for the fix of a red main at `sha`, in `templates/brief.md`'s shape. `jobs`
    is each failed check run's name, URL and failed tests, `red` the commits from `sha`
    down to the last green one, that one left out, and `changed` the files they changed."""
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
            f"# {mainstate.FIX}{sha[:12]}: main's check failed at {sha[:12]}, after {slug} merged",
            f'Task: "main check failed at {sha[:12]}, {len(red)} merges since the last green" '
            f"(jbus, the retro of {slug})",
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
            "Read:",
            *read,
            "",
        ]
    )


def _changed(run: Pass, red: list[dict]) -> list[str]:
    """The files the commits changed, as GitHub lists them for each."""
    files = []
    for commit in red:
        said = _api(run, f"repos/{{owner}}/{{repo}}/commits/{commit['sha']}")
        listed = said.get("files") if isinstance(said, dict) else None
        files += [one.get("filename", "") for one in listed or []]
    return [file for file in dict.fromkeys(files) if file]


def _file(run: Pass, slug: str, sha: str, red: list[dict]) -> None:
    """Write the brief for the fix of a red main to the home's `tasks/`, and queue it with no
    go: the user approves it as any other row. Its priority is one above the first row of
    the queue, so it is the next launch there once it is approved. It is filed while the
    queue has no row of it, so a pass that stopped before the row was added files it again.
    A queue that refuses it is a condition."""
    name = f"{mainstate.FIX}{sha[:12]}"
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


def browser_red_brief(
    name: str, day: str, one: dict[str, Any], jobs: list[tuple[str, str, list[str]]]
) -> str:
    """The brief for the fix of a red browser run, in `templates/brief.md`'s shape. `one` is
    the run as GitHub lists it, and `jobs` is each failed job's name, URL and failed tests."""
    tests = [test for _, _, failed in jobs for test in failed]
    files = list(dict.fromkeys(test.split("::")[0] for test in tests))
    where = ", ".join(f"`{file}`" for file in files) or "the tests marked `browser`"
    number, event = one.get("id"), one.get("event") or "an event"
    read = [
        f"- the job `{job}`, {url or 'with no URL'}: "
        + (", ".join(f"`{test}`" for test in failed) or "its log names no failed test, read it")
        for job, url, failed in jobs
    ]
    read += [f"- the run {one.get('html_url') or number}, from {event}, at {one.get('head_sha')}"]
    return "\n".join(
        [
            f"# {name}: the browser tests failed on {day}",
            f'Task: "the browser run {number} failed on {day}, {len(tests)} tests named" '
            "(jbus, from browser.yml)",
            "Done when:",
            "- each failed test named under Read passes under `make check-browser`",
            "- the Result names the cause: the merge that broke the page, or a flake with its "
            "evidence",
            "Proves it: `make check-browser` passes, and so does a manual run of browser.yml "
            "(workflow_dispatch) on the fix's branch",
            "Size: S",
            f"Where: {where}",
            "Do not touch: .github/workflows/, the ruleset",
            "Decisions: none, jbus filed this from a red browser run and the user has not seen it",
            "Design: none, a fix to what the failed run names",
            "Pull request: open one when done",
            "Review: review",
            "Playbook: bug-fix",
            "Read:",
            *read,
            "",
        ]
    )


def _browser_name(day: str, taken: set[str]) -> str:
    """`browser-red-<day>`, and `-2`, `-3` for each further red run of the same day."""
    name, more = f"browser-red-{day}", 1
    while name in taken:
        more += 1
        name = f"browser-red-{day}-{more}"
    return name


def _browser_red(run: Pass) -> None:
    """A red run of browser.yml, which no pull request's check runs, files the brief for its
    fix and queues it unapproved, once per run: `browser-runs.json` keeps each run seen, so a
    removed row is not filed again. A run seen on a project's first pass is only recorded.

    A red run is one that failed or timed out, and ended within `BROWSER_WINDOW`. Where GitHub
    would not give its jobs, or a failed job's log, the run is asked about again on the next
    pass, and is filed without the names once it ended `BROWSER_GRACE` ago. A manual run
    on a branch other than the default is the branch's own business, and files nothing.
    """
    said = _api(
        run,
        f"repos/{{owner}}/{{repo}}/actions/workflows/{BROWSER}/runs?status=completed&per_page=20",
    )
    runs = said.get("workflow_runs") if isinstance(said, dict) else None
    if not isinstance(runs, list):
        return
    seen: dict[str, str] = read_json(run.state / "browser-runs.json", {})
    default = _default_branch(run)
    for one in sorted(runs, key=lambda r: r.get("created_at") or ""):
        number = str(one.get("id"))
        ended = when(one.get("updated_at") or one["created_at"])
        stale = run.now - ended > BROWSER_WINDOW
        if number in seen or one.get("conclusion") not in BROWSER_RED or stale:
            continue
        if one.get("event") == "workflow_dispatch" and one.get("head_branch") != default:
            continue
        if run.first:
            seen[number] = ""
            continue
        day = run.user.day(when(one["created_at"]))
        name = _browser_name(day, {*seen.values(), *run.removed})
        if queue.fresh(run.state, name) is None:
            asked = _api(run, f"repos/{{owner}}/{{repo}}/actions/runs/{number}/jobs?per_page=100")
            if not isinstance(asked, dict):
                if run.now - ended < BROWSER_GRACE:
                    continue
                asked = {}
            red = [
                j
                for j in asked.get("jobs") or []
                if j.get("status") == "completed" and j.get("conclusion") not in NOT_RED
            ]
            logs = [_log_failed(run, j.get("id")) for j in red]
            if None in logs and run.now - ended < BROWSER_GRACE:
                continue
            jobs = [
                (j.get("name") or "?", j.get("html_url") or "", failed or [])
                for j, failed in zip(red, logs, strict=True)
            ]
            text = browser_red_brief(name, day, one, jobs)
            (run.home / "tasks").mkdir(parents=True, exist_ok=True)
            (run.home / "tasks" / f"{name}.md").write_text(text)
            try:
                queue.add(run.state, name, 0, [], text)
            except Refused as refused:
                run.condition(name, f"its brief was not queued: {refused}")
                continue
            tests = sum(len(failed) for _, _, failed in jobs)
            line = f"retro {name}: the browser run {number} failed on {day}, {tests} tests named"
            run.find(name, "retro", line, key=f"browser {number}", past=True)
        seen[number] = name
        write_json(run.state / "browser-runs.json", seen)
    write_json(run.state / "browser-runs.json", seen)


def _retro(run: Pass, world: World, rows: list[dict[str, Any]]) -> None:
    """A red main within a day of a merge, and a revert of one. Both name the merged slug.

    A main whose run was cancelled is not red: its run is asked for again, and what is said
    is a second cancelled one, or a run GitHub would not start again. A red main is said
    once a commit. The brief for its fix is filed and queued once, and only for main's tip
    as this pass reads it (`_file`): a red commit that a later one superseded is no main to
    fix. A filed row whose main is green again before it launched is said once, and is left
    as it is.
    """
    slugs = sorted(
        (s for s in world.merged if brief_of(run, s) and s not in run.gated),
        key=lambda s: world.merged[s]["mergedAt"],
    )
    unlaunched = [
        row["slug"]
        for row in rows
        if mainstate.fix_of(row["slug"])
        and row.get("status") in ("queued", "gate")
        and not row.get("thread")
    ]
    if not slugs and not unlaunched:
        return
    merges = [world.merged[slug] for slug in slugs]
    slug_of = {pull["number"]: slug for slug, pull in world.merged.items()}
    branch = _default_branch(run)
    commits = _api(run, f"repos/{{owner}}/{{repo}}/commits?sha={branch}&per_page=50")
    if not isinstance(commits, list):
        return
    known: dict[str, str] = read_json(run.state / "checks.json", {})
    tip = commits[0]["sha"] if commits else ""
    if unlaunched and _check(run, known, tip) == "green":
        for name in unlaunched:
            line = f"retro {name}: main is green again at {tip[:12]}, and its row is left as it is"
            run.find(name, "retro", line, key=f"green {name}", past=True)
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
            continue
        slug, answer = slug_of[pull["number"]], _check(run, known, sha, again=True)
        if answer in ("cancelled", "refused"):
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
        line = f"retro {slug}: main check failed at {sha[:12]}, {since} merges since the last green"
        run.find(slug, "retro", line, key=f"red {sha}", past=True)
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
