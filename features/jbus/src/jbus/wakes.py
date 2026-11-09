"""A home is woken from one list: the open items it owns that are new to it since its last wake.

The items are the entries of `state.wrongs` an agent owns, the needs a home passes on
(`blockers.deciding`), the leftovers a home has (`jbus.leftover`), the entries whose go holds
with no live row (`jbus.plan.owed`), the entries whose `Builds on:` merged with no row
(`jbus.plan.buildable`), the deferred lines of a home's plan (`jbus.prose`), the dated lines that
land in a home's notes (`jbus.notes`), the files that hold a standing rule (`jbus.rules`), and
the open alerts whose owner is the project (`jbus.alert`): an alert, a health incident, the
sign-in running out, a tool T3 Code stopped serving (`jbus.t3.contract`), a snapshot that failed,
a home that stalled. The hourly count of what is stale (`jbus.stale`) is one more, which wakes no
home: `jbus status` shows it, with each other item on the list for no home (`Item.quiet`).
The root home hears of a one-way door alone (`door`): every other item no row or scope has is the
catch-all's, `uncategorized` (`catchall_of`).
An item's key has no run and no time in it: a red's
failing tests, a wrong's kind, subject and reason (`state.key_of`), a need's own key. `pick` takes
the items one home thread owns that are new to it, less those whose cause is another open item,
unless the row is that item's fix.
An item that leaves the list wakes no one. A thread's record keeps each key it was told with a
digest of what it said, for `KEEP` after the item leaves the list, so an item told again in that
time wakes its home only when what it says changed.

A pass sends each home thread at most one `wakes` message through the outbox. Its retry key is
made from each item's key and digest, so an item whose words changed is a new message and not a
retry of the one before. `wakes.json` is the
one record of what a home was told, which the view reads too (`state._fixing`). It keeps the line
of each item open within `KEEP`, with when a pass last had it, which `jbus stale` reads.
A fault of a row that the step working the row tells, as a crew's carry-on, is on the list only as
a cause.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbriefs import home as homes
from jbriefs.home import thread_of
from jbus import (
    alert,
    blockers,
    clock,
    history,
    leftover,
    mirror,
    notes,
    outbox,
    party,
    plan,
    prose,
    queue,
    read_json,
    rules,
    stale,
    verbs,
    write_json,
)
from jbus.passes import Pass, side_by_side
from jbus.roles import ROLES
from jbus.t3 import Client, T3Error
from jbus.told import FILE, KIND, told_to
from jbus.view import state
from jbus.view.github import RUNS, shaped
from jbus.watch import NOT_RED, _api, _log_failed
from jmerge import mainjson

if TYPE_CHECKING:
    from jbus.poll import Half

UNREAD = "unread"
KEEP = timedelta(days=1)
CREW = next(role for role in ROLES if role.name == "crew")
MESSAGE = (
    "jbus: {count} new for this home in {project}, from the list of what is open:\n\n"
    "{lines}\n\n"
    "Fix each, or hand it to the thread whose work it is. A question only {user} can answer is a "
    "gate: take the default and pipe it to `jbus gate <slug>`. jbus tells this home of an item "
    "once while it stays open, and of nothing that leaves the list.{texts}"
)
OWED = (
    "The entry {entry} of {plan} has {user}'s go and no live row: its last row ended, and nothing "
    "is queued for the rest. Queue its next row (`jbus queue add <slug> --entry {entry}`, a "
    "scout's if it needs design, `--depends` for what it waits on), or close it with `jbus plan "
    "close {entry}{scope}` once nothing is left to do."
)
BRIEF = (
    "The entry {entry} of {plan} builds on {merged}, which merged, and has no row. Brief it and "
    "queue its first row (`jbus queue add <slug> --entry {entry}`, a scout's if it needs design, "
    "`--depends` for what it still waits on), or change its `Builds on:` line if it waits on more."
)
PROSE = (
    "A line of {file} defers an action on an event no code watches, so a home must remember "
    "this: make it a row with `--depends`, or delete the line."
)
NOTES = (
    "Dated lines in {file}: {dated}. {user}'s word of 2026-10-28 is that a home adds no entries "
    "there: a rule written there is read by no code and goes stale. Move each entry into the plan, "
    "a brief or code, and take it out of the file once it is moved. Deleting the file is a "
    "deletes-data door."
)
_QUOTED = re.compile(r'\bjbus "([^"]+)"')
_RUN_ID = re.compile(r"/actions/runs/(\d+)")


@dataclass(frozen=True)
class Item:
    """One open item: `to` owns it, `of` is the key of the item that caused it, and `fixes` the
    keys of the items its row is the fix of. A `quiet` item wakes no home, and `jbus status`
    shows it while it is open."""

    key: str
    to: str
    line: str
    row: str = ""
    of: str = ""
    fixes: frozenset[str] = field(default_factory=frozenset)
    wrong: str = ""
    text: str = ""
    quiet: bool = False


def words(one: Item) -> str:
    """The digest of what an item says, its line and its text, with no commit or time in them
    (`state.MOMENT`), as its key has none: a fault that only moves to a new commit says nothing
    new."""
    said = state.MOMENT.sub("", f"{one.line}\n{one.text}")
    return hashlib.sha256(said.encode()).hexdigest()[:12]


def pick(items: list[Item], seen: dict[str, Any], thread: str) -> list[Item]:
    """Return the items the thread owns that are new to it, each key once: not folded into another
    open item, and not told to it before with the same words. A key that two items share, as one
    red on two branches, is told while either says what was told. A record written before the
    digest was kept counts as the same words."""
    keys = {one.key for one in items}
    told = {
        one.key
        for one in items
        if one.key in seen and seen[one.key].get("said", words(one)) == words(one)
    }
    found: dict[str, Item] = {}
    for one in items:
        folded = one.of in keys and one.of != one.key and one.of not in one.fixes
        if one.to != thread or folded or one.key in told:
            continue
        found.setdefault(one.key, one)
    return list(found.values())


def kept(
    items: list[Item], seen: dict[str, Any], told: list[Item], now: datetime
) -> dict[str, Any]:
    """Return the thread's record after a wake: each open key it had seen, each it was told
    less than `KEEP` ago, and each told now."""
    keys, at = {one.key for one in items}, now.isoformat()
    record = {
        key: one
        for key, one in seen.items()
        if key in keys or now - datetime.fromisoformat(one.get("at") or at) < KEEP
    }
    return record | {one.key: {"at": at, "wrong": one.wrong, "said": words(one)} for one in told}


@dataclass(frozen=True)
class _Sources(state.Sources):
    """The view's sources of one project of a pass, whose home may have another name."""

    own: Path = Path()

    def home(self, name: str) -> Path:
        return self.own


