"""Read a home's state directory: its handoff, its plan entries, its briefs and their results.

The shapes are the ones that the `home`, `crew` and `handoff` skills write. Everything here
comes from the files alone, and nothing asks T3 or the forge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jbriefs import asks, below, findings, paths, skills, standing, why
from jbriefs import status as status_line
from jbriefs.crowded import crowded
from jbriefs.meets import done_when
from jbriefs.paths import covers, named
from jbriefs.proof import Proof, proof, shown, user_sees
from jbriefs.runnable import runnable
from jbriefs.status import Status
from jsettings.brief import head as head

NO_RESULT = "no result yet"
DONE = "done"
NOT_DONE = "not done"
BLOCKED = "blocked"
PAUSED = "paused"
UNCLEAR = "unclear"
_STATES = (Status.DONE, Status.NOT_DONE, Status.BLOCKED, Status.PAUSED)

_ENTRY = re.compile(r"^## (?P<slug>[A-Za-z0-9][A-Za-z0-9._-]*): (?P<title>.+)$")
_BRIEF_TITLE = re.compile(r"^# [^:\n]+: (?P<title>.+)$", re.MULTILINE)
_RESULT = re.compile(r"^## (?P<heading>Result\b.*)$", re.MULTILINE)
_PULL_REQUEST = re.compile(r"^(?:.*\s)?Pull request:[ \t]*(?P<named>.*)$", re.MULTILINE)
_URL = re.compile(r"https?://[^\s)>\]`]+")
_REPORTED = re.compile(r"^Playbook:[ \t]*(?P<said>.*)$", re.MULTILINE)
_STEP = re.compile(r"(?P<number>\d+) (?:done|skip: (?P<skip>\S.*))")
SIZES = ("S", "M", "L")
_SIZES = "(S, M or L)"


@dataclass(frozen=True)
class Entry:
    """One `## <slug>: <one line>` section of plan.md. `status` is what its `Stage:` line
    says, or what the `Status:` line of an older plan says."""

    slug: str
    title: str
    status: str
    done_when: tuple[str, ...]

    @property
    def open(self) -> bool:
        return not self.status.lower().startswith("done")


@dataclass(frozen=True)
class PullRequest:
    text: str
    url: str | None


@dataclass(frozen=True)
class Step:
    """One step that a Result's `Playbook:` line reports. `skip` is the reason the crewmate did
    not do it, and is empty for a step that the crewmate did."""

    number: int
    skip: str = ""


@dataclass(frozen=True)
class Steps:
    """A Result's `Playbook:` line: the playbook's name, or `none`, and the report on each step.
    `fault` says why the line is not in the template's shape, and is empty when it is."""

    name: str
    steps: tuple[Step, ...] = ()
    fault: str = ""


def steps(said: str) -> Steps:
    """Read what a `Playbook:` line says, without its label. The line gives the name, then `; `
    and each step as `<n> done` or `<n> skip: <reason>`, numbered in order from 1 to the last."""
    name, *parts = [part.strip() for part in said.split(";")]
    if not name or name.startswith("<"):
        return Steps(name, fault="names no playbook")
    if name == "none":
        return Steps(name, fault="reports steps of no playbook" if parts else "")
    if not parts:
        return Steps(name, fault="reports no step")
    found = []
    for part in parts:
        step = _STEP.fullmatch(part)
        if not step:
            return Steps(
                name, tuple(found), f"has `{part}`, not `<n> done` or `<n> skip: <reason>`"
            )
        found.append(Step(int(step["number"]), (step["skip"] or "").strip()))
    if [step.number for step in found] != list(range(1, len(found) + 1)):
        return Steps(name, tuple(found), "does not number its steps 1 to the last in order")
    return Steps(name, tuple(found))


@dataclass(frozen=True)
class Result:
    """One `## Result` section that a crewmate appended to its brief."""

    heading: str
    text: str

    @property
    def state(self) -> str:
        said = status_line.of(self.text)
        return said.value if said in _STATES else UNCLEAR

    @property
    def pull_request(self) -> PullRequest | None:
        found = _PULL_REQUEST.search(self.text)
        named = found["named"].strip() if found else ""
        if not named or named.lower().startswith("none"):
            return None
        url = _URL.search(named)
        return PullRequest(named, url[0].rstrip(".,;:*") if url else None)

    @property
    def playbook(self) -> Steps | None:
        """The steps that the `Playbook:` line reports, or None for a Result with no such line."""
        found = _REPORTED.search(self.text)
        return steps(found["said"]) if found else None


