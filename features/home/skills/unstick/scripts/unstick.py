# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Why each stalled row of jbus's queue has not moved, from jbus's own records, read-only.

A row is open while its queue status is not merged or done. Its stage is that status, and its
age is the time since the last transition into it (`transitions.jsonl`), or, for a row that has
had none since it was added, since its queue `since` or `updated` stamp. A row is stalled when
its age is past the 90th percentile of that stage's past spans in its project, or past `FLOOR`
where the project has fewer than `SAMPLES` spans of the stage.

The cause is read, not guessed: the pass already judged each row (`work.json`, one `value` of
`jbus.work.VALUES`), and two causes the pass does not judge come from beside it. A crew's thread
that is in the test-slot waiters waits on a slot. A `stall` or `failover` event since the row
entered its stage that says its provider is capped, or its limit lasts, until a time still to
come, waits on the usage limit.

Each line ends in what to do, one of `KINDS`:

- `act`: a reversible step this thread takes now, a message to the thread it names;
- `wait`: something that moves by itself, and when;
- `user`: a question jbus already holds for the user, so nothing more is raised;
- `gate`: a call no record settles, which the thread parks with `jbus gate`.

    unstick.py [--project <name>]... [--now <iso time>] [--all] [--json]

`JBUS_STATE_DIR` and `JGAUGE_LOCKS_DIR` name jbus's state and the slots' lock files, as jbus
and jgauge read them.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

FINAL = ("merged", "done")
SAMPLES = 5
FLOOR = timedelta(minutes=60)
TOLD_LATELY = timedelta(minutes=30)
KINDS = ("act", "wait", "user", "gate")
ZONES = {"EDT": timezone(timedelta(hours=-4)), "EST": timezone(timedelta(hours=-5))}
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (EDT|EST)")
CAPPED = re.compile(r"(?:capped|limit) until (\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2}))")
TELLS = ("expedite", "failed", "stall", "stale", "rebase", "leftover")
HELD = "jbus holds this for the user: name it, raise nothing more"
MOVING = "it is moving: look again after the next pass"
UNKNOWN = "look at {slug} by hand: no record names why it waits"
ACTIONS = {
    "check": (
        "act",
        'tell {thread}: a check of {pr} failed, run "The checks" and do what it prints',
    ),
    "rebase": (
        "act",
        'tell {thread}: {pr} is in conflict with its base, do what "A conflict" says',
    ),
    "review": (
        "act",
        'tell {thread}: {pr} has no review yet, launch or wake its reviewer as "The review" says',
    ),
    "second": (
        "act",
        'tell {thread}: {pr} has no second review yet, launch or wake it as "A second pass" says',
    ),
    "findings": ("act", 'tell {thread}: the findings on {pr} are not handled, see "The review"'),
    "result": ("act", 'tell {thread}: write the Result in the brief, as "End" says'),
    "quiet": ("act", "send {thread}: Continue where you left off."),
    "hung": ("act", "send {thread}: Continue where you left off."),
    "lost": ("gate", "start {slug} again in a new thread, from its brief and branch as they are"),
    "behind": ("wait", "it launches once those merge: unstick them first"),
    "waiting": ("user", HELD),
    "unapproved": ("user", HELD),
    "hold": ("user", HELD),
    "leftover": ("user", HELD),
    "closed": ("user", HELD),
    "ready": ("wait", MOVING),
    "launching": ("wait", MOVING),
    "working": ("wait", MOVING),
}
NUDGED = frozenset(value for value, (kind, _) in ACTIONS.items() if kind == "act")

CAUSES = {
    "asking": "gate",
    "review": "review",
    "second": "review",
    "findings": "review",
    "check": "checks",
    "rebase": "checks",
    "hung": "dead-thread",
    "quiet": "dead-thread",
    "lost": "dead-thread",
    "waiting": "thread-asks",
    "behind": "depends",
    "unapproved": "approval",
    "hold": "held",
    "leftover": "leftover",
    "closed": "closed",
    "result": "result",
    "launching": "launching",
    "working": "working",
    "ready": "next-pass",
}


