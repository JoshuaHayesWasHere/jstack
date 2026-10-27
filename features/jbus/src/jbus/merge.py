"""Merging is `jmerge`'s job and nobody else's: jbus runs the command and reads its lines.

jbus is the only merger: it runs `jmerge` on each pass whatever the home's `home-thread` file
says, with no `--home`, so the run judges the pull requests of every home of the repo, and a
home's own run of `jmerge --home` merges nothing. The pass holds the pass lock around the run, so
two passes never run `jmerge` together, and `jmerge` holds the repo's merge lock from its read of
main's tip to its merge, so a hand run of the user's never merges between them either.

`parse`, which is `jmerge.lines.one`, reads each line `jmerge` prints about a pull request. `stall`
and `watch` read the `Line` that `parse` returns, not the text. `rebase` still reads the text of a
`wait` line on its own.

A `hold` is the user's to lift, except the ones a crew can lift (`UNRULED`, and a merge gate
that did not pass). `expedite` asks the crew to lift those first. This module sends the user
no line: `waiting` lists the holds that are the user's.

A sweep is `jmerge`'s job too, and jbus only asks what a sweep would remove. The one command
jbus runs for a sweep is `SWEEP`, which has `--check`.

When no rule of `rules` names a pull request's reason, the pull request is on no step, and
the view shows it in the Unknown lane. `unplaced` then sends the row's home one queued
message for each row and each reason text. The fix is a new rule, and a home writes the brief
for a rule. The message is a quiet event. The row is not the user's, so it is not in
`waiting-on-user.json`. One reason leaves a pull request on no step by design, and jbus tells
nobody of it (`OFF_STEP`): another home's pull request. A draft is on the step its review and
fix are at, and once both are done on the findings step, until its crew marks it ready.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

from jbus import alert, outbox, verbs
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.wake import JMERGE_TIMEOUT
from jmerge import lines as lines_of
from jmerge import ready
from jmerge.lines import Line as Line
from jmerge.lines import one as parse

if TYPE_CHECKING:
    from jbus.cli import Half

EVENTS = {"jmerge": "quiet", "sweep": "quiet", "unplaced": "quiet"}
_NO_LIST = re.compile(
    r"jmerge: .*(protected|guarded|ci-paths)\.txt "
    r"(cannot be read|has a pattern that cannot be read)"
)
NO_LIST = "jmerge has no readable protected-paths list, nothing merges"
SWEEP = ("jmerge", "--sweep", "--check")
UNRULED = re.compile(
    re.escape(ready.UNRULED_DROPS)
    .replace(r"\{user\}", ".+?")
    .replace(r"\{head\}", "([0-9a-f]{12})")
    .replace(r"\{files\}", ".+")
)
UNPLACED = "unplaced"
OFF_STEP = (ready.OTHER_HOME,)
TOLD = (
    "jbus: the view cannot place {slug}. jmerge said of its pull request #{number} `{said}`, "
    "and `merge.rules` in features/jbus/src/jbus/merge.py has no rule for it, so it shows in the "
    "Unknown "
    "lane. Brief the fix and queue it: the reason as a named `Reason` in "
    "features/jmerge/src/jmerge/ready.py, which names the step it puts it on. {user} is not "
    "asked: send {user} "
    "nothing about it. A question only {user} can answer is a gate: take the default and pipe "
    "it to `jbus gate <the fix's slug>`."
)


ELSEWHERE = (
    ("proof", r"no proven safety fact"),
    ("second", r"the rebase changed the patch after"),
    ("rebase", r"needs a rebase"),
    ("check", r"check has not finished|fresh check|could not be fetched|jmerge's own rules"),
    ("findings", r"^its head moved after"),
    ("findings", r"^\d+ of its \d+ findings have no Finding line"),
)
_GUARDED = re.compile(r"^guarded \(touches [^)]*\), ")


def rules() -> tuple[tuple[str, str], ...]:
    """Return the `(step, pattern)` of each reason `jmerge` writes, in the order `step` tries
    them: `ELSEWHERE` first, then each `ready.Reason` in the order `ready` declares it. Each
    pattern matches from the start of the reason.

    `ELSEWHERE` has the reasons `jmerge` writes from outside `ready` (its run, its proof and its
    range-diff), and the reasons an older `jmerge` wrote, which a log may still have. `ELSEWHERE`
    comes first so that a `ready.MAIN_CHANGED` reason with `it needs a rebase` is on the rebase
    step. `jmerge` gives that reason for a guarded path."""
    return ELSEWHERE + tuple((one.step, "^" + one.pattern) for one in ready.reasons().values())


def step(said: str) -> str:
    """Return the step a pull request waits on, read from the last line `jmerge` printed about it
    (`<word>: <reason>`). A `hold` is on the `hold` step, and a `wait` is on the first step of
    `rules` whose pattern matches its reason. Return nothing for a line with no reason, or for a
    reason no rule names."""
    word, _, reason = said.partition(": ")
    if not reason:
        return ""
    if word == "hold":
        return "hold"
    reason = _GUARDED.sub("", reason)
    return next((step for step, pattern in rules() if re.search(pattern, reason)), "")


class Said(list[str]):
    """`Said` is the list of lines `jmerge` printed about pull requests in this pass, as it
    printed them.

    `failed` is true when `jmerge` did not run to its end. In that case, a pull request with no line
    is one that `jmerge` did not reach. It is not one that `jmerge` read and had nothing to say
    about.
    """

    failed = False

    def crews(self, numbers: set[int]) -> Said:
        """Return the lines as the user is to hear them. A hold of one of these pull requests
        is its crew's to lift for now, so its line becomes a `wait`. The line stays in the
        list. A pull request with no line counts as one that `jmerge` did not reach, and such
        a pull request keeps the hold it had."""
        mine = {text for text in self if (line := parse(text)) and line.number in numbers}
        kept = Said(
            "wait" + text[4:] if text in mine and text[:5] == "hold " else text for text in self
        )
        kept.failed = self.failed
        return kept


def merge(run: Pass) -> Said:
    """Run `jmerge`, send each line it prints about a pull request, and return the lines.

    Every line is a quiet event, including a `hold` line. `waiting` lists each hold that is
    the user's. The user learns of a hold when the hold joins that list: once for the pull request,
    not once for each head. `expedite` deals first with a hold that a crew can lift.

    When `jmerge` does not run, that counts as a failure of the `jmerge` streak, and a run of
    `jmerge` ends the streak. A run that stopped after printing a line also ends the streak, as such
    a run always did, and the pass says that `jmerge` stopped. The `Said` that this function returns
    is then `failed`, so jbus keeps what it knew of the rows that `jmerge` did not reach.
    """
    ran = run.run("jmerge", timeout=JMERGE_TIMEOUT)
    lines = Said()
    for text in map(str.strip, ran.stdout.splitlines()):
        line = parse(text)
        if line is None or line.word == "refused":
            continue
        lines.append(text)
        slug = line.name if line.word == "merged" else ""
        run.find(slug or f"#{line.number}", "jmerge", text, key=f"{line.number} {text}")
        if slug and (unfollowed := lines_of.unfollowed(text)):
            alert.deliver(run, f"alert: {run.project.name}: {unfollowed}")
    lines.failed = bool(ran.returncode)
    name, streak = run.project.name, alert.jmerge(run.project.name)
    if not ran.returncode or lines:
        if lines.failed:
            run.say(f"wait {name}: jmerge stopped after {len(lines)} lines ({lines_of.said(ran)})")
        alert.tell(run, streak, alert.ok(run.config.state_dir, streak, user=run.user))
        return lines
    if _NO_LIST.search(why := lines_of.said(ran)):
        run.condition(name, NO_LIST, why, key=f"protected {run.day}")
    else:
        run.say(f"wait {name}: jmerge did not run ({why})")
        alert.tell(
            run, streak, alert.failed(run.config.state_dir, streak, why, now=run.now, user=run.user)
        )
    return lines


def _shown(half: Half) -> None:
    """Keep the lines a row's reason and the list of holds are read from, which are what `merge`
    printed in this pass, and those lines as the user is to hear them (`Said.crews`)."""
    half.shown = half.said
    half.users = half.said.crews(half.crews)


def sweep(run: Pass) -> tuple[bool, str]:
    """Ask `jmerge` what a sweep would remove, and send its lines when there are any.

    This function removes nothing: the command is `SWEEP`, with `--check`. Return whether
    `jmerge` ran, and one line on how the run went, for the status file.
    """
    ran = run.run(*SWEEP)
    if ran.returncode:
        return False, f"{' '.join(SWEEP)} did not run ({lines_of.said(ran)})"
    lines = [line.strip() for line in ran.stdout.splitlines() if line.startswith("removable ")]
    found = f"{len(lines)} to remove"
    if lines:
        run.box.send("", "sweep", f"sweep {run.project.name}: {found}", "\n".join(lines))
    return True, found


def unplaced(run: Pass, client: Client, slug: str, number: str, said: str, thread: str) -> None:
    """Tell the home that a row's pull request is on no step. Send the message once for each row and
    for each thing `jmerge` said of the pull request (`<word>: <reason>`). `thread` is the home's
    thread, or empty where the project has no home. When a message fails to send, the next pass
    sends it again."""
    reason = said.partition(": ")[2]
    if not reason or step(said) or reason in OFF_STEP:
        return
    digest = hashlib.sha256(said.encode()).hexdigest()[:12]
    if f"{UNPLACED}|{slug}|{digest}" in run.box.sent():
        return
    if not thread:
        run.say(f"wait {slug}: no rule names what jmerge said of it, and it has no home to tell")
        return
    text = TOLD.format(slug=slug, number=number, said=said, user=run.user.user)
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=slug,
            key=f"{UNPLACED}|{slug}|{digest}",
            text=text,
            template=UNPLACED,
            needs="decide",
        )
    except T3Error as error:
        run.say(f"wait {slug}: its home could not be told that no rule names its reason ({error})")
        return
    if not went:
        return
    line = f"{UNPLACED} {slug}: told its home, thread {thread}, that no rule names `{said}`"
    run.find(slug, UNPLACED, line, text, key=digest)
    run.say(line)


STEPS = (verbs.Step("derive", 5, "merge.shown", _shown),)
