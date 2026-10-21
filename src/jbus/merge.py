"""Merging, which is `jmerge`'s and nobody else's: jbus runs the command and reads its lines.

It runs only when the project's home is off, which is a `home-thread` file that is missing
or empty: a home that is on merges by itself, and two merges at once would race. The pass
lock is held around the run, so two passes never run it together either.

A line `jmerge` prints about a pull request is read by `parse`, which is `jmerge.lines.one`:
`stall` and `watch` read the `Line` it gives, not the text. `rebase` still reads the text of
a `wait` line by itself.

A `hold` is the user's, but for the ones a crew can lift (`UNRULED`, and a merge gate that
did not pass), which `expedite` asks its crew for first. No line is sent to them from here:
`waiting` lists the holds that are theirs.

A sweep is `jmerge`'s too, and jbus only ever asks what one would remove: `SWEEP` is the
one command it runs for it, and it has `--check`.

A reason no rule of `rules` names puts its pull request on no step, and the view shows it
in the Unknown lane. `unplaced` sends the row's home one queued message, once for a row and
a reason text, since the fix is a rule, which a home briefs. It is a quiet event, and the
row is not the user's: it is not in `waiting-on-user.json`. Two reasons are on no step by
design and tell nobody (`OFF_STEP`): another home's pull request and a draft.
"""

from __future__ import annotations

import hashlib
import re
import subprocess

from jbus import alert
from jbus.t3 import Client, T3Error
from jbus.wake import JMERGE_TIMEOUT, Pass
from jmerge import lines as lines_of
from jmerge import ready
from jmerge.lines import Line as Line
from jmerge.lines import one as parse

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
OFF_STEP = (ready.OTHER_HOME, ready.DRAFT)
TOLD = (
    "jbus: the view cannot place {slug}. jmerge said of its pull request #{number} `{said}`, "
    "and `merge.rules` in src/jbus/merge.py has no rule for it, so it shows in the Unknown "
    "lane. Brief the fix and queue it: the reason as a named `Reason` in src/jmerge/ready.py, "
    "which names the step it puts it on. {user} is not asked: send {user} "
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
    """The `(step, pattern)` of each reason `jmerge` writes, in the order they are tried:
    `ELSEWHERE`, then each `ready.Reason` from the start of the reason, where it is declared.

    `ELSEWHERE` is what `jmerge` writes from outside `ready` (its run, its proof and its
    range-diff), and what an older `jmerge` wrote, which a log still holds. It comes first:
    `ready.MAIN_CHANGED` with `it needs a rebase`, which `jmerge` says of a guarded path, is
    on the rebase step."""
    return ELSEWHERE + tuple((one.step, "^" + one.pattern) for one in ready.reasons().values())


def step(said: str) -> str:
    """The step a pull request waits on, from what `jmerge` last said of it, `<word>: <reason>`:
    a `hold` is `hold`, and a `wait` is on the first step of `rules` whose pattern its reason
    matches. Nothing for a line with no reason, or a reason no rule names."""
    word, _, reason = said.partition(": ")
    if not reason:
        return ""
    if word == "hold":
        return "hold"
    reason = _GUARDED.sub("", reason)
    return next((step for step, pattern in rules() if re.search(pattern, reason)), "")


class Said(list[str]):
    """The lines `jmerge` printed about a pull request in this pass, as it printed them.

    `failed` is a `jmerge` that did not run to its end: a pull request it has no line for
    is one it did not get to, which is not one that it ran past with nothing to say.
    """

    failed = False

    def crews(self, numbers: set[int]) -> Said:
        """The lines as the user is to hear them: a hold of one of these pull requests is its
        crew's for now, so it is a `wait`. The line stays, since a pull request with no line
        is one `jmerge` did not reach, which keeps the hold it had."""
        mine = {text for text in self if (line := parse(text)) and line.number in numbers}
        kept = Said(
            "wait" + text[4:] if text in mine and text[:5] == "hold " else text for text in self
        )
        kept.failed = self.failed
        return kept


def home_thread(run: Pass) -> str:
    try:
        return (run.home / "home-thread").read_text().strip()
    except OSError:
        return ""


def merge(run: Pass) -> Said:
    """Run `jmerge` and send each line it prints about a pull request. The lines come back.

    Every line is a quiet event, a `hold` line too: `waiting` lists a hold that is the
    user's, and the list gaining it is what tells them, once for the pull request and not
    once for each head. A hold a crew can lift is `expedite`'s first.
    A `jmerge` that did not run is a failure of the `jmerge` streak, and one that ran ends it.
    One that stopped after it printed a line ends the streak too, as it always did, and is
    said: the lines are `failed`, which keeps what was known of the rows it did not reach.
    """
    home = home_thread(run)
    if home:
        run.say(f"skipped {run.project.name}: the home {home} merges")
        return Said()
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
            run.say(f"wait {name}: jmerge stopped after {len(lines)} lines ({_why(ran)})")
        alert.tell(run, streak, alert.ok(run.config.state_dir, streak, user=run.user))
        return lines
    if _NO_LIST.search(why := _why(ran)):
        run.condition(name, NO_LIST, why, key=f"protected {run.day}")
    else:
        run.say(f"wait {name}: jmerge did not run ({why})")
        alert.tell(
            run, streak, alert.failed(run.config.state_dir, streak, why, now=run.now, user=run.user)
        )
    return lines


def _why(ran: subprocess.CompletedProcess[str]) -> str:
    said = (ran.stderr or ran.stdout).strip().splitlines()
    return said[-1].strip() if said else str(ran.returncode)


def sweep(run: Pass) -> tuple[bool, str]:
    """Ask `jmerge` what a sweep would remove, and send its lines when there are any.

    Nothing is removed: the command is `SWEEP`, with `--check`. The answer is whether
    `jmerge` ran, and one line of how it went, for the status file.
    """
    ran = run.run(*SWEEP)
    if ran.returncode:
        return False, f"{' '.join(SWEEP)} did not run ({_why(ran)})"
    lines = [line.strip() for line in ran.stdout.splitlines() if line.startswith("removable ")]
    found = f"{len(lines)} to remove"
    if lines:
        run.box.send("", "sweep", f"sweep {run.project.name}: {found}", "\n".join(lines))
    return True, found


def unplaced(run: Pass, client: Client, slug: str, number: str, said: str, thread: str) -> None:
    """Tell the home of a row whose pull request is on no step, once for the row and what
    `jmerge` said of it, `<word>: <reason>`. `thread` is the home's, or nothing where it has
    none. A message that did not go is sent again on the next pass."""
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
    client.recipients = client.recipients | {thread}
    asked = {"threadId": thread, "message": text, "mode": "queue"}
    try:
        client.call("t3_thread_send", {**asked, "clientRequestId": f"{UNPLACED}|{slug}|{digest}"})
    except T3Error as error:
        run.say(f"wait {slug}: its home could not be told that no rule names its reason ({error})")
        return
    line = f"{UNPLACED} {slug}: told its home, thread {thread}, that no rule names `{said}`"
    run.find(slug, UNPLACED, line, text, key=digest)
    run.say(line)
