"""The Throughput drawer in the browser: opened cold from its link, it draws a bar for each of
the last seven days with its count, and the total. `test_view_page_panels` holds that the first
screen opens it. While GitHub has not answered yet, the drawer and the Merged per day card say
they are asking it, and ask again until it does, with no reload."""

from datetime import timedelta

import pytest

from jbus.view import github
from view.page.browser import BROWSES, LAUNCH, PATIENCE, look, walked
from view.scene import NOW, ago, iso

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]

ROUTE = "#/demo/throughput"


def merges(scene):
    """Three merges in the last two days, and one ten days back, which no bar counts."""
    scene.merged(ago(days=10), ago(hours=26), ago(hours=2), ago(hours=1))


def test_the_drawer_opens_cold_and_draws_each_day_with_its_count_and_the_total(scene, tmp_path):
    merges(scene)
    (first,) = walked(scene, tmp_path, ROUTE, ["look"])
    assert first["open"] is True
    assert first["hash"] == ROUTE
    assert first["title"] == "Merges by day"
    assert first["notice"].lower().startswith("the last 7 days 3 merges")
    days = [(NOW - timedelta(days=back)).astimezone() for back in range(6, -1, -1)]
    for one in days:
        assert one.strftime("%m-%d") in first["said"]
    assert "today" in first["said"]


WATCH = """
/* Writes down each text the card and the drawer show, as each change is made, then prints them.
   A watch on the page, not a timer: virtual time runs a wait of the page in a few ms. */
window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () {
  var seen = { card: [], drawer: [] };
  function text(el) { return el ? el.innerText.replace(/\\s+/g, " ").trim() : ""; }
  function note(list, said) { if (said && list[list.length - 1] !== said) list.push(said); }
  function look() {
    note(seen.card, text(document.querySelector("[data-role=perday]")));
    var drawer = document.getElementById("drawer");
    if (drawer.open) note(seen.drawer, text(document.getElementById("dw")));
  }
  var watch = new MutationObserver(look);
  watch.observe(document.body, { childList: true, subtree: true, characterData: true });
  look();
  setTimeout(function () {
    watch.disconnect();
    var pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify(Object.assign(seen, { errors: window.__errs }));
    document.body.appendChild(pre);
  }, 9000);
});
"""


def waits_once(monkeypatch):
    """GitHub has not answered the first ask for the merges, and has 22 merges of today for
    every ask after it."""
    asked = []

    def merged(self, repo, since):
        asked.append(repo)
        if len(asked) == 1:
            return {"merged": [], "at": None, "error": github.WAITING}
        times = [{"number": 100 + n, "at": iso(ago(minutes=n + 1))} for n in range(22)]
        return {"merged": times, "at": iso(NOW), "error": None}

    monkeypatch.setattr(github.GitHub, "merged", merged)
    return asked


def watched(scene, tmp_path, route):
    seen = look(scene, tmp_path, route=route, script=WATCH, at=0, budget=12000)
    assert seen["errors"] == []
    return seen


def test_the_card_asks_github_again_until_it_answers_with_no_reload(scene, tmp_path, monkeypatch):
    asked = waits_once(monkeypatch)
    card = watched(scene, tmp_path, "#/")["card"]
    assert len(asked) >= 2
    assert all("Not known" not in one for one in card), card
    assert card[0].lower().startswith("merged per day asking github"), card
    assert card[-1].lower().startswith("merged per day 22 today"), card


def test_the_drawer_asks_github_again_until_it_answers_with_no_reload(scene, tmp_path, monkeypatch):
    asked = waits_once(monkeypatch)
    drawer = watched(scene, tmp_path, ROUTE)["drawer"]
    assert len(asked) >= 2
    assert all("Not known" not in one for one in drawer), drawer
    assert any("Asking GitHub" in one for one in drawer), drawer
    assert "the last 7 days 22 merges" in drawer[-1].lower(), drawer
    for back in range(6, -1, -1):
        assert (NOW - timedelta(days=back)).astimezone().strftime("%m-%d") in drawer[-1]
