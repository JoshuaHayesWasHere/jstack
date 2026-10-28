"""`jbus view-shot` of the overview, `#/`, over each day of `browser.DAYS`, at a desk's 1440 and a
phone's 390: four shots kept under `fixtures/jbus-view/shots/` as `day-<day>-<width>.png`, the
pictures each later change to the overview is shown by.

The shots are the command's own, with the browser of these tests as its `chromium`, the fonts
of `browser.FONTS` and the zone UTC. The page draws the time of its last read, which the command
does not hide, so a shot is not compared pixel by pixel: the look of each route is kept by
`test_view_page_look.py`. Each run checks that the command draws each one at its width, and that
one is kept. `JSTACK_SHOTS=keep` writes them afresh, and a change that moves the overview runs
this module that way and commits the shots with it. `JSTACK_SHOTS_OUT=<dir>` also writes each
one into that folder."""

import os
import shutil
import struct
from pathlib import Path

import pytest

from jbus import cli
from view.page.browser import CHROMIUM, DAYS, FONTS, LAUNCH, PATIENCE
from view.page.test_view_page_look import SHOTS
from view.scene import Served

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + 2 * (LAUNCH + 5) + 30)]


def width(png):
    """The width in the PNG's header."""
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])[0]


@pytest.mark.parametrize("wide", [1440, 390])
@pytest.mark.parametrize("day", list(DAYS))
def test_view_shot_draws_the_overview_of_each_day_at_each_width(
    scene, tmp_path, monkeypatch, capsys, day, wide
):
    DAYS[day](scene)
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("FONTCONFIG_FILE", str(FONTS))
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    monkeypatch.setenv("XDG_STATE_HOME", str(scene.root / "xdg-state"))
    named = tmp_path / "browser"
    named.mkdir()
    (named / "chromium").symlink_to(CHROMIUM)
    monkeypatch.setenv("PATH", f"{named}{os.pathsep}{os.environ['PATH']}")
    drawn = tmp_path / "shots" / f"day-{day}-{wide}.png"
    drawn.parent.mkdir()
    served = Served(scene)
    words = ["view-shot", "#/", "--out", str(drawn), "--width", str(wide)]
    try:
        code = cli.main([*words, "--port", str(served.port)])
    finally:
        served.close()
    assert (code, capsys.readouterr().out.strip()) == (0, str(drawn))
    assert width(drawn) == wide
    out = [Path(os.environ["JSTACK_SHOTS_OUT"])] if os.environ.get("JSTACK_SHOTS_OUT") else []
    if os.environ.get("JSTACK_SHOTS") == "keep":
        out.append(SHOTS)
    for folder in out:
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(drawn, folder / drawn.name)
    kept = SHOTS / drawn.name
    assert kept.exists(), f"no shot is kept for {kept.name}: run with JSTACK_SHOTS=keep"
    assert width(kept) == wide
