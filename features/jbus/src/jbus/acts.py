"""`act`: the one way a party acts on jbus's state, and the log of every act, `acts.jsonl`.

The command line's `jbus queue approve` and `jbus answer`, and the bot's route, `POST /act` on
jbus view, each call `act` with the `party.Party` that acts, the `party.Action` and the
`party.Evidence` it rests on. `act` checks the action, does it through the existing verb
(`queue.go`, `questions.answer`), and appends one `party.Act` line to the project's
`acts.jsonl`, whatever came of it. Each act is also a quiet `act` event of the project's log, with
the act's id and its `subject`, so the feed (`jbus.cursor`) gives events and acts in one order:

- A go given with `seen`, the id of the last event the party read (`wake.entries`, the feed's
  cursor), is refused as stale when `events.jsonl` has an event for the row after that one, or
  has no event of that id. An `act` event names no row, so an act is no change to the row.
- A go for a brief whose `Holds:` lines name a door (`party.doors`), from a party the door
  does not open for (`party.opens`), approves nothing. It parks a gate that holds for the user
  instead (`questions.park`), and the act is `gated`. The user's own go later closes that gate.
- A go whose row's go already holds for that brief is a `noop`.
- An answer to a gate that holds, from a party the door does not open for, is `refused`, and
  the gate stays open.

Every other verb (`party.Verb`) is given by its caller as `does`, which does the verb and returns
its line, or raises `Refused`: `queue hold`, `remove` and `withdraw`, a word, the view's go of a
work item, and `jmerge --accept`. `act` checks it as it checks a go, the event `seen` and the
doors the caller found, and a door the party may not open parks the gate `parked` names and does
nothing (`gated`). Only an accept has doors: the brief's `Holds:` lines and a protected path.

Acts are taken one at a time, under `acts.lock`: `queue.lock` and `questions.lock` are taken by
the verbs themselves, and an act holds them only through those verbs. A `does` runs outside
`acts.lock`, so a merge does not hold every other act back, and it never takes an act itself:
`locked` takes a lock a second time in one process by waiting on it forever.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsettings
from jbus import (
    Config,
    Refused,
    locked,
    party,
    questions,
    queue,
    read_json,
    verbs,
    wake,
    write_json,
)
from jbus.party import Act, Action, Evidence, Party
from jbus.passes import Pass
from jbus.t3 import typed

LOG = "acts.jsonl"
LOCK = "acts.lock"
KIND = "act"
EVENTS = {"act": "quiet"}
BOT_KEY_SESSION = (
    "refused: jbus bot key runs in an agent's session: the bot's key is the user's to make, "
    "in a shell of their own, and the stored key is as it was"
)
KEY = "bot-key.json"
GO_OPTIONS = {
    "t3-message": "message",
    "t3-pick": "pick",
    "lavish-page": "page",
    "typed": "word",
    "answer": "answer",
}
"""The option of `jbus queue approve` that each source `--evidence` may spell is."""
GO_GATE = "may {slug} go? Its brief holds for {case}"
_GO_GATE_HOLDS = "keeps the go of {slug}, whose brief holds for {cases}"
UNCHECKED_USER = (
    "refused: --as user acts on the user's own words that jbus reads itself, --message "
    "<thread>/<message> or --page <session>/<entry>, and this act has {source} words"
)


def path(state: Path) -> Path:
    return state / LOG


def read(state: Path) -> list[dict[str, Any]]:
    """Every act of the project, oldest first."""
    try:
        text = path(state).read_text()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _write(state: Path, made: Act) -> None:
    line = json.dumps(asdict(made), sort_keys=True) + "\n"
    handle = os.open(path(state), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(handle, line.encode())
    finally:
        os.close(handle)


@dataclass(frozen=True)
class Parked:
    """The gate a verb given as `does` waits on when its door does not open for the party: the
    question, what happens on no answer, how the user gives the word that does it, and what is
    kept."""

    question: str
    default: str
    given: str
    fail_safe: str


def act(
    run: Pass,
    who: Party,
    action: Action,
    said: Evidence,
    *,
    does: Callable[[], str] | None = None,
    parked: Parked | None = None,
    asks: queue.Asks | None = None,
    follows: str = "",
    keeps: bool = False,
    where: str = "",
    ran_by: dict[str, str] | None = None,
    id: str = "",
) -> Act:
    """Take one act and log it. Return the act; a refused one raises `Refused` with its line,
    once it is logged. `follows` is the parent of a go by the follow-up rule, `keeps` says an
    answer is the default, and `where` is where an answer was given. A go needs `asks`, which
    `queue.go` takes. Any verb but a go and an answer is done by `does`, and one with doors
    names the gate it parks, `parked`. `id` is the act's own id where the verb keeps one (a
    word's), else the hash of the act."""
    if action.verb not in ("go", "answer"):
        return _done(run, who, action, said, does, parked, id)
    with locked(run.state, LOCK):
        if action.verb == "go":
            action, outcome, line, gate = _go(run, asks, who, action, said, follows, ran_by)
        else:
            action, outcome, line, gate = _answer(run, who, action, said, keeps, where)
        made = logged(run, who, action, said, outcome, line, gate)
    if outcome == "refused":
        raise Refused(line)
    return made


