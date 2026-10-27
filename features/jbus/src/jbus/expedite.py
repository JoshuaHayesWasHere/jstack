"""Tell a crew what its pull request is short of. A home used to send this wake, and no
longer does.

A crew ends its turn, and nothing wakes it for what it left undone. `jmerge` reports a wait
in a line that nobody reads. `tell` reads those lines. When a line gives the same
crew-fixable reason for the same head for `AFTER` passes, `tell` sends the crew one
message that says what to do, under the key `<kind>|<slug>|<head 12>`. `TABLE` holds every
reason with its sentence:

- `unfixed`, `the Result has no Fixed line`: write an answer for each finding, by id, and
  the `Fixed:` line. The line is `Fixed: none needed` when the crew declines every finding,
  and then the crew pushes nothing for it;
- `unpushed`, `nothing was pushed after them`: push the fix and name its head, or decline
  every finding in writing, as above;
- `unended`, `<k> of <n> have no Finding line`: write the lines that are missing;
- `unanswered`, `uncited`, `repeated` and `risky`, the waits of an answer by id
  (`jbriefs.findings`): answer each finding by id, and give a decline a reason that cites a
  path:line, a command or a gate. Give each finding its own reason, and park a gate for a
  risky one. For each of these four reasons and the three above, the line lists by id the
  findings that have no answer that counts;
- `second`, `the second pass is not written`: launch the second reviewer. `jmerge` gives this
  reason for a brief written before fixes got a scoped review;
- `fix`, `the scoped review of it is not written`: launch the scoped reviewer of the fix
  with the two ranges, the patch the last review saw and the patch at the head. Where the
  crew cannot work out a range, run the crew skill's block, which says what to do;
- `declines`, `the scoped review has not ruled on the declines of <ids>`: run the crew
  skill's block of "A second pass". The block launches the one scoped pass that a blocking
  decline needs, even where the crew pushed nothing;
- `overruled`, `the scoped review did not uphold the decline of <ids>`: fix each finding and answer
  it `fixed`, or, where the crew still stands by the decline, tell its home. The stall for this
  reason goes to the home's thread and never to the user (`OVERRULED_HOME`). Only a decline on one
  of `findings.RISKS` is the user's to settle. That one is a `hold`, and jbus asks no crew to lift
  it;
- `unruled`, a `hold` that says `the review of <head> did not rule on the drops in <files>`:
  launch the scoped pass over the rebase, and push nothing meanwhile;
- `unreviewed`, `it has no review yet`: launch the reviewer the pull request is owed. Or send a
  reviewer that ended its turn with no `## Review` back to work, with `/pr-review run <slug> again`.
  `features/crew/templates/rerun.md` says a reviewer accepts that line whether or not the brief has
  a section. `tell` does not send this reason for a pull request that the crew skill leaves with no
  reviewer, since the crew skill has told somebody of it already. Such a brief names no launched
  reviewer, and either its `Reviewer:` line says `none` or it has an `Unrun:`, `Stuck:` or
  `Stale base:` line for the head;
- `renumber`, `its migration <name> takes number <n>, which <default> has: renumber it to
  <free>`: rebase with the crew skill's "A conflict" block, run with `stale`. Then renumber
  the migration and the ones after it, consecutively.
- `gate`, a `hold` that says `its merge gate failed`, `could not start` or `ran over`: run the
  repo's merge gate at the head, fix what it names or make what it asks for, and push where a
  file changed. Only a gate that passes lifts the hold.

`tell` judges each thread by the status that T3 Code lists for it. It leaves alone a crew whose
thread is at work (`watch.at_work`: starting, `running` or `waiting`), since the line may be
what the crew is about to write. It tells a crew that ended its turn (`completed`, `failed`,
`interrupted`, `cancelled`). The last four reasons wait for a review, so `tell` also does
not send them while a thread titled `review: <slug>` is at work.

The outbox holds a message to a crew whose instance is capped (`jbus.outbox`), and the first pass
after the reset sends it. While it waits the count stays at `AFTER`, as if the message were due for
the first time, so a hold the message is about stays in hand until the reset, and `LAPSE`
counts from the reset.

The message is a quiet event, `expedite`: it starts no POST. `expedite.json` counts the
passes. After the message, a pass is an idle one when the reason and the head are as they
were and nobody is at work, neither the crew nor a reviewer the reason waits for. The
`PASSES`th idle pass logs one `stall` event, quiet and in the digest, which names the pull
request, the reason and the crew's thread, once, and only of a crew that did not act.
Long work does not delay the stall forever. The `REVIEWING`th pass after the message
also sends that stall, and where somebody is at work in that pass, the stall says so.

A `hold` is the user's, except for `unruled` and `gate`. `tell` returns the pull requests whose hold
it has in hand, and a pass shows those to the user as a `wait`. A hold that is not in hand is an
item of the user's list (`waiting`), and the user learns of it when it appears on that list. Such a
hold always has an owner. A hold that `tell` cannot take on goes to the user at once: a hold whose
crew jbus did not launch, or one with no `Rebase:` line to take the ranges from. A hold also goes to
the user when jbus could not tell its crew by the `LAPSE`th pass, because the thread stays at work
or the message is not delivered. A hold that its crew did not lift goes to the user too. Starting
with the pass after a stall that finds nobody at work, that hold is an item of the user's list,
until the reason or the head changes. A stall that jbus sends while work is still going on does not
make the hold the user's. The hold becomes the user's once that work has ended and `PASSES` idle
passes have gone by. A pass that could not ask T3 Code or GitHub has no crew to ask. Then `told`
keeps in hand the holds `tell` had in hand, and every other hold is the user's.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jbriefs import below, findings, skills
from jbriefs import parse as briefs
from jbus import END_TURN, dispatch, merge, outbox, read_json, rebase, verbs, write_json
from jbus.passes import Pass
from jbus.stall import PASSES, REVIEWING
from jbus.t3 import Client, T3Error
from jbus.watch import World, at_work, home_thread, task_brief
from jmerge import ready

if TYPE_CHECKING:
    from jbus.cli import Half

EVENTS = {"expedite": "quiet"}
EXPEDITE = "expedite"
STALL = "stall"
AFTER = 3
LAPSE = AFTER + PASSES
NO_THREAD = "short pull request with no thread to tell"
REFUSED = "T3 Code refused the message about what a pull request is short of"
FILE = "expedite.json"
REVIEW = "review: "
NO_RANGE = "its Result has no Rebase line for its head, so the hold is the user's"
_OWED = re.compile(r"^Scoped review: needed since ([0-9a-f]{40}),", re.M)
NO_FIX_RANGE = (
    'Run the block of the crew skill\'s "A second pass" in your worktree and do what it prints: '
    "the Result says a scoped review of the fix is owed, and jbus could not work out its two "
    "ranges."
)
RERUN = "rerun.md"
ANSWERED = ("unfixed", "unpushed", "unended", "unanswered", "uncited", "repeated", "risky")
AGAIN = "/pr-review run {slug} again"
OVERRULED_HOME = (
    "jbus: {slug}'s pull request #{number} waits on its crew, which has not acted on it in "
    "{since} passes: {reason}. A decline the scoped pass did not uphold is the crew's to fix, "
    "and yours to settle with it where it holds the decline; {user} is not asked, since the "
    "finding is on none of review-triage's categories. Its crew's thread is {thread}."
)
SCOPED = "/pr-review run {slug} scoped {old} {new}"
MESSAGE = (
    "jbus: pull request #{number} waits on you, and jmerge keeps saying the same of it "
    "({reason}). {sentence} " + END_TURN
)


@dataclass(frozen=True)
class Short:
    """A `Short` holds one thing a crew can fix: the word, the reason that `jmerge` gives for it,
    and the sentence that tells the crew what to do. `reviewed` marks a reason that a review clears.
    `tell` does not send such a reason while a reviewer is at work. `unless` reads the brief for a
    head, and says when the crew cannot fix the thing after all. `sends` is the line that the
    sentence asks the crew to send to a reviewer. The event repeats that line as the crew sent it.
    `rerun` adds the statement in `features/crew/templates/rerun.md`, the one place that says when a
    re-run needs `again`. The reviewer's Start 1 prints that statement when it refuses a message."""

    kind: str
    word: str
    reason: re.Pattern[str]
    sentence: str
    reviewed: bool = False
    unless: Callable[[str, str], bool] | None = None
    sends: str = ""
    rerun: bool = False


