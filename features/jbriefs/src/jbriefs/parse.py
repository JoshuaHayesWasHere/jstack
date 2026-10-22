"""Read a home's state directory: its handoff, its plan entries, its briefs and their results.

The shapes are the ones that the `home`, `crew` and `handoff` skills write. Everything here
comes from the files alone, and nothing asks T3 or the forge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jbriefs import skills

NO_RESULT = "no result yet"
DONE = "done"
NOT_DONE = "not done"
BLOCKED = "blocked"
PAUSED = "paused"
UNCLEAR = "unclear"

_ENTRY = re.compile(r"^## (?P<slug>[A-Za-z0-9][A-Za-z0-9._-]*): (?P<title>.+)$")
_BRIEF_TITLE = re.compile(r"^# [^:\n]+: (?P<title>.+)$", re.MULTILINE)
_RESULT = re.compile(r"^## (?P<heading>Result\b.*)$", re.MULTILINE)
_STATUS = re.compile(r"^Status:[ \t]*(?P<status>.*)$", re.MULTILINE)
_THREAD = re.compile(r"^Thread:[ \t]*(?P<thread>\S+)", re.MULTILINE)
_PULL_REQUEST = re.compile(r"^(?:.*\s)?Pull request:[ \t]*(?P<named>.*)$", re.MULTILINE)
_URL = re.compile(r"https?://[^\s)>\]`]+")
_REPORTED = re.compile(r"^Playbook:[ \t]*(?P<said>.*)$", re.MULTILINE)
_STEP = re.compile(r"(?P<number>\d+) (?:done|skip: (?P<skip>\S.*))")

_NAMED = (
    (
        "a test",
        r"\btests?/|\btest_\w+|\w+_test\b|\bpytest\b|\buv run\b"
        r"|\bmake (?!(sure|certain|it|this|that|a|an|the)\b)[\w-]+"
        r"|\b(?!(crew|crewmates?|reviewers?|agents?|self|model|it|he|she|they|who|that|which"
        r"|will|can|could|should|would|must|to|does|did|may|might)\b)[\w-]+[ -]tests\b",
    ),
    (
        "an external judge",
        r"\b(external|outside|independent|blind) judge\b|\bCI\b|\bgithub\b|\bthird[- ]party\b",
    ),
    ("the user", r"\bthe user\b|\buser's\b|\bthe (operator|owner)\b|\bhis (word|pick|eye)\b"),
)
_SELF = (
    ("the crewmate", r"\bcrewmates?\b"),
    ("the crew", r"\bcrew\b"),
    ("the reviewer", r"\breviewers?\b"),
    ("the agent", r"\bagents?\b"),
    ("the agent itself", r"\bself\b|\bitself\b"),
    ("the model", r"\bthe model\b|\bmodel's\b"),
    ("a review alone", r"\breview(s|ed)?\b"),
)
_LOOSE = (
    ("a test", r"\btests?\b"),
    ("a metric", r"\bmetrics?\b|\bmeasured?\b|\bbenchmarks?\b|\blatency\b|\bp\d{2}\b|\d\s*%"),
    ("a dataset", r"\bdata ?sets?\b|\bcorpus\b|\bfixtures?\b|\bgolden\b|\bevals?\b"),
    ("an external judge", r"\bjudge\b"),
)
_SPAN = re.compile(r"`([^`\n]+)`")
_PROVES = "(name a test, a command, a metric, a dataset, an external judge or the user)"

SIZES = ("S", "M", "L", "XL")
_SIZES = "(S, M, L or XL)"
_PLAYBOOK = "(name a file in playbooks/, without its .md, or none)"


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
    not do it, and is empty for a step that was done."""

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
    """Read what a `Playbook:` line says, without its label. It holds the name, then `; ` and
    each step as `<n> done` or `<n> skip: <reason>`, numbered in order from 1 to the last."""
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
        found = _STATUS.search(self.text)
        status = found["status"].lower() if found else ""
        for state in (NOT_DONE, BLOCKED, PAUSED, DONE):
            if status.startswith(state):
                return state
        return UNCLEAR

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


@dataclass(frozen=True)
class Proof:
    """A brief's `Proves it:` line, which names something outside the agent that shows the task
    is done.

    `kind` is the first thing the line names that is not the agent's own word, and `fault`
    says why the line names nothing of the sort. One of the two is set.
    """

    said: str
    kind: str = ""
    fault: str = ""

    @property
    def why(self) -> str:
        """One line on why the proof does not hold, or nothing when it holds."""
        return f"brief's Proves it: line {self.fault} {_PROVES}" if self.fault else ""


