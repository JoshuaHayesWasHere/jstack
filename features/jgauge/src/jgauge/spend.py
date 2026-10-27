"""Claude spend from T3 Code's store, and the time every Claude instance was capped.

The store is `~/.t3/userdata/statev2.sqlite`, opened read-only. A run is one turn of a thread;
its tokens are the sum of its provider turns' `turnTokenUsage`. Spend is in units, the day
audit's proxy (reports/day-audit-1026/premises.md): uncached input x1, cache write x1.25, cache
read x0.1, output x5, and an Opus run x5/3. A run counts whole in the period, and in the
five-hour window, in which it started.

A cap is a run's usage-limit failure: the instance is capped from the failure to its `resetAt`.
Every instance is capped while each Claude instance that ran in the week before the period's end
is capped: then no account is left.

The SQL keywords are upper case, since a line that starts with a lower-case `from` reads to
jbus's test of what the source imports as an import.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import unquote

STORE = Path.home() / ".t3" / "userdata" / "statev2.sqlite"
FIVE_HOURS = timedelta(hours=5)
OPUS = 5 / 3

FIRST, REVIEWS, FIXES, SENDS, HOMES, SCOUTS, CAPPED = KINDS = (
    "first crew run",
    "reviews",
    "fix rounds",
    "jbus sends",
    "homes",
    "scouts",
    "capped failures",
)

TRIGGERS = {
    **dict.fromkeys(
        "failed refailed integration-red rereview unreviewed unfixed remark".split(), FIXES
    ),
    **dict.fromkeys(
        (
            "restack rebase mainmoved conflict drops limit-resume failover slot-wake wake"
            " hold-stall home-stall clock twice word unpushed unruled"
        ).split(),
        SENDS,
    ),
}
ROLES = {"home:": HOMES, "scout:": SCOUTS, "review:": REVIEWS}


class Refused(Exception):
    """The store cannot be read, or the project is not in it."""


@dataclass(frozen=True)
class Tokens:
    """A run's tokens: `input` is every input token, the cached and the written included."""

    input: int
    cached: int
    written: int
    output: int


@dataclass(frozen=True)
class Run:
    """One turn of a thread. It is `capped` when it failed on a usage limit, or failed with only
    partial usage."""

    id: str
    instance: str
    model: str
    title: str
    ordinal: int
    start: datetime
    tokens: Tokens
    trigger: str
    text: str
    capped: bool


@dataclass(frozen=True)
class Cap:
    """A usage-limit failure: its `limit` is five_hour, seven_day, or "" where the store does not
    say."""

    instance: str
    at: datetime
    reset: datetime
    limit: str


@dataclass(frozen=True)
class Window:
    """A five-hour window. It is `from_reset` when its end is a five-hour reset the store gives,
    not one counted from a run."""

    instance: str
    start: datetime
    end: datetime
    from_reset: bool


def units(run: Run) -> float:
    t = run.tokens
    plain = t.input - t.cached - t.written
    spent = plain + t.written * 1.25 + t.cached * 0.1 + t.output * 5
    return spent * (OPUS if "opus" in run.model else 1)


def kind(run: Run) -> str:
    if run.capped:
        return CAPPED
    for prefix, role in ROLES.items():
        if run.title.startswith(prefix):
            return role
    if run.ordinal == 1:
        return FIRST
    if run.trigger in TRIGGERS:
        return TRIGGERS[run.trigger]
    resumed = "Continue where you left off" in run.text or run.text.startswith("/compact")
    return FIXES if not resumed and re.search(r"review|scoped pass", run.text) else SENDS


def trigger(message_id: str) -> str:
    """The key jbus put in the message id it sent a run with (`thread-send:<key>|<slug>|...`);
    TRIGGERS gives its kind, and a key not there is judged by the message's text."""
    said = unquote(unquote(message_id))
    return said.split("thread-send:", 1)[1].split("|")[0] if "thread-send:" in said else ""


def windows(runs: list[Run], caps: list[Cap]) -> list[Window]:
    """Each instance's five-hour windows: one ending at each five-hour reset a cap names, and
    between those, one starting at the first run outside any window."""
    out: list[Window] = []
    for instance in sorted({run.instance for run in runs} | {cap.instance for cap in caps}):
        resets = sorted(
            {c.reset for c in caps if c.instance == instance and c.limit == "five_hour"}
        )
        known = [Window(instance, reset - FIVE_HOURS, reset, True) for reset in resets]
        found: list[Window] = []
        for run in sorted((r for r in runs if r.instance == instance), key=lambda r: r.start):
            if any(w.start <= run.start < w.end for w in known + found):
                continue
            later = [w.start for w in known if w.start > run.start]
            end = min([run.start + FIVE_HOURS, *later])
            found.append(Window(instance, run.start, end, False))
        out += sorted(known + found, key=lambda w: w.start)
    return out


