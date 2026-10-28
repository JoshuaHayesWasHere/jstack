"""What `/state.json` holds: the bus as one dict, read from the files the passes left.

The dict is a frame plus the keys each panel adds to it. A panel is one folder of `panels/`,
and its `panel.py` has its data: the function that builds its keys, the shape the keys are
cut to, and the sources the panel reads. This module has what the panels share. `Read` is
one project at one moment, and it reads each file once: the queue, what the last pass left,
and the logs. `Source` and `Spot` are what a panel declares. `build` puts the frame
(`FRAME`) and the panels of the first screen together, and `Read.asked` gives the answer
of one panel on its own.

Each call reads the files that the panels name in the project's state directory and in
its home's directory, and `pass.json` and `status.json` beside them. It also reads what
systemd says of the timer and the service, and the machine's state: its load, memory,
pressure, the file slots of `/tmp` and the plan's limits. It reads no config of jbus. The
projects are the directories of the state directory that have a `queue.json`, and a
project's home is the directory of its name. It also reads `leftover.json` where a pass
wrote one (`jbus.leftover`), and the log of what the outbox sent, `outbox.jsonl`
(`jbus.outbox`). It never opens the queue of events that waits for the home thread,
`outbox.json`, or the stored token, and it writes nothing. The one setting it takes is the
user's time zone (`jsettings`), and it reads a time with no zone as a time in that zone.

The line is `STEPS`, eleven steps from Queued to Merged. Each open row of the queue is a
task on one step. The holder of the task is the user, a crewmate, a reviewer, the check
runner, jbus, its home or another task. The view works out no state. The last pass judged
each row once (`jbus.work`) and wrote it to `work.json`, and the page draws a task as that
file has it: its value, its holder, what it waits for and the step of the line it is on. A
row that merged or is done and leaves nothing is off the line (`queue.over`). The view
writes the words for a state itself: the reason `jmerge` gave, the rows in front of the
task, the line of its gate, the whole note a Result leaves, and since when its home has a
leftover.

The view does not guess what the pass could not work out, and the pass did not guess
either. A value is `unknown` for a set of facts that no state covers, and a row that
`work.json` does not have is `unknown` too. An unknown task is on no step of the line. Its
step is `UNKNOWN`, and the dict has that step under `unknown`. It is a lane of its own,
and the page draws it only while a task is on it. The view names no holder for the task,
and gives the facts it has.

A task is in one state, `state`, and the page says that state: its kind (the value of
`work.json`), its name, its one sentence, and the one thing it waits for. Only open work is
in `tasks`. The pass may judge a row merged or done while the queue does not yet count the
row as over. Such a row is in `ended`. A task that cannot move says what holds it in
`blocked`: the task that blocks it, or a cause that is no task, with `by` empty. `blocks` has
how many tasks wait behind it. A task that the last pass did not confirm says so in
`unconfirmed`.

`threads` is every thread that the last pass saw and that is not settled: a crew's, a
scout's, a reviewer's, a home's or any other, each with its liveness (`jbus.live`). It is
null where the pass left no list. A null is a blind spot, never a count of none. A task
gives its own thread's liveness under `seen.live`. A pull request that has had no review
for `REVIEW_MINUTES`, with no reviewer's thread listed, says so. A task's `seen.reviewer` is
whether a reviewer's thread of its own is out, and null where the pass left no list.

jbus has stopped when the timer is not active, or when the last pass ended more than
`QUIET` seconds ago and systemd does not say that a pass is running now. A pass that starts
and fails each minute has stopped too, because only the end of a pass counts, and its start
does not. Each source says who writes it. A source that jbus writes stands as the last pass
left it. A source that the server reads itself is as it is now. A session's status line writes
the limits file, so the file is old whenever no session ran. The file gives its age, and its age
is no fault of jbus.

A pass that could not ask T3 Code or GitHub derives no row, and `pass.json` names the
source under `silent`. While `pass.json` names one, every task of that project says so in
`unconfirmed`: since which pass its row is not confirmed, and which source did not answer.
The plan's limits file is a source too, with the time a session last wrote it. A limit in
it whose reset time has passed is from a window that is over. Its use is not known, and the
view never gives it as a number.

`waiting` is the list of what waits on the user. An item that is a question jbus holds is
`answerable`. It has what its gate wrote, so that the page can answer it. That is its
`context` and its `options`. Each option has its `name`, what `follows` from it, whether it
is the `default` that the thread took, and whether the thread `recommended` it. The item
also has what the thread `built_on` the default and how to `undo` it. Last, it has who
asked: the `slug`, the `thread` an answer goes to and that thread's `role` (`asker`). A
gate that is only in a home's `gates.md` is not answerable.

`items` is each live work item of the project (`jbus.item`) and the `ENDED` items that
ended last, in the order of their numbers. Each has its `id`, `slug`, `title`, `state`,
`owner`, `risk`, `last_event` and its last `ITEM_LINES` lines, oldest first. A go names
the `last_event` as the line it saw.

`jbus.code` says which code of the view serves requests: when the server started, and whether a
file it runs is newer on disk than that start.

The dict has the keys that `keys` gives and no other. The view builds each key from named
fields and cuts it to its panel's shape. Every time in the dict is UTC, in the
ISO 8601 form.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import cached_property
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jsettings
from jbriefs import below
from jbriefs import home as jbriefs
from jbriefs import parse as briefs
from jbus import (
    current_level,
    expedite,
    item,
    leftover,
    merge,
    mirror,
    old_names,
    outbox,
    questions,
    queue,
    read_json,
    waiting,
    work,
)
from jbus.live import LIVENESS, OUT
from jbus.roles import OTHER, ROLES
from jbus.roles import shown as shown_roles
from jbus.threads import REPORT
from jbus.told import FILE as TOLD
from jbus.told import KIND as TOLD_KIND
from jbus.told import told_to
from jbus.view import panels
from jbus.view.clean import ANY, HOST, keep
from jbus.view.homes import GROUP, Homes
from jbus.wake import LOG
from jmerge import budget as allowance
from jmerge import mainjson

APPROVAL = 400
HISTORY, TASK_EVENTS, LINE, NOTE = 40, 8, 300, 4000
REVIEW_MINUTES = 10
NO_REVIEWER = "no reviewer has started"
NO_REVIEW = "no review yet"
WHOLE = NOTE + 2 * LINE
WORDS = 600
ITEM_LINES, ENDED = 5, 20
FRAME = ("at", "project", "projects", "repo", "sources", "summary", "kinds", "roles", "items")
_PULL = re.compile(rf"https://{re.escape(HOST)}/([\w.-]+/[\w.-]+)/pull/\d+")
_LOGGED = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d) (.+)$")
_STAMP = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d)(?: \S+)?")
_SHA = re.compile(r"[0-9a-f]{7,40}")
_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")
LEFT = "left: "
ENDS = (
    "Either of two things ends it: a new task for what was left, "
    "a Left: none line in its brief once you say the rest is not wanted"
)
HOME = "home"
CLOSES = (
    "The home closes it: a follow-up task for what was left, "
    "or a Left: none line in its brief with the reason"
)
READY = {
    "no slot": "a slot",
    "dispatch is off": "dispatch to be turned on",
    "the stop file is there": "the stop file to go",
}
DEPENDS = "depends on "
SAYS = {
    "launching": "a thread was started and has not reported yet",
    "working": "the thread is working",
    "quiet": "its thread has written nothing for a while",
    "hung": "its turn has written nothing, and may be hung",
    "waiting": "the thread waits on a request",
}
LOST = {
    "none": "its thread is gone and wrote nothing",
    "settled": "its thread was settled and wrote nothing",
    "archived": "its thread was archived and wrote nothing",
    "missing": "T3 Code has no such thread, and it wrote nothing",
    "completed": "its thread ended and wrote nothing back",
    "failed": "its thread ended early and wrote nothing back",
}
UNKNOWN_WAITS = work.UNKNOWN.waits
NOT_CONFIRMED = "not confirmed: the last pass judged it from what it could not ask"
PULLED = frozenset(str(one) for one in work.STEPPED)
GONE = frozenset(
    str(one)
    for one in (work.Thread.FAILED, work.Thread.SETTLED, work.Thread.ARCHIVED, work.Thread.MISSING)
)
BROKEN, ASKS, WORKS, WAITS, QUEUED, OVER = range(6)
RANK = {
    "hung": BROKEN,
    "lost": BROKEN,
    "closed": BROKEN,
    "unknown": BROKEN,
    "asking": ASKS,
    "waiting": ASKS,
    "leftover": ASKS,
    "unapproved": ASKS,
    "hold": ASKS,
    "quiet": WORKS,
    "launching": WORKS,
    "working": WORKS,
    "result": WORKS,
    "findings": WORKS,
    "rebase": WORKS,
    "review": WAITS,
    "second": WAITS,
    "check": WAITS,
    "behind": WAITS,
    "ready": QUEUED,
    "removed": OVER,
    "merged": OVER,
    "done": OVER,
}
if unranked := set(work.VALUES) - set(RANK):
    raise ValueError(f"RANK does not rank {sorted(unranked)}: add each to a group")
LIVE_AS = {
    "hung": "hung",
    "waiting": "waiting",
    "quiet": "quiet",
    "moving": "working",
    "unknown": "unknown",
    "ended": "done",
}
BLOCKED = {
    "unapproved": "approval",
    "lost": "thread",
    "hung": "thread",
    "findings": "findings",
    "check": "check",
    "hold": "hold",
}


@dataclass(frozen=True)
class Step:
    """One step of the line: its lane, who has a task on it, and what the task waits for."""

    key: str
    name: str
    who: str
    note: str
    group: str = ""


STEPS = (
    Step("queued", "Queued", "", "not approved, behind another task, or ready to launch", "Before"),
    Step("running", "Running", "crew", "a crewmate thread has the task", "Work"),
    Step("gate", "Gate", "user", "a question only you can answer"),
    Step("result", "Result", "crew", "the brief needs a Result that names it", "Pull request"),
    Step("review", "Review", "rev", "a reviewer reads it"),
    Step("findings", "Findings", "crew", "the crewmate handles the findings"),
    Step("second", "Second pass", "rev", "the content moved past its review"),
    Step("check", "Check", "ci", "its check failed, runs or waits for a runner, or passed"),
    Step("rebase", "Rebase", "crew", "main moved under it, or a rebase dropped lines"),
    Step("hold", "Needs you", "user", "jmerge will not merge it until you say"),
    Step("merged", "Merged", "ok", "merged today", "Done"),
)
UNKNOWN = Step("unknown", "Unknown", "unknown", "the view cannot work out its state")
STEP = {step.key: step for step in (*STEPS, UNKNOWN)}


@dataclass(frozen=True)
class Sources:
    """The places the view reads from. Only a test names a place other than the machine's."""

    state_dir: Path
    home_dir: Path
    proc: Path = Path("/proc")
    limits: Path | None = None
    tmp: Path = Path("/tmp")
    user: jsettings.Settings = jsettings.DEFAULTS

    def state(self, name: str) -> Path:
        return self.state_dir / name

    def home(self, name: str) -> Path:
        return self.home_dir / name


