"""The record files `jbus telemetry` compiles, each as one table: what a row of it keeps.

`SOURCES` is the registry: one `Source` per file of a project's records, by the table it fills.
A source's `row` is the table's allow-list. It turns one record into the row's columns, and it
is the only way a record reaches the store. It keeps ids, times, counts and labels, and turns
each text of a record into its length (`<name>_len`), so no table holds what a message said.

A source is a `log` or a `snapshot`:

- A log only grows: `events.jsonl`, `acts.jsonl`, `items.jsonl`, `transitions.jsonl`,
  `outbox.jsonl`, `ci.jsonl`, `review-rounds.jsonl` (`jbus.reviewed`), the home's `merge.log`,
  and the machine's `passes.jsonl`, the seconds of each pass (`jbus.record`), and
  `drift.jsonl`, each probe of a standing word in each run (`jbus.drift`). A row's key is the
  hash of the line, as JSON with sorted keys (as text for `merge.log`), and of how many equal
  lines come before it, as `jbus.wake.entries` names an event. So two equal lines are two rows,
  and a line read again, as after the daily trim rewrites `events.jsonl`, is the row it was.
  The machine's `capped.jsonl`, each read of which instances are capped (`jgauge.limits.note`),
  is a log too.
- A snapshot is written whole each time: `questions.json`, `queue.json`, `merged.json`,
  `ci-prs.jsonl` and `reverts.json`, each revert jbus opened (`jmerge.reverts`). A row's key is
  the record's own (`number`, `slug`, or a revert's red tip), and a newer snapshot updates the
  row and never deletes one, so a record that leaves the file stays in the store.

Each time is kept in UTC, in one form of fixed width (`utc`), so that text order is time order,
and each table has the local `day` of its `at` column in the user's zone, since SQLite has no
zone of its own to bucket by.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import tzinfo
from typing import Any, Literal

from jbus.telemetry import asks
from jbus.telemetry.readers import json_lines, keyed, listed, questions
from jbus.telemetry.values import MACHINE as MACHINE
from jbus.telemetry.values import STAMP as STAMP
from jbus.telemetry.values import Row, _count, _dict, _length, _number, _pull, _text, utc
from jbus.telemetry.values import day as day
from jbus.telemetry.values import key as key

_MERGE_LINE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (\S+)(?: #?(\d+))?(?: (\S+))?")
_LABEL = re.compile(r"\[([\w-]+)\]\s*$")


def _events(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "event": _text(one.get("event")),
        "slug": _text(one.get("slug")),
        "loud": _text(one.get("loud")),
        "item": _text(one.get("item")),
        "act": _text(one.get("act")),
        "subject": _text(one.get("subject")),
        "line_len": _length(one.get("line")),
        "text_len": _length(one.get("text")),
    }


def _acts(one: Row, zone: tzinfo | None) -> Row:
    action, evidence, party = (_dict(one.get(name)) for name in ("action", "evidence", "party"))
    return {
        "id": _text(one.get("id")),
        "at": utc(one.get("at"), zone),
        "verb": _text(action.get("verb")),
        "subject": _text(action.get("subject")),
        "outcome": _text(one.get("outcome")),
        "party": _text(party.get("kind")),
        "party_name": _text(party.get("name")),
        "route": _text(party.get("route")),
        "source": _text(evidence.get("source")),
        "ref": _text(evidence.get("ref")),
        "said_in": _text(evidence.get("said_in")),
        "said_at": utc(evidence.get("said_at"), zone),
        "gate": _number(one.get("gate")),
        "doors": _count(action.get("doors")),
        "picks": _count(evidence.get("picks")),
        "words_len": _length(evidence.get("words")),
        "line_len": _length(one.get("line")),
        "checked": evidence.get("checked") if isinstance(evidence.get("checked"), bool) else None,
        "asks": _asks(action.get("verb"), evidence.get("words")),
    }


def _asks(verb: object, words: object) -> str | None:
    """What a word asks, by the rule of a T3 Code message's; no other act has a label."""
    if verb != "word":
        return None
    return asks.label(words if isinstance(words, str) else None)


def _passes(one: Row, zone: tzinfo | None) -> Row:
    seconds = one.get("seconds")
    return {
        "at": utc(one.get("at"), zone),
        "seconds": seconds if isinstance(seconds, int | float) else None,
    }


def _drift(one: Row, zone: tzinfo | None) -> Row:
    texts = {name: _text(one.get(name)) for name in ("probe", "word", "status", "sha", "error")}
    return {"at": utc(one.get("at"), zone), **texts, "found": _number(one.get("found"))}


