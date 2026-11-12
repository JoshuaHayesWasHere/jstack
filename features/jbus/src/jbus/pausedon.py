"""`tell` tells a crew whose Result waits on merges to carry on, once, when the last of them landed.

A crew whose task waits on other work merging, a row's or a pull request's, writes one line in its
Result naming each, `Waits on: <slug> #<n>` (the crew skill's Result template), at any status: a
paused task waits to go on, and one with a pull request open waits to rebase. Each pass reads the
last Result of each queued row (`World.result`), and where every name on its `Waits on:` line has
landed (`watch.final`), sends the row's crew one message to carry on, under the key
`waits|<slug>|<the names, sorted>|<the Result>` (`key`), marked in `sent.json` once T3 Code took it.
A slug lands by the rule `dispatch` launches a depending row on: its pull request merged, or it
ended `done` with none. A number lands when GitHub says that pull request merged, which
`watch.look` asks after each number a Result names, as it asks after a row's depends, so a merge
older than GitHub's list of the last merges still counts. A line with a word that is neither, a
typo or a slug with a full stop on it, waits on nothing: jbus sends no carry-on for it, rather
than one for the names that did parse before the one the crew meant merged. The carry-on does not
read the row's head: a crew told to rebase at one head, that put it off until another pull request
merged, is told again by this line, where the once-per-head rebase key (`jbus.rebase`) is spent.

The message goes to the crew alone and is no event: no home is woken for it, since the home's own
nudge is what it replaces. It needs `act`, so the outbox holds it while the crew's turn runs or
its thread waits on a slot, and the key stays unsent until the first idle pass sends it. A thread
archived, a row gated, or a Result whose `Waits on:` line is gone is told nothing.

That carry-on is the live case: the crew's thread is listed and not settled (`live`). A row whose
thread T3 Code settled is `left`, and `jbus.dispatch` launches it again on its own branch and
worktree once a cause it waits on clears (`cleared`), so no carry-on goes to a thread that has
ended. A row whose thread T3 Code archived is launched again by nobody, as `tell` carries it on to
nobody: the thread was put away. The causes, each read from the state, are a table (`CAUSES`):

- `waits`: its last Result's `Waits on:` names all landed, as above;
- `review`: a `## Review` with findings was written after its last Result, at a head, so the
  findings came after its thread ended;
- `brief`: its brief was approved again: the row's `brief_sha` is not the go its newest crew
  launch was made under, the record's `go`. A record written before launches kept `go` has none
  to compare, and is no cause.

A gate's answer is not one: `questions.carry` sends it to the thread on the brief's `Thread:`
line, which a resume moves to the new thread (`crewthread.move`).

Each cause is acted on once (`spent`): a resume writes its key into its launch record as `cause`
(`jbus.launches`), and the live carry-on marks its own key in `sent.json`. The `waits` key holds
the Result it was read from (`ident`): which Result of the brief it is, its heading, and its
`Status:` and `Waits on:` lines. So a crew that writes a new Result waiting on the same names is a
new cause, and one that adds a single line to its last Result (`Checked:`, `Rebased:`) is not. A
key written before this one, `paused-on|<slug>|<rows>` in `sent.json` or with the whole Result's
digest after it as a launch's cause, is spent too, so no crew told then is told again; the first
holds no Result, and so stands for every later Result of that row on those rows.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jbriefs import below, findings
from jbriefs.home import thread_of
from jbus import mirror, queue, verbs, watch
from jbus.launches import records
from jbus.passes import Pass
from jbus.t3 import Client, T3Error

if TYPE_CHECKING:
    from jbus.watch import World

TEMPLATE = "waits"
LEGACY = "paused-on"
CARRY_ON = (
    "jbus: {rows} landed, what the `Waits on:` line of your last Result names, so the wait is "
    "over: carry on. Read `tasks/{slug}.md` and its last Result first, bring your branch onto "
    "origin/main, and do what its `Steers:` and `Left:` lines say waited on it: with a pull "
    "request open, push the rebased branch to it. A paused task ends with a follow-up Result that "
    "has another status, and a Result you write now names no landed work on a `Waits on:` line. "
    "jbus says this once."
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


def spent(run: Pass, slug: str, key: str, *legacy: str) -> bool:
    """Say whether a cause was acted on: a launch of the row's crew holds it, or one of the
    `legacy` keys it had before, as its `cause`, or the live carry-on was sent under it."""
    keys = {key, *legacy}
    return any(run.box.has(one) for one in keys) or any(
        one.get("cause") in keys for _, one in records(run, slug, queue.CREW)
    )


def ident(run: Pass, slug: str, result: str) -> str:
    """Which Result of the slug's brief `result` is, as the `waits` key holds it: a digest of how
    many Results the brief has, the Result's heading, and its `Status:` and `Waits on:` lines."""
    lines = result.splitlines()
    brief = watch.brief_of(run, slug).splitlines()
    count = sum(1 for one in brief if one.startswith("## Result"))
    said = [str(count), lines[0] if lines else ""]
    said += [below.line(result, label) for label in ("Status:", mirror.WAITS_ON)]
    return digest("\n".join(said))


