"""`tell` tells a crew that paused on other rows to carry on, once, when the last of them landed.

A crew whose task cannot go on until other rows merge writes its Result with `Status: paused` and
one line naming those rows, `Waits on: <slug> <slug>` (the crew skill's Result template). Each
pass reads the last Result of each queued row (`World.result`), and where it is paused and every
row its `Waits on:` line names has landed, sends the row's crew one message to carry on, under the
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

That carry-on is the live case: the crew's thread is listed and not settled (`live`). A row whose
thread T3 Code settled or archived is `left`, and `jbus.dispatch` launches it again on its own
branch and worktree once a cause it waits on clears (`cleared`), so no carry-on goes to a thread
that has ended. The causes, each read from the state, are a table (`CAUSES`):

- `waits`: its paused Result's `Waits on:` rows all landed, as above;
- `review`: a `## Review` with findings was written after its last Result, at a head, so the
  findings came after its thread ended;
- `brief`: its brief was approved again: the row's `brief_sha` is not the go its newest crew
  launch was made under, the record's `go`. A record written before launches kept `go` has none
  to compare, and is no cause.

A gate's answer is not one: `questions.carry` sends it to the thread on the brief's `Thread:`
line, which a resume moves to the new thread (`dispatch.write_thread`).

Each cause is acted on once (`spent`): a resume writes its key into its launch record as `cause`
(`jbus.launches`), and the live carry-on marks its own key in `sent.json`. The `waits` key of a
resume holds the Result it was read from, so a resumed crew that pauses again on the same rows is
a new cause, and one that ends with its old Result still last is not.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jbriefs import findings
from jbriefs.home import thread_of
from jbus import mirror, queue, verbs, watch
from jbus.launches import records
from jbus.passes import Pass
from jbus.t3 import Client, T3Error

if TYPE_CHECKING:
    from jbus.watch import World

TEMPLATE = "paused-on"
CARRY_ON = (
    "jbus: {rows} landed, the rows the `Waits on:` line of your last Result names, so the "
    "pause is over: carry on. Read `tasks/{slug}.md` and its last Result first, bring your "
    "branch onto origin/main, do what its `Left:` line names, and end with a follow-up Result "
    "that has another status. jbus says this once."
)


@dataclass(frozen=True)
class Cause:
    """A cause a left row waited on that has cleared: its once-key, and the point the resumed
    crew carries on from, as the brief's `Resume:` line names it."""

    key: str
    says: str


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def live(world: World, slug: str) -> bool:
    """Say whether the slug's crew thread is listed and not settled: the case `tell` carries on in
    place. Otherwise a left row is `dispatch`'s to launch again."""
    return bool(world.threads.get(slug))


def spent(run: Pass, slug: str, key: str) -> bool:
    """Say whether a cause was acted on: a launch of the row's crew holds it as its `cause`, or
    the live carry-on was sent under it."""
    return run.box.has(key) or any(
        one.get("cause") == key for _, one in records(run, slug, queue.CREW)
    )


def _waits(
    run: Pass, world: World, row: queue.Row, slugs: set[str], landed: frozenset[str]
) -> Cause | None:
    slug = row["slug"]
    result = world.result(run, slug)
    named = mirror.paused_on(result, slugs)
    if not named or not set(named) <= landed:
        return None
    carried = "|".join([TEMPLATE, slug, *named])
    if run.box.has(carried):
        return None
    rows = ", ".join(named)
    return Cause(f"{carried}|{digest(result)}", f"{rows} landed, the rows its `Waits on:` names")


def _review(
    run: Pass, world: World, row: queue.Row, slugs: set[str], landed: frozenset[str]
) -> Cause | None:
    slug = row["slug"]
    brief = watch.brief_of(run, slug)
    lines = brief.splitlines()
    last = max((at for at, one in enumerate(lines) if one.startswith("## Result")), default=-1)
    after = [
        one
        for one in findings.triage(brief).sections
        if one.line > last and one.ran and one.head and one.verdict.startswith("findings")
    ]
    if not after:
        return None
    head = after[-1].head
    says = f"the findings of the review at {head[:12]}, written after its last Result"
    return Cause(f"review|{slug}|{head[:12]}", says)


def _brief(
    run: Pass, world: World, row: queue.Row, slugs: set[str], landed: frozenset[str]
) -> Cause | None:
    slug, sha = row["slug"], str(row.get("brief_sha") or "")[:12]
    made = records(run, slug, queue.CREW)
    newest = max(made, key=lambda one: str(one[1].get("at") or ""), default=None)
    under = str((newest[1] if newest else {}).get("go") or "")[:12]
    if not row.get("approved") or not sha or not under or under == sha:
        return None
    return Cause(f"brief|{slug}|{sha}", f"its brief as it was approved again, at {sha}")


CAUSES = (_waits, _review, _brief)


def cleared(
    run: Pass, world: World, row: queue.Row, slugs: set[str], landed: frozenset[str]
) -> Cause | None:
    """Return the first cause of a left row that cleared and was not acted on (`spent`), or None.
    `slugs` are the queue's rows and `landed` those that merged or ended done (`watch.final`)."""
    for read in CAUSES:
        cause = read(run, world, row, slugs, landed)
        if cause and not spent(run, row["slug"], cause.key):
            return cause
    return None


def waits_on(run: Pass, world: World, slug: str, slugs: set[str]) -> tuple[str, ...]:
    """Return the rows the last Result of a row names on its `Waits on:` line, as its home is
    told what the row waits on."""
    return mirror.paused_on(world.result(run, slug), slugs)


def tell(run: Pass, client: Client, world: World, rows: list[queue.Row]) -> None:
    """Tell each paused crew whose rows have all landed to carry on, once, while its thread is
    `live`: see the module. `jbus.dispatch` reads the causes here, and `outbox` and `threads`
    import it, so they are imported here and not above."""
    from jbus import outbox
    from jbus.threads import resume_message

    slugs = {row["slug"] for row in rows}
    landed = watch.final(run, world, rows)
    for slug in sorted(slugs - run.gated - set(world.archived)):
        if not live(world, slug):
            continue
        result = world.result(run, slug)
        named = mirror.paused_on(result, slugs)
        if not named or not set(named) <= landed:
            continue
        key = "|".join([TEMPLATE, slug, *named])
        at = thread_of(run.home, slug) or str(world.threads[slug][0].get("threadId") or "")
        if not at or run.box.has(key) or spent(run, slug, f"{key}|{digest(result)}"):
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
            run.say(f"told {slug}: {', '.join(named)} landed, the rows it waits on")


STEPS = (
    verbs.Step(
        "tellers",
        72,
        "pausedon.tell",
        lambda half: tell(half.run, half.client, half.seen.world, half.rows or []),
        ("client", "world"),
    ),
)