def _capped_reads(one: Row, zone: tzinfo | None) -> Row:
    """A read of which instances the ledger has capped (`jgauge.limits.note`): how many it read,
    how many were capped, and, where every one was, `ends_at`, the first time one is free again."""
    instances, capped = one.get("instances"), _dict(one.get("capped"))
    count = _count(instances)
    frees = [found for found in (utc(at) for at in capped.values()) if found is not None]
    every = bool(count) and len(frees) == len(capped) >= count
    return {
        "at": utc(one.get("at"), zone),
        "reader": _text(one.get("reader")),
        "instances": count,
        "capped": len(capped),
        "ends_at": min(frees) if every else None,
    }


def _items(one: Row, zone: tzinfo | None) -> Row:
    return {
        "id": _text(one.get("id")),
        "at": utc(one.get("at"), zone),
        "item": _text(one.get("item")),
        "verb": _text(one.get("verb")),
        "slug": _text(one.get("slug")) or None,
        "by": _text(one.get("by")),
        "by_user": _text(one.get("by_user")),
        "place": _text(one.get("where")),
        "title_len": _length(one.get("title")),
        "line_len": _length(one.get("line")),
    }


def _transitions(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "from_status": _text(one.get("from")),
        "to_status": _text(one.get("to")),
        "by": _text(one.get("by")),
        "why_len": _length(one.get("why")),
    }


def _outbox(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "thread": _text(one.get("thread")),
        "row": _text(one.get("row")),
        "template": _text(one.get("template")),
        "needs": _text(one.get("needs")),
        "send_key": _text(one.get("key")),
        "went": _text(one.get("went")),
        "rule": _text(one.get("rule")),
    }


def _ci_jobs(one: Row, zone: tzinfo | None) -> Row:
    return {
        "run": _number(one.get("run")),
        "job": _number(one.get("job")),
        "attempt": _number(one.get("attempt")),
        "name": _text(one.get("name")),
        "sha": _text(one.get("sha")),
        "branch": _text(one.get("branch")),
        "pr": _number(one.get("pr")),
        "event": _text(one.get("event")),
        "created": utc(one.get("created"), zone),
        "started": utc(one.get("started"), zone),
        "completed": utc(one.get("completed"), zone),
        "conclusion": _text(one.get("conclusion")),
        "runner": _text(one.get("runner")),
        "kind": _text(one.get("kind")),
        "steps": _number(one.get("steps")),
        "selection": _text(one.get("selection")),
        "slowest_s": one.get("slowest_s")
        if isinstance(one.get("slowest_s"), int | float)
        else None,
        "tail_s": one.get("tail_s") if isinstance(one.get("tail_s"), int | float) else None,
        "workers": _number(one.get("workers")),
        "tests": _count(one.get("tests")),
        "signs": _count(one.get("signs")),
    }


def _merges(line: str, zone: tzinfo | None) -> Row:
    """A line of `merge.log`, `<YYYY-MM-DD HH:MM> <verb> <number> <url or slug> ...`, in the
    user's zone: its verb, its number, a merge's slug and a wait's `[label]`."""
    found = _MERGE_LINE.match(line)
    label = _LABEL.search(line)
    merged = found is not None and found[2] == "merged"
    return {
        "at": utc(found[1], zone) if found else None,
        "verb": found[2] if found else None,
        "number": int(found[3]) if found and found[3] else None,
        "slug": found[4] if merged else None,
        "label": label[1] if label else None,
        "line_len": len(line),
    }


def _merge_waits(one: Row, zone: tzinfo | None) -> Row:
    held = {code: s for code, s in _dict(one.get("blockers")).items() if isinstance(s, int | float)}
    return {
        "at": utc(one.get("began"), zone),
        "number": _number(one.get("number")),
        "head": _text(one.get("head")),
        "ready": utc(one.get("ready"), zone),
        "ready_by": _text(one.get("ready_by")),
        "seconds": one["seconds"] if isinstance(one.get("seconds"), int | float) else None,
        "blocker": max(sorted(held), key=held.__getitem__) if held else None,
        "blockers": json.dumps(held, sort_keys=True),
    }