def iso(moment: datetime) -> str:
    return jsettings.stamp(moment)


def when(given: Any, user: jsettings.Settings = jsettings.DEFAULTS) -> str | None:
    """A time as a file has it, given as UTC, or None for any other value.

    A file may have a time as ISO 8601 writes it, seconds since 1970, or the stamp of a
    pass. A stamp is `YYYY-MM-DD HH:MM`, with or without the word of its zone, and it is a
    time in the user's zone."""
    try:
        if isinstance(given, int | float) and not isinstance(given, bool):
            return iso(datetime.fromtimestamp(given, UTC))
        if not isinstance(given, str) or not given:
            return None
        stamped = _STAMP.fullmatch(given)
        if stamped:
            return iso(user.local(datetime.fromisoformat(stamped[1])))
        moment = jsettings.when(given)
        return iso(moment if moment.tzinfo else user.local(moment))
    except (ValueError, OverflowError, OSError):
        return None


def text(given: Any, cap: int = LINE) -> str:
    return given[:cap] if isinstance(given, str) else ""


def by_rule(row: queue.Row) -> dict[str, str] | None:
    """The rule and the parent of a row approved by the follow-up rule. The page
    marks the row with them. The function gives None for a row the user gave their own word
    for, and for a row with no approval."""
    made = queue.record(row)
    if not made or made.basis != queue.RULE:
        return None
    return {"rule": text(made.ref, 20), "follows": text(made.follows, 80)}


def count(given: Any) -> int:
    return given if isinstance(given, int) and not isinstance(given, bool) else 0


def projects(sources: Sources) -> list[str]:
    """The projects jbus looks after, as the files it left show: each directory with a
    `queue.json`."""
    try:
        found = [
            path.name for path in sources.state_dir.iterdir() if (path / "queue.json").is_file()
        ]
    except OSError:
        return []
    return sorted(found)


def repo(sources: Sources, name: str) -> str:
    """The project's repo on GitHub, `<owner>/<name>`, or nothing where `jmerge` logged no
    such line. The function finds the newest pull request for which `jmerge` logged a `wait`
    or a `hold`, and takes that pull request's repo. It reads the repo from the URL that names
    the pull request in that line. A URL inside a line's reason names no repo."""
    for logged in reversed(_lines(sources.home(name) / "merge.log") or []):
        stamped = _LOGGED.match(logged)
        line = merge.parse(stamped[2]) if stamped else None
        found = _PULL.fullmatch(line.name) if line and line.word in ("wait", "hold") else None
        if found:
            return found[1]
    return ""


def pulls(sources: Sources, name: str) -> dict[str, int | None]:
    """Each slug of the project's queue, with the number of its pull request or None. The
    number is the one the slug's row names. Where the row names none, the number is the one of
    the pull request that `merge.log` says merged for the slug."""
    landed = _landed(_lines(sources.home(name) / "merge.log") or [], sources.user)
    return {
        row["slug"]: number
        if (number := _number(row)) is not None
        else landed.get(row["slug"], (None,))[0]
        for row in _rows(sources.state(name)) or []
    }


def _number(row: queue.Row) -> int | None:
    number = text(row.get("pr")).removeprefix("#")
    return int(number) if number.isdigit() else None


def _rows(state: Path) -> list[queue.Row] | None:
    try:
        return sorted(queue.load(state), key=queue.order)
    except (queue.Unparsable, OSError):
        return None


def _lines(path: Path) -> list[str] | None:
    try:
        return path.read_text(errors="replace").splitlines()
    except OSError:
        return None


def _records(path: Path) -> list[dict[str, Any]] | None:
    """The lines of a `.jsonl` file that are a record. It leaves out every other line."""
    lines = _lines(path)
    if lines is None:
        return None
    found = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            found.append(record)
    return found


def _table(path: Path) -> dict[str, Any] | None:
    kept = read_json(path, None)
    return kept if isinstance(kept, dict) else None


def _history(lines: list[str], user: jsettings.Settings) -> dict[int, list[dict[str, str]]]:
    """What `jmerge` logged of each pull request, oldest first: the time, the word, the step
    and the reason's code of each line. A line from before the codes has an empty code, and
    its step comes from its reason's text (`merge.step`)."""
    found: dict[int, list[dict[str, str]]] = {}
    for logged in lines:
        stamped = _LOGGED.match(logged)
        line = merge.parse(stamped[2]) if stamped else None
        at = when(stamped[1], user) if stamped else None
        if line is None or at is None or line.word not in ("wait", "hold", "merged"):
            continue
        if line.word == "merged":
            step, reason = "merged", ""
        else:
            step = merge.step(f"{line.word}: {line.reason}", line.code)
            reason = line.reason if step else f"jmerge said: {line.reason}"
            step = step or UNKNOWN.key
        found.setdefault(line.number, []).append(
            {"at": at, "word": line.word, "step": step, "code": line.code, "reason": text(reason)}
        )
    return found


def _stay(history: list[dict[str, str]], step: str) -> tuple[str | None, int]:
    """Since when a pull request is on its step, and how many times it came to that step."""
    since, visits, last = None, 0, ""
    for one in history:
        if one["step"] == step and last != step:
            since, visits = one["at"], visits + 1
        last = one["step"]
    return (since if last == step else None), visits


def _landed(lines: list[str], user: jsettings.Settings) -> dict[str, tuple[int, str]]:
    """The last pull request that `jmerge` logged as merged for each slug, and when."""
    found = {}
    for logged in lines:
        stamped = _LOGGED.match(logged)
        line = merge.parse(stamped[2]) if stamped else None
        at = when(stamped[1], user) if stamped else None
        if line and at and line.word == "merged" and _SLUG.fullmatch(line.name):
            found[line.name] = (line.number, at)
    return found


def _said(
    kind: str, name: str, say: str, waits: str, row: str = "", cap: int = LINE
) -> dict[str, str]:
    return {
        "kind": kind,
        "name": name,
        "say": text(say, cap),
        "waits": text(waits),
        "row": text(row),
    }


def _whole(state: Path, home: Path, slug: str) -> tuple[str, str]:
    """The whole `Status:` line and the whole `Left:` line of the last Result of a slug's
    brief, or nothing for a brief the view cannot read."""
    if not _SLUG.fullmatch(slug):
        return "", ""
    for path in (home / "tasks" / f"{slug}.md", state / "briefs" / f"{slug}.md"):
        try:
            result = mirror.last_result(path.read_text(errors="replace"))
        except OSError:
            continue
        return below.line(result, "Status:"), below.line(result, "Left:")
    return "", ""


@dataclass(frozen=True)
class Held:
    """What `leftover.json` has of a row that ended with something left.

    `note` is the whole `Left:` line. `told` is the time when jbus told the row's home,
    written as the user reads a time. It is nothing while jbus has not told the home. `since`
    is the same time as `told`, in the form the answer's dicts give a time. `his` is why the
    row is the user's, or nothing while the row is its home's. `busy` is whether a thread was
    at work on the row in the last pass."""

    note: str
    told: str
    since: str | None
    his: str
    busy: bool


def _held(record: leftover.Record, now: datetime, user: jsettings.Settings) -> Held:
    since = when(record.told)
    told = user.stamp(datetime.fromisoformat(since)) if since else ""
    return Held(record.left, told, since, leftover.his(record, now), record.busy)


def _how(row: queue.Row, merged: bool) -> tuple[str, int | None]:
    """How a row ended, in a few words, and the number of its pull request."""
    number = _number(row)
    if merged:
        return f"its pull request{'' if number is None else f' #{number}'} is merged", number
    if number is None:
        return "it ended with no pull request", None
    return f"its thread ended and its pull request #{number} is not merged", number


def _leftover(
    row: queue.Row, value: str, merged: bool, result: tuple[str, str], his: str = ""
) -> tuple[str, str, str]:
    """What the view says of a row that ended with something left, or whose pull request
    closed: its name, its sentence and what it waits for.

    The work is finished where the row's last Result says `Status: done`, its reason is a
    note, and none of its pull requests is left unmerged. The sentence then says how the work
    ended. It also gives the crewmate's whole note, as the brief has it. It also gives the
    two things that end the work. Any other such row is not closed, and its sentence gives
    the note or the reason the row has. Where the view read a `Status:` that is not `done`,
    the sentence also says that the brief does not say the work is finished. A row with a
    home to tell may still wait on the user, and `his` says why (`leftover.his`). The
    sentence gives that reason after the note.
    """
    status, whole = result
    why = text(row.get("why"))
    ended, number = _how(row, merged)
    noted = why.startswith(LEFT)
    yours = f". It waits on you: {his}" if his else ""
    note = whole if whole and whole.lower() != "none" else why.removeprefix(LEFT)
    note = text(note, NOTE).rstrip(". ")
    if value == "leftover" and noted and status == "done" and (merged or number is None):
        said = "Its crewmate left a note of something it did not do"
        say = f"{ended} and the work is done. {said}: {note}{yours}. {ENDS}"
        return "Ended, with a leftover", say, "your word on that note"
    if status and status != "done":
        ended += ", and its brief does not say the work is finished"
    say = f"{ended}. Its crewmate left a note: {note}{yours}" if noted else f"{ended}: {why}"
    name = "Ended, not closed" if value == "leftover" else "Closed"
    return name, say, "your word on how it ends"


