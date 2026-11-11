"""What `jmerge` asks of jbus, and nothing more: the project of a checkout (its state directory,
its migrations and its generated files), the queue's rows and stored briefs there, whether a row is
over, and the act of
an accept. jmerge imports nothing of jbus: jbus fills this in (`jbus.port.Port`) and names it
under the entry point group `GROUP`, which `found` reads.

Where jbus has no project of the checkout, `jmerge` runs as it does in a repo with no jbus: no
queue, no migrations, `uv.lock` the one generated file, and an accept on `--by` and `--at` alone.
Where no package fills the port in, as in an install from before it, `found` refuses: the queue
reads as unreadable, so nothing merges, and an accept is refused, since no go and no door can be
read.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Protocol

import jsettings
from jbriefs.meets import Waiver

GROUP = "jmerge.bus"

Row = dict[str, Any]


@dataclass(frozen=True)
class Migrations:
    directory: str
    numbered: bool


@dataclass(frozen=True)
class Place:
    """The project of a checkout as jbus's config has it. `bases` names each branch besides the
    default one that `jmerge` merges into, on the default branch's rules."""

    state: Path
    migrations: Migrations | None
    generated: tuple[str, ...]
    bases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Acting:
    """Who accepts, on what: `said_at` is when the evidence was said, and `kept` is what the bus
    keeps for the act. `ref` is the message the bus read, as `<thread id>/<message id>`, where
    `--message` named one, a `<thread id>/last` resolved to the message it named."""

    said_at: str
    kept: object
    ref: str = ""


class Bus(Protocol):
    def place(self, checkout: Path) -> Place | None:
        """The project whose main checkout is `checkout`, or None where jbus has no config file
        or no project of it. Raise `jsettings.Refused` where the config file is there and does
        not load, so a caller fails closed."""

    def rows(self, state: Path) -> list[Row] | None:
        """The queue's rows, or None where its files are there and do not read."""

    def over(self, row: Row) -> bool:
        """Whether a row of the queue is over (`jbus.work.over`): jbus alone decides it, and a
        row once over stays so."""

    def stored(self, state: Path, slug: str) -> str | None:
        """The brief of `slug` as jbus stores it, the text its go is judged against."""

    def heard(self, checkout: Path, waiver: Waiver, slug: str) -> str:
        """Why the word a `Waived:` line rests on, `jbriefs.meets.Waiver`, does not waive its
        `Done when` line of the row `slug`, or nothing where it does: it is the user's own message
        in T3 Code, read now by the check `jbus queue approve --message` reads a word with, or a
        word the bot gave over `POST /act`, and its words name the slug, say they waive, and quote
        the line (`meets.quotes`). A home's or a crew's own message, a word a home typed for the
        bot, and a word about the row that waives nothing waive nothing."""

    def acting(
        self, checkout: Path, message: str | None, at: str | None, as_: str, user: Any
    ) -> Acting | None:
        """Who accepts, on what evidence, in the project of `checkout`, or None where jbus has
        no project of it. Raise `jsettings.Refused` for a config that does not load, a message
        that is not the user's own, and `--as user` on typed words."""

    def accept(
        self,
        acting: Acting,
        number: int,
        slug: str,
        head: str,
        brief: str,
        protected: bool,
        does: Callable[[], str],
    ) -> tuple[str, str]:
        """Take the accept of pull request `number` of the row `slug` at `head` as an act, which
        `does` carries out where the party may open each door the brief and a protected path
        name. Return its outcome, `done`, `gated` or `refused`, and its line."""


@functools.cache
def found() -> Bus:
    """The bus a package names under `GROUP`. Raise `jsettings.Refused` where none does."""
    for point in entry_points(group=GROUP):
        return point.load()()
    raise jsettings.Refused(f"no package names a bus under {GROUP}: reinstall jstack")


def place(checkout: Path) -> Place | None:
    """`Bus.place` of the bus there is."""
    return found().place(checkout)


def over(row: Row) -> bool:
    """`Bus.over` of the bus there is."""
    return found().over(row)


def quiet_place(checkout: Path) -> Place | None:
    """`place`, with a config that does not load read as no project."""
    try:
        return place(checkout)
    except jsettings.Refused:
        return None
