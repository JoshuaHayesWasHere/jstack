"""In progress by home, in the browser: a project with child homes draws its rows under one
heading per home, the root first, each heading with the home's open count and its waits on the
user. A task that waits on the user is in Needs you and not under its home. A row whose brief
names a retired scope is under the root and says so. A project with the root alone draws one
list and no heading.
"""

import re

import pytest

from view.page.browser import BROWSES, DESK, LAUNCH, PATIENCE, clean, look
from view.scene import IN_CHECK, OLD, RACK, SHELF, asks, homed, in_check, stacked_pr

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
    assert rows[SHELF] == {"jam-jar", f"thread:home:demo {SHELF}"}
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


def test_each_home_on_the_homes_map_says_what_the_checks_of_its_rows_in_check_did(scene, tmp_path):
    """pie-1 to pie-3 are pantry-shelf's: two red and one that passed. The root has the rest:
    one red, one running, and one with no check reported yet. A question waits on the user, so
    the homes map draws the project's card, with a line for each home."""
    asks(scene)
    in_check(scene, ["failed", "failed", "passed", "failed", "pending", "none"])
    (scene.home / SHELF).mkdir()
    (scene.home / SHELF / "home-id").write_text("mcp:shelf\n")
    (scene.home / "tasks").mkdir(exist_ok=True)
    for slug, _, _ in IN_CHECK[:3]:
        brief = f"# {slug}: a made-up task\nHome: {SHELF}\nTask: x\n"
        (scene.home / "tasks" / f"{slug}.md").write_text(brief)
    seen = look(scene, tmp_path, route="#/homes", screen=DESK)
    clean(seen, DESK)
    said = re.sub(r" ([,.])", r"\1", " ".join(seen["screen"]))
    root = said.index("check: 1 failing, 2 running or queued, 0 passed")
    shelf = said.index("check: 2 failing, 0 running or queued, 1 passed")
    assert said.index(SHELF) < shelf and root < shelf, said


def test_a_home_whose_rows_in_check_are_stacked_counts_them_on_the_homes_map(scene, tmp_path):
    """Two of the root's three rows in check merge after `bun-base`, and one passed: the line
    counts the two as stacked, not as passed."""
    asks(scene)
    stacked_pr(scene)
    seen = look(scene, tmp_path, route="#/homes", screen=DESK)
    clean(seen, DESK)
    said = re.sub(r" ([,.])", r"\1", " ".join(seen["screen"]))
    assert "check: 0 failing, 0 running or queued, 1 passed, 2 stacked" in said, said


SWATCHES = """window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () { setTimeout(function () {
  var all = function (sel) { return [].slice.call(document.querySelectorAll(sel)); };
  var out = { errors: window.__errs, swatches: all(WHERE + " .hsw").map(function (s) {
    var name = s.nextSibling;
    return { colour: s.className.replace("hsw c", ""), bg: getComputedStyle(s).backgroundColor,
      name: name && name.textContent.trim() };
  }) };
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify(out);
  (window.top === window ? document : window.top.document).body.appendChild(pre);
}, window.__at); });
"""


@pytest.mark.parametrize(
    "route, where, names",
    [
        ("#/homes", ".hm", ["demo", f"demo › {SHELF}", f"demo › {RACK}"]),
        ("#/demo/board", ".bd-h", ["root", SHELF, RACK]),
        ("#/homes", "tr[data-home]", ["root", SHELF, RACK]),
    ],
    ids=["homes-page", "homes-drawer", "matrix"],
)
def test_each_home_is_drawn_with_its_colour_beside_its_name(scene, tmp_path, route, where, names):
    """The Homes page, the Homes drawer and the matrix each draw a home's swatch in its own
    categorical colour, the root's 1 and the child homes' 2 and 3, and its name right after it,
    so no home is told by its colour alone."""
    homed(scene)
    asks(scene)
    script = SWATCHES.replace("WHERE", repr(where))
    seen = look(scene, tmp_path, route=route, screen=DESK, script=script)
    assert seen["errors"] == []
    got = [(one["colour"], one["name"]) for one in seen["swatches"]]
    assert got == list(zip(["1", "2", "3"], names, strict=True)), got
    assert len({one["bg"] for one in seen["swatches"]}) == 3
    assert "rgba(0, 0, 0, 0)" not in {one["bg"] for one in seen["swatches"]}
