"""Say why each branch of a merged pull request was force-pushed, over a period.

`jbus ci` counts the force-pushes of the branches of the pull requests merged in a period, over
those pull requests (`rebases per merged PR`, held to under 0.3). This splits that count by what
jbus told the crew before each push:

- `crew fix`: its check failed (`failed`, `refailed`), a review found something (`review` with
  findings, `rereview`, `expedite`), a rebase dropped lines (`drops`), or it was told to carry on
  (`resume`)
- `stack move`: the pull request it was stacked on merged (`restack`)
- `conflict`: it conflicted with main (`conflict`, and a `rebase` for a conflict or for a check
  that failed over today's main)
- `other`: anything else, a told `mainmoved` and a push no event explains included

The cause of a push is the last such event of its pull request in the two hours before it, as
`jbus.ci.numbers` reads a push, else the last since the push before it, at most a day back.

    uv run python features/jmerge/scripts/force_pushes.py ~/.local/state/jbus/jstack \\
        --since 2026-10-26T14:00:00Z --until 2026-11-02T14:00:00Z

It reads `ci-prs.jsonl` and `events.jsonl` in that state directory and prints the counts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

LOOKBACK = timedelta(hours=2)
FALLBACK = timedelta(hours=24)
CAUSES = ("crew fix", "stack move", "conflict", "other")
FIX = {"failed", "refailed", "expedite", "rereview", "drops", "resume"}
TOLD = {*FIX, "review", "restack", "conflict", "rebase", "mainmoved"}


def when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def cause_of(event: dict) -> str:
    kind, text = event["event"], event.get("text", "") + event.get("line", "")
    if kind in FIX or kind == "review":
        return "crew fix"
    if kind == "restack":
        return "stack move"
    if kind == "conflict" or (kind == "rebase" and re.search(r"conflicts with|fails on", text)):
        return "conflict"
    return "other"


def told(pulls: list[dict], events: list[dict]) -> dict[int, list[tuple[datetime, str]]]:
    """Each pull request's told events, as (time, cause). An event names its pull request by
    its slug, which is its branch, else by the `#<n>` of its line, except a `restack`, whose
    number is the pull request that merged under it."""
    numbers = {one["branch"]: int(one["number"]) for one in pulls}
    found: dict[int, list[tuple[datetime, str]]] = {}
    for event in events:
        kind = event.get("event")
        if kind not in TOLD or not event.get("at"):
            continue
        if kind == "review" and "findings" not in event.get("line", ""):
            continue
        number = numbers.get(event.get("slug", ""))
        named = re.search(r"#(\d+)", event.get("line", ""))
        if number is None and named and kind != "restack":
            number = int(named[1])
        if number is not None:
            found.setdefault(number, []).append((when(event["at"]), cause_of(event)))
    return found


def merged_in(pulls: list[dict], since: datetime, until: datetime) -> list[dict]:
    return [one for one in pulls if one.get("merged") and since <= when(one["merged"]) < until]


def causes(pulls: list[dict], events: list[dict], since: datetime, until: datetime) -> Counter:
    """The cause of each force-push of each pull request merged in `[since, until)`."""
    merged = merged_in(pulls, since, until)
    by_pull = told(merged, events)
    counted: Counter = Counter({cause: 0 for cause in CAUSES})
    for one in merged:
        near = by_pull.get(int(one["number"]), [])
        pushes = sorted(when(at) for at in one.get("pushes", []))
        for at, pushed in enumerate(pushes):
            before = [m for m in near if pushed - LOOKBACK <= m[0] <= pushed]
            if not before:
                start = max(pushed - FALLBACK, pushes[at - 1] if at else pushed - FALLBACK)
                before = [m for m in near if start <= m[0] <= pushed]
            counted[max(before)[1] if before else "other"] += 1
    return counted


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    asked = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    asked.add_argument("state", type=Path, help="the project's jbus state directory")
    asked.add_argument("--since", type=when, required=True)
    asked.add_argument("--until", type=when, required=True)
    args = asked.parse_args()
    pulls = read(args.state / "ci-prs.jsonl")
    counted = causes(pulls, read(args.state / "events.jsonl"), args.since, args.until)
    merged = len(merged_in(pulls, args.since, args.until))
    total = sum(counted.values())
    print(f"{total} force-pushes over {merged} merged pull requests ({total / max(merged, 1):.2f})")
    for cause in CAUSES:
        print(f"{cause}: {counted[cause]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
