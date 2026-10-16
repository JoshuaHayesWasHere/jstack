"""Tying each crew to its thread, which a home did by hand: the link, the relay, the settle.

`link` gives an open pull request to the thread jbus launched for its branch, so T3 Code
shows it there. `relay` sends a review's findings to the crewmate when the reviewer could
not. `settle` puts away the threads of a slug that is finished, and the subagent threads
under them, and archives the review threads of a pull request that merged or closed.
`resume` tells a crewmate whose thread ended with no Result to carry on, twice
at most, and then leaves it to the Chef. `merged` tells a crewmate whose pull request
merged, and whose Result leaves work for after the merge, to carry on, once. `out` is every
thread that is not settled, whatever its title, with the role its title gives it (`ROLES`)
and its liveness.

Each action happens once. Its key is recorded in `sent.json` beside the keys of the events,
and only after T3 Code said yes, so one that got no answer is tried again on the next pass.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from jbus import dispatch, lavish, mirror, queue, read_json, record, stall, verbs, watch, work
from jbus.live import Facts, judge
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import ENDED, LIVE, STARTING, World, after_merge, unfinished, when

if TYPE_CHECKING:
    from jbus.cli import Half

EVENTS = {"resume": "quiet", "relayed": "quiet"}
RELAY = "jbus: the reviewer could not deliver these findings."
SCOUT = "scout: "
PREFIXES = ("crew: ", "review: ", SCOUT)
ROLES = {"crew: ": "crew", "review: ": "reviewer", SCOUT: "scout", "home: ": "home"}
OTHER = "other"
RUNS = 20
SECOND = ", second pass"
SCOPED = ", scoped"
REVIEW = "## Review"
CARRY_ON = (
    "jbus: this thread ended ({status}) before writing its Result. Carry on with your brief "
    "from where you stopped: read `tasks/{slug}.md` and your worktree's `git status` and "
    "`git log` first, keep what is committed, and do not start over. This is carry-on {k} of "
    "{most}."
)
CARRY_ONS = 2
MERGED = (
    "jbus: pull request #{number} of this task is merged, and your last Result leaves work "
    "for after the merge. Carry on from your brief: read `tasks/{slug}.md`, do what the "
    "`Left:` line of its last Result names, and write a follow-up Result when it is done."
)
REPORT = "## Report"
Out = dict[str, Any]
_SESSION = re.compile(r"/session/([0-9a-f]+)")


def _done(run: Pass, key: str) -> bool:
    return key in read_json(run.state / "sent.json", [])


def _briefs(run: Pass, kind: str = "tasks") -> dict[str, str]:
    found = {}
    for path in sorted((run.home / kind).glob("*.md")):
        try:
            found[path.stem] = path.read_text(errors="replace")
        except OSError:
            continue
    return found


def link(run: Pass, client: Client, world: World) -> None:
    for slug, pull in world.open.items():
        thread, key = dispatch.launched(run, slug), f"linked|{slug}|#{pull['number']}"
        if not thread or not pull.get("url") or _done(run, key):
            continue
        try:
            client.call("link_pull_request", {"threadId": thread, "url": pull["url"]})
        except T3Error as error:
            run.say(f"wait {slug}: pull request #{pull['number']} could not be linked ({error})")
            continue
        run.box.mark(key)
        run.say(f"linked {slug}: #{pull['number']} to {thread}")


def relay(run: Pass, client: Client, world: World) -> None:
    """Send the crewmate the findings its reviewer could not, once per Review.

    Only for a pull request that is open: the findings of one that merged or closed ask
    for nothing any more.
    """
    briefs = _briefs(run)
    client.recipients = frozenset(filter(None, map(dispatch.thread_of, briefs.values())))
    for slug in sorted(set(briefs) & set(world.open)):
        review = mirror.undelivered(briefs[slug])
        digest = hashlib.sha256(review.encode()).hexdigest()[:16]
        key = f"relayed|{slug}|{digest}"
        if not review or _done(run, key):
            continue
        thread = dispatch.thread_of(briefs[slug])
        if not thread:
            what = "review findings with no thread to send them to"
            run.gate(slug, what, review, key=f"{what} {digest}")
            continue
        asked = {
            "threadId": thread,
            "message": f"{RELAY}\n\n{review}",
            "mode": "queue",
            "clientRequestId": key,
        }
        try:
            client.call("t3_thread_send", asked)
        except T3Refused as error:
            what = "T3 Code refused the review's findings"
            run.gate(slug, what, f"{error}\n\n{review}", key=f"{what} {digest}")
            continue
        except T3Error as error:
            run.say(f"wait {slug}: its review's findings could not be sent ({error})")
            continue
        run.find(slug, "relayed", f"relayed {slug}", review, key=digest)
        run.say(f"relayed {slug}: to {thread}")


UNSEEN = "its page has no session in Lavish's state at {}, so its thread stays"


def _waits(run: Pass, slug: str, page: str, sessions: list[dict[str, Any]]) -> str:
    """Why the page a scout's Report names may still wait on the user, or nothing.

    Its session is the one whose address the `Page:` line gives, or the one of the file the
    scout skill writes a page to. It waits until that session has ended and no answer is
    left queued in it: Lavish ends a session on the user's last send and keeps what they
    sent until a poll takes it. A session Lavish does not know keeps the scout too.
    """
    if not page:
        return ""
    keys = set(_SESSION.findall(page))
    file = str((run.home / "reports" / f"{slug}.html").resolve())
    mine = [one for one in sessions if one.get("key") in keys or one.get("file") == file]
    if not mine:
        return UNSEEN.format(lavish.path())
    heard = all(
        one.get("status") == "ended" and not one.get("prompts") and not one.get("pending_prompts")
        for one in mine
    )
    return "" if heard else "its page waits on the user"


def _scouts(run: Pass) -> dict[str, str]:
    """Each scout with a Report, and why its thread stays: nothing for one that is over."""
    pages = {}
    for slug, text in _briefs(run, "scouts").items():
        whole = mirror.sections(text, gates_inside=True)
        reports = [body for heading, body in whole if heading == REPORT]
        if reports:
            pages[slug] = mirror.page(reports[-1])
    sessions = lavish.sessions() if any(pages.values()) else []
    return {slug: _waits(run, slug, page, sessions) for slug, page in pages.items()}


def shut(world: World, briefs: dict[str, str]) -> set[str]:
    """The slugs whose pull request merged or closed, as `watch.pull` has it, and never one
    whose last Result names a pull request that is open: `watch.pull` knows an open one
    under the one slug `tied` gives it, and another brief naming it would read as closed."""
    open_at = {str(pull.get("url", "")).rstrip("/") for pull in world.open.values()}
    found = set(world.merged) - set(world.open)
    for slug, text in briefs.items():
        result = mirror.last_result(text)
        if watch.named(result)[0].rstrip("/") in open_at:
            found.discard(slug)
        elif watch.pull(world, slug, result, "") in {work.Pull.MERGED, work.Pull.CLOSED}:
            found.add(slug)
    return found


def finished(run: Pass, world: World, scouts: dict[str, str] | None = None) -> dict[str, set[str]]:
    """The slugs whose threads may be put away, by the title such a thread starts with, and
    under `archive` those whose review threads are archived too.

    A task is over when its pull request merged, or when its last Result says `Status:
    done` and `Left: none` and names no pull request: the crew skill keeps a thread with
    something left where the user sees it. A reviewer is over when its pull request merged
    or closed, or its task is over, and the brief's last Review has a verdict: one that
    stopped early stays. It is archived when its pull request merged or closed. A scout is
    over when its Report is written, and the page its last Report names, if any, waits on
    nobody.
    """
    briefs = _briefs(run)
    tasks = set(world.merged) - set(world.open)
    for slug, text in briefs.items():
        result = mirror.last_result(text)
        if result and not unfinished(result) and slug not in world.open:
            tasks.add(slug)
    ended = shut(world, briefs)
    reviewed = set()
    for slug in (tasks | ended) & set(briefs):
        whole = mirror.sections(briefs[slug], gates_inside=True)
        verdicts = [mirror.field(body, "Verdict") for heading, body in whole if heading == REVIEW]
        if verdicts and verdicts[-1] in ("clean", "findings"):
            reviewed.add(slug)
    held = _scouts(run) if scouts is None else scouts
    return {
        "crew: ": tasks,
        "review: ": reviewed,
        "scout: ": {slug for slug, why in held.items() if not why},
        "archive": reviewed & ended,
    }


def _listed(client: Client, project_id: str, **asked: Any) -> list[dict[str, Any]]:
    found, cursor = [], None
    for _ in range(20):
        more = {"cursor": cursor} if cursor else {}
        said = client.call(
            "t3_thread_list", {"projectId": project_id, "limit": 100, **asked, **more}
        )
        found += said.get("threads", [])
        cursor = said.get("nextCursor")
        if not cursor:
            break
    return found


def slug_in(title: str, prefix: str) -> str | None:
    if not title.startswith(prefix):
        return None
    return title.removeprefix(prefix).removesuffix(SECOND).removesuffix(SCOPED).strip()


def role_of(title: str) -> tuple[str, str]:
    """The role a thread's title gives it and the slug after it: `OTHER` and no slug for a
    title that starts with none of `ROLES`."""
    for prefix, role in ROLES.items():
        slug = slug_in(title, prefix)
        if slug is not None:
            return role, slug
    return OTHER, ""


def _silent(now: datetime, updated: Any) -> float | None:
    """The minutes since a thread last wrote, or None where T3 Code gave no time for it."""
    try:
        return (now - when(updated)).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def out(run: Pass, client: Client, also: frozenset[str] = frozenset()) -> list[Out] | None:
    """Every thread of the project that is not settled, oldest first, each with its role,
    its slug and its liveness (`live.judge`). None where T3 Code could not list them.

    When a thread last wrote is `wrote`: its `updatedAt` as of the pass that last saw its
    count of items change. `updatedAt` alone will not do, since T3 Code moves it when a
    message is queued to the thread, and a wake queued behind a hung turn is the very case
    this is for. The count is kept from pass to pass in `pass.json`. A thread seen for the
    first time, or one T3 Code gives no count for, wrote at its `updatedAt`. A turn cannot
    have been silent since before it started: where a read gives the active run a later
    `startedAt`, the silence is counted from that, so a turn started on a thread that ended
    long ago is not hung at once.

    Only a thread that is `quiet` or `hung` by that alone is read, for the run that is
    active, when it started, the runs queued behind it and the requests that wait: a pass
    with nothing quiet reads none. The threads in `also` are read too, whatever they are. A
    scout holds a page while its last Report names one that waits.

    `run` is the run a read gave as active, and nothing for a thread that was not read: the
    list names only a thread's newest run, which is a queued one whenever a run waits. So a
    thread that could not be read is `quiet` at most. Whether it is hung, or waits on a
    request, is said by the first pass that reads it, of the run that pass names.
    """
    try:
        listed = _listed(client, run.project.project_id, settled=False)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the threads out could not be listed ({error})")
        return None
    held = _scouts(run)
    before = {one.get("id"): one for one in record.seen(run.config, run.project.name)}
    found = []
    for thread in sorted(listed, key=lambda t: str(t.get("createdAt", ""))):
        at, title = thread["threadId"], str(thread.get("title", ""))
        role, slug = role_of(title)
        items, was = thread.get("itemCount"), before.get(at, {})
        same = type(items) is int and was.get("items") == items and was.get("wrote")
        wrote = was["wrote"] if same else thread.get("updatedAt")
        silent = _silent(run.now, wrote)
        page = role == "scout" and bool(held.get(slug))
        facts = Facts(str(thread.get("status", "")), silent, page=page)
        active, started, runs = None, None, None
        word = judge(facts).word
        if word in ("quiet", "hung") or at in also:
            try:
                read = client.call("t3_thread_read", {"threadId": at, "limit": 1, "runLimit": RUNS})
            except T3Error as error:
                run.say(f"wait {slug or title}: its thread could not be read ({error})")
                word = "quiet" if word == "hung" else word
            else:
                said = read.get("thread") or {}
                recent = [one for one in read.get("recentRuns") or [] if isinstance(one, dict)]
                active = said.get("activeRunId")
                runs = {str(one.get("runId")): str(one.get("status")) for one in recent}
                started = next(
                    (r.get("startedAt") for r in recent if r.get("runId") == active), None
                )
                behind = [r for r in recent if r.get("runId") != active]
                queued = sum(r.get("status") in STARTING for r in behind)
                pending = said.get("pendingRequestCount")
                since = _silent(run.now, started)
                if since is not None and (silent is None or since < silent):
                    wrote, silent = started, since
                facts = replace(
                    facts,
                    silent=silent,
                    queued=queued,
                    pending=pending if type(pending) is int else 0,
                )
                word = judge(facts).word
        found.append(
            {
                "id": at,
                "title": title,
                "role": role,
                "slug": slug,
                "status": facts.status,
                "createdAt": thread.get("createdAt"),
                "updatedAt": thread.get("updatedAt"),
                "items": items if type(items) is int else None,
                "wrote": wrote,
                "live": word,
                "silent": None if silent is None else int(silent),
                "run": active,
                "run_started": started,
                "queued": facts.queued,
                "pending": facts.pending,
                "page": facts.page,
                "runs": runs,
            }
        )
    return found


def settle(run: Pass, client: Client, world: World) -> None:
    """Settle the threads of each finished slug and the subagent threads under them, once each,
    and archive a review thread whose pull request merged or closed, with what is under it.

    A thread that is still at work is left, with what is under it, for the next pass.
    """
    held = _scouts(run)
    over = finished(run, world, held)
    unseen = {slug for slug, why in held.items() if why == UNSEEN.format(lavish.path())}
    slug_of: dict[str, str] = {}
    shelve: set[str] = set()
    waiting: list[dict[str, Any]] = []
    try:
        for prefix in PREFIXES:
            if not over[prefix] and not (prefix == SCOUT and unseen):
                continue
            for thread in _listed(client, run.project.project_id, titleContains=prefix):
                slug = slug_in(str(thread.get("title", "")), prefix)
                if slug in over[prefix]:
                    slug_of[thread["threadId"]] = slug
                    waiting.append(thread)
                    if prefix == "review: " and slug in over["archive"]:
                        shelve.add(thread["threadId"])
                elif prefix == SCOUT and slug in unseen and not thread.get("settled"):
                    run.say(f"wait {slug}: {held[slug]}")
                    unseen.discard(slug)
        if not slug_of:
            return
        below = _listed(client, run.project.project_id, settled=False, includeSubagents=True)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the threads to settle could not be listed ({error})")
        return
    busy = {t["threadId"] for t in waiting if not t.get("settled") and t["status"] in LIVE}
    below = [t for t in below if t.get("relationshipToParent") == "subagent"]
    grew = True
    while grew:
        grew = False
        for thread in below:
            parent = thread.get("parentThreadId")
            if thread["threadId"] in slug_of or parent not in slug_of:
                continue
            slug_of[thread["threadId"]] = slug_of[parent]
            if parent in shelve:
                shelve.add(thread["threadId"])
            if parent in busy or thread["status"] in LIVE:
                busy.add(thread["threadId"])
            waiting.append(thread)
            grew = True
    for thread in waiting:
        at, slug = thread["threadId"], slug_of[thread["threadId"]]
        if at in busy:
            continue
        for action in ("settle", "archive") if at in shelve else ("settle",):
            key = f"{action}d|{slug}|{at}"
            if _done(run, key):
                continue
            if action == "settle" and thread.get("settled"):
                run.box.mark(key)
                continue
            try:
                client.call("t3_thread_organize", {"action": action, "threadId": at})
            except T3Error as error:
                run.say(f"wait {slug}: thread {at} could not be {action}d ({error})")
                break
            run.box.mark(key)
            run.say(f"{action}d {slug}: {thread.get('title') or 'a thread'} {at}")


def resume(run: Pass, client: Client, world: World) -> None:
    """Tell each crew whose thread ended with no Result to carry on, once per ended run.

    Only the one thread of a slug jbus launched, that the brief names on its `Thread:` line,
    with no pull request yet. The keys of the carry-ons a thread has had are its count: at
    `CARRY_ONS` the next end is a gate, and a new thread for the slug starts from none.
    """
    briefs = _briefs(run)
    sent = read_json(run.state / "sent.json", [])
    for slug, live in sorted(world.threads.items()):
        thread, brief = live[0], briefs.get(slug, "")
        at, status, ended = thread["threadId"], thread["status"], thread.get("latestRunId")
        if len(live) > 1 or slug in run.gated or slug in world.open or slug in world.merged:
            continue
        if status not in ENDED or not ended or thread.get("settled") or thread.get("snoozed"):
            continue
        if not dispatch.launched(run, slug) or mirror.last_result(brief):
            continue
        if dispatch.thread_of(brief) != at:
            continue
        key = f"resume|{slug}|{at}|{ended}"
        if key in sent:
            continue
        had = sum(one.startswith(f"resume|{slug}|{at}|") for one in sent)
        if had >= CARRY_ONS:
            run.gate(slug, f"thread ended {status} after two carry-ons", at, key=f"{at} {ended}")
            continue
        message = CARRY_ON.format(status=status, slug=slug, k=had + 1, most=CARRY_ONS)
        client.recipients = client.recipients | {at}
        asked = {"threadId": at, "message": message, "mode": "queue", "clientRequestId": key}
        try:
            client.call("t3_thread_send", asked)
        except T3Refused as error:
            what = "T3 Code refused the carry-on"
            run.gate(slug, what, f"{error}\n\n{message}", key=f"{what} {at} {ended}")
            continue
        except T3Error as error:
            run.say(f"wait {slug}: its crew could not be told to carry on ({error})")
            continue
        line = f"resume {slug}: told the crew to carry on ({status}, {had + 1} of {CARRY_ONS})"
        run.find(slug, "resume", line, key=f"{at} {ended}")
        run.box.mark(key)
        run.say(line)


def merged(run: Pass, client: Client, world: World, rows: list[queue.Row]) -> None:
    """Tell the crew of each row whose pull request merged with work left for after it, once.

    The thread is the one the brief names on its `Thread:` line, or the one jbus launched
    for the slug, or the one T3 Code lists. A row told in this pass is on `Pass.told`.
    """
    briefs = _briefs(run)
    for slug in sorted(row["slug"] for row in rows):
        pull, brief = world.merged.get(slug), briefs.get(slug, "")
        if not pull or slug in world.open or slug in run.gated:
            continue
        if not after_merge(mirror.last_result(brief)):
            continue
        key = f"merged-left|{slug}|#{pull['number']}"
        listed = (world.thread(slug) or {}).get("threadId", "")
        at = dispatch.thread_of(brief) or dispatch.launched(run, slug) or listed
        if not at or _done(run, key):
            continue
        message = MERGED.format(number=pull["number"], slug=slug)
        client.recipients = client.recipients | {at}
        asked = {"threadId": at, "message": message, "mode": "queue", "clientRequestId": key}
        try:
            client.call("t3_thread_send", asked)
        except T3Error as error:
            run.say(f"wait {slug}: its crew could not be told of the merge ({error})")
            continue
        run.box.mark(key)
        run.told.add(slug)
        run.say(f"told {slug}: #{pull['number']} is merged, and its Result leaves work")


def tie(run: Pass, client: Client, world: World) -> None:
    dispatch.write_missing(run)
    link(run, client, world)
    relay(run, client, world)
    settle(run, client, world)


def _out(half: Half) -> None:
    """The crews out, for the record, and then `stall.hung` over them: one step, so that no
    rank can put `hung` before the list it reads."""
    half.out = out(half.run, half.client, stall.watched(half.run))
    stall.hung(half.run, half.out)


STEPS = (
    verbs.Step(
        "tellers",
        50,
        "threads.tie",
        lambda half: tie(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
    verbs.Step(
        "tellers",
        60,
        "threads.resume",
        lambda half: resume(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
    verbs.Step(
        "tellers",
        70,
        "threads.merged",
        lambda half: merged(half.run, half.client, half.seen.world, half.rows or []),
        ("client", "world"),
    ),
    verbs.Step("tellers", 80, "threads.out and stall.hung", _out, ("client", "world")),
)
