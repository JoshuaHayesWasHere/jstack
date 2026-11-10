"""Claude spend from T3 Code's store, and the time every Claude instance was capped.

The store is `~/.t3/userdata/statev2.sqlite`, opened read-only. A run is one turn of a thread;
its tokens are the sum of its provider turns' `turnTokenUsage`. Spend is in units, the day
audit's proxy (reports/day-audit-1026/premises.md): each token at its kind's rate (`PLAIN`,
`WRITTEN`, `CACHED`, `OUTPUT`), and an Opus run times `OPUS`. A run counts whole in the period,
and in the five-hour window, in which it started.

A cap is a run's usage-limit failure: the instance is capped from the failure to its `resetAt`.
Every instance is capped while each Claude instance that ran in the week before the period's end
is capped: then no account is left.

The SQL keywords are upper case, since a line that starts with a lower-case `from` reads to
jbus's test of what the source imports as an import.
"""

from __future__ import annotations

import bisect
import contextlib
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import unquote

import jsettings

STORE = Path.home() / ".t3" / "userdata" / "statev2.sqlite"
FIVE_HOURS = timedelta(hours=5)
PLAIN, WRITTEN, CACHED, OUTPUT = 1, 1.25, 0.1, 5
"""Units per token: uncached input, cache write, cache read and output. `units` weighs a run by
these, and `jbus.telemetry.schema.UNITS` weighs a call by them, so the two never part."""
OPUS = 5 / 3
"""The weight on a run whose model's name holds `OPUS_NAME`, case and all."""
OPUS_NAME = "opus"


@dataclass(frozen=True)
class Price:
    """A model's list price in dollars per million tokens: uncached input, cache write, cache
    read and output, the four classes the rates above weigh."""

    plain: float
    written: float
    cached: float
    output: float


PRICED_ON = date(2026, 10, 6)
"""The date of the price list `PRICES` is copied from: the claude-api skill's model table,
cached 2026-10-06, read on 2026-11-03. The Fable row and Sonnet's cache read alone were read
later, from the page the `PRICES` docstring names."""
PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(4, 8, 0.20, 20),
    "claude-sonnet-5-5": Price(2, 4, 0.10, 10),
    "claude-haiku-5-5": Price(0.10, 0.20, 0.01, 0.50),
    "claude-fable-5-2": Price(8, 16, 0.20, 40),
}
"""Each priced model's list price, by its exact id, the one place a price is named. A cache write
is priced at the one-hour cache's 2x input, not the five-minute 1.25x: the store keeps one count
of written tokens, and of the cache writes in 200 Claude Code transcripts read on 2026-11-03,
98.9% were to the one-hour cache. Haiku's higher price for a prompt over 100K tokens is not
counted. A model not here, every Codex model among them, is unpriced: its calls have no dollars.
What a subscription bills is not per token, so a sum of these is an estimate at API list prices.
Fable 5.2's row is from Anthropic's pricing page,
https://platform.claude.com/docs/en/about-claude/pricing, read on 2026-11-09: $8 input, $16 for
a one-hour cache write, $0.20 for a cache hit and $40 output per million tokens. Sonnet 5.5's
cache read is from the same page, read on 2026-11-09: $0.10 per million tokens, 0.05x its $2
input."""


def dollars(model: str, plain: int, written: int, cached: int, output: int) -> float | None:
    """A call's dollars at `PRICES`, from its uncached input, cache write, cache read and output
    tokens, or None for a model the table does not price."""
    price = PRICES.get(model)
    if price is None:
        return None
    spent = (
        plain * price.plain
        + written * price.written
        + cached * price.cached
        + output * price.output
    )
    return spent / 1e6


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
    **dict.fromkeys("failed refailed rereview unreviewed unfixed remark".split(), FIXES),
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
    project_id: str = ""


@dataclass(frozen=True)
class Cap:
    """A usage-limit failure: its `limit` is five_hour, seven_day, or "" where the store does not
    say. It `ends` at its reset, or at the start of the next run its instance completed after it,
    whichever is first."""

    instance: str
    at: datetime
    reset: datetime
    limit: str
    ends: datetime


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
    spent = plain * PLAIN + t.written * WRITTEN + t.cached * CACHED + t.output * OUTPUT
    return spent * (OPUS if OPUS_NAME in run.model else 1)


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
    of [failure, end)."""
    if not instances:
        return []
    every: list[tuple[datetime, datetime]] | None = None
    for instance in sorted(instances):
        own = _union([(c.at, c.ends) for c in caps if c.instance == instance and c.ends > c.at])
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


COLUMNS = dict(
    zip(KINDS, ("first", "reviews", "fixes", "sends", "homes", "scouts", "capped"), strict=True)
)
"""The name of each kind's units in a day's spend line."""
THREADS = {"crew: ": "crew", "review: ": "review", "home: ": "home", "scout: ": "scout"}
"""The role of a thread by the start of its title, which jbus gives it, then the row's slug."""