def no_reviewer_by_rule(brief: str, head: str) -> bool:
    """Say whether the brief records, by the crew skill's rule, that the pull request has
    no reviewer at this head. That is so when the crew launched no reviewer, and either none
    can run (`Reviewer: none`) or none runs yet (no check ran, a check is stuck, or the base
    is stale). A pull request whose crew launched a reviewer still waits for that review."""
    said = below.reviewers(brief, "Reviewer")
    if any(map(below.launched, said)):
        return False
    gated = rf"^(?:Unrun|Stuck|Stale base): at {re.escape(head)},"
    return bool(said) or bool(re.search(gated, brief, re.M))


TABLE = (
    Short(
        "unfixed",
        "wait",
        re.compile(re.escape(ready.NO_FIXED)),
        f"Write one line in the Result for each finding, {findings.ANSWER}, and then the `Fixed:` "
        "line: `Fixed: <the head you pushed>` where you pushed a fix, or `Fixed: none needed, "
        "<reason>` when every finding is declined. Push nothing for a `Fixed: none needed`.",
    ),
    Short(
        "unpushed",
        "wait",
        re.compile(re.escape(ready.NOT_PUSHED)),
        "The `Fixed:` line names the head the review saw, so no fix is at the head. Push the "
        "fix and set `Fixed:` to the head you pushed. Or, when every finding is declined, write "
        f"{findings.ANSWER} for each and `Fixed: none needed, <reason>`, and push nothing for "
        "that.",
    ),
    Short(
        "unended",
        "wait",
        re.compile(
            re.escape(ready.UNENDED).replace(r"\{left\}", r"\d+").replace(r"\{found\}", r"\d+")
        ),
        "Write the lines that are missing, one for each finding of both passes, "
        f"{findings.ANSWER}. Set `Fixed:` to the head you pushed where you push for them, and "
        "push nothing where you decline them.",
    ),
    Short(
        "unanswered",
        "wait",
        re.compile(ready.UNANSWERED.pattern),
        f"Answer each finding the reason names by its id, {findings.ANSWER}: `jbriefs --findings "
        "<the brief>` lists them. An answer with no id answers none of them.",
    ),
    Short(
        "uncited",
        "wait",
        re.compile(ready.UNCITED.pattern),
        "Give the decline of each finding the reason names a reason that cites a path:line, a "
        f"command in backticks, or the gate it is parked on, {findings.ANSWER}, or fix it.",
    ),
    Short(
        "repeated",
        "wait",
        re.compile(ready.REPEATED.pattern),
        "A reason given for one finding does not decline another: give the decline of each "
        f"finding the reason names a reason of its own, {findings.ANSWER}, or fix it.",
    ),
    Short(
        "risky",
        "wait",
        re.compile(ready.RISK_UNASKED.pattern),
        "A finding on security, auth, billing, data, migrations or concurrency is not declined "
        'by the crew alone: park it as a gate (the crew skill, "Do the task") with the default '
        "that it is fixed, fix it, and answer it `Finding F<n>: fixed, ...`; where the user "
        "answers that it stays, answer it `Finding F<n>: not fixed, ..., because question <n>: "
        "<the answer>`, with the Result's `Gate: question <n>` line.",
    ),
    Short(
        "second",
        "wait",
        re.compile(re.escape(ready.SECOND_UNWRITTEN)),
        'Launch the second reviewer now, the way the crew skill\'s "A second pass" says, with '
        f"the message `{AGAIN}`, and add `Second reviewer: <threadId>` to the "
        "Result, in place of a `Second reviewer:` line whose thread wrote no `## Review`. Push "
        "nothing until its `## Review` is written.",
        reviewed=True,
        sends=AGAIN,
    ),
    Short(
        "twice",
        "wait",
        re.compile(ready.TWICE_UNWRITTEN.pattern),
        "Its brief says `Review: twice`: launch its second review of the head you pushed now, "
        f'the way the crew skill\'s "The review" says, with the message `{AGAIN}`, and add '
        "`Second reviewer: <threadId>` to the Result, in place of a `Second reviewer:` line "
        "whose thread wrote no `## Review`. Fix nothing it finds: its findings go to a cleanup "
        "row.",
        reviewed=True,
        sends=AGAIN,
    ),
    Short(
        "fix",
        "wait",
        re.compile(re.escape(ready.FIX_UNREVIEWED)),
        "Launch ONE scoped reviewer of the fix now, not a full review, the way the crew skill's "
        f'"The review" launches a reviewer, with the message `{SCOPED}`, '
        "and add `Scoped reviewer: <threadId>, of {head}` to the Result, in place of a "
        "`Scoped reviewer:` line whose thread wrote no `## Review`. Push nothing until its "
        "`## Review` is written.",
        reviewed=True,
        sends=SCOPED,
    ),
    Short(
        "unruled",
        "hold",
        merge.UNRULED,
        'Launch ONE scoped reviewer over the rebase, the way the crew skill\'s "The review" '
        f"launches a reviewer, with the message `{SCOPED}`, and "
        "add `Scoped reviewer: <threadId>, of {head}` to the Result. Push nothing and do not "
        "rebase until its `## Review` is written: a `Dropped on rebase:` line is read for this "
        "head and no other.",
        reviewed=True,
        sends=SCOPED,
    ),
    Short(
        "unreviewed",
        "wait",
        re.compile(re.escape(ready.NO_REVIEW)),
        "No thread titled `review: {slug}` is at work, and the brief has no `## Review`. Run "
        'the block of the crew skill\'s "The checks" and then the blocks of "The review", and '
        "do what they print. Where they say `launch a reviewer`, launch it and add `Reviewer: "
        "<threadId> #<n>` to the Result, `<n>` its number. Where they say `launch no reviewer` "
        "because the Result has a `Reviewer:` line, that reviewer ended its turn and wrote "
        "nothing: send its thread "
        f"the one line `{AGAIN}` with `t3_thread_send`, and write `Woke: jbus, sent {AGAIN}` "
        "in the Result, the line as sent. Launch no second one.",
        reviewed=True,
        unless=no_reviewer_by_rule,
        sends=AGAIN,
        rerun=True,
    ),
    Short(
        "declines",
        "wait",
        re.compile(ready.DECLINES_UNRULED.pattern),
        'Run the block of the crew skill\'s "A second pass" in your worktree and do what it '
        "prints: each blocking decline is ruled on by one scoped pass, also where nothing was "
        "pushed, and the block writes the `Scoped review:` line and gives the launch.",
        reviewed=True,
    ),
    Short(
        "overruled",
        "wait",
        re.compile(ready.DECLINES_OVERRULED.pattern),
        "The scoped pass did not uphold the decline of the findings the reason names. Fix each, "
        "push, and answer it `Finding F<n>: fixed, ...`: declining it again does not lift the "
        'ruling. Where you still hold a decline, send the home one line ("Telling the home"), '
        "`<slug>: <pull request url>, the decline of F<n> is not upheld and I hold it: <why>`, "
        "and end your turn: the home settles it with you.",
    ),
    Short(
        "renumber",
        "wait",
        re.compile(
            re.escape(ready.MIGRATION_TAKEN)
            .replace(r"\{name\}", r"\S+")
            .replace(r"\{number\}", r"\d+")
            .replace(r"\{default\}", r"\S+")
            .replace(r"\{free\}", r"\d+")
        ),
        'Rebase onto the default branch with the crew skill\'s "A conflict" block, run with '
        "`stale`. Then renumber the migration the reason "
        "names to the number it gives, and each migration of yours after it to the numbers that "
        "follow, one each and in their order: the files, and every other line that names an old "
        "number. Run the check command, and push with the block's push.",
    ),
    Short(
        "gate",
        "hold",
        ready.GATE_HELD,
        "The repo's merge gate did not pass at your pull request's head: `jmerge` ran the "
        "command in the `merge-gate` file of the repo's state, and `merge.log` there keeps its "
        "whole output under the hold line. Run the same command in your worktree, with the merge "
        "base and the head as its last two arguments, the way the pr-review skill's \"The merge "
        'gate" block runs it. Fix what it names or make what it asks for, run the check command, '
        "and push where a file changed. `jmerge` runs the gate again on its next run, and only a "
        "gate that passes lifts the hold: `--accept` does not.",
    ),
)