def capped_spans(caps: list[Cap], instances: set[str]) -> list[tuple[datetime, datetime]]:
    """The spans in which every instance was capped: the intersection of each instance's union
    of [failure, reset)."""
    if not instances:
        return []
    every: list[tuple[datetime, datetime]] | None = None
    for instance in sorted(instances):
        own = _union([(c.at, c.reset) for c in caps if c.instance == instance and c.reset > c.at])
        every = own if every is None else _intersect(every, own)
    return every or []


def _union(spans: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _intersect(a, b) -> list[tuple[datetime, datetime]]:
    return [(max(s1, s2), min(e1, e2)) for s1, e1 in a for s2, e2 in b if max(s1, s2) < min(e1, e2)]


def _days(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """The local days that [start, end) touches, each clipped to it."""
    out = []
    day = start.astimezone().date()
    while (begin := _midnight(day)) < end:
        out.append((max(begin, start), min(_midnight(day + timedelta(days=1)), end)))
        day += timedelta(days=1)
    return out


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time()).astimezone()


def _clock(at: datetime) -> str:
    return (at + timedelta(seconds=30)).astimezone().strftime("%H:%M")


def _m(spent: float) -> str:
    return f"{spent / 1e6:.1f}M"


def report(
    runs: list[Run],
    caps: list[Cap],
    instances: set[str],
    since: datetime,
    until: datetime,
) -> list[str]:
    """The report's lines: spend in [since, until) by kind, by instance and by five-hour window,
    then each day's minutes with every instance capped."""
    inside = [run for run in runs if since <= run.start < until]
    by_kind: dict[str, float] = defaultdict(float)
    by_instance: dict[str, float] = defaultdict(float)
    for run in inside:
        by_kind[kind(run)] += units(run)
        by_instance[run.instance] += units(run)
    total = sum(by_kind.values())
    zone = since.astimezone().strftime("%Z")
    out = [
        f"spend {since.astimezone():%Y-%m-%d %H:%M} to {until.astimezone():%Y-%m-%d %H:%M}"
        f" {zone}: {_m(total)} units, {len(inside)} runs",
        "by kind:",
        *(f"  {k:16} {_m(by_kind[k]):>8} {by_kind[k] / (total or 1):6.1%}" for k in KINDS),
        "by instance:",
        *(f"  {i:26} {_m(by_instance[i]):>8}" for i in sorted(by_instance)),
        "by five-hour window:",
    ]
    for w in windows(runs, caps):
        if w.end <= since or w.start >= until:
            continue
        spent = sum(
            units(r) for r in runs if r.instance == w.instance and w.start <= r.start < w.end
        )
        hit = [c.at for c in caps if c.instance == w.instance and w.start <= c.at < w.end]
        note = f", capped at {_clock(min(hit))}" if hit else ""
        source = "reset" if w.from_reset else "first run"
        out.append(
            f"  {w.instance:26} {w.start.astimezone():%Y-%m-%d %H:%M} to {_clock(w.end)}"
            f" ({source}) {_m(spent):>8}{note}"
        )
    out.append(f"every instance capped ({', '.join(sorted(instances)) or 'none'}):")
    spans = capped_spans(caps, instances)
    for begin, end in _days(since, until):
        today = [(max(s, begin), min(e, end)) for s, e in spans if max(s, begin) < min(e, end)]
        minutes = round(sum((e - s).total_seconds() for s, e in today) / 60)
        shown = ", ".join(f"{_clock(s)} to {_clock(e)}" for s, e in today)
        line = f"  {begin.astimezone():%Y-%m-%d} {minutes:4} min"
        out.append(f"{line}  {shown}" if shown else line)
    return out


def _at(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


RUNS = """
WITH r AS (
    SELECT run_id, thread_id, ordinal, status, provider_instance_id, requested_at, payload_json
    FROM orchestration_v2_projection_runs
    WHERE requested_at < :until AND (completed_at IS NULL OR completed_at >= :since)
        AND json_extract(payload_json, '$.modelSelection.model') LIKE 'claude%'
), u AS (
    SELECT a.run_id,
        sum(json_extract(p.payload_json, '$.turnTokenUsage.inputTokens')) input,
        sum(json_extract(p.payload_json, '$.turnTokenUsage.cachedInputTokens')) cached,
        sum(json_extract(p.payload_json, '$.turnTokenUsage.cacheCreationTokens')) written,
        sum(json_extract(p.payload_json, '$.turnTokenUsage.outputTokens')) output,
        min(json_extract(p.payload_json, '$.turnTokenUsage.usageStatus') = 'partial') partial
    FROM orchestration_v2_projection_run_attempts a
    JOIN orchestration_v2_projection_provider_turns p ON p.run_attempt_id = a.attempt_id
    WHERE a.run_id IN (SELECT run_id FROM r)
    GROUP BY a.run_id
)
SELECT r.run_id, r.provider_instance_id, json_extract(r.payload_json, '$.modelSelection.model'),
    t.title, coalesce(pr.title, ''), r.ordinal, r.status,
    coalesce(json_extract(r.payload_json, '$.startedAt'), r.requested_at),
    coalesce(u.input, 0), coalesce(u.cached, 0), coalesce(u.written, 0), coalesce(u.output, 0),
    coalesce(u.partial, 0),
    coalesce(json_extract(r.payload_json, '$.userMessageId'), ''),
    coalesce((
        SELECT json_extract(i.payload_json, '$.text') FROM orchestration_v2_projection_turn_items i
        WHERE i.thread_id = r.thread_id AND i.run_id = r.run_id AND i.type = 'user_message'
            AND json_extract(i.payload_json, '$.messageId')
                = json_extract(r.payload_json, '$.userMessageId')
    ), ''),
    EXISTS (
        SELECT 1 FROM orchestration_v2_projection_turn_items i
        WHERE i.thread_id = r.thread_id AND i.run_id = r.run_id AND i.type = 'error'
            AND json_extract(i.payload_json, '$.failure.class') = 'usage_limit'
    )
FROM r
JOIN orchestration_v2_projection_threads t ON t.thread_id = r.thread_id
LEFT JOIN projection_projects pr ON pr.project_id = t.project_id
LEFT JOIN u ON u.run_id = r.run_id
"""

CAPS = """
SELECT r.provider_instance_id, json_extract(i.payload_json, '$.startedAt'),
    json_extract(i.payload_json, '$.failure.resetAt'),
    coalesce((
        SELECT json_extract(n.payload_json, '$.nativeItemRef.nativeId')
        FROM orchestration_v2_projection_turn_items n
        WHERE n.thread_id = i.thread_id AND n.run_id = i.run_id AND n.type = 'system_notice'
            AND json_extract(n.payload_json, '$.nativeItemRef.nativeId') LIKE 'usage-limit:%'
        LIMIT 1
    ), '')
FROM orchestration_v2_projection_turn_items i
JOIN orchestration_v2_projection_runs r ON r.run_id = i.run_id
WHERE i.type = 'error' AND i.status = 'failed'
    AND json_extract(i.payload_json, '$.failure.class') = 'usage_limit'
    AND json_extract(i.payload_json, '$.failure.resetAt') IS NOT NULL
"""

INSTANCES = """
SELECT DISTINCT provider_instance_id FROM orchestration_v2_projection_runs
WHERE requested_at >= :week AND requested_at < :until
    AND json_extract(payload_json, '$.modelSelection.model') LIKE 'claude%'
"""


def read(
    store: Path, since: datetime, until: datetime, project: str | None
) -> tuple[list[Run], list[Cap], set[str]]:
    """Every Claude run that ran in [since - 5 h, until + 5 h), so that a five-hour window
    across either end of the period is whole; every usage-limit cap; and the Claude instances
    of the week."""
    if not store.is_file():
        raise Refused(f"{store} is not T3 Code's store")
    edges = {"since": _stamp(since - FIVE_HOURS), "until": _stamp(until + FIVE_HOURS)}
    week = {"week": _stamp(until - timedelta(days=7)), "until": _stamp(until)}
    try:
        with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as db:
            projects = {name for (name,) in db.execute("SELECT title FROM projection_projects")}
            found = db.execute(RUNS, edges).fetchall()
            capped = db.execute(CAPS).fetchall()
            instances = {name for (name,) in db.execute(INSTANCES, week)}
    except sqlite3.Error as error:
        raise Refused(f"{store} cannot be read: {error}") from None
    if project is not None and project not in projects:
        raise Refused(f"no project {project!r} in {store}: it has {', '.join(sorted(projects))}")
    runs = [
        Run(
            id=run_id,
            instance=instance,
            model=model,
            title=title,
            ordinal=ordinal,
            start=_at(start),
            tokens=Tokens(int(input_), int(cached), int(written), int(output)),
            trigger=trigger(message),
            text=text,
            capped=bool(limited) or (status == "failed" and bool(partial)),
        )
        for (
            run_id,
            instance,
            model,
            title,
            in_project,
            ordinal,
            status,
            start,
            input_,
            cached,
            written,
            output,
            partial,
            message,
            text,
            limited,
        ) in found
        if project is None or in_project == project
    ]
    caps = [
        Cap(instance, _at(at), _at(reset), native.split(":")[-2] if native else "")
        for instance, at, reset, native in capped
    ]
    return runs, caps, instances
