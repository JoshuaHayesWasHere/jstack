"""`jbus standing`: a home's standing word for follow-ups, which approves them as they are queued.

The user tells a home once that the briefs it queues need no go of theirs, as "when new briefs
need my approval, approve them". The home kept that message as a word (`jbus word`), and
`jbus standing --to <project> --word <id>` makes it the standing word of the home the word is for:
its scope, or the root home, whose standing word stands for every home of the project. From then
a follow-up of that home (its brief names a parent on a `Follows:` line) that the follow-up rule
does not approve, and whose brief holds no case of gates.md, is approved on the word in the same
`jbus queue add` that queued it (`queue._standing_for`), and its approved column names the word.
A row with a `Holds:` line, or a command that opens a door, still waits for the user's own word,
and so does a row with no `Follows:` line. A hold is never lifted by it.

Only a word jbus read from the user's own message in T3 Code stands: a word from the bot's chat,
or one whose time was typed, is refused, since a standing word approves rows nobody names.

The word is an act (`jbus.acts`) whose verb is `standing`, whose subject is the home's scope, whose
evidence is the word (its id as `ref`), and whose action's `pre` says it stands or is withdrawn
(`queue.STAND`, `queue.WITHDRAW`); its line says the same to a person. The last such act of a
scope is what the home holds (`queue.standing_words`). `--withdraw` with the same word ends it,
and a second run of either changes nothing. `jbus needs` names each home's standing word while it
holds.

`--covers goes` makes the root home's word its standing word for goes instead: the root gives a
plan entry its go on it (`jbus plan go <entry> --standing --from <root id>`, `jbus.plan`), where
it would otherwise ask the user for one. Only a word said in the root's own thread stands for
goes: a word said in a thread that is no home's is the root home's too, and stands for none. Its
act's subject is `goes:` (`queue.standing_subject`), and its withdrawal ends each go the root gave
on it.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from jbriefs.home import thread_of
from jbus import Config, Refused, acts, locked, party, queue, verbs, word
from jbus.passes import Pass

NOT_OWN = (
    "refused: word {id} is not the user's own message that jbus read in T3 Code, and only such "
    "a word stands for follow-ups"
)


def name(scope: str) -> str:
    """The home of a scope as a line names it: the root home's scope is empty."""
    return scope or "root"


def _standing(args: argparse.Namespace, config: Config) -> int:
    """Make the word the standing word for follow-ups of the home it is for, or withdraw it."""
    project = config.addressee(args.to)
    run = Pass(config, project, datetime.now(UTC), lambda _: None)
    kept = next((one for one in word.load(run.state) if one.id == args.word), None)
    if kept is None:
        raise Refused(f"refused: {acts.path(run.state)} has no word {args.word}")
    if not kept.checked or not kept.ref or kept.said_in.startswith(queue.BOT_CHAT):
        raise Refused(NOT_OWN.format(id=kept.id))
    root = thread_of(run.home)
    if args.covers == queue.GOES and (not root or kept.ref.partition("/")[0] != root):
        raise Refused(
            f"refused: word {kept.id} was not said in the root's thread, and only a word said "
            "there stands for goes"
        )
    home = name(kept.home)
    said = party.Evidence("typed", kept.id, kept.words, kept.at, kept.said_in, True)
    who = acts.cli_party(args, said)
    stands, withdrawn = LINES[args.covers]
    with locked(run.state, acts.LOCK):
        held = queue.standing_words(run.state, args.covers).get(kept.home)
        holds = held is not None and held[0] == kept.id
        if args.withdraw:
            pre, line = (
                queue.WITHDRAW,
                withdrawn.format(project=project.name, home=home, id=kept.id),
            )
            if not holds:
                print(
                    f"refused: the {home} home of {project.name} holds no standing word {kept.id}"
                )
                return 1
        else:
            pre, line = queue.STAND, stands.format(project=project.name, home=home, id=kept.id)
            if holds:
                print(line)
                return 0
        subject = queue.standing_subject(kept.home, args.covers)
        acts.logged(run, who, party.Action(queue.STANDING, subject, pre), said, "done", line)
    print(line)
    return 0


LINES = {
    queue.FOLLOW_UPS: (
        "standing: {project}, the {home} home approves its follow-ups that open no door on word "
        "{id}",
        "withdrawn: {project}, the {home} home's standing word {id} approves nothing more",
    ),
    queue.GOES: (
        "standing: {project}, the root gives a plan entry its go on word {id}",
        "withdrawn: {project}, the root's standing word {id} for goes gives no more go",
    ),
}
"""What `jbus standing` prints when a word for each of `queue.COVERS` stands, and when it is
withdrawn."""


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--to", metavar="PROJECT", required=True, help="the project of the home")
    parser.add_argument(
        "--word",
        required=True,
        metavar="ID",
        help="a kept word of the user's own message: it stands for the home it is for",
    )
    parser.add_argument(
        "--covers",
        choices=queue.COVERS,
        default=queue.FOLLOW_UPS,
        help="what the word stands for: the home's follow-ups (the default), or goes, the root's "
        "go for a plan entry (jbus plan go <entry> --standing), which only the root's word gives",
    )
    parser.add_argument(
        "--withdraw", action="store_true", help="end the home's standing word, which --word names"
    )


VERBS = (
    verbs.Verb(
        "standing",
        "a home's standing word, which approves its follow-ups that open no door as they are "
        "queued, or with --covers goes lets the root give a plan entry its go, or --withdraw to "
        "end it",
        _arguments,
        _standing,
    ),
)