def thread_of(text: str) -> str:
    """The thread id on a brief's first `Thread:` line, wherever it sits, as the skills read it.
    It is an empty string for a brief with none."""
    return "".join(below.line(text, "Thread:").split()[:1])


def proves_it(text: str) -> Proof | None:
    """The first `Proves it:` line of a brief's head, judged, or None for a brief with none."""
    said = head(text, "Proves it:")
    return None if said is None else proof(said)


def _template(said: str) -> bool:
    return said.startswith("<") or "|" in said


def sized(text: str) -> str:
    """Why a brief's `Size:` line names no t-shirt size, in one line. It is an empty string
    when the line names a size.

    Step 4 of the feature playbook reads the size to decide on a design read. So this check
    refuses a brief with no line. Before the line existed, every brief counted as S, and a
    brief with no line would still count as S.
    """
    said = head(text, "Size:")
    if said is None:
        fault = "brief has no Size: line"
    elif not said:
        fault = "brief's Size: line is empty"
    elif _template(said):
        fault = "brief's Size: line is the template's own text"
    elif said not in SIZES:
        fault = f"brief's Size: line says {said}"
    else:
        return ""
    return f"{fault} {_SIZES}"


def crewmates(name: str) -> bool:
    """Whether a brief may name `playbooks/<name>.md`. Its `Run by:` line must say that a
    crewmate runs it, and it must not be the one playbook that no brief may name."""
    try:
        text = skills.where("playbook", name).read_text()
    except (LookupError, OSError):
        return False
    by = next((line for line in text.splitlines() if line.startswith("Run by: ")), "")
    return by.startswith("Run by: a crewmate,") and "never picked for a brief" not in by


def playbook_named(text: str) -> str:
    """The name that the `Playbook:` line of a brief, a request or a plan gives. It is the
    first word of the first such line of its head. It is nothing when the head has no such
    line, or when the line is empty. `jbus playbook` opens the file it names, and this
    function is the one reader of the line."""
    said = head(text, "Playbook:")
    return said.split()[0] if said else ""


def playbook(text: str) -> str:
    """Why a brief's `Playbook:` line names no playbook, as one line. It is an empty string when
    it names one.

    The name is the line's first word, as `jbus playbook` reads it. It must be a crewmate's
    file of `playbooks/` without its `.md`, never `none`: its fault names the home's table.
    """
    said = head(text, "Playbook:")
    name = playbook_named(text)
    if said is None:
        return f"brief has no Playbook: line {skills.TABLE}"
    if name.rstrip(".,;:").lower() == "none":
        fault = "says none"
    elif not said:
        fault = "is empty"
    elif _template(said):
        fault = "is the template's own text"
    elif name not in skills.listed("playbook"):
        fault = f"names {name}, which is no file in playbooks/"
    elif not crewmates(name):
        fault = f"names {name}, which is not a crewmate's playbook"
    else:
        return asks.fault(text, name)
    return f"brief's Playbook: line {fault} {skills.TABLE}"


NO_DESIGN = "brief's Design: line gives no design call (run /architect or say none, <why>)"
_NONE = re.compile(r"none[ \t]*,[ \t]*\S", re.I)
_DESIGN = re.compile(r"[\w/~-]{2,}\.[A-Za-z0-9]{2,}")


def designed(text: str) -> str:
    """Why a brief has no design call, as one line. It is an empty string when it has one.

    The first `Design:` line of its head gives the call: the path of the design the brief
    was written from, a file with its extension, or `none, <why>`. A brief with no such line
    needs no design, as `none` would say. A `none` with no reason gives no call. Neither does
    a word that names no file (`TBD`, `n/a`), or the template's own line left unchanged.
    """
    said = head(text, "Design:")
    if said is None:
        return ""
    named = not said.startswith("<") and _DESIGN.search(said)
    return "" if _NONE.match(said) or named else NO_DESIGN


