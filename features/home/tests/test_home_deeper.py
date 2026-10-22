"""A home writing a brief or a scout's request asks for the deeper version of research, perf,
analysis and outcome work itself. The step is a shell block in the home skill's "Handing a task to a
crewmate", and the test takes it from the skill and runs it. For those kinds the block prints its
own copy of the four questions of `/sharpen`, each with the line of the brief its answer goes on.
For a mechanical fix, a docs change or a bug fix with a known cause it prints `skip`."""

import re
import subprocess
import sys
import textwrap

import pytest

from test_home_thread import as_read
from testing.paths import skills

SKILL = skills()["home"] / "SKILL.md"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
KINDS = ("research", "perf", "analysis", "outcome")


def block():
    (found,) = [one for one in FENCED.findall(as_read(SKILL)) if "picked=" in one]
    return textwrap.dedent(found)


def run(picked):
    text = block().replace("'<the playbook picked, or for none the kind of work>'", f"'{picked}'")
    done = subprocess.run(["sh", "-c", text], capture_output=True, text=True, check=True)
    return done.stdout.splitlines()


def deeper_playbooks():
    """The playbook names the block runs the step for, as its `case` arm lists them."""
    (arm,) = [line for line in block().splitlines() if "investigation |" in line]
    names = [name.strip() for name in arm.strip().rstrip(")").split("|")]
    return [name for name in names if name not in KINDS]


def test_every_playbook_the_step_names_is_one_jbus_finds():
    names = deeper_playbooks()
    assert {"investigation", "perf-issue"} <= set(names)
    for name in names:
        opened = subprocess.run(
            [sys.executable, "-m", "jbus", "playbook", "home", "--name", name],
            capture_output=True,
            text=True,
            check=False,
        )
        assert opened.stdout and not opened.stdout.startswith("no playbook"), (name, opened)


@pytest.mark.parametrize("picked", [*KINDS, "investigation", "perf-issue", "runtime-forensics"])
def test_research_perf_analysis_and_outcome_work_gets_the_four_questions(picked):
    said = run(picked)
    assert said[0].startswith("deeper: ")
    questions = said[1:]
    assert [line[:2] for line in questions] == ["1.", "2.", "3.", "4."]
    assert "top professional" in questions[0]
    assert "rawest material" in questions[1]
    assert "methods and tools" in questions[2]
    assert "other than the agent" in questions[3]


def test_the_answers_go_to_read_to_the_crew_and_to_proves_it():
    _, first, second, third, fourth = run("perf-issue")
    assert "no line" in first
    assert "Read:" in second and "where to start looking" in second
    assert "Instruments:" in third and "for the crew" in third
    assert fourth.endswith("A brief's Proves it: line")


@pytest.mark.parametrize("picked", ["other", "refactoring", "none"])
def test_a_mechanical_fix_a_docs_change_and_a_known_bug_skip_it(picked):
    (said,) = run(picked)
    assert said.startswith(f"skip: {picked} ")
    assert "mechanical fix" in said and "docs change" in said and "known cause" in said


@pytest.mark.parametrize(
    ("picked", "kind"),
    [("bug-fix", "analysis"), ("feature", "outcome"), ("autonomous-run", "outcome")],
)
def test_a_playbook_that_hides_the_kind_skips_and_sends_the_home_back_with_it(picked, kind):
    (said,) = run(picked)
    assert said.startswith("skip: ")
    again = said.rsplit("run this again with ", 1)[1]
    assert again == kind
    assert run(again)[0].startswith("deeper: ")


def test_the_placeholder_left_in_is_refused():
    text = block()
    done = subprocess.run(["sh", "-c", text], capture_output=True, text=True, check=True)
    assert done.stdout.startswith("not filled in: ")