def key(run: Pass, slug: str, result: str, named: tuple[str, ...]) -> str:
    """The once-key of a `waits` carry-on or resume: `waits|<slug>|<names>|<ident>`."""
    return "|".join([TEMPLATE, slug, ",".join(named), ident(run, slug, result)])


def _legacy(slug: str, result: str, named: tuple[str, ...]) -> tuple[str, str]:
    """The keys a `waits` cause had before it read numbers: the live carry-on's, and a resume's."""
    sent = "|".join([LEGACY, slug, *named])
    return sent, f"{sent}|{digest(result)}"


def landed_waits(
    run: Pass, world: World, slug: str, slugs: set[str], landed: frozenset[str]
) -> tuple[tuple[str, ...], str] | None:
    """The names the slug's last Result waits on and its `waits` key, where every name landed
    and no carry-on or resume was made for that Result yet, or None."""
    result = world.result(run, slug)
    named = mirror.waits_on(result, slugs)
    if not named or not set(named) <= landed:
        return None
    made = key(run, slug, result, named)
    return None if spent(run, slug, made, *_legacy(slug, result, named)) else (named, made)


def _waits(
    run: Pass, world: World, row: queue.Row, slugs: set[str], landed: frozenset[str]
) -> Cause | None:
    found = landed_waits(run, world, row["slug"], slugs, landed)
    if found is None:
        return None
    named, made = found
    return Cause(made, f"{', '.join(named)} landed, what its `Waits on:` names")


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
    """Return what the last Result of a row names on its `Waits on:` line, rows and pull
    requests, as its home is told what the row waits on."""
    return mirror.waits_on(world.result(run, slug), slugs)


def tell(run: Pass, client: Client, world: World, rows: list[queue.Row]) -> None:
    """Tell each crew whose waits have all landed to carry on, once, while its thread is `live`:
    see the module. `jbus.dispatch` reads the causes here, and `outbox` and `threads` import it,
    so they are imported here and not above."""
    from jbus import outbox
    from jbus.threads import resume_message

    slugs = {row["slug"] for row in rows}
    landed = watch.final(run, world, rows)
    for slug in sorted(slugs - run.gated - set(world.archived)):
        if not live(world, slug):
            continue
        found = landed_waits(run, world, slug, slugs, landed)
        at = thread_of(run.home, slug) or str(world.threads[slug][0].get("threadId") or "")
        if found is None or not at:
            continue
        named, made = found
        message = resume_message(
            CARRY_ON, f"crew: {slug}", run.home, rows=", ".join(named), slug=slug
        )
        try:
            went = outbox.send(
                run,
                client,
                thread=at,
                row=slug,
                key=made,
                text=message,
                template=TEMPLATE,
                needs="act",
            )
        except T3Error as error:
            run.say(f"wait {slug}: its crew could not be told to carry on ({error})")
            continue
        if went:
            run.box.mark(made)
            run.say(f"told {slug}: {', '.join(named)} landed, what it waits on")


STEPS = (
    verbs.Step(
        "tellers",
        72,
        "pausedon.tell",
        lambda half: tell(half.run, half.client, half.seen.world, half.rows or []),
        ("client", "world"),
    ),
)