TITLE = "title"
REST = "the rest"
_LABEL = re.compile(r"(?P<label>[A-Z][A-Za-z]*(?:[ -][A-Za-z]+){0,3}):(?:[ \t]|$)")
REQUIRED = (
    "Task",
    "Why",
    "Done when",
    "Proves it",
    "Size",
    "Where",
    "Pull request",
    "Review",
    "Playbook",
)


def fields(text: str) -> list[tuple[str, list[str]]]:
    """A brief as its fields, in order: each label with the lines under it.

    A line of the head (the lines above the first `## `) that starts `<Label>: ` starts a
    field, and the text after the label is the field's first line. Every other line
    continues the field above it, so a `Done when:` list and a re-wrapped line each make one
    field. The `# <slug>: <title>` line is `TITLE`, text above any label goes under the label
    `""`, and the first `## ` and everything under it are `REST`.
    """
    found: list[tuple[str, list[str]]] = []
    head = True
    for line in text.splitlines():
        if head and line.startswith("## "):
            head = False
            found.append((REST, [line]))
        elif not head:
            found[-1][1].append(line)
        elif not found and line.startswith("# "):
            found.append((TITLE, [line.removeprefix("# ")]))
        elif label := _LABEL.match(line):
            found.append((label["label"], [line[label.end() :]]))
        elif found:
            found[-1][1].append(line)
        elif line.strip():
            found.append(("", [line]))
    return found


_MARKER = re.compile(r"""^[\s"'“‘*+-]+""")
_PLACEHOLDER = re.compile(r"""<[^<>]*>[\s"'”’.,;:]*""")
_CHOICES = ("Pull request", "Review")
_PULL_REQUESTS = re.compile(r"(open one|ask first|none)\b")
"""How a `Pull request:` line starts: jbus owes one only on `open one` (`watch.owes_pull`)."""


def _filled(text: str, label: str) -> str:
    """Why the brief's `<label>:` field is not filled in, as one line. It is an empty string
    when it is.

    A field is not filled in when its first line, or an item of a list under it, is still
    the template's whole placeholder (`<...>`, without its quote or list marker). A field of
    `_CHOICES` that still offers its choices (`review | none`) is not filled in either, nor a
    `Pull request:` line not of `_PULL_REQUESTS` (`after the review`). A line that only starts
    with `<` (`<200 ms`) is filled in, and so is a field with the template's notes under it.
    """
    held = [lines for name, lines in fields(text) if name == label]
    if not held:
        return f"brief has no {label}: line"
    first, *rest = held[0]
    lines = [first] + [line for line in rest if _MARKER.match(line) and line.strip()[:1] in "-*+"]
    lines = [_MARKER.sub("", line).strip() for line in lines]
    lines = [line for line in lines if line]
    if not lines:
        return f"brief's {label}: line is empty"
    if any(_PLACEHOLDER.fullmatch(line) for line in lines) or (
        label in _CHOICES and "|" in lines[0]
    ):
        return f"brief's {label}: line is the template's own text"
    if label == "Pull request" and not _PULL_REQUESTS.match(lines[0]):
        return (
            f"brief's Pull request: line says {lines[0]}, and begins with none of the "
            "template's choices: `open one when done`, `ask first` or `none, <why>`"
        )
    return ""


def proven(text: str) -> str:
    """Why a brief's `Proves it:` line proves nothing, as one line. It is an empty string when
    it proves something.

    A brief with no such line gets nothing here. A brief that reaches a launch with no such
    line was written before the template asked for the line, and `faults` reports that the
    line is missing.
    """
    found = proves_it(text)
    return found.why if found and not found.was else ""


def proof_runs(text: str) -> str:
    """Why a brief's `Proves it:` line names only what proof.py once took as a proof and no
    longer does, as one line (`Proof.was`): CI, the user with no `judged: <why>`, or a test by
    the word alone. It is an empty string for any other line, which `proven` judges."""
    found = proves_it(text)
    return found.why if found and found.was else ""


_SLOT = re.compile(r"^jgauge\s+test-slot\s+--\s+")
_BARE_CHECK = re.compile(r"\bmake check(?![-\w])")


def check_command(fresh_check: str) -> str:
    """The repo's check command: the first line of its `fresh-check`, with the `jgauge test-slot
    --` it takes a slot by left off, or an empty string when the file names none."""
    first = "".join(fresh_check.strip().splitlines()[:1]).strip()
    return _SLOT.sub("", first)


