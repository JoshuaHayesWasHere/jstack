"""Merging is `jmerge`'s job and nobody else's: jbus runs the command and reads its lines.

jbus is the only merger: each pass starts a run of `jmerge` whatever the home's `home-thread`
file says, with no `--home`, so the run judges the pull requests of every home of the repo, and a
home's own run of `jmerge --home` merges nothing. The pass does not wait for its run: the next
pass reads what it printed (`merge`). Between passes the merge tick runs it too, a few seconds
after a check ends (`tick`, `jbus.tick`). `jmerge` holds the repo's run lock for the whole of a
run that may merge, so the pass's run, the tick and a hand run of the user's never run it together
(`jmerge.lock`). The pass's run and the tick both run it with `--if-free`: a run that finds the
lock held does nothing, and neither waits on another's run inside its own timeout.

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

import fcntl
import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from jbus import alert, outbox, pulls, restated, verbs, work
from jbus.judged import Said, parse
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.wake import JMERGE_TIMEOUT
from jmerge import lines as lines_of
from jmerge import lock, ready
from jmerge.asked import Silent
from jmerge.judgement import step
from jmerge.lines import Line as Line
from jsettings import budget, paths, proc
from jsettings.store import read_json, write_json

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
KNOWN = 600
"""How old, in seconds, what GitHub said of its API budget may be for `handed` to go by it."""
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


RUNS = "jmerge-runs"
"""The directory, in a project's state, of the pass's runs of `jmerge`: `GOING`, `STARTED`, the
record of each run that ended and was not read (`ran-<at>.json`), and the last one read (`READ`)."""
GOING = "going.lock"
"""Held by a run's process (`keep`) from its start to its end, so a pass starts no second run.
The kernel gives it back when the process dies."""
STARTED = "started"
"""Written by the pass that starts a run, with when, and removed by the run once its record is
written: a stamp older than `STARTING` that the run's lock does not cover is a run that ended with
no record. A younger one is a run that may not yet hold its lock, and is left to start."""
STARTING = timedelta(minutes=1)
"""How long a run's process has to take `GOING` from its start: a Python's start and an import of
jbus, a second or two on a loaded machine."""
READ = "read.json"
CHILD_LOG = "child.log"
"""What the run's process printed itself, outside the record: the one place a process that died
before `keep` could write a record says why."""
UNIT = "jbus-jmerge-{name}-{digest}"
"""The transient unit of a run started from a pass that systemd runs (`start`). The digest of the
state directory keeps a sandbox's runs apart from the machine's."""
SYSTEMD = ("INVOCATION_ID", "JOURNAL_STREAM", "SYSTEMD_EXEC_PID", "MANAGERPID")
"""The variables systemd sets for one unit, which the run's unit gets of its own."""


def merge(run: Pass) -> Said:
    """Start a run of `jmerge --if-free` where none of the pass's runs is going, and return the
    lines of each run that ended since a pass last read one, sending each line once.

    The run is not the pass's to wait for: it may build a batch and run its guards for many
    minutes, and the pass launches, tells and wakes in the meantime. It runs in a process of its
    own (`start`), which keeps what `jmerge` printed in a record when it ends (`keep`), and the
    first pass after reads the record once (`_records`): what `jmerge` said reaches each step a pass
    late at most. A pass that finds no record returns no line, `failed`, as a busy run did: each
    step keeps what it knew of the rows. `Said.at` is when the run ended, not when it was read.

    A record is read as a run that ended in the pass was. Every line is a quiet event, including a
    `hold` line. `waiting` lists each hold that is the user's. The user learns of a hold when the
    hold joins that list: once for the pull request, not once for each head. `expedite` deals first
    with a hold that a crew can lift.

    A run of the tick's or one by hand may hold the run lock. With `--if-free` the pass's run then
    does nothing and ends at once (`lock.BUSY`): it is no run, so it leaves the `jmerge` streak as
    it was, and the next pass starts it again.

    When `jmerge` does not run, or holds the run lock past `JMERGE_TIMEOUT`, that counts as a
    failure of the `jmerge` streak, and a run of `jmerge` ends the streak. So does a run whose
    process could not be started, or ended with no record. A run that stopped after printing a line
    also ends the streak, as such a run always did, and the pass says that `jmerge` stopped. The
    `Said` of that run is then `failed`, so jbus keeps what it knew of the rows that `jmerge` did
    not reach, as it does for a busy run.
    """
    where = runs(run)
    where.mkdir(parents=True, exist_ok=True)
    if not _going(where) and not _starting(where):
        if (where / STARTED).exists():
            (where / STARTED).unlink()
            _unrun(run, f"its run ended with no record: {_last(where / CHILD_LOG)}")
        (where / STARTED).write_text(restated.moment(verbs.clock()) + "\n")
        if why := start(run):
            (where / STARTED).unlink(missing_ok=True)
            _unrun(run, why)
    return _records(run, where)


