"""Replay `jbus needs` over a week's records: how many of the user's "what needs me" asks the list
answers, and how many items it shows that needed no one.

Run it from the repo, read only: `uv run python features/jbus/scripts/needs_replay.py [<dataset>]`.
The dataset is the week audit's (`$H/reports/week-audit/week-audit-data` by default), and the week
is its `audit` week. It reads three of its files:

- `messages.jsonl`: an ask is a typed message of the week that the audit's scorecard counts as
  "what needs me" (`NEEDS_ME`, the scorecard's own regex);
- `gates.jsonl`: a question is open at a time from its `asked_at` until its `answered_at`;
- `rows.jsonl`: a row waits for its go from its first record until its `approval_ran_at`, its
  launch or its removal.

At each ask the list is what was open in the ask's project, kept by the code's own rule
(`blockers.needs`), and a row only after `blockers.APPROVE_GRACE_SECONDS`. A gate with no `Holds:`
line closes by silence in the first pass that sees it today (`questions.silent`), so it is never on
the list, and the user's later answer to one is a correction of a default that stands, not a wait.
A gate whose default is `approve` is taken as a go gate under `go = "entry"`, whose silence starts
nothing (the records do not keep the setting). A pull request `jmerge` held is not in the records,
so no hold is replayed.

An item needed the user when the user closed it: a question answered by the user, or still open
when the records were taken, or a row approved on the user's word (basis `word`, `message`,
`answer` or `pick`). Any other item needed no one: a question closed by silence or cleared, a row
approved by a rule, an entry's go or a bot, or removed with no go. An ask is answered when the
list at that time holds every item that waited on the user, so a list that says nothing waits
answers an ask at which nothing did. Under today's settle rule that is every ask: a gate the user
answered that the list leaves out had no `Holds:` line, so its default stood and his answer
corrected it. The replay counts the asks at which such a gate was open, since a correction is
what the list does not prompt.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from jbus import blockers, questions

DATASET = Path.home() / ".local/state/home/jstack/reports/week-audit/week-audit-data"
NEEDS_ME = re.compile(r"\b(what|anything|who|does anything)\b[^?.!]{0,20}\bneeds? me\b", re.I)
WEEK = "audit"
USERS_WORD = {"word", "message", "answer", "pick"}
GRACE = timedelta(seconds=blockers.APPROVE_GRACE_SECONDS)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _at(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def asks(messages: list[dict]) -> list[dict]:
    return [
        one
        for one in messages
        if one.get("week") == WEEK
        and one.get("kind") != "resume"
        and NEEDS_ME.search(one.get("text") or "")
    ]


def _gate(one: dict) -> dict:
    """The item a question is on the list as, with the go gate's wait where its default is
    `approve`."""
    waits = "the setting go is entry, not silence" if one["default"] == "approve" else ""
    return {
        "kind": "gate",
        "key": f"gate:q{one['number']}",
        "source": questions.SOURCE,
        "number": str(one["number"]),
        "question": one["question"],
        "default": one["default"],
        "holds": one["holds"],
        "slug": one["slug"],
        "waits": waits,
    }


def gates_at(gates: list[dict], project: str, at: datetime) -> list[tuple[dict, bool]]:
    """Each question open in the project at `at`, with whether it needed the user."""
    found = []
    for one in gates:
        asked, answered = _at(one["asked_at"]), _at(one["answered_at"])
        if one["project"] != project or asked is None or asked > at:
            continue
        if answered is not None and answered <= at:
            continue
        needed = one["answered_at"] is None or one["answered_by"] not in (None, "jbus")
        found.append((one, needed))
    return found


def rows_at(rows: list[dict], project: str, at: datetime) -> list[tuple[dict, bool]]:
    """Each row of the project waiting for its go at `at`, past its grace, with whether the go
    was the user's word."""
    found = []
    for row in rows:
        first = _at(row["t_first_record"])
        if row["project"] != project or first is None or first + GRACE > at:
            continue
        ends = [_at(row[name]) for name in ("approval_ran_at", "t_launched", "t_removed")]
        if any(end is not None and end <= at for end in ends):
            continue
        approved = _at(row["approval_ran_at"])
        if approved is None and row["approval_basis"] is not None:
            continue
        needed = approved is None and row["t_removed"] is None
        needed = needed or (approved is not None and row["approval_basis"] in USERS_WORD)
        found.append((row, needed))
    return found


def replay(dataset: Path) -> dict:
    messages = _jsonl(dataset / "messages.jsonl")
    gates = _jsonl(dataset / "gates.jsonl")
    rows = _jsonl(dataset / "rows.jsonl")
    counted = {
        "asks": 0,
        "answered": 0,
        "answered with items": 0,
        "answered with nothing waits": 0,
        "asks with a gate left out that the user answered later": 0,
        "items shown": 0,
        "items shown that needed no one": 0,
        "corrections, no Holds: line": 0,
        "old list items": 0,
        "old list items that needed no one": 0,
    }
    shown, noise, old, old_noise, corrected = set(), set(), set(), set(), set()
    for ask in asks(messages):
        at, project = _at(ask["at"]), ask["project"]
        counted["asks"] += 1
        listed, left_out = [], False
        for one, needed in gates_at(gates, project, at):
            key = (project, "q", one["number"])
            old.add(key)
            if not needed:
                old_noise.add(key)
            if blockers.needs(_gate(one)):
                listed.append(key)
                if not needed:
                    noise.add(key)
            elif needed:
                corrected.add(key)
                left_out = True
        for row, needed in rows_at(rows, project, at):
            key = (project, "row", row["slug"])
            listed.append(key)
            if not needed:
                noise.add(key)
        shown.update(listed)
        counted["asks with a gate left out that the user answered later"] += left_out
        counted["answered"] += 1
        name = "answered with items" if listed else "answered with nothing waits"
        counted[name] += 1
    counted["items shown"] = len(shown)
    counted["items shown that needed no one"] = len(noise)
    counted["corrections, no Holds: line"] = len(corrected)
    counted["old list items"] = len(old)
    counted["old list items that needed no one"] = len(old_noise)
    return counted


def main(argv: list[str]) -> int:
    dataset = Path(argv[0]) if argv else DATASET
    for name, count in replay(dataset).items():
        print(f"{name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
