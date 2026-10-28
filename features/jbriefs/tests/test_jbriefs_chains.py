"""A brief builds on a row only for that row's code, which it changes, calls or imports. A plan
layer is no such need: `jbus queue add` refuses a brief whose `Builds on:` line gives a layer as
its reason (`jbriefs.parse.faults`), so siblings of one layer queue unstacked."""

import pytest

from jbriefs import chains, parse

BRIEF = """\
# beta: the second task
Task: "do the second task"
Done when:
- `make check` passes.
Proves it: `make check` prints 0 failures
Size: S
Where: `src/`
Design: none, a one-line fix
Skills: none
Pull request: open one when done
Review: twice
Playbook: none
"""


def with_builds_on(line: str) -> str:
    return BRIEF.replace("Pull request:", f"Builds on: {line}\nPull request:")


def stacking(text: str) -> list[str]:
    return [fault for fault in parse.faults(text) if "Builds on:" in fault]


@pytest.mark.parametrize(
    "line",
    [
        "launch-caps: its merged code, the base of layer 2",
        "stack-onto-main: the base of layer 4; rejudge-repeat-red: its merged code",
        "alpha: the plan layer before this one",
        "alpha: Layer 3's work",
    ],
)
def test_a_builds_on_that_names_a_plan_layer_is_refused_and_says_what_a_stack_is_for(line):
    (said,) = stacking(with_builds_on(line))
    assert "layer" in said
    assert "changes, calls or imports" in said
    assert "--merge-after" in said


@pytest.mark.parametrize(
    "line",
    [
        "alpha: `jbus.reviewed`, which its #571 adds and this calls",
        "alpha: the cache layer in `src/cache.py` that this changes",
    ],
)
def test_a_builds_on_that_names_code_is_no_fault(line):
    assert stacking(with_builds_on(line)) == []


def test_a_brief_with_no_builds_on_has_no_fault_for_it():
    assert stacking(BRIEF) == []
    assert parse.faults(BRIEF) == []


def test_a_refused_layer_item_still_names_its_row():
    text = with_builds_on("launch-caps: its merged code, the base of layer 2")
    assert chains.builds_on(text) == {"launch-caps"}