def _questions(one: Row, zone: tzinfo | None) -> Row:
    answer = _dict(one.get("answer"))
    return {
        "number": _number(one.get("number")),
        "slug": _text(one.get("slug")),
        "thread": _text(one.get("thread")),
        "asked_at": utc(one.get("asked_at"), zone),
        "holds": bool(one.get("holds")),
        "options": _count(one.get("options")),
        "answered_at": utc(answer.get("at"), zone),
        "answered_by": _text(answer.get("by")),
        "closed_by": _text(answer.get("closed_by")),
        "answer_place": _text(answer.get("where")),
        "keeps": answer.get("keeps") if isinstance(answer.get("keeps"), bool) else None,
        "ref": _text(answer.get("ref")),
        "question_len": _length(one.get("question")),
        "default_len": _length(one.get("default")),
        "context_len": _length(one.get("context")),
        "words_len": _length(answer.get("words")),
    }


def _queue(one: Row, zone: tzinfo | None) -> Row:
    approval = _dict(one.get("approval"))
    return {
        "slug": _text(one.get("slug")),
        "status": _text(one.get("status")),
        "item": _text(one.get("item")),
        "entry": _text(one.get("entry")) or _text(one.get("parent_entry")),
        "priority": _number(one.get("priority")),
        "thread": _text(one.get("thread")),
        "pr": _pull(one.get("pr")),
        "on_hold": bool(one.get("held")),
        "role": _text(one.get("role")),
        "updated": utc(one.get("updated"), zone),
        "approval_basis": _text(approval.get("basis")),
        "approval_ref": _text(approval.get("ref")),
        "approval_said_at": utc(approval.get("said_at"), zone),
        "approval_ran_at": utc(approval.get("ran_at"), zone),
        "follows": _text(approval.get("follows")) or None,
    }


def _merged(one: Row, zone: tzinfo | None) -> Row:
    return {
        "slug": _text(one.get("slug")),
        "number": _number(one.get("number")),
        "merged_at": utc(one.get("mergedAt"), zone),
        "merge_commit": _text(_dict(one.get("mergeCommit")).get("oid")),
        "state": _text(one.get("state")),
        "title_len": _length(one.get("title")),
    }


def _ci_prs(one: Row, zone: tzinfo | None) -> Row:
    return {
        "number": _number(one.get("number")),
        "branch": _text(one.get("branch")),
        "head": _text(one.get("head")),
        "created": utc(one.get("created"), zone),
        "updated": utc(one.get("updated"), zone),
        "merged": utc(one.get("merged"), zone),
        "closed": utc(one.get("closed"), zone),
        "merge_commit": _text(one.get("merge_commit")),
        "pushes": _count(one.get("pushes")),
    }


def _reverts(one: Row, zone: tzinfo | None) -> Row:
    return {
        "red": _text(one.get("red")),
        "slug": _text(one.get("slug")),
        "branch": _text(one.get("branch")),
        "pr": _pull(one.get("pull")),
    }


def _brief_versions(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "sha": _text(one.get("sha")),
        "was": _text(one.get("was")),
        "bytes": _number(one.get("bytes")),
    }


def _row_pulls(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "number": _number(one.get("number")),
        "state": _text(one.get("state")),
        "branch": _text(one.get("branch")),
        "head": _text(one.get("head")),
        "merged_at": utc(one.get("merged_at"), zone),
    }


def _runs(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "run": _number(one.get("run")),
        "attempt": _number(one.get("attempt")),
        "workflow": _text(one.get("workflow")),
        "sha": _text(one.get("sha")),
        "branch": _text(one.get("branch")),
        "event": _text(one.get("event")),
        "pr": _number(one.get("pr")),
        "created": utc(one.get("created"), zone),
        "started": utc(one.get("started"), zone),
        "updated": utc(one.get("updated"), zone),
        "conclusion": _text(one.get("conclusion")),
    }


SPENT = ("units", "runs", "input", "cached", "written", "output")
KINDS = ("first", "reviews", "fixes", "sends", "homes", "scouts", "capped")
"""The units of a day's spend by kind, as `jgauge.spend.COLUMNS` names them."""


def _spend_days(one: Row, zone: tzinfo | None) -> Row:
    spent_on = _text(one.get("day"))
    return {
        "at": utc(one.get("at"), zone),
        "spent_on": spent_on,
        **{name: _number(one.get(name)) for name in (*SPENT, *KINDS)},
    }


def _spend_rows(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "spent_on": _text(one.get("day")),
        "role": _text(one.get("role")),
        "slug": _text(one.get("slug")) or None,
        **{name: _number(one.get(name)) for name in SPENT},
    }


