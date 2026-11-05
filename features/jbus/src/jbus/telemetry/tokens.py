"""The token usage of every Claude and Codex call, copied into the store, by its thread.

Claude Code deletes a transcript whose last write is older than its `cleanupPeriodDays` setting,
30 days unless its settings say otherwise, and with it the only record of each call's usage.
Each build copies the usage of the calls written since the last one, so the store has each call
long before its transcript is gone, and keeps it forever. It keeps ids, times, the model and four
counts per call, and no text of a message.

- `sessions` is T3 Code's map of a provider's native session to its thread: one row for each
  provider thread T3's store has (`orchestration_v2_projection_provider_threads`), so a thread
  resumed on a new session has each. A row gives the thread's project, as jbus names it where
  the T3 project is one of jbus's, and the role and slug its title gives (`roles.role_of`). A
  build updates the rows T3 has and drops none.
- `calls` is one row per call. A Claude call is one `message.id`, counted by
  `jgauge.transcript`'s rule: a message is final once a line of it has a `stop_reason`, and
  before that its output is a floor, the most any of its lines said. A subagent's transcript
  (`<session>/subagents/agent-*.jsonl`) counts to its parent's session, with the subagent's id
  as its `agent`. T3 Code's own count of a run's usage, which `jgauge spend` reads, leaves the
  subagents' calls out, so a day of `jgauge spend` is the day's calls with no `agent`. A Codex
  call is one `token_count` event whose running total is new, keyed by the session and that
  total, with its model from the `turn_context` before it; its uncached input is its input
  less what it read from the cache and wrote to it, as Claude counts it. A call another session
  has already copied keeps its first session, as a resumed or forked Claude session copies the
  calls it carries over.
  A Claude call keeps its reasoning `effort`, the one the first of its lines that names one
  names (Claude Code 2.1.303 and later), its `effort` or else its `perTurnEffort`, and none
  where no line does, as a Codex call has none.

A build reads only the transcripts of the sessions `sessions` names, so a test's T3 home, which
has no store, reads none. Each file is read on from a cursor in `cursors`, under the provider
in place of a project and the file's path as its source, as a jbus log is (`telemetry._log`).
The files written since the last build are read first, newest calls and all, and then the rest
oldest first, so the ones nearest the cleanup are copied next when a pass's budget runs out: a
backlog of old files, such as the reread of `REREAD`, holds up no new call.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any

import jbus
from jbus import boxes, roles
from jbus.telemetry import cursors, values
from jgauge import transcript
from jroles import inventory

CLAUDE, CODEX = "claude", "codex"
PRICED = CLAUDE
"""The provider whose models `jgauge.spend.PRICES` prices, and the only one."""
DRIVERS = {inventory.BUILT_IN: CLAUDE, "codex": CODEX}
"""T3's driver of a provider thread, by the provider the store names."""
COUNTS = ("input", "cache_write", "cache_read", "output")

SESSIONS = """
SELECT coalesce(p.driver, json_extract(p.payload_json, '$.nativeThreadRef.driver')),
    json_extract(p.payload_json, '$.nativeThreadRef.nativeId'), p.thread_id,
    p.provider_instance_id, t.title, t.project_id, j.title
FROM orchestration_v2_projection_provider_threads p
LEFT JOIN orchestration_v2_projection_threads t ON t.thread_id = p.thread_id
LEFT JOIN projection_projects j ON j.project_id = t.project_id
WHERE json_extract(p.payload_json, '$.nativeThreadRef.nativeId') IS NOT NULL
"""


@dataclass(frozen=True)
class Session:
    """A provider's native session and the T3 thread it ran: its project, and the role and slug
    its title gives."""

    provider: str
    session: str
    thread: str | None
    instance: str | None
    project: str | None
    role: str
    slug: str | None


@dataclass(frozen=True)
class Transcript:
    """A file of calls: the provider, the session they count to, its path, and for a Claude
    subagent's transcript, the subagent's id."""

    provider: str
    session: str
    path: Path
    agent: str | None = None


def sessions(config: jbus.Config) -> list[Session]:
    """Each native session of Claude or Codex that T3's store names, or none where there is no
    store or it cannot be read."""
    store = boxes.store()
    if not store.is_file():
        return []
    try:
        reader = sqlite3.connect(f"file:{store}?mode=ro", uri=True, timeout=30)
        try:
            found = reader.execute(SESSIONS).fetchall()
        finally:
            reader.close()
    except sqlite3.Error:
        return []
    names = {project.project_id: project.name for project in config.projects}
    out = []
    for driver, native, thread, instance, title, project_id, project in found:
        provider = DRIVERS.get(driver or "")
        if provider is None or not isinstance(native, str) or not native:
            continue
        role, slug = roles.role_of(title or "")
        out.append(
            Session(
                provider,
                native,
                thread,
                instance,
                names.get(project_id, project),
                role,
                slug or None,
            )
        )
    return out


