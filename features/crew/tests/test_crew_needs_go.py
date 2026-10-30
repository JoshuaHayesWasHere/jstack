"""A crewmate's start asks `jbus queue verify` whether the user's go holds for the brief on disk,
and stops with a Result on none, so a crew launched by hand does no work.

The test runs the skill's block as an agent does, with the real `jbus` and a `uv` stand-in that
drops `run --project`, against the queue of `test_jbus_kitchen`."""

import os
import subprocess

import test_room as room
from crew_helpers import block
from test_jbus_queue import go

BRIEF = """\
# alpha: a task
Task: "do it"
Done when:
- the thing is done
Proves it: a test
Size: S
Where: `a.py`
Do not touch: none
Decisions: none
Design: none, one line
Pull request: open one when done
Review: none
Playbook: none
Home: root
"""


def start(kitchen, **env):
    """What the block prints, and the brief on disk after it ran."""
    room.uv(kitchen.stub)
    ran = subprocess.run(
        ["sh", "-c", block("Start", "jbus queue verify").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        env={**os.environ, "H": str(kitchen.home), "T": str(kitchen.root / "templates"), **env},
        cwd=kitchen.checkout,
        check=True,
    )
    return ran.stdout.splitlines(), (kitchen.home / "tasks" / "alpha.md").read_text()


def queued(kitchen, approve):
    (kitchen.home / "tasks" / "alpha.md").write_text(BRIEF)
    assert kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=BRIEF)[0] == 0
    if approve:
        assert go(kitchen, "alpha")[0] == 0


def test_a_brief_whose_go_holds_goes_on(kitchen):
    queued(kitchen, approve=True)
    (line,), brief = start(kitchen)
    assert line.startswith("go: ")
    assert brief == BRIEF


def test_a_brief_whose_go_holds_through_its_thread_line_goes_on(kitchen):
    queued(kitchen, approve=True)
    on_disk = BRIEF.replace("Task:", "Thread: mcp:a-crew\nTask:")
    (kitchen.home / "tasks" / "alpha.md").write_text(on_disk)
    (line,), _ = start(kitchen)
    assert line.startswith("go: ")


def test_a_row_with_no_go_stops_and_writes_the_result(kitchen):
    queued(kitchen, approve=False)
    (line,), brief = start(kitchen)
    assert line == "stop: no go: jbus holds no go for alpha"
    result = brief.removeprefix(BRIEF)
    assert result.startswith("\n## Result\nStatus: not done\n")
    assert "- the go: no go: jbus holds no go for alpha\n" in result
    assert "Pull request: none\n" in result and result.endswith("Left: none\n")


def test_a_brief_edited_past_its_go_stops(kitchen):
    queued(kitchen, approve=True)
    edited = BRIEF.replace("the thing is done", "the thing and another are done")
    (kitchen.home / "tasks" / "alpha.md").write_text(edited)
    (line,), brief = start(kitchen)
    path = kitchen.home / "tasks" / "alpha.md"
    assert line.startswith(f"stop: the go does not hold for {path}: ")
    assert brief.startswith(edited + "\n## Result\nStatus: not done\n")


def test_a_brief_with_no_row_stops(kitchen):
    (kitchen.home / "tasks" / "alpha.md").write_text(BRIEF)
    (line,), brief = start(kitchen)
    assert line == "stop: refused: the queue has no row alpha"
    assert "Status: not done" in brief


def test_with_no_jbus_on_the_machine_the_block_says_so_and_goes_on(kitchen, tmp_path):
    (kitchen.home / "tasks" / "alpha.md").write_text(BRIEF)
    (line,), brief = start(kitchen, JBUS_CONFIG_DIR=str(tmp_path / "nowhere"))
    assert line == f"no jbus: refused: no config at {tmp_path / 'nowhere' / 'config.toml'}"
    assert brief == BRIEF
