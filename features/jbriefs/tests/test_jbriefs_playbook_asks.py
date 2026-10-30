"""A lint of `jbriefs.parse.faults`, which `jbus queue add` runs: a brief has each line its
playbook's `Run by:` asks a brief to have. An investigation's playbook (runtime-forensics,
prototype, eval) asks for `Pull request: ask first`, so a brief that would open a pull request
for an investigation is refused before it is queued, and its findings never reach main."""

import pytest

from jbriefs import parse


def brief(playbook, more="", pull_request="Pull request: open one when done\n"):
    """Return a brief with every field that `queue add` asks for, `more` under them."""
    return (
        '# alpha: a task\nTask: "find out why alpha spins"\nDone when:\n- the cause is named\n'
        "Proves it: `make check`\nSize: S\nWhere: `src/alpha/`\n"
        f"Design: none, a read\n{pull_request}Review: twice\nPlaybook: {playbook}\n{READ}{more}"
    )


READ = "Read: `src/alpha/spin.py:12`, the loop\nInstruments: `py-spy dump --pid <pid>`\n"
"""What the home's deeper step writes on a brief for a runtime-forensics or an eval playbook,
which `parse.instrumented` asks for."""


ASK_FIRST = "Pull request: ask first\n"


@pytest.mark.parametrize("playbook", ["runtime-forensics", "prototype"])
def test_an_investigation_that_would_open_a_pull_request_is_refused(playbook):
    (fault,) = [one for one in parse.faults(brief(playbook)) if "Pull request: ask first" in one]
    assert fault.startswith(f"brief's Playbook: line names {playbook}, whose Run by: asks"), fault


def test_an_investigation_that_asks_first_has_no_fault():
    assert parse.faults(brief("runtime-forensics", pull_request=ASK_FIRST)) == []


def test_every_line_the_playbook_asks_for_is_named_once_in_one_fault():
    (fault,) = parse.faults(brief("eval"))
    for asked in ("`Candidates:`", "`Judge:`", "`Pull request: ask first`"):
        assert fault.count(asked) == 1, fault
    more = "Candidates: a, b\nJudge: the rubric\n"
    assert parse.faults(brief("eval", more, ASK_FIRST)) == []


def test_a_playbook_that_asks_for_no_line_adds_no_fault():
    assert parse.faults(brief("feature")) == []
    assert parse.faults(brief("bug-fix")) == []