def short_of(said: merge.Line) -> Short | None:
    """Return the row of `TABLE` that a line of `jmerge` matches, or nothing for a line no
    crew can fix."""
    rows = (row for row in TABLE if row.word == said.word and row.reason.fullmatch(said.reason))
    return next(rows, None)


def _kept(run: Pass, slug: str) -> str:
    """Return the head the crew kept before its last rebase, or nothing where it kept none.
    That head is the newest commit under the slug's `refs/jstack/pre-rebase/` directory."""
    ref = f"refs/jstack/pre-rebase/{slug}/"
    asked = ("git", "for-each-ref", "--sort=-committerdate", "--count=1", "--format=%(objectname)")
    kept = run.run(*asked, ref)
    return "" if kept.returncode else kept.stdout.strip()


def ranges(run: Pass, slug: str, head: str, kind: str) -> tuple[str, str] | None:
    """Return the two ranges of a scoped review that ends on `head`: the patch before it and
    the patch after. Each patch starts where its branch left the default branch.

    The patch before ends on one commit. For a rebase, that commit is the one the `Rebase:`
    line of this head names. With no such line, it is the newest head the crew kept under
    `refs/jstack/pre-rebase/<slug>/`, since the crew's keep step writes the ref and no line.
    For a fix, it is the head the last `Scoped review: needed since` line names, the one the
    last review saw."""
    brief = task_brief(run, slug)
    if kind == "fix":
        before = (_OWED.findall(brief) or [""])[-1]
    else:
        before = next((was for _, was, to in reversed(below.rebases(brief)) if to == head), "")
        before = before or _kept(run, slug)
    default = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if not before or default.returncode:
        return None
    old, new = (run.run("git", "merge-base", default.stdout.strip(), to) for to in (before, head))
    if old.returncode or new.returncode:
        return None
    return f"{old.stdout.strip()}..{before}", f"{new.stdout.strip()}..{head}"


