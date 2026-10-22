"""A brief's review findings and the crew's answers to them. This module is their one parser.

A brief has one `## Review` section from each reviewer the role map lists, and one more for
each later pass. Each section lists findings under `Findings:` and lists the ones its lead
dismissed under `Dismissed:`. A finding line has the shape that pr-review's
`templates/review.md` gives,

    - <severity> <file>:<line> <what is wrong> (principle: <name>) (bucket: Act on)

with an optional `(risk: <area>)` tag. A dismissed line ends `(dismissed: <reason>)`. A line
with no `(bucket: ...)` tag dates from before the buckets existed (`Raised.legacy`).

`triage` reads them all into `Finding`s. It gives each an id, `F1`, `F2`, ..., in the order
the lines appear in the brief. Reviewers write no id, because two of them write at once and
would take the same one. The brief only grows, and a line takes the id of an earlier finding
or the next free one, so a finding keeps its id whatever the brief adds after it. `_same`
merges two reviewers' findings of one head into one finding when they name the same file,
lines at most `NEAR` apart, and the same principle, and both raised it. When one reviewer
raised a finding and another dismissed it there, `triage` keeps the two apart and prints the
dismissal beside the finding (`Finding.contradicts`). The `By:` line names a reviewer. Its
last word is the reviewer's number, `#<n>`. The number is the line of the role map's review
list that the crew launched the reviewer for, so two reviewers of one model count as two
(`Section.seat`). The `Reviewer:` lines say whom a round waits for (`Roster`). Once one of
them carries a number, the round waits for the numbered lines alone, and the unnumbered lines
before them are a launch that the numbered ones replaced. When a reviewer writes a section
again at the same head, the new section takes the place of the earlier one. `triage` merges
lines as if the earlier section were still there, so no id moves. A finding whose every line
is in such a replaced section keeps its id and counts for nothing (`Finding.superseded`).

The crew answers by id, `Finding F2: fixed, ...` or `Finding F2: not fixed, ..., because
<reason>` (`ANSWER`). An answer with no id, `Finding: fixed, ...`, is how a brief from before
the ids answered. `triage` gives such answers, in order, to the findings that have no bucket
and no answer by id, as the crew's count matched them. Only an **Act on** finding blocks a
merge. A finding from before the buckets blocks too, as every finding did then, and so does a
finding on one of `RISKS`, whatever its bucket. A decline of a blocking finding counts only
when its reason cites a `path:line`, a command in backticks, or a gate that the Result names
(`Gate: question <n>`). `_judge` refuses a reason that the crew gave for an earlier finding. A
decline of a finding on one of `RISKS` counts only on a gate, which asks the user with the
default "fix it". Severity is a field and decides nothing.

The scoped pass, a section with a `Scope:` line, rules on each blocking finding that the crew
declined by id. It writes `Declines: upheld F2, F4`, and `Declines: not upheld F3: <the
disproof>` for each decline it does not uphold (`Ruling`). The last ruling of an id is the one
that counts. A decline that the pass did not uphold stays overruled until the crew answers the
finding `fixed`, and a decline written again after the ruling is still not upheld
(`Finding.state`). A scoped section that its reviewer wrote again at the same head rules on
nothing, because the section that took its place says all that pass says. So a scoped pass
rules on every blocking decline, those with an earlier ruling included. A scoped section is a
pass of its own. At the head of the first review, the only section it replaces is an earlier
scoped section by the same reviewer.

`jmerge` (`ready.said_of`, `short_of`), the crew skill's count of the findings and its second
pass (`jbriefs --findings --left` and `--rounds`), and jbus's ask (`expedite`) read the brief
through this module and nowhere else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

NEAR = 5
ACT_ON, CONSIDER, NOTED, DISMISSED = "Act on", "Consider", "Noted", "Dismissed"
BUCKETS = (ACT_ON, CONSIDER, NOTED, DISMISSED)
SENT = (ACT_ON, CONSIDER)
RISKS = ("security", "auth", "billing", "data", "migrations", "concurrency")
ANSWER = (
    "`Finding F<n>: fixed, <the finding in a few words>` or `Finding F<n>: not fixed, <the "
    "finding in a few words>, because <a reason that cites a path:line, a command in "
    "backticks, or the gate it is parked on, question <n>>`"
)
UNANSWERED, UNCITED, REPEATED, UNASKED = "unanswered", "uncited", "repeated", "unasked"
WHY = {
    UNANSWERED: "no answer by id",
    UNCITED: "its decline cites no path:line, command or gate question",
    REPEATED: "its decline gives the reason of {first}",
    UNASKED: "a finding on {risk} declined with no gate question",
}

_TAGS = ("principle", "bucket", "risk", "dismissed")
_PLACE = re.compile(r"(.+):(\d+)")
_BY_ID = re.compile(r"Finding (F\d+): (fixed|not fixed), (.*)")
_DECLINE = re.compile(r"(.+?), because (.*)")
_OLD = re.compile(r"Finding: (?:fixed, .|not fixed, .+, because .*\w)")
_CITED = re.compile(r"[\w./-]*[A-Za-z_][\w./-]*:\d+|`[^`]+`")
_QUESTION = re.compile(r"\bquestion (\d+)\b")
_UPHELD = "Declines: upheld "
_NOT_UPHELD = "Declines: not upheld "
_ID = re.compile(r"F\d+")
OPEN, FIXED, UNRULED, UPHELD, OVERRULED = "open", "fixed", "unruled", "upheld", "overruled"


@dataclass(frozen=True)
class Raised:
    """One finding as one reviewer wrote it, in the section `section` of the brief."""

    section: int
    reviewer: str
    head: str
    severity: str
    path: str
    line: int | None
    what: str
    category: str
    bucket: str
    risk: str = ""
    reason: str = ""
    legacy: bool = False
    scoped: bool = False

    @property
    def place(self) -> str:
        return self.path + ("" if self.line is None else f":{self.line}")


@dataclass(frozen=True)
class Ruling:
    """What a scoped pass said of one decline: upheld, or not upheld because of `why`."""

    upheld: bool
    why: str = ""


@dataclass(frozen=True)
class Section:
    """One `## Review` section: who wrote it, the first word of its verdict, its head, the
    findings it lists (`found` counts them) and the ones it dismissed. `scoped` is true for a
    scoped pass, which has a `Scope:` line, and `rulings` holds that pass's ruling on each
    decline by id. `line` is the index of the section's heading among the brief's lines.
    `by` is the whole `By:` text, the number included, and `seat` is that number, or None for
    a `By:` line that has no number."""

    by: str = ""
    verdict: str = ""
    ran: bool = False
    head: str = ""
    raised: tuple[Raised, ...] = ()
    found: int = 0
    scoped: bool = False
    rulings: tuple[tuple[str, Ruling], ...] = ()
    line: int = 0

    @property
    def seat(self) -> int | None:
        found = _SEAT.search(self.by)
        return int(found[1]) if found else None


_SEAT = re.compile(r"\s#(\d+)$")


@dataclass(frozen=True)
class Legacy:
    """A brief in which no `Reviewer:` line has a number. This module reads it as it read every
    brief before reviewers had numbers. `named` holds the lines that name a thread. The round
    waits for them only where more than one is named, and counts them against the distinct
    `By:` texts of the sections."""

    named: int

    @property
    def size(self) -> int:
        return self.named

    def owed(self, sections: list[Section]) -> int:
        wrote = len({one.by for one in sections if one.by})
        return self.named - wrote if self.named > 1 and wrote < self.named else 0

    def counted(self, sections: list[Section]) -> list[Section]:
        return sections


@dataclass(frozen=True)
class Numbered:
    """A brief with a `Reviewer: <threadId> #<n>` line. The round waits for each number that
    those lines name. The numbers are a set, so a seat launched again does not count twice.
    The unnumbered `Reviewer:` lines are a launch that the numbered ones replaced, and the
    round no longer waits for them. Sections with no number do not count toward the round,
    but their findings still need answers. A section with a seat's number counts for that
    seat, at any head."""

    seats: frozenset[int]

    @property
    def size(self) -> int:
        return len(self.seats)

    def owed(self, sections: list[Section]) -> int:
        return len(self.seats - {one.seat for one in sections})

    def counted(self, sections: list[Section]) -> list[Section]:
        return [one for one in sections if one.seat is not None]


Roster = Legacy | Numbered


def roster(text: str) -> Roster:
    """Whom the round waits for, read from the `Reviewer:` lines that name a thread."""
    named = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("Reviewer:") and "".join(line.split()[1:2]) not in ("", "none", "none,")
    ]
    seats = frozenset(int(found[1]) for line in named if (found := _SEAT.search(line)))
    return Numbered(seats) if seats else Legacy(len(named))


@dataclass(frozen=True)
class Answer:
    """The crew's answer to a finding: fixed, or not fixed because of `reason`."""

    fixed: bool
    what: str
    reason: str = ""
    by_id: bool = True


