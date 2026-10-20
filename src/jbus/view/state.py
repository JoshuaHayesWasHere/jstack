"""What `/state.json` holds: the bus as one dict, read from what the passes left.

The dict is a frame and what each panel adds to it. A panel is one folder of `panels/`,
and its `panel.py` has its data: the function that builds its keys, the shape they are
cut to, and the sources it reads. This module has what the panels share. `Read` is one
project at one moment, with each file read once: the queue, what the last pass left, the
logs. `Source` and `Spot` are what a panel declares. `build` puts the frame (`FRAME`) and
the panels of the first screen together, and `Read.asked` answers for one panel by itself.

Each time it is called it reads the files the panels name of the project's state directory
and of its home's, `pass.json` and `status.json` beside them, what systemd says of the
timer and the service, and the machine: its load, memory, pressure, the file slots of
`/tmp` and the plan's limits. It reads no config of jbus: the projects are the directories
of the state directory that hold a `queue.json`, and a project's home is the directory of
its name. It also reads `leftover.json` where a pass wrote one (`jbus.leftover`). It never
opens the outbox or the stored token, and it writes nothing. The one
setting it takes is the user's time zone (`jsettings`), which a time with no zone is in.

The line is `STEPS`, twelve steps from Queued to Merged. Each open row of the queue is a
task on one step, held by the user, a crewmate, a reviewer, the check runner, jbus, its home
or another task. The view works no state out: the last pass judged each row once
(`jbus.work`) and wrote it to `work.json`, and a task is drawn as that file has it, its
value, its holder, what it waits for and the step of the line it is on. A row that merged
or is done and leaves nothing is off the line (`queue.over`). The words a state is said in
are the view's: the reason `jmerge` gave, the rows in front of it, the line of its gate,
the note a Result leaves, whole, and since when its home has a leftover.

What the pass could not work out it did not guess, and neither does the view. A value is
`unknown` for a set of facts no state holds for, and a row `work.json` does not have is
`unknown` too. An unknown task is on no step of the line: its step is `UNKNOWN`, which the
dict has under `unknown`, a lane of its own that the page draws only while a task is on it.
Nobody is said to hold it, and it says the facts it has.

A task is in one state, `state`, and that is what the page says of it: its kind (the value
of `work.json`), its name, the one sentence of it, and the one thing it waits for. Only open
work is in `tasks`. A row the pass judged merged or done while its row is not over is in
`ended`. A task that cannot move says what holds it in `blocked`, and how many tasks wait
behind it in `blocks`. A task the last pass did not confirm says so in `unconfirmed`.

`threads` is every thread the last pass saw that is not settled, a crew's, a scout's, a
reviewer's, a home's or any other, each with its liveness (`jbus.live`), or null where the
pass left no list: that is a blind spot, never a count of none. A task says
its own thread's under `seen.live`. A pull request that has had no review for `REVIEW_MINUTES`,
with no reviewer's thread listed, says so.

jbus has stopped when the timer is not active, or when the last pass ended more than
`QUIET` seconds ago and systemd does not say one is running now. A pass that starts and
dies each minute has stopped too: a start is no end. Each source says who
writes it: what jbus writes stands as the last pass left it, and what the server reads
itself is as it is now. The limits file is written by a session's status line, so it is
old whenever no session ran: it says its age, and is no fault of jbus.

A pass that could not ask T3 Code or GitHub derives no row, and `pass.json` names the
source under `silent`. While it does, every task of that project says so in `unconfirmed`:
since which pass its row is not confirmed, and which source did not answer. The plan's
limits file is a source too, with the time it was last written. A limit in it whose reset
time has passed is from a window that is over: its use is not known, and is never given
as a number.

`waiting` is the list of what waits on the user. An item that is a question jbus holds is
`answerable`, and has what its gate wrote, so that the page can answer it: its `context`,
its `options` (each one's `name`, what `follows` from it, whether it is the `default` that
was taken and whether the thread `recommended` it), what was `built_on` the default and
how to `undo` it, and who asked: the `slug`, the `thread` an answer goes to and that
thread's `role` (`asker`). A gate that lives only in a home's `gates.md` is not answerable.

`jbus.code` says which code of the view answers: when the server started, and whether a
file it runs is newer on disk than that.

The dict has the keys `keys` gives and no other, each built from named fields and cut to
its panel's shape. Every time in it is UTC, as ISO 8601 writes it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any

import jsettings
from jbus import (
    current_level,
    dispatch,
    leftover,
    merge,
    mirror,
    noticed,
    old_names,
    questions,
    queue,
    read_json,
    waiting,
    work,
)
from jbus.live import LIVENESS, OUT
from jbus.threads import OTHER, REPORT, ROLES
from jbus.threads import shown as shown_roles
from jbus.view import panels
from jbus.view.clean import ANY, HOST, keep
from jbus.wake import LOG

APPROVAL = 400
HISTORY, TASK_EVENTS, LINE, NOTE = 40, 8, 300, 4000
REVIEW_MINUTES = 10
NO_REVIEWER = "no reviewer has started"
NO_REVIEW = "no review yet"
WHOLE = NOTE + 2 * LINE
WORDS = 600
FRAME = ("at", "project", "projects", "repo", "sources", "summary", "kinds", "roles")
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
    "proof": WAITS,
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
    """One step of the line: its lane, who holds a task there, and what it waits for."""

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
    Step("check", "Check", "ci", "it waits for a runner, then runs"),
    Step("proof", "Proof", "rev", "a guarded path needs a proven safety fact"),
    Step("rebase", "Rebase", "crew", "main moved under it, or a rebase dropped lines"),
    Step("hold", "Needs you", "user", "jmerge will not merge it until you say"),
    Step("merged", "Merged", "ok", "merged today", "Done"),
)
UNKNOWN = Step("unknown", "Unknown", "unknown", "the view cannot work out its state")
STEP = {step.key: step for step in (*STEPS, UNKNOWN)}


@dataclass(frozen=True)
class Sources:
    """Where everything is read from. Only a test names another place than the machine's."""

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
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def when(given: Any, user: jsettings.Settings = jsettings.DEFAULTS) -> str | None:
    """A time as a file has it, as UTC: a time ISO 8601 writes, seconds since 1970, or a
    stamp of a pass, `YYYY-MM-DD HH:MM` with or without the word of its zone, which is a
    time in the user's zone. None for any other."""
    try:
        if isinstance(given, int | float) and not isinstance(given, bool):
            return iso(datetime.fromtimestamp(given, UTC))
        if not isinstance(given, str) or not given:
            return None
        stamped = _STAMP.fullmatch(given)
        if stamped:
            return iso(user.local(datetime.fromisoformat(stamped[1])))
        moment = datetime.fromisoformat(given.replace("Z", "+00:00"))
        return iso(moment if moment.tzinfo else user.local(moment))
    except (ValueError, OverflowError, OSError):
        return None