def _done(
    run: Pass,
    who: Party,
    action: Action,
    said: Evidence,
    does: Callable[[], str] | None,
    parked: Parked | None,
    id: str,
) -> Act:
    """Take an act whose verb `does` does: refused when stale, gated on a door the party may not
    open, else done or refused by the verb itself, which runs with no lock of this module's."""
    with locked(run.state, LOCK):
        stale = _stale(run, action.subject, action.seen)
        if stale or does is None:
            line = stale or f"refused: {action.verb} was given nothing to do it with"
            logged(run, who, action, said, "refused", line, id=id)
            raise Refused(line)
        if action.doors and not party.opens(who, said):
            if parked is None:
                line = f"refused: {action.verb} {action.subject} holds and names no gate"
                logged(run, who, action, said, "refused", line, id=id)
                raise Refused(line)
            number = _parked(run, who, action, said, parked)
            line = (
                f"gated {action.verb} {action.subject}: it holds for {', '.join(action.doors)}, "
                f"so it waits for {run.user.user}'s own word: question {number}"
            )
            return logged(run, who, action, said, "gated", line, number, id=id)
    try:
        line, outcome = does(), "done"
    except Refused as error:
        line, outcome = str(error), "refused"
    with locked(run.state, LOCK):
        made = logged(run, who, action, said, outcome, line, id=id)  # type: ignore[arg-type]
    if outcome == "refused":
        raise Refused(line)
    return made


def logged(
    run: Pass,
    who: Party,
    action: Action,
    said: Evidence,
    outcome: party.Outcome,
    line: str,
    gate: int | None = None,
    *,
    id: str = "",
) -> Act:
    """Append one act to the log, as it came out, and return it. The caller holds the lock, or
    logs what a batch did (`queue apply`). `id` is the act's own id where the verb keeps one,
    else the hash of the act."""
    at = jsettings.stamp(run.now)
    body = {"at": at, "party": asdict(who), "action": asdict(action), "line": line}
    body["evidence"] = asdict(said)
    made = Act(
        id=id or hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16],
        at=at,
        party=who,
        action=action,
        evidence=said,
        outcome=outcome,
        line=line,
        gate=gate,
    )
    _write(run.state, made)
    run.box.record(KIND, line, act=made.id, subject=action.subject)
    return made


Done = tuple[Action, party.Outcome, str, int | None]


def _go(
    run: Pass,
    asks: queue.Asks | None,
    who: Party,
    action: Action,
    said: Evidence,
    follows: str,
    ran_by: dict[str, str] | None,
) -> Done:
    slug = action.subject
    if asks is None:
        return action, "refused", "refused: a go was given nothing to read the queue with", None
    stale = _stale(run, slug, action.seen)
    if stale:
        return action, "refused", stale, None
    _, text = queue.current(run.state, slug)
    action = replace(action, doors=party.doors(text or ""))
    if action.doors and not party.opens(who, said):
        number = _park(run, who, action, said)
        line = (
            f"gated {slug}: its brief holds for {', '.join(action.doors)}, so it waits for "
            f"{run.user.user}'s own word: question {number}"
        )
        return action, "gated", line, number
    try:
        said_lines = queue.go(run.state, slug, said, follows, action.pre, run.user, asks, ran_by)
    except Refused as error:
        return action, "refused", str(error), None
    if said_lines[0].startswith(queue.ALREADY):
        return action, "noop", said_lines[0], None
    if action.doors:
        for one in questions.read(run.state):
            if one.slug == slug and one.question.startswith(f"may {slug} go?"):
                questions.clear(run, one.number, f"{run.user.user} gave the go")
    return action, "done", "\n".join(said_lines), None


