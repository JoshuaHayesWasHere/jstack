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

Two builds of a browser, or one browser on two machines with other fonts, draw the same page
further apart than that. So the shots are kept from one browser, the one the nightly browser
run on CI uses, and `browser.txt` beside them names it, as its `--version` prints it. On any
other browser the comparison is skipped (`drawn_by`).

The kept shots are main's, and a pull request keeps them: only the shots row redraws them
(`jbus.shots`). So a shot that moved, a shot that is missing, or a browser that moved fails only
a CI run on main or on a tag, the nightly and a release (`judged`). There the run's
`jbus-view-shots` artifact holds the shots to keep, and jbus files the shots row of the day from
it. Anywhere else, a pull request's run, a run by hand on a branch or a desk, the test compares
the page with main's shots and skips with what moved and where the shot it drew is: a feature
that changes the look merges with main's shots, and its look is looked at in the shots row's pull
request. What moved there is the change's, or a look that merged since the last shots row.

`JSTACK_SHOTS=keep` writes each shot afresh in place of comparing it, for a look at the shots of
a change on a desk; only the shots row's pull request commits them.
`JSTACK_SHOTS_OUT=<dir>` also writes each shot as drawn, and `browser.txt`, into that folder."""

import os
import subprocess
from functools import cache
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from jbus import shots
from testing.paths import REPO
from view.page.browser import (
    BROWSES,
    CHROMIUM,
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


DRAWN_BY = "browser.txt"


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


@cache
def browser():
    """The browser that draws the shots here, as its `--version` prints it."""
    said = subprocess.run([CHROMIUM, "--version"], capture_output=True, text=True, timeout=60)
    return said.stdout.strip()


def judged():
    """Whether a shot that moved fails here: in a CI run on main or on a tag, whose shots jbus
    files the shots row from. Anywhere else the kept shots are main's, and a change may not
    redraw them."""
    ref = os.environ.get("GITHUB_REF", "")
    return bool(os.environ.get("CI")) and (ref == "refs/heads/main" or ref.startswith("refs/tags/"))


def judge(said, skipped):
    """Fail with `said` and the line that names the shots to keep where the run is `judged`,
    and skip with `skipped` anywhere else."""
    if judged():
        pytest.fail(f"{said}: {shots.MOVED}")
    pytest.skip(skipped)


def drawn_by(drew, this):
    """Skip the comparison when the shots were drawn by a browser that is not this one, and fail
    it instead on main or a tag (`judge`): there the browser that draws them moved."""
    if drew == this:
        return
    moved_on = f"{shots.BROWSER_MOVED} {drew}, and this is {this}"
    judge(moved_on, moved_on)


def compare(kept, drawn, new):
    """Compare the shot `drawn`, an RGB image, with the one kept as `kept`, on the browser that
    drew the kept ones only (`drawn_by`). A missing or moved shot fails on main and skips anywhere
    else (`judge`), naming `new`, where the drawn shot is."""
    drawn_by((SHOTS / DRAWN_BY).read_text().strip(), browser())
    if not kept.exists():
        said = f"no shot is kept for {kept.name}; the new shot is {new}"
        judge(said, f"{said}: {MAINS}")
    with Image.open(kept) as old:
        share = moved(old.convert("RGB"), drawn)
    if share > MOVED:
        drawn.save(new)
        said = f"{share:.2%} of {kept.name} moved; the new shot is {new}"
        judge(said, f"{said}: {MAINS}")


MAINS = "a pull request keeps main's shots, and the shots row redraws them once it merged"


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
    out = [Path(os.environ["JSTACK_SHOTS_OUT"])] if os.environ.get("JSTACK_SHOTS_OUT") else []
    if os.environ.get("JSTACK_SHOTS") == "keep":
        out.append(SHOTS)
    for folder in out:
        folder.mkdir(parents=True, exist_ok=True)
        drawn.save(folder / kept.name, optimize=True)
        (folder / DRAWN_BY).write_text(browser() + "\n")
    if os.environ.get("JSTACK_SHOTS") == "keep":
        return
    compare(kept, drawn, tmp_path / kept.name)