def text(given: Any, cap: int = LINE) -> str:
    return given[:cap] if isinstance(given, str) else ""


def by_rule(row: queue.Row) -> dict[str, str] | None:
    """The rule and the parent of a row a home approved by a standing rule, which is the mark
    the page puts on it, or None for a row the user gave his own word for, or none."""
    made = queue.record(row)
    if not made or made.basis != queue.RULE:
        return None
    return {"rule": text(made.ref, 20), "follows": text(made.follows, 80)}


def count(given: Any) -> int:
    return given if isinstance(given, int) and not isinstance(given, bool) else 0


def projects(sources: Sources) -> list[str]:
    """The projects jbus looks after, by what it left: each directory with a `queue.json`."""
    try:
        found = [
            path.name for path in sources.state_dir.iterdir() if (path / "queue.json").is_file()
        ]
    except OSError:
        return []
    return sorted(found)


def repo(sources: Sources, name: str) -> str:
    """The project's repo on GitHub, `<owner>/<name>`: the one of the newest pull request
    `jmerge` logged a `wait` or a `hold` for, by the URL that names it in the line. Nothing
    where it has logged none. A URL inside a line's reason names no repo."""
    for logged in reversed(_lines(sources.home(name) / "merge.log") or []):
        stamped = _LOGGED.match(logged)
        line = merge.parse(stamped[2]) if stamped else None
        found = _PULL.fullmatch(line.name) if line and line.word in ("wait", "hold") else None
        if found:
            return found[1]
    return ""


