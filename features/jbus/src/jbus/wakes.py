"""A home is woken from one list: the open items it owns that are new to it since its last wake.

The items are the entries of `state.wrongs` an agent owns, the needs the root home passes on
(`blockers.deciding`), the leftovers a home has (`jbus.leftover`), the entries whose go holds
with no live row (`jbus.plan.owed`), the entries whose `Builds on:` merged with no row
(`jbus.plan.buildable`) and the deferred lines of a home's plan (`jbus.prose`). An item's key has
no run and no time in it: a red's failing
tests, a wrong's kind, subject and reason (`state.key_of`), a need's own key. `pick` takes the items
one home thread owns that are new to it, less those its own thread caused and those whose cause is
another open item, unless the row is that item's fix.
An item that leaves the list wakes no one, since a thread's record keeps only open keys.

A pass sends each home thread at most one `wakes` message through the outbox. `wakes.json` is the
one record of what a home was told, which the view reads too (`state._fixing`). A fault of a row
that the step working the row tells, as a crew's carry-on, is on the list only as a cause.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbriefs import home as homes
from jbriefs.home import thread_of
from jbus import (
    blockers,
    clock,
    leftover,
    outbox,
    plan,
    prose,
    queue,
    read_json,
    verbs,
    write_json,
)
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.threads import ROLES
from jbus.told import FILE, KIND, told_to
from jbus.view import state
from jbus.view.github import RUNS, shaped
from jbus.watch import NOT_RED, _api, _log_failed
from jmerge import mainjson

if TYPE_CHECKING:
    from jbus.cli import Half

UNREAD = "unread"
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
LATE = "Its home, thread {thread}, has not acted on it in {minutes} min since jbus told it."
_QUOTED = re.compile(r'\bjbus "([^"]+)"')
_RUN_ID = re.compile(r"/actions/runs/(\d+)")


@dataclass(frozen=True)
class Item:
    """One open item: `to` owns it, `by` caused it, `of` is the key of the item that caused it, and
    `fixes` the keys of the items its row is the fix of."""

    key: str
    to: str
    line: str
    row: str = ""
    by: str = ""
    of: str = ""
    fixes: frozenset[str] = field(default_factory=frozenset)
    wrong: str = ""
    text: str = ""


def pick(items: list[Item], seen: dict[str, Any], thread: str) -> list[Item]:
    """Return the items the thread owns that are new to it, each key once: not caused by the
    thread, not folded into another open item, and not among the keys it has seen."""
    keys = {one.key for one in items}
    found: dict[str, Item] = {}
    for one in items:
        folded = one.of in keys and one.of != one.key and one.of not in one.fixes
        if one.to != thread or one.by == thread or folded or one.key in seen:
            continue
        found.setdefault(one.key, one)
    return list(found.values())


def kept(items: list[Item], seen: dict[str, Any], told: list[Item], at: str) -> dict[str, Any]:
    """Return the thread's record after a wake: each open key it had seen, and each told now."""
    keys = {one.key for one in items}
    record = {key: one for key, one in seen.items() if key in keys}
    return record | {one.key: {"at": at, "wrong": one.wrong} for one in told}


@dataclass(frozen=True)
class _Sources(state.Sources):
    """The view's sources of one project of a pass, whose home may have another name."""

    own: Path = Path()

    def home(self, name: str) -> Path:
        return self.own


def read(run: Pass) -> state.Read:
    """The project as the view reads it now. Its repo's runs are asked of GitHub in its checkout,
    as each call of the pass asks, so a repo the view has no `jmerge` line of is known too."""

    def runs(repo: str) -> dict:
        return shaped(_api(run, f"repos/{{owner}}/{{repo}}/actions/runs?per_page={RUNS}"), run.now)

    sources = _Sources(run.state.parent, run.home.parent, user=run.user, own=run.home)
    found = state.Read(sources, run.project.name, run.now, runs)
    found.where = found.where or "{owner}/{repo}"
    return found


def _hung(one: dict) -> bool:
    """Whether the entry is a crew of the root home's whose turn hung: `jbus.stall.hung` only
    logs it. A home's own thread is no crew, and a crew a child home owns is left to
    `jbus.children`, whose nudge to that home counts all it has out."""
    hung = one["cause"].startswith(state.QUIET_OR_HUNG["hung"])
    crew = one["subj"].startswith(CREW.prefix) and one["owner"] == state.ROOT_HOME
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
        failed = set()
        for job in asked.get("jobs") or []:
            if job.get("status") != "completed" or job.get("conclusion") in NOT_RED:
                continue
            said = _log_failed(self.run, job.get("id"))
            if said is None:
                return None
            failed |= set(said.tests)
        return sorted(failed)


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
    """The items of the list from `state.wrongs`, each with the open item its cause is: a red
    main's is the red at its tip, and a stalled row's is its own red. A red whose tests are not
    read yet is on the list for no one this pass (`_Tests`), so what it causes still folds into
    it."""
    wrongs = [one for one in found.once(state.wrongs) if one["owner"] != state.USER and one["to"]]
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
                line=f"{one['kind']} {one['subj']}: {one['cause']}",
                row=one["row"],
                of=reds.get(cause, "") if cause else "",
                fixes=_fixes(found, one["row"], lines),
                wrong=state.key_of(one),
            )
        )
    return items


def root_of(run: Pass) -> str:
    """The root home's thread, or with none the top-level `home_thread` its wakes go to
    (`alert._thread`)."""
    return thread_of(run.home) or run.config.home_thread


