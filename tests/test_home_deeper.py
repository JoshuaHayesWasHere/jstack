"""A home writing a brief or a scout's request asks for the deeper version of research, perf,
analysis and outcome work itself. The step is a shell block in the home skill's "Handing a task
to a crewmate", lifted from it and run here: for those kinds it prints its own copy of the four
questions of `/deeper`, each with the line of the brief its answer goes on, and for a mechanical
fix, a docs change or a bug fix with a known cause it prints `skip`."""

import re
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SKILL = REPO / "skills" / "home" / "SKILL.md"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
KINDS = ("research", "perf", "analysis", "outcome")


def block():
    (found,) = [one for one in FENCED.findall(SKILL.read_text()) if "picked=" in one]
    return textwrap.dedent(found)


def run(picked):
    text = block().replace("'<the playbook picked, or for none the kind of work>'", f"'{picked}'")
    done = subprocess.run(["sh", "-c", text], capture_output=True, text=True, check=True)
    return done.stdout.splitlines()


def deeper_playbooks():
    """The playbook names the block runs the step for, read off its `case` arm."""
    (arm,) = [line for line in block().splitlines() if "investigation |" in line]
    names = [name.strip() for name in arm.strip().rstrip(")").split("|")]
    return [name for name in names if name not in KINDS]


def test_every_playbook_the_step_names_is_a_file_in_playbooks():
    names = deeper_playbooks()
    assert {"investigation", "perf-issue"} <= set(names)
    for name in names:
        assert (REPO / "playbooks" / f"{name}.md").is_file(), name


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


@pytest.mark.parametrize("picked", ["other", "refactoring", "feature", "none"])
def test_a_mechanical_fix_a_docs_change_and_a_known_bug_skip_it(picked):
    (said,) = run(picked)
    assert said.startswith(f"skip: {picked} ")
    assert "mechanical fix" in said and "docs change" in said and "known cause" in said


def test_a_bug_fix_skips_only_with_its_cause_known_and_one_unproven_goes_deeper_as_analysis():
    (said,) = run("bug-fix")
    assert said.startswith("skip: a bug fix with a known cause ")
    assert said.endswith("run this again with analysis")
    assert run("analysis")[0].startswith("deeper: ")


def test_the_placeholder_left_in_is_refused():
    text = block()
    done = subprocess.run(["sh", "-c", text], capture_output=True, text=True, check=True)
    assert done.stdout.startswith("not filled in: ")