def pulls(sources: Sources, name: str) -> dict[str, int | None]:
    """Each slug of the project's queue, with the number of its pull request or None: the
    one its row names, or the one `merge.log` says merged for it where the row names none."""
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
    """The lines of a `.jsonl` file that are a record. A line that is not is left out."""
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
    """What `jmerge` logged of each pull request, oldest first: when, the word, the step."""
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
            step = merge.step(f"{line.word}: {line.reason}")
            reason = line.reason if step else f"jmerge said: {line.reason}"
            step = step or UNKNOWN.key
        found.setdefault(line.number, []).append(
            {"at": at, "word": line.word, "step": step, "reason": text(reason)}
        )
    return found


def _stay(history: list[dict[str, str]], step: str) -> tuple[str | None, int]:
    """Since when a pull request is on its step, and how many times it came to it."""
    since, visits, last = None, 0, ""
    for one in history:
        if one["step"] == step and last != step:
            since, visits = one["at"], visits + 1
        last = one["step"]
    return (since if last == step else None), visits


def _landed(lines: list[str], user: jsettings.Settings) -> dict[str, tuple[int, str]]:
    """The pull request `jmerge` logged as merged for each slug, and when: its last one."""
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
    """What the last Result of a slug's brief has on its `Status:` line and on its `Left:`
    line, whole, or nothing for a brief that cannot be read."""
    if not _SLUG.fullmatch(slug):
        return "", ""
    for path in (home / "tasks" / f"{slug}.md", state / "briefs" / f"{slug}.md"):
        try:
            result = mirror.last_result(path.read_text(errors="replace"))
        except OSError:
            continue
        return mirror.field(result, "Status"), mirror.field(result, "Left")
    return "", ""


@dataclass(frozen=True)
class Held:
    """What `leftover.json` has of a row that ended with something left: the `Left:` line
    whole, when its home was told as the user reads a time, or nothing while it was not,
    the same time as the dict has one, why the row is the user's, or nothing while its
    home has it, and whether a thread was at work on it in the last pass."""

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
    """How a row that ended did so, in a few words, and its pull request's number."""
    number = _number(row)
    if merged:
        return f"its pull request{'' if number is None else f' #{number}'} is merged", number
    if number is None:
        return "it ended with no pull request", None
    return f"its thread ended and its pull request #{number} is not merged", number


def _leftover(
    row: queue.Row, value: str, merged: bool, result: tuple[str, str], his: str = ""
) -> tuple[str, str, str]:
    """What is said of a row that ended with something left, or whose pull request closed:
    its name, its sentence and what it waits for.

    Where its last Result says `Status: done`, its reason is a note and no pull request of
    its is left unmerged, the work is finished: it says how the work ended, the note its
    crewmate left, whole as the brief has it, and the two things that end it. Any other
    such row is not closed: it says the note or the reason the row has, and that its brief
    does not say the work is finished where a `Status:` was read that is not `done`. `his`
    is why a row with a home to tell waits on the user all the same (`leftover.his`), and is
    said after the note.
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
    """What is said of a row that ended with something left and that its home has: how it
    ended, the note whole, since when the home has it, and that the home closes it."""
    ended = _how(row, merged)[0]
    note = text(held.note, NOTE).rstrip(". ")
    return f"{ended}. Its crewmate left a note: {note}. jbus told its home {held.told}. {CLOSES}"


@dataclass(frozen=True)
class About:
    """What the view has of a row beside its state, to say it in words: the rows in front
    of it that are not merged or done, the line of its gate in the list the last pass left,
    what its brief's last Result says, and what `leftover.json` has of it."""

    blockers: list[str]
    asked: str
    result: tuple[str, str]
    held: Held | None