@dataclass
class Finding:
    """One finding of the triaged list, with its id, the lines that raised it (one per
    reviewer), and the answer it has."""

    id: str
    raised: list[Raised]
    contradicts: str = ""
    stale: frozenset[int] = frozenset()
    answer: Answer | None = None
    refused: str = ""
    first: str = ""
    ruling: Ruling | None = None

    @property
    def lead(self) -> Raised:
        return self.raised[0]

    @property
    def reviewers(self) -> tuple[str, ...]:
        return tuple(one.reviewer for one in self.raised)

    @property
    def standing(self) -> list[Raised]:
        """The lines that raised it in sections that still count, or all of them where none does."""
        return [one for one in self.raised if one.section not in self.stale] or self.raised

    @property
    def superseded(self) -> bool:
        """Whether every line that raised it is in a section that its reviewer wrote again."""
        return all(one.section in self.stale for one in self.raised)

    @property
    def bucket(self) -> str:
        return min((one.bucket for one in self.standing), key=BUCKETS.index)

    @property
    def severity(self) -> str:
        ranks = ("error", "warning", "info")
        return min(
            (one.severity for one in self.standing),
            key=lambda value: ranks.index(value) if value in ranks else len(ranks),
        )

    @property
    def path(self) -> str:
        return self.lead.path

    @property
    def line(self) -> int | None:
        return self.lead.line

    @property
    def legacy(self) -> bool:
        return self.lead.legacy

    @property
    def risk(self) -> str:
        return next((one.risk for one in self.standing if one.risk), "")

    @property
    def sent(self) -> bool:
        """Whether the reviewer sent the finding to the crew, so that the crew must answer it. The
        reviewer sends the findings of a section that still counts."""
        return not self.superseded and self.bucket in SENT

    @property
    def blocks(self) -> bool:
        """Whether it holds the merge until the crew answers it. An Act on finding holds it, as
        every finding from before the buckets does, and so does a finding on one of `RISKS`
        in any bucket."""
        return self.sent and (self.bucket == ACT_ON or bool(self.risk))

    @property
    def ended(self) -> bool:
        return self.answer is not None and not self.refused

    @property
    def why(self) -> str:
        return WHY[self.refused].format(first=self.first, risk=self.risk) if self.refused else ""

    @property
    def state(self) -> str:
        """The state of a blocking finding. It is `open` until an answer counts, and then
        `fixed`. A decline by id is `unruled` until a scoped pass rules on it, and then
        `upheld` or `overruled`. A finding that does not block, or one answered with no id,
        is `fixed` once it has an answer that counts, because nothing rules on it."""
        if not self.ended:
            return OPEN
        if self.answer.fixed or not self.answer.by_id or not self.blocks:
            return FIXED
        if self.ruling is None:
            return UNRULED
        return UPHELD if self.ruling.upheld else OVERRULED


