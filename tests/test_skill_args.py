import re
import shlex
from pathlib import Path

import pytest

from testing.paths import REPO

SKILLS = sorted((REPO / "skills").glob("*/*.md"))

TYPED = {
    "pr-review": ["run a-slug", "a-slug"],
    "crew": ["a-slug"],
    "scout": ["a-slug"],
    "nohome": ["off", "on"],
}
EVERY_POSITION = "zero one two three four five six seven eight nine ten"

DOLLAR, EDGE = "\ue000", "\ue001"
FENCE = re.compile(r"^[ \t]*```[^\n]*\n.*?^[ \t]*```[ \t]*$", re.M | re.S)


def loaded(text, typed, names=()):
    """A skill's text as Claude Code hands it over when the skill is typed with arguments.

    This is `nHe` of the installed build (claude 2.1.296), the function behind "String
    substitutions" in https://code.claude.com/docs/en/skills, then the `${CLAUDE_*}`
    names and the `!` command forms that page lists.
    """
    try:
        args = shlex.split(typed)
    except ValueError:
        args = typed.split()

    def put(value):
        return EDGE + value.replace("$", DOLLAR) + EDGE

    def at(match):
        index = int(match.group(1))
        if index < len(args):
            return put(args[index])
        return DOLLAR + match.group(0)[1:]

    named = sorted(((name, i) for i, name in enumerate(names) if name), key=lambda n: -len(n[0]))
    tokens = "|".join([r"\d", "ARGUMENTS", *(re.escape(name) + r"(?![\[\w])" for name, _ in named)])
    text = re.sub(rf"(?<!\\)\\\$(?={tokens})", DOLLAR, text, flags=re.A)
    for name, i in named:
        value = args[i] if i < len(args) else ""
        text = re.sub(
            rf"\${re.escape(name)}(?![\[\w])", lambda _, v=value: put(v), text, flags=re.A
        )
    text = re.sub(r"\$ARGUMENTS\[(\d+)\]", at, text, flags=re.A)
    text = re.sub(r"\$(\d+)(?!\w)", at, text, flags=re.A)
    text = text.replace("$ARGUMENTS", put(typed))
    text = re.sub(r"\$\{CLAUDE_[A-Z_]+\}", "<a value>", text)
    text = re.sub(r"^([ \t]*```)!", r"\1<ran>", text, flags=re.M)
    text = re.sub(r"(?<!\S)!`[^`\n]*`", "<what the command printed>", text)
    return text.replace(DOLLAR, "$").replace(EDGE, "")


def blocks(text):
    return FENCE.findall(text)


def argument_names(text):
    """The names a skill's frontmatter declares under `arguments`, in order."""
    front = text.split("---\n", 2)[1] if text.startswith("---\n") else ""
    found = re.search(r"^arguments:[ \t]*(.*)((?:\n[ \t]*-[ \t].*)*)", front, re.M)
    if not found:
        return []
    inline, listed = found.groups()
    words = inline.strip("[] \t").replace(",", " ").split() or [
        line.split("-", 1)[1] for line in listed.splitlines() if line
    ]
    names = [word.strip(" \t\"'") for word in words]
    return [name for name in names if name and not name.isdigit()]


def test_the_rule_replaces_what_the_documentation_says_it_replaces():
    assert loaded("Summarize $0", '"$ARGUMENTS from yesterday"') == (
        "Summarize $ARGUMENTS from yesterday"
    )
    assert loaded("$0 and $1, $2 stays", '"hello world" second') == (
        "hello world and second, $2 stays"
    )
    assert loaded(r"\$1.00 and \\$1 and $ARGUMENTS[0] and $1x", "a b") == (
        r"$1.00 and \\b and a and $1x"
    )
    assert loaded("$issue then $branch.", "7", ["issue", "branch"]) == "7 then ."
    assert loaded("$ARGUMENTS[5] is kept, $ARGUMENTS[1] is not", "a b") == (
        "$ARGUMENTS[5] is kept, b is not"
    )
    assert loaded("x=$1\u00e9 and $\u0661", "a b") == "x=b\u00e9 and $\u0661"
    assert loaded("```!\ndate\n```\nnow: !`date` in ${CLAUDE_SKILL_DIR}", "") == (
        "```<ran>\ndate\n```\nnow: <what the command printed> in <a value>"
    )


@pytest.mark.parametrize(
    "front",
    [
        "arguments: [issue, branch]",
        "arguments: issue branch",
        "arguments:\n  - issue\n  - branch",
        "arguments:\n- issue\n- branch",
        'arguments:\n  - "issue"\n  - branch\nuser-invocable: true',
    ],
)
def test_the_names_a_skill_declares_are_read_in_every_shape(front):
    text = f"---\nname: a\n{front}\n---\n```sh\ngh issue view $issue on $branch, $- stays\n```\n"
    assert argument_names(text) == ["issue", "branch"]
    assert blocks(loaded(text, "7 main", argument_names(text))) == [
        "```sh\ngh issue view 7 on main, $- stays\n```"
    ]


def test_a_skill_that_declares_no_names_has_none():
    assert argument_names("---\nname: a\n---\n$issue\n") == []


def test_the_blocks_of_a_skill_are_found():
    text = "a\n```sh\none $1\n```\n1. b\n   ```json\n   two\n   ```\n"
    assert blocks(text) == ["```sh\none $1\n```", "   ```json\n   two\n   ```"]
    assert blocks(loaded(text, "x y")) != blocks(text)


@pytest.mark.parametrize(
    ("skill", "typed"),
    [
        (skill, typed)
        for skill in SKILLS
        for typed in [*TYPED.get(skill.parent.name, []), EVERY_POSITION]
    ],
    ids=lambda value: value.parent.name if isinstance(value, Path) else value,
)
def test_a_skill_typed_with_arguments_keeps_its_blocks(skill, typed):
    text = skill.read_text()
    if re.search(r"^[ \t]*```", text, re.M):
        assert blocks(text) != []
    assert blocks(loaded(text, typed, argument_names(text))) == blocks(text)
