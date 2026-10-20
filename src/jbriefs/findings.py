"""A brief's review findings and the crew's answers to them: the one parser.

Every `## Review` section of a brief, one from each reviewer the role map lists and one
for each later pass, holds a list of findings under `Findings:` and the ones its lead
dismissed under `Dismissed:`. A finding line is the one `templates/review.md` gives,

    - <severity> <file>:<line> <what is wrong> (principle: <name>) (bucket: Act on)

with an optional `(risk: <area>)` tag, and a dismissed one ends `(dismissed: <reason>)`.
A line with no `(bucket: ...)` tag was written before buckets were (`Raised.legacy`).

`triage` reads them all into `Finding`s, each with an id, `F1`, `F2`, ..., given in the
order the lines stand in the brief. Reviewers write no id: two of them write at once and
would take the same one. The brief only grows, and a line takes the id of an earlier
finding or the next one, so a finding keeps its id whatever is written after it. Two
reviewers' findings of one head are one finding (`_same`): the same file, lines at most
`NEAR` apart, the same principle, both raised. A finding one reviewer raised and another
dismissed there is kept as two, the dismissal printed beside it (`Finding.contradicts`).
A section a reviewer wrote again at the same head takes the place of its earlier one, whose
findings keep their ids and count for nothing (`Finding.superseded`).

The crew answers by id, `Finding F2: fixed, ...` or `Finding F2: not fixed, ..., because
<reason>` (`ANSWER`). An answer with no id, `Finding: fixed, ...`, is how a brief from
before the ids answered: such answers go, in order, to the findings with no bucket, as the
crew's count matched them. Only an **Act on** finding blocks a merge, and one from before
the buckets does, as every finding did. Its decline counts only with a reason that cites a
`path:line`, a command in backticks, or a gate the Result names (`Gate: question <n>`); a
reason given for an earlier finding is refused; and a finding on one of `RISKS` declined
counts only on a gate, which asks the user with the default "fix it". Severity is a field
and decides nothing.

`jmerge` (`ready.said_of`, `short_of`), the crew skill's count of the findings and its
second pass (`jbriefs --findings --left` and `--rounds`) and jbus's ask (`expedite`) read
the brief through this module and nowhere else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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

    @property
    def place(self) -> str:
        return self.path + ("" if self.line is None else f":{self.line}")


@dataclass(frozen=True)
class Section:
    """One `## Review` section: who wrote it, its verdict's first word, its head, the
    findings it lists (`found` counts them) and the ones it dismissed."""

    by: str = ""
    verdict: str = ""
    ran: bool = False
    head: str = ""
    raised: tuple[Raised, ...] = ()
    found: int = 0


@dataclass(frozen=True)
class Answer:
    """The crew's answer to a finding: fixed, or not fixed for `reason`."""

    fixed: bool
    what: str
    reason: str = ""
    by_id: bool = True