@dataclass
class Triage:
    """A brief's findings, merged and answered: `sections` in order, `findings` by id,
    `answers` by id, and whom the round waits for (`roster`)."""

    sections: list[Section] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    answers: dict[str, Answer] = field(default_factory=dict)
    roster: Roster = field(default_factory=lambda: Legacy(0))

    def blocking(self) -> tuple[Finding, ...]:
        """The findings that hold the merge, each Act on finding with no answer that counts, in
        the order of their ids."""
        return tuple(one for one in self.findings if one.blocks and not one.ended)

    def sent(self) -> list[Finding]:
        return [one for one in self.findings if one.sent]

    def declines(self, state: str) -> tuple[Finding, ...]:
        """The blocking findings whose `state` is `UNRULED` or `OVERRULED`, in the order of
        their ids."""
        return tuple(one for one in self.findings if one.blocks and one.state == state)


def _tags(text: str) -> tuple[str, dict[str, str]]:
    """The text of a finding line with the tags taken off its end, and the tags."""
    tags: dict[str, str] = {}
    text = text.rstrip()
    while text.endswith(")"):
        starts = {name: text.rfind(f"({name}: ") for name in _TAGS}
        name = max(starts, key=lambda one: starts[one])
        if starts[name] < 0 or name in tags:
            break
        tags[name] = text[starts[name] + len(name) + 3 : -1].strip()
        text = text[: starts[name]].rstrip()
    return text, tags


