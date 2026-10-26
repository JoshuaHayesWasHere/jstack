"""These tests cover two lints of `jbriefs.parse.faults`, which `jbus queue add` runs. A brief
whose `Review:` is not the default `twice` gives the user's words for it, and a brief never asks
for a load that takes every core."""

import pytest

from jbriefs import parse


def brief(review="Review: twice\n", more=""):
    """Return a brief with every field that `queue add` asks for, and `more` under them."""
    return (
        '# alpha: a task\nTask: "do alpha"\nDone when:\n- it is done\n'
        "Proves it: `make check`\nSize: S\nWhere: `src/alpha/`\n"
        "Design: none, a test\nPull request: open one when done\n"
        f"{review}Playbook: feature\n{more}"
    )


def test_a_clean_brief_has_no_fault():
    assert parse.faults(brief()) == []


@pytest.mark.parametrize("review", ["Review: twice\n", "Review: none\n"])
def test_twice_and_none_need_no_word(review):
    assert parse.faults(brief(review)) == []


@pytest.mark.parametrize("mode", ["review", "after"])
@pytest.mark.parametrize(
    "decisions",
    ["", "Decisions: none\n", "Decisions: None.\n", "Decisions: <any the user made>\n"],
)
def test_review_or_after_with_no_word_is_refused(mode, decisions):
    (fault,) = parse.faults(brief(f"Review: {mode}\n", decisions))
    assert fault.startswith(f"brief's Review: line says {mode} with no Decisions: line")
    assert "Review: twice" in fault


@pytest.mark.parametrize("mode", ["review", "after"])
@pytest.mark.parametrize(
    "decisions",
    [
        'Decisions: Josh, 2026-10-26: "review it once, fix every finding"\n',
        'Decisions:\n- 2026-10-21: "speed first"\n',
        "Decisions: none, jbus filed this from a red main and the user has not seen it\n",
    ],
)
def test_review_or_after_with_the_word_passes(mode, decisions):
    assert parse.faults(brief(f"Review: {mode}\n", decisions)) == []


@pytest.mark.parametrize(
    ("line", "asked"),
    [
        ("Load: `stress-ng --cpu 0 --timeout 60s`\n", "stress-ng --cpu 0"),
        ("Load: stress-ng --cpu $(nproc) for a minute\n", "--cpu $(nproc)"),
        ("Load: run `stress-ng --cpu=`nproc`` beside the test\n", "--cpu=`nproc`"),
        ("Done when:\n- the test passes with every core busy\n", "every core"),
        ("Proves it: the timing holds with all the cores loaded\n", "all the cores"),
    ],
)
def test_a_load_that_takes_every_core_is_refused(line, asked):
    (fault,) = parse.faults(brief(more=line))
    assert fault.startswith(f"brief asks for {asked}, a load that takes every core")
    assert "`jgauge test-slot`" in fault


@pytest.mark.parametrize(
    "line",
    [
        "Load: two cores with `taskset -c 0,1 stress-ng --cpu 2`, inside `jgauge test-slot`\n",
        "Load: bounded, never `stress-ng --cpu 0`\n",
        "Load: a few cores instead of every core\n",
        "## Result\nProof: stress-ng --cpu 0 was not run\n",
    ],
)
def test_a_bounded_load_or_one_turned_down_passes(line):
    assert parse.faults(brief(more=line)) == []