def check_asked(text: str, fresh_check: str) -> str:
    """Why a brief's `Done when:` asks for the wrong check, as one line. It is an empty string
    when it does not.

    The repo's `fresh-check` names its check command. When that command is not a bare
    `make check`, a `Done when:` item that asks for a bare `make check` sends a crewmate to run
    the full suite instead of the named command. Where the command is a `make check-fast`,
    `desk_suite` warns of that line instead.
    """
    command = check_command(fresh_check)
    if not command or _BARE_CHECK.fullmatch(command) or _SELECTS.match(command):
        return ""
    if not any(_BARE_CHECK.search(item) for item in done_when(text.splitlines())):
        return ""
    return (
        f"brief's Done when: asks for `make check`, and fresh-check names the check command "
        f"`{command}`: a check line names the check command (`fresh-check`)"
    )


_SELECTS = re.compile(r"make check-fast\b")
_WHOLE = re.compile(r"\bmake check-fast\b(?![^`\n]*\bPART=)")


def desk_suite(text: str, fresh_check: str) -> str:
    """Why a brief's `Proves it:` or `Done when:` asks a crewmate to run the whole suite at the
    desk, as one line. It is an empty string when it does not.

    A `make check-fast` with no `PART=` runs every test the branch selects, and CI's check on
    the pull request runs the same again: the desk's check is the touched one
    (`crew/do-the-task.md`). A bare `make check` asks for the same where `fresh-check` names a
    `make check-fast`, the check of a repo whose check selects its tests. It is a warning and no
    fault: a task about the suite itself may need the whole run.
    """
    selects = bool(_SELECTS.match(check_command(fresh_check)))
    lines = [("Done when", item) for item in done_when(text.splitlines())]
    lines.append(("Proves it", _head_lines(text, "Proves it") or ""))
    labels = dict.fromkeys(
        label
        for label, line in lines
        if _WHOLE.search(line) or (selects and _BARE_CHECK.search(line))
    )
    if not labels:
        return ""
    return (
        f"brief's {' and '.join(f'{label}:' for label in labels)} runs the whole suite at the "
        "desk (`make check-fast` with no `PART=`, or `make check`): a crewmate's desk check is "
        "the touched check, `make check-fast BASE=<base> PART=touched`, and the whole suite is "
        "CI's check on the pull request"
    )


def _head_lines(text: str, label: str) -> str | None:
    """The head field `<label>`: its first line and the lines under it, joined by a space."""
    for name, lines in fields(text):
        if name == label:
            return " ".join(line.strip() for line in lines)
    return None


def where(text: str, label: str = "Where") -> tuple[str, ...]:
    """The paths and globs that the head's `Where:` line names (`jbriefs.paths.named`), or that
    another head line names, such as `Do not touch:`."""
    line = _head_lines(text, label)
    return () if line is None else named(line)


def reach(text: str) -> tuple[str, ...]:
    """The paths a brief may change: its `Where:` and the docs it reaches (`paths.reach`)."""
    return paths.reach(where(text), where(text, "Do not touch"))


def shared_where(text: str, other: str) -> tuple[str, ...]:
    """The paths that both briefs' `Where:` lines cover (`covers`), the narrower where one names a
    directory and the other a file under it. A brief whose `Where:` is the whole repo (`.`) says
    nothing of what it shares."""
    mine, theirs = where(text), where(other)
    if "." in mine or "." in theirs:
        return ()
    found = (path for path in (*mine, *theirs) if covers(mine, path) and covers(theirs, path))
    return tuple(dict.fromkeys(found))


def wheres(text: str) -> str:
    """Why a brief's `Where:` line names no path, as one line. It quotes the `Where:` line. It
    is an empty string when it names one.

    `_filled` handles a brief with no line, or with the template's own text.
    """
    line = _head_lines(text, "Where")
    if line is None or _filled(text, "Where") or where(text):
        return ""
    return (
        "brief's Where: line names no path under the repo, so a changed file cannot be "
        f"told from one outside it (write each path or directory in backticks): {line}"
    )


_SLUG = re.compile(r"^# (?P<slug>[A-Za-z0-9][A-Za-z0-9._-]*):", re.MULTILINE)


