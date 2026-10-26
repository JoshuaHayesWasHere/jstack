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
    assert "Slowed by 6 rows in check, the oldest for 1h00, and every test slot is held." in said
    if screen == PHONE:
        assert "Runner" not in said
        return
    assert "Runner 6 in check oldest 1h00" in said
    assert "Test slots: 4 of 4 held" in said
    assert "Load: 2.5 of " in said