def _sums(runs: list[Run]) -> dict[str, float | int]:
    return {
        "units": round(sum(units(run) for run in runs)),
        "runs": len(runs),
        "input": sum(run.tokens.input for run in runs),
        "cached": sum(run.tokens.cached for run in runs),
        "written": sum(run.tokens.written for run in runs),
        "output": sum(run.tokens.output for run in runs),
    }


def role(title: str) -> tuple[str, str]:
    """The role and the slug a thread's title names, or `other` and no slug for a title jbus did
    not give: such a title is the user's, so none of it is kept."""
    for prefix, name in THREADS.items():
        if title.startswith(prefix):
            return name, title[len(prefix) :].strip()
    return "other", ""


def day_lines(runs: list[Run], day: str) -> tuple[dict, list[dict]]:
    """A day's spend of `runs`, the runs that started on it: one line of its totals and its units
    by kind, and one line for each role and slug. No line holds a title or a message, only the
    slug of a thread jbus named."""
    by_kind: dict[str, float] = defaultdict(float)
    for run in runs:
        by_kind[kind(run)] += units(run)
    total = {"day": day, **_sums(runs), **{COLUMNS[k]: round(by_kind[k]) for k in KINDS}}
    groups: dict[tuple[str, str], list[Run]] = defaultdict(list)
    for run in runs:
        groups[role(run.title)].append(run)
    rows = [
        {"day": day, "role": name, "slug": slug, **_sums(grouped)}
        for (name, slug), grouped in sorted(groups.items())
    ]
    return total, rows


def _at(stamp: str) -> datetime:
    return jsettings.when(stamp)


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


USAGE = """u AS (
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
)"""
"""Each run of `r`'s tokens, summed over its attempts' provider turns, and whether any turn's
usage is only partial: one definition of a run's tokens, for `RUNS` and `REVIEWS` both."""

RUNS = f"""
WITH r AS (
    SELECT run_id, thread_id, ordinal, status, provider_instance_id, requested_at, payload_json
    FROM orchestration_v2_projection_runs
    WHERE requested_at < :until AND (completed_at IS NULL OR completed_at >= :since)
        AND json_extract(payload_json, '$.modelSelection.model') LIKE 'claude%'
), {USAGE}
SELECT r.run_id, r.provider_instance_id, json_extract(r.payload_json, '$.modelSelection.model'),
    t.title, coalesce(pr.title, ''), t.project_id, r.ordinal, r.status,
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

COMPLETED = """
SELECT provider_instance_id, coalesce(json_extract(payload_json, '$.startedAt'), requested_at)
FROM orchestration_v2_projection_runs WHERE status = 'completed'
"""

INSTANCES = """
SELECT DISTINCT provider_instance_id FROM orchestration_v2_projection_runs
WHERE requested_at >= :week AND requested_at < :until
    AND json_extract(payload_json, '$.modelSelection.model') LIKE 'claude%'
