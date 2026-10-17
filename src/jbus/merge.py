"""Merging, which is `jmerge`'s and nobody else's: jbus runs the command and reads its lines.

It runs only when the project's home is off, which is a `home-thread` file that is missing
or empty: a home that is on merges by itself, and two merges at once would race. The pass
lock is held around the run, so two passes never run it together either.

A line `jmerge` prints about a pull request is read by `parse`: `stall` and `watch` read
the `Line` it gives, not the text. `rebase` still reads the text of a `wait` line by itself.

A `hold` is the user's, but for the one a crew can lift (`UNRULED`), which `expedite` asks
its crew for first. No line is sent to them from here: `waiting` lists the holds that are
theirs.

A sweep is `jmerge`'s too, and jbus only ever asks what one would remove: `SWEEP` is the
one command it runs for it, and it has `--check`.

A reason no rule of `RULES` names puts its pull request on no step, and the view shows it
in the Unknown lane. `unplaced` sends the row's home one queued message, once for a row and
a reason text, since the fix is a rule, which a home briefs. It is a quiet event, and the
row is not the user's: it is not in `waiting-on-user.json`. Two reasons are on no step by
design and tell nobody (`OFF_STEP`): another home's pull request and a draft.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass

from jbus import alert
from jbus.t3 import Client, T3Error
from jbus.wake import JMERGE_TIMEOUT, Pass
from jmerge import ready

EVENTS = {"jmerge": "quiet", "sweep": "quiet", "unplaced": "quiet"}
_LINE = re.compile(r"^(merged|wait|hold|refused) (\d+)\b(?: (\S+)(?: (.+))?)?")
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
    "and `merge.RULES` in src/jbus/merge.py has no rule for it, so it shows in the Unknown "
    "lane. Brief the fix and queue it: the reason as a named constant in src/jmerge/ready.py, "
    "and a rule in `merge.RULES` that puts it on its step. {user} is not asked: send {user} "
    "nothing about it. A question only {user} can answer is a gate: take the default and pipe "
    "it to `jbus gate <the fix's slug>`."
)


@dataclass(frozen=True)
class Line:
    """A line `jmerge` prints about a pull request: `<word> <number> <name>: <reason>`.

    `word` is `merged`, `wait` or `hold`, or the `refused` of an accept. `name` is the word
    after the number, the pull request's URL or the merged slug with no comma after it,
    and `reason` is what follows its colon. A line with no name has neither, and one with
    no colon has no reason.
    """

    word: str
    number: int
    name: str = ""
    reason: str = ""


def parse(text: str) -> Line | None:
    """The `Line` a line of `jmerge` is, or nothing where it is not about a pull request."""
    found = _LINE.match(text.strip())
    if not found:
        return None
    word, number, name, rest = found.groups()
    if rest and len(name) > 1 and name.endswith(":"):
        return Line(word, int(number), name[:-1], rest)
    return Line(word, int(number), (name or "").rstrip(","))


RULES = (
    ("hold", r"^needs [^\s,]+, |needs the user's word|which the user lands|^its base is "),
    ("hold", r"a stack its brief does not name|auto-merge is off|held a third rebase"),
    ("proof", r"no proven safety fact"),
    ("second", r"second pass is not written|the rebase changed the (content|patch) after"),
    ("second", r"scoped review has not ruled|not the one its review saw|no head to compare"),
    ("second", r"scoped review of it is not written"),
    ("rebase", r"needs a rebase|^the rebase dropped|conflicts with (its base|today's)"),
    ("rebase", r"fails on \S+ over today's|^its Rebase line"),
    ("check", r"check has not (passed|finished)|fresh check|GitHub has not decided"),
    ("check", r"its check has no start time|could not be fetched|moved while it was judged"),
    ("check", r"jmerge's (own )?rules"),
    ("findings", r"findings are not handled|^its head moved after|^its Fixed line"),
    ("findings", r"have no Finding line"),
    ("review", r"no review yet|review has no verdict"),
    ("result", r"^no brief has a Result that names it"),
    ("result", "^" + re.escape(ready.SKILLS_UNRUN).replace(r"\{names\}", ".+")),
)
_RULES = tuple((step, re.compile(pattern)) for step, pattern in RULES)
_GUARDED = re.compile(r"^guarded \(touches [^)]*\), ")


def step(said: str) -> str:
    """The step a pull request waits on, from what `jmerge` last said of it, `<word>: <reason>`:
    a `hold` is `hold`, and a `wait` is on the first step of `RULES` whose pattern its reason
    matches. Nothing for a line with no reason, or a reason no rule names."""
    word, _, reason = said.partition(": ")
    if not reason:
        return ""
    if word == "hold":
        return "hold"
    reason = _GUARDED.sub("", reason)
    return next((step for step, pattern in _RULES if pattern.search(reason)), "")


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
