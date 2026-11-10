"""This module ties each crew to its thread, work that a home used to do by hand: the link and the
settle.

`link` links an open pull request to the thread that jbus launched for the pull request's branch, so
T3 Code shows the pull request in that thread. A review's findings reach the crew from
`jbus.reviewed`. `settle` archives the threads of a slug that is finished, and the subagent threads
under them, and only settles them while the slug still has work open. It settles every other idle
subagent thread whose parent has no run going. `resume` tells a crewmate to carry on when its
thread ended with no Result. `resume` does this twice at most, and after that it tells the
brief's home in one line. `merged` tells a crewmate to carry on, once, when its pull request
merged and its Result leaves work for after the merge. `out` lists every thread that is not
settled, whatever its title, with the role that its title gives it (`ROLES`) and its liveness.

Each action happens once, and a settle or an archive once per run of its thread. jbus records the
action's key in `sent.json`, beside the keys of the events, but only after T3 Code accepted the
call. So when an action got no answer, the next pass tries it again.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbriefs import findings, skills
from jbriefs.home import home_of, thread_of
from jbus import (
    END_TURN,
    cleanup,
    dispatch,
    mirror,
    outbox,
    questions,
    queue,
    rebase,
    record,
    review,
    stall,
    t3,
    verbs,
    watch,
    work,
)
from jbus.live import Facts, judge
from jbus.passes import Pass
from jbus.roles import PREFIXES, role_of, slug_in
from jbus.t3 import Client, T3Error, T3Refused
from jbus.watch import ENDED, STARTING, World, after_merge, at_work, closes, owes_pull, when

if TYPE_CHECKING:
    from jbus.poll import Half

EVENTS = {"resume": "quiet"}
RUNS = 20
TAIL = 100
REVIEW = "## Review"
CARRY_ON = (
    "jbus: this thread ended ({status}) before writing its Result. Carry on with your brief "
    "from where you stopped: read `tasks/{slug}.md` and your worktree's `git status` and "
    "`git log` first, keep what is committed, and do not start over. This is carry-on {k} of "
    "{most}."
)
OWES_PULL = (
    "jbus: this thread ended ({status}) with a Result that says `Status: done` and names no pull "
    "request, while its brief asks for one, so its row is not done. Open the pull request from "
    'what your worktree has committed, as the crew skill\'s "Do the task" says, and write a '
    "follow-up Result that names it: read `tasks/{slug}.md` first. jbus says this once."
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


def _done(run: Pass, key: str) -> bool:
    return run.box.has(key)


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


def _says_done(report: str) -> bool:
    """Say whether a scout's Report says `Status: done`, on its last `Status:` line, as the scout
    skill's own settle block reads it: the word after `Status:` is `done`, so `Status: done, but`
    is not."""
    said = [line.split()[1:2] for line in report.splitlines() if line.split()[:1] == ["Status:"]]
    return bool(said) and said[-1] == ["done"]


def over_scouts(run: Pass) -> set[str]:
    """Return each scout that is over: its last Report, a follow-up (`## Report, follow-up (…)`)
    as much as the first, says `Status: done`. Any other stays, as the scout skill's End keeps
    it."""
    over = set()
    for slug, text in _briefs(run, "scouts").items():
        reports = [body for heading, body in mirror.sections(text) if heading.startswith(REPORT)]
        if reports and _says_done(reports[-1]):
            over.add(slug)
    return over


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


def finished(run: Pass, world: World, reviews: set[str] | None = None) -> dict[str, set[str]]:
    """Return the slugs whose threads may be put away, by the start of such a thread's title.
    Given `reviews`, the slugs that have a reviewer's thread, only those are asked whether their
    reviewer is over.

    A task is over when its pull request merged, or when its last Result says `Status: done` and
    `Left: none`, names no pull request and names the row's `Outcome:` where its brief asks for a
    pull request (`watch.closes`). Under the crew skill, a thread that has something left
    stays where the user sees it. A reviewer is over when the brief's last Review has a verdict and
    either the reviewer's pull request merged or closed or the reviewer's task is over. A reviewer
    that stopped early stays. A scout is over when its last Report says `Status: done`. A slug
    removed from the queue (`Pass.removed`) is over, for its crew and its scout.
    """
    briefs = _briefs(run)
    tasks = (set(world.merged) - set(world.open)) | run.removed
    for slug, text in briefs.items():
        result = mirror.last_result(text)
        if (
            result
            and not closes(run, slug, text, result)
            and not owes_pull(run, slug, text, result)
            and slug not in world.open
        ):
            tasks.add(slug)
    ended = shut(world, briefs)
    reviewed = set()
    for slug in (tasks | ended) & set(briefs) & (set(briefs) if reviews is None else reviews):
        ran = [one.ran for one in findings.triage(briefs[slug]).sections]
        if ran and ran[-1]:
            reviewed.add(slug)
    return {
        "crew: ": tasks,
        "review: ": reviewed,
        "scout: ": over_scouts(run) | run.removed,
    }


def _silent(now: datetime, updated: Any) -> float | None:
    """Return the minutes since a thread last wrote, or None where T3 Code gave no time for it."""
    try:
        return (now - when(updated)).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def _tail(thread: str, items: Any) -> dict[str, Any]:
    """Return the arguments of a read that gives a thread's active run, the runs behind it and
    the last `TAIL` items of its timeline, each cut to one character, as `_subagents` needs them."""
    asked = {"threadId": thread, "view": "activity", "limit": TAIL, "maxCharsPerItem": 1}
    if type(items) is int and items > TAIL:
        asked["afterPosition"] = items - TAIL - 1
    return asked | {"runLimit": RUNS}


def _subagents(read: dict[str, Any]) -> str | None:
    """Return the `updatedAt` of the running subagent item a read gave that updated last, or None
    where the read gave none."""
    times = []
    for one in [one for one in read.get("items") or [] if isinstance(one, dict)]:
        if (one.get("type"), one.get("status")) == ("subagent", "running"):
            stamp = one.get("updatedAt")
            if not isinstance(stamp, str):
                continue
            try:
                times.append((when(stamp), stamp))
            except (TypeError, ValueError):
                continue
    return max(times)[1] if times else None


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

    A subagent's item updates in place: its status text and `updatedAt` move, the count of items
    does not. So where a read gives a subagent item that is still running, and that item updated
    later than `wrote`, `out` counts that update as the thread's last write. A scout that waits on
    its own subagents through a long run is not hung while they work. A subagent that finished
    writes nothing more, and a wake queued behind the turn moves no item, so neither counts.

    An answered request moves neither the count of items nor `updatedAt`, and T3 Code keeps no time
    for the answer. So a pass that reads a request count of 0, where the pass before kept one above
    0 and the count of items has not changed, counts the answer as the thread's last write, and
    `wrote` is the time of this pass. A thread that is not read, or that is read with no count,
    keeps the count the pass before kept. So a crew that waited on an approval for 17 minutes is
    not hung 3 minutes after the answer.

    `out` reads a thread only when the thread is `quiet` or `hung` by the listed data alone. The
    read gives the active run, when it started, the runs queued behind it, the requests that wait
    and the last `TAIL` items of the thread's timeline, each cut to one character, for the
    subagents. A pass with no quiet thread reads no thread. `out` also reads the threads in `also`,
    whatever their state.

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
    before = {one.get("id"): one for one in record.seen(run.config, run.project.name)}
    found = []
    for thread in sorted(listed, key=lambda t: str(t.get("createdAt", ""))):
        at, title = thread["threadId"], str(thread.get("title", ""))
        role, slug = role_of(title)
        items, was = thread.get("itemCount"), before.get(at, {})
        same = type(items) is int and was.get("items") == items and was.get("wrote")
        wrote = was["wrote"] if same else thread.get("updatedAt")
        silent = _silent(run.now, wrote)
        facts = Facts(str(thread.get("status", "")), silent)
        active, started, runs = None, None, None
        asked = was.get("pending") if same and type(was.get("pending")) is int else 0
        word = judge(facts).word
        if word in ("quiet", "hung") or at in also:
            try:
                read = client.call("t3_thread_read", _tail(at, items))
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
                for moved in (started, _subagents(read)):
                    since = _silent(run.now, moved)
                    if since is not None and (silent is None or since < silent):
                        wrote, silent = moved, since
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
                "runs": runs,
            }
        )
    return found


def _trees(run: Pass) -> dict[str, tuple[str, str]] | None:
    """Return each worktree of the checkout that is on a branch, as its path and its head by the
    branch, or None where git could not list them."""
    listed = run.run("git", "worktree", "list", "--porcelain")
    if listed.returncode:
        return None
    found = {}
    for block in listed.stdout.strip().split("\n\n")[1:]:
        lines = {
            key: value for key, _, value in (line.partition(" ") for line in block.splitlines())
        }
        if lines.get("branch") and lines.get("worktree"):
            found[lines["branch"].removeprefix("refs/heads/")] = (lines["worktree"], lines["HEAD"])
    return found


def _unsaved(run: Pass, world: World, slug: str, tree: tuple[str, str]) -> str:
    """Return why a slug's worktree holds work that would be lost, or nothing. Work is lost where
    the worktree has an uncommitted or untracked file, or a commit that no branch of origin has
    and that the head of its merged pull request does not hold."""
    path, head = tree
    status = run.run("git", "--no-optional-locks", "-C", path, "status", "--porcelain")
    if status.returncode or status.stdout.strip():
        return f"its worktree {path} has uncommitted work, or git could not say"
    left = run.run("git", "rev-list", "--count", head, "--not", "--remotes")
    if left.returncode == 0 and left.stdout.strip() == "0":
        return ""
    oid = str((world.merged.get(slug) or {}).get("headRefOid") or "")
    if oid and run.run("git", "merge-base", "--is-ancestor", head, oid).returncode == 0:
        return ""
    return f"its worktree {path} has a commit that is not pushed"


def held(run: Pass, world: World, slugs: set[str]) -> dict[str, str]:
    """Return, by slug, why each finished slug of `slugs` still has work open, so its threads are
    not archived: its row is not over (`queue.over`), as a `left` row is until its home closes it;
    an open row follows it (`Follows:`); a question or gate it asked (`jbus.questions`) waits for
    an answer; its last Result leaves work for after the merge; or its worktree holds uncommitted
    or unpushed work (`_unsaved`). A slug whose pull request is open is never finished
    (`finished`). Where the queue or the questions do not parse, or git cannot list the
    worktrees, every slug is held: nothing is archived on a guess."""
    try:
        rows = queue.load(run.state)
        asked = {
            one.slug
            for one in questions.read(run.state)
            if one.answer is None or one.answer.closed_by == questions.SILENCE
        }
    except (queue.Unparsable, questions.Unparsable):
        return dict.fromkeys(slugs, "its queue or its questions do not parse")
    briefs = _briefs(run)
    found: dict[str, str] = {}
    trees = _trees(run)
    branch = {row["slug"]: row.get("branch") or row["slug"] for row in rows}
    for row in rows:
        parent = queue.named_parent(row["slug"], briefs.get(row["slug"], ""))
        if parent in slugs and not queue.over(row):
            found.setdefault(parent, f"its follower {row['slug']} is open")
    for row in rows:
        if row["slug"] in slugs and not queue.over(row):
            found[row["slug"]] = f"its row is {row.get('status')}"
    for slug in slugs - set(found):
        tree = None if trees is None else trees.get(branch.get(slug, slug))
        if slug in asked:
            found[slug] = "a question it asked waits for an answer"
        elif after_merge(mirror.last_result(briefs.get(slug, ""))):
            found[slug] = "its Result leaves work for after the merge"
        elif trees is None:
            found[slug] = "git could not list the worktrees"
        elif tree:
            why = _unsaved(run, world, slug, tree)
            if why:
                found[slug] = why
    return found


def _ran(thread: dict[str, Any]) -> str:
    """Return the run that a settle or an archive of `thread` is keyed by: its latest run, or, for
    a subagent thread that has none, its count of items."""
    mark = thread.get("latestRunId") or thread.get("itemCount")
    return "" if mark is None else str(mark)


def _put_away(
    run: Pass, client: Client, thread: dict[str, Any], slug: str, actions: tuple[str, ...]
) -> bool:
    """Do each of `actions` (`settle`, `archive`) to `thread` that is not done for its run yet,
    and return whether none is left. The key of each holds the thread's run (`_ran`), so a
    thread that a message woke is due again once that run has ended, and a thread the user
    unsettled or unarchived with no run since is not. A thread listed settled counts as settled
    for its run. Before it acts, `_put_away` reads the thread, and leaves one that has a run
    going or a request waiting (`pendingRequestCount`), which T3 Code's list does not give."""
    at, ran = thread["threadId"], _ran(thread)
    due = []
    for action in actions:
        key = f"{action}d|{slug}|{at}|{ran}"
        if _done(run, key):
            continue
        if action == "settle" and thread.get("settled"):
            run.box.mark(key)
            continue
        due.append((action, key))
    if not due:
        return True
    name = slug or "a subagent"
    try:
        said = client.call("t3_thread_read", {"threadId": at, "limit": 1}).get("thread") or {}
    except T3Error as error:
        run.say(f"wait {name}: thread {at} could not be read ({error})")
        return False
    pending = said.get("pendingRequestCount")
    if said.get("activeRunId") or (type(pending) is int and pending > 0):
        return False
    for action, key in due:
        try:
            client.call("t3_thread_organize", {"action": action, "threadId": at})
        except T3Error as error:
            run.say(f"wait {name}: thread {at} could not be {action}d ({error})")
            return False
        run.box.mark(key)
        run.say(f"{action}d {name}: {thread.get('title') or 'a thread'} {at}")
    return True