def _word_sends(one: Row, zone: tzinfo | None) -> Row:
    return {
        "word": _text(one.get("id")),
        "thread": _text(one.get("thread")) or None,
        "sent_at": utc(one.get("sent_at"), zone),
        "waiting": bool(one.get("waits")),
    }


SEVERITIES = ("errors", "warnings", "infos", "others", "dismissed")
"""The counts of a review round's findings by severity, as `jbus.reviewed.round_lines` writes
them: `others` of a severity none of the three, and `dismissed` those its lead dismissed."""


def _review_rounds(one: Row, zone: tzinfo | None) -> Row:
    return {
        "at": utc(one.get("at"), zone),
        "slug": _text(one.get("slug")),
        "pr": _number(one.get("pr")),
        "round_number": _number(one.get("round")),
        "head": _text(one.get("head")),
        "scoped": one.get("scoped") if isinstance(one.get("scoped"), bool) else None,
        "sections": _number(one.get("sections")),
        "meets": _text(one.get("meets")),
        "met": _number(one.get("met")),
        "done_when": _number(one.get("of")),
        **{name: _number(one.get(name)) for name in SEVERITIES},
    }


@dataclass(frozen=True)
class Source:
    """A file of a project's records and the table it fills.

    `where` is `state`, the project's jbus state (`Config.state`), `home`, its home's
    (`Config.home`), or `machine`, jbus's own state directory, whose rows are the machine's, of
    the project `MACHINE`. `columns` are the table's own columns besides `project`, `key` and `day`,
    each with its SQLite type, and `row` makes them of one record. A log's `text` is True where
    its lines are text, not JSON. A snapshot's `records` reads its records from the file, and
    `natural` names the column that is its key. `at` names the column whose local date is
    `day`."""

    table: str
    file: str
    kind: Literal["log", "snapshot"]
    columns: tuple[tuple[str, str], ...]
    row: Callable[[Any, tzinfo | None], Row]
    at: str = "at"
    where: Literal["state", "home", "machine"] = "state"
    text: bool = False
    records: Callable[[str], Iterable[Row]] = json_lines
    natural: str = ""


def _columns(*names: str) -> tuple[tuple[str, str], ...]:
    """Columns by name, typed by their suffix: `_len`, counts and numbers are INTEGER."""
    whole = {
        "gate",
        "doors",
        "picks",
        "run",
        "job",
        "attempt",
        "pr",
        "steps",
        "workers",
        "tests",
        "signs",
        "number",
        "options",
        "priority",
        "pushes",
        "holds",
        "on_hold",
        "keeps",
        "bytes",
        "waiting",
        "instances",
        *SPENT,
        *KINDS,
        "checked",
        "round_number",
        "scoped",
        "sections",
        "met",
        "done_when",
        *SEVERITIES,
        "found",
    }
    real = {"slowest_s", "tail_s", "seconds"}
    return tuple(
        (
            name,
            "INTEGER"
            if name.endswith("_len") or name in whole
            else "REAL"
            if name in real
            else "TEXT",
        )
        for name in names
    )


