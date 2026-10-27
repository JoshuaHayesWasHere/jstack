"""A `Pass` is one pass of jbus over one project, and `jbus done` is the verb that sends a result
through one at once.

A finding goes out through the project's `Box` (`jbus.wake`), once per key. What no rule covers is a
`condition`, a quiet event that asks the user nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import jbus
from jbus import Config, Project, queue, read_json, verbs
from jbus.wake import COMMAND_TIMEOUT, Box

if TYPE_CHECKING:
    from jbus.watch import World

CONDITION = "condition"

EVENTS = {"condition": "quiet"}


@dataclass(frozen=True)
class Changed:
    """A `Changed` is a brief that changed after its approval. It holds the first 12
    characters of the brief's sha now, the first 12 of the sha the go was given for, and the
    lines of the brief that the go does not cover (`queue.changed`)."""

    sha: str
    was: str = ""
    lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class Depends:
    """A `Depends` is a row that waits for slugs that are not merged."""

    slugs: tuple[str, ...]


@dataclass(frozen=True)
class Slot:
    """A `Slot` is a row that waits only for a slot or room on the machine."""


Reason = Changed | Depends | Slot


@dataclass
class Pass:
    """A `Pass` is one pass over one project, with the state that all its steps share.

    `find` sends a finding, once per key. What no rule covers is a `condition`, a quiet event that
    asks the user nothing. `gate` records a condition for a slug, and the rest of the pass leaves
    the slug alone: the slug is in `gated`, its row is at `gate`, and `asked` keeps what the
    condition is. `held` is the rows where a full pass held back the gate. `reasons` holds why each
    approved row was not launched. `dispatch` records that reason once it has judged the row.

    A slug that `jbus queue remove` took out is gone for good: each time a caller asks,
    `removed` reads the names from `removed.json`, and `find` sends nothing for one of them.
    If a pull request for such a slug opens later, every step still treats it as a pull
    request.

    `told` is the threads this pass sent a message that needs `act` (`jbus.outbox`), each id in
    T3 Code's `mcp:` form: each waits on its thread, not on the user, and the outbox sends it no
    second such message this pass.
    `limited` is the slugs whose last run ended on a usage limit (`jbus.failover`). The pass sends
    their threads no carry-on, since the failover sends one. `world` is what the pass saw of T3
    Code and GitHub, once it has looked (`watch.look`), or None before then or where it could not
    look.
    """

    config: Config
    project: Project
    now: datetime
    say: Callable[[str], None] = print
    gated: set[str] = field(default_factory=set)
    reasons: dict[str, Reason] = field(default_factory=dict)
    asked: dict[str, str] = field(default_factory=dict)
    held: set[str] = field(default_factory=set)
    told: set[str] = field(default_factory=set)
    limited: set[str] = field(default_factory=set)
    world: World | None = None

    def __post_init__(self) -> None:
        self.state = self.config.state(self.project)
        self.home = self.config.home(self.project)
        self.box = Box(self.state, self.project, self.config.webhook, self.config.blocking)
        self.first = not read_json(self.state / "wake.json", {}).get("began")
        self.user = self.config.user
        self.day = self.user.day(self.now)

    def run(
        self, *command: str, timeout: float = COMMAND_TIMEOUT
    ) -> subprocess.CompletedProcess[str]:
        """Run a command in the project's main checkout. A command that is missing, or that
        runs past `timeout` seconds, fails like any other. `JMERGE_TIMEOUT` is jmerge's: above
        the fresh check's own limit and below the unit's TimeoutStartSec
        (`features/jbus/tests/test_jbus.py`)."""
        try:
            return subprocess.run(
                command, cwd=self.project.checkout, capture_output=True, text=True, timeout=timeout
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return subprocess.CompletedProcess(command, 127, "", str(error))

    @property
    def removed(self) -> frozenset[str]:
        return queue.removed_slugs(self.state)

    def find(
        self, slug: str, kind: str, line: str, text: str = "", *, key: str = "", past: bool = False
    ) -> bool:
        """Send a finding once. On a project's first pass, `find` only records a finding about
        the past. It only records a finding about a removed slug, and never sends it."""
        key = f"{kind}|{slug}|{key or line}"
        if slug in self.removed:
            self.box.mark(key)
            return False
        if past and self.first:
            self.box.mark(key)
            return False
        return self.box.send(slug, kind, line, text, key=key)

    def condition(self, slug: str, what: str, text: str = "", *, key: str = "") -> bool:
        """Record what jbus found that no rule covers, once. Return True if it was new."""
        return self.find(slug, CONDITION, f"{CONDITION} {slug}: {what}", text, key=key)

    def gate(self, slug: str, what: str, text: str = "", *, key: str = "") -> None:
        self.gated.add(slug)
        self.asked[slug] = what
        self.condition(slug, what, text, key=key)


def _done(args: argparse.Namespace, config: Config) -> int:
    """Run `jbus done`: a thread with no home gives its result here, and jbus sends it at once."""
    project = verbs.here(config, args.project)
    run = Pass(config, project, datetime.now(UTC))
    text = sys.stdin.read().strip()
    if not text:
        raise jbus.Refused("refused: no lines on stdin")
    line = f"result {args.slug}: {text.splitlines()[0]}"
    new = run.find(args.slug, "result", line, text, key=f"piped {queue.sha(text)[:16]}")
    print("queued" if new else "already sent")
    return 0


def _slug(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("slug")


VERBS = (verbs.Verb("done", "send a result now, its lines on stdin", _slug, _done),)