def _clear(run: Pass, client: Client, thread: dict[str, Any], slug: str) -> None:
    """Clear the scratch of a crew whose thread is put away (`cleanup.clear_scratch`), once per
    run of the thread, as `_put_away` keys its actions. The key is recorded only once T3 Code
    named the thread's worktree, or said it has none, and nothing stayed behind, so a worktree
    in use is tried again on the next pass and a thread that a message woke is cleared again
    once that run ends."""
    at = thread["threadId"]
    key = f"cleared|{slug}|{at}|{_ran(thread)}"
    if _done(run, key):
        return
    tree = rebase.worktree(client, at)
    if cleanup.clear_scratch(run, slug, tree or "") and tree != "":
        run.box.mark(key)


def settle(run: Pass, client: Client, world: World) -> None:
    """Put away each thread that has no work left, on every pass, once per run of the thread.

    The threads of each finished slug (`finished`), and the subagent threads under them, are
    archived. A slug that still has work open (`held`) has its threads settled instead, and they
    wait for a pass that finds the work closed. Every other subagent thread, under a home, a
    crew that is not finished or a thread that is gone, is settled once it is idle and its
    parent has no run going. A home thread is never touched.

    Settle is a state that `settle` keeps, not an event it fires once: T3 Code unsettles a thread
    on any message that starts a run, whoever sends it, so a finished thread that a gate answer
    or a reload woke is put away again on the first pass after that run ends (`_put_away`).

    `settle` lists the threads once, settled or not and subagents too, so a thread that an
    earlier pass settled is archived by the same step once its slug is finished. A subagent thread
    whose parent jbus archived keeps its parent's slug through the parent's key in `sent.json`,
    since T3 Code no longer lists the parent.

    `settle` skips a thread that is still at work, settled or not, since T3 Code leaves a thread
    settled while it takes up a message, with the threads under it and the threads above it, so a
    running subagent keeps its parent too, until the next pass.
    Once a crew's thread is put away, its scratch folder goes, once per run of the thread
    (`_clear`).
    """
    slug_of: dict[str, str] = {}
    waiting: list[dict[str, Any]] = []
    try:
        every = t3.listed(client, run.project.project_id, includeSubagents=True)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the threads to settle could not be listed ({error})")
        return
    over = finished(run, world, {slug_in(str(t.get("title", "")), "review: ") or "" for t in every})
    below = [t for t in every if t.get("relationshipToParent") == "subagent"]
    for prefix in PREFIXES:
        for thread in every:
            slug = slug_in(str(thread.get("title", "")), prefix)
            if slug in over[prefix] and thread.get("relationshipToParent") != "subagent":
                slug_of[thread["threadId"]] = slug
                waiting.append(thread)
    busy = {t["threadId"] for t in waiting if watch.at_work([t], settled_too=True)}
    parents = dict(slug_of)
    for key in run.box.sent():
        action, slug, at, *_ = [*key.split("|"), ""]
        if action == "archived" and at:
            parents.setdefault(at, slug)
    grew = True
    while grew:
        grew = False
        for thread in below:
            parent = thread.get("parentThreadId")
            if thread["threadId"] in slug_of or parent not in parents:
                continue
            slug_of[thread["threadId"]] = parents[thread["threadId"]] = parents[parent]
            if parent in busy or watch.at_work([thread], settled_too=True):
                busy.add(thread["threadId"])
            waiting.append(thread)
            grew = True
    up = {t["threadId"]: t.get("parentThreadId") for t in waiting}
    for at in list(busy):
        while up.get(at) in slug_of and up[at] not in busy:
            at = up[at]
            busy.add(at)
    open_work = held(run, world, set(slug_of.values())) if slug_of else {}
    for thread in waiting:
        at, slug = thread["threadId"], slug_of[thread["threadId"]]
        if at in busy or role_of(str(thread.get("title", "")))[0] == "home":
            continue
        actions = ("settle",) if slug in open_work else ("settle", "archive")
        done = _put_away(run, client, thread, slug, actions)
        if done and str(thread.get("title", "")).startswith(watch.TITLE):
            _clear(run, client, thread, slug)
    by_id = {t["threadId"]: t for t in every}
    working: set[str] = set()
    for thread in every:
        at = thread["threadId"] if watch.at_work([thread], settled_too=True) else None
        while at in by_id and at not in working:
            working.add(at)
            one = by_id[at]
            at = (
                one.get("parentThreadId") if one.get("relationshipToParent") == "subagent" else None
            )
    for thread in below:
        at, parent = thread["threadId"], by_id.get(thread.get("parentThreadId"))
        if at in slug_of or at in working or thread.get("settled"):
            continue
        if parent and watch.at_work([parent], settled_too=True):
            continue
        slug = role_of(str(parent.get("title", "")))[1] if parent else ""
        _put_away(run, client, thread, slug, ("settle",))