def _homes(driver: str, default: Path) -> list[Path]:
    """The homes of the provider's instances in T3's settings, and `default`, each once."""
    declared = inventory.declared(inventory.path(), Path.home())
    found = [default]
    if isinstance(declared, dict):
        found += [one.home for one in declared.values() if one.driver == driver and one.home]
    seen: dict[Path, None] = {}
    for home in found:
        seen.setdefault(home.resolve(), None)
    return list(seen)


def transcripts(known: set[tuple[str, str]], since: datetime | None = None) -> list[Transcript]:
    """The transcripts of the sessions in `known`: a Claude session's under each Claude home's
    `projects/`, with its subagents', and a Codex session's rollouts. Those written after `since`
    come first, then the rest, each part oldest first."""
    found: dict[Path, Transcript] = {}
    claude = {session for provider, session in known if provider == CLAUDE}
    codex = {session for provider, session in known if provider == CODEX}
    if claude:
        for home in _homes(inventory.BUILT_IN, Path.home() / ".claude"):
            for folder in _folders(home / "projects"):
                for entry in _entries(folder):
                    name = entry.name
                    if name.endswith(".jsonl") and name[:-6] in claude:
                        found.setdefault(
                            Path(entry.path).resolve(),
                            Transcript(CLAUDE, name[:-6], Path(entry.path)),
                        )
                    elif name in claude and entry.is_dir():
                        for agent in _entries(Path(entry.path) / "subagents"):
                            if agent.name.endswith(".jsonl"):
                                found.setdefault(
                                    Path(agent.path).resolve(),
                                    Transcript(CLAUDE, name, Path(agent.path), agent.name[:-6]),
                                )
    if codex:
        named = os.environ.get("CODEX_HOME")
        for home in _homes("codex", Path(named) if named else Path.home() / ".codex"):
            for folder in ("sessions", "archived_sessions"):
                for path in (home / folder).rglob("rollout-*.jsonl"):
                    session = path.stem[-36:]
                    if session in codex:
                        found.setdefault(path.resolve(), Transcript(CODEX, session, path))
    fresh = since.timestamp() * 1e9 if since else None
    return sorted(
        found.values(), key=lambda one: (fresh is None or _age(one)[0] <= fresh, _age(one))
    )


def _age(one: Transcript) -> tuple[int, str]:
    try:
        return one.path.stat().st_mtime_ns, str(one.path)
    except OSError:
        return 0, str(one.path)


def _folders(where: Path) -> Iterator[Path]:
    for entry in _entries(where):
        if entry.is_dir():
            yield Path(entry.path)


def _entries(where: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(where) as found:
            return list(found)
    except OSError:
        return []


Call = dict[str, Any]
"""One call's row of `calls`, by column, without its `day`."""


def claude_calls(lines: Iterable[bytes], session: str, _: sqlite3.Connection) -> list[Call]:
    """The calls of a Claude transcript's lines, by `jgauge.transcript`'s rule. Only a line
    that names a usage is parsed."""
    entries = []
    for line in lines:
        if b'"usage"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return [
        {
            "call": one.id,
            "session": session,
            "at": values.utc(one.first_ts),
            "model": one.model,
            "input": one.tokens_in,
            "cache_write": one.cache_write,
            "cache_read": one.cache_read,
            "output": one.out,
            "final": int(one.final),
            "effort": one.effort,
        }
        for one in transcript.calls(entries)
    ]


def codex_calls(lines: Iterable[bytes], session: str, store: sqlite3.Connection) -> list[Call]:
    """The calls of a Codex rollout's lines: each `token_count` whose running total is new,
    on the model of the turn before it. A count timed before the rollout's own start is one a
    fork replayed from its parent, so it is not this session's. Lines read on from a cursor
    take the model the session's last call had."""
    held = store.execute(
        "SELECT model FROM calls WHERE provider = ? AND session = ? ORDER BY at DESC LIMIT 1",
        (CODEX, session),
    ).fetchone()
    model, began, out = held[0] if held else None, None, {}
    for line in lines:
        if not any(word in line for word in (b"token_count", b"turn_context", b"session_meta")):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict):
            continue
        at = values.utc(entry.get("timestamp"))
        if entry.get("type") == "session_meta":
            began = values.utc(payload.get("timestamp")) or at
        elif entry.get("type") == "turn_context":
            model = payload.get("model") if isinstance(payload.get("model"), str) else model
        elif payload.get("type") == "token_count":
            info = payload.get("info")
            if not isinstance(info, dict) or (began and at and at < began):
                continue
            last, total = info.get("last_token_usage"), info.get("total_token_usage")
            if not isinstance(last, dict) or not isinstance(total, dict):
                continue
            mark = transcript.count(total.get("total_tokens"))
            read = transcript.count(last.get("cached_input_tokens"))
            wrote = transcript.count(last.get("cache_write_input_tokens"))
            key = f"{session}:{mark}"
            out.setdefault(
                key,
                {
                    "call": key,
                    "session": session,
                    "at": at,
                    "model": model,
                    "input": max(0, transcript.count(last.get("input_tokens")) - read - wrote),
                    "cache_write": wrote,
                    "cache_read": read,
                    "output": transcript.count(last.get("output_tokens")),
                    "final": 1,
                    "effort": None,
                },
            )
    return list(out.values())


