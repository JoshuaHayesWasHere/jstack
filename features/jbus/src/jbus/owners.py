"""A fault an agent can fix goes to that agent, once: the user is never its owner.

The view's list of what is wrong (`jbus.view.state.wrongs`) names each entry's owner by the rule
of its kind (`state.OWNERS`): the crew of its row, the home of its row, the root home, or the
user where no agent can fix it. `tell` reads the project as the view reads it, at the end of
each pass, and sends the home that owns an entry it was not told of one message through the
outbox, which needs it to act. The message's key is `state.key_of`, the same while the cause
stands, so a home is told once of a fault, and again only of a new one or as a new home.

Told here are a fault with no row, one of the project or the machine, which the root home
owns, and two faults of a row that no other step tells a home of: a crew of the root home's
that hung at work, which `jbus.stall.hung` only logs, and a stalled row, whose `stall` event
`jbus.stall.guarded`, `jbus.expedite` and `jbus.clock` only log, which its home owns. A child
home hears of its own hung crew from `jbus.children`, whose nudge counts all it has out. A
crew that is only quiet is not told of. Any other fault of a row is told by the step that
already works that row, and the view reads its message as what the owner was told
(`state._fixing`). A crew owns a red check of its own pull request, which `jbus.rebase` tells
it of, and a red main whose main-red row it works. A crew whose thread ended with something
left goes to its home through `jbus.leftover`, whose record counts as the telling. A user's
entry is told to nobody: the band shows it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from jbus import outbox, verbs
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.threads import ROLES
from jbus.view import state
from jbus.view.github import RUNS, shaped
from jbus.watch import _api

if TYPE_CHECKING:
    from jbus.cli import Half

KIND = "wrong"
CREW = next(role for role in ROLES if role.name == "crew")
MESSAGE = (
    "jbus: {what} is wrong in {project}, and it is this home's to fix. {user} is not asked: it "
    "waits on this home.\n\n"
    "{kind} {subj}: {cause}{since}.{row}\n\n"
    "Fix it, or hand it to the thread whose work it is. A question only {user} can answer is a "
    "gate: take the default and pipe it to `jbus gate <slug>`. Send {user} nothing about it. jbus "
    "tells this home once while the cause stands, and draws it in the view as fixing by this home."
)


@dataclass(frozen=True)
class _Sources(state.Sources):
    """The view's sources of one project of a pass, whose home may have another name."""

    own: Path = Path()

    def home(self, name: str) -> Path:
        return self.own


def read(run: Pass) -> state.Read:
    """The project as the view reads it now. Its repo's runs are asked of GitHub in its checkout,
    as each call of the pass asks, so a repo the view has no `jmerge` line of is known too."""

    def runs(repo: str) -> dict:
        return shaped(_api(run, f"repos/{{owner}}/{{repo}}/actions/runs?per_page={RUNS}"), run.now)

    sources = _Sources(run.state.parent, run.home.parent, user=run.user, own=run.home)
    found = state.Read(sources, run.project.name, run.now, runs)
    found.where = found.where or "{owner}/{repo}"
    return found


def message(run: Pass, one: dict) -> str:
    """The one message a home gets about a fault it owns."""
    row = (
        f" It is the row {one['row']}, whose brief is `tasks/{one['row']}.md`."
        if one["row"]
        else ""
    )
    since = (
        f", since {run.user.stamp(datetime.fromisoformat(one['since']))}" if one["since"] else ""
    )
    return MESSAGE.format(
        what=f"the {one['kind']} {one['subj']}",
        project=run.project.name,
        user=run.user.user,
        kind=one["kind"],
        subj=one["subj"],
        cause=one["cause"],
        since=since,
        row=row,
    )


def _hung(one: dict) -> bool:
    """Whether the entry is a crew whose turn hung and whose row no step works, which only this
    step tells the root home of. The crew of a queued row is told of by `jbus.watch.unwritten`,
    whose leftover counts as the telling, a home's own thread is no crew, and a crew a child
    home owns is left to `jbus.children`, whose nudge to that home counts all it has out."""
    hung = one["cause"].startswith(state.QUIET_OR_HUNG["hung"])
    crew = one["subj"].startswith(CREW.prefix) and one["owner"] == state.ROOT_HOME
    return one["kind"] == "thread" and hung and crew


def _logged(one: dict) -> bool:
    """Whether the entry is a fault of a row that the step that found it only logged, which
    only this step tells: a hung crew (`_hung`), or a stalled row."""
    return _hung(one) or one["kind"] == state.STALLED


def tell(run: Pass, client: Client) -> None:
    """Tell the owner, once, of each fault of the project or the machine, each hung crew and
    each stalled row."""
    for one in read(run).once(state.wrongs):
        fault = f"{one['kind']} {one['subj']}"
        if one["owner"] == state.USER or one["fixing"] or (one["row"] and not _logged(one)):
            continue
        key = state.key_of(one)
        try:
            went = outbox.send(
                run,
                client,
                thread=one["to"],
                row=one["row"] or run.project.name,
                key=key,
                text=message(run, one),
                template=KIND,
                needs="act",
            )
        except T3Error as error:
            run.say(
                f"wait {run.project.name}: {one['owner']} could not be told of {fault} ({error})"
            )
            continue
        if went:
            to = f"{one['owner']}, thread {one['to']}"
            run.say(f"{KIND} {run.project.name}: told {to}, of {fault}")


def _tell(half: Half) -> None:
    tell(half.run, half.client)


STEPS = (
    verbs.Step("after-derive", 45, "owners.tell", _tell, ("sight", "client", "world", "budget")),
)