def resume(run: Pass, client: Client, world: World) -> None:
    """Tell each crew whose thread ended with no Result to carry on, once per ended run, and each
    crew whose turn ended on a Result that still owes its pull request (`owes_pull`) to open it,
    once for the thread.

    `resume` tells only the one thread of a slug that jbus launched and that the brief names on its
    `Thread:` line, and only while the slug has no pull request. `resume` counts a thread's
    carry-ons by the keys that `resume` wrote for them. When the count reaches `CARRY_ONS`, the
    thread's next end goes to the brief's home in one line, or is a gate where the brief has no
    home (`_stopped`). A new thread for the slug starts again from zero. A thread whose turn ended
    on a wait that jbus owns (`World.awaits`), a test slot or its own run that holds one, gets no
    carry-on: jbus wakes it when a slot is free or the run ends (`slotwait`). Nor does a crew whose
    Result says its pull request opens after its review, while that review is to come
    (`review.awaited`): `jbus.prereview` tells it once the review is written.
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
        result = mirror.last_result(brief)
        owes = owes_pull(run, slug, brief, result)
        over = not at_work([thread]) if owes else status in ENDED
        if not over or not ended or thread.get("settled") or thread.get("snoozed"):
            continue
        if not dispatch.launched(run, slug) or (result and not owes):
            continue
        if thread_of(run.home, slug) != at or world.awaits(thread):
            continue
        if owes and review.awaited(brief, result):
            continue
        key = f"owes-pull|{slug}|{at}" if owes else f"resume|{slug}|{at}|{ended}"
        if key in sent:
            continue
        had = sum(one.startswith(f"resume|{slug}|{at}|") for one in sent)
        if not owes and had >= CARRY_ONS:
            _stopped(run, client, slug, (at, ended), status, brief)
            continue
        message = resume_message(
            OWES_PULL if owes else CARRY_ON,
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
        told = "open the pull request its brief asks for" if owes else "carry on"
        count = "once" if owes else f"{had + 1} of {CARRY_ONS}"
        line = f"resume {slug}: told the crew to {told} ({status}, {count})"
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
    home = thread_of(home_of(run.home, brief))
    key = f"stopped|{slug}|{at}"
    if home and run.box.has(key):
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
        at = thread_of(run.home, slug) or dispatch.launched(run, slug) or listed
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
    if half.client is not None:
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