def _bucket(said: str | None, dismissed: bool) -> str:
    if dismissed:
        return DISMISSED
    named = {bucket.lower(): bucket for bucket in BUCKETS}
    return named.get((said or "").strip().lower(), ACT_ON)


def _raised(text: str, section: int, by: str, head: str, dismissed: bool) -> Raised:
    """One line of a section's list, after its `- `."""
    rest, tags = _tags(text)
    if dismissed and "dismissed" not in tags:
        what, _, reason = rest.rpartition(": ")
        return Raised(section, by, head, "", "", None, what or rest, "", DISMISSED, "", reason)
    severity, _, rest = rest.partition(" ")
    place, _, what = rest.partition(" ")
    found = _PLACE.fullmatch(place)
    path, line = (found[1], int(found[2])) if found else (place, None)
    return Raised(
        section,
        by,
        head,
        severity,
        path,
        line,
        what,
        tags.get("principle", ""),
        _bucket(tags.get("bucket"), dismissed),
        tags.get("risk", "").lower(),
        tags.get("dismissed", ""),
        legacy="bucket" not in tags and not dismissed,
    )


def _sections(text: str) -> list[Section]:
    """Each `## Review` section, parsed the way the crew's count and `jmerge` parse it. Its
    list runs from `Findings:` to `Dropped:` or the next heading. A line in the list that
    starts `- ` and is not `- none` is a finding, and the lines under `Dismissed:` that start
    `- ` are its dismissed findings."""
    found: list[dict] = []
    listing = dismissing = False
    for at, line in enumerate(text.splitlines()):
        if line.startswith("## "):
            listing = dismissing = False
            if line == "## Review":
                found.append(
                    {"by": "", "verdict": "", "ran": False, "head": "", "lines": [], "at": at}
                )
                found[-1] |= {"scoped": False, "rulings": []}
            elif found:
                found[-1]["closed"] = True
            continue
        here = found[-1] if found and not found[-1].get("closed") else None
        if line.startswith("Dropped:"):
            listing = False
        if here is None:
            continue
        if line.startswith("Findings:"):
            listing, dismissing = True, False
        elif line.startswith("Dismissed:"):
            listing, dismissing = False, True
        elif line.startswith("- ") and (listing or dismissing):
            if line != "- none":
                here["lines"].append((line[2:], dismissing))
        else:
            dismissing = dismissing and line.startswith("- ")
        if line.startswith("Verdict:"):
            here["verdict"] = "".join(line.split()[1:2])
            here["ran"] = line.strip() in ("Verdict: clean", "Verdict: findings")
        elif line.startswith("Head:"):
            here["head"] = "".join(line.split()[1:2])
        elif line.startswith("By:"):
            here["by"] = line[len("By:") :].strip()
        elif line.startswith("Scope:"):
            here["scoped"] = True
        elif line.startswith(_NOT_UPHELD):
            ident, _, why = line.removeprefix(_NOT_UPHELD).partition(": ")
            here["rulings"].append((ident.strip(), Ruling(False, why.strip())))
        elif line.startswith(_UPHELD):
            named = _ID.findall(line.removeprefix(_UPHELD))
            here["rulings"].extend((ident, Ruling(True)) for ident in named)
    sections = []
    for number, one in enumerate(found):
        raised = tuple(
            replace(_raised(text, number, one["by"], one["head"], dismissed), scoped=one["scoped"])
            for text, dismissed in one["lines"]
        )
        listed = sum(1 for _, dismissed in one["lines"] if not dismissed)
        sections.append(
            Section(
                one["by"],
                one["verdict"],
                one["ran"],
                one["head"],
                raised,
                listed,
                one["scoped"],
                tuple(one["rulings"]),
                one["at"],
            )
        )
    return sections