def read(run: Pass) -> state.Read:
    """The project as the view reads it now. Its repo's runs are asked of GitHub in its checkout,
    as each call of the pass asks, so a repo the view has no `jmerge` line of is known too. Each
    completed attempt in the answer is kept in `runs.jsonl` (`jbus.history.runs`)."""

    def runs(repo: str) -> dict:
        said = _api(run, f"repos/{{owner}}/{{repo}}/actions/runs?per_page={RUNS}")
        history.runs(run.state, said, run.now)
        return shaped(said, run.now)

    sources = _Sources(run.state.parent, run.home.parent, user=run.user, own=run.home)
    found = state.Read(sources, run.project.name, run.now, runs)
    found.where = found.where or "{owner}/{repo}"
    return found


def _hung(one: dict) -> bool:
    """Whether the entry is a crew of the catch-all's, `uncategorized`, whose turn hung:
    `jbus.stall.hung` only logs it. A home's own thread is no crew,
    and a crew another child home owns is left to `jbus.children`, whose nudge to that home
    counts all it has out."""
    hung = one["cause"].startswith(state.QUIET_OR_HUNG["hung"])
    crew = one["subj"].startswith(CREW.prefix) and one["owner"] == f"home {homes.UNCATEGORIZED}"
    return one["kind"] == "thread" and hung and crew


