"""A crew's check and proof blocks never run as a background command.

Claude Code stops a background command at 30 minutes, and both blocks can wait that long on busy
test slots: on 2026-11-12 #1718 and #1802 each lost a check that way. So the install's hooks
refuse a `Bash` call with `run_in_background` whose command is one of those blocks, or the
targeted run in a test slot that the skill says never to wait on in a background job, as the skill
gives each, and allow the same command in the foreground and any other background command.

Each test feeds what Claude Code gives a `PreToolUse` hook for `Bash` to every hook the crew
feature has `skills.json` register for that event and tool, the way the install runs them.
"""

import json
import subprocess

import pytest

from crew_helpers import block
from jinstall import layout
from testing.paths import REPO

CHECK = block("Do the task", "<check command>")
PROOF = block("Do the task", "proved.sh")
TARGETED = block("Do the task", "<the targeted tests>")
BLOCKS = pytest.mark.parametrize(
    "command", [CHECK, PROOF, TARGETED], ids=["check", "proof", "targeted run"]
)


def hooks():
    """The script of each `PreToolUse` hook on `Bash` that the crew feature registers for
    Claude Code."""
    return [
        REPO / hook["path"]
        for hook in layout.hooks(REPO)
        if hook["path"].startswith("features/crew/")
        for one in hook["events"]
        if one["harness"] == "claude-code"
        and one["event"] == "PreToolUse"
        and one.get("matcher") == "Bash"
    ]


def decided(command, background):
    """Each refusal the crew's hooks give the call, as (exit code, what it printed), or none
    where every hook allows it."""
    tool_input = {"command": command, "timeout": 600000, "description": "Run the check"}
    if background:
        tool_input["run_in_background"] = True
    payload = json.dumps(
        {
            "session_id": "a-session",
            "cwd": str(REPO),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": tool_input,
        }
    )
    refusals = []
    for script in hooks():
        done = subprocess.run(
            ["sh", str(script)], input=payload, capture_output=True, text=True, timeout=30
        )
        if done.returncode:
            refusals.append((done.returncode, done.stderr))
    return refusals


@BLOCKS
def test_a_check_or_proof_block_sent_to_the_background_is_refused_with_the_foreground_line(
    command,
):
    ((code, said),) = decided(command, background=True)
    assert code == 2
    assert said.count("\n") == 1
    assert "foreground" in said and "timeout: 600000" in said


@BLOCKS
def test_the_same_block_in_the_foreground_is_allowed(command):
    assert decided(command, background=False) == []


@pytest.mark.parametrize(
    "command",
    ["sleep 300; echo done", "uv run pytest features/crew/tests", "make lint"],
)
def test_any_other_background_command_is_allowed(command):
    assert decided(command, background=True) == []
