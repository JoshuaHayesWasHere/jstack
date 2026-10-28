"""What slows us, on the desk overview of every project, at a desk's size and a phone's: the
In check tile, with its rows split by their checks and the stacked ones counted apart, the
Slowed by card of the rail, and the machine's line of load and test slots."""

import re

import pytest

from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, PHONE, clean, look
from view.scene import in_check, slots, stacked_pr

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


def said(seen):
    """The words on the screen, lowercased, since a tag is drawn in capitals."""
    return re.sub(r" ([,.])", r"\1", " ".join(seen["screen"])).lower()


@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["desk", "phone"])
def test_six_rows_in_check_and_every_slot_held_say_so_on_the_overview(
    scene, tmp_path, monkeypatch, screen
):
    in_check(scene)
    slots(scene, monkeypatch, held=4)
    seen = look(scene, tmp_path, route="#/", screen=screen)
    clean(seen, screen)
    words = said(seen)
    assert "in check 6 6 running or queued" in words
    assert "slowed by" in words
    if screen == PHONE:
        return
    assert "test slots: 4 of 4 held" in words
    assert "load: 2.5 of " in words


def test_red_checks_that_outnumber_the_rest_are_what_slows_us(scene, tmp_path):
    """Four of the six are red: the tile names the failing checks first, in the alarm colour,
    and the Slowed by card leads with them."""
    in_check(scene, ["failed", "failed", "failed", "failed", "pending", "passed"])
    seen = look(scene, tmp_path, route="#/", screen=DESK)
    clean(seen, DESK)
    words = said(seen)
    assert "in check 6 4 failing · 1 running or queued · 1 passed" in words
    assert re.search(r"slowed by \S", words)


def test_stacked_rows_are_counted_apart_on_the_check_card(scene, tmp_path):
    """Two of the three merge after `bun-base`: the tile counts them stacked, not by their
    checks."""
    stacked_pr(scene)
    seen = look(scene, tmp_path, route="#/", screen=DESK)
    clean(seen, DESK)
    assert "in check 1 + 2 stacked 1 passed" in said(seen)