def _homes(row: queue.Row, merged: bool, held: Held) -> str:
    """What the view says of a row that ended with something left, when the row is its
    home's to close: how the row ended, the whole note, since when the home has had it, and
    that the home closes it."""
    ended = _how(row, merged)[0]
    note = text(held.note, NOTE).rstrip(". ")
    return f"{ended}. Its crewmate left a note: {note}. jbus told its home {held.told}. {CLOSES}"


@dataclass(frozen=True)
class About:
    """What the view knows of a row besides its state, to put the state in words.

    It has four things. They are the rows in front of the row that are not merged or done,
    and the line of the row's gate in the list the last pass left. They are also what the
    row's brief's last Result says, and what `leftover.json` has of the row."""

    blockers: list[str]
    asked: str
    result: tuple[str, str]
    held: Held | None


def _saying(row: queue.Row, line: dict[str, Any] | None, about: About) -> dict[str, str]:
    """The state of a row as the page says it. The value, the holder and what the row waits
    for come from the pass, in `work.json` (`line`). This function works out the words. A
    row that the last pass did not judge is `unknown`, and gets what its row in the queue
    says."""
    why = text(row.get("why"))
    status = text(row.get("status")) or "queued"
    says = f"the row says {status}" + (", approved" if row.get("approved") else "")
    if line is None:
        say = "the last pass did not judge it: work.json does not have it"
        return _said(UNKNOWN.key, UNKNOWN.name, say, UNKNOWN_WAITS, says)
    value, facts = line["value"], line["facts"]
    name, waits = text(line.get("name"), 60), text(line.get("waits"))
    merged = facts.get("pull") == "merged"
    say = why
    if value in PULLED:
        say = why.partition(": ")[2] or why
    elif value == "unknown" and status == "pr":
        reason = why.partition(": ")[2]
        say = f"jmerge said: {reason}" if reason else "jmerge has said nothing of it yet"
    elif value == "unknown":
        shown = ", ".join(f"{facet} {said}" for facet, said in facts.items())
        say = f"no state holds for what the pass saw: {shown}"
    elif value == "asking":
        say = about.asked or why or STEP["gate"].note
    elif value == "unapproved":
        say = why if row.get("approved") else "nobody has approved it"
    elif value == "behind":
        first = (about.blockers or [why.removeprefix(DEPENDS)])[0]
        many = len(about.blockers) > 1
        say = f"{', '.join(about.blockers) or first} {'come' if many else 'comes'} first"
        waits = f"{first} to merge"
    elif value == "ready":
        say, waits = (why, READY[why]) if why in READY else ("nothing is in front of it", waits)
    elif value in SAYS:
        say = why or SAYS[value]
    elif value == "lost":
        say = LOST.get(facts.get("thread", ""), LOST["completed"])
    elif value in ("leftover", "closed") and line.get("who") == HOME and about.held:
        say = _homes(row, merged, about.held)
    elif value == "leftover" and line.get("who") == "crew":
        say = why
    elif value in ("leftover", "closed"):
        his = about.held.his if about.held else ""
        name, say, waits = _leftover(row, value, merged, about.result, his)
        return _said(value, name, say, waits, cap=WHOLE)
    elif value == "merged":
        say = _how(row, True)[0]
    elif value == "done":
        say = "it ended with no pull request, and its Result says the work is done"
    if value == UNKNOWN.key:
        waits = UNKNOWN_WAITS
    return _said(value, name, say, waits, cap=WHOLE)