def proof(said: str) -> Proof:
    """Judge what a `Proves it:` line says, without its label.

    It reads three tables in turn, and the first match decides. `_NAMED` lists the words
    that on their own name something outside the agent: a test's path or name, a runner, a
    make target, CI, a named judge or the user. A command in backticks that names no agent
    counts too, so a test that the crewmate runs is still a test. `_SELF` lists the agent's
    own word. `_LOOSE` lists words that count only when no agent is named, because "the
    agent tests it" is the agent's own word.
    """
    said = said.strip()
    if not said:
        return Proof(said, fault="is empty")
    if said.startswith("<"):
        return Proof(said, fault="is the template's own text")
    for kind, pattern in _NAMED:
        if re.search(pattern, said, re.I):
            return Proof(said, kind=kind)
    for span in _SPAN.findall(said):
        if not any(re.search(pattern, span, re.I) for _, pattern in _SELF):
            return Proof(said, kind="a test")
    for name, pattern in _SELF:
        if re.search(pattern, said, re.I):
            return Proof(said, fault=f"names {name}, the agent's own word")
    for kind, pattern in _LOOSE:
        if re.search(pattern, said, re.I):
            return Proof(said, kind=kind)
    return Proof(said, fault="names nothing outside the agent")


def _head(text: str, label: str) -> str | None:
    """What the first `<label>` line of a brief's head says, or None for a head with none."""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith(label):
            return line.removeprefix(label).strip()
    return None


def proves_it(text: str) -> Proof | None:
    """The first `Proves it:` line of a brief's head, judged, or None for a brief with none."""
    said = _head(text, "Proves it:")
    return None if said is None else proof(said)


def _template(said: str) -> bool:
    return said.startswith("<") or "|" in said


def sized(text: str) -> str:
    """One line on why a brief's `Size:` line names no t-shirt size, or nothing.

    Step 4 of the feature playbook reads the size to decide on a design read. So this check
    refuses a brief with no line, which would otherwise count as S, as every brief did
    before the line existed.
    """
    said = _head(text, "Size:")
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
    first word of the first such line of its head, or nothing for a head with no such line
    or an empty one. `jbus playbook` opens the file it names, and this function is the one
    reader of the line."""
    said = _head(text, "Playbook:")
    return said.split()[0] if said else ""


def playbook(text: str) -> str:
    """One line on why a brief's `Playbook:` line names no playbook, or nothing.

    The name is the line's first word, as `jbus playbook` reads it. It must be a crewmate's
    file of `playbooks/` without its `.md`, or `none`. A brief with no line counts as `none`.
    """
    said = _head(text, "Playbook:")
    name = playbook_named(text)
    if said is None or name == "none":
        return ""
    if not said:
        fault = "is empty"
    elif _template(said):
        fault = "is the template's own text"
    elif name not in skills.listed("playbook"):
        fault = f"names {name}, which is no file in playbooks/"
    elif not crewmates(name):
        fault = f"names {name}, which is not a crewmate's playbook"
    else:
        return ""
    return f"brief's Playbook: line {fault} {_PLAYBOOK}"


NO_DESIGN = "brief has no Design: line (run /architect or say none, <why>)"
_NONE = re.compile(r"none[ \t]*,[ \t]*\S", re.I)
_DESIGN = re.compile(r"[\w/~-]{2,}\.[A-Za-z0-9]{2,}")


def designed(text: str) -> str:
    """Why a brief has no design call, or nothing.

    The first `Design:` line of its head gives the call: the path of the design the brief
    was written from, a file with its extension, or `none, <why>`. A `none` with no reason
    gives no call. Neither does a word that names no file (`TBD`, `n/a`), or the template's
    own line left unchanged.
    """
    said = _head(text, "Design:")
    if said is None:
        return NO_DESIGN
    named = not said.startswith("<") and _DESIGN.search(said)
    return "" if _NONE.match(said) or named else NO_DESIGN


TITLE = "title"
REST = "the rest"
_LABEL = re.compile(r"(?P<label>[A-Z][A-Za-z]*(?: [A-Za-z]+){0,3}):(?:[ \t]|$)")
REQUIRED = (
    "Task",
    "Done when",
    "Proves it",
    "Size",
    "Where",
    "Pull request",
    "Review",
    "Playbook",
)


def fields(text: str) -> list[tuple[str, list[str]]]:
    """A brief as its fields, in order: each label with the lines it holds.

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