def _reviewing(run: Pass, client: Client, slug: str) -> bool | None:
    """Say whether a reviewer of the slug is at work, or return None where T3 Code did not
    say."""
    asked = {"projectId": run.project.project_id, "titleContains": REVIEW + slug, "limit": 100}
    try:
        found = client.call("t3_thread_list", asked).get("threads", [])
    except T3Error as error:
        run.say(f"wait {slug}: its reviewers could not be listed ({error})")
        return None
    mine = (t for t in found if re.fullmatch(re.escape(REVIEW + slug) + r"(,.*)?", t["title"]))
    return at_work(mine)


def _busy(run: Pass, client: Client, world: World, slug: str, row: Short) -> bool | None:
    """Say whether somebody is at work on what the row is short of: the crew, or a reviewer
    for a row that a review clears. Return None where T3 Code did not say."""
    if at_work(world.threads.get(slug, [])):
        return True
    return _reviewing(run, client, slug) if row.reviewed else False


def _capped(run: Pass, client: Client, slug: str) -> bool:
    """Say whether the crew's instance is capped, so the outbox holds the message to it."""
    return bool(outbox.capped(run, client, briefs.thread_of(task_brief(run, slug))))


def told(run: Pass, pulls: merge.Said) -> set[int]:
    """Return the holds in hand in a pass that could not ask T3 Code or GitHub, and so has
    no crew to ask. They are the holds `tell` had in hand for the same reason when it last
    could ask. A hold `tell` never took on, or one that is the user's by now, stays the
    user's in such a pass. So the list gains and loses no hold just because one pass could
    not ask."""
    was: dict[str, Any] = read_json(run.state / FILE, {})
    asked = {
        (entry.get("number"), entry.get("reason"))
        for entry in was.values()
        if not entry.get("users")
    }
    said = (line for line in map(merge.parse, pulls) if line and line.word == "hold")
    return {line.number for line in said if short_of(line) and (line.number, line.reason) in asked}