def _tasks(
    rows: list[queue.Row],
    history: dict[int, list[dict[str, str]]],
    judged: dict[str, dict[str, Any]],
    asked: dict[str, str],
    moves: list[dict[str, Any]],
    events: list[dict[str, Any]],
    seen: dict[str, Any],
    user: jsettings.Settings,
    results: Callable[[str], tuple[str, str]],
    out: list[dict[str, Any]] | None,
    now: datetime,
    unconfirmed: dict[str, Any] | None = None,
    held: dict[str, leftover.Record] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The open work of the queue, and the rows that ended while their row in the queue
    says another thing. Each row is in the state that the last pass judged for it. `judged`
    is the rows of `work.json` by slug.

    `out` is the threads the last pass listed (`_threads`), or None where it left no list.
    `held` is the record `leftover.json` has of each row that ended with something left.
    `unconfirmed` is what every row says while the last pass could not ask a source. A row
    whose state the last pass did not confirm says so by itself."""
    crews: dict[str, list[dict[str, Any]]] = {}
    for one in out or []:
        if one["role"] == "crew":
            crews.setdefault(one["slug"], []).append(one)
    reviewed = {one["slug"] for one in out or [] if one["role"] == "reviewer"}
    reviewing = {one["slug"] for one in out or [] if one["role"] == "reviewer" and one["out"]}
    status = {row["slug"]: text(row.get("status")) or "queued" for row in rows}
    through = {slug for slug, line in judged.items() if line.get("who") == "ok"}
    tasks, ended = [], []
    for row in rows:
        slug, state = row["slug"], text(row.get("status")) or "queued"
        line = judged.get(slug)
        if queue.over(row) and (line is None or line.get("who") == "ok"):
            continue
        number = _number(row)
        logged = history.get(number, []) if number is not None else []
        depends = [
            {
                "slug": text(one),
                "state": f"{judged[one]['value']}, and its row says {status[one]}"
                if one in through and one in status
                else status.get(one, "not in the queue"),
            }
            for one in row.get("depends", [])
        ]
        holds = [one for one in row.get("depends", []) if status.get(one) not in queue.FINAL]
        blockers = sorted(map(text, holds), key=lambda one: one in through)
        watched = seen.get(slug) if isinstance(seen.get(slug), dict) else {}
        has = _held(held[slug], now, user) if held and slug in held else None
        value = line["value"] if line else UNKNOWN.key
        about = About(
            blockers,
            asked.get(slug, ""),
            results(slug) if value in ("leftover", "closed") else ("", ""),
            has,
        )
        said = _saying(row, line, about)
        step = text(line.get("lane"), 20) if line else ""
        step = step if step in STEP else UNKNOWN.key
        who = text(line.get("who"), 20) if line else UNKNOWN.who
        since, visits = None, 1
        if who == HOME and has:
            since = has.since
        elif state == "pr":
            since, visits = _stay(logged, step)
        if since is None:
            here = (slug, state)
            came = [move.get("at") for move in moves if (move.get("slug"), move.get("to")) == here]
            since = when(came[-1]) if came else when(row.get("since"), user)
        check = watched.get("check") if isinstance(watched.get("check"), dict) else None
        waited = (now - datetime.fromisoformat(since)).total_seconds() / 60 if since else 0
        if step == "review" and out is not None and slug not in reviewed:
            if waited >= REVIEW_MINUTES and NO_REVIEW in said["say"]:
                said |= {"say": NO_REVIEWER, "waits": "its crewmate to start a reviewer"}
        crew = crews[slug][0] if len(crews.get(slug, [])) == 1 else {}
        thread = line["facts"].get("thread") if line else None
        doubt = unconfirmed
        if doubt is None and line is not None and line.get("confirmed") is False:
            doubt = {"since": None, "source": "", "line": NOT_CONFIRMED}
        (tasks if who != "ok" else ended).append(
            {
                "slug": slug,
                "pr": f"#{number}" if number is not None else "",
                "row_pr": text(row.get("pr"), 20),
                "status": state,
                "step": step,
                "who": who,
                "state": said,
                "rank": RANK.get(value, BROKEN),
                "reason": said["say"],
                "unconfirmed": doubt,
                "blockers": blockers,
                "blocked": None,
                "blocks": 0,
                "behind": [],
                "since": since,
                "visits": max(visits, 1),
                "priority": count(row.get("priority")),
                "approved": text(queue.approval(row), APPROVAL),
                "approved_at": when(queue.ran_at(row), user),
                "by_rule": by_rule(row),
                "checks": text(row.get("checks"), 20),
                "updated": when(row.get("updated"), user),
                "thread": text(row.get("thread"), 80),
                "gone": who == "crew" and thread in GONE,
                "depends": depends,
                "history": logged[-HISTORY:],
                "events": [one for one in events if one["slug"] == slug][-TASK_EVENTS:],
                "seen": {
                    "threads": count(watched.get("threads")),
                    "thread_status": text(watched.get("thread_status"), 20),
                    "thread_updated": when(watched.get("thread_updated")),
                    "live": _live(watched.get("live")) if watched.get("live") else "",
                    "wrote": crew.get("updated"),
                    "run_started": crew.get("run_started"),
                    "queued": count(crew.get("queued")),
                    "reviewer": None if out is None else slug in reviewing,
                    "check": check
                    and {
                        "name": text(check.get("name"), 60),
                        "state": text(check.get("state"), 20),
                        "started": when(check.get("started")),
                        "completed": when(check.get("completed")),
                    },
                },
            }
        )
    _blocks(tasks, ended)
    queued = {task["slug"]: task["blockers"] for task in tasks if task["step"] == "queued"}
    last = waits_on(sorted((row["slug"] for row in rows), key=lambda slug: slug in through), queued)
    for task in tasks:
        task["waits_on"] = last.get(task["slug"], "")
    return tasks, ended


def waits_on(order: list[str], front: dict[str, list[str]]) -> dict[str, str]:
    """The one row each queued row waits on last, the head of its longest chain.

    `order` is the queue's slugs, followed by the rows that the log has as merged, as in
    `blockers`. `front` has each queued row with the rows in front of it that are not merged
    or done. A row that `front` does not have is out, and its depth is 0. A row with nothing
    in front has depth 0, and any other row has one more than the deepest row in front of
    it. The row it waits on last is the deepest one in front of it, and among equals the
    first in the queue. While the function works out a row's depth, the row may come up again
    in front of itself. It then counts as 0, so that the count ends for rows that depend on
    each other.
    """
    place = {slug: at for at, slug in enumerate(order)}
    found: dict[str, int] = {}

    def depth(slug: str) -> int:
        if slug not in front:
            return 0
        if slug not in found:
            found[slug] = 0
            found[slug] = max((depth(one) + 1 for one in front[slug]), default=0)
        return found[slug]

    def last(slug: str) -> str:
        ahead = sorted(front[slug], key=lambda one: (-depth(one), place.get(one, len(place))))
        return ahead[0] if ahead else ""

    return {slug: last(slug) for slug in front}


def _live(word: Any) -> str:
    return word if word in LIVENESS else "unknown"


SCOUTS = "scouts"
REQUEST = {"state": None, "status": None, "asks": None}
THREAD = {
    key: None
    for key in (
        "title",
        "role",
        "slug",
        "status",
        "live",
        "out",
        "today",
        "created",
        "updated",
        "run_started",
        "queued",
        "pending",
        "page",
        "rank",
        "open",
        "health",
    )
} | {"request": REQUEST, "home": None, "retired": None}


def request(home: Path, slug: str) -> dict[str, str]:
    """What a scout's request says of its work, from `scouts/<slug>.md` under the home. The
    view only reads the file.

    The state is `researching` while the request has no `## Report`, and `reported` where
    the `Status:` of its last Report is `done`. It is `blocked` where that line says so, and
    `not done` for any other line, because the scout skill counts a Report that is not done
    as unfinished. It is `missing` where there is no request to read. `status` is the words
    of that line, and `asks` is the request's title. A gate that a scout wrote in its Report
    is part of the Report. The gate's own `Status:` line is not the Report's."""
    try:
        whole = (home / SCOUTS / f"{slug}.md").read_text(errors="replace")
    except (OSError, ValueError):
        return {"state": "missing", "status": "", "asks": ""}
    lines = whole.splitlines()
    asks = text(lines[0].removeprefix("# ") if lines else "", 160)
    reports = [body for heading, body in mirror.sections(whole) if heading == REPORT]
    if not reports:
        return {"state": "researching", "status": "", "asks": asks}
    status = text(briefs.head(reports[-1], "Status:") or "", 160)
    word = status.split(" ", 1)[0]
    blocked = word.rstrip(",.:;") == "blocked"
    state = "reported" if word == "done" else "blocked" if blocked else "not done"
    return {"state": state, "status": status, "asks": asks}


def _threads(
    left: Any, home: Path | None = None, day: str = "", homes: Homes | None = None
) -> list[dict[str, Any]] | None:
    """Every thread the last pass listed as not settled, or None where it left no list.

    `out` marks a thread in which a turn may be under way. That is any thread except one
    that ended. `today` marks a thread that is out, or that last wrote since `day` began. A
    scout's thread also has what its `request` says, and with `homes` each thread has its
    `home`, None where it has none (`homes.Homes.of_thread`). `open` is nothing until
    `_home_work` counts a home's open tasks."""
    if not isinstance(left, list):
        return None
    found = []
    for one in left:
        if not isinstance(one, dict):
            continue
        live, updated = _live(one.get("live")), when(one.get("wrote") or one.get("updatedAt"))
        thread = {
            "title": text(one.get("title"), 120),
            "role": one.get("role") if one.get("role") in {role.name for role in ROLES} else OTHER,
            "slug": text(one.get("slug"), 80),
            "status": text(one.get("status"), 20),
            "live": live,
            "out": live in OUT,
            "rank": RANK[LIVE_AS[live]],
            "today": live in OUT or bool(updated and day and updated >= day),
            "created": when(one.get("createdAt")),
            "updated": updated,
            "run_started": when(one.get("run_started")),
            "queued": count(one.get("queued")),
            "pending": count(one.get("pending")),
            "page": one.get("page") is True,
            "open": 0,
        }
        if thread["role"] == "scout" and home is not None and _SLUG.fullmatch(thread["slug"]):
            thread["request"] = request(home, thread["slug"])
        if homes is not None:
            owner = homes.of_thread(thread, text(one.get("id"), 80))
            thread |= owner.said() if owner else {"home": None, "retired": ""}
        found.append(thread)
    return found


def _home_work(
    found: list[dict[str, Any]] | None, tasks: list[dict[str, Any]]
) -> list[dict[str, Any]] | None:
    """The threads, with each home's count of its own open tasks, the tasks whose `home` is
    the home's. A home's thread whose id is in no `home-id` and on no `Was home:` line is the
    home its title names: the words after the project's name, which a root home's title has
    none of. A home whose turn ended while a task of its own is open is idle: nothing moves it
    but the user, so it ranks with what asks.

    A home's thread also has its `health`: the word of its liveness while it is out,
    `ended` where its turn ended with a task of its own open, and `rest` where it ended with
    nothing open."""
    if found is None:
        return None
    owned: dict[str, int] = {}
    for task in tasks:
        owned[task["home"]] = owned.get(task["home"], 0) + 1
    made = []
    for thread in found:
        if thread["role"] == "home":
            name = thread["home"]
            if name is None:
                name = thread["slug"].partition(" ")[2]
            thread = thread | {"home": name, "open": owned.get(name, 0)}
            if thread["out"]:
                thread["health"] = thread["live"]
            else:
                thread["health"] = "ended" if thread["open"] else "rest"
            if thread["health"] == "ended":
                thread["rank"] = ASKS
        made.append(thread)
    return made


def _blocks(tasks: list[dict[str, Any]], ended: list[dict[str, Any]]) -> None:
    """Mark each open task that cannot move with what blocks it. Where other tasks
    wait behind a task, mark that task with them: the ones that depend on it, and the ones
    behind those. A task stays behind a row until jbus records that row as merged or done. The
    row's state does not change that. `blockers` has those rows, followed by the ones the log
    has as merged."""
    by_slug = {task["slug"]: task for task in tasks + ended}
    behind: dict[str, set[str]] = {}
    for task in tasks:
        kind = task["state"]["kind"]
        first = (task["blockers"] or [""])[0]
        if kind == "behind":
            holder = by_slug.get(first)
            held = holder["state"]["kind"] if holder else ""
            task["blocked"] = {
                "by": first if holder else "",
                "what": first,
                "state": holder["state"]["name"] if holder else "not in the queue",
            }
            if held == "merged":
                task["state"]["waits"] = f"jbus to see that {first} is through"
        elif kind in BLOCKED:
            task["blocked"] = {"by": "", "what": BLOCKED[kind], "state": ""}
        for one in task["blockers"]:
            behind.setdefault(one, set()).add(task["slug"])
    for task in tasks + ended:
        found, look = set(), [task["slug"]]
        while look:
            for slug in behind.get(look.pop(), ()):
                if slug not in found:
                    found.add(slug)
                    look.append(slug)
        task["behind"] = sorted(found - {task["slug"]})
        task["blocks"] = len(task["behind"])


def _events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The events of the log, oldest first, each as its time, kind, loudness, slug and line.
    The loudness has its current name. A line from before jbus dropped the name `chef` is
    `quiet`."""
    names = old_names()
    return [
        {
            "at": when(one.get("at")),
            "kind": text(one.get("event"), 40),
            "loud": current_level(text(one.get("loud"), 10), names),
            "slug": text(one.get("slug"), 80),
            "line": text(one.get("line")),
        }
        for one in records
        if "event" in one and when(one.get("at"))
    ]


def _acts(read: Read) -> list[dict[str, Any]]:
    """Every act the project's records keep, oldest first, each with its time, its line and
    the home it is of (`homes.Homes.of_key`), or None for an act of no home: each change of a
    row's status in `transitions.jsonl`, each event of `events.jsonl`, a wake and a Result
    among them, but jbus's hourly heartbeat, which says only that jbus runs, and each line of
    `merge.log`, by the pull request it names, or the slug a merge names."""
    pulls = {text(row.get("pr")).removeprefix("#"): row["slug"] for row in read.rows}
    pulls.pop("", None)
    rows, homes = {row["slug"] for row in read.rows}, read.homes
    known: dict[str, str | None] = {}

    def act(at: str | None, key: str, what: str) -> dict[str, Any] | None:
        if not at:
            return None
        if key not in known:
            known[key] = homes.of_key(key, pulls, rows)
        return {"at": at, "home": known[key], "what": text(what, 160)}

    made = [
        act(
            when(one.get("at")),
            text(one.get("slug"), 80),
            f"{one.get('slug')}: {one.get('from')} to {one.get('to')}",
        )
        for one in read.moves or []
    ]
    made += [
        act(one["at"], one["slug"], one["line"])
        for one in read.events
        if one["kind"] != "heartbeat"
    ]
    for logged in read.log or []:
        stamped = _LOGGED.match(logged)
        line = merge.parse(stamped[2]) if stamped else None
        if stamped and line:
            named = (
                line.name
                if line.word == "merged" and str(line.number) not in pulls
                else f"#{line.number}"
            )
            made.append(act(when(stamped[1], read.user), named, stamped[2]))
    return sorted((one for one in made if one), key=lambda one: one["at"])


def threads_seen(sources: Sources, name: str) -> Any:
    """The threads the last pass listed for the project, as `pass.json` has them."""
    record = _table(sources.state_dir / "pass.json") or {}
    seen = record.get("projects", {}).get(name) if isinstance(record.get("projects"), dict) else {}
    return seen.get("threads") if isinstance(seen, dict) else None


def asker(home: Path, slug: str, threads: Any) -> tuple[str, str]:
    """The thread that an answer to a question of the slug goes to, and that thread's role.

    The thread is the one `questions` sends to, on the `Thread:` line of the slug's brief or
    request. Its role is the one the last pass listed it with (`threads`). Where the pass did
    not list it, its file gives the role: a brief is a crew's and a request is a scout's.
    Both the thread and the role are nothing for a slug with no such line."""
    thread = questions.thread_of(home, slug)
    if not thread:
        return "", ""
    for one in threads if isinstance(threads, list) else []:
        if (
            isinstance(one, dict)
            and one.get("id") == thread
            and one.get("role") in {role.name for role in ROLES if role.prefix}
        ):
            return thread, one["role"]
    for kind, role in (("tasks", "crew"), ("scouts", "scout")):
        try:
            brief = (home / kind / f"{slug}.md").read_text(errors="replace")
        except OSError:
            continue
        if briefs.thread_of(brief):
            return thread, role
    return thread, ""


def _mtime(path: Path) -> str | None:
    try:
        return iso(datetime.fromtimestamp(path.stat().st_mtime, UTC))
    except OSError:
        return None


def _source(
    name: str,
    by: str,
    at: str | None,
    now: datetime,
    read: bool = True,
    path: Path | None = None,
    fresh: int | None = None,
    old: bool = False,
) -> dict[str, Any]:
    """One source and the one word for how it is: `ok`, or `missing`, `unreadable` or `stale`.

    A source with a path that is not there is missing, and any other source the view could
    not read is unreadable. A source is stale only where the caller gives `fresh`, the
    seconds it may be old. A file changes when something happens, so an old file says
    nothing by itself. `stopped` says whether the two files a pass writes are late. The view
    reads `gates.md` where a home still writes one, and a home with none lacks nothing,
    because jbus keeps its gates.

    The server asks GitHub again each minute, and a `gh` that fails overwrites the answer
    with an error. GitHub's answer can only reach `GITHUB_FRESH` seconds old when a `gh` is
    slow to return, and the server keeps the old answer meanwhile. Only then is it stale.
    The limits file is stale when it is `old`, which means a limit in it has reset since a
    session wrote it."""
    word = "ok" if read else "missing" if path is not None and not path.exists() else "unreadable"
    word = "stale" if read and old else word
    if read and at and fresh is not None:
        age = (now - datetime.fromisoformat(at)).total_seconds()
        word = "stale" if age > fresh else word
    return {"name": name, "by": by, "at": at, "state": word}


@dataclass(frozen=True)
class Source:
    """One source a panel reads: its name, who writes it, and how it is now. The writer is
    `jbus`, the `server` itself or a `session`. The fields are the arguments `_source` takes
    besides `now`. The list of the sources is in the order of `rank`. A `machine` source is
    the same for every project, so the overview gives it once, on the machine row, and on no
    project's row."""

    name: str
    by: str
    seen: Callable[[Read], dict[str, Any]]
    rank: int = 1000
    machine: bool = False


@dataclass(frozen=True)
class Spot:
    """One thing a panel cannot say, which is a line of `blind`. On the page, a click on
    the line opens the panel that gives it. The lines are in the order of `rank`. A
    `machine` line is the same for every project."""

    line: str
    rank: int = 1000
    machine: bool = False


def kept(name: str, value: Callable[[Read], Any], rank: int = 1000) -> Source:
    """A file of the project's state directory, which jbus writes. Where `value` gives
    anything but None, the view read the file."""

    def seen(read: Read) -> dict[str, Any]:
        path = read.state / name
        return {"at": _mtime(path), "read": value(read) is not None, "path": path}

    return Source(name, "jbus", seen, rank)


def _passed(read: Read) -> dict[str, Any]:
    path = read.sources.state_dir / "pass.json"
    return {"at": _mtime(path), "read": bool(read.record), "path": path}


def _merges(read: Read) -> dict[str, Any]:
    path = read.home / "merge.log"
    return {"at": _mtime(path), "read": read.log is not None, "path": path}


PASS_FILE = Source("pass.json", "jbus", _passed, 30, machine=True)
QUEUE_FILE = kept("queue.json", lambda read: read.table_of_rows, 40)
WAITING_FILE = kept(waiting.NAME, lambda read: read.left, 50)
MOVES_FILE = kept("transitions.jsonl", lambda read: read.moves, 60)
WORK_FILE = kept(work.NAME, lambda read: read.work, 35)
EVENTS_FILE = kept(LOG, lambda read: read.logged, 70)
MERGE_LOG = Source("merge.log", "jbus", _merges, 130)


class Read:
    """What the view builds one answer from: one project at one moment. It reads each file
    once.

    A panel's `build` gets it as its argument. What more than one panel reads is a property
    here, and its source is one of the six above. A panel calls `panel` to get what another
    panel works out. `once` keeps what a panel works out for its own functions. `merged` asks
    GitHub for the pull requests merged since a day, as `github.GitHub.merged` does, and
    `landed` for the integration branches that landed on the default branch, as
    `github.GitHub.landed` does. Each is None where no server asks.
    """

    def __init__(
        self,
        sources: Sources,
        name: str,
        now: datetime,
        runs: Callable[[str], dict[str, Any]],
        code: dict[str, Any] | None = None,
        found: tuple[panels.Panel, ...] | None = None,
        shared: dict[Any, Any] | None = None,
        merged: Callable[[str, date], dict[str, Any]] | None = None,
        landed: Callable[[str, tuple[str, ...]], dict[str, Any]] | None = None,
    ) -> None:
        self.sources, self.name, self.now, self.runs = sources, name, now, runs
        self.merged, self.landed = merged, landed
        self.code = code or {}
        self.user = sources.user
        self.state, self.home = sources.state(name), sources.home(name)
        self.panels = panels.found() if found is None else found
        self._kept: dict[Any, Any] = {}
        self._shared: dict[Any, Any] = {} if shared is None else shared

    def once(self, make: Callable[[Read], Any]) -> Any:
        """What `make` gives of this `Read`. The view works it out the first time a caller
        asks."""
        if make not in self._kept:
            self._kept[make] = make(self)
        return self._kept[make]

    def machine(self, make: Callable[[Read], Any]) -> Any:
        """What `make` gives of the machine, which is the same for every project.

        Several `Read`s can share one `shared`. The view works the answer out the first time
        any of them asks. One answer of `/stack.json` reads every project with one `shared`."""
        if make not in self._shared:
            self._shared[make] = make(self)
        return self._shared[make]

    def panel(self, name: str) -> dict[str, Any]:
        """What the panel `name` builds, before the view cuts it to its shape."""
        return self.once(next(one for one in self.panels if one.name == name).data.build)

    def table(self, file: str) -> dict[str, Any] | None:
        """A file of the project's state directory that contains one dict, or None."""
        return self._file(_table, file)

    def records(self, file: str) -> list[dict[str, Any]] | None:
        """The records of a `.jsonl` file of the project's state directory, or None."""
        return self._file(_records, file)

    def _file(self, how: Callable[[Path], Any], file: str) -> Any:
        if (how, file) not in self._kept:
            self._kept[how, file] = how(self.state / file)
        return self._kept[how, file]

    @cached_property
    def table_of_rows(self) -> list[queue.Row] | None:
        """The rows of `queue.json`, or None where the view could not read it."""
        return _rows(self.state) if self.name else None

    @cached_property
    def rows(self) -> list[queue.Row]:
        return self.table_of_rows or []

    @cached_property
    def moves(self) -> list[dict[str, Any]] | None:
        return self.records("transitions.jsonl")

    @cached_property
    def logged(self) -> list[dict[str, Any]] | None:
        return self.records(LOG)

    @cached_property
    def events(self) -> list[dict[str, Any]]:
        return _events(self.logged or [])

    @cached_property
    def acts(self) -> list[dict[str, Any]]:
        """Every act the project's records keep, oldest first, each with its home (`_acts`)."""
        return _acts(self)

    @cached_property
    def log(self) -> list[str] | None:
        return _lines(self.home / "merge.log")

    @cached_property
    def history(self) -> dict[int, list[dict[str, str]]]:
        return _history(self.log or [], self.user)

    @cached_property
    def where(self) -> str:
        return repo(self.sources, self.name)

    @cached_property
    def left(self) -> list[Any] | None:
        return waiting.read(self.state)

    @cached_property
    def record(self) -> dict[str, Any]:
        """What the last pass left in `pass.json`."""
        return _table(self.sources.state_dir / "pass.json") or {}

    @cached_property
    def mine(self) -> dict[str, Any]:
        """What the last pass left of this project."""
        every = self.record.get("projects")
        mine = every.get(self.name) if isinstance(every, dict) else None
        return mine if isinstance(mine, dict) else {}

    @cached_property
    def threads_listed(self) -> list[dict[str, Any]] | None:
        """The threads the last pass listed, or None where it left no list."""
        return _threads(self.mine.get("threads"), self.home, self.day, self.homes)

    @cached_property
    def out(self) -> list[dict[str, Any]] | None:
        """The threads the last pass listed, each home with its open tasks (`_home_work`), or
        None where the pass left no list."""
        return _home_work(self.threads_listed, self.tasks)

    @cached_property
    def homes(self) -> Homes:
        """The project's homes, which each task, thread and need belongs to."""
        return Homes(self.home, self.state)

    @cached_property
    def unconfirmed(self) -> dict[str, Any] | None:
        """The line every task shows while the last pass could not ask a source, or None where
        it could ask every source."""
        silent = self.record.get("silent") if isinstance(self.record.get("silent"), dict) else {}
        unasked = text(silent.get(self.name), 40)
        if not unasked:
            return None
        since = when(self.mine.get("seen"))
        stamp = self.user.stamp(datetime.fromisoformat(since)) if since else ""
        last = f"since {stamp}" if since else "by any pass kept"
        line = f"not confirmed {last}: {unasked} did not answer"
        return {"since": since, "source": unasked, "line": line}

    @cached_property
    def work(self) -> dict[str, Any] | None:
        """What the last pass judged, `work.json`, or None where the view could not read it."""
        return work.read(self.state) if self.name else None

    @cached_property
    def judged(self) -> dict[str, dict[str, Any]]:
        """The state the last pass judged for each row of the queue, by its slug."""
        listed = (self.work or {}).get("work", [])
        return {
            one["key"]: one
            for one in listed
            if isinstance(one, dict)
            and one.get("kind") == "row"
            and isinstance(one.get("key"), str)
        }

    @cached_property
    def _open(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        asked = {
            one["slug"]: one["line"].partition(": ")[2]
            for one in self.left or []
            if one.get("kind") == "row" and isinstance(one.get("line"), str) and one.get("slug")
        }
        seen = self.mine.get("rows")
        made = _tasks(
            self.rows,
            self.history,
            self.judged,
            asked,
            self.moves or [],
            self.events,
            seen if isinstance(seen, dict) else {},
            self.user,
            lambda slug: _whole(self.state, self.home, slug),
            self.threads_listed,
            self.now,
            self.unconfirmed,
            leftover.read(self.state) if self.name else {},
        )
        for task in made[0] + made[1]:
            task |= self.homes.of_task(task["slug"]).said()
        return made

    @property
    def tasks(self) -> list[dict[str, Any]]:
        """The open work of the queue."""
        return self._open[0]

    @property
    def ended(self) -> list[dict[str, Any]]:
        """The rows that ended, though the queue still gives each of them another state."""
        return self._open[1]

    @cached_property
    def day(self) -> str:
        """The start of the user's day."""
        return iso(self.user.local(self.now).replace(hour=0, minute=0, second=0, microsecond=0))

    def merged_since(self, start: str) -> list[dict[str, Any]]:
        """Each merge at or after `start`, oldest first: each row that moved to merged in the
        queue, each row the pass judged merged while the row says another state, and each row
        whose last `merge.log` line is `merged`, at that line's time, before any pass reads it.
        The view works it out once for each `start`: the panel `merged` and the band `glance`
        ask for the same one for most of the day."""
        if ("merged", start) not in self._kept:
            self._kept["merged", start] = self._merged_since(start)
        return self._kept["merged", start]

    def _merged_since(self, start: str) -> list[dict[str, Any]]:
        pull = {row["slug"]: row for row in self.rows}
        merged = []
        for move in self.moves or []:
            slug, at = text(move.get("slug"), 80), when(move.get("at"))
            if move.get("to") == "merged" and at and at >= start:
                was = pull.get(slug, {})
                approved = when(queue.ran_at(was), self.user)
                merged.append(
                    {"slug": slug, "pr": text(was.get("pr"), 20), "at": at, "approved": approved}
                )
        for one in self.ended:
            at = one["since"] if one["state"]["kind"] == "merged" else None
            if at and at >= start and one["slug"] not in {m["slug"] for m in merged}:
                approved = one["approved_at"]
                merged.append(
                    {"slug": one["slug"], "pr": one["pr"], "at": at, "approved": approved}
                )
        for row in self.rows:
            logged = self.history.get(number, []) if (number := _number(row)) is not None else []
            at = logged[-1]["at"] if logged and logged[-1]["word"] == "merged" else None
            if at and at >= start and row["slug"] not in {m["slug"] for m in merged}:
                approved = when(queue.ran_at(row), self.user)
                merged.append(
                    {"slug": row["slug"], "pr": f"#{number}", "at": at, "approved": approved}
                )
        merged.sort(key=lambda one: one["at"])
        return merged

    @cached_property
    def listed(self) -> list[dict[str, Any]]:
        """Every source a panel names, once, in the order of its rank, and how it is now."""
        named: dict[str, Source] = {}
        for panel in self.panels:
            for source in panel.sources:
                named.setdefault(source.name, source)
        return self._how(named.values())

    def read_by(self, panel: panels.Panel) -> list[dict[str, Any]]:
        """The sources the panel names, and how each is now. It looks at no other source."""
        return self._how({one.name: one for one in panel.sources}.values())

    def _how(self, named: Any) -> list[dict[str, Any]]:
        found = []
        for one in sorted(named, key=lambda one: one.rank):
            if ("source", one.name) not in self._kept:
                seen = _source(one.name, one.by, now=self.now, **one.seen(self))
                self._kept["source", one.name] = seen
            found.append(self._kept["source", one.name])
        return found

    def answer(self) -> dict[str, Any]:
        """What `/state.json` holds: the frame, and what each panel of the first screen
        builds, cut to the panel's shape."""
        keys(self.panels)
        parts = {
            "at": iso(self.now),
            "project": self.name,
            "projects": projects(self.sources),
            "repo": self.where,
            "sources": self.listed,
            "summary": keep(summary(self), SUMMARY),
            "kinds": waiting.shown(),
            "roles": shown_roles(),
            "items": items(self.sources.state(self.name)),
        }
        for panel in self.panels:
            if panel.first:
                parts |= keep(self.panel(panel.name), panel.shape)
        return parts

    def asked(self, name: str) -> dict[str, Any] | None:
        """What `/panel/<name>.json` holds: what the panel builds, cut to its shape, and how
        each source it names is now. It is None for a name that no folder has."""
        panel = next((one for one in self.panels if one.name == name), None)
        if panel is None:
            return None
        return {
            "at": iso(self.now),
            "panel": name,
            "data": keep(self.panel(name), panel.shape),
            "sources": self.read_by(panel),
        }


def items(state: Path) -> list[dict[str, Any]]:
    """`items`: each work item of the project as the view builds it from its log, with its
    risk and its last lines."""
    lines = item.read(state)
    found = sorted(item.fold(lines).values(), key=lambda one: item._number(one.id))
    ended = {one.id for one in found if one.state not in item.LIVE}
    last = [line["item"] for line in lines if line.get("item") in ended]
    shown = set(list(dict.fromkeys(reversed(last)))[:ENDED])
    made = []
    for one in (one for one in found if one.state in item.LIVE or one.id in shown):
        one = item.judged(state, one)
        mine = [line for line in lines if line.get("item") == one.id][-ITEM_LINES:]
        made.append(
            {
                "id": one.id,
                "slug": one.slug,
                "title": text(one.title),
                "state": str(one.state),
                "owner": one.owner,
                "risk": str(one.risk),
                "last_event": one.last_event,
                "lines": [
                    {
                        key: text(line.get(key))
                        for key in ("id", "at", "verb", "action", "by", "where", "line")
                    }
                    for line in mine
                ],
            }
        )
    return made


def keys(found: tuple[panels.Panel, ...] | None = None) -> tuple[str, ...]:
    """The keys of `/state.json`: the frame's, then each key of the shape of a panel that is
    on the first screen. It refuses a key that two of them give."""
    owner = dict.fromkeys(FRAME, "the frame")
    for panel in panels.found() if found is None else found:
        for key in panel.shape if panel.first else ():
            if key in owner:
                raise ValueError(f"{owner[key]} and the panel {panel.name} both give the key {key}")
            owner[key] = f"the panel {panel.name}"
    return tuple(owner)


def build(
    sources: Sources,
    name: str,
    now: datetime,
    runs: Callable[[str], dict[str, Any]],
    code: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The state of one project, `name`, or of no project where the state directory has no
    such project.

    `runs` gives the repo's last workflow runs, as `github.GitHub.runs` does. `code` says
    which code serves requests, as the server's `Code.said` gives it, and the function puts
    it under `jbus`.
    """
    return Read(sources, name, now, runs, code).answer()


KEPT_BY_JBUS = ("last_pass", "token_expires", "streaks", "homes_off_bus", "scratch")
SUMMARY = {
    "name": None,
    "repo": None,
    "waits": None,
    "open": None,
    "steps": {ANY: None},
    "merged": None,
    "threads": [THREAD],
    "homes": [GROUP],
    "last": {"at": None, "home": None, "what": None},
    "broken": [{"what": None, "open": None, "since": None}],
    "unplaced": [None],
    "health": {
        "checks": {"running": None, "waiting": None, "failed": None, "error": None},
        "bus": {"outbox": None, "failed_wakes": None, "last_error": None},
        "threads": None,
        "blind": None,
        "unwell": [{"name": None, "state": None}],
    },
}


def oldest(needs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The records of the user's queue, oldest `since` first and a record with no time last.
    Where two records tie, the project and then the key decide the order."""
    return sorted(
        needs,
        key=lambda one: (one["since"] is None, one["since"] or "", one["project"], one["key"]),
    )


WRONG = {
    "kind": None,
    "subj": None,
    "cause": None,
    "since": None,
    "where": [{"project": None, "home": None, "open": None}],
    "row": None,
    "owner": None,
    "fixing": {"told": None, "what": None},
}
SHARED = ("bus", "source", "unasked")
STALLED = "stall"
QUIET_OR_HUNG = {
    "hung": "its turn has written nothing, and may be hung",
    "quiet": "it has written nothing for a while",
}
SOURCE_IS = {"unreadable": "cannot be read", "stale": "is stale"}
_STALLED = re.compile(r"stall (\S+): (.+)", re.S)
_ASIDE = re.compile(r'thread "|it ended with something left')
_AT_HEAD = re.compile(r"\bat ([0-9a-f]{12})\b")
_CAPPED = re.compile(r"\bcapped until (\d{4}-\S+)$")


def _wrong(
    read: Read,
    kind: str,
    subj: str,
    cause: str,
    since: Any,
    route: str,
    home: Any = "",
    row: str = "",
) -> dict[str, Any]:
    """One thing that is wrong in the project, the drawer of the page that has it, and the row
    it is about, or an empty `row` for a fault of the project or the machine."""
    place = {
        "project": read.name,
        "home": home or "",
        "open": f"#/{quote(read.name, safe='')}/{route}",
    }
    found = {"kind": kind, "subj": subj, "cause": cause, "since": since, "where": [place]}
    return found | {"row": row}


USER, ROOT_HOME, CREW = "user", "root home", "crew"
CHECK_TOLD = ("failed", "refailed")
"""The outbox's templates that tell a crew its pull request's check failed (`jbus.rebase`)."""


def _main(read: Read, one: dict[str, Any]) -> tuple[str, str]:
    """A red main is the crew's of its main-red row while one is open, else the root home's."""
    fix = next((task["slug"] for task in read.tasks if mainjson.fix_of(task["slug"])), "")
    return (CREW, fix) if fix else (ROOT_HOME, "")


def _ci(read: Read, one: dict[str, Any]) -> tuple[str, str]:
    """A red branch is the crew's of the row whose branch it is, and CI that could not be read
    or a branch no row has is the root home's."""
    return (CREW, one["row"]) if one["row"] else (ROOT_HOME, "")


def _bus(read: Read, one: dict[str, Any]) -> tuple[str, str]:
    """Wakes go to the home thread through T3 Code alone, so wakes that fail reach no agent, and
    are the user's."""
    return USER, ""


def _unasked(read: Read, one: dict[str, Any]) -> tuple[str, str]:
    """T3 Code not answering is the user's, since no agent is reached without it."""
    return (USER, "") if one["subj"] == "T3 Code" else (ROOT_HOME, "")


def _of_row(read: Read, one: dict[str, Any]) -> tuple[str, str]:
    """A fault of a row is its home's, unless the row waits on a gate, which holds only for a
    case of `gates.md` and is the user's to answer, or the fault waits on a cap of the user's
    plan."""
    task = next((task for task in read.tasks if task["slug"] == one["row"]), {})
    if task.get("status") == "gate" or _CAPPED.search(one["cause"]):
        return USER, one["row"]
    return "home", one["row"]


OWNERS: dict[str, Callable[[Read, dict[str, Any]], tuple[str, str]]] = {
    "main": _main,
    "ci": _ci,
    "bus": _bus,
    "source": lambda read, one: (ROOT_HOME, ""),
    "unasked": _unasked,
    "thread": _of_row,
    "stall": _of_row,
    "idle": _of_row,
}
"""Who fixes each kind of `wrongs`: `crew` with the row whose crew it is, `home` with the row
whose home it is, the root home, or the user."""


def _home_of(read: Read, row: str) -> tuple[str, str]:
    """The name and the thread of the home of a row, or of the root home for no row."""
    scope = read.homes.of_task(row).name if row else ""
    thread = jbriefs.thread_of(read.home / scope if scope else read.home)
    return (f"home {scope}" if scope else ROOT_HOME), thread


def owner(read: Read, one: dict[str, Any]) -> tuple[str, str, str]:
    """Who fixes an entry of `wrongs`, the thread jbus tells, and the row it is about: an agent
    that can be told, or else the next one up. A crew with no thread hands it to its row's home,
    and a home with no thread to the root home. With no root home to tell, it is the user's."""
    who, row = OWNERS[one["kind"]](read, one)
    if who == CREW:
        task = next((task for task in read.tasks if task["slug"] == row), {})
        if task.get("thread"):
            return f"crew of {row}", task["thread"], row
        who = "home"
    if who == "home":
        name, thread = _home_of(read, row)
        if thread:
            return name, thread, row
        who = ROOT_HOME
    if who == ROOT_HOME:
        name, thread = _home_of(read, "")
        if thread:
            return name, thread, row
    return USER, "", row


_MOMENT = re.compile(r"\s*\b(?:at |until )?(?:[0-9a-f]{7,40}|\d{4}-\S+)\b")
"""A commit or a time in a cause, which the key of an entry leaves out."""


def key_of(one: dict[str, Any]) -> str:
    """The outbox's key for the one message that tells an entry's owner of it: its kind, subject
    and reason, with no commit, run or time, so one fault is one key whatever runs show it, and a
    new owner thread a new one."""
    stands = f"{one['kind']}|{one['subj']}|{_MOMENT.sub('', one['cause'])}"
    digest = hashlib.sha256(stands.encode()).hexdigest()[:12]
    return f"wrong|{one['kind']}|{digest}|{one['to']}"


def _fixing(read: Read, one: dict[str, Any]) -> dict[str, str] | None:
    """What the owner was told and when: the wake that told it of the entry (`jbus.wakes`), the
    failed-check message to a crew since its run, any other message to the owner about the
    entry's row since the fault began (a stalled row's home line from `jbus.expedite`), the
    main-red row that fixes a red main, or the leftover its row's home was told of
    (`jbus.leftover`). None where the owner was not told yet."""
    if one["owner"] == USER:
        return None
    if one["kind"] == "main" and mainjson.fix_of(one["row"]):
        moves = [
            when(move.get("at")) for move in read.moves or [] if move.get("slug") == one["row"]
        ]
        task = next((task for task in read.tasks if task["slug"] == one["row"]), {})
        at = min((at for at in moves if at), default=None) or task.get("updated")
        return {"told": at, "what": "the main-red row"} if at else None
    held = leftover.read(read.state).get(one["row"]) if read.name and one["row"] else None
    if held and held.told and held.thread == one["to"]:
        return {"told": when(held.told), "what": leftover.KIND}
    key = key_of(one)
    for told in told_to(read.table(TOLD) or {}, one["to"]).values():
        if told.get("wrong") == key and when(told.get("at")):
            return {"told": when(told["at"]), "what": TOLD_KIND}
    sent = [line for line in read.records(outbox.FILE) or [] if line.get("went") == "sent"]
    for line in reversed(sent):
        at = when(line.get("at"))
        if not at or line.get("thread") != one["to"]:
            continue
        about = one["row"] and line.get("row") == one["row"] and at >= (one["since"] or "")
        if about and (one["kind"] != "ci" or line.get("template") in CHECK_TOLD):
            return {"told": at, "what": text(line.get("template"), 40)}
    return None


def _owned(read: Read, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each entry with its `owner`, the thread `to` tell, and `fixing`."""
    for one in found:
        name, thread, row = owner(read, one)
        one |= {"owner": name, "to": thread, "row": row}
        one["fixing"] = _fixing(read, one)
    return found


def _unwell(read: Read) -> list[dict[str, Any]]:
    """Each source of the project that is not ok, except one that a session writes, one that
    is missing and one of the machine. A missing file is one jbus has not written for the
    project, as `ci.jsonl` where no `jbus ci` runs: the pulse lists it, and it is no fault. A
    file that is there and cannot be read is."""
    machine = {one.name for panel in read.panels for one in panel.sources if one.machine}
    return [
        one
        for one in read.listed
        if one["state"] not in ("ok", "missing")
        and one["by"] != "session"
        and one["name"] not in machine
    ]


def _stalls(read: Read, tasks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The last stall of each open row that still stands, by slug, from the log.

    A stall stands while its row is open and has not moved since. One that names a head (`at
    <head>`) stands while `expedite.json` still counts that head, and one of a cap (`capped
    until <time>`) while the cap lasts. A stall of a hung thread is the thread's, which the list
    of threads says as it is now, and a stall of a leftover is a need of the user: neither is
    here."""
    moved: dict[str, str] = {}
    for one in read.moves or []:
        at = when(one.get("at"))
        if at and isinstance(one.get("slug"), str):
            moved[one["slug"]] = max(moved.get(one["slug"], ""), at)
    last = {}
    for one in read.events:
        said = _STALLED.fullmatch(one["line"]) if one["kind"] == STALLED else None
        if said and one["slug"] in tasks and not _ASIDE.match(said[2]):
            last[one["slug"]] = one | {"cause": said[2]}
    counted = {
        slug: text(entry.get("head"), 40)
        for slug, entry in (read.table(expedite.FILE) or {}).items()
        if isinstance(entry, dict)
    }
    found = {}
    for slug, one in last.items():
        head, capped = _AT_HEAD.search(one["cause"]), _CAPPED.search(one["cause"])
        if moved.get(slug, "") >= one["at"]:
            continue
        if head and not counted.get(slug, "").startswith(head[1]):
            continue
        if capped and (when(capped[1]) or "") <= iso(read.now):
            continue
        found[slug] = one
    return found


def wrongs(read: Read) -> list[dict[str, Any]]:
    """What is wrong in the project, each with its kind, its subject, its cause, since when,
    and where: the project, the home and the drawer of the page that has it.

    The kinds are `main`, red at its tip; `ci`, a branch whose newest run failed, or CI that could
    not be read; `bus`, the wakes of the home thread failing; `source`, a source that is there and
    cannot be read, or is stale; `unasked`, a source the last pass could not ask; `thread`, a thread
    that is `hung` or `quiet`; `stall`, a row jbus logged a stall of that still stands (`_stalls`);
    and `idle`, a pull request whose crew jbus told what it is short of and found nobody at work
    after (`jbus.expedite`), while no stall of it stands and the hold is not the user's. A `since`
    is None where nothing kept says. Each reads its source as it is now, so an entry goes once its
    source works again.

    Each entry also has its `owner`, who fixes it (`owner`, by the rule of its kind in
    `OWNERS`), the thread jbus tells it `to`, the `row` it is about, and `fixing`, what that
    owner was told and when (`_fixing`). The user owns only what no agent can fix (`users`)."""
    checks, bus = read.panel("checks")["checks"], read.panel("bus")["bus"]
    main = read.panel("pulse")["main"]
    found = []
    if main["red"]:
        since = main["at"] if main["red"] == main["sha"] else None
        found.append(_wrong(read, "main", "main", f"red at {main['red'][:7]}", since, "pulse"))
    if checks["error"]:
        named = checks["error"] if allowance.is_named(checks["error"]) else ""
        cause = f"could not be read: {named}" if named else "could not be read"
        found.append(_wrong(read, "ci", "CI", cause, None, "checks"))
    else:
        for at in checks["now"]["failed"]:
            run = checks["runs"][at]
            cause, row = f"{run['name']} failed", run["branch"]
            mine = row if any(task["slug"] == row for task in read.tasks) else ""
            found.append(_wrong(read, "ci", row, cause, run["created"], "checks", row=mine))
    if bus["failed_wakes"] or bus["last_error"]:
        error = f": {bus['last_error']}" if bus["last_error"] else ""
        cause = f"wakes to the home thread fail{error}"
        found.append(_wrong(read, "bus", "bus", cause, bus.get("since"), "bus"))
    for one in _unwell(read):
        cause = SOURCE_IS.get(one["state"], one["state"])
        found.append(_wrong(read, "source", one["name"], cause, one["at"], "pulse"))
    if read.unconfirmed:
        cause, since = "did not answer the last pass", read.unconfirmed["since"]
        found.append(_wrong(read, "unasked", read.unconfirmed["source"], cause, since, "pulse"))
    for one in read.out or []:
        if one["live"] in QUIET_OR_HUNG:
            parts = ("thread", one["role"], one["slug"]) if one["slug"] else ("threads",)
            route = "/".join(quote(part, safe="") for part in parts)
            cause = QUIET_OR_HUNG[one["live"]]
            if one["queued"]:
                cause += f", and {one['queued']} run{'' if one['queued'] == 1 else 's'} wait"
            home, mine = one.get("home"), one["slug"] or ""
            found.append(
                _wrong(read, "thread", one["title"], cause, one["updated"], route, home, mine)
            )
    tasks = {task["slug"]: task for task in read.tasks}
    stalls = _stalls(read, tasks)
    for slug, one in stalls.items():
        route = f"task/{quote(slug, safe='')}"
        home = tasks[slug]["home"]
        found.append(_wrong(read, "stall", slug, one["cause"], one["at"], route, home, slug))
    told = {one["slug"]: one["at"] for one in read.events if one["kind"] == expedite.EXPEDITE}
    for slug, entry in (read.table(expedite.FILE) or {}).items():
        if not isinstance(entry, dict) or slug not in tasks or slug in stalls:
            continue
        if "told" not in entry or not entry.get("idle") or entry.get("users"):
            continue
        short = text(entry.get("reason"))
        cause = f"#{entry.get('number')} is short, {short}, and its crew has not acted"
        route = f"task/{quote(slug, safe='')}"
        home = tasks[slug]["home"]
        found.append(_wrong(read, "idle", slug, cause, told.get(slug), route, home, slug))
    return _owned(read, found)


def users(read: Read) -> list[dict[str, Any]]:
    """The entries of `wrongs` that are the user's, which no agent can fix: what the band, the
    since line and `/stack.json`'s `wrong` show."""
    return [one for one in read.once(wrongs) if one["owner"] == USER]


def fixing(read: Read) -> dict[str, dict[str, Any]]:
    """By row, the first entry of `wrongs` an agent owns, as its row draws it: who fixes it
    and when they were told, or None where they were not told yet."""
    found: dict[str, dict[str, Any]] = {}
    for one in read.once(wrongs):
        if one["owner"] != USER and one["row"] and one["row"] not in found:
            told = (one["fixing"] or {}).get("told")
            found[one["row"]] = {"owner": one["owner"], "told": told}
    return found


def merged(wrong: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The list of what is wrong across the projects, oldest first and an entry with no time
    last. Entries of a kind that one machine shares (`SHARED`: the bus, a source, a source the
    pass could not ask) with the same subject and cause are one entry, which names each place
    and is wrong since the oldest of them. Any other entry stays one per project, so a red main
    of two repos is two entries."""
    found: dict[Any, dict[str, Any]] = {}
    for at, one in enumerate(wrong):
        key = (one["kind"], one["subj"], one["cause"]) if one["kind"] in SHARED else at
        if key not in found:
            found[key] = one | {"where": list(one["where"])}
            continue
        kept = found[key]
        kept["where"] += one["where"]
        times = [time for time in (kept["since"], one["since"]) if time]
        kept["since"] = min(times) if times else None
    return sorted(found.values(), key=lambda one: (one["since"] is None, one["since"] or ""))


def broken(wrong: list[dict[str, Any]], bus: dict[str, Any]) -> list[dict[str, str | None]]:
    """What is broken in a project, each as a plain reason, the drawer that has it, and
    `since`, when it broke, or None where nothing kept says. It says the kinds `main`, `ci`,
    `bus`, `source` and `unasked` of `wrong`, the project's list of what is wrong (`wrongs`),
    so the two never disagree. The failed branches are one reason, since the oldest of their
    runs, and so are the sources, since the oldest was written. It says nothing of what is
    well, and nothing of what is only quiet."""
    found: list[dict[str, str | None]] = []
    for kind, drawer in (("main", "pulse"), ("ci", "checks"), ("bus", "bus")):
        mine = [one for one in wrong if one["kind"] == kind]
        times = [one["since"] for one in mine if one["since"]]
        since = min(times) if times else None
        if not mine:
            continue
        if kind == "main":
            what = f"main red {mine[0]['cause'].rpartition(' ')[2]}"
        elif kind == "ci":
            what = "CI not read" if mine[0]["subj"] == "CI" else f"CI {len(mine)} failed"
        else:
            what = f"bus outbox {bus['outbox']}" if bus["outbox"] else "bus failed to send"
        found.append({"what": what, "open": drawer, "since": since})
    unread = [one for one in wrong if one["kind"] == "source"]
    if unread:
        times = [one["since"] for one in unread if one["since"]]
        what = f"{len(unread)} source{'' if len(unread) == 1 else 's'} unread"
        found.append({"what": what, "open": "pulse", "since": min(times) if times else None})
    for one in wrong:
        if one["kind"] == "unasked":
            found.append(
                {"what": f"{one['subj']} did not answer", "open": "pulse", "since": one["since"]}
            )
    return found


def summary(read: Read) -> dict[str, Any]:
    """One project as the overview has it.

    It has how many things need the user. That is `waits`, the count of the project's
    `needs` and nothing else. It has the project's open tasks by step in the order of the line, what
    merged today, and its health. The threads are the ones that are out, or None where
    the last pass left no list. `blind` is what the project's page cannot say now. It leaves
    out what the page never can say. It also leaves out a source the view could not read,
    because that source is in `unwell`. `unwell` is each source of the project that is not ok,
    except one that a session writes and one that is missing. A missing file is one jbus has
    not written for the project, as `ci.jsonl` where no `jbus ci` runs: the pulse lists it,
    and it is no fault. A file that is there and cannot be read is. A source or a blind spot of
    the machine is on no project's row."""
    held = [task["step"] for task in read.tasks]
    steps = {key: held.count(key) for key in STEP if key in held}
    checks, bus = read.panel("checks")["checks"], read.panel("bus")["bus"]
    own = [
        spot
        for panel in read.panels
        for spot in (panel.data.blind(read) if hasattr(panel.data, "blind") else [])
        if not spot.machine
    ]
    unwell = _unwell(read)
    failed = {key: len(at) for key, at in checks["now"].items()} | {"error": checks["error"]}
    return {
        "name": read.name,
        "repo": read.where,
        "broken": broken(users(read), bus),
        "unplaced": [task["slug"] for task in read.tasks if task["step"] == UNKNOWN.key],
        "waits": len(read.panel("you")["needs"]),
        "open": len(held),
        "steps": steps,
        "merged": len(read.panel("merged")["merged"]),
        "threads": read.out,
        "homes": read.homes.group(read.tasks, read.panel("you")["needs"], read.out, read.acts),
        "last": read.acts[-1] if read.acts else None,
        "health": {
            "checks": failed,
            "bus": {key: bus[key] for key in ("outbox", "failed_wakes", "last_error")},
            "threads": None if read.out is None else sum(1 for one in read.out if one["out"]),
            "blind": len(own),
            "unwell": [{"name": one["name"], "state": one["state"]} for one in unwell],
        },
    }


def needs(
    sources: Sources,
    name: str,
    now: datetime,
    runs: Callable[[str], dict[str, Any]],
    found: tuple[panels.Panel, ...] | None = None,
) -> list[dict[str, Any]]:
    """What waits on the user in one project, oldest first, as `/stack.json`'s `needs` has
    each entry: the feed's catch-up (`jbus.feed`)."""
    found = panels.found() if found is None else found
    shape = next(panel.shape for panel in found if panel.name == "you")["needs"]
    return keep(Read(sources, name, now, runs, found=found).panel("you")["needs"], shape)


def stack(
    sources: Sources,
    now: datetime,
    runs: Callable[[str], dict[str, Any]],
    code: dict[str, Any] | None = None,
    found: tuple[panels.Panel, ...] | None = None,
    names: list[str] | None = None,
) -> dict[str, Any]:
    """What `/stack.json` holds.

    It has the machine once, the steps of the line and the roles of a thread
    (`roles.ROLES`). It has a summary of each project of `names`, or of each project the
    state directory has. It has the user's two queues across the projects: `needs`, oldest
    first, and `proceeds`, the soonest to go ahead first. It has `wrong`, what is wrong across
    the projects that is the user's (`users`), with the machine's sources that are not ok, and
    one cause that several projects share as one entry (`merged`). What an agent owns is on its
    row (`fixing`), never here.

    The machine is what one jbus and one room provide for every project: the pass and the
    timer, the room and the plan's use, and the runner units. A `Read` of its own reads each
    project as `/state.json` reads it, and every `Read` shares one `machine`. So one answer
    asks systemd, the room script and the runner units once each, however many projects
    there are. It calls `runs` once for each repo, and `runs` keeps its answer. Under `unwell`, the
    machine lists each of its own sources that is not ok, except one that a session writes.
    No project's row gives those sources. Each panel with a `stack` adds what it gives, except one
    that is `alone` (`panels.Panel.alone`).
    """
    found = panels.found() if found is None else found
    keys(found)
    shared: dict[Any, Any] = {}
    shapes = {panel.name: panel.shape for panel in found}
    base = Read(sources, "", now, runs, code, found, shared)
    pulse = shapes["pulse"]["jbus"]
    kept_by_jbus = {key: pulse["status"][key] for key in KEPT_BY_JBUS}
    checks = base.panel("checks")["checks"]
    machine = {
        "jbus": keep(base.panel("pulse")["jbus"], pulse | {"status": kept_by_jbus}),
        "room": keep(base.panel("room")["room"], shapes["room"]["room"]),
        "runners": keep(checks["runners"], shapes["checks"]["checks"]["runners"]),
        "runners_read": checks["runners_read"],
        "unwell": [
            {"name": one.name, "state": seen["state"]}
            for panel in found
            for one in panel.sources
            if one.machine
            and one.by != "session"
            and (seen := _source(one.name, one.by, now=now, **one.seen(base)))["state"] != "ok"
        ],
    }
    reads = [
        Read(sources, name, now, runs, code, found, shared)
        for name in (projects(sources) if names is None else names)
    ]
    every = [keep(summary(read), SUMMARY) for read in reads]
    queues = [read.panel("you") for read in reads]
    shape = shapes["you"]
    needs = oldest([one for each in queues for one in keep(each["needs"], shape["needs"])])
    proceeds = sorted(
        (one for each in queues for one in keep(each["proceeds"], shape["proceeds"])),
        key=lambda one: (one["due"] or "~", one["project"], one["key"]),
    )
    line = [{"key": one.key, "name": one.name, "who": one.who} for one in (*STEPS, UNKNOWN)]
    machine_wrong = [
        {
            "kind": "source",
            "subj": one["name"],
            "cause": SOURCE_IS.get(one["state"], one["state"]),
            "since": None,
            "where": [],
            "row": "",
            "owner": USER,
            "fixing": None,
        }
        for one in machine["unwell"]
    ]
    answer = {
        "at": iso(now),
        "machine": machine,
        "steps": line,
        "roles": shown_roles(),
        "projects": every,
        "needs": needs,
        "proceeds": proceeds,
        "wrong": merged(
            machine_wrong + [one for read in reads for one in keep(users(read), [WRONG])]
        ),
    }
    for panel in found:
        if hasattr(panel.data, "stack") and not panel.alone:
            added = keep(panel.data.stack(base, reads, answer), panel.shape)
            if taken := set(added) & set(answer):
                raise ValueError(f"the panel {panel.name} gives {sorted(taken)}, which are taken")
            answer |= added
    return answer
