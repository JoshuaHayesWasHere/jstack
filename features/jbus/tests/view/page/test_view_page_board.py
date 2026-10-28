"""The board in the browser: `#/<project>/board` opens with every home as one card and every
worker's stage drawn. At a desk's size each worker is on the first screen, with no click and no
scroll. At a phone's size each card fits in one screen, so one scroll brings each home whole.
"""

import pytest

from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, PHONE, look
from view.scene import RACK, SHELF, homed

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]

STAGES = {"Briefed", "Running", "PR open", "In review", "Fixing", "Green", "Merged"}


BOARD = """window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () { setTimeout(function () {
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var card = function (c) {
    var r = c.getBoundingClientRect();
    var last = c.querySelector(".bd-hs .ct");
    return { home: c.getAttribute("aria-label"), height: r.height,
      last: last && { text: last.textContent, title: last.getAttribute("title") },
      workers: all(".bd-w", c).map(function (w) {
        var b = w.getBoundingClientRect();
        return { kind: w.getAttribute("data-kind"), stage: w.querySelector(".bd-st b").textContent,
          top: b.top, bottom: b.bottom, left: b.left, right: b.right };
      }) };
  };
  var out = { errors: window.__errs, high: window.innerHeight,
    wide: document.documentElement.clientWidth, cards: all(".bd-card").map(card) };
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify(out);
  (window.top === window ? document : window.top.document).body.appendChild(pre);
}, window.__at); });
"""


LAST = [
    {"text": "last act 40m ago", "title": "merged 9 rye-loaf"},
    {"text": "last act 30m ago", "title": "result jam-jar: Status: done"},
    {
        "text": "last act 4m ago",
        "title": "wait 13 https://github.com/acme/demo/pull/13: check has not passed",
    },
]
"""Each card's last act, the newest record of its home in the scene: rye-loaf's merge for the
root, jam-jar's Result for the shelf, and jmerge's wait on oat-milk's pull request for the
rack, with the record's line as its title."""


def seen(scene, tmp_path, screen):
    homed(scene)
    return look(scene, tmp_path, at=2500, route="#/demo/board", screen=screen, script=BOARD)


def test_at_a_desk_every_worker_of_every_home_is_on_the_first_screen(scene, tmp_path):
    said = seen(scene, tmp_path, DESK)
    assert said["errors"] == []
    assert [one["home"] for one in said["cards"]] == ["root home", f"home {SHELF}", f"home {RACK}"]
    workers = [one for card in said["cards"] for one in card["workers"]]
    assert len(workers) >= 9
    assert {one["stage"] for one in workers} <= STAGES
    assert all(0 <= one["top"] and one["bottom"] <= said["high"] for one in workers)
    assert [one["last"] for one in said["cards"]] == LAST


def test_on_a_phone_each_home_fits_in_one_screen_and_nothing_spills_sideways(scene, tmp_path):
    said = seen(scene, tmp_path, PHONE)
    assert said["errors"] == []
    assert len(said["cards"]) == 3
    assert all(card["height"] <= said["high"] for card in said["cards"])
    workers = [one for card in said["cards"] for one in card["workers"]]
    assert {one["stage"] for one in workers} <= STAGES
    assert all(0 <= one["left"] and one["right"] <= said["wide"] for one in workers)
