"""`jmerge --accept` as an act of jbus's (`jbus.acts`).

The accept of a held pull request lifts its hold and merges it, which is the user's alone where
it opens a door: the brief's `Holds:` lines, and "changes access or secrets" for a pull request
that touches a protected path (`protected.txt`). jmerge takes the accept through `acts.act`
with the party of `--as` and the evidence of `--message` (the user's own message, which jbus
reads from T3 Code) or of `--by` and `--at` (typed, which opens no door). A door that the
party may not open parks a gate for the user and merges nothing. Every accept, whatever came of
it, is one line of the project's `acts.jsonl`.

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

import jsettings
from jbus import Refused, acts, party, t3
from jbus.passes import Pass
from jmerge import rows

ACCESS = "changes access or secrets"


@dataclass(frozen=True)
class Acting:
    """Who accepts, on what, in which project of jbus's."""

    run: Pass
    who: party.Party
    said: party.Evidence


def acting(
    checkout: Path, message: str | None, at: str | None, as_: str, user: jsettings.Settings
) -> Acting | None:
    """The party and the evidence of an accept, in the jbus project of `checkout`, or None where
    jbus has no project for it. Refuse a config that does not load, a message that is not the
    user's own, and `--as user` on typed words."""
    found = rows.project(checkout)
    if found is None:
        return None
    config, project = found
    run = Pass(config, project, datetime.now(UTC), say=lambda _: None)
    if message:
        heard = t3.heard(config, message)
        said = party.Evidence(
            "t3-message", message, heard.words, heard.said_at, heard.said_in, heard.checked
        )
    else:
        said = party.Evidence("typed", "", f"accept, by {user.user}", at or "")
    return Acting(run, acts.cli_party(types.SimpleNamespace(as_=as_), said), said)


def doors(brief: str, protected: bool) -> tuple[str, ...]:
    """The cases an accept holds for: the brief's, and a protected path's, in the table's order."""
    named = set(party.doors(brief)) | ({ACCESS} if protected else set())
    return tuple(case for case in party.CASES if case in named)


def accept(
    acting: Acting,
    number: int,
    slug: str,
    head: str,
    held: tuple[str, ...],
    does: Callable[[], str],
) -> tuple[party.Outcome, str]:
    """Take the accept of pull request `number` of the row `slug` at `head` as an act. Return its
    outcome and its line: `done` where `does` merged it, `gated` where a door parked a gate, and
    `refused` where the act or the merge refused it."""
    user = acting.run.user.user
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
        made = acts.act(acting.run, acting.who, action, acting.said, does=does, parked=parked)
    except Refused as error:
        return "refused", str(error)
    return made.outcome, made.line
