"""Judge a brief's `Proves it:` line: does it name something outside the agent that shows the
task is done, or only the agent's own word."""

from __future__ import annotations

import re
from dataclasses import dataclass

from jbriefs import proved
from jbriefs.meets import done_when

_NAMED = (
    (
        "a test",
        r"\btests?/|\btest_\w+|\w+_test\b|\bpytest\b|\buv run\b"
        r"|\bmake (?!(sure|certain|it|this|that|a|an|the)\b)[\w-]+",
    ),
    ("an external judge", r"\b(external|outside|independent|blind) judge\b|\bthird[- ]party\b"),
)
_NO_COMMAND = re.compile(
    r"\btests?/|\btest_\w+|\w+_test\b|\.test\.|\bpytest\b|\btest\b"
    r"|\bmake (?!(sure|certain|it|this|that|a|an|the)\b)[\w-]+"
    r"|^\s*(rg|grep|git grep)\b|^\s*\S+\s*$",
    re.I,
)
"""A span in backticks that is no command of the product: one that runs a test (`_NAMED`'s test
with `uv run` left out, which runs a product's command as often as a test, and with a runner's
`test` word and a `.test.` file in), a search of the repo's own text, or a single word, which
names a file or a value and runs nothing."""
_SEEN = (
    (
        "a command of the product with what it prints",
        (
            r"^[^`]*?\b(prints?|shows?|reads?|reports?|answers?|says?|exits?)\b",
            r"\b(prints?|shows?|reports?)( \w+)? (in|from|by)\s*$",
        ),
    ),
    (
        "a measure read after the merge",
        (
            r"\bafter (the|its) merge\b|\b(a|one|an) (whole |full )?(day|week|hour)s? (after|of)\b"
            r"|\bafter (a|one|an) (whole |full )?(day|week|hour)\b"
            r"|\b(first|next) (whole |full )?(day|week|hour)\b",
            r"\d|\bat (most|least)\b|\b(metrics?|measured?|counts?|share|rate|query)\b"
            r"|\b(grows?|falls?|reads?|prints?|shows?|reports?|Instruments)\b",
        ),
    ),
    ("a person's call", (r"\bjudged:\s*\S",)),
)
"""What a user sees, beside a test, that shows a change to code is done, each with the patterns
one clause of the `Proves it:` line holds all of (a clause is cut at `;` and at a period that ends
a sentence, with its parentheses left out): a command of the product in backticks (none of
`_NO_COMMAND`) with what it prints after it, or a verb of
printing just before it (`shows in`); a time after the merge and a count or a measure read
then; or `judged: <why>`, a person's call. A line that names a test and none of these proves the
change by a test alone."""
_CLAUSE = re.compile(r";|\.\s+(?=[A-Z`])|\.$")
_PAREN = re.compile(r"\([^()]*\)")
_JUDGED = re.compile(r"^judged:\s*(?P<why>.*)$", re.I)
_RAN_NOTHING = (
    ("an external judge", "names CI, which runs nothing by itself", r"\bCI\b|\bgithub\b"),
    (
        "the user",
        "names the user with no judged: <why>",
        r"\bthe user\b|\buser's\b|\bthe (operator|owner)\b|\bhis (word|pick|eye)\b",
    ),
    (
        "a test",
        "names a test by the word alone",
        r"\b(?!(crew|crewmates?|reviewers?|agents?|self|model|it|he|she|they|who|that|which"
        r"|will|can|could|should|would|must|to|does|did|may|might)\b)[\w-]+[ -]tests\b",
    ),
)
"""The words proof.py once took as a proof on their own, each with the kind it took them for,
the fault it finds in them now, and its pattern. CI and a word for a test run nothing anyone can
rerun, and the user's word is a proof only with the reason no command can stand in for it."""
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
    ("a metric", r"\bmetrics?\b|\bmeasured?\b|\bbenchmarks?\b|\blatency\b|\bp\d{2}\b|\d\s*%"),
    ("a dataset", r"\bdata ?sets?\b|\bcorpus\b|\bfixtures?\b|\bgolden\b|\bevals?\b"),
    ("an external judge", r"\bjudge\b"),
)
_DRAWN = r"(window|screen|ui|app|page|tree|sidebar|hover|desktop|browser)s?"
_SHOWN = re.compile(
    r"\bscreen[- ]?(shots?|grabs?|captures?|recordings?)\b"
    rf"|\b(shots?|recordings?)\s+of\b[^.;,()]{{0,60}}?\b{_DRAWN}\b"
    rf"|\brecord(s|ed)?\s+(the|a|its)\s+{_DRAWN}\b",
    re.I,
)
"""A screenshot, a shot or a recording of a window or the UI, which the user does not take as
proof (2026-11-08: "i don't need screenshots of anything")."""
_SHOWN_FAULT = "asks for a screenshot, a shot or a recording of the window as proof"
_INSTEAD = "(prove a UI change by a test, or by a live read of the data it draws)"
_SPAN = re.compile(r"`([^`\n]+)`")
_PROVES = "(name a test, a command, a metric, a dataset, an external judge or the user)"
_RUNS = (
    "(name a command in backticks, a `tests/...py[::name]` path, or `judged: <why>` for what "
    "only a person can judge)"
)


