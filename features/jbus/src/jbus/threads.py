"""This module ties each crew to its thread, work that a home used to do by hand: the link and the
settle.

`link` links an open pull request to the thread that jbus launched for the pull request's branch, so
T3 Code shows the pull request in that thread. A review's findings reach the crew from
`jbus.reviewed`. `settle` settles the threads of a slug that is finished, and
the subagent threads under them. `settle` also archives the review threads of a pull request that
merged or closed. `resume` tells a crewmate to carry on when its thread ended with no Result.
`resume` does this twice at most, and after that it tells the brief's home in one line. `merged`
tells a crewmate to carry on, once, when its pull request merged and its Result leaves work for
after the merge. `out` lists every thread that is not settled, whatever its title, with the role
that its title gives it (`ROLES`) and its liveness.

Each action happens once. jbus records the action's key in `sent.json`, beside the keys of the
events, but only after T3 Code accepted the call. So when an action got no answer, the next pass
tries it again.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsettings
from jbriefs import findings, parse, skills
from jbus import (
    END_TURN,
    dispatch,
    lavish,
    mirror,
    outbox,
    queue,
    record,
    stall,
    t3,
    verbs,
    watch,
    work,
)
from jbus.live import Facts, judge
from jbus.passes import Pass
from jbus.roles import PREFIXES, SCOUT, role_of, slug_in
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import ENDED, STARTING, World, after_merge, unfinished, when

if TYPE_CHECKING:
    from jbus.poll import Half

EVENTS = {"resume": "quiet"}
RUNS = 20
REVIEW = "## Review"
CARRY_ON = (
    "jbus: this thread ended ({status}) before writing its Result. Carry on with your brief "
    "from where you stopped: read `tasks/{slug}.md` and your worktree's `git status` and "
    "`git log` first, keep what is committed, and do not start over. This is carry-on {k} of "
    "{most}."
)
CARRY_ONS = 2
STOPPED = (
    "jbus: {slug}'s crew thread {thread} ended ({status}) with no Result after {most} "
    "carry-ons. It is the home's from here: pick it up as the home skill's \"Picking up a "
    'thread that stopped" says.'
)
MERGED = (
    "jbus: pull request #{number} of this task is merged, and your last Result leaves work "
    "for after the merge. Carry on from your brief: read `tasks/{slug}.md`, do what the "
    "`Left:` line of its last Result names, and write a follow-up Result when it is done."
)
REPORT = "## Report"
SKILLS = {"crew": "crew", "reviewer": "pr-review", "scout": "scout"}


def skill_file(name: str) -> Path:
    """Return the file of skill `name` in the jstack checkout itself, as `skills.json` lists it."""
    return skills.where("skill", name)


READ_SKILL = (
    " Your role's skill is not loaded in this thread and the Skill tool cannot load it: read "
    "`{path}` from the file and follow it from where your work stands. Run `jbriefs --skills "
    "{brief}` for the brief's Skills line and read what it prints."
)


def resume_message(template: str, title: str, home: Path, **fields: Any) -> str:
    """Return the text that resumes the thread titled `title`. The text is the template filled in.
    For a role that has a skill (`SKILLS`), the text also gives the path of the skill's file. A
    skill loads only when someone types the skill's slash command. A resumed thread never typed that
    command, or lost the loaded skill to a compaction, and such a thread cannot load the skill
    through the Skill tool. The text names the brief in `home` by its full path, since the thread's
    own worktree has no `tasks/`. A reviewer's message also ends with `END_TURN`, since the
    reviewer's turn waits for a run, and that run is the reviewer's proof. For a title that gives no
    such role, the text is the template alone."""
    message = template.format(**fields)
    role = role_of(title)[0]
    name = SKILLS.get(role)
    if not name:
        return message
    brief = home / ("scouts" if role == "scout" else "tasks") / f"{fields['slug']}.md"
    message += READ_SKILL.format(path=skill_file(name), brief=brief)
    return f"{message} {END_TURN}" if role == "reviewer" else message


Out = dict[str, Any]
_SESSION = re.compile(r"/session/([0-9a-f]+)")


def _done(run: Pass, key: str) -> bool:
    return key in run.box.sent()


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


UNSEEN = "its page has no session in Lavish's state at {}, so its thread stays"
UNDONE = "its Report does not say Status: done, so its thread stays"


def _says_done(report: str) -> bool:
    """Say whether a scout's Report says `Status: done`, on its last `Status:` line, as the scout
    skill's own settle block reads it: the word after `Status:` is `done`, so `Status: done, but`
    is not."""
    said = [line.split()[1:2] for line in report.splitlines() if line.split()[:1] == ["Status:"]]
    return bool(said) and said[-1] == ["done"]


def _waits(run: Pass, slug: str, page: str, sessions: list[dict[str, Any]]) -> str:
    """Return why the page that a scout's Report names may still wait on the user, or nothing.

    The page's session is the one at the address on the `Page:` line, or else the session of the
    file to which the scout skill writes a page. The page waits until that session has ended and no
    answer is left queued in it. Lavish ends a session on the user's final send, and keeps what the
    user sent until a poll takes it. When Lavish does not know the session, the scout's thread also
    stays.
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
    """Return each scout that has a Report, with the reason its thread stays. The reason is empty
    for a scout that is over. A scout whose last Report does not say `Status: done` stays, as the
    scout skill's End keeps it, and a page that waits is the reason it gives first."""
    pages, undone = {}, set()
    for slug, text in _briefs(run, "scouts").items():
        whole = mirror.sections(text)
        reports = [body for heading, body in whole if heading == REPORT]
        if reports:
            pages[slug] = mirror.page(reports[-1])
            if not _says_done(reports[-1]):
                undone.add(slug)
    sessions = lavish.sessions() if any(pages.values()) else []
    return {
        slug: _waits(run, slug, page, sessions) or (UNDONE if slug in undone else "")
        for slug, page in pages.items()
    }