@dataclass(frozen=True)
class Stalled:
    project: str
    slug: str
    stage: str
    age_minutes: int
    p90_minutes: int
    cause: str
    evidence: str
    kind: str
    action: str
    thread: str


def when(text):
    if not text:
        return None
    local = STAMP.fullmatch(str(text))
    if local:
        return datetime.strptime(local[1], "%Y-%m-%d %H:%M").replace(tzinfo=ZONES[local[2]])
    try:
        found = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


def read(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def lines(path):
    try:
        with path.open() as file:
            for line in file:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return


def minutes(span):
    return int(span.total_seconds() // 60)


def age(span):
    hours, left = divmod(minutes(span), 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d{hours:02d}h"
    return f"{hours}h{left:02d}m" if hours else f"{left}m"


def thread_id(text):
    text = str(text or "")
    return text if not text or text.startswith("mcp:") else f"mcp:{text}"


def p90(spans):
    """The 90th percentile by nearest rank, or None under `SAMPLES` spans."""
    if len(spans) < SAMPLES:
        return None
    ordered = sorted(spans)
    return ordered[max(0, -(-9 * len(ordered) // 10) - 1)]


def stages(transitions):
    """Each slug's transitions in order, and each stage's past spans: from entering a status to
    the next transition of the same slug."""
    by_slug, spans = {}, {}
    for one in transitions:
        at = when(one.get("at"))
        if at and one.get("slug") and one.get("to"):
            by_slug.setdefault(one["slug"], []).append((at, one["to"]))
    for moves in by_slug.values():
        moves.sort()
        for (at, to), (after, _) in zip(moves, moves[1:], strict=False):
            spans.setdefault(to, []).append(after - at)
    return by_slug, spans


def entered(moves, status):
    """When the row last entered `status`, or None when no transition says so."""
    for at, to in reversed(moves or []):
        if to == status:
            return at
    return None


def open_question(questions, slug):
    """The row's last question with no answer yet. One closed by silence took its default and
    holds nothing up, though the user may still answer it."""
    for one in reversed(questions.get("records") or []):
        if one.get("slug") == slug and one.get("answer") is None:
            return one
    return None


def capped(events, since, now):
    """The last time a capped provider or a usage limit lifts, from an event since `since`, if
    it is still to come."""
    lifts = None
    for one in events:
        at = when(one.get("at"))
        if one.get("event") in ("stall", "failover") and at and at >= since:
            found = CAPPED.search(one.get("line") or "")
            until = when(found[1]) if found else None
            if until and until > now:
                lifts = until
    return lifts


def told(events, since):
    last = None
    for one in events:
        at = when(one.get("at"))
        if one.get("event") in TELLS and at and at >= since:
            last = (at, one.get("line") or "")
    return last


def diagnose(project, row, work, events, question, waiter, since, now):
    """The cause of one stalled row and what to do, as (cause, evidence, kind, action)."""
    slug, thread = row["slug"], row.get("thread") or ""
    value = (work or {}).get("value", "unknown")
    if question or value == "asking" or row.get("status") == "gate":
        if question:
            number = question.get("number")
            return (
                "gate",
                f"question {number}: {question.get('question', '')}",
                "user",
                f"answer it: jbus --project {project} answer {number}",
            )
        gated = "the row's status is gate and no question is open"
        return ("gate", gated, "gate", UNKNOWN.format(slug=slug))
    lifts = capped(events, since, now)
    if lifts:
        return (
            "usage-limit",
            f"capped until {lifts.isoformat()}",
            "wait",
            f"it moves once the limit lifts, {age(lifts - now)} from now",
        )
    if waiter:
        return (
            "slot",
            f"its thread waits on a {waiter.get('lane', '')} test slot since {waiter.get('since')}",
            "wait",
            "jbus wakes the thread when a slot of its lane is free",
        )
    cause = CAUSES.get(value, "unknown")
    said = (work or {}).get("waits") or ""
    evidence = f"jbus judged it {value}, waiting on {said}" if said else f"jbus judged it {value}"
    last = told(events, since)
    pr, checks = row.get("pr") or "", row.get("checks") or "running"
    if value == "check" and checks != "failed":
        return (cause, f"{evidence}, {pr} checks {checks}", "wait", "the check runner moves it")
    if value in NUDGED and last and now - last[0] < TOLD_LATELY:
        fresh = f"{evidence}; jbus told it {age(now - last[0])} ago: {last[1][:160]}"
        return (cause, fresh, "wait", "jbus's own word is fresh: let it work")
    if value == "behind":
        evidence += f": {', '.join(row.get('depends') or []) or 'a row in front of it'}"
    if value not in ACTIONS:
        seen = last[1][:160] if last else "none"
        return ("unknown", f"{evidence}; last event: {seen}", "gate", UNKNOWN.format(slug=slug))
    kind, action = ACTIONS[value]
    return (cause, evidence, kind, action.format(thread=thread, slug=slug, pr=pr))


def project_rows(state, project, now, every, waiters):
    folder = state / project
    queue = read(folder / "queue.json", [])
    if not isinstance(queue, list):
        return [], 0
    judged = {
        one.get("slug"): one
        for one in (read(folder / "work.json", {}).get("work") or [])
        if one.get("kind") == "row"
    }
    questions = read(folder / "questions.json", {})
    by_slug, spans = stages(lines(folder / "transitions.jsonl"))
    rows = [row for row in queue if row.get("slug") and row.get("status") not in FINAL]
    events = {row["slug"]: [] for row in rows}
    for one in lines(folder / "events.jsonl"):
        if one.get("slug") in events:
            events[one["slug"]].append(one)
    found = []
    for row in rows:
        status = row.get("status") or "queued"
        since = entered(by_slug.get(row["slug"]), status) or when(row.get("since"))
        since = since or when(row.get("updated"))
        if since is None:
            continue
        limit = p90(spans.get(status, [])) or FLOOR
        if now - since <= limit and not every:
            continue
        waiter = waiters.get(thread_id(row.get("thread")))
        cause, evidence, kind, action = diagnose(
            project,
            row,
            judged.get(row["slug"]),
            events.get(row["slug"], []),
            open_question(questions, row["slug"]),
            waiter,
            since,
            now,
        )
        found.append(
            Stalled(
                project,
                row["slug"],
                status,
                minutes(now - since),
                minutes(limit),
                cause,
                evidence,
                kind,
                action,
                row.get("thread") or "",
            )
        )
    return found, len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", action="append", default=[])
    parser.add_argument("--now", help="the time to measure ages at, ISO (default: now)")
    parser.add_argument("--all", action="store_true", help="every open row, stalled or not")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    state = Path(os.environ.get("JBUS_STATE_DIR") or Path.home() / ".local/state/jbus")
    locks = Path(os.environ.get("JGAUGE_LOCKS_DIR") or Path.home() / ".local/state/locks")
    now = when(args.now) if args.now else datetime.now(UTC)
    if now is None:
        sys.exit(f"unstick: --now {args.now} is not an ISO time")
    if not state.is_dir():
        sys.exit(f"unstick: no jbus state at {state}")
    waiting = read(locks / "test-slot-waiters.json", [])
    waiters = {
        thread_id(one.get("thread")): one
        for one in waiting
        if isinstance(one, dict) and not one.get("woken")
    }
    projects = args.project or sorted(
        p.name for p in state.iterdir() if (p / "queue.json").is_file()
    )
    found, total = [], 0
    for project in projects:
        rows, count = project_rows(state, project, now, args.all, waiters)
        found += rows
        total += count
    found.sort(key=lambda one: -one.age_minutes)
    if args.json:
        print(json.dumps([asdict(one) for one in found], indent=1))
        return
    if not found:
        print(f"nothing is stalled: {total} open rows, each inside its stage's p90")
        return
    stalled = sum(one.age_minutes > one.p90_minutes for one in found)
    print(f"stalled: {stalled} of {total} open rows, oldest first")
    for one in found:
        took, limit = (
            age(timedelta(minutes=one.age_minutes)),
            age(timedelta(minutes=one.p90_minutes)),
        )
        print(
            f"{one.project} {one.slug}: {one.stage} {took} (p90 {limit}),",
            f"{one.cause}: {one.evidence}",
        )
        print(f"  {one.kind}: {one.action}")


if __name__ == "__main__":
    main()