@dataclass
class Finding:
    """One finding of the triaged list, with its id: the lines that raised it, one per
    reviewer, and the answer it has."""

    id: str
    raised: list[Raised]
    contradicts: str = ""
    superseded: bool = False
    answer: Answer | None = None
    refused: str = ""
    first: str = ""

    @property
    def lead(self) -> Raised:
        return self.raised[0]

    @property
    def reviewers(self) -> tuple[str, ...]:
        return tuple(one.reviewer for one in self.raised)

    @property
    def bucket(self) -> str:
        return min((one.bucket for one in self.raised), key=BUCKETS.index)

    @property
    def severity(self) -> str:
        ranks = ("error", "warning", "info")
        return min(
            (one.severity for one in self.raised),
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
        return next((one.risk for one in self.raised if one.risk), "")

    @property
    def sent(self) -> bool:
        """Whether the crew was sent it, and owes it an answer: a finding of a section that
        stands, in the list the reviewer sends."""
        return not self.superseded and self.bucket in SENT

    @property
    def blocks(self) -> bool:
        """Whether it holds the merge until it is answered: an Act on finding, which every
        finding from before the buckets is."""
        return self.sent and self.bucket == ACT_ON

    @property
    def ended(self) -> bool:
        return self.answer is not None and not self.refused

    @property
    def why(self) -> str:
        return WHY[self.refused].format(first=self.first, risk=self.risk) if self.refused else ""


@dataclass
class Triage:
    """A brief's findings, merged and answered: `sections` in order, `findings` by id,
    `answers` by id, and the `Reviewer:` lines that name a thread (`named`)."""

    sections: list[Section] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    answers: dict[str, Answer] = field(default_factory=dict)
    named: int = 0

    def blocking(self) -> tuple[Finding, ...]:
        """The findings that hold the merge: each Act on finding with no answer that
        counts, in the order of their ids."""
        return tuple(one for one in self.findings if one.blocks and not one.ended)

    def sent(self) -> list[Finding]:
        return [one for one in self.findings if one.sent]


def _tags(text: str) -> tuple[str, dict[str, str]]:
    """The text of a finding line with its tags taken off its end, and the tags."""
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
    """One line of a section's list, past its `- `."""
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
    """Each `## Review` section, as the crew's count and `jmerge` read it: its list runs
    from `Findings:` to `Dropped:` or the next heading, a line in it that starts `- ` and is
    not `- none` is a finding, and the lines under `Dismissed:` that start `- ` are its
    dismissed findings."""
    found: list[dict] = []
    listing = dismissing = False
    for line in text.splitlines():
        if line.startswith("## "):
            listing = dismissing = False
            if line == "## Review":
                found.append({"by": "", "verdict": "", "ran": False, "head": "", "lines": []})
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
    sections = []
    for number, one in enumerate(found):
        raised = tuple(
            _raised(text, number, one["by"], one["head"], dismissed)
            for text, dismissed in one["lines"]
        )
        listed = sum(1 for _, dismissed in one["lines"] if not dismissed)
        sections.append(Section(one["by"], one["verdict"], one["ran"], one["head"], raised, listed))
    return sections


def _near(one: Raised, other: Raised) -> int | None:
    """How far apart two findings of one place are, or None where they are not of one place:
    the same file, both of a line at most `NEAR` apart or both of the file as a whole, and
    the same principle, which a finding tagged `none` has with nothing."""
    if one.path in ("", "-") or one.path != other.path:
        return None
    if not one.category or one.category.lower() == "none" or one.category != other.category:
        return None
    if one.line is None or other.line is None:
        return 0 if one.line is other.line else None
    apart = abs(one.line - other.line)
    return apart if apart <= NEAR else None


def _same(finding: Finding, one: Raised) -> int | None:
    """How far `one` is from a finding it would be merged into, or None where it is not:
    another reviewer's finding of the same head and place, both raised and both written
    with a bucket, and one line from each reviewer at most."""
    lead = finding.lead
    if finding.superseded or lead.legacy or one.legacy or not one.head:
        return None
    if DISMISSED in (lead.bucket, one.bucket) or lead.head != one.head:
        return None
    if one.reviewer in finding.reviewers:
        return None
    return _near(lead, one)


def _superseded(sections: list[Section]) -> set[int]:
    """The sections a later one by the same reviewer at the same head took the place of."""
    last = {(one.by, one.head): number for number, one in enumerate(sections) if one.by}
    return {
        number
        for number, one in enumerate(sections)
        if one.by and last[(one.by, one.head)] != number
    }


def _answers(text: str) -> tuple[dict[str, Answer], list[Answer]]:
    """The answers by id, the last for each id, and the answers with no id, in order."""
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
    """Refuse the answers that do not count: an Act on finding's decline that cites
    nothing, that gives an earlier finding's reason, or that leaves a risky finding with no
    gate. An answer with no id, to a finding from before the ids, is read as it was."""
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
    """The brief's findings, merged, given their ids, contradicted and answered."""
    sections = _sections(text)
    stale = _superseded(sections)
    findings: list[Finding] = []
    for number, section in enumerate(sections):
        for one in section.raised:
            near = [(apart, f) for f in findings if (apart := _same(f, one)) is not None]
            if near and number not in stale:
                min(near, key=lambda pair: pair[0])[1].raised.append(one)
            else:
                findings.append(Finding(f"F{len(findings) + 1}", [one], superseded=number in stale))
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
        if one.legacy:
            one.answer = next(unnumbered, None)
        else:
            one.answer = answers.get(one.id)
    _judge(findings, text)
    named = sum(
        1
        for line in text.splitlines()
        if line.startswith("Reviewer:") and "".join(line.split()[1:2]) not in ("", "none", "none,")
    )
    return Triage(sections, findings, answers, named)


def listed(said: Triage) -> list[str]:
    """The triaged list as `jbriefs --findings` prints it: each finding by id, a dismissal
    that contradicts one beside it, and under each who raised it and its answer."""
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
    elif one.sent:
        lines.append("  answer: none" + (", it blocks the merge" if one.blocks else ""))
    return lines


def left(said: Triage) -> str:
    """What the crew is to do next with the findings, the one line its count prints: wait
    for a reviewer, answer the findings that have no answer, or write the `Fixed:` line it
    names. The findings of the last round, the sections at the head of the last one, are the
    ones a fix answers."""
    sent = said.sent()
    if not said.sections:
        return "wait: the review is not written in the brief yet"
    wrote = len({one.by for one in said.sections if one.by})
    if said.named > 1 and wrote < said.named:
        return f"wait: {wrote} of {said.named} reviewers have written their section"
    open_ = [one for one in sent if not one.ended]
    if open_:
        line = f"not yet: {len(open_)} of {len(sent)} findings have no Finding: line"
        named = [
            one.id + (f" ({one.why})" if one.refused else "") for one in open_ if not one.legacy
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
    """What the crew's second pass reads of the review, one line: how many sections ran, the
    head the last of them saw, and every head a section names, or `-` for none."""
    ran = [one for one in said.sections if one.ran]
    saw = next((one.head for one in reversed(ran) if one.head), "-")
    heads = ",".join(dict.fromkeys(one.head for one in said.sections if one.head)) or "-"
    return f"{len(ran)} {saw} {heads}"
