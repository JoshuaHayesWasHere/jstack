"""`jbus home <brief-or-request>`: the thread of the home a brief or a scout's request is.

The file is `<state>/tasks/<slug>.md` or `<state>/scouts/<slug>.md`, and its state is the
directory two above it. It prints the thread in the `home-id` of the file's home, read now,
or nothing where that home has none: between a handoff and the next start, or in a repo with
no home. With `--directory` it prints the home's directory in its place, which a home holds
up to its own. A file that is not there names no home and is the root's. The rule is
`jbriefs.home`, the one the skills, jbus and `jmerge` share.
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