def lands(text: str) -> str:
    """Why a `Done when:` item cannot be met inside the brief, as one line: the first item whose
    `(in ...)` marker names a file outside `reach`, or one that `Do not touch:` covers. It is an
    empty string when every marked file is inside, and for a brief whose `Where:` names no path,
    which `wheres` refuses.

    The marker is the writer's word for the file the goal lands in: the check reads nothing else
    of the item, since most items name files they only read or run.
    """
    inside, kept = reach(text), where(text, "Do not touch")
    if not inside:
        return ""
    slug = found["slug"] if (found := _SLUG.search(text)) else "<this row's slug>"
    remedy = (
        f'move the line to a follow-up brief with a "Follows: {slug}" line and queue it with '
        "jbus queue add, where it is approved on this row's go"
    )
    for number, item in enumerate(done_when(text.splitlines()), 1):
        for path in paths.lands_in(item) or ():
            said = f"brief's Done when {number} lands in {path}"
            if not covers(inside, path):
                return (
                    f"{said}, outside Where ({', '.join(inside)}): widen Where to it, or {remedy}"
                )
            if covers(kept, path):
                return (
                    f"{said}, under Do not touch ({', '.join(kept)}): take it off Do not touch, "
                    f"or {remedy}"
                )
    return ""


def unmarked(text: str) -> str:
    """Why items of a brief's `Done when:` list say no file they land in (`lands`), as one line:
    how many, and the first. It is an empty string when every item ends with its marker."""
    items = done_when(text.splitlines())
    bare = [item for item in items if paths.lands_in(item) is None]
    if not bare:
        return ""
    return (
        f"brief's Done when: has {len(bare)} of {len(items)} items that say no file they land "
        f"in, the first: {bare[0]} (end each with (in `<path>`), the file the goal needs "
        "changed, or (in none))"
    )


LONGEST = 2000


def overlong(text: str, label: str) -> str:
    """Why the `<label>:` field of a brief or a request is too long, as one line. It is an empty
    string when the field has `LONGEST` characters or fewer, or when there is no such field.

    The field is as `fields` reads it, its lines joined by one space. A line this long is a
    pasted transcript or a design, which belongs in a file that the line names: the thread reads
    the field as the task, and a home or a bot that pastes a conversation into it sends the
    thread the whole conversation as its task.
    """
    held = [lines for name, lines in fields(text) if name == label]
    if not held:
        return ""
    said = " ".join(line.strip() for line in held[0]).strip()
    if len(said) <= LONGEST:
        return ""
    return (
        f"{label}: line is {len(said)} characters, over the {LONGEST} it may have: put a "
        "transcript or a long text in a file, and name the file on the line"
    )


def tasked(text: str) -> str:
    """Why a brief's `Task:` line is too long, as one line (`overlong`)."""
    said = overlong(text, "Task")
    return f"brief's {said}" if said else ""


REVIEWS = (findings.TWICE, findings.REVIEW, findings.NONE)
_REVIEWS = "(review or none)"


def reviewed(text: str) -> str:
    """Why a brief's `Review:` line is not one of `REVIEWS`, as one line. It is an empty string
    when it is.

    The line is the one word and nothing else. The crew reads its first word, and reads any word
    it does not know as `review` (`findings.mode_of`), so `standard` would launch a reviewer
    unasked and `none, docs only` would too. A stored brief with an older word keeps it, and
    `twice` is still taken, so a brief written before one round retired it queues, and reads as
    `review`.
    `cleanup` is the day's warnings row's, which only jbus files: a brief whose `Decisions:` line
    begins `findings.CLEANUP_DECIDED` may say it, and no other.
    """
    said = head(text, "Review:") or ""
    if said == findings.CLEANUP and (head(text, "Decisions:") or "").startswith(
        findings.CLEANUP_DECIDED.strip()
    ):
        return ""
    return "" if said in REVIEWS else f"brief's Review: line says {said} {_REVIEWS}"


DEEPER = ("perf-issue", "hillclimb", "runtime-forensics", "eval")
"""The crewmate's playbooks that the home skill's deeper step runs on
(`home/skills/home/handing-a-task-to-a-crewmate.md`), which writes the brief's `Read:` and
`Instruments:` lines. The step's scout playbooks go on a request, never on a brief."""
_KINDS = re.compile(r"\b(research|perf|performance|analysis|outcome)\b", re.I)
_DEEPER = (
    "(Read: the rawest material to start from, Instruments: each method with the command that "
    "runs it here)"
)


