"""These tests run the exhaustive check of main.json's red-main contract
(`features/jbus/tests/main_red_model.py`). The check walks every order of events within its
bounds, with the real `mainmoved.tell` and `mainjson.read`.

Each test checks one property in the world where that property must hold, and fails there with
its trace. The first walks found three faults: F1, a lost send of the message `tell` no longer
sends, and F2 and F3, each a tip that no pass saw. The tests that walk every order use the world
where those faults came up. The skill that reruns this is
`features/jbus/project-skill/verify-main-red/SKILL.md`."""

import re
from pathlib import Path

import pytest

from main_red_model import Options, walk

SKILL = Path(__file__).parents[1] / "project-skill" / "verify-main-red" / "SKILL.md"

EVERY = Options()
ONE_AT_A_TIME = Options(one_at_a_time=True)


def holds(options, prop):
    found = walk(options)
    if prop in found.traces:
        pytest.fail(found.report(prop), pytrace=False)


def test_the_walk_reaches_every_event_the_model_has():
    """If a check never reached a refused check or a rerun that passes, it proves nothing about
    them."""
    found = walk(EVERY)
    kinds = {"merge", "pass", "rerun passes"}
    kinds |= {
        f"settles {answer}"
        for answer in ("green", "failed", "cancelled", "refused", "nojob", "batched")
    }
    assert found.events == kinds


def test_s1_a_failed_tip_seen_by_a_pass_is_read_as_red():
    holds(ONE_AT_A_TIME, "S1")


def test_s1_a_failed_tip_is_read_as_red_whatever_lands_after_it():
    holds(EVERY, "S1")


def test_s2_a_green_tip_seen_by_a_pass_ends_the_red():
    holds(ONE_AT_A_TIME, "S2")


def test_s2_a_green_tip_ends_the_red_in_every_order():
    holds(EVERY, "S2")


def test_s3_the_tests_kept_are_the_red_tip_s_own_one_at_a_time():
    holds(ONE_AT_A_TIME, "S3")


def test_s3_the_tests_kept_are_the_red_tip_s_own_in_every_order():
    holds(EVERY, "S3")


def test_s4_each_red_tip_has_one_line_in_the_ledger_one_at_a_time():
    holds(ONE_AT_A_TIME, "S4")


def test_s4_each_red_tip_has_one_line_in_the_ledger_in_every_order():
    holds(EVERY, "S4")


def test_the_skill_states_the_counts_the_walk_walks():
    """verify-main-red says different counts after a pure move mean the move changed behavior, so
    a count it states that the walk no longer walks reads a clean move as a behavior change."""
    text = SKILL.read_text()
    run_it = text.split("\n## Run it\n", 1)[1].split("\n## ", 1)[0]

    def number(pattern):
        found = re.search(pattern, run_it)
        assert found, f'{SKILL}\'s "Run it" section has no line matching {pattern!r}'
        return int(found[1].replace(",", ""))

    every = walk(EVERY).states
    one = walk(ONE_AT_A_TIME).states
    stated = {
        "the widest world": number(r"\(([\d,]+) states in the widest world\)"),
        "every order": number(r"every order walks ([\d,]+) states"),
        "one tip at a time": number(r"one tip at a time walks ([\d,]+)"),
    }
    walked = {"the widest world": max(every, one), "every order": every, "one tip at a time": one}
    assert stated == walked, f"{SKILL} states counts the walk does not walk"