def _answer(run: Pass, who: Party, action: Action, said: Evidence, keeps: bool, where: str) -> Done:
    try:
        number = int(action.subject)
    except ValueError:
        return action, "refused", f"refused: {action.subject} is not a question's number", None
    asked = questions.question(run.state, number)
    if asked is not None and asked.holds:
        action = replace(action, doors=(asked.holds,))
    elif asked is not None and keeps and questions.go_gate(asked):
        _, text = queue.current(run.state, asked.slug)
        action = replace(action, doors=party.doors(text or ""))
    if action.doors and not party.opens(who, said):
        why = (
            f"holds ({asked.holds})"
            if asked and asked.holds
            else _GO_GATE_HOLDS.format(
                slug=asked.slug if asked else "", cases=", ".join(action.doors)
            )
        )
        line = (
            f"refused: question {number} {why}: only {run.user.user}'s own word, read in T3 "
            "Code or on a Lavish page, answers it, so it stays open"
        )
        return action, "refused", line, number
    try:
        closed, went = questions.answer(
            run.state, number, party=who, evidence=said, where=where, keeps=keeps, user=run.user
        )
    except Refused as error:
        return action, "refused", str(error), number
    given = closed.answer
    assert given is not None
    if went:
        carried = f"nothing is sent, and {went}"
    elif given.keeps and not closed.holds:
        carried = "nothing is sent"
    elif questions.thread_of(run.home, closed.slug):
        carried = f"the next pass tells {closed.slug}'s thread"
    else:
        carried = f"{closed.slug} has no Thread: line in a brief or request, so no thread is told"
    return action, "done", f"answered: question {number}: {given.line()}: {carried}", number


def _stale(run: Pass, slug: str, seen: str) -> str:
    """Why a go given after the event `seen` is stale, or nothing: the log has no event of that
    id (`wake.entries`), or has an event for the row after it."""
    if not seen:
        return ""
    log = wake.entries(run.state)
    at = next((place for place, one in enumerate(log) if one["id"] == seen), None)
    if at is None:
        return f"refused: stale: no event {seen} in {run.project.name}'s log"
    later = [one for one in log[at + 1 :] if one.get("slug") == slug]
    if later:
        return (
            f"refused: stale: {slug} changed after event {seen}, in event {later[-1]['id']} "
            f"({later[-1].get('line')})"
        )
    return ""


def _park(run: Pass, who: Party, action: Action, said: Evidence) -> int:
    """Park the gate a go on a door waits on, and return its number. A gate holds for one case,
    so it names the first, and its context names the rest."""
    slug, user = action.subject, run.user.user
    case, *rest = action.doors
    also = f"; it holds for {', '.join(rest)} too" if rest else ""
    lines = "\n".join(
        (
            f"## Gate <n>: {GO_GATE.format(slug=slug, case=case)}",
            "Status: open",
            f"Asked by: {slug}, by the {who.kind}'s go",
            f"Default: {slug} waits, with no go and no launch",
            "Built on it: nothing, since no thread launched",
            f"Undo: nothing to undo; {user} gives the go in T3 Code, and jbus --as user queue "
            f"approve {slug} --sha {action.pre} --message <thread>/<message> records it",
            f"Holds: {case}",
            f"Fail-safe: the brief, stored at {queue.brief_path(run.state, slug)}, unlaunched",
            f"Context: the {who.kind} gave the go on {said.source} {said.ref}, and a door "
            f"opens only on {user}'s own word that jbus reads in T3 Code or on a Lavish page{also}",
            f"Option: wait (default, recommended): {slug} stays unlaunched",
            f"Option: go: {user} gives the go in T3 Code, and the next pass launches it",
        )
    )
    one, _ = questions.park(run, slug, lines)
    return one.number


