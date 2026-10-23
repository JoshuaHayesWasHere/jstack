"""In progress by home, in the browser: a project with child homes draws its rows under one
heading per home, the root first, each heading with the home's open count and its waits on the
user. A task that waits on the user is in Needs you and not under its home. A row whose brief
names a retired scope is under the root and says so. A project with the root alone draws one
list and no heading.
"""

import pytest

from view.page.browser import BROWSES, LAUNCH, PATIENCE, look
from view.scene import OLD, RACK, SHELF, homed

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


GROUPS = """window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () { setTimeout(function () {
  var all = function (sel, el) {
    return [].slice.call((el || document).querySelectorAll(sel));
  };
  var text = function (el) { return el.textContent; };
  var row = function (l) {
    return { key: l.getAttribute("data-key"), chips: all(".chip", l).map(text) };
  };
  var group = function (s) {
    var h = s.querySelector(".pgh");
    return { home: s.getAttribute("data-key"), head: h.hidden ? null : h.textContent,
      rows: all("li", s).map(row) };
  };
  var out = { errors: window.__errs, rows: all("#prog li").length };
  out.groups = all("#prog .pgg").map(group);
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify(out);
  (window.top === window ? document : window.top.document).body.appendChild(pre);
}, window.__at); });
"""


def test_a_project_page_draws_its_rows_under_each_home_the_root_first(scene, tmp_path):
    homed(scene)
    seen = look(scene, tmp_path, script=GROUPS)
    assert seen["errors"] == []
    heads = [(one["home"], one["head"]) for one in seen["groups"]]
    assert heads == [
        ("", "root 5 open 1 waits on you"),
        (SHELF, f"{SHELF} 2 open 1 waits on you"),
        (RACK, f"{RACK} 2 open 2 wait on you"),
    ]
    rows = {one["home"]: {row["key"] for row in one["rows"]} for one in seen["groups"]}
    assert {"tea-cups", "tea-tray", "oat-bowl", "oat-spoon"} <= rows[""]
    assert rows[SHELF] == {"jam-jar"}
    assert rows[RACK] == {"oat-milk", "thread:scout:look"}
    chips = {row["key"]: row["chips"] for one in seen["groups"] for row in one["rows"]}
    retired = f"home {OLD} retired, so under the root"
    assert [key for key, said in chips.items() if retired in said] == ["tea-tray"]


def test_a_project_with_the_root_alone_draws_one_list_and_no_heading(scene, tmp_path):
    seen = look(scene, tmp_path, script=GROUPS)
    assert seen["errors"] == []
    (one,) = seen["groups"]
    assert (one["home"], one["head"]) == ("", None)
    assert len(one["rows"]) == seen["rows"] == 6
