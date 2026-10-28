"""Who acts in jbus, on what word, and through which door: the shapes every act is made of.

One act is one `Act`, a line of `acts.jsonl` that `jbus.acts` writes. It names the `Party`
that acted, the `Action` it took, the `Evidence` it acted on, and what came of it.

- `Party`: the user, the one bot, a home, or jbus's own pass. Its `route` is how it reached
  jbus: the command line, the view's page, or the bot's own route, `POST /act` on the view.
  The bot has no name: one bot speaks for the user, and it is known by its route alone.
- `Door`: an action that is irreversible or slow to revert. `DOORS` is the one table of them:
  the six cases a gate's `Holds:` line names (`CASES`), each with the words that name it in
  prose, which `jbus.waiting` and `jbus.item` read.
- `Evidence`: the user's words an act rests on, and where jbus read them. `checked` says jbus
  read the words and their time itself, in T3 Code or on a Lavish page; anything typed or
  carried by the bot is not checked. Each basis of an approval (`jbus.queue.BASES`, `RULE`
  and `ENTRY`) is one `source` (`SOURCE`).
- `Action`: a go for a row, or an answer to a question, with what it was given to check
  against: the brief's sha for a go, and the event the actor last saw.
- `Act`: the record, `v` 1, with its `outcome`: `done`, `gated` (a door the party may not open
  alone, parked as a gate for the user), `refused`, or `noop` (the same go again).

The rule of doors is `opens`: an act on a door goes through only for the user, on checked
evidence. Everything else the bot or a home may do as the user would.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from jbriefs import parse as briefs

Kind = Literal["user", "bot", "home", "jbus"]
Route = Literal["cli", "view", "bot"]
Source = Literal[
    "t3-message", "lavish-page", "bot-chat", "typed", "answer", "rule", "plan-entry", "view"
]
Verb = Literal["go", "answer"]
Outcome = Literal["done", "gated", "refused", "noop"]
SOURCES: tuple[str, ...] = get_args(Source)
CLI_PARTIES = ("user", "home")
CLI_BOT = (
    "refused: --as {party}: the bot acts only over its own route, POST /act on jbus view, with "
    "its key, and on the command line a party is user or home"
)
V = 1


@dataclass(frozen=True)
class Party:
    kind: Kind
    route: Route
    name: str = ""


USER = Party("user", "cli")
HOME = Party("home", "cli")
BOT = Party("bot", "bot")


@dataclass(frozen=True)
class Door:
    """One case of a gate that holds. `case` is the words a `Holds:` line names it by, and
    `named` the pattern of the words that name it in a gate's prose, or nothing."""

    case: str
    named: str = ""


DOORS = (
    Door(
        "deletes data", r"\b(delet|drop|eras|wip)\w*\b[^.]*\b(data|database|tables?|rows|records)\b"
    ),
    Door("rewrites history", r"\bforce[- ]?push"),
    Door("spends money"),
    Door(
        "touches prod or real users",
        r"\bdeploy"
        r"|\b(customers?|outside|external|public)\b[^.]*\b(message|e-?mail|post|reply)"
        r"|\b(message|e-?mail|post|reply)\w*\b[^.]*\b(customers?|outside|external|public)\b",
    ),
    Door(
        "changes access or secrets",
        r"\b(secrets?|tokens?|credentials?|passwords?|api[ -]?keys?)\b",
    ),
    Door("publishes"),
)
CASES = tuple(one.case for one in DOORS)


def door(case: str) -> Door:
    return next(one for one in DOORS if one.case == case)


SOURCE = {
    "word": "typed",
    "answer": "answer",
    "message": "t3-message",
    "page": "lavish-page",
    "rule": "rule",
    "entry": "plan-entry",
}
"""The `Evidence.source` of each basis an approval has today (`jbus.queue.BASES`, `RULE` and
`ENTRY`).
A source no basis has, such as `bot-chat`, is its own basis in the approval record."""


@dataclass(frozen=True)
class Evidence:
    source: Source
    ref: str
    words: str = ""
    said_at: str = ""
    said_in: str = ""
    checked: bool = False

    @property
    def basis(self) -> str:
        """The basis the approval record names for this evidence."""
        return next(
            (basis for basis, source in SOURCE.items() if source == self.source), self.source
        )


def evidence(given: str) -> Evidence:
    """Read `--evidence <source>:<ref>`: the source and its reference, not yet read."""
    source, colon, ref = given.partition(":")
    if not colon or not ref or source not in SOURCES:
        raise ValueError(f"evidence is <{' | '.join(SOURCES)}>:<ref>, not {given}")
    return Evidence(source, ref)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Action:
    """A go for the row `subject` whose brief's sha starts with `pre`, or the answer to the
    question numbered `subject`. `seen` is the event the party last saw, or nothing. `doors`
    are the cases the brief or the gate holds for."""

    verb: Verb
    subject: str
    pre: str = ""
    seen: str = ""
    doors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Act:
    id: str
    at: str
    party: Party
    action: Action
    evidence: Evidence
    outcome: Outcome
    line: str
    gate: int | None = None
    v: int = V


def opens(party: Party, said: Evidence) -> bool:
    """Whether the party may open a door on this evidence: only the user, on words jbus read
    itself."""
    return party.kind == "user" and said.checked


def held(*lines: str) -> tuple[str, ...]:
    """The cases that `Holds:` lines name, in the table's order. Several cases on a line are
    split by commas. A line naming no case of the table holds for every door, since its words
    name one jbus does not know, and so does an empty one. No line holds for none."""
    named = {one.strip() for line in lines for one in line.split(",")}
    if named - set(CASES):
        return CASES
    return tuple(case for case in CASES if case in named)


def doors(brief: str) -> tuple[str, ...]:
    """The cases a brief's head holds for, by its `Holds: <case>` lines (`held`), as
    `jbriefs.parse.fields` reads the head."""
    return held(*(" ".join(lines) for label, lines in briefs.fields(brief) if label == "Holds"))