def tell(run: Pass, client: Client, world: World, pulls: merge.Said) -> set[int]:
    """Tell each crew what its pull request has been short of for `AFTER` passes, once per
    reason and head. Send a stall for a crew that has made no progress after `PASSES` idle
    passes. Return the pull requests whose hold `tell` is dealing with. The user sees each of
    them as a `wait`. `tell` deals with a hold that stalled with nobody at work for that pass
    only. From the next pass on, the hold is the user's.
    """
    by_number = {pull["number"]: slug for slug, pull in world.open.items()}
    was: dict[str, Any] = read_json(run.state / FILE, {})
    kept: dict[str, Any] = dict(was) if pulls.failed else {}
    sent = run.box.sent()
    hand: set[int] = set()
    for text in pulls:
        said = merge.parse(text)
        row = short_of(said) if said else None
        if not said or not row:
            continue
        number, reason = said.number, said.reason
        slug = by_number.get(number, "")
        head = world.open[slug].get("headRefOid", "") if slug else ""
        if row.unless and row.unless(task_brief(run, slug), head):
            continue
        if not head or not dispatch.launched(run, slug):
            continue
        seen = was.get(slug, {})
        same = (seen.get("head"), seen.get("reason")) == (head, reason)
        entry = {**seen, "passes": seen["passes"] + 1} if same else {"passes": 1}
        entry |= {"head": head, "reason": reason, "number": number}
        kept[slug] = entry
        due = not entry.keys() & {"told", "users"} and entry["passes"] >= AFTER
        if due and _capped(run, client, slug):
            entry["passes"] = AFTER
        passes = entry["passes"]
        if due and rebase.mark(row.kind, slug, head) in sent:
            entry["told"], due = passes, False
        asked = "told" in entry and not entry.get("users")
        busy = _busy(run, client, world, slug, row) if due or asked else None
        if due and busy is False:
            went = _tell(run, client, world, number, slug, row, entry)
            entry |= {"told": passes} if went == "told" else {"users": True} if went else {}
        if row.word == "hold" and due and "told" not in entry and passes >= LAPSE:
            run.say(
                f"wait {slug}: its crew was not told in {passes} passes, so the hold is the user's"
            )
            entry["users"] = True
        if entry.get("users"):
            continue
        if row.word == "hold":
            hand.add(number)
        since = passes - entry.get("told", passes)
        if since and busy is False:
            entry["idle"] = entry.get("idle", 0) + 1
        if entry.get("idle", 0) >= PASSES or since >= REVIEWING:
            thread = briefs.thread_of(task_brief(run, slug)) or "not known"
            work = ", with its crew or a reviewer at work" if busy else ""
            line = (
                f"{STALL} {slug}: #{number} is as short as it was {since} passes after its "
                f"crew was told{work}, at {head[:12]}, {reason}; its crew's thread is {thread}"
            )
            if row.kind == "overruled":
                _to_home(run, client, slug, number, since, reason)
            else:
                run.find(slug, STALL, line, key=f"{head[:12]} {row.kind}")
            if row.word == "hold" and busy is False and entry.get("idle", 0) >= PASSES:
                entry["users"] = True
    if kept != was:
        write_json(run.state / FILE, kept)
    return hand


