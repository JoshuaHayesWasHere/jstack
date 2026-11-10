"""The append-only records jbus keeps of what its snapshots overwrite: each version of a brief,
each pull request of a row, and each attempt of a workflow run. The telemetry store reads each as
a log (`jbus.telemetry.records`).

Each comes from what jbus already holds, and none asks GitHub anything:

- `brief-versions.jsonl`: `queue._store`, the one writer of a stored brief, adds a line each time
  the brief's sha (`judgement.brief_sha`) changes, and a line with no sha when the brief is taken
  away. It writes the line before the brief, and no line whose sha is the slug's last already, so
  a store that dies between the two loses no version and writes none twice. The text of each
  version is kept once, by its sha, in `brief-versions/`, and the line holds the sha, the size,
  what the version's `Pull request:` line asks (`pull`) and how its last Result ended the row
  (`outcome`, `jbus.outcome.kind`, null where it names none): the store keeps no text. A row's
  close is written in the home's copy of its brief, which `queue._store` never stores, so the
  pass also adds a line of that copy when it moves a row to `done` (`states.derive`).
- `row-pulls.jsonl`: the step `history.pulls` adds a line the first time the pass's world shows a
  pull request under a row's slug as open, and again the first time it shows it merged. A row
  whose pull request was closed and opened again, or redone, has a line for each.
- `runs.jsonl`: `wakes.read` hands the list of the repo's last workflow runs it asked GitHub for
  to `runs`, which adds a line for each completed attempt not already in the log, by run and
  attempt. A run is in that list while it is among the repo's last 40, so an attempt that ends and
  is rerun between two passes, or a rerun of an older run, is not seen.

A line is added only where the log does not hold its key, read from the log itself, so a writer
that dies after its append and runs again adds nothing twice.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbus import outcome, verbs
from jmerge import judgement
from jsettings import store

if TYPE_CHECKING:
    from jbus.poll import Half

BRIEFS = "brief-versions.jsonl"
KEPT = "brief-versions"
PULLS = "row-pulls.jsonl"
RUNS = "runs.jsonl"
TAIL = 256 * 1024
"""How much of the end of `runs.jsonl` holds the keys a list of the last runs can repeat."""


def _lines(path: Path, tail: int | None = None) -> list[dict[str, Any]]:
    """The log's lines that are JSON objects, in order, of its last `tail` bytes where given."""
    try:
        with open(path, "rb") as handle:
            if tail is not None:
                handle.seek(max(0, os.fstat(handle.fileno()).st_size - tail))
            data = handle.read()
    except FileNotFoundError:
        return []
    found = []
    for line in data.decode(errors="replace").splitlines():
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if isinstance(one, dict):
            found.append(one)
    return found


def held(path: Path, key: Callable[[dict[str, Any]], Any], tail: int | None = None) -> set:
    """The keys of the log's lines, of its last `tail` bytes where given."""
    return {key(one) for one in _lines(path, tail)}


def add(path: Path, lines: Iterable[dict[str, Any]], key, tail: int | None = None) -> None:
    """Append each line whose key the log does not hold, once."""
    found = held(path, key, tail)
    new = []
    for line in lines:
        if key(line) not in found:
            found.add(key(line))
            new.append(line)
    store.append_jsonl(path, new)


def brief(state: Path, slug: str, was: str | None, text: str | None, at: datetime) -> None:
    """Record that the stored brief of `slug` went from `was` to `text`, None for no brief, where
    its sha changed."""
    before = judgement.brief_sha(was) if was is not None else ""
    after = judgement.brief_sha(text) if text is not None else ""
    if before == after or _last(state / BRIEFS, slug) == after:
        return
    if text is not None:
        kept = state / KEPT / f"{after}.md"
        if not kept.exists():
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_text(text)
    line = {
        "at": at.isoformat(),
        "slug": slug,
        "sha": after,
        "was": before,
        "bytes": len(text.encode()) if text is not None else 0,
        "pull": outcome.pull(text) if text is not None else "none",
        "outcome": outcome.kind(outcome.read(text)) if text is not None else None,
    }
    store.append_jsonl(state / BRIEFS, [line])


def _last(path: Path, slug: str) -> str | None:
    """The sha of the last version the log holds of `slug`, of its last `TAIL` bytes."""
    found = None
    for one in _lines(path, TAIL):
        if one.get("slug") == slug:
            found = one.get("sha")
    return found


def _pull_key(one: dict[str, Any]) -> tuple:
    return one.get("slug"), one.get("number"), one.get("state")


def pulls(half: Half) -> None:
    """Record each pull request the world shows under a row's slug, open or merged, once each."""
    world = half.seen.world
    assert world is not None
    at = half.run.now.isoformat()
    lines = [
        {
            "at": at,
            "slug": slug,
            "number": pull.get("number"),
            "state": state,
            "branch": pull.get("headRefName"),
            "head": pull.get("headRefOid"),
            "merged_at": pull.get("mergedAt"),
        }
        for state, found in (("open", world.open), ("merged", world.merged))
        for slug, pull in sorted(found.items())
        if isinstance(pull, dict) and isinstance(pull.get("number"), int)
    ]
    add(half.run.state / PULLS, lines, _pull_key)


def _run_key(one: dict[str, Any]) -> tuple:
    return one.get("run"), one.get("attempt")


def runs(state: Path, said: Any, now: datetime) -> None:
    """Record each completed run attempt of GitHub's list of the repo's workflow runs."""
    found = said.get("workflow_runs") if isinstance(said, dict) else None
    lines = [
        {
            "at": now.isoformat(),
            "run": one.get("id"),
            "attempt": one.get("run_attempt") or 1,
            "workflow": one.get("name"),
            "sha": one.get("head_sha"),
            "branch": one.get("head_branch"),
            "event": one.get("event"),
            "pr": next(
                (p.get("number") for p in one.get("pull_requests") or [] if isinstance(p, dict)),
                None,
            ),
            "created": one.get("created_at"),
            "started": one.get("run_started_at"),
            "updated": one.get("updated_at"),
            "conclusion": one.get("conclusion"),
        }
        for one in found or []
        if isinstance(one, dict) and isinstance(one.get("id"), int)
        if one.get("status") == "completed"
    ]
    add(state / RUNS, sorted(lines, key=lambda one: one["updated"] or ""), _run_key, TAIL)


STEPS = (verbs.Step("tellers", 16, "history.pulls", pulls, ("world",)),)
