import copy
import json
import re

import pytest
from jsonschema import Draft202012Validator

from jbriefs.skills import listed
from test_home_thread import named
from testing.paths import REPO, skills

SKILLS = skills()
SCHEMAS = {
    path.stem: json.loads(path.read_text())
    for tools in ("features/jbus/tests/fixtures/t3", "testing/tests/fixtures/claude")
    for path in (REPO / tools).glob("*.json")
}
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
INLINE = re.compile(r"`(\{[^`\n]*\})`")
TOOL = re.compile(r"`((?<=`t3-code` server's `)\w+|t3_\w+|Agent)`")
PLACEHOLDER = re.compile(r"<[^<>]+>")
FILLED = {
    "<slug>": "fix-login",
    "<n>": "2",
    "<default branch>": "main",
    "<that worktree>": "/home/someone/trees/fix-login",
    "<the pull request's branch>": "fix-login",
    "<repo>": "demo",
    "<the checkout>": "/home/someone/repos/demo",
    "<the T3 project id>": "a1b2c3d4-0000-4000-8000-000000000000",
    "<seed>": "This message was written by the previous home of demo.",
    "<title>": "home: demo",
    "<date>": "2026-10-10",
    "<the lens's prompt>": "You are one of three reviewers of a thread.",
    "<the prompt file>": "/tmp/pr-review-fix-login.Ab12Cd/prompt.md",
    "<the pull request's url>": "https://github.com/someone/demo/pull/7",
    "<thread>": "mcp:this-thread",
    "<scheduledTaskId>": "scheduled-task:1c2d3e4f-0000-4000-8000-000000000000",
    "<model selection>": '{"provider": "codex", "model": "gpt-5-codex"}',
    "<the line>": "the home of demo is mcp:the-next-home now.",
    "<this thread's id>": "mcp:this-thread",
    "<the sender>": "mcp:the-sender",
    "<the message>": "From the cook: the oven is off.",
    "<the next home's id>": "mcp:the-next-home",
    "<the home's id>": "mcp:the-root-home",
    "<the home-id file>": "/home/someone/.local/state/home/demo/home-id",
    "<name>": "deploy-buttons",
    "<the actions>": "deploy, rollback",
    "<the secretRef from step 2>": "secret-ref:5e6f7a8b-0000-4000-8000-000000000000",
}


class Call:
    """One JSON call of a skill: where it is, the tool its lead-in names, and what it sends."""

    def __init__(self, where, lead_in, written):
        self.where = where
        named = TOOL.findall(lead_in)
        self.tool = named[-1] if named else None
        self.written = written

    @property
    def given(self):
        """The call as an agent sends it, with its placeholders filled in. A test reads it, so a
        call that does not parse fails its own test."""
        unknown = sorted(set(PLACEHOLDER.findall(self.written)) - set(FILLED))
        assert not unknown, f"{self.where}: add {unknown} to FILLED in this test"
        try:
            return json.loads(PLACEHOLDER.sub(lambda found: FILLED[found[0]], self.written))
        except json.JSONDecodeError as error:
            raise AssertionError(f"{self.where}: not JSON: {error}") from None


def read(skill, text):
    """A skill's fenced blocks as (first line, language, body, lead-in) tuples, and the fences this
    reader would misread. A block's lead-in is the text between the block before and this block. The
    last tuple has no block: its lead-in is the text after the last block."""
    blocks, unread, lead_in, body, opened = [], [], [], [], None
    for number, line in enumerate(text.splitlines(), 1):
        fence = FENCE.match(line)
        if opened is None and fence:
            opened = (number, fence[2])
            tag = fence[2].strip().lower()
            if fence[1] != "```" or (tag.startswith("json") and fence[2] != "json"):
                unread.append(f"{skill}:{number}: {line.strip()!r}")
        elif opened and fence and not fence[2].strip():
            blocks.append((*opened, "\n".join(body), "\n".join(lead_in)))
            lead_in, body, opened = [], [], None
        else:
            (lead_in if opened is None else body).append(line)
    if opened:
        unread.append(f"{skill}:{opened[0]}: never closed")
    return [*blocks, (number + 1, None, "", "\n".join(lead_in))], unread


def calls():
    """Every JSON call in every skill, in a block or in a line, and every fence that this reader
    cannot read."""
    found, unread = [], []
    for skill_md in (folder / "SKILL.md" for folder in SKILLS.values()):
        skill = skill_md.parent.name
        for path in [skill_md, *named(skill_md)]:
            at = skill if path == skill_md else f"{skill}:{path.name}"
            blocks, odd = read(at, path.read_text())
            unread += odd
            for number, language, body, lead_in in blocks:
                for inline in INLINE.finditer(lead_in):
                    line = number - 1 - lead_in.count("\n", inline.start())
                    found.append(Call(f"{at}:{line}", lead_in[: inline.start()], inline[1]))
                if language == "json":
                    found.append(Call(f"{at}:{number}", lead_in, body))
    return found, unread


CALLS, UNREAD = calls()
LAUNCHES = [call for call in CALLS if call.tool == "t3_thread_launch"]
TWINS = [call for call in LAUNCHES if "<model selection>" in call.written]


def where(call):
    return call.where


