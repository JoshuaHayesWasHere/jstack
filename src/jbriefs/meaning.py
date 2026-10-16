"""What a brief asks for, as a fingerprint an approval is bound to, and the rule that says
whether a later brief still asks for the same thing.

It is deterministic and asks no model. The fields read are the ones that carry scope and
risk: every field of the brief but `WORDING` (the title, Task, Decisions, Design, Read,
Change, Rests on, Sources and Ruled out), so a field the template does not name, such as
an eval's `Candidates:`, counts, and so does anything under a `## ` in the brief. `Home:`
and `Thread:` (`ROUTING`) say whom a brief is sent to, not what it asks for, and are left
out too.

Each field becomes lines, and each line its tokens (`tokens`):

- a code span in backticks, a URL, and a word with a `/`, a `.` inside it or a digit (a
  path, a file, a number) are kept exact, as written, marked with `EXACT` in front;
- every other word is lowercased, with the markdown, the punctuation and the white space
  around it dropped, and a word of `FILLER` is dropped;
- the tokens of a line are sorted, so a line said in another order is the same line.

A list field (`Done when:` and any other with `- ` items) is a line for each item, a
re-wrapped item joined into one; any other field is one line. The lines of a field are
sorted, and the fields go in a fixed order: `SCOPE` first, as the template lists them,
then any other by its label. The values of `VALUES` (Size, Playbook, Review, Pull request
and Stack) are kept exact whole, lowercased and with their white space collapsed.

A brief means what the approved one meant (`same`) when it has the same fields, each with
as many lines, and each line of the approved one pairs with one line of the new one whose
exact tokens are the same and whose words are the same, but that a word of `NEAR` letters
or more may be within `EDITS` edits of the approved word: a typo fixed. So a typo, a
change of formatting, punctuation or case, lines or fields put in another order, and any
edit to the wording fields keep the go. A line added, taken out or changed, a path, a
number or a value changed, re-ask.

Its limit: it compares words, not meaning. A reword that swaps one content word for
another ("must" for "may", "all" for "any") re-asks, by design: a check with no model
cannot tell a harmless synonym from a change of intent. And two words of five letters or
more within two edits of each other count as one ("files" and "fixes"), which is the price
of keeping a fixed typo's go.
"""

from __future__ import annotations

import hashlib
import json
import re

from jbriefs import parse

WORDING = (
    parse.TITLE,
    "Task",
    "Decisions",
    "Design",
    "Read",
    "Change",
    "Rests on",
    "Sources",
    "Ruled out",
)
ROUTING = ("Home", "Thread")
SCOPE = (
    "Done when",
    "Proves it",
    "Size",
    "Where",
    "Do not touch",
    "Pull request",
    "Review",
    "Playbook",
    "Stack",
)
VALUES = ("Size", "Playbook", "Review", "Pull request", "Stack")
FILLER = frozenset(
    "a an the of to in on at for by with is are was be been it its that this as from so then "
    "there".split()
)
EXACT = "="
NEAR = 5
EDITS = 2

_SPAN = re.compile(r"`([^`\n]*)`")
_URL = re.compile(r"https?://[^\s)>\]`]+")
_WORD = re.compile(r"[\w./~-]+")
_ITEM = re.compile(r"[ \t]*[-*+][ \t]+|[ \t]*\d+[.)][ \t]+")

Line = list[str]
Meaning = list[list]


def tokens(line: str) -> Line:
    """A line's tokens, sorted: the exact ones marked with `EXACT`, the words bare."""
    found = [EXACT + span.strip() for span in _SPAN.findall(line)]
    line = _SPAN.sub(" ", line)
    found += [EXACT + url.rstrip(".,;:*") for url in _URL.findall(line)]
    line = re.sub(r"(?<=\w)['’](?=\w)", "", _URL.sub(" ", line))
    for word in _WORD.findall(line):
        word = word.strip("._~-")
        if re.search(r"\d|/|\w\.\w", word):
            found.append(EXACT + word)
            continue
        for part in re.split(r"[-~.]+", word):
            part = part.strip("_").lower()
            if part and part not in FILLER:
                found.append(part)
    return sorted(found)


def _lines(lines: list[str]) -> list[str]:
    """A field's lines as the lines it means: an item each, or all of it as one."""
    items: list[str] = []
    text: list[str] = []
    for line in lines:
        item = _ITEM.match(line)
        if item:
            items.append(line[item.end() :])
        elif items and line.strip():
            items[-1] += " " + line
        elif line.strip():
            text.append(line)
    return [" ".join(text), *items] if text and items else items or [" ".join(text)]


def meaning(text: str) -> Meaning:
    """The fingerprint of a brief: `[label, lines]` for each field it reads, in order."""
    held: dict[str, list[str]] = {}
    for label, lines in parse.fields(text):
        if label not in WORDING + ROUTING:
            held.setdefault(label, []).extend(lines)
    order = [label for label in SCOPE if label in held]
    order += sorted(label for label in held if label not in SCOPE)
    made: Meaning = []
    for label in order:
        if label in VALUES:
            value = " ".join(" ".join(held[label]).split()).lower().rstrip(".")
            lines = [[EXACT + value]] if value else []
        else:
            lines = [tokens(line) for line in _lines(held[label])]
            lines = [line for line in lines if line]
        made.append([label, sorted(lines)])
    return made


def fingerprint(made: Meaning) -> str:
    """The sha256 of a fingerprint, for a reader that only asks whether two are the same."""
    return hashlib.sha256(json.dumps(made, separators=(",", ":")).encode()).hexdigest()


def _edits(one: str, other: str) -> int:
    """The Levenshtein distance between two words."""
    row = list(range(len(other) + 1))
    for at, mine in enumerate(one, 1):
        was, row[0] = row[0], at
        for to, theirs in enumerate(other, 1):
            was, row[to] = row[to], min(row[to] + 1, row[to - 1] + 1, was + (mine != theirs))
    return row[-1]


def _near(approved: str, now: str) -> bool:
    if approved == now:
        return True
    if approved.startswith(EXACT) or now.startswith(EXACT):
        return False
    long = len(approved) >= NEAR and len(now) >= NEAR and approved.isalpha() and now.isalpha()
    return long and _edits(approved, now) <= EDITS


def _pairs(approved: list, now: list, alike) -> bool:
    """Whether every item of `approved` pairs with its own item of `now`, the two being as
    many: equal items first, then the first that is `alike`."""
    if len(approved) != len(now):
        return False
    left = list(now)
    rest = []
    for item in approved:
        if item in left:
            left.remove(item)
        else:
            rest.append(item)
    for item in rest:
        match = next((other for other in left if alike(item, other)), None)
        if match is None:
            return False
        left.remove(match)
    return True


def same(approved: Meaning, now: Meaning) -> bool:
    """Whether a brief whose fingerprint is `now` asks for what the approved one did."""
    if [label for label, _ in approved] != [label for label, _ in now]:
        return False
    return all(
        _pairs(was, lines, lambda one, other: _pairs(one, other, _near))
        for (_, was), (_, lines) in zip(approved, now, strict=True)
    )
