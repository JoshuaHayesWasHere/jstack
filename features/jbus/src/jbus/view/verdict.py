"""The verdict of the band at the top of `#/`: one word for the state of the work, and its exact
cause, counted from the pipeline's board (`panels/pipeline`), so the page counts nothing.

`groups` sorts the still rows of the board, the ones whose cause says they do not move, by what
each waits on. A row with a `wait` is grouped by it: a failing check, a check that runs or waits
for a runner, a check that passed and a row that has not moved since, or a row stacked on its
parent, whose group names the heads its rows' chains go back to. A row in check with no `wait`
has no run. Any other row that waits on another row is behind its head, the row its chain goes
back to, and any other row is grouped by the value the last pass judged (`cause_kind`). The
largest group comes first, and of two as large the first of `RANK`.

`judge` gives the first word of `WORDS` that holds:

- `CANNOT SEE`: jbus is stopped or its passes fail, a source the view reads cannot be read, or
  CI could not be read. The cause is that line.
- `HELD BY YOU`: the largest group of still rows waits on the user. A row waits on the user where
  it is in the stage `you`, or behind a head that is. The cause names the groups that wait on the
  user, then the largest of the rest.
- `STALLED`: rows are open, nothing merged in the last `WINDOW` hours and nothing was done in the
  last `QUIET` minutes.
- `MOVING`: rows are open otherwise. The cause names the largest groups.
- `AT REST`: nothing is open.

`needs` is the count of what needs the user, `/stack.json`'s `needs`, and the verdict carries it
so the band says it beside the word. `quiet_since` is the time of the last act or merge where
none came in the last `QUIET` minutes, and None while the work is not quiet.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from jbus.view import checked

CANNOT_SEE, HELD, STALLED, MOVING, AT_REST = (
    "CANNOT SEE",
    "HELD BY YOU",
    "STALLED",
    "MOVING",
    "AT REST",
)
WORDS = (CANNOT_SEE, HELD, STALLED, MOVING, AT_REST)
WINDOW = 3
"""The hours with no merge after which open work may be stalled."""
QUIET = 30
"""The minutes with no act after which open work with no merge is stalled."""
SHOWN = 3
"""How many groups a cause names."""
UNSEEN = frozenset({("jbus", None), ("source", None), ("ci", "could not be read")})
"""The kinds of `wrong` that leave the view blind, with the cause that does where a kind has
causes that do not: a failed run of CI is wrong but seen. A cause is matched by what it says
before its first colon, so CI that could not be read for GitHub's rate limit is blind too."""
YOU = "you"
BEHIND, NO_RUN = "behind", "no run"
WAIT = {
    checked.FAILING: "failing",
    checked.WAITING: "running",
    checked.PASSED: "passed",
    checked.STACKED: "stacked",
}
"""The kind of the group of each `wait`, named apart from the values of `work`."""
TEXT = {
    "unapproved": ("not approved", "not approved"),
    "asking": ("at a gate", "at a gate"),
    "hold": ("held for your word", "held for your word"),
    "hung": ("with a hung thread", "with a hung thread"),
    "waiting": ("with a thread that asks", "with a thread that asks"),
    "leftover": ("left with a note", "left with a note"),
    "closed": ("closed and not merged", "closed and not merged"),
    "lost": ("with a lost thread", "with a lost thread"),
    "ready": ("ready for a launch slot", "ready for a launch slot"),
    "launching": ("launching", "launching"),
    "working": ("at work", "at work"),
    "quiet": ("with a quiet thread", "with a quiet thread"),
    "result": ("with no Result yet", "with no Result yet"),
    "review": ("waiting for a review", "waiting for a review"),
    "findings": ("with findings to handle", "with findings to handle"),
    "second": ("waiting for a second review", "waiting for a second review"),
    "proof": ("waiting for a proof", "waiting for a proof"),
    "rebase": ("to rebase", "to rebase"),
    "scout": ("scouting", "scouting"),
    "failing": ("failing check", "failing checks"),
    "running": ("check running or queued", "checks running or queued"),
    "passed": ("passed and not moved", "passed and not moved"),
    NO_RUN: ("check with no run", "checks with no run"),
}
"""What a group of each kind is, after its count, for one row and for more."""
RANK = (
    "unapproved",
    "asking",
    "hold",
    "hung",
    "waiting",
    "leftover",
    "closed",
    "lost",
    BEHIND,
    "ready",
    "launching",
    "working",
    "quiet",
    "result",
    "review",
    "findings",
    "second",
    "failing",
    "running",
    "passed",
    NO_RUN,
    "stacked",
    "proof",
    "rebase",
)
"""The order of two groups as large: what waits on the user first, then the order of the
process."""


@dataclass(frozen=True)
class Group:
    """Still rows that wait on one thing: its kind, what it is in words, how many, the head they
    are behind, and the oldest row's time."""

    kind: str
    text: str
    count: int
    head: str | None
    since: str | None

    @property
    def said(self) -> str:
        return f"{self.count} {self.text}"


@dataclass(frozen=True)
class Verdict:
    word: str
    cause: str
    groups: tuple[Group, ...]
    needs: int
    quiet_since: str | None