def strict(schema):
    """A tool's schema, changed to refuse unknown keys at every depth. The tool itself accepts
    such keys."""
    schema = copy.deepcopy(schema)
    todo = [schema]
    while todo:
        node = todo.pop()
        if isinstance(node, dict):
            if node.get("additionalProperties") is True:
                node["additionalProperties"] = False
            todo.extend(node.values())
        elif isinstance(node, list):
            todo.extend(node)
    return schema


def errors(call, given):
    """The messages of the errors that a validator finds when it checks `given` against the `strict`
    form of the call's tool schema. An empty list means the tool accepts `given`."""
    schema = strict(SCHEMAS[call.tool])
    Draft202012Validator.check_schema(schema)
    return [error.message for error in Draft202012Validator(schema).iter_errors(given)]


def misspelt(given):
    """`given` once for each of its keys, at any depth, with that one key misspelt."""
    for key, value in given.items():
        rest = {other: kept for other, kept in given.items() if other != key}
        yield key, {**rest, f"{key}x": value}
        if isinstance(value, dict):
            for inner, changed in misspelt(value):
                yield f"{key}.{inner}", {**given, key: changed}


def test_the_skills_have_calls_to_check():
    assert len(CALLS) >= 21
    assert len(LAUNCHES) >= 8
    assert len(LAUNCHES) == 2 * len(TWINS)
    of_a_crewmate = [call.tool for call in CALLS if call.where.startswith("crew:")]
    assert of_a_crewmate == ["t3_thread_organize", "link_pull_request"]
    assert [call.given for call in CALLS if call.where.startswith("scout:")] == [
        {"action": "settle"}
    ]
    settles = [call.given for call in CALLS if call.where.startswith("home:")]
    assert {"action": "settle", "threadId": FILLED["<thread>"]} in settles
    of_a_home = [call for call in CALLS if call.where.startswith("home:")]
    assert of_a_home and [errors(call, call.given) for call in of_a_home] == [[]] * len(of_a_home)
    on_a_worktree_that_is_there = [
        call.given["workspaceStrategy"]
        for call in LAUNCHES
        if call.where.startswith("home:")
        and call.given["workspaceStrategy"]["type"] == "existing_worktree"
    ]
    assert on_a_worktree_that_is_there == 2 * [
        {
            "type": "existing_worktree",
            "worktreePath": FILLED["<that worktree>"],
            "branch": FILLED["<slug>"],
        }
    ]
    launch, twin = (
        call.given
        for call in LAUNCHES
        if call.where[:5] == "home:"
        and call.given["workspaceStrategy"]["type"] == "existing_worktree"
    )
    assert twin == {**launch, "modelSelection": json.loads(FILLED["<model selection>"])}


def test_no_skill_names_a_tool_the_way_only_claude_code_does():
    only_claude = [
        f"{path.relative_to(folder.parent)}:{number}"
        for folder in SKILLS.values()
        for path in sorted(folder.rglob("*.md"))
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if "mcp__t3-code__" in line
        or ("ToolSearch" in line and not re.search(r"\bif\b", line, re.I))
    ]
    assert only_claude == []


def test_no_fence_in_a_skill_is_one_the_finder_would_skip():
    assert UNREAD == []


@pytest.mark.parametrize("call", CALLS, ids=where)
def test_a_json_block_is_for_a_tool_whose_schema_is_a_fixture(call):
    assert call.tool in SCHEMAS, (
        f"{call.where}: no schema for {call.tool!r} in features/jbus/tests/fixtures/t3 or claude. "
        "Name the tool in the text before the block, or add its schema as the README there says."
    )


@pytest.mark.parametrize("call", CALLS, ids=where)
def test_a_json_block_is_a_call_its_tool_takes(call):
    assert errors(call, call.given) == [], f"{call.where}, sent to {call.tool}"


@pytest.mark.parametrize("call", CALLS, ids=where)
def test_a_misspelt_key_in_a_json_block_is_refused(call):
    passed = [key for key, changed in misspelt(call.given) if not errors(call, changed)]
    assert passed == [], f"{call.where}: {call.tool} would take these keys misspelt"


@pytest.mark.parametrize("call", LAUNCHES, ids=where)
def test_a_launch_starts_its_thread_with_a_skill_that_exists(call):
    typed = re.fullmatch(r"/([\w-]+)( .+)?", call.given["message"])
    assert typed, f"{call.where}: the message is not a skill and its arguments"
    assert typed[1] in listed("skill"), f"{call.where}: no skill {typed[1]!r}"


@pytest.mark.parametrize("call", TWINS, ids=where)
def test_a_model_selection_with_no_model_or_a_misspelt_key_is_refused(call):
    selection = call.given["modelSelection"]
    assert selection == json.loads(FILLED["<model selection>"])
    no_model = {key: value for key, value in selection.items() if key != "model"}
    assert errors(call, {**call.given, "modelSelection": no_model}) == [
        "{'provider': 'codex'} is not valid under any of the given schemas"
    ]
    for key in ("provider", "model", "instanceId"):
        changed = {**selection, "instanceId": "codex", f"{key}x": "codex"}
        assert errors(call, {**call.given, "modelSelection": changed}) != [], key
    assert (
        errors(call, {**call.given, "modelSelection": {**selection, "instanceId": "codex"}}) == []
    )
