"""What one thread cost, read from its transcript and nothing else.

The transcript is the record. The counting rule is `transcript.calls`: once
per `message.id`. Two figures come from it:

- the total: input, cache write, cache read and output, summed over calls;
- the peak context: the largest input side (input plus cache read plus cache
  write) of any one call, which is how full the context got.

A session's subagents, when it has any, are rows of their own.
"""

from __future__ import annotations

from pathlib import Path

from jgauge import transcript

SUMMED = (*transcript.empty_totals(), "total")


def _row(path: Path, role: str, seen: set[str]) -> dict:
    """One transcript's counts. A message id already in `seen` is not counted again."""
    entries = transcript.lines(path)
    found = [call for call in transcript.calls(entries) if call.id not in seen]
    seen.update(call.id for call in found)
    whole, by_model = transcript.totals(found)
    stamps = sorted(stamp for call in found for stamp in (call.first_ts, call.last_ts) if stamp)
    return {
        "role": role,
        "session": next(
            (e["sessionId"] for e in entries if isinstance(e.get("sessionId"), str)), path.stem
        ),
        "agent": path.stem.removeprefix("agent-") if role == "subagent" else None,
        "transcript": str(path),
        **whole,
        "total": _total(whole),
        "peak_context": max((call.input_side for call in found), default=0),
        "first_ts": stamps[0] if stamps else None,
        "last_ts": stamps[-1] if stamps else None,
        "models": by_model,
    }


def _total(sums: dict) -> int:
    """Every token of a sum. A floor counts as output too, though it is not yet final."""
    return (
        sums["tokens_in"]
        + sums["cache_write"]
        + sums["cache_read"]
        + sums["tokens_out"]
        + sums["out_floor"]
    )


def _rows(path: Path, seen: set[str]) -> list[dict]:
    """A session's row, then one for each subagent it started.

    The search goes down the whole `subagents/` directory: Claude Code writes an agent that a
    workflow started a level below, in `subagents/workflows/<workflow id>/`.
    """
    agents = sorted((path.with_suffix("") / "subagents").rglob("agent-*.jsonl"))
    return [_row(path, "session", seen), *(_row(agent, "subagent", seen) for agent in agents)]


def _sum(rows: list[dict]) -> dict:
    whole = {name: sum(row[name] for row in rows) for name in SUMMED}
    return {**whole, "peak_context": max((row["peak_context"] for row in rows), default=0)}


def of_transcript(path: Path) -> dict:
    """A session's cost. Raises `TranscriptError` if its transcript cannot be read."""
    rows = _rows(path, set())
    return {"transcript": str(path), "rows": rows, "total": _sum(rows)}


def render(report: dict) -> str:
    heads = ("", "Calls", "Input", "Cache write", "Cache read", "Output", "Total", "Peak context")
    lines = [heads]
    for row in [*report["rows"], {**report["total"], "role": "total", "session": ""}]:
        output = row["tokens_out"] + row["out_floor"]
        name = f"{row['role']} {(row.get('agent') or row['session'])[:8]}".strip()
        sizes = ("calls", "tokens_in", "cache_write", "cache_read")
        lines.append(
            (
                name,
                *(f"{row[key]:,}" for key in sizes),
                f"{output:,}",
                f"{row['total']:,}",
                f"{row['peak_context']:,}",
            )
        )
    widths = [max(len(line[i]) for line in lines) for i in range(len(heads))]
    total = report["total"]
    out = [
        f"Session {report['transcript']}: "
        f"{total['total'] / 1e6:.2f}M tokens in {total['calls']:,} calls",
        "",
    ]
    out += [
        "  ".join(
            f"{cell:<{width}}" if i == 0 else f"{cell:>{width}}"
            for i, (cell, width) in enumerate(zip(line, widths, strict=True))
        ).rstrip()
        for line in lines
    ]
    if total["out_floor_calls"]:
        out.append(
            f"  note: {total['out_floor_calls']} call(s) had no finished line; "
            f"{total['out_floor']:,} of the output is a floor"
        )
    return "\n".join(out)
