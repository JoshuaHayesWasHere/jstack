"""Telling a crew what its pull request is short of: the wake a home no longer gives.

A crew ends its turn, and nothing wakes it for what it left undone: `jmerge` waits, on a
line nobody reads. `tell` reads those lines. Where one says the same crew-fixable reason of
the same head for `AFTER` passes, the crew is sent one message that says what to do, under
the key `<kind>|<slug>|<head 12>`. `TABLE` is the whole of it, a reason to its sentence:

- `unfixed`, `the Result has no Fixed line`: write an answer for each finding, by id, and
  the `Fixed:` line, `Fixed: none needed` when every one is declined, and push nothing for
  that;
- `unpushed`, `nothing was pushed after them`: push the fix and name its head, or decline
  every finding in writing, as above;
- `unended`, `<k> of <n> have no Finding line`: write the lines that are missing;
- `unanswered`, `uncited`, `repeated` and `risky`, the waits of an answer by id
  (`jbriefs.findings`): answer each finding by id, give a decline a reason that cites a
  path:line, a command or a gate, give each its own reason, and park a gate for a risky one.
  Each of these and the three above names the findings with no answer that counts, by id;
- `second`, `the second pass is not written`, which a brief from before fixes got a scoped
  review says: launch the second reviewer;
- `fix`, `the scoped review of it is not written`: launch the scoped reviewer of the fix,
  with the two ranges, the patch the last review saw and the patch at the head, or where
  no range can be worked out, run the crew skill's block, which says what to do;
- `declines`, `the scoped review has not ruled on the declines of <ids>`: run the crew
  skill's block of "A second pass", which launches the one scoped pass a blocking decline is
  owed, also where nothing was pushed;
- `overruled`, `the scoped review did not uphold the decline of <ids>`: fix each and answer
  it `fixed`, or, where the crew still holds the decline, tell its home. Its stall goes to
  the home's thread and never to the user (`OVERRULED_HOME`): only a decline on one of
  `findings.RISKS` is the user's, and that one is a `hold` no crew is asked to lift;
- `unruled`, a `hold` that says `the review of <head> did not rule on the drops in <files>`:
  launch the scoped pass over the rebase, and push nothing meanwhile;
- `unreviewed`, `it has no review yet`: launch the reviewer it is owed, or send the one that
  ended its turn with no `## Review` back to it, with `/pr-review run <slug> again`, the line
  `templates/rerun.md` says is accepted whether or not the brief has a section. It is not
  said of a pull request the crew skill leaves with no reviewer, which somebody was told of
  already: a brief that names no reviewer launched, and whose `Reviewer:` line says `none` or
  that has an `Unrun:`, `Stuck:` or `Stale base:` line for the head;
- `renumber`, `its migration <name> takes number <n>, which <default> has: renumber it to
  <free>`: rebase with the crew skill's "A conflict" block, which counts the rebase toward its
  cap of two after fixed and green, then renumber the migration and those after it, consecutively.

A thread is read by the status T3 Code lists it with. A crew whose thread is at work
(`watch.LIVE`: starting, `running` or `waiting`) is left alone, since the line may be what
it is about to write, and one that ended its turn (`completed`, `failed`, `interrupted`,
`cancelled`) is told. The last four reasons wait for a review, so they are not said while a
thread titled `review: <slug>` is at work either.

The message is a quiet event, `expedite`: it starts no POST. `expedite.json` counts the
passes. After the message, a pass in which the reason and the head are as they were and
nobody is at work, neither the crew nor a reviewer the reason waits for, is an idle one.
The `PASSES`th idle pass is one `stall` event for the chat, which names the pull request,
the reason and the crew's thread. So the user hears once, and only of a crew that did not
act. Work that lasts is no reason to say nothing for good: the `REVIEWING`th pass after the
message is that stall too, and says so where somebody is at work in that pass.

A `hold` is the user's, but for `unruled`. `tell` answers with the pull requests whose hold
it has in hand, and a pass shows those to the user as a `wait`: a hold that is not in hand
is an item of their list (`waiting`), and the list gaining it is what tells them. Such a
hold always has somebody. One `tell` cannot take on (no crew jbus launched, no `Rebase:`
line to take the ranges from) is the user's at once. So is one whose crew could not be told
by its `LAPSE`th pass: a thread that stays at work, a message that will not go. And so is
one its crew did not lift: from the pass after a stall that finds nobody at work it is the
user's, an item of their list, until the reason or the head changes. A stall said over work
that lasts hands nothing over: the hold is the user's once that work has ended and `PASSES`
idle passes are counted. A pass that could not ask T3 Code or GitHub has no crew to ask:
`told` keeps in hand the holds `tell` had in hand, and any other is the user's.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jbriefs import findings
from jbus import END_TURN, dispatch, leftover, merge, read_json, rebase, word, write_json
from jbus.stall import PASSES, REVIEWING
from jbus.t3 import Client, T3Error
from jbus.wake import Pass
from jbus.watch import LIVE, World
from jmerge import ready

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
_REBASE = re.compile(
    r"^Rebase: patch (?:unchanged|changed in .+), before ([0-9a-f]{40}), head ([0-9a-f]{40})$",
    re.M,
)
_OWED = re.compile(r"^Scoped review: needed since ([0-9a-f]{40}),", re.M)
NO_FIX_RANGE = (
    'Run the block of the crew skill\'s "A second pass" in your worktree and do what it prints: '
    "the Result says a scoped review of the fix is owed, and jbus could not work out its two "
    "ranges."
)
RERUN = Path(__file__).parents[2] / "templates" / "rerun.md"
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
    """One thing a crew can fix: the word and the reason `jmerge` says it with, and the
    sentence that tells the crew what to do. `reviewed` is one that a review ends, which
    is not said while a reviewer is at work. `unless` reads the brief, for a head, and
    says where the crew cannot fix it after all. `sends` is the line the sentence has the
    crew send a reviewer, which the event repeats as it went. `rerun` adds the statement of
    `templates/rerun.md`, the one copy of when a re-run needs `again`, which the reviewer's
    Start 1 prints when it refuses a message."""

    kind: str
    word: str
    reason: re.Pattern[str]
    sentence: str
    reviewed: bool = False
    unless: Callable[[str, str], bool] | None = None
    sends: str = ""
    rerun: bool = False


def _no_reviewer_by_rule(brief: str, head: str) -> bool:
    """Whether the crew skill left the pull request with no reviewer at this head, and said
    so: no reviewer was launched, and none can be (`Reviewer: none`) or none is yet (no
    check ran, a check is stuck, the base is stale). One that was launched is still owed."""
    if re.search(r"^Reviewer: (?!none\b)", brief, re.M):
        return False
    rule = rf"^(?:Reviewer: none\b|(?:Unrun|Stuck|Stale base): at {re.escape(head)},)"
    return bool(re.search(rule, brief, re.M))


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
        unless=_no_reviewer_by_rule,
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
        "`stale`: it counts the rebase toward the cap of two after fixed and green, and holds a "
        "third. Then renumber the migration the reason names to the number it gives, and each "
        "migration of yours after it to the numbers that follow, one each and in their order: "
        "the files, and every other line that names an old number. Run the check command, and "
        "push with the block's push.",
    ),
)


def short_of(said: merge.Line) -> Short | None:
    """The row of `TABLE` a line of `jmerge` is, or nothing for one no crew can fix."""
    rows = (row for row in TABLE if row.word == said.word and row.reason.fullmatch(said.reason))
    return next(rows, None)


def _brief(run: Pass, slug: str) -> str:
    try:
        return (run.home / "tasks" / f"{slug}.md").read_text(errors="replace")
    except OSError:
        return ""


def _kept(run: Pass, slug: str) -> str:
    """The head the crew kept before its last rebase, the newest commit under the slug's
    `refs/jstack/pre-rebase/` directory, or nothing where it kept none."""
    ref = f"refs/jstack/pre-rebase/{slug}/"
    asked = ("git", "for-each-ref", "--sort=-committerdate", "--count=1", "--format=%(objectname)")
    kept = run.run(*asked, ref)
    return "" if kept.returncode else kept.stdout.strip()


def _ranges(run: Pass, slug: str, head: str, kind: str) -> tuple[str, str] | None:
    """The two ranges of a scoped review that ends on `head`: the patch before it and the
    patch after, each from where it left the default branch. Before a rebase it is the commit
    the `Rebase:` line of this head names, or with no such line the newest head the crew kept
    under `refs/jstack/pre-rebase/<slug>/` (its keep step writes the ref and no line), and
    before a fix the head the last `Scoped review: needed since` line names, the one the last
    review saw."""
    brief = _brief(run, slug)
    if kind == "fix":
        before = (_OWED.findall(brief) or [""])[-1]
    else:
        before = next((was for was, to in reversed(_REBASE.findall(brief)) if to == head), "")
        before = before or _kept(run, slug)
    default = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if not before or default.returncode:
        return None
    old, new = (run.run("git", "merge-base", default.stdout.strip(), to) for to in (before, head))
    if old.returncode or new.returncode:
        return None
    return f"{old.stdout.strip()}..{before}", f"{new.stdout.strip()}..{head}"


def _reviewing(run: Pass, client: Client, slug: str) -> bool | None:
    """Whether a reviewer of the slug is at work, or None where T3 Code did not say."""
    asked = {"projectId": run.project.project_id, "titleContains": REVIEW + slug, "limit": 100}
    try:
        found = client.call("t3_thread_list", asked).get("threads", [])
    except T3Error as error:
        run.say(f"wait {slug}: its reviewers could not be listed ({error})")
        return None
    mine = (t for t in found if re.fullmatch(re.escape(REVIEW + slug) + r"(,.*)?", t["title"]))
    return any(not t.get("settled") and t["status"] in LIVE for t in mine)


def _busy(run: Pass, client: Client, world: World, slug: str, row: Short) -> bool | None:
    """Whether somebody is at work on what the row is short of: the crew, or for a row a
    review ends, a reviewer. None where T3 Code did not say."""
    if any(thread["status"] in LIVE for thread in world.threads.get(slug, [])):
        return True
    return _reviewing(run, client, slug) if row.reviewed else False


def told(run: Pass, pulls: merge.Said) -> set[int]:
    """The holds in hand in a pass that could not ask T3 Code or GitHub, where there is no
    crew to ask: the ones `tell` had in hand for the same reason when it last could ask. A
    hold it never took on, or one that is the user's by now, is the user's in such a pass
    too, so the list gains and loses no hold because one pass could not ask."""
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
    reason and head, and say the one that is no further `PASSES` idle passes on. The answer
    is the pull requests whose hold is in hand here: a `wait` for the user. A
    hold that stalled with nobody at work is in hand for that pass and the user's from the
    next.
    """
    by_number = {pull["number"]: slug for slug, pull in world.open.items()}
    was: dict[str, Any] = read_json(run.state / FILE, {})
    kept: dict[str, Any] = dict(was) if pulls.failed else {}
    sent = read_json(run.state / "sent.json", [])
    hand: set[int] = set()
    for text in pulls:
        said = merge.parse(text)
        row = short_of(said) if said else None
        if not said or not row:
            continue
        number, reason = said.number, said.reason
        slug = by_number.get(number, "")
        head = world.open[slug].get("headRefOid", "") if slug else ""
        if row.unless and row.unless(_brief(run, slug), head):
            continue
        if not head or not dispatch.launched(run, slug):
            continue
        seen = was.get(slug, {})
        same = (seen.get("head"), seen.get("reason")) == (head, reason)
        entry = {**seen, "passes": seen["passes"] + 1} if same else {"passes": 1}
        entry |= {"head": head, "reason": reason, "number": number}
        kept[slug] = entry
        passes = entry["passes"]
        due = not entry.keys() & {"told", "users"} and passes >= AFTER
        if due and f"{row.kind}|{slug}|{head[:12]}" in sent:
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
            thread = dispatch.thread_of(_brief(run, slug)) or "not known"
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
    """Send the home the stall of a decline not upheld, once for the slug and the reason, in
    place of the user, who is never paged for it: the finding is on none of review-triage's
    categories. Where there is no home it is said in the pass and the pull request stays
    where the view shows it, on the findings step, and a message that did not go is sent
    again on the next pass."""
    brief = _brief(run, slug)
    thread = word.home(leftover.home_of(run.home, brief))
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
        thread=dispatch.thread_of(brief) or "not known",
    )
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": text, "mode": "queue", "clientRequestId": digest}
    try:
        client.call("t3_thread_send", asked)
    except T3Error as error:
        run.say(f"wait {slug}: its home could not be told of the decline not upheld ({error})")
        return
    run.box.mark(digest)
    run.say(f"{STALL} {slug}: told its home, thread {thread}, of #{number}: {reason}")


