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
"""

from __future__ import annotations

import argparse
from pathlib import Path

import jbus
from jbriefs import home
from jbriefs.home import thread_of
from jbus import homestatus, verbs

STATUS = "status"


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "brief",
        nargs="?",
        default="",
        help="the brief or the request, <state>/tasks/<slug>.md, or status",
    )
    parser.add_argument(
        "--directory", action="store_true", help="print the home's directory, not its thread"
    )
    parser.add_argument(
        "--home", metavar="DIRECTORY", help="with status: the home's directory, $M of the skill"
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


def _run(args: argparse.Namespace, _: jbus.Config) -> int:
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