def _label(row: dict[str, Any]) -> tuple[str, str | None]:
    """The kind of the group a still row is in, and the head it is behind."""
    if row["wait"]:
        return WAIT[row["wait"]], None
    if row["stage"] == checked.STEP:
        return NO_RUN, None
    if row["waits_on"]:
        return BEHIND, row["head"]
    return row["cause_kind"], None


def _stacked(rows: list[dict[str, Any]]) -> str:
    """What stacked rows are: each one once, on the head its chain goes back to, the head with
    the most rows first. Past `SHOWN` heads the rest are counted, but never just one: its name
    takes no more room than "and 1 more"."""
    heads = Counter(row["head"] if row["waits_on"] else "a merged or gone row" for row in rows)
    named = [head for head, _ in heads.most_common()]
    if len(named) <= SHOWN + 1:
        return f"stacked (on {', '.join(named)})"
    return f"stacked (on {', '.join(named[:SHOWN])} and {len(named) - SHOWN} more)"


def _text(kind: str, head: str | None, rows: list[dict[str, Any]]) -> str:
    if kind == BEHIND:
        return f"behind {head}"
    if kind == "stacked":
        return _stacked(rows)
    one, many = TEXT.get(kind, (kind, kind))
    return one if len(rows) == 1 else many


def _rank(group: Group) -> tuple[int, int, str]:
    return -group.count, RANK.index(group.kind) if group.kind in RANK else len(RANK), group.text


def _grouped(rows: list[dict[str, Any]]) -> tuple[Group, ...]:
    """The rows grouped by what they wait on, largest first."""
    lots: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for row in rows:
        lots.setdefault(_label(row), []).append(row)
    made = [
        Group(
            kind,
            _text(kind, head, lot),
            len(lot),
            head,
            min((row["since"] for row in lot if row["since"]), default=None),
        )
        for (kind, head), lot in lots.items()
    ]
    return tuple(sorted(made, key=_rank))


def _still(board: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in board["rows"] if not row["moving"]]


def groups(board: dict[str, Any]) -> tuple[Group, ...]:
    """The still rows of `board` grouped by what they wait on, largest first."""
    return _grouped(_still(board))


def _yours(row: dict[str, Any], by: dict[tuple[str, str], dict[str, Any]]) -> bool:
    """Whether a row waits on the user: it is in `you`, or behind a head that is."""
    if row["stage"] == YOU:
        return True
    head = by.get((row["project"], row["head"]))
    return bool(row["waits_on"]) and head is not None and head["stage"] == YOU


def _listed(groups: tuple[Group, ...]) -> str:
    said = [one.said for one in groups[:SHOWN]]
    return " and ".join(said) if len(said) < 3 else f"{', '.join(said[:-1])} and {said[-1]}"


def _at(when: str) -> datetime:
    return datetime.fromisoformat(when)


def judge(
    board: dict[str, Any],
    needs: int,
    wrong: list[dict[str, Any]],
    merges: list[str],
    last: str | None,
    now: datetime,
) -> Verdict:
    """The verdict at `now` of the work on `board`, with `needs` things that need the user,
    `wrong` what is wrong that is the user's (the band's wrong tier, jbus first), `merges` the
    times of the merges and `last` the time of the last act."""
    every = groups(board)
    moments = [_at(one) for one in [*merges, *([last] if last else [])]]
    latest = max(moments, default=None)
    quiet = latest is not None and now - latest >= timedelta(minutes=QUIET)
    quiet_since = latest.isoformat() if quiet and latest else None

    def said(word: str, cause: str) -> Verdict:
        return Verdict(word, cause, every, needs, quiet_since)

    blind = [
        one
        for one in wrong
        if (one["kind"], None) in UNSEEN or (one["kind"], one["cause"].partition(":")[0]) in UNSEEN
    ]
    if blind:
        first = blind[0]
        more = f", and {len(blind) - 1} more the view cannot see" if len(blind) > 1 else ""
        return said(CANNOT_SEE, f"{first['subj']} {first['cause']}{more}")
    if not board["rows"] and not board["unplaced"]:
        return said(AT_REST, "nothing is open")
    by = {(row["project"], row["slug"]): row for row in board["rows"]}
    still = _still(board)
    mine = _grouped([row for row in still if _yours(row, by)])
    rest = _grouped([row for row in still if not _yours(row, by)])
    if mine and (not rest or _rank(mine[0]) <= _rank(rest[0])):
        waits = "waits" if sum(one.count for one in mine[:SHOWN]) == 1 else "wait"
        cause = f"{_listed(mine)} {waits} on you"
        return said(HELD, cause + (f"; slowed too by {_listed(rest)}" if rest else ""))
    start = now - timedelta(hours=WINDOW)
    if not any(_at(one) >= start for one in merges) and (latest is None or quiet):
        cause = f"nothing merged in the last {WINDOW} h and nothing done in the last {QUIET} min"
        return said(STALLED, cause + (f"; still: {_listed(every)}" if every else ""))
    return said(MOVING, f"slowed by {_listed(every)}" if every else "nothing is held back")
