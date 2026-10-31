"""The panels on the page: each opened from the first screen or a drawer, and a folder added."""

import json
import re
from pathlib import Path

import pytest

from jbus import view
from jbus.view import panels
from view.page.browser import (
    BROWSES,
    LAUNCH,
    PATIENCE,
    WORDS,
    browse,
    clean,
    gated,
    look,
    shown,
)
from view.scene import (
    DRAWN,
    Process,
    Served,
    ago,
    iso,
    item,
    out,
    row,
    table,
)
from view.scene import folder as panel
from view.test_view_owner import crewed, told

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


PAGE = Path(view.__file__).with_name("page.html")


FONT = 'src: url("/font.woff2") format("woff2");'


DRAWER = re.compile(r"\bdrawer\s*:")


def drawn(found):
    """The names of the panels that have a drawer: a panel with only a card, or only what it
    adds to another panel, has nothing to open."""
    return [one.name for one in found if DRAWER.search(one.script.read_text())]


def unreached(seen, names):
    """The panels that nothing on the first screen and nothing in a drawer opens: the
    browser found no `data-open` and no link of a Needs you row that names them."""
    opened = {one["target"].partition(":")[0] for one in seen["opened"]}
    return sorted(set(names) - opened)


def test_the_page_is_one_document_that_loads_nothing_and_asks_only_its_own_server(scene):
    """The page loads nothing but its one font, from its own server."""
    served = Served(scene)
    try:
        _, headers, page = served.ask("/")
    finally:
        served.close()
    scripts = [one.script.read_text() for one in panels.found()]
    for part in (PAGE.read_text().replace(FONT, "", 1), *scripts):
        assert "://" not in part
        for loads in ("<link", "<img", "<iframe", "<object", "<embed", " src=", "@import", "url("):
            assert loads not in part, loads
    assert FONT in page
    asks = [
        "/answer",
        "/approve",
        "/panel/",
        "/panel/milestones.json?project=",
        "/panel/pipeline.json",
        "/panel/throughput.json?project=",
        "/panel/you/approve",
        "/panel/you/hold?project=",
        "/stack.json",
        "/state.json",
        "/task/",
        "/usage",
    ]
    assert sorted(set(re.findall(r'ask\("(/[^"]*)"', page))) == asks
    assert "fetch(path," in page and page.count("fetch(") == 1
    assert page.count("<script") == 2 and all(script in page for script in scripts)
    assert "connect-src 'self'" in headers["Content-Security-Policy"]
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert "font-src 'self'" in headers["Content-Security-Policy"]


def test_every_panel_is_opened_from_the_first_screen_or_from_a_drawer(scene, tmp_path):
    """The scene has a question jbus holds, which opens the drawer of a gate. It also has a
    work item linked to a task, and the task's drawer opens the item's drawer."""
    gated(scene)
    made = {"id": "w1.1", "item": "w1", "at": iso(ago(minutes=9)), "by": "Josh", "where": "chat"}
    made |= {"line": "proposed", "verb": "proposed", "project": "demo", "slug": "jam-jar"}
    (scene.state / "items.jsonl").write_text(json.dumps(made) + "\n")
    scene.passed(20, threads=[out("home: demo")])
    seen = look(scene, tmp_path)
    assert unreached(seen, drawn(panels.found())) == []
    assert "since" not in drawn(panels.found()), "the line of `#/` has no drawer"


def test_a_folder_added_to_a_copy_of_the_package_opens_its_drawer_and_adds_its_lines(
    scene, tmp_path
):
    """The test adds two folders to a copy of the package and edits no other file of it
    (`test_view_panels.py` compares the trees). `sample` adds a count beside the Needs you
    queue, and a line to the task drawer. That line opens the `sample` drawer. Nothing opens
    `lost`, and the drawer of `thrown` throws."""
    process = Process(scene)
    panel(process, "sample")
    panel(process, "lost", DRAWN + "panel({ drawer: drawn });\n")
    panel(process, "thrown", 'panel({ drawer: function () { throw new Error("no"); } });\n')
    scene.write("sample.json", {"lines": ["a first line", "a second line"]})
    try:
        process.start()
        seen = look(scene, tmp_path, port=process.port)
        clean(seen)
        assert unreached(seen, ["sample", "lost", "thrown"]) == ["lost", "thrown"]
        assert seen["needs"]["head"] == "3 Needs you · 1 takes its default ›"
        assert (seen["needs"]["extra"][-1]["text"], seen["needs"]["extra"][-1]["open"]) == (
            "1 sample",
            "sample",
        )
        assert seen["words"] <= WORDS
        said = shown(process.port, tmp_path, "sample")
        assert said.startswith(
            "All › demo › 2 sample lines Sample 2 sample lines As the last pass"
        ), said
        assert ": jbus has stopped Close (Esc) a first line" in said, (
            "how fresh it is, once in its head"
        )
        assert "a first line a second line" in said and "could not be read" not in said
        assert "a sample line of oat-milk the sample" in shown(
            process.port, tmp_path, "task:oat-milk"
        )
        said = shown(process.port, tmp_path, "thrown")
        assert (
            said.startswith("All › demo › thrown Panel thrown Close")
            and "This panel could not be drawn." in said
        )
        (scene.state / "sample.json").unlink()
        said = shown(process.port, tmp_path, "sample")
        assert said.startswith(
            "All › demo › 0 sample lines Sample 0 sample lines As the last pass"
        ), said
        assert said.endswith("missing sample.json could not be read.")
    finally:
        process.stop()