def _woken(found: state.Read, one: dict) -> bool:
    """Whether a wrong wakes its owner: a fault with no row, a hung crew, or a stalled row whose
    wait no clock still works (`jbus.clock`). Any other fault of a row, as a red check of a crew's
    pull request, is told by the step that works the row, and is on the list only as a cause."""
    if not one["row"]:
        return True
    wait = (found.table(clock.FILE) or {}).get(one["row"])
    clocked = isinstance(wait, dict) and not wait.get("home")
    return _hung(one) or (one["kind"] == state.STALLED and not clocked)


class _Tests:
    """The failing tests of red runs, read once a run from its failed jobs' logs. A run whose
    tests cannot be read yet, its jobs or a failed job's log unanswered, is `UNREAD` for one pass,
    and its red waits that pass. Still unread a pass later, it is keyed with no tests, and keeps
    that key for its life, so one red never wakes a home twice."""

    def __init__(self, run: Pass, kept: dict[str, Any]) -> None:
        self.run, self.kept, self.used = run, kept, {}

    def of(self, url: str) -> list[str] | None:
        """Return the run's failing tests, or None while its red waits to have them read."""
        number = _RUN_ID.search(url or "")
        if not number:
            return []
        run_id = number[1]
        if self.kept.get(run_id, UNREAD) == UNREAD:
            read = self._read(run_id)
            if read is None and run_id not in self.kept:
                self.kept[run_id] = self.used[run_id] = UNREAD
                return None
            self.kept[run_id] = read or []
        self.used[run_id] = self.kept[run_id]
        return self.kept[run_id]

    def _read(self, run_id: str) -> list[str] | None:
        asked = _api(self.run, f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs")
        if not isinstance(asked, dict):
            return None
        red = [
            job.get("id")
            for job in asked.get("jobs") or []
            if job.get("status") == "completed" and job.get("conclusion") not in NOT_RED
        ]
        said = side_by_side(lambda job: _log_failed(self.run, job), red)
        if None in said:
            return None
        return sorted({test for one in said if one is not None for test in one.tests})


def red_key(tests: list[str]) -> str:
    """The key of a red by its failing tests: the same set is the same red on any branch."""
    return f"red|{hashlib.sha256('|'.join(sorted(tests)).encode()).hexdigest()[:12]}"


def _url(found: state.Read, one: dict) -> str:
    """The URL of the newest run whose failure the ci entry is."""
    checks = found.panel("checks")["checks"]
    runs = [run for run in checks.get("runs") or [] if isinstance(run, dict)]
    mine = [
        run
        for run in runs
        if run.get("branch") == one["subj"] and f"{run.get('name')} failed" == one["cause"]
    ]
    return max(mine, key=lambda run: run.get("created") or "", default={}).get("url", "")


def fixes(row: str, brief: str, lines: dict[str, str]) -> frozenset[str]:
    """The keys of the open items, by their lines, that a row is the fix of: the key its brief's
    `Fix of:` names, each item whose line its `Task:` quotes as from jbus, and a red main for a
    main-red row."""
    task = blockers.head(brief, "Task")
    named = {lines[said] for said in _QUOTED.findall(task) if said in lines}
    named |= {blockers.head(brief, blockers.FIX_OF)} - {""}
    if mainjson.fix_of(row):
        named |= {key for said, key in lines.items() if said.startswith("main ")}
    return frozenset(named)


def _fixes(found: state.Read, row: str, lines: dict[str, str]) -> frozenset[str]:
    if not row:
        return frozenset()
    brief = found.home / "tasks" / f"{row}.md"
    return fixes(row, brief.read_text(errors="replace") if brief.exists() else "", lines)


def wrong_items(found: state.Read, tests: _Tests | None) -> list[Item]:
    """The items of the list from `state.wrongs` that an agent is told of or status shows (a
    quiet item), each with the open item its cause is: a red main's is the red at its tip, and a
    stalled row's is its own red. A red whose tests are not
    read yet is on the list for no one this pass (`_Tests`), so what it causes still folds into
    it."""
    wrongs = [one for one in found.once(state.wrongs) if one["to"] or one["owner"] == state.STATUS]
    keys, lines, reds, unread = [], {}, {}, set()
    for one in wrongs:
        failing = tests.of(_url(found, one)) if tests and one["kind"] == "ci" else []
        unread |= {len(keys)} if failing is None else set()
        keys.append(red_key(failing) if failing else state.key_of(one).rsplit("|", 1)[0])
        lines[f"{one['kind']} {one['subj']}: {one['cause']}"] = keys[-1]
        if one["kind"] == "ci":
            reds[one["row"] or one["subj"]] = keys[-1]
    items = []
    for at, (key, one) in enumerate(zip(keys, wrongs, strict=True)):
        cause = {"main": "main", state.STALLED: one["row"]}.get(one["kind"])
        items.append(
            Item(
                key=key,
                to=one["to"] if at not in unread and _woken(found, one) else "",
                quiet=one["owner"] == state.STATUS,
                line=f"{one['kind']} {one['subj']}: {one['cause']}",
                row=one["row"],
                of=reds.get(cause, "") if cause else "",
                fixes=_fixes(found, one["row"], lines),
                wrong=state.key_of(one),
            )
        )
    return items


def root_of(run: Pass) -> str:
    """The root home's thread, or with none the top-level `home_thread` its wakes go to. It hears
    of a one-way door alone (`door`)."""
    return thread_of(run.home) or run.config.home_thread


def catchall_of(run: Pass) -> str:
    """The thread of the catch-all, `uncategorized`, which owns each item no row or scope has:
    the root's while the root stands in for it (`jbriefs.home.stands_in`)."""
    if homes.stands_in(run.home):
        return root_of(run)
    return thread_of(homes.catchall(run.home))


def door(one: dict[str, Any]) -> bool:
    """Whether a need of the user's is a one-way door, the one kind of item the root home hears
    of: a gate whose `Holds:` line names a case of `party.CASES`, a pull request `jmerge` holds
    for the user's word, or a setup only the user can give. A `Holds:` line is read as the rest of
    jbus reads it (`party.held`): one that names no case of the table holds for every door."""
    if one["kind"] in ("hold", "config"):
        return True
    holds = str(one.get("holds") or "").strip()
    return one["kind"] == "gate" and bool(holds) and bool(party.held(holds))


def need_items(run: Pass, listed: list | None) -> list[Item]:
    """The needs of the user that a home passes on: each item of the list that the user has to
    decide (`blockers.deciding`). A one-way door (`door`) is the root's (`root_of`). A row to
    approve is no thread's: a home approves a row on the user's word as it queues it (`queue add
    --message`), so a go still owed waits on the user alone, on `jbus needs` and the view. A
    stalled home's is no thread's either, since that home is the one that stalled, and nor is a
    T3 Code build to install, which no home can do. Any other need
    is the item of the home whose brief or scout's request its row is (`jbriefs.home`), as `jbus
    home` says: a gate with no case on its `Holds:` line. A gate a home asked itself
    (`mirror.asker`) wakes no thread: it is that home's question to the user, which `jbus needs`
    lists."""
    items = []
    for one, line in blockers.deciding(run, listed):
        slug = one.get("slug") or ""
        files = (run.home / kind / f"{slug}.md" for kind in ("tasks", "scouts"))
        brief = next((file for file in files if slug and file.exists()), None)
        if door(one):
            to = root_of(run)
        elif one["kind"] == "install":
            to = ""
        elif one["kind"] in ("approve", "stalled") or (
            one["kind"] == "gate" and slug == mirror.HOME
        ):
            to = ""
        else:
            text = brief.read_text(errors="replace") if brief else ""
            where = homes.home_of(run.home, text)
            to = catchall_of(run) if where == homes.catchall(run.home) else thread_of(where)
        items.append(Item(key=one["key"], to=to, line=line, row=slug))
    return items


def alert_items(run: Pass) -> list[Item]:
    """The open alerts whose owner is this project (`jbus.Config.owner`), each the item of the
    catch-all's thread (`catchall_of`), the machine's for the infra project only."""
    to = catchall_of(run)
    return [
        Item(key=f"alert|{one.key}", to=to, line=one.line)
        for one in alert.open_items(run.config.state_dir, run.now)
        if run.config.owner(one.owner) == run.project
    ]


def left_items(run: Pass) -> list[Item]:
    """The leftovers its home has (`jbus.leftover`), each the item of that home's thread alone:
    one its home leaves open is told to no other home."""
    items = []
    for slug, one in leftover.read(run.state).items():
        if one.why or one.busy or not one.thread:
            continue
        line = leftover.key_of(slug, one.left)
        items.append(Item(key=line, to=one.thread, line=line, row=slug, text=one.text))
    return items


def _plan_home(run: Pass, scope: str) -> str:
    """The thread of the home whose plan or notes a line is in: a scope's, or the catch-all's for
    the root's own, since the root home owns no row."""
    return thread_of(run.home / scope) if scope else catchall_of(run)


def owed_items(run: Pass, rows: list[queue.Row]) -> list[Item]:
    """The entries whose go holds with no live row (`plan.owed`), each the item of its home's
    thread (`_plan_home`)."""
    items = []
    for made in plan.owed(run.state, run.home, rows):
        key = plan.owed_key(made)
        line = f"{key}: go holds, no live row"
        where = f"the {made.scope} home's plan" if made.scope else "the root home's plan"
        flag = f" --scope {made.scope}" if made.scope else ""
        text = OWED.format(entry=made.entry, plan=where, user=run.user.user, scope=flag)
        items.append(Item(key, _plan_home(run, made.scope), line, made.entry, text=text))
    return items


def brief_items(run: Pass, rows: list[queue.Row]) -> list[Item]:
    """The entries ready to brief (`plan.buildable`), each the item of its home's thread
    (`_plan_home`)."""
    items = []
    for made in plan.buildable(run.home, rows):
        merged = ", ".join(made.merged)
        where = f"the {made.scope} home's plan" if made.scope else "the root home's plan"
        text = BRIEF.format(entry=made.entry, plan=where, merged=merged)
        line = f"{made.key()}: {merged} merged"
        thread = _plan_home(run, made.scope)
        items.append(Item(key=made.key(), to=thread, line=line, row=made.entry, text=text))
    return items


def prose_items(run: Pass) -> list[Item]:
    """The deferred lines of a home's plan written since the seed pass (`jbus.prose`),
    each the item of its home's thread (`_plan_home`)."""
    items = []
    for key, one in (prose.read(run.state) or {}).items():
        if one.seeded:
            continue
        line, text = f"{key}: {one.text}", PROSE.format(file=one.file)
        items.append(Item(key, _plan_home(run, one.scope), line, text=text))
    return items


def notes_items(run: Pass) -> list[Item]:
    """Each home's notes that hold a dated line (`jbus.notes`), the item of its home's thread
    (`_plan_home`), named by the newest new line."""
    items = []
    for key, one in notes.read(run.state).items():
        line = f"{key}: {one.last}"
        text = NOTES.format(file=one.file, dated=one.dated, user=run.user.user)
        items.append(Item(key, _plan_home(run, one.scope), line, text=text))
    return items


def rule_items(run: Pass) -> list[Item]:
    """The files of the project that hold a standing rule (`jbus.rules`), each the catch-all's
    (`catchall_of`)."""
    to = catchall_of(run)
    return [
        Item(
            key=f"{rules.KEY}:{path}",
            to=to,
            line=f"{rules.KEY} {path}",
            text=rules.TEXT.format(path=path, user=run.user.user),
        )
        for path in rules.found(run.config, run.project)
    ]


def stale_items(run: Pass) -> list[Item]:
    """The hourly count of what is stale, a quiet item while it is above none: it wakes no home,
    and `jbus status` shows it."""
    line = stale.line(run.project.name, stale.read(run.state))
    return [Item(key=stale.KEY, to="", line=line, quiet=True)] if line else []


def tell(run: Pass, client: Client, listed: list | None = None) -> None:
    """Send each home thread, at most once a pass, the open items it owns that are new to it."""
    record = read_json(run.state / FILE, {})
    tests = _Tests(run, record.get("tests", {}))
    found = read(run)
    items = wrong_items(found, tests) + need_items(run, listed) + left_items(run)
    try:
        rows = queue.load(run.state)
    except queue.Unparsable:
        pass
    else:
        items += owed_items(run, rows) + brief_items(run, rows)
    items += (
        prose_items(run) + notes_items(run) + rule_items(run) + alert_items(run) + stale_items(run)
    )
    threads = record.get("threads", {})
    for thread in sorted(({one.to for one in items} | set(threads)) - {""}):
        seen = told_to(record, thread)
        new = pick(items, seen, thread)
        told = new if new and _send(run, client, thread, new) else []
        threads[thread] = kept(items, seen, told, run.now)
    threads = {thread: seen for thread, seen in threads.items() if seen}
    lines = seen_lines(record.get("open"), items, run.now)
    quiet = sorted({one.line for one in items if one.quiet})
    record = {"threads": threads, "tests": tests.used, "open": lines, "quiet": quiet}
    write_json(run.state / FILE, record)


def seen_lines(was: Any, items: list[Item], now: datetime) -> dict[str, str]:
    """The line of each item open now, and of each open within `KEEP`, with when a pass last had
    it: a pass where a source gave no answer lists less, and its gap ends no line it left out."""
    kept = {
        line: at
        for line, at in (was if isinstance(was, dict) else {}).items()
        if isinstance(at, str) and now - datetime.fromisoformat(at) < KEEP
    }
    return kept | dict.fromkeys(sorted({one.line for one in items}), now.isoformat())


def _send(run: Pass, client: Client, thread: str, new: list[Item]) -> bool:
    """Send the thread its new items in one message, and count the streak of that thread's wakes:
    the root's is the project's `home thread` streak, and each other thread has its own."""
    streak = alert.home(run.project.name, "" if thread == root_of(run) else thread)
    keys = "|".join(sorted(f"{one.key}:{words(one)}" for one in new))
    digest = hashlib.sha256(keys.encode()).hexdigest()[:12]
    text = MESSAGE.format(
        count=len(new),
        project=run.project.name,
        lines="\n".join(f"- {one.line}" for one in new),
        texts="".join(f"\n\n{one.text}" for one in new if one.text),
        user=run.user.user,
    )
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=run.project.name,
            key=f"{KIND}|{run.project.name}|{digest}|{thread}",
            text=text,
            template=KIND,
            needs="act",
        )
    except T3Error as error:
        run.say(f"wait {run.project.name}: {thread} could not be woken ({error})")
        alert.count(run, streak, [f"T3 Code did not take the wake: {error}"])
        return False
    if went:
        alert.count(run, streak, [""])
        said = ", ".join(one.line for one in new)
        run.say(f"{KIND} {run.project.name}: told {thread} of {said}")
    return went


def _tell(half: Half) -> None:
    if half.client is not None:
        tell(half.run, half.client, half.listed)


STEPS = (verbs.Step("close", 27, "wakes.tell", _tell, ("sight", "client", "world", "budget")),)