READERS: dict[str, Callable[[Iterable[bytes], str, sqlite3.Connection], list[Call]]] = {
    CLAUDE: claude_calls,
    CODEX: codex_calls,
}

_COLUMNS = (
    "provider",
    "call",
    "session",
    "agent",
    "at",
    "model",
    *COUNTS,
    "final",
    "effort",
    "day",
)


def _while_open(name: str, value: str) -> str:
    return f"{name} = CASE WHEN calls.final = 0 THEN {value} ELSE calls.{name} END"


_KEEP = ", ".join(
    [
        *(
            _while_open(
                name,
                f"CASE WHEN excluded.final > calls.final THEN excluded.{name} "
                f"ELSE max(calls.{name}, excluded.{name}) END",
            )
            for name in COUNTS
        ),
        _while_open(
            "model",
            "CASE WHEN excluded.final > calls.final THEN excluded.model ELSE calls.model END",
        ),
        _while_open("at", "min(calls.at, excluded.at)"),
        _while_open("final", "max(calls.final, excluded.final)"),
        "effort = coalesce(calls.effort, excluded.effort)",
    ]
)
CALL_INSERT = (
    f"INSERT INTO calls ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' for _ in _COLUMNS)}) "
    f"ON CONFLICT (provider, call) DO UPDATE SET {_KEEP} "
    "WHERE calls.final = 0 OR (calls.effort IS NULL AND excluded.effort IS NOT NULL)"
)
"""A call not held is added. One held is changed only while it is not final: a final line's
counts replace a floor's, and another floor's raise it, as `jgauge.transcript.calls` merges a
message's lines. Its session stays the one that first copied it. A call held with no effort takes
the first one a line of it names, final or not, and that changes nothing else of a final call, so
a store copied before calls kept effort (`migrations.v013_call_effort`) takes it by reading each
transcript again."""

REREAD = f"DELETE FROM cursors WHERE project = '{CLAUDE}';\n"
"""The SQL that drops the cursor of each Claude transcript, so the next build reads each one
still on disk again: `migrations.v013_call_effort` runs it to copy the effort of the calls the
store held before it kept one."""

_FROM_T3 = ("thread", "instance", "project", "role", "slug")
SESSION_INSERT = (
    "INSERT INTO sessions (provider, session, thread, instance, project, role, slug) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (provider, session) DO UPDATE SET "
    + ", ".join(f"{name} = excluded.{name}" for name in _FROM_T3)
    + " WHERE "
    + " OR ".join(f"sessions.{name} IS NOT excluded.{name}" for name in _FROM_T3)
)
"""A session T3 names is added, and one held takes what T3 says of it now where that changed."""


def keep_sessions(store: sqlite3.Connection, found: list[Session]) -> int:
    """Add or update each session T3 names, and return how many rows changed."""
    store.execute("BEGIN")
    before = store.total_changes
    store.executemany(
        SESSION_INSERT,
        [
            (one.provider, one.session, one.thread, one.instance, one.project, one.role, one.slug)
            for one in found
        ],
    )
    changed = store.total_changes - before
    store.execute("COMMIT")
    return changed


def read(
    store: sqlite3.Connection, one: Transcript, zone: tzinfo | None, room: int | None
) -> tuple[int, int, bool]:
    """Copy the calls of a transcript's new whole lines, at most `room` bytes of them, with its
    cursor, in one transaction. Return the rows changed, the bytes read, and whether the file
    has lines left that were not read. A file unchanged since it was read whole is not opened."""
    source = str(one.path)
    try:
        stat = one.path.stat()
    except OSError:
        return 0, 0, False
    held = cursors.held(store, one.provider, source)
    if held and (held[0], held[3], held[4]) == (stat.st_ino, stat.st_size, stat.st_mtime_ns):
        return 0, 0, False
    if room is not None and room <= 0:
        return 0, 0, True
    try:
        with open(one.path, "rb") as handle:
            stat = os.fstat(handle.fileno())
            size, inode = stat.st_size, stat.st_ino
            head = cursors.head(handle)
            fits = held and held[0] == inode and held[2] == head and held[1] <= size
            start = held[1] if held and fits else 0
            handle.seek(start)
            data = handle.read(size - start if room is None else min(size - start, room))
    except OSError:
        return 0, 0, False
    end = data.rfind(b"\n") + 1
    rows = READERS[one.provider](data[:end].splitlines(), one.session, store)
    store.execute("BEGIN")
    before = store.total_changes
    store.executemany(
        CALL_INSERT,
        [
            (
                one.provider,
                *(row[name] for name in _COLUMNS[1:3]),
                one.agent,
                *(row[name] for name in _COLUMNS[4:-1]),
                values.day(row["at"], zone),
            )
            for row in rows
        ],
    )
    changed = store.total_changes - before
    whole = start + end == size
    cursors.keep(
        store,
        one.provider,
        source,
        inode,
        start + end,
        head,
        size if whole else None,
        stat.st_mtime_ns if whole else None,
    )
    store.execute("COMMIT")
    return changed, end, start + end < size and len(data) < size - start