def _saying(row: queue.Row, line: dict[str, Any] | None, about: About) -> dict[str, str]:
    """The state of a row as the page says it: the value, the holder and what it waits for
    are the pass's, from `work.json` (`line`), and the words are worked out here. A row the
    last pass did not judge is `unknown`, with what its row says."""
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
    """The open work of the queue, each row in the state the last pass judged for it
    (`judged`, the rows of `work.json` by slug), and the rows that ended while their row
    says another thing.

    `out` is the threads the last pass listed (`_threads`), or None where it left no list.
    `held` is the record `leftover.json` has of each row that ended with something left.
    `unconfirmed` is what every one of them says while the last pass could not ask, and a
    row whose state the last pass did not confirm says so by itself."""
    crews: dict[str, list[dict[str, Any]]] = {}
    for one in out or []:
        if one["role"] == "crew":
            crews.setdefault(one["slug"], []).append(one)
    reviewed = {one["slug"] for one in out or [] if one["role"] == "reviewer"}
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
    flow = waves(sorted((row["slug"] for row in rows), key=lambda slug: slug in through), queued)
    for task in tasks:
        task["wave"], task["waits_on"] = flow.get(task["slug"], (None, ""))
    return tasks, ended


def waves(order: list[str], front: dict[str, list[str]]) -> dict[str, tuple[int, str]]:
    """The wave of each queued row, and the one row it waits on last.

    `order` is the queue's slugs, the rows the log has as merged last as in `blockers`, and
    `front` has each queued row with the rows in front of it that are not merged or done. A
    row `front` does not have is out, and counts as 0. The wave is 0 with nothing in front,
    and otherwise one more than the highest wave in front. The row it waits on last is the
    one of that highest wave, the first in the queue among equals. A row met again while its
    own wave is worked out counts as 0, so rows that depend on each other end.
    """
    place = {slug: at for at, slug in enumerate(order)}
    found: dict[str, int] = {}

    def wave(slug: str) -> int:
        if slug not in front:
            return 0
        if slug not in found:
            found[slug] = 0
            found[slug] = max((wave(one) + 1 for one in front[slug]), default=0)
        return found[slug]

    def last(slug: str) -> str:
        ahead = sorted(front[slug], key=lambda one: (-wave(one), place.get(one, len(place))))
        return ahead[0] if ahead else ""

    return {slug: (wave(slug), last(slug)) for slug in front}


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
    )
} | {"request": REQUEST}


def request(home: Path, slug: str) -> dict[str, str]:
    """What a scout's request says of its work, from `scouts/<slug>.md` under the home, which
    the view only reads: `researching` while it has no `## Report`, `reported` where the
    `Status:` of its last Report is `done`, `blocked` where it says so, `not done` for any
    other, as the scout skill holds a Report that is not done unfinished, and `missing` where
    there is no request to read. `status` is that line's words and `asks` the request's title.
    A gate a scout wrote in its Report is part of it: its own `Status:` is not the Report's."""
    try:
        whole = (home / SCOUTS / f"{slug}.md").read_text(errors="replace")
    except (OSError, ValueError):
        return {"state": "missing", "status": "", "asks": ""}
    lines = whole.splitlines()
    asks = text(lines[0].removeprefix("# ") if lines else "", 160)
    reports = [
        body for heading, body in mirror.sections(whole, gates_inside=True) if heading == REPORT
    ]
    if not reports:
        return {"state": "researching", "status": "", "asks": asks}
    own = re.split(r"^## ", reports[-1], maxsplit=1, flags=re.M)[0]
    status = text(mirror.field(own, "Status"), 160)
    word = status.split(" ", 1)[0]
    blocked = word.rstrip(",.:;") == "blocked"
    state = "reported" if word == "done" else "blocked" if blocked else "not done"
    return {"state": state, "status": status, "asks": asks}


def _threads(left: Any, home: Path | None = None, day: str = "") -> list[dict[str, Any]] | None:
    """Every thread the last pass listed as not settled, or None where it left no list.
    `out` is one a turn may be under way in: any but one that ended. `today` is one that is
    out or last wrote since `day` began, and a scout's has what its `request` says."""
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
        }
        if thread["role"] == "scout" and home is not None and _SLUG.fullmatch(thread["slug"]):
            thread["request"] = request(home, thread["slug"])
        found.append(thread)
    return found