def test_a_homes_drawer_names_its_scope_and_an_idle_home_is_a_row_in_progress(scene, tmp_path):
    """A scoped home's drawer names its scope and counts its own open tasks, and the root's
    says it is the root's. A home that ended with a task of its own open is a row of In
    progress that says it is idle."""
    (scene.home / "second").mkdir()
    (scene.home / "second" / "home-id").write_text("mcp:home: demo second\n")
    (scene.home / "tasks").mkdir(exist_ok=True)
    (scene.home / "tasks" / "jam-jar.md").write_text("# jam-jar: a jar\nHome: second\n")
    scene.passed(
        20, threads=[out("home: demo", minutes=3), out("home: demo second", "ended", "completed")]
    )
    served = Served(scene)
    try:
        second = shown(served.port, tmp_path, "thread:home:demo%20second")
        root = shown(served.port, tmp_path, "thread:home:demo")
        seen = look(scene, tmp_path, port=served.port)
    finally:
        served.close()
    assert "The home of the scope second of demo: " in second
    assert "1 open task of its own now" in second
    assert "The root home of demo: " in root
    rows = {one["slug"]: one for one in seen["prog"]}
    assert rows["demo second"]["state"] == "Idle, work open"
    assert rows["demo"]["state"] == "Working"


def test_a_fault_its_crew_owns_is_drawn_on_its_row_as_fixing_by_the_crew(scene, tmp_path):
    """oat-milk's check is red and its crew was told 20 minutes ago: the task drawer draws the
    row as fixing by its crew, with when it was told."""
    crewed(scene)
    scene.lines("outbox.jsonl", [told("oat-milk", "mcp:crew-oat-milk", "failed", 20)])
    served = Served(scene)
    try:
        task = shown(served.port, tmp_path, "task:oat-milk")
    finally:
        served.close()
    assert "Fixing: crew of oat-milk, told " in task, task


def folded(port, tmp_path, opens):
    """The rows of the drawer that `opens` names, as the slugs of the tasks they open: those
    shown, and those folded under its `details`, with what the fold's summary says."""
    ran = browse(
        f"--user-data-dir={tmp_path / 'profile'}",
        "--virtual-time-budget=3000",
        f"http://127.0.0.1:{port}/#/demo/{opens.replace(':', '/')}",
    )
    drawer = ran.stdout.partition('id="drawer"')[2].partition("</dialog>")[0]
    shown_, _, rest = drawer.partition('<details class="more">')
    summary = re.search(r"<summary>([^<]*)</summary>", rest)
    found = [re.findall(r'data-open="task:(tea-\d)"', part) for part in (shown_, rest)]
    return *found, summary and summary.group(1)


def test_a_long_list_in_a_drawer_folds_and_the_row_it_was_opened_on_stays_shown(scene, tmp_path):
    """Six rows wait for an approval. The drawer of what waits on you shows the first two and
    folds the rest under how many they are. Opened on one of the folded rows, it shows that row
    beside the first two."""
    slugs = [f"tea-{n}" for n in range(6)]
    scene.queue(table() + [row(slug, approved="", why="not approved") for slug in slugs])
    scene.waiting(
        [
            item("approve", f"approve:{one}", f"approve {one}: jbus queue approve", slug=one)
            for one in slugs
        ]
    )
    served = Served(scene)
    try:
        kind = folded(served.port, tmp_path, "you:approve")
        named = folded(served.port, tmp_path, "you:approve:tea-4")
    finally:
        served.close()
    assert kind == (slugs[:2], slugs[2:], "4 more")
    assert named == (["tea-0", "tea-1", "tea-4"], ["tea-2", "tea-3", "tea-5"], "3 more")


LISTS = """window.addEventListener("load", function () { setTimeout(function () {
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var named = function (li) {
    var task = li.querySelector('[data-open^="task:"]');
    var slug = task ? task.getAttribute("data-open").slice(5) : "row";
    return slug + (li.classList.contains("hit") ? " hit" : "");
  };
  var lists = all("#drawer h3").map(function (h) {
    var one = { head: h.textContent, shown: [], folded: [], summary: null, marker: null };
    for (var el = h.nextElementSibling; el && el.tagName !== "H3"; el = el.nextElementSibling) {
      if (el.matches("details.more")) {
        var s = el.querySelector("summary"), look = getComputedStyle(s);
        one.summary = s.textContent;
        one.marker = look.display === "list-item" && look.listStyleType !== "none";
        one.folded = all("li", el).map(named);
      } else one.shown = one.shown.concat(all("li", el).map(named));
    }
    return one;
  });
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify({ lists: lists });
  document.body.appendChild(pre);
}, window.__at); });
"""


def lists(scene, tmp_path, opens):
    """The lists of the drawer that `opens` names: for each, its heading, the rows it shows and
    those folded under its `details`, each as the slug of the task it opens (or `row`), marked
    `hit` where it is the row the drawer was opened on, with what the fold's summary says and
    whether the browser draws the summary a disclosure marker."""
    route = "#/demo/" + opens.replace(":", "/")
    seen = look(scene, tmp_path, at=2500, budget=6000, route=route, script=LISTS)
    return [
        (one["head"], one["shown"], one["folded"], one["summary"], one["marker"])
        for one in seen["lists"]
    ]
