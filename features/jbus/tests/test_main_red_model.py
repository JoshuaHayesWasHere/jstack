"""These tests run the exhaustive check of main.json's red-main contract
(`features/jbus/tests/main_red_model.py`). The check walks every order of events within its
bounds, with the real `mainmoved.tell` and `mainjson.read`.

Each test checks one property in the world where that property must hold, and fails there with
its trace. The first walks found three faults: F1, a lost send of the message `tell` no longer
sends, and F2 and F3, each a tip that no pass saw. The tests that walk every order use the world
where those faults came up. The skill that reruns this is
`features/jbus/project-skill/verify-main-red/SKILL.md`."""

import pytest

from main_red_model import Options, walk

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
