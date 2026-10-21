"""The exhaustive check of main.json's red-main contract (`tests/main_red_model.py`): every
order of events within its bounds, with the real `mainmoved.tell` and `rows.red`.

Each property is walked in the world where it must hold, and fails there with its trace.
The findings are the worlds where today's code breaks it: each is a strict xfail, so the
check stays green and its mark fails once the fix lands. `--runxfail` prints their traces.
The skill that reruns this is `.cursor/skills/verify-main-red/SKILL.md`."""

import pytest

from main_red_model import Options, walk

EVERY = Options()
ONE_AT_A_TIME = Options(one_at_a_time=True)
ANSWERED = Options(lost_sends=False)
BOTH = Options(one_at_a_time=True, lost_sends=False)


def holds(options, prop):
    found = walk(options)
    if prop in found.traces:
        pytest.fail(found.report(prop), pytrace=False)


def test_the_walk_reaches_every_event_the_model_has():
    """A check that never reached a lost send, a held merge or a refused check proves
    nothing about them."""
    found = walk(EVERY)
    kinds = {"jmerge merges", "jmerge holds", "another merge", "no send"}
    kinds |= {f"settles {answer}" for answer in ("green", "failed", "cancelled", "refused")}
    kinds |= {f"T3 Code {answer}" for answer in ("answers", "loses the send", "refuses the send")}
    assert found.events == kinds


def test_s1_a_failed_tip_seen_by_a_pass_holds_every_merge():
    holds(ONE_AT_A_TIME, "S1")


@pytest.mark.xfail(
    strict=True,
    reason="F2: a tip that fails and is followed by another before a pass looks at it is never "
    "kept as broken (src/jbus/mainmoved.py:97-99), so jmerge merges onto it",
)
def test_s1_a_failed_tip_holds_every_merge_whatever_lands_after_it():
    holds(EVERY, "S1")


def test_s2_a_green_tip_seen_by_a_pass_whose_send_goes_ends_the_red():
    holds(BOTH, "S2")


@pytest.mark.xfail(
    strict=True,
    reason="F1: a green tip whose send T3 Code loses writes only fixed "
    "(src/jbus/mainmoved.py:173), and the next pass at a pending tip keeps broken again "
    "(164-165), so main reads red after a tip passed",
)
def test_s2_a_green_tip_ends_the_red_when_t3_code_loses_the_send():
    holds(ONE_AT_A_TIME, "S2")


@pytest.mark.xfail(
    strict=True,
    reason="F3: while main is red only another merge lands (the fix, a second fix, a merge by "
    "hand or --accept), and a green tip it follows before a pass looks at it is never seen "
    "(src/jbus/mainmoved.py:87-100 read the newest tip only), so broken stays while the "
    "newest tip is pending",
)
def test_s2_a_green_tip_ends_the_red_whatever_lands_after_it():
    holds(ANSWERED, "S2")


@pytest.mark.xfail(
    strict=True,
    reason="F1 and F3: S2 over every order, lost sends and tips no pass saw at once, so an "
    "order that needs both is checked once both are fixed",
)
def test_s2_a_green_tip_ends_the_red_in_every_order():
    holds(EVERY, "S2")
