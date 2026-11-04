"""Judge a brief's `Proves it:` line: does it name something outside the agent that shows the
task is done, or only the agent's own word."""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAMED = (
    (
        "a test",
        r"\btests?/|\btest_\w+|\w+_test\b|\bpytest\b|\buv run\b"
        r"|\bmake (?!(sure|certain|it|this|that|a|an|the)\b)[\w-]+",
    ),
    ("an external judge", r"\b(external|outside|independent|blind) judge\b|\bthird[- ]party\b"),
)
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
        return f"brief's Proves it: line {self.fault} {_RUNS if self.was else _PROVES}"


def proof(said: str) -> Proof:
    """Judge what a `Proves it:` line says, without its label.

    A line that begins `judged: <why>` is a person's call, and holds with its reason. Otherwise
    it reads the tables in turn, and the first match decides. `_NAMED` lists the words that on
    their own name something outside the agent: a test's path or name, a runner, a make target
    or a named judge. A command in backticks that names no agent counts too, so a test that the
    crewmate runs is still a test. `_RAN_NOTHING` lists the words that once counted and no
    longer do, as CI, the user and a word for a test. `_SELF` lists the agent's own claims.
    `_LOOSE` lists words that count only when no agent is named, because "the agent measures
    it" is the agent's own claim.
    """
    said = said.strip()
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
