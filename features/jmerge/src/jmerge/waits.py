"""How long each green pull request waited for `jmerge`, to the second, and what held it.

A pull request is ready once every check the repo requires has passed at its head and it is no
draft. From then until `jmerge` begins its merge it waits, and that wait is one spell, kept in
`merge-waits.json` while the pull request is open (`Spells`):

- `ready` is the second its required checks passed, the latest end of the run `ready.latest`
  picks of each (`ready_by` `check`), or, where GitHub gives no end, the second a run of
  `jmerge` first saw it ready (`ready_by` `run`).
- Each run that sees it ready and does not merge it names the code of the reason it waits or
  holds (`ready.code_of`). From that sighting to the next one, or to the merge, the wait is that
  code's, so the spell keeps one open segment, `code` since `seen`, and the seconds of each
  closed one by code (`blockers`). The segments do not overlap: a blocker that clears and comes
  back adds only the seconds it held, and the blockers' seconds never exceed the wait.
- From `ready` to the first sighting no run had seen it: that part of the wait is `jmerge`'s own
  delay in coming round, and no code holds it.
- A push to the head, a check run again or a draft ends the spell: it is ready again only once
  the new head's checks pass, and its wait starts then.

When the merge begins, the second before `gh pr merge` runs, the spell closes and one line goes
to the append-only `merge-waits.jsonl` beside `merge.log` (`Wait`), which `jbus telemetry`
reads. `merge.log` keeps its lines as they were.

Only a run that may merge writes, under the run lock (`jmerge.lock`); `--check` writes nothing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from jmerge import ready
from jsettings import store

SPELLS = "merge-waits.json"
LOG = "merge-waits.jsonl"

ReadyBy = Literal["check", "run"]


def stamp(at: datetime) -> str:
    """A second as the record keeps it: UTC, to the millisecond."""
    return at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _at(text: object) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Spell:
    """The wait of one pull request at one head, from `ready` on."""

    head: str
    ready: datetime
    ready_by: ReadyBy
    seen: datetime | None = None
    code: str = ""
    blockers: dict[str, float] = field(default_factory=dict)

    def close(self, at: datetime) -> None:
        """End the open segment at `at`, adding its seconds to its code's."""
        if self.seen is not None and self.code:
            held = max(0.0, (at - self.seen).total_seconds())
            self.blockers[self.code] = round(self.blockers.get(self.code, 0.0) + held, 3)
        self.seen, self.code = None, ""

    def held(self, code: str, at: datetime) -> None:
        """A sighting at `at` that waits on `code`: the open segment ends and one of `code`
        starts."""
        self.close(at)
        self.seen, self.code = at, code

    def kept(self) -> dict:
        return {
            "head": self.head,
            "ready": stamp(self.ready),
            "ready_by": self.ready_by,
            "seen": stamp(self.seen) if self.seen else None,
            "code": self.code,
            "blockers": self.blockers,
        }

    @classmethod
    def read(cls, kept: object) -> Spell | None:
        if not isinstance(kept, dict):
            return None
        at = _at(kept.get("ready"))
        head = kept.get("head")
        by = kept.get("ready_by")
        if at is None or not isinstance(head, str) or by not in ("check", "run"):
            return None
        blockers = kept.get("blockers")
        return cls(
            head,
            at,
            by,
            _at(kept.get("seen")),
            str(kept.get("code") or ""),
            {
                str(code): float(seconds)
                for code, seconds in (blockers.items() if isinstance(blockers, dict) else ())
                if isinstance(seconds, int | float)
            },
        )


@dataclass(frozen=True)
class Wait:
    """One line of `merge-waits.jsonl`: a pull request's wait from ready to the merge's start."""

    number: int
    head: str
    ready: str
    ready_by: ReadyBy
    began: str
    seconds: float
    blockers: dict[str, float]

    def line(self) -> dict:
        return {"at": self.began, **asdict(self)}


def is_ready(one: ready.PullRequest) -> bool:
    """Whether every required check passed at the head of a pull request that is no draft."""
    return not one.waiting and not one.draft


class Spells:
    """The open spells of a repo's state, by pull request, and the log of the closed ones."""

    def __init__(self, state: Path, run: bool) -> None:
        self.state = state
        self.run = run and state.is_dir()

    def _read(self) -> dict[str, Spell]:
        found = {}
        for number, kept in store.read_dict(self.state / SPELLS).items():
            spell = Spell.read(kept)
            if spell is not None:
                found[number] = spell
        return found

    def _write(self, spells: dict[str, Spell]) -> None:
        kept = {number: spell.kept() for number, spell in spells.items()}
        if kept != store.read_dict(self.state / SPELLS):
            store.write_json(self.state / SPELLS, kept)

    def _spell(self, spells: dict[str, Spell], one: ready.PullRequest, at: datetime) -> Spell:
        """The spell of `one` at its head, begun now where it has none at that head."""
        spell = spells.get(str(one.number))
        if spell is None or spell.head != one.head:
            passed = one.passed_at
            spell = Spell(one.head, passed or at, "check" if passed else "run")
            spells[str(one.number)] = spell
        return spell

    def saw(self, one: ready.PullRequest, code: str, at: datetime) -> None:
        """A run saw `one` wait or hold on `code` at `at`: a pull request that is not ready has
        no spell, and one that is gets its segment of `code` from `at`."""
        if not self.run:
            return
        spells = self._read()
        if is_ready(one):
            self._spell(spells, one, at).held(code, at)
        else:
            spells.pop(str(one.number), None)
        self._write(spells)

    def merged(self, one: ready.PullRequest, began: datetime) -> Wait | None:
        """`one` merged in a merge that began at `began`: its spell closes there and its line is
        logged."""
        if not self.run:
            return None
        spells = self._read()
        spell = self._spell(spells, one, began)
        spell.close(began)
        del spells[str(one.number)]
        wait = Wait(
            one.number,
            one.head,
            stamp(spell.ready),
            spell.ready_by,
            stamp(began),
            round(max(0.0, (began - spell.ready).total_seconds()), 3),
            spell.blockers,
        )
        store.append_jsonl(self.state / LOG, [wait.line()], sort_keys=True)
        self._write(spells)
        return wait

    def open_only(self, numbers: set[int]) -> None:
        """Drop the spells of pull requests no longer open."""
        if not self.run:
            return
        spells = self._read()
        self._write({n: spell for n, spell in spells.items() if int(n) in numbers})