def _blocks(tasks: list[dict[str, Any]], ended: list[dict[str, Any]]) -> None:
    """Mark each open task that cannot move with what holds it, and each task others wait
    behind with which do: the ones that depend on it, and the ones behind those. A task is
    behind a row until that row says merged or done, as jbus holds it, whatever the row's state
    is: `blockers` has those rows, the ones the log has as merged last."""
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
    The loudness is by the name it has now: a line from before `chef` went is `quiet`."""
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


def threads_seen(sources: Sources, name: str) -> Any:
    """The threads the last pass listed for the project, as `pass.json` has them."""
    record = _table(sources.state_dir / "pass.json") or {}
    seen = record.get("projects", {}).get(name) if isinstance(record.get("projects"), dict) else {}
    return seen.get("threads") if isinstance(seen, dict) else None


def asker(home: Path, slug: str, threads: Any) -> tuple[str, str]:
    """The thread an answer to a question of the slug goes to, and that thread's role.

    The thread is the one `questions` sends to, on the `Thread:` line of the slug's brief or
    request. Its role is the one the last pass listed it with (`threads`), or the one its
    file gives it: a brief is a crew's and a request a scout's. Both are nothing for a slug
    with no such line."""
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
        if dispatch.thread_of(brief):
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

    A source with a path that is not there is missing, and any other that was not read is
    unreadable. A source is stale only where it is given `fresh`, the seconds it may be
    old: a file changes when something happens, so an old one says nothing, and whether
    the two files a pass writes are late is what `stopped` says. `gates.md` is read where a
    home still writes one, and a home that has none lacks nothing: jbus holds its gates.

    GitHub's answer is renewed each minute, and a `gh` that fails overwrites it with an
    error. So it is `GITHUB_FRESH` old, and stale, only when the server kept an answer
    while a slow `gh` had not come back. The limits file is stale when it is `old`: a
    limit in it has reset since it was written."""
    word = "ok" if read else "missing" if path is not None and not path.exists() else "unreadable"
    word = "stale" if read and old else word
    if read and at and fresh is not None:
        age = (now - datetime.fromisoformat(at)).total_seconds()
        word = "stale" if age > fresh else word
    return {"name": name, "by": by, "at": at, "state": word}


@dataclass(frozen=True)
class Source:
    """One source a panel reads: its name, who writes it (`jbus`, the `server` itself or a
    `session`), and how it is now, as the arguments `_source` takes beside `now`. The list
    of the sources is in the order of `rank`. A `machine` source is the same for every
    project, so the overview says it once, on the machine row, and on no project's row."""

    name: str
    by: str
    seen: Callable[[Read], dict[str, Any]]
    rank: int = 1000
    machine: bool = False


@dataclass(frozen=True)
class Spot:
    """One thing a panel cannot say, a line of `blind`, which opens the panel that says it.
    The lines are in the order of `rank`. A `machine` one is the same for every project."""

    line: str
    rank: int = 1000
    machine: bool = False