def _to_home(run: Pass, client: Client, slug: str, number: int, since: int, reason: str) -> None:
    """Send the home the stall of a decline that the scoped review did not uphold, once for
    the slug and the reason. The home gets it instead of the user. jbus never pages the user for
    it, since the finding is in none of review-triage's categories. Where there is no home,
    the pass prints the stall, and the view keeps showing the pull request on the findings
    step. When a message fails to send, the next pass sends it again."""
    brief = task_brief(run, slug)
    thread = home_thread(run, brief)
    if not thread:
        run.say(f"wait {slug}: #{number} waits on its crew, {reason}, and it has no home to tell")
        return
    digest = f"overruled|{slug}|{reason}"
    if digest in run.box.sent():
        return
    text = OVERRULED_HOME.format(
        slug=slug,
        number=number,
        since=since,
        reason=reason,
        user=run.user.user,
        thread=briefs.thread_of(brief) or "not known",
    )
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=slug,
            key=digest,
            text=text,
            template="overruled",
            needs="decide",
        )
    except T3Error as error:
        run.say(f"wait {slug}: its home could not be told of the decline not upheld ({error})")
        return
    if not went:
        return
    run.box.mark(digest)
    run.say(f"{STALL} {slug}: told its home, thread {thread}, of #{number}: {reason}")