def _filled(text: str, label: str) -> str:
    """One line on why the brief's `<label>:` field is not filled in, or nothing.

    A field is not filled in when its first line, or an item of a list under it, is still
    the template's whole placeholder (`<...>`, without its quote or list marker). A field of
    `_CHOICES` that still offers its choices (`review | none`) is not filled in either. A
    line that only starts with `<` (`<200 ms`) is filled in, and so is a field that still
    has the template's notes under it.
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
    return ""


def proven(text: str) -> str:
    """One line on why a brief's `Proves it:` line proves nothing, or nothing.

    A brief with no such line gets nothing here. A brief that reaches a launch with no such
    line was written before the template asked for the line, and `faults` reports that the
    line is missing.
    """
    found = proves_it(text)
    return found.why if found else ""


_CHECK_COMMAND = re.compile(r"^[-* ]*Check command:[ \t]*`(?P<command>[^`\n]+)`", re.MULTILINE)
_BARE_CHECK = re.compile(r"\bmake check(?![-\w])")


def check_command(notes: str) -> str:
    """The repo's check command, as the `Check command:` line of its notes names it, or nothing."""
    named = _CHECK_COMMAND.search(notes)
    return named["command"].strip() if named else ""


def check_asked(text: str, notes: str) -> str:
    """One line on why a brief's `Done when:` asks for the wrong check, or nothing.

    The notes name the repo's check command on a `Check command:` line. A `Done when:` item
    that asks for a bare `make check`, while that command is another one, sends a crewmate
    to run the full suite instead.
    """
    command = check_command(notes)
    if not command or _BARE_CHECK.fullmatch(command):
        return ""
    if not any(_BARE_CHECK.search(item) for item in _done_when(text.splitlines())):
        return ""
    return (
        f"brief's Done when: asks for `make check`, and notes.md names the check command "
        f"`{command}`: a check line names the check command (`notes.md`)"
    )


_PAREN = re.compile(r"\([^()]*\)")
_WORD = re.compile(r"`[^`]+`|\S+")
_LINES = re.compile(r":\d+(?:-\d+)?$")
_PATHLIKE = re.compile(r"[\w.@+~*?\[\]{}/-]+")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_BRACES = re.compile(r"\{([^{}]*)\}")


def _head_lines(text: str, label: str) -> str | None:
    """The head field `<label>`: its first line and the lines under it, joined by a space."""
    for name, lines in fields(text):
        if name == label:
            return " ".join(line.strip() for line in lines)
    return None


def _path(word: str, ticked: bool) -> str:
    """The path or glob that a word names under the repo, or nothing.

    A word in backticks names one if it is a single token that is not an option, a URL or a
    path that leaves the repo. A word between commas needs more to tell it from prose: a
    `/`, a glob, or a file extension.
    """
    if word.strip() in (".", "./"):
        return "."
    word = _LINES.sub("", word.strip().rstrip(".,;:")).removeprefix("./")
    if not word or word[0] in "-/~" or ".." in word.split("/") or "://" in word:
        return ""
    if not _PATHLIKE.fullmatch(word):
        return ""
    if not ticked and not ("/" in word or "*" in word or _EXTENSION.search(word)):
        return ""
    return word.rstrip("/")


def _items(line: str) -> list[str]:
    """The line cut at each comma that is not inside a brace set."""
    items, depth, start = [], 0, 0
    for at, char in enumerate(line):
        if char == "{":
            depth += 1
        elif char == "}" and depth:
            depth -= 1
        elif char == "," and not depth:
            items.append(line[start:at])
            start = at + 1
    return [*items, line[start:]]


def _expanded(word: str) -> tuple[str, ...]:
    """A word with its brace sets spelled out, the innermost first: `a{b,c}.py` gives two."""
    found = _BRACES.search(word)
    if found is None:
        return (word,)
    head, tail = word[: found.start()], word[found.end() :]
    return tuple(
        whole for part in found.group(1).split(",") for whole in _expanded(head + part + tail)
    )


def where(text: str) -> tuple[str, ...]:
    """The paths and globs that the head's `Where:` line names, in its order, each once.

    It keeps an item in backticks or between commas that names a path under the repo. A
    `path:line` or `path:a-b` keeps its path, a directory loses its closing `/`, and it drops
    prose in parentheses, the commas in it included. It spells out a brace set, so
    `src/{a,b}.py` gives two paths, and the commas of a brace set do not end an item. It
    reads a bare word when the word is the first of its item (`docs/ pages tied to`) or has
    a `/` (`plus templates/x.service`). A line that names no path gives an empty tuple.
    """
    line = _head_lines(text, "Where")
    if line is None:
        return ()
    while (bare := _PAREN.sub("", line)) != line:
        line = bare
    found: dict[str, None] = {}
    for item in _items(line):
        for at, word in enumerate(_WORD.findall(item)):
            ticked = word.startswith("`") and word.endswith("`") and len(word) > 1
            if ticked or at == 0 or "/" in word:
                named = (
                    _path(one, ticked) for one in _expanded(word.strip("`") if ticked else word)
                )
                found.update(dict.fromkeys(filter(None, named)))
    return tuple(found)


