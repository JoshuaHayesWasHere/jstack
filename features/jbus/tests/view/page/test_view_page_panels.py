"""The panels on the page: each opened from the first screen or a drawer, and a folder added."""

import json
import re
from pathlib import Path

import pytest

from jbus import queue, view
from jbus.view import panels
from jbus.view.panels.usage import panel as usage
from view.page.browser import BROWSES, LAUNCH, PATIENCE, WORDS, Proxy, clean, gated, look, shown
from view.scene import DRAWN, NOW, Process, Served, a_noticed, ago, et, iso, out, rounded, table
from view.scene import folder as panel

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


PAGE = Path(view.__file__).with_name("page.html")


FONT = 'src: url("/font.woff2") format("woff2");'


def unreached(seen, names):
    """The panels that nothing on the first screen and nothing in a drawer opens: no
    `data-open` the browser found names them."""
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
        "/answer?project=",
        "/panel/",
        "/panel/steps.json?project=",
        "/stack.json",
        "/state.json",
        "/steer",
        "/steer?project=",
        "/task/",
    ]
    assert sorted(set(re.findall(r'ask\("(/[^"]*)"', page))) == asks
    assert "fetch(path," in page and page.count("fetch(") == 1
    assert page.count("<script") == 2 and all(script in page for script in scripts)
    assert "connect-src 'self'" in headers["Content-Security-Policy"]
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert "font-src 'self'" in headers["Content-Security-Policy"]


def test_every_panel_is_opened_from_the_first_screen_or_from_a_drawer(scene, tmp_path):
    """The scene has a question jbus holds, which is what opens the drawer of a gate, and a
    work item linked to a task, whose drawer opens the item's."""
    gated(scene)
    made = {"id": "w1.1", "item": "w1", "at": iso(ago(minutes=9)), "by": "Josh", "where": "chat"}
    made |= {"line": "proposed", "verb": "proposed", "project": "demo", "slug": "jam-jar"}
    (scene.state / "items.jsonl").write_text(json.dumps(made) + "\n")
    a_noticed(scene, ("alpha", "new", 5, {}))
    scene.passed(20, threads=[out("home: demo")])
    seen = look(scene, tmp_path)
    assert unreached(seen, [one.name for one in panels.found()]) == []


def test_an_approval_by_a_pick_on_a_lavish_page_says_so_with_the_pages_file(scene, tmp_path):
    by = {"session": "s-1", "directory": "/made/up/elsewhere"}
    page = "/made/up/reports/grill-tea.html"
    made = queue.Approval(
        "page",
        "k1/e3",
        "1. Cups: as recommended",
        et(ago(minutes=20)),
        page,
        True,
        by,
        iso(ago(minutes=10)),
    )
    rows = table()
    rows[1] |= {"approved": made.line(), "approval": queue.held(made)}
    scene.queue(rows)
    served = Served(scene)
    try:
        task = shown(served.port, tmp_path, "task:tea-cups")
        words = shown(served.port, tmp_path, "words:approval:tea-cups")
    finally:
        served.close()
    assert "Approval on your pick on a Lavish page, " in task
    assert ", grill-tea.html, run " in task.partition("Approval on your pick")[2]
    assert "by page" in words
    assert "Your pick on a Lavish page, " in words
    assert "grill-tea.html. Run " in words
    assert page not in words


def test_a_folder_added_to_a_copy_of_the_package_opens_its_drawer_and_adds_its_lines(
    scene, tmp_path
):
    """The test adds two folders to a copy of the package and edits no other file of it
    (`test_view_panels.py` compares the trees). `sample` adds a line to the task drawer that
    opens it, and a count beside the Needs you queue. Nothing opens `lost`, and the drawer of
    `thrown` throws."""
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
        assert seen["needs"]["head"] == "3 Needs you"
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


def test_a_task_drawer_says_its_rounds_in_one_line_that_opens_them(scene, tmp_path):
    """A round has a time where the event log has a `review` event of its head, and says no
    time is kept where it has none. A task whose brief cannot be read says that instead."""
    _, first, fixed = rounded(scene)
    served = Served(scene)
    try:
        task = shown(served.port, tmp_path, "task:oat-milk")
        drawer = shown(served.port, tmp_path, "rounds:oat-milk")
        other = shown(served.port, tmp_path, "rounds:oat-bowl")
    finally:
        served.close()
    assert "2 reviews, 1 rebase, 3 wakes" in task
    assert drawer.startswith(
        f"All › demo › oat-milk Rounds oat-milk Updated {NOW.astimezone():%H:%M:%S} "
        "Close (Esc) Now 2 reviews, 1 rebase, 3 wakes"
    ), drawer
    at = ago(minutes=20).astimezone()
    when = f"{at:%H:%M}" if at.date() == NOW.astimezone().date() else f"{at:%m-%d %H:%M}"
    assert f"1st findings review of {first[:12]} 2 findings {when}" in drawer
    assert f"2nd clean review of {fixed[:12]} 0 findings no time kept" in drawer
    assert "second pass needed scoped review needed wakes 3 rebases 1" in drawer
    assert "0 reviews" not in other
    assert "not read it has no brief in its home or in jbus's copies." in other


def test_the_usage_line_of_a_task_says_not_known_when_its_ask_fails(scene, tmp_path, monkeypatch):
    """The task drawer fills its Usage line with a request of its own. The line says when a
    transcript is not there, and says so too when the server does not answer the request,
    rather than wait."""
    monkeypatch.setattr(usage, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(usage, "_kept", {})
    served = Served(scene)
    proxy = Proxy(served.port, 600, probe=False)
    try:
        said = shown(proxy.port, tmp_path, "task:oat-milk")
        assert "Usage: not known: no transcript under " in said
        proxy.refused = ("/panel/usage.json",)
        said = shown(proxy.port, tmp_path / "again", "task:oat-milk")
        assert "Usage: not known: the view server did not answer" in said
    finally:
        proxy.close()
        served.close()