def instrumented(text: str) -> str:
    """Why a brief for research, perf, analysis or outcome work lacks the lines its crewmate
    starts from, as one line. It is an empty string when it has them, or is no such work.

    The work is the deeper kind when the `Playbook:` line names one of `DEEPER`, or when the
    `Task:` line names the kind in so many words. Such a brief has a filled-in `Read:` line,
    where to start looking, and `Instruments:`, the methods and the commands that run them.
    """
    name = playbook_named(text)
    task = _KINDS.search(_head_lines(text, "Task") or "")
    if name in DEEPER:
        where, kind = "Playbook: line", name
    elif task:
        where, kind = "Task: line", task[0].lower()
    else:
        return ""
    lacks = [label for label in ("Read", "Instruments") if _filled(text, label)]
    if not lacks:
        return ""
    lines = " and ".join(f"{label}:" for label in lacks) + (" lines" if len(lacks) > 1 else " line")
    return f"brief's {where} names {kind} work, and the brief has no filled-in {lines} {_DEEPER}"


def warnings(text: str, fresh_check: str) -> list[str]:
    """What `jbus queue add` and `jbus queue check` warn of in a brief they still queue, one
    line each: a check line asking for the wrong command (`check_asked`), the whole suite at the
    desk (`desk_suite`), a long `Done when:` list (`crowded`), and `Review: none` on a brief whose
    pull request opens, which no reviewer reads and `jmerge` leaves to wait for the user's word
    (`crew/the-review.md`). Each check of `WARNED` warns here too, in place of its fault."""
    found = [
        check_asked(text, fresh_check),
        desk_suite(text, fresh_check),
        user_sees(where(text), _head_lines(text, "Proves it") or ""),
        crowded(text),
        *(check(text) for check in WARNED),
    ]
    opens = head(text, "Pull request:") == "open one when done"
    if opens and head(text, "Review:") == findings.NONE:
        found.append(
            "brief says Review: none and Pull request: open one when done: no reviewer runs, and "
            "jmerge leaves the pull request to wait for the user's word"
        )
    return [one for one in found if one]


CHECKS = (
    ("Task", tasked),
    ("Why", lambda text: why.fault(fields(text))),
    ("Design", designed),
    ("Done when", runnable),
    ("Done when", unmarked),
    ("Done when", lands),
    ("Done when", shown),
    ("Proves it", proven),
    ("Proves it", proof_runs),
    ("Skills", skills.fault),
    ("Size", sized),
    ("Review", reviewed),
    ("Playbook", playbook),
    ("Where", wheres),
    ("Instruments", instrumented),
    ("Builds on", lambda text: standing.layered(fields(text))),
    ("Load", lambda text: standing.load(one for one in fields(text) if one[0] != REST)),
)
WARNED = (runnable, unmarked, proof_runs)
"""The checks of `CHECKS` that warn first: `jbus queue add` queues a brief they find at fault,
and prints the fault as a warning (`warnings`). A check taken out of `WARNED` refuses the brief
as the other checks do, and a row already approved keeps its go all the same (`jbus.queue`)."""
_SAYS_MISSING = ("Design", "Size", "Skills", "Playbook", "Instruments", "Builds on", "Load")


def faults(text: str) -> list[str]:
    """Every reason a brief may not be queued, one line for each field at fault.

    It checks that each field of `REQUIRED` but those of `_SAYS_MISSING` is filled in, then runs
    every check of each field (`CHECKS`), the first fault of a field the one it gives, but a check
    of `WARNED`, which only warns. The checks of `Size`, `Skills` and `Playbook` report a missing
    line themselves, the last two with the home's table (`skills.TABLE`). `Why` is refused
    missing as any field of `REQUIRED` is, and as a repeat of the title and `Task` (`why`). A
    brief needs no `Design:` line, as `none` would say, `Instruments:` only for the deeper work
    (`instrumented`), and no `Builds on` or `Load` line. A brief with no fault is complete. This
    check runs when a row is first queued and not again at a launch, so a brief that already has
    a go launches without being checked again (`jbus.queue`).
    """
    labels = dict.fromkeys((*REQUIRED, *(label for label, _ in CHECKS)))
    found = []
    for label in labels:
        fault = "" if label in _SAYS_MISSING else _filled(text, label)
        checks = (check for name, check in CHECKS if name == label and check not in WARNED)
        fault = fault or next((said for check in checks if (said := check(text))), "")
        if fault:
            found.append(fault)
    return found


