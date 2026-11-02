"""Who acts in jbus, on what word, and through which door: the shapes every act is made of.

One act is one `Act`, a line of `acts.jsonl` that `jbus.acts` writes. It names the `Party`
that acted, the `Action` it took, the `Evidence` it acted on, and what came of it.

- `Party`: the user, the one bot, a home, or jbus's own pass. Its `route` is how it reached
  jbus: the command line, the view's page, or the bot's own route, `POST /act` on the view.
  The bot has no name: one bot speaks for the user, and it is known by its route alone.
- `Door`: an action that is irreversible or slow to revert. `DOORS` is the one table of them:
  the six cases a gate's `Holds:` line names (`CASES`), each with the words that name it in
  prose, which `jbus.waiting` and `jbus.item` read in a gate's words as `prose` gives them, and
  the commands that walk through it (`runs`). A brief holds for the cases its `Holds:` lines
  name and for those the commands of its `Done when:` and `Proves it:` lines walk through
  (`doors`), and `jbus.door` refuses a home's own command that walks through one.
- `Evidence`: the user's words an act rests on, and where jbus read them. `checked` says jbus
  read the words and their time itself, in T3 Code (a message, or the answer to a question box);
  anything typed or carried by the bot is not checked. Each basis of an approval
  (`jbus.queue.BASES`, `RULE` and `ENTRY`) is one `source` (`SOURCE`).
- `Action`: what the party did (`Verb`) to what, with what it was given to check against: the
  brief's sha for a go, the head for an accept, and the event the actor last saw.
- `Act`: the record, `v` 1, with its `outcome`: `done`, `gated` (a door the party may not open
  alone, parked as a gate for the user), `refused`, or `noop` (the same go again).

The rule of doors is `opens`: an act on a door goes through only for the user, on checked
evidence. Everything else the bot or a home may do as the user would.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal, get_args

from jbriefs import parse as briefs

Kind = Literal["user", "bot", "home", "jbus"]
Route = Literal["cli", "view", "bot"]
Source = Literal[
    "t3-message",
    "t3-pick",
    "lavish-page",
    "bot-chat",
    "typed",
    "answer",
    "rule",
    "plan-entry",
    "view",
]
Verb = Literal["go", "answer", "hold", "remove", "withdraw", "accept", "word", "item"]
Outcome = Literal["done", "gated", "refused", "noop"]
RECORDED = "lavish-page"
"""The source of an old approval's words, which `acts.jsonl` keeps and no verb is given now."""
SOURCES: tuple[str, ...] = tuple(one for one in get_args(Source) if one != RECORDED)
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
    """One case of a gate that holds. `case` is the words a `Holds:` line names it by, `named`
    the pattern of the words that name it in a gate's prose, and `runs` the pattern of a command
    that walks through it, or nothing for either. `runs` reads one command at a time, as `walks`
    gives it, a backticked command of a brief's or a command a thread runs."""

    case: str
    named: str = ""
    runs: str = ""


_IN = r"[^`\n]"
"""What a pattern of `runs` may read past within one command: no backtick and no new line."""
_TOKEN = r"[^\s`]+"