def need_items(run: Pass, listed: list | None) -> list[Item]:
    """The needs of the user that the root home passes on: each item of the list that the user
    has to decide (`blockers.deciding`), but for a kind in `blockers.UNLISTED`. A row to approve
    is caused by the home whose brief it is. They wake the root's thread (`root_of`)."""
    root, items = root_of(run), []
    for one, said in blockers.deciding(run, listed):
        if one["kind"] in blockers.UNLISTED:
            continue
        brief = run.home / "tasks" / f"{one.get('slug')}.md"
        text = (
            brief.read_text(errors="replace") if one["kind"] == "approve" and brief.exists() else ""
        )
        by = thread_of(homes.home_of(run.home, text)) if text else ""
        items.append(Item(key=one["key"], to=root, line=said, row=one.get("slug") or "", by=by))
    return items


def left_items(run: Pass) -> list[Item]:
    """The leftovers its home has (`jbus.leftover`), each the item of that home's thread, and the
    root home's too once its home has not closed it in `leftover.CLOSE_MINUTES`."""
    root, items = root_of(run), []
    for slug, one in leftover.read(run.state).items():
        if one.why or one.busy or not one.thread:
            continue
        line = leftover.key_of(slug, one.left)
        items.append(Item(key=line, to=one.thread, line=line, row=slug, text=one.text))
        if root and leftover.late(one, run.now):
            key = leftover.key_of(slug, one.left, "left-late")
            text = leftover.raised(run, slug, one)
            items.append(Item(key=key, to=root, line=line, row=slug, text=text))
    return items


def owed_items(run: Pass, record: dict[str, Any], rows: list[queue.Row]) -> list[Item]:
    """The entries whose go holds with no live row (`plan.owed`), each the item of its home's
    thread, and the root home's too once its home has not acted on it in
    `leftover.CLOSE_MINUTES`, as a leftover is."""
    root, items = root_of(run), []
    for made in plan.owed(run.state, run.home, rows):
        key = plan.owed_key(made)
        line = f"{key}: go holds, no live row"
        thread = thread_of(run.home / made.scope) or root
        where = f"the {made.scope} home's plan" if made.scope else "the root home's plan"
        flag = f" --scope {made.scope}" if made.scope else ""
        text = OWED.format(entry=made.entry, plan=where, user=run.user.user, scope=flag)
        items += _with_late(run, record, root, Item(key, thread, line, made.entry, text=text))
    return items


def brief_items(run: Pass, rows: list[queue.Row]) -> list[Item]:
    """The entries ready to brief (`plan.buildable`), each the item of its home's thread."""
    root, items = root_of(run), []
    for made in plan.buildable(run.home, rows):
        merged = ", ".join(made.merged)
        where = f"the {made.scope} home's plan" if made.scope else "the root home's plan"
        text = BRIEF.format(entry=made.entry, plan=where, merged=merged)
        line = f"{made.key()}: {merged} merged"
        thread = thread_of(run.home / made.scope) or root
        items.append(Item(key=made.key(), to=thread, line=line, row=made.entry, text=text))
    return items


def prose_items(run: Pass, record: dict[str, Any]) -> list[Item]:
    """The deferred lines of a home's plan written since the seed pass (`jbus.prose`),
    each the item of its home's thread, and the root home's too once its home has not acted on it
    in `leftover.CLOSE_MINUTES`, as a leftover is."""
    root, items = root_of(run), []
    for key, one in (prose.read(run.state) or {}).items():
        if one.seeded:
            continue
        thread = (thread_of(run.home / one.scope) if one.scope else "") or root
        line, text = f"{key}: {one.text}", PROSE.format(file=one.file)
        items += _with_late(run, record, root, Item(key, thread, line, text=text))
    return items


def _with_late(run: Pass, record: dict[str, Any], root: str, one: Item) -> list[Item]:
    """The item, and the root home's item of it too once a home that is not the root was told of
    it `leftover.CLOSE_MINUTES` ago or more."""
    at = told_to(record, one.to).get(one.key, {}).get("at", "")
    if not at or one.to == root or not leftover.late(leftover.Record("", told=at), run.now):
        return [one]
    said = LATE.format(thread=one.to, minutes=leftover.CLOSE_MINUTES)
    return [one, replace(one, key=f"{one.key} late", to=root, text=f"{one.text} {said}")]


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
        items += owed_items(run, record, rows) + brief_items(run, rows)
    items += prose_items(run, record)
    threads = record.get("threads", {})
    for thread in sorted(({one.to for one in items} | set(threads)) - {""}):
        seen = told_to(record, thread)
        new = pick(items, seen, thread)
        told = new if new and _send(run, client, thread, new) else []
        threads[thread] = kept(items, seen, told, run.now.isoformat())
    threads = {thread: seen for thread, seen in threads.items() if seen}
    write_json(run.state / FILE, {"threads": threads, "tests": tests.used})


def _send(run: Pass, client: Client, thread: str, new: list[Item]) -> bool:
    keys = "|".join(sorted(one.key for one in new))
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
        return False
    if went:
        said = ", ".join(one.line for one in new)
        run.say(f"{KIND} {run.project.name}: told {thread} of {said}")
    return went


def _tell(half: Half) -> None:
    tell(half.run, half.client, half.listed)


STEPS = (verbs.Step("close", 27, "wakes.tell", _tell, ("sight", "client", "world", "budget")),)
