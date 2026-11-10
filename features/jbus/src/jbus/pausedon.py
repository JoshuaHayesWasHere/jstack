"""`tell` tells a crew that paused on other rows to carry on, once, when the last of them landed.

A crew whose task cannot go on until other rows merge writes its Result with `Status: paused` and
one line naming those rows, `Paused on: <slug> <slug>` (the crew skill's Result template). Each
pass reads the last Result of each queued row (`World.result`), and where it is paused and every
row its `Paused on:` line names has landed, sends the row's crew one message to carry on, under the
key `paused-on|<slug>|<the rows, sorted>`, marked in `sent.json` once T3 Code took it. A row lands
by the rule `dispatch` launches a depending row on (`watch.final`): its pull request merged, or it
ended `done` with none. A line with a word that is no slug of the queue, a typo or a slug with
a full stop on it, waits on nothing: jbus sends no carry-on for it, rather than one for the rows
that did parse before the one the crew meant merged. `watch.look` asks GitHub after each slug a
paused Result names, as it asks after a row's depends, so a merge older than GitHub's list of the
last merges still counts.

The message goes to the crew alone and is no event: no home is woken for it, since the home's own
nudge is what it replaces. It needs `act`, so the outbox holds it while the crew's turn runs or
its thread waits on a slot, and the key stays unsent until a pass sends it. A thread archived, a
row gated, or a Result that no longer says `paused` is told nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jbriefs.home import thread_of
from jbus import dispatch, mirror, outbox, queue, verbs, watch
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.threads import resume_message

if TYPE_CHECKING:
    from jbus.watch import World

TEMPLATE = "paused-on"
CARRY_ON = (
    "jbus: {rows} landed, the rows the `Paused on:` line of your last Result names, so the "
    "pause is over: carry on. Read `tasks/{slug}.md` and its last Result first, bring your "
    "branch onto origin/main, do what its `Left:` line names, and end with a follow-up Result "
    "that has another status. jbus says this once."
)


def tell(run: Pass, client: Client, world: World, rows: list[queue.Row]) -> None:
    """Tell each paused crew whose rows have all landed to carry on, once: see the module."""
    slugs = {row["slug"] for row in rows}
    landed = watch.final(run, world, rows)
    for slug in sorted(slugs - run.gated - set(world.archived)):
        named = mirror.paused_on(world.result(run, slug), slugs)
        if not named or not set(named) <= landed:
            continue
        key = "|".join([TEMPLATE, slug, *named])
        at = thread_of(run.home, slug) or dispatch.launched(run, slug)
        if not at or run.box.has(key):
            continue
        message = resume_message(
            CARRY_ON, f"crew: {slug}", run.home, rows=", ".join(named), slug=slug
        )
        try:
            went = outbox.send(
                run,
                client,
                thread=at,
                row=slug,
                key=key,
                text=message,
                template=TEMPLATE,
                needs="act",
            )
        except T3Error as error:
            run.say(f"wait {slug}: its crew could not be told to carry on ({error})")
            continue
        if went:
            run.box.mark(key)
            run.say(f"told {slug}: {', '.join(named)} landed, the rows it paused on")


STEPS = (
    verbs.Step(
        "tellers",
        72,
        "pausedon.tell",
        lambda half: tell(half.run, half.client, half.seen.world, half.rows or []),
        ("client", "world"),
    ),
)