@dataclass(frozen=True)
class Proof:
    """A brief's `Proves it:` line, which names something outside the agent that shows the task
    is done.

    `kind` is the first thing the line names that is not the agent's own claim, and `fault`
    says why the line names nothing of the sort. One of the two is set. `was` is set on a line
    that names only what proof.py once took and no longer does (`_RAN_NOTHING`): the kind the
    older rule took it for, so a caller can warn of the line before it refuses it.
    """

    said: str
    kind: str = ""
    fault: str = ""
    was: str = ""

    @property
    def why(self) -> str:
        """Why the proof does not hold, as one line. It is an empty string when it holds."""
        if not self.fault:
            return ""
        if self.fault == _SHOWN_FAULT:
            return f"brief's Proves it: line {self.fault} {_INSTEAD}"
        return f"brief's Proves it: line {self.fault} {_RUNS if self.was else _PROVES}"

    @property
    def test_alone(self) -> bool:
        """Whether the line names a test, by its run or by the word, and nothing a user sees
        beside it (`_SEEN`)."""
        if "a test" not in (self.kind, self.was):
            return False
        return not any(_seen(clause) for clause in _CLAUSE.split(_PAREN.sub("", self.said)))


def _seen(clause: str) -> bool:
    """Whether one clause of a `Proves it:` line names what a user sees (`_SEEN`): a command's
    two patterns are read after each command in backticks, up to the next one, and just before
    it, and each other kind's patterns over the whole clause."""
    (_, (after, before)), *rest = _SEEN
    for span in _SPAN.finditer(clause):
        if _NO_COMMAND.search(span[1]):
            continue
        if re.search(after, clause[span.end() :], re.I) or re.search(
            before, clause[: span.start()], re.I
        ):
            return True
    return any(all(re.search(one, clause, re.I) for one in patterns) for _, patterns in rest)


def proof(said: str) -> Proof:
    """Judge what a `Proves it:` line says, without its label.

    A line that asks for a screenshot, a shot or a recording of the window (`_SHOWN`) is
    refused first, whatever else it names, `judged:` included. A line that begins `judged:
    <why>` is a person's call, and holds with its reason. Otherwise it reads the tables in turn,
    and the first match decides. `_NAMED` lists the words that on their own name something
    outside the agent: a test's path or name, a runner, a make target or a named judge. A
    command in backticks that names no agent counts too, so a test that the crewmate runs is
    still a test. `_RAN_NOTHING` lists the words that once counted and no longer do, as CI, the
    user and a word for a test. `_SELF` lists the agent's own claims.
    `_LOOSE` lists words that count only when no agent is named, because "the agent measures
    it" is the agent's own claim.
    """
    said = said.strip()
    if _SHOWN.search(said):
        return Proof(said, fault=_SHOWN_FAULT)
    if judged := _JUDGED.match(said):
        if not judged["why"].strip():
            return Proof(said, fault="is empty")
        return Proof(said, kind="judged")
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
    for was, fault, pattern in _RAN_NOTHING:
        if re.search(pattern, said, re.I):
            return Proof(said, fault=fault, was=was)
    for name, pattern in _SELF:
        if re.search(pattern, said, re.I):
            return Proof(said, fault=f"names {name}, the agent's own word")
    if re.search(r"\btests?\b", said, re.I):
        return Proof(said, fault=_RAN_NOTHING[-1][1], was="a test")
    for kind, pattern in _LOOSE:
        if re.search(pattern, said, re.I):
            return Proof(said, kind=kind)
    return Proof(said, fault="names nothing outside the agent")


def shown(text: str) -> str:
    """Why a brief's `Done when:` list asks for a screenshot, a shot or a recording of a window
    or the UI as proof, as one line naming the first item that does. It is an empty string when
    no item does."""
    for number, item in enumerate(done_when(text.splitlines()), 1):
        if _SHOWN.search(item):
            return f"brief's Done when {number} {_SHOWN_FAULT}: {item} {_INSTEAD}"
    return ""


def code(path: str) -> bool:
    """Whether a `Where:` path is code: neither docs nor config (`proved.of_kind`) nor a test
    (`proved.TEST_FILE`), read both as a file and as a directory, since a `Where:` path has its
    trailing `/` dropped. The whole repo, `.`, is code."""
    if path == ".":
        return True
    return not any(
        proved.TEST_FILE.search(one) or any(proved.of_kind(one, kind) for kind in proved.EXEMPT)
        for one in (path, f"{path}/")
    )


def user_sees(where: tuple[str, ...], said: str) -> str:
    """Why a brief for a change to code proves it by a test alone, as one line, from its `Where:`
    paths and its `Proves it:` line. It is an empty string when it does not.

    A brief whose `Where:` names a file of code (`code`) and whose `Proves it:` names a test and
    nothing a user sees beside it (`Proof.test_alone`) shows that the code runs, and not what a
    user meets once it merges. It is a warning and no fault: a change no user sees, such as a
    refactoring, is proved by its test alone.
    """
    if not any(code(path) for path in where) or not proof(said).test_alone:
        return ""
    return (
        "brief's Proves it: names a test alone for a change to code: beside the test, name what a "
        "user would see, a command of the product in backticks with what it prints, a measure "
        "read after the merge, or judged: <why> (a change no user sees, such as a refactoring, "
        "may keep its test alone)"
    )