def _near(one: Raised, other: Raised) -> int | None:
    """How far apart two findings of one place are, or None when they are not of one place.
    Two findings are of one place when they name the same file, both name lines at most
    `NEAR` apart or both name the whole file, and both name the same principle. A finding
    tagged `none` shares its principle with no other."""
    if one.path in ("", "-") or one.path != other.path:
        return None
    if not one.category or one.category.lower() == "none" or one.category != other.category:
        return None
    if one.line is None or other.line is None:
        return 0 if one.line is other.line else None
    apart = abs(one.line - other.line)
    return apart if apart <= NEAR else None


def _same(finding: Finding, one: Raised) -> int | None:
    """How far `one` is from a finding it would merge into, or None when it would merge into
    none. It merges into another reviewer's finding of the same head and place when the
    reviewers raised both findings rather than dismissing them, both have a bucket, and the
    merged finding holds at most one line from each reviewer."""
    lead = finding.lead
    if lead.legacy or one.legacy or not one.head:
        return None
    if lead.scoped != one.scoped:
        return None
    if DISMISSED in (lead.bucket, one.bucket) or lead.head != one.head:
        return None
    if one.reviewer in (
        line.reviewer for line in finding.raised if line.section not in finding.stale
    ):
        return None
    return _near(lead, one)


def _superseded(sections: list[Section]) -> set[int]:
    """The sections that a later section took the place of. The later one has the same
    reviewer, the same head, and the same kind, a scoped pass or not."""
    last = {(one.by, one.head, one.scoped): n for n, one in enumerate(sections) if one.by}
    return {
        number
        for number, one in enumerate(sections)
        if one.by and last[(one.by, one.head, one.scoped)] != number
    }


def _answers(text: str) -> tuple[dict[str, Answer], list[Answer]]:
    """The last answer for each id, and the answers with no id, in order."""
    by_id: dict[str, Answer] = {}
    old: list[Answer] = []
    for line in text.splitlines():
        found = _BY_ID.match(line)
        if found:
            ident, how, rest = found.groups()
            if how == "fixed":
                by_id[ident] = Answer(True, rest)
            else:
                declined = _DECLINE.fullmatch(rest)
                by_id[ident] = Answer(False, *(declined.groups() if declined else (rest, "")))
        elif _OLD.match(line):
            fixed = line.startswith("Finding: fixed, ")
            old.append(Answer(fixed, line.split(", ", 1)[1], by_id=False))
    return by_id, old