def runs(run: Pass) -> Path:
    return run.state / RUNS


def start(run: Pass) -> str:
    """Start `keep` for the project in a process that outlives the pass, with the pass's list for
    `jmerge` (`handed`), and return why it could not start, or nothing.

    A pass that systemd runs is a oneshot unit, and systemd ends every process left in it when the
    pass ends, a new session or not: the run is then a transient unit of its own (`UNIT`), with the
    pass's environment. A pass run by hand starts it in a session of its own.
    """
    where = runs(run)
    child = (sys.executable, "-c", "import sys; from jbus import merge; merge.keep(*sys.argv[1:])")
    child += (str(where), str(run.project.checkout), *handed(run))
    if os.environ.get("INVOCATION_ID"):
        name = re.sub(r"[^A-Za-z0-9_.-]", "-", run.project.name)
        digest = hashlib.sha256(str(where.resolve()).encode()).hexdigest()[:8]
        log = f"truncate:{where / CHILD_LOG}"
        command = ["systemd-run", "--user", "--quiet", "--collect"]
        command += [f"--unit={UNIT.format(name=name, digest=digest)}"]
        command += [f"--working-directory={run.project.checkout}"]
        command += [f"--property=StandardOutput={log}", f"--property=StandardError={log}"]
        command += [f"--setenv={key}" for key in os.environ if key not in SYSTEMD]
        ran = proc.run(*command, "--", *child)
        return lines_of.said(ran) if ran.returncode else ""
    try:
        with open(where / CHILD_LOG, "w") as log:
            subprocess.Popen(
                child,
                cwd=run.project.checkout,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError as error:
        return f"{sys.executable} could not be run: {error.strerror}"
    return ""


def keep(where: str | Path, checkout: str | Path, *more: str) -> None:
    """Run `jmerge --if-free`, with `more`, in `checkout` as the process of one of the pass's runs, holding
    `GOING` for the whole run, and keep what it printed as a record in `where`, written whole
    before the lock is given back. A process that dies first leaves no record, and the next pass
    counts it (`merge`)."""
    where = Path(where)
    with open(where / GOING, "a") as going:
        fcntl.flock(going, fcntl.LOCK_EX)
        ran = proc.run(*RUN, *more, cwd=checkout, timeout=JMERGE_TIMEOUT)
        at = restated.moment(verbs.clock())
        record = {
            "returncode": ran.returncode,
            "stdout": ran.stdout,
            "stderr": ran.stderr,
            "timed_out": isinstance(ran, proc.TimedOut),
            "at": at,
        }
        write_json(where / f"ran-{at}.json", record)
        (where / STARTED).unlink(missing_ok=True)


def _going(where: Path) -> bool:
    """Whether a run's process holds `GOING`."""
    with open(where / GOING, "a") as going:
        try:
            fcntl.flock(going, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def _starting(where: Path) -> bool:
    """Whether a pass started a run within `STARTING`, which may not yet hold `GOING`. A stamp
    that does not parse is no start."""
    try:
        at = datetime.fromisoformat((where / STARTED).read_text().strip())
    except (OSError, ValueError):
        return False
    return verbs.clock() - at < STARTING


def _records(run: Pass, where: Path) -> Said:
    """Read each record of a run that ended and was not read, oldest first, mark it read, and
    return their lines: `failed` and `at` are the newest's. With none, return no line, `failed`,
    at the end of the last run read."""
    said = Said()
    said.failed = True
    for path in sorted(where.glob("ran-*.json")):
        record = read_json(path, {})
        os.replace(path, where / READ)
        made = proc.TimedOut if record.get("timed_out") else subprocess.CompletedProcess
        ran = made(RUN, record["returncode"], record["stdout"], record["stderr"])
        lines = _judged(run, ran, record["at"])
        said.extend(lines)
        said.failed, said.at = lines.failed, lines.at
    if not said.at:
        said.at = str(read_json(where / READ, {}).get("at", ""))
    return said


def _judged(run: Pass, ran: subprocess.CompletedProcess[str], at: str) -> Said:
    """Send each line of a run of `jmerge` that ended at `at`, count it on the `jmerge` streak,
    and return its lines (`merge`)."""
    lines = _sent(run, ran, at=at)
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
        _unrun(run, why)
    return lines


def handed(run: Pass) -> tuple[str, ...]:
    """The flags that hand `jmerge` the pass's read of the open pull requests (`pulls.read`), so
    it asks GitHub for no list of its own: `--pulls <path> --pulls-at <stamp>`. Nothing where the
    read raised `Silent`, and nothing where what GitHub said of its API budget in the last `KNOWN`
    seconds (`budget.logged`, which asks nothing here) does not leave it above the floor: a pass
    asks GitHub nothing under the floor, and `watch.look`, after the run, reads the budget for
    the pass. `jmerge` then asks for its own list, or says why it waits, as a run by hand does."""
    if budget.held(budget.logged(paths.jbus_state_dir(), KNOWN, asked=lambda _: None)):
        return ()
    try:
        opened = pulls.read(run)
    except Silent:
        return ()
    return ("--pulls", str(opened.path), "--pulls-at", opened.at)


def _unrun(run: Pass, why: str) -> None:
    """Say that `jmerge` did not run, and count it on the `jmerge` streak."""
    run.say(f"wait {run.project.name}: jmerge did not run ({why})")
    _failed(run, why)


def _last(path: Path) -> str:
    """The last line of `path`, or that it said nothing."""
    said = path.read_text(errors="replace").strip().splitlines() if path.is_file() else []
    return said[-1].strip() if said else "it said nothing"


def _failed(run: Pass, why: str) -> None:
    """Count one failure of the project's `jmerge` streak, and raise its alert once it is due."""
    streak = alert.jmerge(run.project.name)
    alert.tell(
        run, streak, alert.failed(run.config.state_dir, streak, why, now=run.now, user=run.user)
    )


def _sent(
    run: Pass,
    ran: subprocess.CompletedProcess[str],
    read: dict[int, str] | None = None,
    at: str = "",
) -> Said:
    """Send each line a run of `jmerge` printed about a pull request, once for its key, and
    return them. The run restates each line it judged, and logs as a quiet `work-drift` each one
    the merge tick restated otherwise (`restated.pulled`), with the heads the merge tick read
    (`read`) where it ran it. `at` is when the run ended, where that was before now."""
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
    lines.at = at or restated.moment(verbs.clock())
    for key, what in restated.pulled(run.state, verdicts(lines), lines.at, read):
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


def tick(run: Pass, read: dict[int, str]) -> Said:
    """Run `jmerge` for the merge tick (`jbus.tick`), send its lines as `merge` does, and return
    them, `failed` where it did not run to its end. `read` is the head the tick read of each
    pull request it watches, by number, which a line whose checks the run saw end names.

    It runs with `--if-free`, as the pass does, so a run of the pass's under way makes it do
    nothing. It leaves the `jmerge` streak alone for a run that ended, failed or not: the tick runs
    every few seconds, and the pass's own run, once a pass, is what counts a `jmerge` that does not
    run. A run that held the run lock past `JMERGE_TIMEOUT` and was stopped is the one the tick
    counts itself, since the pass, which does not wait on the lock, cannot see it. A run that did
    not end, busy or failed, is the tick's to try again.
    """
    ran = run.run(*RUN, timeout=JMERGE_TIMEOUT)
    if isinstance(ran, proc.TimedOut):
        _failed(run, lines_of.said(ran))
    return _sent(run, ran, read)


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
