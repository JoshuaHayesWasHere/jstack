"""`jbus home <brief-or-request>`: print the thread of the home that a brief or a scout's
request belongs to.

The file is `<state>/tasks/<slug>.md` or `<state>/scouts/<slug>.md`, and its state is the directory
two levels above it. The command reads the `home-id` of the home of the brief or request now, and
prints the thread that the `home-id` names. It prints nothing where that home has no thread: between
a handoff and the next start, or in a repo with no home. With `--directory` it prints the home's
directory instead, and a home compares that directory with its own. A file that does not exist names
no home, so the command counts it as the root home's. The rule is `jbriefs.home`, which the
skills, jbus and `jmerge` share.

`jbus home status --home <directory>` prints where things stand for that home, at its start, and
with `--gates` what the home skill's blocks of "Gates" read (`jbus.homestatus`). It asks whose
each row, merge and Result is in one process, not one each.

`jbus home was --home <directory>` looks for the last thread that was that home, as the home's start
does last, and settles it if it is not settled: an archived home settles itself, and a settle clears
its pin, but a turn cut off leaves it active and pinned. The last home is the thread on the
`Was home:` line of the directory's last note, the one an older handoff left as `handoff.md`, or
else the newest in its `log/`. One whose id is in the directory's `home-id` is this home, and is
left as it is.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import jbus
from jbriefs import home
from jbriefs.home import thread_of
from jbus import homestatus, t3, verbs

STATUS = "status"
WAS = "was"
NOTED = re.compile(r"^Was home:[ \t]*(\S*)", re.M)


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "brief",
        nargs="?",
        default="",
        help="the brief or the request, <state>/tasks/<slug>.md, or status or was",
    )
    parser.add_argument(
        "--directory", action="store_true", help="print the home's directory, not its thread"
    )
    parser.add_argument(
        "--home",
        metavar="DIRECTORY",
        help="with status or was: the home's directory, $M of the skill",
    )
    parser.add_argument(
        "--gates", action="store_true", help="with status: print what the blocks of Gates read"
    )
    parser.add_argument(
        "--no-jbus", action="store_true", help="with status: jbus is not installed on the machine"
    )


def _directory(brief: Path) -> Path:
    try:
        text = brief.read_text(errors="replace")
    except OSError:
        text = ""
    return home.home_of(brief.parent.parent, text)


def was_home(directory: Path) -> str:
    """Return the id of the last thread that was the home of `directory`, or "" where no note
    names one."""
    found = ""
    for note in [*sorted((directory / "log").glob("*.md")), directory / "handoff.md"]:
        try:
            noted = NOTED.search(note.read_text(errors="replace"))
        except OSError:
            continue
        if noted:
            found = noted.group(1)
    return found


def _settle_was(directory: Path) -> str:
    """Settle the last home of `directory` where it is not settled, and say what was done."""
    was = was_home(directory)
    try:
        me = (directory / "home-id").read_text(errors="replace").split()[:1]
    except OSError:
        me = []
    if not was:
        return (
            f"no home before this one: no note of {directory} names one, so no thread is looked for"
        )
    if [was] == me:
        return f"no home before this one: {was}, the last home the notes name, is this home"
    config = jbus.load()
    client = t3.Client(config.server, config.token_path)
    try:
        thread = client.call("t3_thread_read", {"threadId": was, "limit": 1}).get("thread") or {}
        if thread.get("settled") or thread.get("archived"):
            return f"settled: {was} is settled, and a settle clears its pin"
        client.call("t3_thread_organize", {"action": "settle", "threadId": was})
    except t3.T3Error as error:
        if isinstance(error, t3.T3Refused) and t3.GONE.search(str(error)):
            return f"not found: T3 Code has no thread {was}, so nothing is settled"
        raise jbus.Refused(f"refused: T3 Code did not settle {was}: {error}") from error
    return (
        f"settled now: {was}, the home before this one, was still active and may have been pinned"
    )


def _run(args: argparse.Namespace, _: jbus.Config) -> int:
    if args.brief == WAS:
        if not args.home:
            raise jbus.Refused("refused: was needs --home, the home's directory: set M first")
        print(_settle_was(Path(args.home)))
        return 0
    if args.brief == STATUS:
        if not args.home:
            raise jbus.Refused("refused: status needs --home, the home's directory: set M first")
        for line in homestatus.run(args.home, not args.no_jbus, args.gates):
            print(line)
        return 0
    if not args.brief.strip():
        raise jbus.Refused("refused: no brief, set B to <state>/tasks/<slug>.md and run it again")
    found = _directory(Path(args.brief))
    said = str(found) if args.directory else thread_of(found)
    if said:
        print(said)
    return 0


VERBS = (
    verbs.Verb(
        "home", "print the thread of a brief's home, or nothing", _arguments, _run, config=False
    ),
)