@dataclass(frozen=True)
class Brief:
    """One `tasks/<slug>.md`: the brief that the home wrote, then the crewmate's results."""

    slug: str
    title: str
    body: str
    results: tuple[Result, ...]
    thread: str | None

    @property
    def state(self) -> str:
        return self.results[-1].state if self.results else NO_RESULT

    @property
    def pull_request(self) -> PullRequest | None:
        for result in reversed(self.results):
            if result.pull_request:
                return result.pull_request
        return None

    @property
    def proof(self) -> Proof | None:
        return proves_it(self.body)

    @property
    def thread_title(self) -> str | None:
        """The thread's title in T3's left bar, where the home skill's launch puts it."""
        return f"crew: {self.slug}" if self.thread else None


@dataclass(frozen=True)
class Handoff:
    title: str
    sections: dict[str, str]

    def section(self, heading: str) -> str:
        return self.sections.get(heading, "")


@dataclass(frozen=True)
class Repo:
    name: str
    handoff: Handoff | None
    entries: tuple[Entry, ...]
    briefs: tuple[Brief, ...]

    @property
    def live(self) -> list[tuple[Entry, Brief | None]]:
        by_slug = {brief.slug: brief for brief in self.briefs}
        return [(entry, by_slug.get(entry.slug)) for entry in self.entries if entry.open]

    @property
    def cleared(self) -> list[Brief]:
        open_slugs = {entry.slug for entry in self.entries if entry.open}
        return [brief for brief in self.briefs if brief.slug not in open_slugs]


def sections(text: str) -> list[tuple[str, list[str]]]:
    """Each `## ` heading line, as written, with the lines under it, in order. Lines above the
    first heading are in none."""
    found: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            found.append((line, []))
        elif found:
            found[-1][1].append(line)
    return found


def plan_entries(text: str) -> list[Entry]:
    entries = []
    for heading, lines in sections(text):
        found = _ENTRY.match(heading)
        if not found:
            continue
        status = next((line for line in lines if line.startswith(("Stage:", "Status:"))), "")
        entries.append(
            Entry(
                slug=found["slug"],
                title=found["title"].strip(),
                status=status.partition(":")[2].strip(),
                done_when=done_when(lines),
            )
        )
    return entries


def brief(slug: str, text: str) -> Brief:
    marks = list(_RESULT.finditer(text))
    body = text[: marks[0].start()] if marks else text
    starts = [mark.start() for mark in marks] + [len(text)]
    results = tuple(
        Result(mark["heading"].strip(), text[mark.end() : end].strip())
        for mark, end in zip(marks, starts[1:], strict=True)
    )
    title = _BRIEF_TITLE.search(body)
    return Brief(
        slug=slug,
        title=title["title"].strip() if title else "",
        body=body.strip(),
        results=results,
        thread=thread_of(body) or None,
    )


def handoff(text: str) -> Handoff:
    first = text.lstrip().splitlines()[:1]
    title = first[0].removeprefix("# ").strip() if first and first[0].startswith("# ") else ""
    found = {
        heading.removeprefix("## ").strip(): "\n".join(lines).strip()
        for heading, lines in sections(text)
    }
    return Handoff(title, found)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def repo(path: Path) -> Repo | None:
    plan = _read(path / "plan.md")
    hand = _read(path / "handoff.md")
    tasks = sorted((path / "tasks").glob("*.md"))
    if plan is None and hand is None and not tasks:
        return None
    briefs = [(task.stem, _read(task)) for task in tasks]
    return Repo(
        name=path.name,
        handoff=handoff(hand) if hand is not None else None,
        entries=tuple(plan_entries(plan or "")),
        briefs=tuple(brief(slug, text) for slug, text in briefs if text is not None),
    )


def repos(state: Path) -> list[Repo]:
    if not state.is_dir():
        return []
    found = (repo(path) for path in state.iterdir() if path.is_dir())
    return sorted((one for one in found if one), key=lambda one: one.name.lower())