def _parked(run: Pass, who: Party, action: Action, said: Evidence, parked: Parked) -> int:
    """Park the gate a verb on a door waits on, as `_park` does a go's, and return its number."""
    case, *rest = action.doors
    also = f"; it holds for {', '.join(rest)} too" if rest else ""
    user = run.user.user
    lines = "\n".join(
        (
            f"## Gate <n>: {parked.question}",
            "Status: open",
            f"Asked by: {action.subject}, by the {who.kind}'s {action.verb}",
            f"Default: {parked.default}",
            f"Built on it: nothing, since the {action.verb} was not done",
            f"Undo: nothing to undo; {parked.given}",
            f"Holds: {case}",
            f"Fail-safe: {parked.fail_safe}",
            f"Context: the {who.kind} acted on {said.source} {said.ref or said.words}, and a "
            f"door opens only on {user}'s own word that jbus reads in T3 Code or on a Lavish "
            f"page{also}",
            f"Option: wait (default, recommended): {parked.default}",
            f"Option: {action.verb}: {parked.given}",
        )
    )
    one, _ = questions.park(run, action.subject, lines)
    return one.number


def is_bot(state_dir: Path, authorization: str) -> bool:
    """Whether a request is the bot's: its `Authorization` header is `Bearer <key>`, and the
    key's sha256 is the one `jbus bot key` kept in jbus's state. This is the one test of who
    the bot is. jbus keeps no key, only its hash, so nobody who reads the state can act as the
    bot, and no address is trusted: the bot's site passes its requests on from loopback, where
    any process of this machine can call too."""
    kept = read_json(state_dir / KEY, {}).get("sha256", "")
    scheme, _, key = authorization.partition(" ")
    if not isinstance(kept, str) or not kept or scheme != "Bearer" or not key.strip():
        return False
    return hmac.compare_digest(hashlib.sha256(key.strip().encode()).hexdigest(), kept)


def new_key(state_dir: Path, now: datetime) -> str:
    """Make the bot a new key, keep its hash in place of the old one, and return the key. Only
    this call ever sees it."""
    key = secrets.token_urlsafe(32)
    digest = hashlib.sha256(key.encode()).hexdigest()
    write_json(state_dir / KEY, {"sha256": digest, "made_at": jsettings.stamp(now)}, mode=0o600)
    return key


def _bot(args: argparse.Namespace, config: Config) -> int:
    if os.environ.get(queue.SESSION):
        raise Refused(BOT_KEY_SESSION)
    key = new_key(config.state_dir, datetime.now(UTC))
    print(key)
    print(
        "the bot's new key, shown this once: give it to the bot, which sends it as "
        "Authorization: Bearer <key> to POST /act; the old key no longer works",
        file=sys.stderr,
    )
    return 0


def _bot_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_subparsers(dest="verb", required=True).add_parser(
        "key", help="make the bot a new key, print it once, and keep only its hash"
    )


def cli_party(args: argparse.Namespace, said: Evidence) -> Party:
    """The party the command line acts as: `--as`, a home by default. The bot is no party of
    the command line, and the user acts on words jbus reads itself."""
    kind = getattr(args, "as_", None) or "home"
    if kind not in party.CLI_PARTIES:
        raise Refused(party.CLI_BOT.format(party=kind))
    if kind == "user" and not said.checked:
        raise Refused(UNCHECKED_USER.format(source=said.source))
    return Party(kind, "cli")  # type: ignore[arg-type]


def read_evidence(asks: queue.Asks, given: Evidence) -> Evidence:
    """Read the words that unread evidence names, by `asks.said`, as the approve of a batch
    reads them. Evidence by rule names no words."""
    if given.source == "rule" or asks.said is None:
        return given
    heard = asks.said(given.basis, given.ref)
    return replace(
        given,
        words=heard.words,
        said_at=heard.said_at,
        said_in=heard.said_in,
        checked=heard.checked,
        picks=heard.picks,
    )