_WAITS = _columns("at", "number", "head", "ready", "ready_by", "seconds", "blocker", "blockers")
SOURCES: tuple[Source, ...] = (
    Source(
        "events",
        "events.jsonl",
        "log",
        _columns("at", "event", "slug", "loud", "item", "act", "subject", "line_len", "text_len"),
        _events,
    ),
    Source(
        "acts",
        "acts.jsonl",
        "log",
        _columns(
            "id",
            "at",
            "verb",
            "subject",
            "outcome",
            "party",
            "party_name",
            "route",
            "source",
            "ref",
            "said_in",
            "said_at",
            "gate",
            "doors",
            "picks",
            "words_len",
            "line_len",
            "checked",
            "asks",
        ),
        _acts,
    ),
    Source(
        "items",
        "items.jsonl",
        "log",
        _columns(
            "id", "at", "item", "verb", "slug", "by", "by_user", "place", "title_len", "line_len"
        ),
        _items,
    ),
    Source(
        "transitions",
        "transitions.jsonl",
        "log",
        _columns("at", "slug", "from_status", "to_status", "by", "why_len"),
        _transitions,
    ),
    Source(
        "outbox",
        "outbox.jsonl",
        "log",
        _columns("at", "thread", "row", "template", "needs", "send_key", "went", "rule"),
        _outbox,
    ),
    Source(
        "ci_jobs",
        "ci.jsonl",
        "log",
        _columns(
            "run",
            "job",
            "attempt",
            "name",
            "sha",
            "branch",
            "pr",
            "event",
            "created",
            "started",
            "completed",
            "conclusion",
            "runner",
            "kind",
            "steps",
            "selection",
            "slowest_s",
            "tail_s",
            "workers",
            "tests",
            "signs",
        ),
        _ci_jobs,
        at="created",
    ),
    Source(
        "merges",
        "merge.log",
        "log",
        _columns("at", "verb", "number", "slug", "label", "line_len"),
        _merges,
        where="home",
        text=True,
    ),
    Source(
        "questions",
        "questions.json",
        "snapshot",
        _columns(
            "number",
            "slug",
            "thread",
            "asked_at",
            "holds",
            "options",
            "answered_at",
            "answered_by",
            "closed_by",
            "answer_place",
            "keeps",
            "ref",
            "question_len",
            "default_len",
            "context_len",
            "words_len",
        ),
        _questions,
        at="asked_at",
        records=questions,
        natural="number",
    ),
    Source(
        "queue",
        "queue.json",
        "snapshot",
        _columns(
            "slug",
            "status",
            "item",
            "entry",
            "priority",
            "thread",
            "pr",
            "on_hold",
            "role",
            "updated",
            "approval_basis",
            "approval_ref",
            "approval_said_at",
            "approval_ran_at",
            "follows",
        ),
        _queue,
        at="approval_ran_at",
        records=listed,
        natural="slug",
    ),
    Source(
        "merged",
        "merged.json",
        "snapshot",
        _columns("slug", "number", "merged_at", "merge_commit", "state", "title_len"),
        _merged,
        at="merged_at",
        records=keyed("slug"),
        natural="slug",
    ),
    Source(
        "ci_prs",
        "ci-prs.jsonl",
        "snapshot",
        _columns(
            "number",
            "branch",
            "head",
            "created",
            "updated",
            "merged",
            "closed",
            "merge_commit",
            "pushes",
        ),
        _ci_prs,
        at="created",
        natural="number",
    ),
    Source(
        "brief_versions",
        "brief-versions.jsonl",
        "log",
        _columns("at", "slug", "sha", "was", "bytes"),
        _brief_versions,
    ),
    Source(
        "row_pulls",
        "row-pulls.jsonl",
        "log",
        _columns("at", "slug", "number", "state", "branch", "head", "merged_at"),
        _row_pulls,
    ),
    Source(
        "runs",
        "runs.jsonl",
        "log",
        _columns(
            "at",
            "run",
            "attempt",
            "workflow",
            "sha",
            "branch",
            "event",
            "pr",
            "created",
            "started",
            "updated",
            "conclusion",
        ),
        _runs,
        at="updated",
    ),
    Source(
        "spend_days",
        "spend.jsonl",
        "log",
        _columns("at", "spent_on", *SPENT, *KINDS),
        _spend_days,
    ),
    Source(
        "spend_rows",
        "spend-rows.jsonl",
        "log",
        _columns("at", "spent_on", "role", "slug", *SPENT),
        _spend_rows,
    ),
    Source(
        "word_sends",
        "word-sends.json",
        "snapshot",
        _columns("word", "thread", "sent_at", "waiting"),
        _word_sends,
        at="sent_at",
        records=keyed("id"),
        natural="word",
    ),
    Source(
        "reverts",
        "reverts.json",
        "snapshot",
        _columns("red", "slug", "branch", "pr"),
        _reverts,
        at="",
        records=keyed("red"),
        natural="red",
    ),
    Source("passes", "passes.jsonl", "log", _columns("at", "seconds"), _passes, where="machine"),
    Source(
        "review_rounds",
        "review-rounds.jsonl",
        "log",
        _columns(
            "at",
            "slug",
            "pr",
            "round_number",
            "head",
            "scoped",
            "sections",
            "meets",
            "met",
            "done_when",
            *SEVERITIES,
        ),
        _review_rounds,
    ),
    Source(
        "drift",
        "drift.jsonl",
        "log",
        _columns("at", "probe", "word", "status", "found", "sha", "error"),
        _drift,
        where="machine",
    ),
    Source(
        "capped_reads",
        "capped.jsonl",
        "log",
        _columns("at", "reader", "instances", "capped", "ends_at"),
        _capped_reads,
        where="machine",
    ),
    Source("merge_waits", "merge-waits.jsonl", "log", _WAITS, _merge_waits, where="home"),
)
"""Each source by its table. A source added here has its table made by a migration of its own
(`jbus.telemetry.migrations`), never by the first."""