def shut(world: World, briefs: dict[str, str]) -> set[str]:
    """Return the slugs whose pull request merged or closed, as `watch.pull` has it. Leave out every
    slug whose last Result names a pull request that is open. `watch.pull` lists an open pull
    request under only the one slug that `tied` gives it. Without this rule, another brief that
    names the same pull request would read as closed."""
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
    """Return the slugs whose threads may be put away, by the start of such a thread's title. Under
    `archive`, also return the slugs whose review threads jbus archives.

    A task is over when its pull request merged, or when its last Result says `Status: done` and
    `Left: none` and names no pull request. Under the crew skill, a thread that has something left
    stays where the user sees it. A reviewer is over when the brief's last Review has a verdict and
    either the reviewer's pull request merged or closed or the reviewer's task is over. A reviewer
    that stopped early stays. jbus archives a reviewer when its pull request merged or closed. A
    scout is over when its last Report says `Status: done` and nobody waits on the page that it
    names, if it names one.
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
        ran = [one.ran for one in findings.triage(briefs[slug]).sections]
        if ran and ran[-1]:
            reviewed.add(slug)
    held = _scouts(run) if scouts is None else scouts
    return {
        "crew: ": tasks,
        "review: ": reviewed,
        "scout: ": {slug for slug, why in held.items() if not why},
        "archive": reviewed & ended,
    }


def _silent(now: datetime, updated: Any) -> float | None:
    """Return the minutes since a thread last wrote, or None where T3 Code gave no time for it."""
    try:
        return (now - when(updated)).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def out(run: Pass, client: Client, also: frozenset[str] = frozenset()) -> list[Out] | None:
    """Return every thread of the project that is not settled, oldest first, each with its role, its
    slug and its liveness (`live.judge`). Return None where T3 Code could not list the threads.

    `wrote` is when a thread last wrote. `wrote` is the thread's `updatedAt`, taken at the last pass
    that saw the thread's count of items change. `updatedAt` alone will not do, because T3 Code
    moves `updatedAt` when someone queues a message to the thread. A wake queued behind a hung turn
    is exactly the case for which this check exists. jbus keeps the count from pass to pass in
    `pass.json`. For a thread seen for the first time, or a thread for which T3 Code gives no count,
    `wrote` is its `updatedAt`. A turn cannot have been silent since before it started. So where a
    read gives the active run a later `startedAt`, `out` counts the silence from that time. So a
    turn that just started on a thread that ended long ago is not hung at once.

    An answered request moves neither the count of items nor `updatedAt`, and T3 Code keeps no time
    for the answer. So a pass that reads a request count of 0, where the pass before kept one above
    0 and the count of items has not changed, counts the answer as the thread's last write, and
    `wrote` is the time of this pass. A thread that is not read, or that is read with no count,
    keeps the count the pass before kept. So a crew that waited on an approval for 17 minutes is
    not hung 3 minutes after the answer.

    `out` reads a thread only when the thread is `quiet` or `hung` by the listed data alone. The
    read gives the active run, when it started, the runs queued behind it and the requests that
    wait. A pass with no quiet thread reads no thread. `out` also reads the threads in `also`,
    whatever their state. A scout's entry has `page` set while its last Report names a page that
    waits.

    `run` is the run that a read gave as active, and nothing for a thread that was not read. T3
    Code's list of threads names only a thread's newest run, and that run is a queued one whenever a
    run waits. So a thread that could not be read is `quiet` at most. The first pass that reads the
    thread decides whether the thread is hung or waits on a request, for the run that this pass
    names.
    """
    try:
        listed = t3.listed(client, run.project.project_id, settled=False)
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
        page = role == "scout" and held.get(slug) not in (None, "", UNDONE)
        facts = Facts(str(thread.get("status", "")), silent, page=page)
        active, started, runs = None, None, None
        asked = was.get("pending") if same and type(was.get("pending")) is int else 0
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
                kept, asked = asked, pending if type(pending) is int else asked
                if kept and not asked:
                    wrote, silent = record.stamp(run.now), 0
                facts = replace(facts, silent=silent, queued=queued, pending=asked)
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
                "pending": asked,
                "page": facts.page,
                "runs": runs,
            }
        )
    return found


def settle(run: Pass, client: Client, world: World) -> None:
    """Settle the threads of each finished slug, and the subagent threads under them, once each.
    Archive each review thread whose pull request merged or closed, with the threads under it.

    `settle` skips a thread that is still at work, and the threads under it, until the next pass.
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
            for thread in t3.listed(client, run.project.project_id, titleContains=prefix):
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
        below = t3.listed(client, run.project.project_id, settled=False, includeSubagents=True)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the threads to settle could not be listed ({error})")
        return
    busy = {t["threadId"] for t in waiting if watch.at_work([t])}
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
            if parent in busy or watch.at_work([thread]):
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

    `resume` tells only the one thread of a slug that jbus launched and that the brief names on its
    `Thread:` line, and only while the slug has no pull request. `resume` counts a thread's
    carry-ons by the keys that `resume` wrote for them. When the count reaches `CARRY_ONS`, the
    thread's next end goes to the brief's home in one line, or is a gate where the brief has no
    home (`_stopped`). A new thread for the slug starts again from zero. A thread whose own run
    holds a test slot (`World.holding`) is at work, and gets no carry-on: jbus wakes it when the
    run ends (`slotwait.wake_ended`).
    """
    briefs = _briefs(run)
    sent = run.box.sent()
    for slug, live in sorted(world.threads.items()):
        thread, brief = live[0], briefs.get(slug, "")
        at, status, ended = thread["threadId"], thread["status"], thread.get("latestRunId")
        if len(live) > 1 or slug in run.gated or slug in world.open or slug in world.merged:
            continue
        if slug in run.limited:
            continue
        if status not in ENDED or not ended or thread.get("settled") or thread.get("snoozed"):
            continue
        if not dispatch.launched(run, slug) or mirror.last_result(brief):
            continue
        if parse.thread_of(brief) != at or jsettings.thread_id(at) in world.holding:
            continue
        key = f"resume|{slug}|{at}|{ended}"
        if key in sent:
            continue
        had = sum(one.startswith(f"resume|{slug}|{at}|") for one in sent)
        if had >= CARRY_ONS:
            _stopped(run, client, slug, (at, ended), status, brief)
            continue
        message = resume_message(
            CARRY_ON,
            str(thread.get("title", "")),
            run.home,
            status=status,
            slug=slug,
            k=had + 1,
            most=CARRY_ONS,
        )
        try:
            went = outbox.send(
                run,
                client,
                thread=at,
                row=slug,
                key=key,
                text=message,
                template="resume",
                needs="act",
            )
        except T3Refused as error:
            what = "T3 Code refused the carry-on"
            run.gate(slug, what, f"{error}\n\n{message}", key=f"{what} {at} {ended}")
            continue
        except T3Error as error:
            run.say(f"wait {slug}: its crew could not be told to carry on ({error})")
            continue
        if not went:
            continue
        line = f"resume {slug}: told the crew to carry on ({status}, {had + 1} of {CARRY_ONS})"
        run.find(slug, "resume", line, key=f"{at} {ended}")
        run.box.mark(key)
        run.say(line)


def _stopped(
    run: Pass, client: Client, slug: str, run_of: tuple[str, str], status: str, brief: str
) -> None:
    """Hand a thread that ended again after its last carry-on to the brief's home, in one line,
    once for the thread: the wait is the home's from there, not the user's. With no home to tell,
    it is a gate, once for the ended run, as before homes were told, and a line T3 Code refused
    is a gate once for the thread. A line that got no answer is sent again on the next pass."""
    at, ended = run_of
    what = f"thread ended {status} after two carry-ons"
    home = watch.home_thread(run, brief)
    key = f"stopped|{slug}|{at}"
    if home and key in run.box.sent():
        return
    if not home:
        run.gate(slug, what, at, key=f"{at} {ended}")
        return
    text = STOPPED.format(slug=slug, thread=at, status=status, most=CARRY_ONS)
    try:
        went = outbox.send(
            run,
            client,
            thread=home,
            row=slug,
            key=key,
            text=text,
            template="stopped",
            needs="decide",
        )
    except T3Refused as error:
        run.box.mark(key)
        run.gate(slug, what, f"{at}\n\nT3 Code refused its home the line: {error}", key=at)
        return
    except T3Error as error:
        run.say(f"wait {slug}: its home could not be told the crew stopped ({error})")
        return
    if not went:
        return
    run.box.mark(key)
    run.say(f"resume {slug}: told its home, thread {home}, that {at} {what}")


def merged(run: Pass, client: Client, world: World, rows: list[queue.Row]) -> None:
    """Tell the crew of each row whose pull request merged with work left for after the merge, once.

    `merged` sends to the thread that the brief names on its `Thread:` line, or else the thread that
    jbus launched for the slug, or else the thread that T3 Code lists. The outbox puts each thread
    it tells on `Pass.told`, as it does for every message that needs `act` (`jbus.outbox`).
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
        at = parse.thread_of(brief) or dispatch.launched(run, slug) or listed
        if not at or _done(run, key):
            continue
        message = resume_message(
            MERGED, f"crew: {slug}", run.home, number=pull["number"], slug=slug
        )
        try:
            went = outbox.send(
                run,
                client,
                thread=at,
                row=slug,
                key=key,
                text=message,
                template="merged-left",
                needs="act",
            )
        except T3Error as error:
            run.say(f"wait {slug}: its crew could not be told of the merge ({error})")
            continue
        if not went:
            continue
        run.box.mark(key)
        run.say(f"told {slug}: #{pull['number']} is merged, and its Result leaves work")


def tie(run: Pass, client: Client, world: World) -> None:
    dispatch.write_missing(run)
    link(run, client, world)
    settle(run, client, world)


def _out(half: Half) -> None:
    """List the crews out for the record, then run `stall.hung` over that list. The two run as one
    step, so that no rank can put `hung` before the list that `stall.hung` reads."""
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