DOORS = (
    Door(
        "deletes data",
        r"\b(delet|drop|eras|wip)\w*\b[^.]*\b(data|database|tables?|rows|records)\b",
        r"\bdrop\s+(table|database|schema)\b|\baws\s+s3\s+rm\b|\bgh\s+repo\s+delete\b"
        rf"|\bgit\s+(branch\s+-D\b|worktree\s+remove\b|push(\s+{_TOKEN})*?\s+--delete\b)",
    ),
    Door(
        "rewrites history",
        r"\bforce[- ]?push",
        rf"\bpush(\s+{_TOKEN})*?\s+(-f|--force)(?![\w-])|\bfilter-repo\b",
    ),
    Door("spends money"),
    Door(
        "touches prod or real users",
        r"\bdeploy"
        r"|\b(customers?|outside|external|public)\b[^.]*\b(message|e-?mail|post|reply)"
        r"|\b(message|e-?mail|post|reply)\w*\b[^.]*\b(customers?|outside|external|public)\b",
        r"\b(DSQL_STAGE|STAGE|AWS_PROFILE)=[\w-]*prod\b"
        r"|[\w./-]*\bdeploy\b[\w.-]*\s+(--?\S+\s+)*prod\b"
        r"|`(\s*[A-Z_][A-Z0-9_]*=\S*)*\s*(sudo\s+|env\s+|ba?sh\s+|make\s+|just\s+"
        r"|(npm|pnpm|yarn|bun)\s+run\s+|uv\s+run\s+)?[\w./-]*\bdeploy\b[\w.-]*"
        rf"(?!{_IN}*(\bdev\b|--help))"
        r"|\b(sam|cdk|serverless|wrangler|fly|flyctl|vercel)\s+deploy\b"
        r"|\bterraform\s+apply\b|\bpulumi\s+up\b|\bkubectl\s+apply\b"
        r"|(?-i:\b(A|AAAA|CNAME|TXT) record\b)",
    ),
    Door(
        "changes access or secrets",
        r"\b(secrets?|tokens?|credentials?|passwords?|api[ -]?keys?)\b",
        rf"\btailscale\s+(funnel|serve|set|up)\b(?!{_IN}*\b(off|status)\b)"
        r"|tailnet\.hujson|\btag:[a-z][\w-]*|\bauth key\b"
        r"|\b(CLOUDFLARE|TAILSCALE|TS)_API_(TOKEN|KEY)\b",
    ),
    Door(
        "publishes",
        "",
        r"\bgh\s+release\s+create\b|\b(npm|uv|cargo)\s+publish\b|\btwine\s+upload\b"
        rf"|\bgit\s+push\b{_IN}*?(--tags\b|\brefs/tags\b)",
    ),
)
CASES = tuple(one.case for one in DOORS)


def door(case: str) -> Door:
    return next(one for one in DOORS if one.case == case)


def prose(words: str, slugs: Collection[str] = ()) -> str:
    """A gate's words as the door table reads them: with its `Asked by:` line and each of the
    `slugs` jbus knows left out, but for a slug of one word, which is also the word itself. A
    known slug such as token-no-cleanup-rows then names no door, while a row named deploy does.
    A hyphenated run that is no known slug is read whole, since its shape cannot tell a slug from
    prose: drop-and-recreate, force-push-with-lease and one-time-password still name theirs."""
    words = re.sub(r"^\s*Asked by:.*$", "", words, flags=re.M | re.I)
    for slug in sorted((one for one in slugs if "-" in one), key=len, reverse=True):
        words = re.sub(rf"(?<![\w-]){re.escape(slug)}(?![\w-])", " ", words)
    return words


SOURCE = {
    "word": "typed",
    "answer": "answer",
    "message": "t3-message",
    "pick": "t3-pick",
    "page": RECORDED,
    "rule": "rule",
    "entry": "plan-entry",
}
"""The `Evidence.source` of each basis an approval has (`jbus.queue.BASES`, `RULE` and `ENTRY`),
and of `jbus.queue.PAGE`, which only an old record has.
A source no basis has, such as `bot-chat`, is its own basis in the approval record."""


@dataclass(frozen=True)
class Pick:
    """One label the user picked in a question box of T3 Code, and the question it answers."""

    question: str
    label: str


@dataclass(frozen=True)
class Evidence:
    """`picks` are the labels of a question box (`t3-pick`), and no other source has any."""

    source: Source
    ref: str
    words: str = ""
    said_at: str = ""
    said_in: str = ""
    checked: bool = False
    picks: tuple[Pick, ...] = ()

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


CHAT = "bot-chat:<address>/<device>"


