"""Reading a Claude Code transcript: its lines, and its calls counted once each.

The counting rule (features/jgauge/docs/meter-findings.md has the observations behind it):

- A call is one `message.id`. A message has one line per content block, and a
  line can be written twice, so lines are never counted.
- A line with a `stop_reason` was written when the message finished and holds
  its final counts. A message with such a line is final.
- A message with no such line has only the output count as it started: a floor.
  Its input and cache counts are still exact. The floor is kept apart from the
  final output and flagged, never added to it and never estimated upward.
- A message whose model is `<synthetic>` is the harness's own text, not a call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SYNTHETIC = "<synthetic>"
FIELDS = ("tokens_in", "tokens_out", "cache_read", "cache_write")


class TranscriptError(Exception):
    """A transcript that cannot be read. `reason` is one short word for the record."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def read_text(path: Path) -> str:
    """A transcript's text. Raises `TranscriptError` if it cannot be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError as error:
        raise TranscriptError("missing", str(path)) from error
    except OSError as error:
        raise TranscriptError("unreadable", f"{path}: {error}") from error


def lines(path: Path) -> list[dict]:
    """A transcript's lines. A line still being written does not parse and is skipped."""
    return parse(read_text(path), path)


def parse(text: str, path: Path) -> list[dict]:
    entries, bad = [], 0
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(entry, dict):
            entries.append(entry)
        else:
            bad += 1
    if bad and not entries:
        raise TranscriptError("unknown-shape", f"{path}: no line is a JSON object")
    return entries


def count(value: object) -> int:
    """A token count, or 0 for anything that is not one. `True` is not a count."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


@dataclass
class Call:
    id: str
    model: str
    tokens_in: int = 0
    cache_write: int = 0
    cache_read: int = 0
    out: int = 0
    final: bool = False
    first_ts: str | None = None
    last_ts: str | None = None

    @property
    def input_side(self) -> int:
        return self.tokens_in + self.cache_write + self.cache_read


def calls(entries: list[dict]) -> list[Call]:
    found: dict[str, Call] = {}
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        key, model, usage = message.get("id"), message.get("model"), message.get("usage")
        if not isinstance(key, str) or not key or not isinstance(usage, dict):
            continue
        if not isinstance(model, str) or model == SYNTHETIC:
            continue
        call = found.setdefault(key, Call(key, model))
        stamp = entry.get("timestamp") if isinstance(entry.get("timestamp"), str) else None
        call.first_ts = call.first_ts or stamp
        call.last_ts = stamp or call.last_ts
        stopped = bool(message.get("stop_reason"))
        if call.final and not stopped:
            continue
        fresh = stopped and not call.final
        sizes = {
            "tokens_in": count(usage.get("input_tokens")),
            "cache_write": count(usage.get("cache_creation_input_tokens")),
            "cache_read": count(usage.get("cache_read_input_tokens")),
            "out": count(usage.get("output_tokens")),
        }
        for name, size in sizes.items():
            setattr(call, name, size if fresh else max(getattr(call, name), size))
        call.final = call.final or stopped
        call.model = model
    return list(found.values())


def empty_totals() -> dict:
    return {
        "calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cache_read": 0,
        "cache_write": 0,
        "out_floor": 0,
        "out_floor_calls": 0,
    }


def add_call(totals: dict, call: Call) -> None:
    totals["calls"] += 1
    totals["tokens_in"] += call.tokens_in
    totals["cache_read"] += call.cache_read
    totals["cache_write"] += call.cache_write
    if call.final:
        totals["tokens_out"] += call.out
    else:
        totals["out_floor"] += call.out
        totals["out_floor_calls"] += 1


def totals(found: list[Call]) -> tuple[dict, dict[str, dict]]:
    whole, by_model = empty_totals(), {}
    for call in found:
        add_call(whole, call)
        add_call(by_model.setdefault(call.model, empty_totals()), call)
    return whole, by_model