def given_evidence(args: argparse.Namespace, names: dict[str, str]) -> dict[str, str]:
    """Fold a global `--evidence <source>:<ref>` into the basis option it spells, by `names`,
    the option of each source the verb takes."""
    spelled = getattr(args, "evidence", None)
    if not spelled:
        return {}
    try:
        given = party.evidence(spelled)
    except ValueError as error:
        raise Refused(f"refused: --{error}") from None
    if given.source not in names:
        takes = ", ".join(names)
        raise Refused(f"refused: --evidence {given.source} is not one this verb takes: {takes}")
    return {names[given.source]: given.ref}


def go(args: argparse.Namespace, run: Pass, asks: queue.Asks) -> Act:
    """`jbus queue approve` as an act: the evidence its basis names, read now, and the party of
    `--as`."""
    given = vars(args) | given_evidence(args, GO_OPTIONS)
    unread, follows = queue.basis(given)
    said = read_evidence(asks, unread)
    who = cli_party(args, said)
    action = Action("go", args.slug, args.sha, args.seen or "")
    return act(run, who, action, said, asks=asks, follows=follows)


OWN = {"t3-message": "message", "lavish-page": "page"}
"""The options of the user's own words, which jbus reads itself, that a verb on a row takes."""
REMOVE_BY = (
    "refused: only {user} removes a row, on their own words: --by {user}, or --message "
    "<thread>/<message> or --page <session>/<entry>, not {by}; a home takes out a row of its own "
    "that never launched with jbus queue withdraw"
)
REMOVE_WORDS = (
    "refused: remove takes the user's own words, one of --message <thread>/<message>, --page "
    "<session>/<entry>, or --by <user> with --at"
)


def own(args: argparse.Namespace, asks: queue.Asks, words: str, run: Pass) -> Evidence:
    """The evidence a verb on a row rests on: the user's words that `--evidence` names, read now,
    or else the command's own words, typed now by whoever runs it."""
    given = given_evidence(args, OWN)
    if given:
        ((name, ref),) = given.items()
        return read_evidence(asks, Evidence(party.SOURCE[name], ref))  # type: ignore[arg-type]
    return Evidence("typed", "", words, run.user.stamp(run.now))


def hold(args: argparse.Namespace, run: Pass, asks: queue.Asks) -> Act:
    """`jbus queue hold` as an act: no door, so any party holds a row."""
    said = own(args, asks, f"hold {args.slug}", run)
    who = cli_party(args, said)
    held = Action("hold", args.slug)
    return act(run, who, held, said, does=lambda: queue.hold(run.state, args.slug))


def withdraw(args: argparse.Namespace, run: Pass, asks: queue.Asks) -> Act:
    """`jbus queue withdraw` as an act, its words the reason it gives."""
    said = own(args, asks, args.why, run)
    who = cli_party(args, said)
    at, by = run.user.stamp(queue.clock()), queue.who(queue.runner())
    slug = args.slug
    return act(
        run,
        who,
        Action("withdraw", slug),
        said,
        does=lambda: queue.withdraw(run.state, slug, args.why, at, by, asks),
    )


def remove(args: argparse.Namespace, run: Pass, asks: queue.Asks) -> Act:
    """`jbus queue remove` as an act: on the user's message or page, read now, or on the words
    typed with `--by` and `--at`. Only the user's own words remove a row, and the act of any
    other `--by` is refused and logged."""
    given = vars(args) | given_evidence(args, OWN)
    named = [name for name in OWN.values() if given.get(name)]
    typed = given.get("by") is not None or given.get("at") is not None
    if len(named) + typed != 1:
        raise Refused(REMOVE_WORDS)
    slug, user = args.slug, run.user.user
    if named:
        (name,) = named
        source = next(one for one, option in OWN.items() if option == name)
        said = read_evidence(asks, Evidence(source, given[name]))  # type: ignore[arg-type]
        by, at = user, said.said_at
    else:
        by, at = given.get("by") or "", given.get("at") or ""
        said = Evidence("typed", "", f"remove {slug}", at)
    who = cli_party(args, said)

    def does() -> str:
        if by != user:
            raise Refused(REMOVE_BY.format(user=user, by=by or "nobody"))
        if not said.checked:
            verbs.typed_at(run.user, at)
        return queue.remove(run.state, slug, by, at, asks)

    return act(run, who, Action("remove", slug), said, does=does)