def _judge(findings: list[Finding], text: str) -> None:
    """Refuse the answers that do not count. A decline of an Act on finding does not count
    when it cites nothing, gives an earlier finding's reason, or leaves a risky finding with
    no gate. This function applies the old rule to an answer with no id, which is an answer
    to a finding from before the ids."""
    gates = set(re.findall(r"Gate: question (\d+)\b", text))
    given: dict[str, str] = {}
    for one in findings:
        answer = one.answer
        if answer is None:
            one.refused = UNANSWERED if one.blocks else ""
            continue
        if answer.fixed or not answer.by_id or not one.blocks:
            continue
        asked = set(_QUESTION.findall(answer.reason)) & gates
        said = " ".join(answer.reason.lower().split())
        if one.risk and not asked:
            one.refused = UNASKED
        elif not asked and not _CITED.search(answer.reason):
            one.refused = UNCITED
        elif said in given:
            one.refused, one.first = REPEATED, given[said]
        given.setdefault(said, one.id)


def triage(text: str) -> Triage:
    """The brief's findings after `triage` merges them, gives each its id, sets each beside the
    dismissals that contradict it, and attaches each one's answer."""
    sections = _sections(text)
    stale = _superseded(sections)
    findings: list[Finding] = []
    for section in sections:
        for one in section.raised:
            near = [(apart, f) for f in findings if (apart := _same(f, one)) is not None]
            if near:
                min(near, key=lambda pair: pair[0])[1].raised.append(one)
            else:
                findings.append(Finding(f"F{len(findings) + 1}", [one], stale=frozenset(stale)))
    for one in findings:
        if one.bucket != DISMISSED or one.legacy or one.superseded:
            continue
        near = [
            (apart, other.id)
            for other in findings
            if other.bucket != DISMISSED
            and not other.legacy
            and not other.superseded
            and other.lead.head == one.lead.head
            and one.lead.reviewer not in other.reviewers
            and (apart := _near(other.lead, one.lead)) is not None
        ]
        one.contradicts = min(near, key=lambda pair: (pair[0], int(pair[1][1:])))[1] if near else ""
    answers, old = _answers(text)
    unnumbered = iter(old)
    for one in findings:
        if not one.sent:
            continue
        one.answer = answers.get(one.id)
        if one.answer is None and one.legacy:
            one.answer = next(unnumbered, None)
    _judge(findings, text)
    by_id = {one.id: one for one in findings}
    for number, section in enumerate(sections):
        if section.scoped and number not in stale:
            for ident, ruling in section.rulings:
                if ident in by_id:
                    by_id[ident].ruling = ruling
    return Triage(sections, findings, answers, roster(text))


def listed(said: Triage) -> list[str]:
    """The triaged list as `jbriefs --findings` prints it. It prints each finding by its id,
    and beside the finding any dismissal that contradicts it. Under each finding it prints
    who raised it and its answer."""
    beside: dict[str, list[Finding]] = {}
    for one in said.findings:
        if one.contradicts:
            beside.setdefault(one.contradicts, []).append(one)
    lines: list[str] = []
    for one in said.findings:
        if one.contradicts:
            continue
        for shown in [one, *beside.get(one.id, [])]:
            lines.extend(_shown(shown))
    return lines