def _glob(pattern: str) -> re.Pattern[str]:
    """A glob as a regex over a whole path. A `*` matches within one name, and `**` crosses `/`."""
    out, at = "", 0
    while at < len(pattern):
        if pattern.startswith("**/", at):
            out, at = out + "(?:.*/)?", at + 3
        elif pattern.startswith("**", at):
            out, at = out + ".*", at + 2
        elif pattern[at] == "*":
            out, at = out + "[^/]*", at + 1
        elif pattern[at] == "?":
            out, at = out + "[^/]", at + 1
        else:
            out, at = out + re.escape(pattern[at]), at + 1
    return re.compile(out)


def covers(patterns: tuple[str, ...], path: str) -> bool:
    """Whether a changed file is one of the paths and globs that `where` gave, or is under one.
    `.` is the whole repo."""
    if "." in patterns:
        return True
    parts = path.split("/")
    parents = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    return any(_glob(pattern).fullmatch(parent) for pattern in patterns for parent in parents)


def wheres(text: str) -> str:
    """One line on why a brief's `Where:` line names no path, quoting the `Where:` line, or
    nothing.

    `_filled` handles a brief with no line, or with the template's own text.
    """
    line = _head_lines(text, "Where")
    if line is None or _filled(text, "Where") or where(text):
        return ""
    return (
        "brief's Where: line names no path under the repo, so a changed file cannot be "
        f"told from one outside it (write each path or directory in backticks): {line}"
    )


CHECKS = (
    ("Design", designed),
    ("Proves it", proven),
    ("Skills", skills.unknown),
    ("Size", sized),
    ("Playbook", playbook),
    ("Where", wheres),
)
_SAYS_MISSING = ("Design", "Size", "Skills")


def faults(text: str) -> list[str]:
    """Every reason a brief may not be queued, one line for each field at fault.

    It checks that each field of `REQUIRED` is filled in, then runs every check of each
    filled field (`CHECKS`). It leaves `Design`, `Size` and `Skills` to their own checks.
    Those checks report a missing line, and for `Skills` the check reports instead that a
    brief with no line names no skill. A brief with no fault is complete. The check runs when
    a row is first queued and not again at a launch, so a brief that already has a go
    launches without it (`jbus.queue`).
    """
    checks = dict(CHECKS)
    found = []
    for label in (*REQUIRED, *(label for label in checks if label not in REQUIRED)):
        fault = "" if label in _SAYS_MISSING else _filled(text, label)
        if not fault and label in checks:
            fault = checks[label](text)
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


def _sections(text: str) -> list[tuple[str, list[str]]]:
    found: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            found.append((line, []))
        elif found:
            found[-1][1].append(line)
    return found


def _done_when(lines: list[str]) -> tuple[str, ...]:
    items: list[str] = []
    inside = False
    for line in lines:
        if not inside:
            if line.startswith("Done when:"):
                inside = True
                inline = line.removeprefix("Done when:").strip()
                if inline:
                    items.append(inline)
            continue
        if not line.strip():
            continue
        if line.startswith(("- ", "* ")):
            items.append(line[2:].strip())
        elif line[:1].isspace() and items:
            items[-1] += " " + line.strip()
        else:
            break
    return tuple(items)


def plan_entries(text: str) -> list[Entry]:
    entries = []
    for heading, lines in _sections(text):
        found = _ENTRY.match(heading)
        if not found:
            continue
        status = next((line for line in lines if line.startswith(("Stage:", "Status:"))), "")
        entries.append(
            Entry(
                slug=found["slug"],
                title=found["title"].strip(),
                status=status.partition(":")[2].strip(),
                done_when=_done_when(lines),
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
    thread = _THREAD.search(body)
    return Brief(
        slug=slug,
        title=title["title"].strip() if title else "",
        body=body.strip(),
        results=results,
        thread=thread["thread"] if thread else None,
    )


def handoff(text: str) -> Handoff:
    first = text.lstrip().splitlines()[:1]
    title = first[0].removeprefix("# ").strip() if first and first[0].startswith("# ") else ""
    sections = {
        heading.removeprefix("## ").strip(): "\n".join(lines).strip()
        for heading, lines in _sections(text)
    }
    return Handoff(title, sections)


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
