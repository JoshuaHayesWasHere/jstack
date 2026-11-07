"""Merging is `jmerge`'s job and nobody else's: jbus runs the command and reads its lines.

jbus is the only merger: it runs `jmerge` on each pass whatever the home's `home-thread` file
says, with no `--home`, so the run judges the pull requests of every home of the repo, and a
home's own run of `jmerge --home` merges nothing. Between passes the merge tick runs it too, a
few seconds after a check ends (`tick`, `jbus.tick`). `jmerge` holds the repo's run lock for the
whole of a run that may merge, so the pass, the tick and a hand run of the user's never run it
together (`jmerge.lock`). The pass and the tick both run it with `--if-free`: a run that finds
the lock held does nothing, and neither waits on another's run inside its own timeout.

`parse`, which is `jmerge.lines.one`, reads each line `jmerge` prints about a pull request. `stall`
and `watch` read the `Line` that `parse` returns, not the text, and `rebase` and `expedite` go by
its reason's code. `step`, which is `jmerge.judgement.step`, goes by a reason's code where
`merge.log` wrote one. `parse` and `Said` are in `jbus.judged`, below `jbus.watch`, which reads
them too.

A `hold` is the user's to lift, except the ones a crew can lift (`UNRULED`). `expedite` asks the
crew to lift those first. This module sends the user
no line: `waiting` lists the holds that are the user's.

A sweep is `jmerge`'s job too, and jbus only asks what a sweep would remove. The one command
jbus runs for a sweep is `SWEEP`, which has `--check`.

When no rule of `ready.rules` names a pull request's reason, the pull request is on no step, and
the view shows it in the Unknown lane. `unplaced` then sends the row's home one queued
message for each row and each reason text. The fix is a new rule, and a home writes the brief
for a rule. The message is a quiet event. The row is not the user's, so it is not in
`waiting-on-user.json`. One reason leaves a pull request on no step by design, and jbus tells
nobody of it (`OFF_STEP`): another home's pull request. A draft, which only a hand opens, is on
the step its review and fix are at, and once both are done on the Result step (`HAND_DRAFT`):
jmerge never marks it ready.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from typing import TYPE_CHECKING

from jbus import alert, outbox, restated, verbs, work
from jbus.judged import Said, parse
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.wake import JMERGE_TIMEOUT
from jmerge import lines as lines_of
from jmerge import lock, ready
from jmerge.judgement import step
from jmerge.lines import Line as Line
from jsettings import proc

if TYPE_CHECKING:
    from jbus.poll import Half

EVENTS = {"jmerge": "quiet", "sweep": "quiet", "unplaced": "quiet"}
_NO_LIST = re.compile(
    r"jmerge: .*(protected|ci-paths)\.txt "
    r"(cannot be read|has a pattern that cannot be read)"
)
NO_LIST = "jmerge has no readable protected-paths list, nothing merges"
RUN = ("jmerge", "--if-free")
"""The run of `jmerge` the pass and the tick make: with `--if-free`, a run that finds the run lock
held does nothing and exits `lock.BUSY`, rather than wait inside `JMERGE_TIMEOUT`."""
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
    "and `rules` in features/jmerge/src/jmerge/ready.py has no rule for it, so it shows in the "
    "Unknown "
    "lane. Brief the fix and queue it: the reason as a named `Reason` in "
    "features/jmerge/src/jmerge/ready.py, which names the step it puts it on. {user} is not "
    "asked: send {user} "
    "nothing about it. A question only {user} can answer is a gate: take the default and pipe "
    "it to `jbus gate <the fix's slug>`."
)


def merge(run: Pass) -> Said:
    """Run `jmerge --if-free`, send each line it prints about a pull request, and return the lines.

    Every line is a quiet event, including a `hold` line. `waiting` lists each hold that is
    the user's. The user learns of a hold when the hold joins that list: once for the pull request,
    not once for each head. `expedite` deals first with a hold that a crew can lift.

    A run of the tick's or one by hand may hold the run lock. With `--if-free` the pass's run then
    does nothing and ends at once (`lock.BUSY`): it is no run, so it leaves the `jmerge` streak as
    it was, and the next pass runs it again. Without it the pass would wait for the lock inside
    `JMERGE_TIMEOUT` and count the other run's minutes as its own failure.

    When `jmerge` does not run, or holds the run lock past `JMERGE_TIMEOUT`, that counts as a
    failure of the `jmerge` streak, and a run of `jmerge` ends the streak. A run that stopped after
    printing a line also ends the streak, as such a run always did, and the pass says that `jmerge`
    stopped. The `Said` that this function returns is then `failed`, so jbus keeps what it knew of
    the rows that `jmerge` did not reach, as it does for a busy run.
    """
    ran = run.run(*RUN, timeout=JMERGE_TIMEOUT)
    lines = _sent(run, ran)
    name, streak = run.project.name, alert.jmerge(run.project.name)
    if ran.returncode == lock.BUSY:
        run.say(f"wait {name}: jmerge is busy: another run holds its run lock")
        return lines
    if not ran.returncode or lines:
        if lines.failed:
            run.say(f"wait {name}: jmerge stopped after {len(lines)} lines ({lines_of.said(ran)})")
        alert.tell(run, streak, alert.ok(run.config.state_dir, streak, user=run.user))
        return lines
    if _NO_LIST.search(why := lines_of.said(ran)):
        run.condition(name, NO_LIST, why, key=f"protected {run.day}")
    else:
        run.say(f"wait {name}: jmerge did not run ({why})")
        _failed(run, why)
    return lines


def _failed(run: Pass, why: str) -> None:
    """Count one failure of the project's `jmerge` streak, and raise its alert once it is due."""
    streak = alert.jmerge(run.project.name)
    alert.tell(
        run, streak, alert.failed(run.config.state_dir, streak, why, now=run.now, user=run.user)
    )