"""


def caps(store: Path, until: datetime) -> tuple[list[Cap], set[str]]:
    """Every usage-limit cap, each ended by its instance's next completed run, and the Claude
    instances that ran in the week before `until`."""
    if not store.is_file():
        raise Refused(f"{store} is not T3 Code's store")
    week = {"week": _stamp(until - timedelta(days=7)), "until": _stamp(until)}
    try:
        with contextlib.closing(sqlite3.connect(f"file:{store}?mode=ro", uri=True)) as db:
            capped = db.execute(CAPS).fetchall()
            completed = db.execute(COMPLETED).fetchall()
            instances = {name for (name,) in db.execute(INSTANCES, week)}
    except sqlite3.Error as error:
        raise Refused(f"{store} cannot be read: {error}") from None
    starts: dict[str, list[datetime]] = defaultdict(list)
    for instance, start in completed:
        starts[instance].append(_at(start))
    for own in starts.values():
        own.sort()
    found = []
    for instance, at, reset, native in capped:
        failed, resets = _at(at), _at(reset)
        own = starts[instance]
        later = bisect.bisect_right(own, failed)
        ends = min(resets, own[later]) if later < len(own) else resets
        found.append(Cap(instance, failed, resets, native.split(":")[-2] if native else "", ends))
    return found, instances


def read(
    store: Path, since: datetime, until: datetime, project: str | None
) -> tuple[list[Run], list[Cap], set[str]]:
    """Every Claude run that ran in [since - 5 h, until + 5 h), so that a five-hour window
    across either end of the period is whole; and `caps` until `until`."""
    if not store.is_file():
        raise Refused(f"{store} is not T3 Code's store")
    edges = {"since": _stamp(since - FIVE_HOURS), "until": _stamp(until + FIVE_HOURS)}
    try:
        with contextlib.closing(sqlite3.connect(f"file:{store}?mode=ro", uri=True)) as db:
            projects = {name for (name,) in db.execute("SELECT title FROM projection_projects")}
            found = db.execute(RUNS, edges).fetchall()
    except sqlite3.Error as error:
        raise Refused(f"{store} cannot be read: {error}") from None
    capped, instances = caps(store, until)
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
            project_id=project_id,
        )
        for (
            run_id,
            instance,
            model,
            title,
            in_project,
            project_id,
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
    return runs, capped, instances


REVIEW = "review: "
"""The start of a review thread's title, which jbus gives it: `review: <slug>, <round>`."""

REVIEWS = f"""
WITH r AS (
    SELECT r.run_id, r.thread_id, r.requested_at, r.completed_at, r.payload_json
    FROM orchestration_v2_projection_runs r
    JOIN orchestration_v2_projection_threads t ON t.thread_id = r.thread_id
    WHERE t.project_id = :project AND substr(t.title, 1, {len(REVIEW)}) = '{REVIEW}'
        AND r.requested_at >= :since AND r.requested_at < :until
), {USAGE}
SELECT r.thread_id, t.title,
    coalesce(json_extract(r.payload_json, '$.startedAt'), r.requested_at), r.completed_at,
    coalesce(u.input, 0), coalesce(u.cached, 0), coalesce(u.written, 0), coalesce(u.output, 0)
FROM r
JOIN orchestration_v2_projection_threads t ON t.thread_id = r.thread_id
LEFT JOIN u ON u.run_id = r.run_id
"""


@dataclass(frozen=True)
class Launch:
    """One launch of the reviewer: a thread jbus titled `review: <slug>, <round>`, of any model,
    a failed launch among them. Its `start` is its first run's, its `active` the seconds its runs
    ran, each from its start to its completion, so a wait between two turns is not in it, and a
    run not completed adds nothing. Its `tokens` are its runs' summed."""

    thread: str
    slug: str
    start: datetime
    active: float
    tokens: Tokens
    runs: int


def reviews(store: Path, project_id: str, since: datetime, until: datetime) -> list[Launch]:
    """Each review launch of the T3 Code project `project_id` with a run requested in
    [since, until), oldest first. A launch counts the runs in that span only."""
    if not store.is_file():
        raise Refused(f"{store} is not T3 Code's store")
    edges = {"project": project_id, "since": _stamp(since), "until": _stamp(until)}
    try:
        with contextlib.closing(sqlite3.connect(f"file:{store}?mode=ro", uri=True)) as db:
            found = db.execute(REVIEWS, edges).fetchall()
    except sqlite3.Error as error:
        raise Refused(f"{store} cannot be read: {error}") from None
    threads: dict[str, list[tuple]] = defaultdict(list)
    for row in found:
        threads[row[0]].append(row)
    launches = []
    for thread, rows in threads.items():
        title = rows[0][1]
        starts = [_at(start) for _, _, start, *_ in rows]
        active = sum(
            (_at(done) - _at(start)).total_seconds() for _, _, start, done, *_ in rows if done
        )
        sums = [sum(int(row[i]) for row in rows) for i in range(4, 8)]
        launches.append(
            Launch(
                thread=thread,
                slug=title[len(REVIEW) :].split(",")[0].strip(),
                start=min(starts),
                active=active,
                tokens=Tokens(*sums),
                runs=len(rows),
            )
        )
    return sorted(launches, key=lambda one: one.start)
