"""`jbus feed`: what changed in a project since a party's cursor, for the bot that polls.

The page, its shape, its cursor and its long poll are `jbus.cursor`'s, below the view that serves
the same page, and this module is the verb that prints it.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

from jbus import Config, Refused, verbs
from jbus.cursor import START as START
from jbus.cursor import WAIT_MOST, seconds, wait


def _feed(args: argparse.Namespace, config: Config) -> int:
    """Print the page after `--after`, as one JSON object."""
    from jbus.view import state as view
    from jbus.view.github import GitHub

    try:
        waits = seconds(args.wait)
    except ValueError as error:
        raise Refused(f"refused: --{error}") from None
    project = verbs.project(config, args.project)
    sources = view.Sources(config.state_dir, config.home_dir, user=config.user)
    runs = GitHub(lambda: datetime.now(UTC)).runs

    def needs() -> list[dict[str, Any]]:
        return view.needs(sources, project.name, datetime.now(UTC), runs)

    page = wait(config.state(project), project.name, args.after, waits, needs)
    print(json.dumps(page, sort_keys=True))
    return 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--after", default="", help="the id of the last event you read")
    parser.add_argument(
        "--wait",
        default="0",
        help=f"wait up to this many seconds for a new event, {WAIT_MOST} at most",
    )


VERBS = (
    verbs.Verb(
        "feed",
        "what changed since a cursor, JSON: events and acts, or a reset with what waits",
        _arguments,
        _feed,
        abbrev=False,
    ),
)