def _sent(run: Pass, ran: subprocess.CompletedProcess[str]) -> Said:
    """Send each line a run of `jmerge` printed about a pull request, once for its key, and
    return them. The run restates each line it judged, and logs as a quiet `work-drift` each one
    the merge tick restated otherwise (`restated.pulled`)."""
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
    lines.at = restated.moment(verbs.clock())
    for key, what in restated.pulled(run.state, verdicts(lines), lines.at):
        run.box.send(key, "work-drift", f"work-drift {key}: {what}")
    return lines


def verdicts(lines: Said) -> dict[int, tuple[work.Pull, str]]:
    """Return the `Pull` facet each line of a run of `jmerge` gives its pull request, by number,
    with the line's `why`, the last line of a number winning: `merged` for a merge, with no
    `why`, and for a `wait` or a `hold` the step of `word: reason` (`step`), as the pass reads it
    (`jbus.watch.waits`), or `other` where no rule names the reason, with `word: reason` as the
    `why`, the shape the queue keeps."""
    found = {}
    for text in lines:
        line = parse(text)
        if line is None:
            continue
        if line.word == "merged":
            found[line.number] = (work.Pull.MERGED, "")
        elif line.word in ("wait", "hold") and line.reason:
            why = f"{line.word}: {line.reason}"
            said = step(why)
            found[line.number] = (work.Pull(said) if said else work.Pull.OTHER, why)
    return found


def tick(run: Pass) -> Said:
    """Run `jmerge` for the merge tick (`jbus.tick`), send its lines as `merge` does, and return
    them, `failed` where it did not run to its end.

    It runs with `--if-free`, as the pass does, so a run of the pass's under way makes it do
    nothing. It leaves the `jmerge` streak alone for a run that ended, failed or not: the tick runs
    every few seconds, and the pass's own run each minute is what counts a `jmerge` that does not
    run. A run that held the run lock past `JMERGE_TIMEOUT` and was stopped is the one the tick
    counts itself, since the pass, which does not wait on the lock, cannot see it. A run that did
    not end, busy or failed, is the tick's to try again.
    """
    ran = run.run(*RUN, timeout=JMERGE_TIMEOUT)
    if isinstance(ran, proc.TimedOut):
        _failed(run, lines_of.said(ran))
    return _sent(run, ran)


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