def batch(run: Pass, asks: queue.Asks, args: argparse.Namespace, text: str) -> list[str]:
    """`jbus queue apply` with its approve lines as acts: a go on a brief that holds, the one
    stored or one the batch adds, is refused in a batch, since its door is checked by
    `jbus queue approve` alone, and so is a remove that is not on the user's own words. Each
    go, hold and remove the batch made is logged once the batch is done."""
    kind = getattr(args, "as_", None) or "home"
    if kind != "home":
        raise Refused(f"refused: --as {kind}: a batch acts as the home, and nothing was applied")
    lines = [verb for _, verb in queue.parse(text)]
    gos = [verb for verb in lines if isinstance(verb, queue.Approve)]
    for verb in gos:
        briefs = [queue.brief(run.state, verb.slug) or ""]
        briefs += [
            one.text for one in lines if isinstance(one, queue.Add) and one.slug == verb.slug
        ]
        held = tuple(dict.fromkeys(door for one in briefs for door in party.doors(one)))
        if held:
            raise Refused(
                f"refused: approve {verb.slug} in a batch: its brief holds for "
                f"{', '.join(held)}, so its go goes by jbus queue approve alone, and nothing in "
                "the batch was applied"
            )
    for verb in lines:
        if isinstance(verb, queue.Remove):
            if verb.by != run.user.user:
                said = REMOVE_BY.format(user=run.user.user, by=verb.by).removeprefix("refused: ")
                raise Refused(
                    f"refused: remove {verb.slug} in a batch: {said}, and nothing in the batch "
                    "was applied"
                )
            verbs.typed_at(run.user, verb.at)
    with locked(run.state, LOCK):
        said = queue.apply(run.state, text, run.user, asks)
        for verb in lines:
            if isinstance(verb, queue.Approve):
                source = party.SOURCE[verb.basis]
                done = f"approved {verb.slug}:"
                action, evidence = Action("go", verb.slug, verb.given), Evidence(source, verb.ref)  # type: ignore[arg-type]
            elif isinstance(verb, queue.Hold):
                done = f"held {verb.slug}"
                action = Action("hold", verb.slug)
                evidence = Evidence("typed", "", f"hold {verb.slug}", run.user.stamp(run.now))
            elif isinstance(verb, queue.Remove):
                done = f"removed {verb.slug}:"
                action = Action("remove", verb.slug)
                evidence = Evidence("typed", "", f"remove {verb.slug}", verb.at)
            else:
                continue
            line = next((one for one in said if one.startswith(done)), "")
            logged(run, party.HOME, action, evidence, "done", line)
    return said


def _answer_verb(args: argparse.Namespace, config: Config) -> int:
    """`jbus answer`: close a question with the user's words, from wherever the user
    answered, as an act."""
    project = verbs.here(config, args.project)
    message = given_evidence(args, {"t3-message": "message"}).get("message")
    if message is not None:
        args.message = message
    heard = typed(args, config, "answer")
    if heard is None:
        if args.by != config.user.user:
            raise Refused(f"refused: only {config.user.user} answers a question, not {args.by}")
        verbs.typed_at(config.user, args.at)
        said = Evidence("typed", "", " ".join(args.words), args.at, "", False)
    else:
        said = Evidence("t3-message", heard.ref, heard.words, heard.said_at, heard.said_in, True)
    who = cli_party(args, said)
    run = Pass(config, project, datetime.now(UTC))
    made = act(
        run,
        who,
        Action("answer", str(args.number)),
        said,
        keeps=args.keeps,
        where=str(Path.cwd()),
    )
    print(made.line)
    return 0


VERBS = (
    verbs.Verb(
        "answer",
        "close a question with the user's answer",
        questions.closes,
        _answer_verb,
        abbrev=False,
    ),
    verbs.Verb("bot", "the bot's key: jbus bot key makes a new one", _bot_arguments, _bot),
)
