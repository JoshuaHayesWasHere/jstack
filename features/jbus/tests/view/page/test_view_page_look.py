"""A shot of each route of the view, kept, so a later change to the look cannot undo it
silently.

Each route is opened over the same day, `every_kind`, at a desk's 1440 and a phone's 390, in
light and in dark, and its first screen is compared with the shot kept for it under
`fixtures/jbus-view/shots/`. The server's clock is the scene's, and the browser's zone is
UTC, so every time the page writes is the same on each run. What the page says about the
machine it runs on, the read-at time beside the title, is hidden before the shot.

Two browsers do not draw the same text to the same pixel, so the comparison counts the
pixels whose colour moved by more than `NOISE` on some channel, and fails when they are more
than `MOVED` of the shot. A token that changes a colour of text, or a space that moves a
row, moves far more than that.

`JSTACK_SHOTS=keep` writes each shot afresh in place of comparing it: a change that means to
change the look runs the tests that way and commits the new shots with it."""

import os

import pytest
from PIL import Image, ImageChops

from testing.paths import REPO
from view.page.browser import (
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    Proxy,
    address,
    browse,
)
from view.page.test_view_page_keys import every_kind
from view.scene import Served

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


SHOTS = REPO / "features" / "jbus" / "tests" / "fixtures" / "jbus-view" / "shots"


ROUTES = {
    "all": "#/",
    "triage": "#/triage",
    "project": "#/demo",
    "help": "#/help",
    "task": "#/demo/task/tea-kettle",
}


NOISE = 48


MOVED = 0.004


STILL = "<style>#readat, #mach, #scratch { visibility: hidden !important; }</style>"


def shot(scene, tmp_path, route, screen, theme):
    """The route's first screen at this size and in this theme, as the browser draws it."""
    served = Served(scene)
    proxy = Proxy(served.port, 0, script="")
    proxy.head = STILL
    url, window = address(proxy.port, screen, f"{route}&theme={theme}")
    made = tmp_path / "shot.png"
    try:
        ran = browse(
            "--hide-scrollbars",
            f"--user-data-dir={tmp_path / 'profile'}",
            f"--window-size={window[0]},{window[1]}",
            "--virtual-time-budget=6000",
            f"--screenshot={made}",
            url,
            dump=False,
        )
    finally:
        proxy.close()
        served.close()
    assert made.exists(), f"the browser made no shot: {ran.stderr[-2000:]}"
    with Image.open(made) as drawn:
        return drawn.convert("RGB").crop((0, 0, *screen))


def moved(kept, drawn):
    """The share of the pixels whose colour moved by more than `NOISE` on some channel."""
    if kept.size != drawn.size:
        return 1.0
    apart = ImageChops.difference(kept, drawn)
    worst = ImageChops.lighter(ImageChops.lighter(*apart.split()[:2]), apart.split()[2])
    many = sum(worst.point(lambda v: 255 if v > NOISE else 0).histogram()[255:])
    return many / (kept.width * kept.height)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["desk", "phone"])
@pytest.mark.parametrize("name", list(ROUTES))
def test_each_route_looks_as_its_kept_shot(scene, tmp_path, monkeypatch, name, screen, theme):
    monkeypatch.setenv("TZ", "UTC")
    every_kind(scene)
    drawn = shot(scene, tmp_path, ROUTES[name], screen, theme)
    kept = SHOTS / f"{name}-{screen[0]}-{theme}.png"
    if os.environ.get("JSTACK_SHOTS") == "keep":
        SHOTS.mkdir(parents=True, exist_ok=True)
        drawn.save(kept, optimize=True)
        return
    assert kept.exists(), f"no shot is kept for {kept.name}: run with JSTACK_SHOTS=keep"
    with Image.open(kept) as old:
        share = moved(old.convert("RGB"), drawn)
    if share > MOVED:
        drawn.save(tmp_path / kept.name)
    assert share <= MOVED, (
        f"{share:.2%} of {kept.name} moved; the new shot is {tmp_path / kept.name}. If the "
        "change means it, run with JSTACK_SHOTS=keep and commit the shots."
    )