def _tell(
    run: Pass,
    client: Client,
    world: World,
    number: int,
    slug: str,
    row: Short,
    entry: dict,
) -> str:
    """Send the message that is due, and return how it went: `told`, `users` for a hold no
    message can lift, or nothing when the next pass must try the message again."""
    head = entry["head"]
    sentence, sent = row.sentence, row.sends.replace("{slug}", slug)
    if row.kind in ("unruled", "fix"):
        found = ranges(run, slug, head, row.kind)
        if not found and row.kind == "unruled":
            run.say(f"wait {slug}: {NO_RANGE}")
            return "users"
        if found:
            sentence = sentence.replace("{old}", found[0]).replace("{new}", found[1])
            sent = sent.replace("{old}", found[0]).replace("{new}", found[1])
        else:
            sentence, sent = NO_FIX_RANGE, ""
    if row.rerun:
        sentence += " " + skills.where("template", RERUN).read_text().strip()
    if row.kind in ANSWERED:
        left = [one.id for one in findings.triage(task_brief(run, slug)).blocking()]
        sentence += f" The findings with no answer that counts: {', '.join(left)}." if left else ""
    message = MESSAGE.replace("{sentence}", sentence)
    ask = rebase.Ask(
        row.kind, "", "told what it is short of", message, no_thread=NO_THREAD, refused=REFUSED
    )
    went = rebase.post(run, client, world, number, entry["reason"], ask)
    if not went:
        return ""
    run.box.mark(rebase.mark(row.kind, slug, head))
    line = f"{EXPEDITE} {slug}: told the crew what #{number} is short of ({row.kind}, {head[:12]})"
    line += f", sent `{sent}`" if sent else ""
    run.find(slug, EXPEDITE, line, went[2], key=f"{row.kind} {head[:12]}")
    run.say(line)
    return "told"


def _step(half: Half) -> None:
    """Run `tell` where the pass could ask T3 Code and GitHub, and `told` where it could not."""
    world = half.seen.world
    if world is not None and half.client is not None:
        half.crews = tell(half.run, half.client, world, half.said)
    else:
        half.crews = told(half.run, half.said)


STEPS = (verbs.Step("after-expedite", 1, "expedite.tell", _step),)
