"""A home is woken from one list: the open items it owns that are new to it since its last wake.

The list is what the view already builds. It holds each entry of `state.wrongs` that an agent owns,
for the thread that `state.owner` names. Where the project's wakes go to its home thread, it also
holds each need of the user that the root home passes on (`blockers.deciding`). An item's key is
what the item is, with no run and no time in it: a red's failing tests where its run's log names
them, and a wrong's kind, subject and reason where it does not (`state.key_of`). A need keeps its
own key. One red is one item whatever runs or branches show it. `pick` takes, of the items that
one home thread owns, those that are new to it:

- an item that the home's own thread caused does not wake it. A row to approve is caused by the
  home whose brief it is, since a home queues only its own briefs (`queue.owned`);
- an item whose cause is another open item folds into that item: the stall of a row whose pull
  request is red folds into the red, and so does a red main into the red of its tip. The row
  that fixes the item is the exception. Its brief names the item (`Fix of:`, or the line it was
  queued from in its `Task:`), and a stall of a fix on the very red it fixes is news;
- an item that leaves the list wakes no one, since the keys a home has seen keep only the open
  ones, and a later return of the item is news again.

A pass sends each home thread at most one message, `wakes`, through the outbox, with the line of
each item that is new to it. `wakes.json` in the project's state is the one record of what a home
was told. It keeps, by thread, each open item's key with when it was told and its `state.key_of`,
which the view reads as what the owner was told (`state._fixing`). It also keeps the failing
tests of each red run that it read, so a log is read once.

Of the faults of a row, only those that no step that works the row tells are items here: a crew of
the root home's that hung at work, and a stalled row whose wait no clock takes to its home
(`jbus.clock`). A crew is told of its own work by the step that works it, as a crew's carry-on
(`jbus.rebase`, `jbus.expedite`), and what a thread asked or a reviewer wrote goes to its reader
as it is: neither is an item of the list.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbriefs import home as homes
from jbriefs.home import thread_of
from jbus import blockers, clock, outbox, read_json, verbs, write_json
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.threads import ROLES
from jbus.view import state
from jbus.view.github import RUNS, shaped
from jbus.watch import NOT_RED, _api, _failed_tests
from jmerge import mainjson

if TYPE_CHECKING:
    from jbus.cli import Half

FILE = "wakes.json"
KIND = "wakes"
CREW = next(role for role in ROLES if role.name == "crew")
MESSAGE = (
    "jbus: {count} new for this home in {project}, from the list of what is open:\n\n"
    "{lines}\n\n"
    "Fix each, or hand it to the thread whose work it is. A question only {user} can answer is a "
    "gate: take the default and pipe it to `jbus gate <slug>`. jbus tells this home of an item "
    "once while it stays open, and of nothing that leaves the list."
)
_QUOTED = re.compile(r'\bjbus "([^"]+)"')
_RUN_ID = re.compile(r"/actions/runs/(\d+)")


@dataclass(frozen=True)
class Item:
    """One open item of the list: its key, the thread that owns it (`to`), its line, the row it
    is about, the thread that caused it (`by`), the key of the open item that caused it (`of`),
    and the keys of the items its row is the fix of (`fixes`)."""

    key: str
    to: str
    line: str
    row: str = ""
    by: str = ""
    of: str = ""
    fixes: frozenset[str] = field(default_factory=frozenset)
    wrong: str = ""


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


def _clocked(found: state.Read, row: str) -> bool:
    """Whether the row's wait has a clock that takes it to the home (`jbus.clock`): one that has
    not reached the home yet, or one whose line went to the home."""
    wait = (found.table(clock.FILE) or {}).get(row)
    if not isinstance(wait, dict):
        return False
    sent = found.records(outbox.FILE) or []
    went = {line.get("key") for line in sent if line.get("went") == "sent"}
    return not wait.get("home") or clock.home_key(row, wait) in went


def _woken(found: state.Read, one: dict) -> bool:
    """Whether a wrong wakes its owner: a fault with no row, a hung crew, or a stalled row whose
    wait no clock takes to its home. Any other fault of a row, as a red check of a crew's pull
    request, is told by the step that works the row, and is on the list only as a cause."""
    if not one["row"]:
        return True
    return _hung(one) or (one["kind"] == state.STALLED and not _clocked(found, one["row"]))


class _Tests:
    """The failing tests of red runs, read once a run from its failed jobs' logs."""

    def __init__(self, run: Pass, kept: dict[str, list[str]]) -> None:
        self.run, self.kept, self.used = run, kept, {}

    def of(self, url: str) -> list[str]:
        number = _RUN_ID.search(url or "")
        if not number:
            return []
        run_id = number[1]
        if run_id not in self.kept:
            asked = _api(self.run, f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs")
            if not isinstance(asked, dict):
                return []
            jobs = [
                job
                for job in asked.get("jobs") or []
                if job.get("status") == "completed" and job.get("conclusion") not in NOT_RED
            ]
            failed = {test for job in jobs for test in _failed_tests(self.run, job.get("id"))}
            self.kept[run_id] = sorted(failed)
        self.used[run_id] = self.kept[run_id]
        return self.kept[run_id]


def red_key(tests: list[str]) -> str:
    """The key of a red by its failing tests: the same set is the same red on any branch."""
    return f"red|{hashlib.sha256('|'.join(sorted(tests)).encode()).hexdigest()[:12]}"


def line_of(one: dict) -> str:
    return f"{one['kind']} {one['subj']}: {one['cause']}"


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
    """The items of the list from `state.wrongs`: each with its key, its owner thread, and the
    open item its cause is."""
    wrongs = [one for one in found.once(state.wrongs) if one["owner"] != state.USER and one["to"]]
    keys: dict[int, str] = {}
    for at, one in enumerate(wrongs):
        failing = tests.of(_url(found, one)) if tests and one["kind"] == "ci" else []
        keys[at] = red_key(failing) if failing else state.key_of(one).rsplit("|", 1)[0]
    lines = {line_of(one): keys[at] for at, one in enumerate(wrongs)}
    ci = [one for one in wrongs if one["kind"] == "ci"]
    red_of = {one["row"]: keys[at] for at, one in enumerate(wrongs) if one["kind"] == "ci"}
    reds = [keys[at] for at, one in enumerate(wrongs) if one["kind"] == "ci"]
    main_red = next((key for key, one in zip(reds, ci, strict=True) if one["subj"] == "main"), "")
    items = []
    for at, one in enumerate(wrongs):
        cause = main_red if one["kind"] == "main" else ""
        if one["kind"] == state.STALLED:
            cause = red_of.get(one["row"], "")
        items.append(
            Item(
                key=keys[at],
                to=one["to"] if _woken(found, one) else "",
                line=line_of(one),
                row=one["row"],
                of=cause,
                fixes=_fixes(found, one["row"], lines),
                wrong=state.key_of(one),
            )
        )
    return items


def need_items(run: Pass, listed: list | None) -> list[Item]:
    """The needs of the user that the root home passes on: each item of the list that the user
    has to decide (`blockers.deciding`). A row to approve is caused by the home whose brief it
    is."""
    root = thread_of(run.home)
    if not root:
        return []
    items = []
    for one, said in blockers.deciding(run, listed):
        by = ""
        if one["kind"] == "approve":
            brief = run.home / "tasks" / f"{one['slug']}.md"
            text = brief.read_text(errors="replace") if brief.exists() else ""
            by = thread_of(homes.home_of(run.home, text)) if text else ""
        items.append(Item(key=one["key"], to=root, line=said, row=one.get("slug") or "", by=by))
    return items


def tell(run: Pass, client: Client, listed: list | None = None) -> None:
    """Send each home thread, at most once a pass, the open items it owns that are new to it."""
    record = read_json(run.state / FILE, {})
    tests = _Tests(run, record.get("tests", {}))
    found = read(run)
    needs = need_items(run, listed)
    items = wrong_items(found, tests) + needs
    owned = {
        one["to"]
        for one in found.once(state.wrongs)
        if one["owner"] == state.ROOT_HOME or one["owner"].startswith("home ")
    }
    threads = record.get("threads", {})
    for thread in sorted((owned | {one.to for one in needs}) - {""}):
        seen = threads.get(thread, {})
        new = pick(items, seen, thread)
        if new and _send(run, client, thread, new):
            threads[thread] = kept(items, seen, new, run.now.isoformat())
        else:
            threads[thread] = kept(items, seen, [], run.now.isoformat())
    write_json(run.state / FILE, {"threads": threads, "tests": tests.used})


def _send(run: Pass, client: Client, thread: str, new: list[Item]) -> bool:
    keys = "|".join(sorted(one.key for one in new))
    digest = hashlib.sha256(keys.encode()).hexdigest()[:12]
    text = MESSAGE.format(
        count=len(new),
        project=run.project.name,
        lines="\n".join(f"- {one.line}" for one in new),
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
