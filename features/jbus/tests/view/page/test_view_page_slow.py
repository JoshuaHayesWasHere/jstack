"""The band of what slows us, on the overview of every project, at a desk's size and a
phone's. On a phone it is its first line, which opens to the rest."""

import re

import pytest

from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, PHONE, clean, look
from view.scene import in_check, slots

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["desk", "phone"])
def test_six_rows_in_check_and_every_slot_held_say_so_on_the_overview(
    scene, tmp_path, monkeypatch, screen
):
    in_check(scene)
    slots(scene, monkeypatch, held=4)
    seen = look(scene, tmp_path, route="#/", screen=screen)
    clean(seen, screen)
    said = re.sub(r" ([,.])", r"\1", " ".join(seen["screen"]))
    assert (
        "Slowed by 6 checks running or queued of 6 rows in check, the oldest for 1h00, "
        "and every test slot is held." in said
    )
    if screen == PHONE:
        assert "Check 6 in check" not in said
        return
    assert "Check 6 in check 0 failing, 6 running or queued, 0 passed oldest 1h00" in said
    assert "Test slots: 4 of 4 held" in said
    assert "Load: 2.5 of " in said


@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["desk", "phone"])
def test_a_band_the_reader_folds_or_opens_stays_so_when_the_overview_draws_again(
    scene, tmp_path, monkeypatch, screen
):
    in_check(scene)
    slots(scene, monkeypatch, held=4)
    walk = ['tap:[data-role="slow"] > summary', "hash:#/demo", "hash:#/", "look"]
    seen = look(scene, tmp_path, route="#/", screen=screen, walk=walk, at=6000, budget=12000)
    clean(seen, screen)
    said = " ".join(seen["screen"])
    assert ("Check 6 in check" in said) is (screen == PHONE)


def test_red_checks_that_outnumber_the_rest_are_what_slows_us(scene, tmp_path):
    """Four of the six are red: the band names the failing checks, not a runner."""
    in_check(scene, ["failed", "failed", "failed", "failed", "pending", "passed"])
    seen = look(scene, tmp_path, route="#/", screen=DESK)
    clean(seen, DESK)
    said = re.sub(r" ([,.])", r"\1", " ".join(seen["screen"]))
    assert "Slowed by 4 failing checks of 6 rows in check, the oldest for 1h00." in said
    assert "Check 6 in check 4 failing, 1 running or queued, 1 passed oldest 1h00" in said
