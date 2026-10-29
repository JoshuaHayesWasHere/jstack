"""jbus's side of `jmerge.bus`: what `jmerge` asks of jbus, answered from jbus's config, its
queue and its acts. jmerge imports nothing of jbus; the entry point `jmerge.bus` names `Port`.

`jmerge --accept` is an act of jbus's (`jbus.acts`). The accept of a held pull request lifts its
hold and merges it, which is the user's alone where it opens a door: the brief's `Holds:` lines,
and "changes access or secrets" for a pull request that touches a protected path
(`protected.txt`). The accept goes through `acts.act` with the party of `--as` and the evidence of
`--message` (the user's own message, which jbus reads from T3 Code) or of `--by` and `--at`
(typed, which opens no door). A door that the party may not open parks a gate for the user and
merges nothing. Every accept, whatever came of it, is one line of the project's `acts.jsonl`.

A checkout that is no project of jbus's has no `acts.jsonl` and no gates: there the accept runs
on `--by` and `--at` alone, as it did before acts, and nothing logs it. `--check` is no accept
and records nothing.
"""

from __future__ import annotations

import types
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import jbus
import jsettings
from jbus import Refused, acts, party, queue, t3
from jbus.passes import Pass
from jmerge import bus

ACCESS = "changes access or secrets"


@dataclass(frozen=True)
class Acting:
    """Who accepts, on what, in which project of jbus's."""

    run: Pass
    who: party.Party
    said: party.Evidence


def project(checkout: Path) -> tuple[jbus.Config, jbus.Project] | None:
    """jbus's config and its project of this checkout, or None where jbus has no config file or
    no project of it. Raise `jbus.Refused` where the config file is there and does not load, so a
    caller fails closed."""
    try:
        config = jbus.load()
    except jbus.Refused:
        if (jbus.config_dir() / "config.toml").exists():
            raise
        return None
    found = next(
        (one for one in config.projects if one.checkout.resolve() == checkout.resolve()), None
    )
    return None if found is None else (config, found)


def doors(brief: str, protected: bool) -> tuple[str, ...]:
    """The cases an accept holds for: the brief's, and a protected path's, in the table's order."""
    named = set(party.doors(brief)) | ({ACCESS} if protected else set())
    return tuple(case for case in party.CASES if case in named)


class Port:
    """`jmerge.bus.Bus`, from jbus's config, queue and acts."""

    def place(self, checkout: Path) -> bus.Place | None:
        found = project(checkout)
        if found is None:
            return None
        config, one = found
        numbered = one.migration_names == jbus.NUMBERED
        migrations = bus.Migrations(one.migrations, numbered) if one.migrations else None
        return bus.Place(config.state(one), migrations, tuple(one.generated), one.merge_bases)

    def rows(self, state: Path) -> list[bus.Row] | None:
        try:
            return queue.load(state)
        except (queue.Unparsable, OSError):
            return None

    def stored(self, state: Path, slug: str) -> str | None:
        return queue.brief(state, slug)

    def acting(
        self,
        checkout: Path,
        message: str | None,
        at: str | None,
        as_: str,
        user: jsettings.Settings,
    ) -> bus.Acting | None:
        found = project(checkout)
        if found is None:
            return None
        config, one = found
        run = Pass(config, one, datetime.now(UTC), say=lambda _: None)
        if message:
            heard = t3.heard(config, message)
            said = party.Evidence(
                "t3-message", message, heard.words, heard.said_at, heard.said_in, heard.checked
            )
        else:
            said = party.Evidence("typed", "", f"accept, by {user.user}", at or "")
        who = acts.cli_party(types.SimpleNamespace(as_=as_), said)
        return bus.Acting(said.said_at, Acting(run, who, said))

    def accept(
        self,
        acting: bus.Acting,
        number: int,
        slug: str,
        head: str,
        brief: str,
        protected: bool,
        does: Callable[[], str],
    ) -> tuple[str, str]:
        kept = acting.kept
        assert isinstance(kept, Acting)
        held = doors(brief, protected)
        user = kept.run.user.user
        parked = acts.Parked(
            question=f"may jmerge merge pull request {number} of {slug}? It holds for "
            f"{', '.join(held)}",
            default=f"pull request {number} stays held at {head[:12]}, and nothing merges",
            given=f"{user}'s own message, read by jbus: jmerge --accept {number} --as user "
            "--message <thread id>/<message id>",
            fail_safe=f"the hold of pull request {number} at {head[:12]}, as jmerge keeps it",
        )
        action = party.Action("accept", slug, head[:12], doors=held)
        try:
            made = acts.act(kept.run, kept.who, action, kept.said, does=does, parked=parked)
        except Refused as error:
            return "refused", str(error)
        return made.outcome, made.line
