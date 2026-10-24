"""These tests run the exhaustive check of main.json's red-main contract
(`features/jbus/tests/main_red_model.py`). The check walks every order of events within its
bounds, with the real `mainmoved.tell` and `rows.red`.

Each test checks one property in the world where that property must hold, and fails there with
its trace. The first walks found three faults: F1, a lost send, and F2 and F3, each a tip that no
pass saw. The tests that walk every order, or that walk with lost sends, use the worlds where
those faults came up. The skill that reruns this is
`features/jbus/project-skill/verify-main-red/SKILL.md`."""

import json
from unittest import mock

import pytest

from main_red_model import PROPERTIES, Options, State, walk

EVERY = Options()
ONE_AT_A_TIME = Options(one_at_a_time=True)
ANSWERED = Options(lost_sends=False)
BOTH = Options(one_at_a_time=True, lost_sends=False)


def holds(options, prop):
    found = walk(options)
    if prop in found.traces:
        pytest.fail(found.report(prop), pytrace=False)


def test_the_walk_reaches_every_event_the_model_has():
    """If a check never reached a lost send, a held merge, a refused check or a rerun that
    passes, it proves nothing about them."""
    found = walk(EVERY)
    kinds = {"jmerge merges", "jmerge holds", "another merge", "no send", "rerun passes"}
    kinds |= {
        f"settles {answer}" for answer in ("green", "failed", "cancelled", "refused", "nojob")
    }
    kinds |= {f"T3 Code {answer}" for answer in ("answers", "loses the send", "refuses the send")}
    assert found.events == kinds


def test_s1_a_failed_tip_seen_by_a_pass_holds_every_merge():
    holds(ONE_AT_A_TIME, "S1")


def test_s1_a_failed_tip_holds_every_merge_whatever_lands_after_it():
    holds(EVERY, "S1")


def test_s2_a_green_tip_seen_by_a_pass_whose_send_goes_ends_the_red():
    holds(BOTH, "S2")


def test_s2_a_green_tip_ends_the_red_when_t3_code_loses_the_send():
    holds(ONE_AT_A_TIME, "S2")


def test_s2_a_green_tip_ends_the_red_whatever_lands_after_it():
    holds(ANSWERED, "S2")


def test_s2_a_green_tip_ends_the_red_in_every_order():
    holds(EVERY, "S2")


@pytest.mark.parametrize("pull", [False, True])
def test_a_trace_starts_from_its_own_red_pull_request_whatever_order_the_key_has(pull):
    """A trace's start line says whether the red pull request was open. The walk reads that from
    the state, not from where `State.key` puts it, so a key with its fields in another order
    still gives each trace its own start."""

    def reordered(self):
        return json.dumps([self.checks, self.record, self.sent, self.looked, self.pull])

    breaks = {"P": lambda state, files: state.pull != pull}
    with (
        mock.patch.object(State, "key", reordered),
        mock.patch.dict(PROPERTIES, breaks, clear=True),
    ):
        found = walk.__wrapped__(BOTH)
    one = "one" if pull else "no"
    assert found.traces["P"][0] == f"start: M0 is green, no main.json, {one} red pull request"
