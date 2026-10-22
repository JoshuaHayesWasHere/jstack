"""`jbus home <brief-or-request>`: print the thread of the home that a brief or a scout's
request belongs to.

The file is `<state>/tasks/<slug>.md` or `<state>/scouts/<slug>.md`, and its state is the directory
two levels above it. The command reads the `home-id` of the file's home now and prints the thread in
that file. It prints nothing where that home has no thread: between a handoff and the next start, or
in a repo with no home. With `--directory` it prints the home's directory instead, and a home
compares that directory with its own. A file that does not exist names no home, so the command
counts it as the root home's. The rule is `jbriefs.home`, which the skills, jbus and `jmerge` share.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import jbus
from jbriefs import home
from jbus import verbs


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("brief", help="the brief or the request, <state>/tasks/<slug>.md")
    parser.add_argument(
        "--directory", action="store_true", help="print the home's directory, not its thread"
    )


def _run(args: argparse.Namespace, _: jbus.Config) -> int:
    if not args.brief.strip():
        raise jbus.Refused("refused: no brief, set B to <state>/tasks/<slug>.md and run it again")
    brief = Path(args.brief)
    try:
        text = brief.read_text(errors="replace")
    except OSError:
        text = ""
    found = home.home_of(brief.parent.parent, text)
    said = str(found) if args.directory else home.thread_of(found)
    if said:
        print(said)
    return 0


VERBS = (
    verbs.Verb(
        "home", "print the thread of a brief's home, or nothing", _arguments, _run, config=False
    ),
)