def _tell(
    run: Pass, client: Client, world: World, number: int, slug: str, row: Short, entry: dict
) -> str:
    """Send the message that is due. The answer is how it went: `told`, `users` for a hold
    no message can lift, or nothing for one to try again in the next pass."""
    head = entry["head"]
    sentence, sent = row.sentence, row.sends.replace("{slug}", slug)
    if row.kind in ("unruled", "fix"):
        ranges = _ranges(run, slug, head, row.kind)
        if not ranges and row.kind == "unruled":
            run.say(f"wait {slug}: {NO_RANGE}")
            return "users"
        if ranges:
            sentence = sentence.replace("{old}", ranges[0]).replace("{new}", ranges[1])
            sent = sent.replace("{old}", ranges[0]).replace("{new}", ranges[1])
        else:
            sentence, sent = NO_FIX_RANGE, ""
    if row.rerun:
        sentence += " " + RERUN.read_text().strip()
    if row.kind in ANSWERED:
        left = [one.id for one in findings.triage(_brief(run, slug)).blocking()]
        sentence += f" The findings with no answer that counts: {', '.join(left)}." if left else ""
    message = MESSAGE.replace("{sentence}", sentence)
    ask = rebase.Ask(
        row.kind, "", "told what it is short of", message, no_thread=NO_THREAD, refused=REFUSED
    )
    went = rebase.post(run, client, world, number, entry["reason"], ask)
    if not went:
        return ""
    run.box.mark(f"{row.kind}|{slug}|{head[:12]}")
    line = f"{EXPEDITE} {slug}: told the crew what #{number} is short of ({row.kind}, {head[:12]})"
    line += f", sent `{sent}`" if sent else ""
    run.find(slug, EXPEDITE, line, went[2], key=f"{row.kind} {head[:12]}")
    run.say(line)
    return "told"
