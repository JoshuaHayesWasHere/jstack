"""A home plans, assigns and starts: what finishes the work reaches it only while it merges.

A crewmate asks who merges before any line about its pull request, by the test the home
skill's "Who merges" makes. A gate is piped to `jbus gate` and not sent to the home, and
`tests/test_gates.py` has the home read it back from jbus. Every block here is lifted from
its skill and run, the gate's against the real `jbus` in a temporary state directory."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_home_thread import (
    CONTEXT,
    FILLED,
    NAME,
    OTHER,
    PROPOSED,
    SLUG,
    THREAD,
    Scene,
    a_gate_in,
    block,
    finds_this_home,
    paths,
)

SENDERS = ["crew", "scout"]
ASKED = "may the old flag stay?"
GATE = f"""\
## Gate <n>: {ASKED}
Status: open
Asked by: {SLUG}, thread mcp:the-crewmate
Default: it stays
Built on it: the test of the flag
Undo: remove the flag and its test"""


class Quiet(Scene):
    """A scene whose blocks find only the `jbus` put in its own `bin`."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        tools = Path(sys.executable).parent
        stub = f'#!/bin/sh\n[ "$1 $2" = "run --project" ] || exit 64\nshift 3\nexec "{tools}/$@"\n'
        (self.bin / "uv").write_text(stub)
        (self.bin / "uv").chmod(0o755)
        self.switch = self.home_dir / "home-thread"
        (self.home_dir / "tasks").mkdir()
        self.brief = self.home_dir / "tasks" / f"{SLUG}.md"
        self.brief.write_text(f"# {SLUG}: a title\n")
        self.file.write_text(f"{THREAD}\n")

    def jbus(self, repo=NAME):
        """The real `jbus`, with one project: the repo whose home's directory is `repo`."""
        (self.bin / "jbus").symlink_to(Path(sys.executable).parent / "jbus")
        config = self.user / ".config" / "jbus" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text(
            'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "demo"\n'
            f'state = "{repo}"\ncheckout = "{self.main}"\nprojectId = "a-project"\n'
        )
        config.chmod(0o600)

    def says(self, skill, text, checkout, thread=None):
        top = paths(skill)
        if thread is not None:
            top = f"{top}\n{finds_this_home(thread)}"
        ran = subprocess.run(
            ["sh", "-c", f"{top}\n{text}"],
            capture_output=True,
            text=True,
            env={"HOME": str(self.user), "PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"},
            cwd=checkout,
        )
        assert ran.stderr == ""
        return ran.stdout.strip()

    def gate(self, skill, text=GATE):
        sends = block(skill, "jbus gate")
        assert "'<slug>'" in sends
        return self.says(skill, a_gate_in(sends, text).replace("<slug>", SLUG), self.worktree)

    def who_merges(self, line):
        asks = block("crew", "home-thread")
        assert "<fixed or waits>" in asks and "<slug>" in asks
        asks = asks.replace("<fixed or waits>", line).replace("<slug>", SLUG)
        return self.says("crew", asks, self.worktree)

    def outbox(self):
        return json.loads((self.user / ".local/state/jbus/demo/outbox.json").read_text())


@pytest.fixture
def quiet(tmp_path):
    return Quiet(tmp_path)


SWITCHES = [(None, "jbus"), ("", "jbus"), (" \n", "jbus"), (f"{THREAD}\n", "home")]
SAID = {
    ("home", "fixed"): "send the line",
    ("home", "waits"): "send the line",
    ("jbus", "fixed"): "send nothing",
    ("jbus", "waits"): "send no line, and park it as a gate",
}


@pytest.mark.parametrize(("switch", "merges"), SWITCHES)
@pytest.mark.parametrize("line", ["fixed", "waits"])
def test_a_crewmate_asks_who_merges_by_the_test_the_home_makes(quiet, switch, merges, line):
    if switch is not None:
        quiet.switch.write_text(switch)
    crew = quiet.who_merges(line)
    assert quiet.says("home", block("home", 'echo "$merges merges"'), quiet.main) == (
        f"{merges} merges"
    )
    assert crew.startswith(f"{merges} merges: {SAID[merges, line]}")


def test_a_crewmate_that_does_not_say_which_line_is_not_told_whether_to_send_it(quiet):
    assert quiet.who_merges("<fixed or waits>").startswith("not filled in: ")


@pytest.mark.parametrize("names", ["id", "handed off", "handed off, by its id", "scope"])
def test_a_fixed_pull_request_of_a_scoped_home_is_a_gate_while_jbus_merges(quiet, names):
    """jbus merges no pull request of a scoped home, so a ready one waits for the user."""
    scope = quiet.home_dir / "speed"
    scope.mkdir()
    (scope / "plan.md").write_text("# a plan\n")
    if names.startswith("handed off"):
        (scope / "handoff.md").write_text(f"# handoff\nWas home: {OTHER}\n")
    else:
        (scope / "home-id").write_text(f"{OTHER}\n")
    quiet.brief.write_text(
        f"# {SLUG}: a title\nHome: {OTHER if names.endswith('id') else 'speed'}\n"
    )
    said = quiet.who_merges("fixed")
    assert said.startswith("jbus merges: send no line, and park it as a gate")
    assert said.endswith("jbus merges no pull request of the scoped home speed")
    quiet.switch.write_text(f"{THREAD}\n")
    assert quiet.who_merges("fixed").startswith("home merges: send the line")


@pytest.mark.parametrize("skill", SENDERS)
def test_a_gate_is_queued_by_the_real_jbus_and_the_home_is_sent_nothing(quiet, skill):
    quiet.jbus()
    assert quiet.gate(skill) == "sent to jbus: queued: question 1\nGate: question 1"
    (sent,) = quiet.outbox()
    assert (sent["event"], sent["slug"], sent["loud"]) == ("gate", SLUG, "user")
    assert sent["line"] == f"gate {SLUG}: question 1: {ASKED}"
    assert sent["text"] == f"{GATE}\n{CONTEXT}\n{PROPOSED}"
    assert quiet.gate(skill) == "sent to jbus: already sent: question 1\nGate: question 1"


@pytest.mark.parametrize("skill", SENDERS)
def test_a_gate_jbus_cannot_take_goes_to_the_home(quiet, skill):
    assert quiet.gate(skill) == "to the home: jbus is not installed here"
    quiet.jbus(repo="another repo")
    said = quiet.gate(skill)
    assert said.startswith("to the home: jbus said: refused: no project for this repo")


@pytest.mark.parametrize("skill", SENDERS)
@pytest.mark.parametrize(
    ("text", "why"),
    [
        (FILLED, "the first line is not"),
        ("may the old flag stay?", "the first line is not"),
        ("## Gate <n>: <the question>", "the first line is not"),
        (GATE.replace("it stays", "<what the thread did>"), "the gate has no Default: line"),
        (GATE.replace("Asked by:", "Asked:"), "the gate has no Asked by: line"),
        (GATE.split("\nUndo:")[0], "the gate has no Undo: line"),
    ],
)
def test_a_gate_that_is_not_filled_in_is_not_sent(quiet, skill, text, why):
    quiet.jbus()
    assert quiet.gate(skill, text).startswith(f"not sent: {why}")
    assert not (quiet.user / ".local/state/jbus").exists()