def chat(given: str) -> Evidence:
    """Read the bot's evidence, `bot-chat:<address>/<device>`: the message's address in the
    bot's chat and the device it came from, both named. Any other source, such as `voice`, and
    a chat with no address or no device, is refused. The bot's go, answer and word, and a home's
    `jbus word --evidence`, are each read by this one check."""
    source, _, ref = given.partition(":")
    address, _, device = ref.partition("/")
    if source != "bot-chat" or not address.strip() or not device.strip():
        raise ValueError(f"evidence is {CHAT}, not {given}")
    return Evidence(source, ref)


@dataclass(frozen=True)
class Action:
    """One verb on its subject: a go for the row `subject` whose brief's sha starts with `pre`,
    the answer to the question numbered `subject`, a hold, remove or withdraw of the row
    `subject`, the accept of the pull request of the row `subject` at the head `pre`, a word for
    the home whose scope is `subject` (empty for the root home), or the go of the work item
    `subject`. `seen` is the event the party last saw, or nothing. `doors` are the cases the
    action holds for: the brief's or the gate's, and for an accept a protected path's."""

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


DRY = re.compile(r"--dry-run\b|--help\b|\bDRY_RUN=(1|true|yes)\b", re.I)
"""A command that runs dry, or only says how it is run, walks through no door."""
ASIDE = re.compile(r"\b(never|do not|don't|not run|without)\b", re.I)
"""Words that say a brief's segment runs no command it names."""
_RUNS = tuple((one.case, re.compile(one.runs, re.I)) for one in DOORS if one.runs)
_SEGMENT = re.compile(r"[;\n]|, (?=and |then )")
_SPAN = re.compile(r"`[^`\n]*`")
WALKED = ("Done when", "Proves it")
"""The fields of a brief whose commands it runs."""


def walks(command: str) -> tuple[tuple[str, str], ...]:
    """The doors one command walks through, by each case's `runs`, in the table's order, each
    with what it matched: the backticked command it is in, where it is in one. `command` is a
    segment of a brief's prose, its commands in backticks, or one command a thread runs, in
    backticks. A command that runs dry (`DRY`) walks through none."""
    if DRY.search(command):
        return ()
    found = []
    for case, runs in _RUNS:
        matched = runs.search(command)
        if matched is None:
            continue
        span = next(
            (one for one in _SPAN.finditer(command) if one.start() <= matched.start() < one.end()),
            None,
        )
        found.append((case, (span.group(0) if span else matched.group(0)).strip("`").strip()))
    return tuple(found)


def walked(brief: str) -> tuple[tuple[str, str], ...]:
    """The doors the commands of a brief's `Done when:` and `Proves it:` lines walk through, in
    the table's order, each with the first command that does. The lines are read in segments,
    split at a semicolon, a line's end, and a comma before "and" or "then"; a segment that says
    the command is not run (`ASIDE`) walks through none."""
    lines = [line for label, lines in briefs.fields(brief) if label in WALKED for line in lines]
    first: dict[str, str] = {}
    for segment in _SEGMENT.split("\n".join(lines)):
        if ASIDE.search(segment):
            continue
        for case, command in walks(segment):
            first.setdefault(case, command)
    return tuple((case, first[case]) for case in CASES if case in first)


def doors(brief: str) -> tuple[str, ...]:
    """The cases a brief holds for, in the table's order: those its head's `Holds: <case>` lines
    name (`held`), as `jbriefs.parse.fields` reads the head, and those its commands walk through
    (`walked`), whether or not a `Holds:` line names them."""
    named, run = set(declared(brief)), {case for case, _ in walked(brief)}
    return tuple(case for case in CASES if case in named or case in run)


def declared(brief: str) -> tuple[str, ...]:
    """The cases a brief's head names on `Holds:` lines (`held`), as `jbriefs.parse.fields` reads
    the head."""
    return held(*(" ".join(lines) for label, lines in briefs.fields(brief) if label == "Holds"))


def undeclared(brief: str) -> tuple[tuple[str, str], ...]:
    """The doors a brief's commands walk through (`walked`) that no `Holds:` line of its names,
    each with the command, which `jbus queue add` names so the home can write the line."""
    named = declared(brief)
    return tuple((case, command) for case, command in walked(brief) if case not in named)