def kept(name: str, value: Callable[[Read], Any], rank: int = 1000) -> Source:
    """A file of the project's state directory, which jbus writes. It was read where
    `value` gives anything but None."""

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
    """What one answer is built from: one project at one moment, each file read once.

    A panel's `build` takes it. What more than one panel reads is a property here, and its
    source is one of the six above. What one panel works out and another needs is asked
    with `panel`, and `once` keeps what a panel works out for its own functions.
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
    ) -> None:
        self.sources, self.name, self.now, self.runs = sources, name, now, runs
        self.code = code or {}
        self.user = sources.user
        self.state, self.home = sources.state(name), sources.home(name)
        self.panels = panels.found() if found is None else found
        self._kept: dict[Any, Any] = {}
        self._shared: dict[Any, Any] = {} if shared is None else shared

    def once(self, make: Callable[[Read], Any]) -> Any:
        """What `make` gives of this, worked out the first time it is asked."""
        if make not in self._kept:
            self._kept[make] = make(self)
        return self._kept[make]

    def machine(self, make: Callable[[Read], Any]) -> Any:
        """What `make` gives of the machine, which is the same for every project: worked out
        the first time any `Read` that shares `shared` with this one asks, as one answer of
        `/stack.json` reads every project with one `shared`."""
        if make not in self._shared:
            self._shared[make] = make(self)
        return self._shared[make]

    def panel(self, name: str) -> dict[str, Any]:
        """What the panel `name` builds, before it is cut to its shape."""
        return self.once(next(one for one in self.panels if one.name == name).data.build)

    def table(self, file: str) -> dict[str, Any] | None:
        """A file of the project's state directory that holds one dict, or None."""
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
        """The rows of `queue.json`, or None where it could not be read."""
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
    def log(self) -> list[str] | None:
        return _lines(self.home / "merge.log")

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
    def out(self) -> list[dict[str, Any]] | None:
        """The threads the last pass listed, or None where it left no list."""
        return _threads(self.mine.get("threads"), self.home, self.day)

    @cached_property
    def unconfirmed(self) -> dict[str, Any] | None:
        """What every task says while the last pass could not ask a source, or None."""
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
        """What the last pass judged, `work.json`, or None where it could not be read."""
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
        return _tasks(
            self.rows,
            _history(self.log or [], self.user),
            self.judged,
            asked,
            self.moves or [],
            self.events,
            seen if isinstance(seen, dict) else {},
            self.user,
            lambda slug: _whole(self.state, self.home, slug),
            self.out,
            self.now,
            self.unconfirmed,
            leftover.read(self.state) if self.name else {},
        )

    @property
    def tasks(self) -> list[dict[str, Any]]:
        """The open work of the queue."""
        return self._open[0]

    @property
    def ended(self) -> list[dict[str, Any]]:
        """The rows that ended while they say another thing."""
        return self._open[1]

    @cached_property
    def day(self) -> str:
        """The start of the user's day."""
        return iso(self.user.local(self.now).replace(hour=0, minute=0, second=0, microsecond=0))

    @cached_property
    def listed(self) -> list[dict[str, Any]]:
        """Every source a panel names, once, in the order of its rank, and how it is now."""
        named: dict[str, Source] = {}
        for panel in self.panels:
            for source in panel.sources:
                named.setdefault(source.name, source)
        return self._how(named.values())

    def read_by(self, panel: panels.Panel) -> list[dict[str, Any]]:
        """The sources the panel names, and how each is now. No other source is looked at."""
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
        builds, cut to its shape."""
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
        }
        for panel in self.panels:
            if panel.first:
                parts |= keep(self.panel(panel.name), panel.shape)
        return parts

    def asked(self, name: str) -> dict[str, Any] | None:
        """What `/panel/<name>.json` holds: what the panel builds, cut to its shape, and how
        each source it names is now. None for a name no folder has."""
        panel = next((one for one in self.panels if one.name == name), None)
        if panel is None:
            return None
        return {
            "at": iso(self.now),
            "panel": name,
            "data": keep(self.panel(name), panel.shape),
            "sources": self.read_by(panel),
        }


def keys(found: tuple[panels.Panel, ...] | None = None) -> tuple[str, ...]:
    """The keys of `/state.json`: the frame's, then each key of the shape of a panel that is
    on the first screen. A key two of them give is refused."""
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
    """The state of one project, `name`, or of none where the state directory has none.

    `runs` gives the repo's last workflow runs, as `github.GitHub.runs` does. `code` is
    which code answers, as the server's `Code.said` gives it: it goes under `jbus`.
    """
    return Read(sources, name, now, runs, code).answer()


KEPT_BY_JBUS = ("last_pass", "token_expires", "streaks", "homes_off_bus")
SUMMARY = {
    "name": None,
    "repo": None,
    "waits": None,
    "noticed": None,
    "open": None,
    "steps": {ANY: None},
    "merged": None,
    "threads": [THREAD],
    "broken": [{"what": None, "open": None}],
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
    """The records of the user's queue, oldest `since` first and one with no time last, the
    project and the key breaking a tie."""
    return sorted(
        needs,
        key=lambda one: (one["since"] is None, one["since"] or "", one["project"], one["key"]),
    )


def broken(checks: dict[str, Any], bus: dict[str, Any], unwell: list[Any]) -> list[dict[str, str]]:
    """What is broken in a project, each as a plain reason and the drawer that has it: its
    checks that failed or could not be read, its bus when a wake failed, and its sources
    that could not be read. Nothing is said of what is well, or merely quiet."""
    found = []
    if checks["error"]:
        found.append({"what": "CI not read", "open": "checks"})
    elif checks["failed"]:
        found.append({"what": f"CI {checks['failed']} failed", "open": "checks"})
    if bus["failed_wakes"] or bus["last_error"]:
        what = f"bus outbox {bus['outbox']}" if bus["outbox"] else "bus failed to send"
        found.append({"what": what, "open": "bus"})
    if unwell:
        found.append(
            {
                "what": f"{len(unwell)} source{'' if len(unwell) == 1 else 's'} unread",
                "open": "pulse",
            }
        )
    return found


def summary(read: Read) -> dict[str, Any]:
    """One project as the overview has it: how many things need the user (`waits`, the
    count of the project's `needs` and nothing else), the new noticed lines (counted apart:
    they are no wait), its open tasks by step, in the order of the line, what merged today,
    and its health. The threads are the ones
    out, or None where the last pass left no list. Blind is what the project's page cannot
    say now, without what it never can and without a source that could not be read, which is
    in unwell. Unwell is each source of the project that is not ok, but for one a session
    writes. What is the machine's, a source or a blind spot, is on no project's row."""
    held = [task["step"] for task in read.tasks]
    steps = {key: held.count(key) for key in STEP if key in held}
    checks, bus = read.panel("checks")["checks"], read.panel("bus")["bus"]
    machine = {one.name for panel in read.panels for one in panel.sources if one.machine}
    own = [
        spot
        for panel in read.panels
        for spot in (panel.data.blind(read) if hasattr(panel.data, "blind") else [])
        if not spot.machine
    ]
    unwell = [
        {"name": one["name"], "state": one["state"]}
        for one in read.listed
        if one["state"] != "ok" and one["by"] != "session" and one["name"] not in machine
    ]
    failed = {key: len(at) for key, at in checks["now"].items()} | {"error": checks["error"]}
    return {
        "name": read.name,
        "repo": read.where,
        "broken": broken(failed, bus, unwell),
        "unplaced": [task["slug"] for task in read.tasks if task["step"] == UNKNOWN.key],
        "waits": len(read.panel("you")["needs"]),
        "noticed": sum(1 for one in read.panel("noticed")["noticed"] if one["mark"] == noticed.NEW),
        "open": len(held),
        "steps": steps,
        "merged": len(read.panel("merged")["merged"]),
        "threads": read.out,
        "health": {
            "checks": failed,
            "bus": {key: bus[key] for key in ("outbox", "failed_wakes", "last_error")},
            "threads": None if read.out is None else sum(1 for one in read.out if one["out"]),
            "blind": len(own),
            "unwell": unwell,
        },
    }


def stack(
    sources: Sources,
    now: datetime,
    runs: Callable[[str], dict[str, Any]],
    code: dict[str, Any] | None = None,
    found: tuple[panels.Panel, ...] | None = None,
    names: list[str] | None = None,
) -> dict[str, Any]:
    """What `/stack.json` holds: the machine once, the steps of the line and the roles of a
    thread (`threads.ROLES`), a summary of each project of `names`, or of each the state
    directory has, and the user's two queues across them: `needs`, oldest first, and
    `proceeds`, the soonest to go ahead first.

    The machine is what one jbus and one room serve every project with: the pass and the
    timer, the room and the plan's use, and the runner units. Each project is read as
    `/state.json` reads it, by a `Read` of its own, and every `Read` shares one `machine`, so
    systemd, the room script and the runner units are asked once for the answer, however
    many projects there are. `runs` is asked once for each repo, and keeps its answer.
    The machine says each of its own sources that is not ok, but for one a session writes,
    under `unwell`: no project's row says it.
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
    return {
        "at": iso(now),
        "machine": machine,
        "steps": line,
        "roles": shown_roles(),
        "projects": every,
        "needs": needs,
        "proceeds": proceeds,
    }
