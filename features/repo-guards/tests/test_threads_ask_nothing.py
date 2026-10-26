"""No thread skill tells its thread to ask the user and wait in its own thread.

The rule is the user's (2026-10-13: "scouts and crewmates should not have interactive questions,
those would be somethign jbus should flag up back to you to prompt me to answer"). A crewmate, a
scout or an expert puts a question only the user can answer to jbus as a gate
(`features/home/templates/gates.md`), and one whose default is irreversible, such as a force-push
to a shared branch, a deploy, deleting data or a message to anyone outside, holds there with its
`Holds:` and `Fail-safe:` lines. Nothing in the thread waits on an answer typed into it.

The lint reads every file of the three skills but their tests, outside fenced blocks, one
sentence at a time, and fails on a sentence that tells the thread to pause, or that asks and
waits in one breath. A sentence it fails on is reworded into a gate, never let off by a list.
"""

import re

import pytest

from testing.paths import REPO

READ_SET = ("features/crew/", "features/scout/", "features/expert/")
FENCED = re.compile(r"^[ \t]*```.*?^[ \t]*```[ \t]*$", re.M | re.S)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)")
PAUSE = re.compile(r"\bpause[ds]? (?:for|before|until|on)\b", re.I)
ASK = re.compile(r"\bask(?:s|ed|ing)? (?:the user|them|here|in (?:this|its own) thread)\b", re.I)
WAIT = re.compile(r"\bwait(?:s|ed|ing)?\b", re.I)


def sentences(text):
    return [
        " ".join(one.split()) for one in SENTENCE_END.split(FENCED.sub("", text)) if one.strip()
    ]


def asks_and_waits(sentence):
    """Whether a sentence tells a thread to hold for an answer in its own thread."""
    return bool(PAUSE.search(sentence) or (ASK.search(sentence) and WAIT.search(sentence)))


def thread_files():
    for skill in READ_SET:
        for path in sorted((REPO / skill).rglob("*.md")):
            if "tests" not in path.relative_to(REPO).parts:
                yield path.relative_to(REPO).as_posix(), path


def sentences_that_ask():
    return [
        (relative, sentence)
        for relative, path in thread_files()
        for sentence in sentences(path.read_text())
        if asks_and_waits(sentence)
    ]


def test_the_lint_reads_each_thread_skill():
    read = {relative for relative, _ in thread_files()}
    assert {f"{skill}SKILL.md" for skill in READ_SET} <= read


def test_no_thread_skill_asks_the_user_and_waits_in_its_own_thread():
    assert sentences_that_ask() == []


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("Pause for the user's word before four things only: a deploy.", True),
        ("Only the four pauses of Carry on are asked here and waited on.", True),
        ("Ask the user in this thread, and wait for the answer.", True),
        ("Ask the user, then end your turn waiting.", True),
        ("The thread pauses until the user answers.", True),
        ("Park it as a gate: the action waits for the user's answer.", False),
        ("Claude Code stops the thread to ask the user before it runs any of those.", False),
        ("Asked by: the slug of the brief. It waits for the user's word.", False),
        ("End your turn and wait for the line.", False),
        ("```sh\necho 'ask the user and wait'\n```", False),
        ("Ask the user.\nWait for a test slot.", False),
    ],
)
def test_the_lint_flags_a_sentence_that_asks_and_waits(text, flagged):
    assert any(asks_and_waits(one) for one in sentences(text)) is flagged
