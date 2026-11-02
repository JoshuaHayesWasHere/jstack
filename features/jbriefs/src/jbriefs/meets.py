"""The reviewer's judgement of the brief, as a typed line `jmerge` reads, and the one rule it is
read by. pr-review's `templates/review.md` gives the shape, and this module is its one parser.

A `## Review` section says whether the change meets its brief on one line, and under it one item
for each `Done when` line it does not take as met:

    Meets the brief: no, 2 of 3
    - unmet 3: <the third Done when line, as the brief words it>
    - waiting 2: <the second, which only waits on CI>

`<n>`, after `of`, is the count of the brief's `Done when` lines (`done_when`), and `<m>`, before
it, how many of them the change meets. `k`, in each item, is the number of a `Done when` line in
the brief's list, from 1. An `after-merge` line can only be proven once the change is merged, and
a `waiting` line waits only on CI: neither is unmet, so `m` is `n` less the `unmet` items, and
`yes` is the line with no `unmet` item, `yes, <n> of <n>`. Any other shape reads as no line
(`parse`): today's free text `Meets the brief: yes` included, so a skipped or skimmed check is
not a pass.

`reading` is the rule. The last round of the brief's review, at the head the last section that
ran saw, is the one that counts: each reviewer's last section of the round says `yes`, with the
brief's count, or the pull request is short. A round at a later head, such as the scoped review
of the fix, takes the place of an earlier `no`, and so does a scoped pass at the same head, which
rules on what the crew declined. A `Done when` line the round says is unmet is cleared by a
`Waived: <the Done when line>, <thread>/<message>` line of the brief whose words the caller
checked (`heard`): `jmerge` asks jbus, by the same check `jbus queue approve --message` reads a
word with.

`jmerge` (`ready.short_of`), the crew skill's second pass (`jbriefs --meets`) and the replay in
`features/jmerge/scripts/meets_replay.py` read the line through this module and nowhere else.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass

from jbriefs import findings
from jsettings.brief import head_lines

LABEL = "Meets the brief:"
YES, NO = "yes", "no"
UNMET, AFTER_MERGE, WAITING = "unmet", "after-merge", "waiting"
KINDS = (UNMET, AFTER_MERGE, WAITING)
"""The kinds of item under the line. Only `UNMET` counts against the brief."""
UNREAD, MISCOUNTED, NONE = "unread", "miscounted", "none"
WAIVED = "Waived:"

_LINE = re.compile(rf"{LABEL} ({YES}|{NO}), (\d+) of (\d+)")
_ITEM = re.compile(rf"- ({'|'.join(KINDS)}) (\d+): \S.*")
_REF = re.compile(r"\S+/\S+")


@dataclass(frozen=True)
class Meets:
    """One section's typed line: its word, how many `Done when` lines it meets of how many, and
    the number of each line it names under each kind."""

    word: str
    met: int
    of: int
    unmet: tuple[int, ...] = ()
    after_merge: tuple[int, ...] = ()
    waiting: tuple[int, ...] = ()


def parse(lines: tuple[str, ...]) -> Meets | None:
    """The typed line of a section, from the lines `lines_of` gives: the `Meets the brief:` line
    and the `- ` items right under it. None where it has no such line, or one whose word, counts
    and items do not agree."""
    if not lines:
        return None
    found = _LINE.fullmatch(lines[0].strip())
    if not found:
        return None
    word, met, of = found[1], int(found[2]), int(found[3])
    named: dict[str, list[int]] = {kind: [] for kind in KINDS}
    for line in lines[1:]:
        item = _ITEM.fullmatch(line.strip())
        if not item:
            return None
        named[item[1]].append(int(item[2]))
    every = [k for kind in KINDS for k in named[kind]]
    if len(set(every)) != len(every) or any(not 1 <= k <= of for k in every):
        return None
    if met != of - len(named[UNMET]) or (word == YES) != (met == of):
        return None
    return Meets(word, met, of, *(tuple(named[kind]) for kind in KINDS))


def lines_of(text: str, section: findings.Section) -> tuple[str, ...]:
    """The section's last `Meets the brief:` line and the `- ` items right under it, read from
    the brief from the section's heading (`findings.Section.line`) to the next heading."""
    found: list[str] = []
    under = False
    for line in text.splitlines()[section.line + 1 :]:
        if line.startswith("## "):
            break
        if line.startswith(LABEL):
            found, under = [line], True
        elif under and line.startswith("- "):
            found.append(line)
        else:
            under = False
    return tuple(found)


