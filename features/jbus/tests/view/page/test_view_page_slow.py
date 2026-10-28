"""What slows us, on the desk overview of every project, at a desk's size and a phone's: the
In check tile, with its rows split by their checks and the stacked ones counted apart, the
Slowed by card of the rail, and the machine's line of load and test slots."""

import re
from pathlib import Path

import pytest

from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, PHONE, clean, look
from view.scene import in_check, slots, stacked_pr

OVERVIEW = (Path(__file__).parent / "overview.js").read_text()

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
    assert re.search(r"slowed by failing checks 4 ", words), "the largest group first, counted"


def test_a_ci_that_could_not_be_read_is_said_on_the_slowed_by_card(scene, tmp_path):
    """GitHub does not answer: the Slowed by card's CI line says CI could not be read, and
    counts no failing checks it never saw."""
    in_check(scene)
    scene.script("gh", "exit 1\n")
    seen = look(scene, tmp_path, route="#/", screen=DESK, script=OVERVIEW, at=8000, budget=12000)
    assert seen["errors"] == []
    (rail,) = [one["text"] for one in seen["parts"] if one["name"] == "slow:rail"]
    assert rail.endswith("CI: could not be read"), rail


def test_stacked_rows_are_counted_apart_on_the_check_card(scene, tmp_path):
    """Two of the three merge after `bun-base`: the tile counts them stacked, not by their
    checks."""
    stacked_pr(scene)
    seen = look(scene, tmp_path, route="#/", screen=DESK)
    clean(seen, DESK)
    assert "in check 1 + 2 stacked 1 passed" in said(seen)