def _shown(one: Finding) -> list[str]:
    lead = one.lead
    tags = f" (principle: {lead.category})" if lead.category else ""
    tags += f" (risk: {one.risk})" if one.risk else ""
    head = f"{one.id} [{one.bucket}] {one.severity} {lead.place} {lead.what}".replace("  ", " ")
    lines = [head.rstrip() + tags]
    lines.append(
        "  by: " + "; ".join(name or "a reviewer with no By: line" for name in one.reviewers)
    )
    if lead.head:
        lines.append(f"  head: {lead.head}")
    if one.contradicts:
        lines.append(f"  contradicts: {one.contradicts}")
    if one.bucket == DISMISSED:
        lines.append(f"  dismissed: {lead.reason or 'no reason given'}")
    elif one.superseded:
        lines.append("  superseded: its reviewer wrote this head's section again")
    elif one.answer is not None:
        answer = one.answer
        said = f"fixed, {answer.what}" if answer.fixed else f"not fixed, {answer.what}"
        said += f", because {answer.reason}" if not answer.fixed else ""
        lines.append(f"  answer: {said}" + (f" (refused: {one.why})" if one.refused else ""))
        if one.state in (UPHELD, OVERRULED):
            ruled = "upheld" if one.state == UPHELD else f"not upheld, {one.ruling.why}"
            lines.append(f"  ruling: {ruled}")
        elif one.state == UNRULED:
            lines.append("  ruling: none, a scoped pass rules on it before the merge")
    elif one.sent:
        lines.append("  answer: none" + (", it blocks the merge" if one.blocks else ""))
    return lines


def left(said: Triage) -> str:
    """The one line that the crew's count prints to say what the crew does next with the
    findings. The line tells the crew to wait for a reviewer, to answer the findings that
    have no answer, or to write a `Fixed:` line, and names that line. A fix answers the
    findings of the last round. The last round is the set of sections at the head of the
    last section."""
    sent = said.sent()
    if not said.sections:
        return "wait: the review is not written in the brief yet"
    owed = said.roster.owed(said.sections)
    if owed:
        size = said.roster.size
        line = f"wait: {size - owed} of {size} reviewers have written their section"
        uncounted = len(said.sections) - len(said.roster.counted(said.sections))
        if uncounted:
            line += f"; {uncounted} with no #<n> on its By: line counts for no reviewer"
        return line
    open_ = [one for one in sent if not one.ended]
    if open_:
        line = f"not yet: {len(open_)} of {len(sent)} findings have no Finding: line"
        named = [
            one.id + (f" ({one.why})" if one.answer and one.refused else "")
            for one in open_
            if not one.legacy
        ]
        return line + (": " + ", ".join(named) if named else "")
    last = _last_round(said)
    recent = [one for one in sent if one.lead.section in last]
    earlier = len(sent) - len(recent)
    fixed = any(one.answer and one.answer.fixed for one in sent)
    if earlier and recent and not any(one.answer and one.answer.fixed for one in recent):
        return (
            f"write Fixed: none needed, <reason>: {len(recent)} findings of the last review, "
            "none fixed"
        )
    if fixed:
        return f"write Fixed: <the head you pushed>, {len(sent)} findings each have their ending"
    if sent:
        return f"write Fixed: none needed, <reason>: {len(sent)} findings, none fixed"
    return "write Fixed: none needed, <reason>: the review has no findings"


def _last_round(said: Triage) -> set[int]:
    """The sections of the last round: the last section, and the ones right before it that
    name its head."""
    numbers = list(range(len(said.sections)))
    last = {numbers[-1]}
    head = said.sections[-1].head
    for number in reversed(numbers[:-1]):
        if not head or said.sections[number].head != head:
            break
        last.add(number)
    return last


def rounds(said: Triage) -> str:
    """The one line that the crew's second pass reads about the review. It gives how many
    sections ran, the head the last of them saw, every head a section names, and the
    blocking declines that no scoped pass has ruled on. It joins each list with commas, and
    writes `-` for an empty one."""
    ran = [one for one in said.sections if one.ran]
    saw = next((one.head for one in reversed(ran) if one.head), "-")
    heads = ",".join(dict.fromkeys(one.head for one in said.sections if one.head)) or "-"
    unruled = ",".join(one.id for one in said.declines(UNRULED)) or "-"
    return f"{len(ran)} {saw} {heads} {unruled}"