def done_when(lines: list[str]) -> tuple[str, ...]:
    """The items of the first `Done when:` list in `lines`, each re-wrapped line joined to the
    item above it."""
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


def _plain(text: str) -> str:
    return " ".join(text.split()).lower()


def waivers(text: str) -> tuple[tuple[int, str], ...]:
    """Each `Waived: <the Done when line>, <thread>/<message>` line of the brief, as the number of
    the `Done when` line it names and the reference of the word it rests on. The line is named by
    its words, spaces and case aside, whole or by a start no other line has. A line that names
    none, or two, waives nothing."""
    items = [_plain(one) for one in done_when(head_lines(text))]
    found = []
    for line in text.splitlines():
        if not line.startswith(WAIVED):
            continue
        named, _, ref = line.removeprefix(WAIVED).strip().rpartition(", ")
        said = _plain(named)
        if not said or not _REF.fullmatch(ref):
            continue
        whole = [k for k, one in enumerate(items, 1) if one == said]
        start = [k for k, one in enumerate(items, 1) if one.startswith(said)]
        if whole or len(start) == 1:
            found.append(((whole or start)[0], ref))
    return tuple(found)


def refs(text: str) -> tuple[str, ...]:
    """The reference of each word a `Waived:` line rests on, once each, for the caller to check."""
    return tuple(dict.fromkeys(ref for _, ref in waivers(text)))


@dataclass(frozen=True)
class Reading:
    """What the last round says of the brief: `YES`, `NO`, `UNREAD` for a section with no line
    `parse` reads, `MISCOUNTED` for one whose count is not the brief's, or `NONE` where the rule
    does not apply. `said` is the count a `MISCOUNTED` section gave, `unmet` the numbers left
    unmet once the waivers are taken, and `waived` the numbers a waiver cleared."""

    word: str
    head: str = ""
    met: int = 0
    count: int = 0
    said: int = 0
    unmet: tuple[int, ...] = ()
    waived: tuple[int, ...] = ()


def last_round(triage: findings.Triage) -> list[findings.Section]:
    """The sections of the last round: of the sections that ran and count for a reviewer, those at
    the head and of the kind, scoped or not, of the last one, each reviewer's last."""
    ran = [one for one in triage.roster.counted(triage.sections) if one.ran and one.head]
    if not ran:
        return []
    head, scoped = ran[-1].head, ran[-1].scoped
    last = {one.by: one for one in ran if (one.head, one.scoped) == (head, scoped)}
    return list(last.values())


def reading(text: str, heard: Collection[str] = ()) -> Reading:
    """The rule (`Reading`). It does not apply to a brief that says `Review: none`, to one with no
    review that ran, or to one with no `Done when` list. `heard` holds the references of the
    words the caller checked, and only a waiver that rests on one of them counts."""
    items = done_when(head_lines(text))
    triage = findings.triage(text)
    last = last_round(triage)
    if not items or triage.mode == findings.NONE or not last:
        return Reading(NONE, count=len(items))
    count, head = len(items), last[0].head
    said = [parse(lines_of(text, one)) for one in last]
    if any(one is None for one in said):
        return Reading(UNREAD, head, count=count)
    off = next((one.of for one in said if one.of != count), None)
    if off is not None:
        return Reading(MISCOUNTED, head, count=count, said=off)
    named = {k for one in said for k in one.unmet}
    waived = named & {k for k, ref in waivers(text) if ref in heard}
    unmet = tuple(sorted(named - waived))
    word = NO if unmet else YES
    return Reading(word, head, count - len(unmet), count, unmet=unmet, waived=tuple(sorted(waived)))


def shown(said: Reading) -> str:
    """The reading as `jbriefs --meets` prints it, one line of four fields the crew skill's
    second pass reads: the word, how many lines are met (`-` where no line was read), the
    brief's count, and the head (`-` for none)."""
    met = str(said.met) if said.word in (YES, NO) else "-"
    return f"{said.word} {met} {said.count} {said.head or '-'}"
