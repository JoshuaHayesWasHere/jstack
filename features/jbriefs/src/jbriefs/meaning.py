"""What a brief asks for, as a fingerprint that an approval binds to, and the rule that
decides whether a later brief still asks for the same thing.

It is deterministic and asks no model. An approval binds to the goal, the scope and the
done-when of a brief, and to nothing else: the fields of `MEANING` (the title, Task, Done
when, Where, Do not touch and Size). Every other field says how the work is done or who
runs it. Those are the fields of `NOT_MEANING`: Skills, Decisions, Design, Proves it,
Review, Playbook, Pull request, Stack, Read, Change, Rests on, Sources, Ruled out, and
`Home:` and `Thread:`, which say whom a brief is sent to. A field that the template does not
name, and anything under a `## ` in the brief, count the same way. An edit to any of them
keeps the go.

Each field becomes lines, and each line becomes its tokens (`tokens`):

- a code span in backticks, a URL, and a word with a `/`, an inner `.` or a digit (a path,
  a file, a number) stay exact, as written, with `EXACT` in front;
- every other word is lowercased, and loses the markdown, the punctuation and the white
  space around it, and a word of `FILLER` is dropped; a `n't` becomes a word of its own,
  `not`, so a negation adds a word and is never a typo of the word it negates;
- the tokens of a line are sorted, so a line said in another order is the same line.

A list field (`Done when:` and any other with `- ` items) gives a line for each item, with a
re-wrapped item joined into one. Any other field is one line. The lines of a field are
sorted, and the fields go in the order of `MEANING`, each present even when the brief does
not have it. The value of `VALUES` (Size) stays exact as a whole, lowercased and with its
white space collapsed.

A brief means what the approved one meant (`same`) when each field has as many lines as
before, and each line of the approved brief pairs with one line of the new brief. Two lines
pair when their exact tokens are the same and their words are the same, except that a word
of `NEAR` letters or more may be within `EDITS` edits of the approved word, which is how a
fixed typo passes. So a typo, a change of formatting, punctuation or case, and lines put in
another order keep the go. A line added, removed or changed in a field of `MEANING`, or a
changed path, number or value, needs a new approval.

An approval recorded before this module read the title and Task has neither in its fingerprint
(`LEGACY`), and holds for any title and Task. The comparison skips the fields that the old
approval recorded and that are no longer part of the meaning.

Its limit is that it compares words, not meaning. A reword that swaps one content word for
another ("must" for "may", "all" for "any") needs a new approval, by design, because a check
with no model cannot tell a harmless synonym from a change of intent. And two words of five
letters or more within two edits of each other count as one word, which is the cost of keeping
the go of a fixed typo. That covers "files" and "fixes", and opposites too, "include" and
"exclude", "import" and "export", "maximum" and "minimum", so such a swap keeps the go.
"""

from __future__ import annotations

import hashlib
import json
import re

from jbriefs import parse

MEANING = (parse.TITLE, "Task", "Done when", "Where", "Do not touch", "Size")
NOT_MEANING = (
    "Home",
    "Thread",
    "Skills",
    "Decisions",
    "Design",
    "Proves it",
    "Review",
    "Playbook",
    "Pull request",
    "Stack",
    "Read",
    "Change",
    "Rests on",
    "Sources",
    "Ruled out",
)
LEGACY = tuple(label for label in MEANING if label not in (parse.TITLE, "Task"))
VALUES = ("Size",)
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
_NOT = re.compile(r"n['’]t\b", re.I)
_ITEM = re.compile(r"[ \t]*[-*+][ \t]+|[ \t]*\d+[.)][ \t]+")

Line = list[str]
Meaning = list[list]


def tokens(line: str) -> Line:
    """A line's tokens, sorted. The exact tokens carry an `EXACT` mark, and the other words
    carry none."""
    found = [EXACT + span.strip() for span in _SPAN.findall(line)]
    line = _SPAN.sub(" ", line)
    found += [EXACT + url.rstrip(".,;:*") for url in _URL.findall(line)]
    line = _NOT.sub(" not", _URL.sub(" ", line))
    line = re.sub(r"(?<=\w)['’](?=\w)", "", line)
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
    """The lines of a field: one line for each list item, or the whole field as one line."""
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
    """The fingerprint of a brief: `[label, lines]` for each field of `MEANING`, in order."""
    held: dict[str, list[str]] = {}
    for label, lines in parse.fields(text):
        if label in MEANING:
            held.setdefault(label, []).extend(lines)
    made: Meaning = []
    for label in MEANING:
        if label in VALUES:
            value = " ".join(" ".join(held.get(label, [])).split()).lower().rstrip(".")
            lines = [[EXACT + value]] if value else []
        else:
            lines = [tokens(line) for line in _lines(held.get(label, []))]
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
    """Whether every item of `approved` pairs with its own item of `now`, with as many items in
    each. Equal items pair first, then each item pairs with the first item that is `alike`."""
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
    was, here = dict(approved), dict(now)
    labels = MEANING if parse.TITLE in was else LEGACY
    return all(
        _pairs(
            was.get(label, []), here.get(label, []), lambda one, other: _pairs(one, other, _near)
        )
        for label in labels
    )
