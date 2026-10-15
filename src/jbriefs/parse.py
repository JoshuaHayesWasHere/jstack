"""Read a home's state directory: its handoff, its plan entries, its briefs and their results.

The shapes are the ones the `home`, `crew` and `handoff` skills write. Everything
here comes from the files alone; nothing asks T3 or the forge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class Entry:
    """One `## <slug>: <one line>` section of plan.md. `status` is what its `Stage:` line
    says, or the `Status:` line of a plan from before."""

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
class Result:
    """One `## Result` section a crewmate appended to its brief."""

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


@dataclass(frozen=True)
class Proof:
    """A brief's `Proves it:` line: what outside the agent shows the task is done.

    `kind` is the first thing it names that is not the agent's own word, and `fault` is
    why it names nothing of the sort. One of the two is set.
    """

    said: str
    kind: str = ""
    fault: str = ""

    @property
    def why(self) -> str:
        """One line on why the proof does not hold, or nothing when it does."""
        return f"brief's Proves it: line {self.fault} {_PROVES}" if self.fault else ""


def proof(said: str) -> Proof:
    """Judge what a `Proves it:` line says, the label left off.

    Three tables are read in turn, and the first match decides. `_NAMED` is what names a
    thing outside the agent by itself: a test's path or name, a runner, a make target, CI,
    a named judge or the user, and so is a command in backticks that names no agent. So a
    test the crewmate runs is still a test. `_SELF` is the agent's own word. `_LOOSE` is
    what holds only with no agent named: "the agent tests it" is the agent's word.
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


def proves_it(text: str) -> Proof | None:
    """The first `Proves it:` line of a brief's head, judged, or None for a brief with none."""
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("Proves it:"):
            return proof(line.removeprefix("Proves it:"))
    return None


@dataclass(frozen=True)
class Brief:
    """One `tasks/<slug>.md`: the brief the home wrote, then the crewmate's results."""

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
