"""A panel is one folder of two files, and the rest is built from the folders."""

import http.client
import json
import re
import subprocess
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from jbus import view
from jbus.view import panels
from jbus.view import state as built
from view.scene import LINKED, LINKS, REPO, SAMPLE, folder

PANELS = ["blind", "bus", "checks", "flow", "merged", "pulse", "room", "rounds", "steps", "task"]


PANELS.append("threads")


PANELS.append("you")


POLICY = (
    "default-src 'none'; font-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


BEFORE = "edd7c43d"


WIDENED = " font-src 'self';"


def differs(copy, real=REPO / "features" / "jbus" / "src"):
    """Each file of the copy that the checkout does not have as it is, from the copy's top."""
    found = []
    for path in sorted(copy.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        there = real / path.relative_to(copy)
        if not there.is_file() or there.read_bytes() != path.read_bytes():
            found.append(str(path.relative_to(copy)))
    return found


def test_a_panel_is_one_folder_of_two_files_and_the_rest_is_built_from_the_folders(served):
    folders = sorted(
        one.name for one in panels.HERE.iterdir() if one.is_dir() and one.name != "__pycache__"
    )
    assert set(PANELS) <= set(folders)
    for name in folders:
        files = sorted(one.name for one in (panels.HERE / name).iterdir())
        assert [one for one in files if one != "__pycache__"] == ["panel.js", "panel.py"], name
    found = panels.found()
    assert [panel.name for panel in found] == folders
    state = served.json("/state.json?project=demo")
    shaped = {key for panel in found if panel.first for key in panel.shape}
    assert set(state) == set(built.keys()) == {*built.FRAME, *shaped}
    first = [one for one in found if one.first]
    assert len(built.keys()) == len(built.FRAME) + sum(len(one.shape) for one in first)
    assert view.routes() == (*view.FIXED, *(f"/panel/{name}.json" for name in folders))
    named = {source.name for panel in found for source in panel.sources}
    assert {one["name"] for one in state["sources"]} == named
    assert {one["by"] for one in state["sources"]} == {"jbus", "server", "session"}
    frame = (panels.HERE.parent / "page.html").read_text()
    assert frame.count(view.MARK) == 1
    assert [name for name in folders if f'kind === "{name}"' in frame] == []
    _, _, page = served.ask("/")
    assert view.MARK not in page
    for panel in found:
        assert panel.script.read_text() in page, panel.name
        assert f'(panels("{panel.name}", {json.dumps(panel.first)}));' in page


def test_a_key_that_two_panels_give_is_refused():
    def panel(name, first, *keys):
        data = types.SimpleNamespace(FIRST=first, SHAPE=dict.fromkeys(keys))
        return panels.Panel(name, data, Path("panel.js"))

    with pytest.raises(ValueError, match="the panel one and the panel two both give the key a"):
        built.keys((panel("one", True, "a"), panel("two", True, "b", "a")))
    with pytest.raises(ValueError, match="the frame and the panel one both give the key repo"):
        built.keys((panel("one", True, "repo"),))
    asked = built.keys((panel("one", True, "a"), panel("two", False, "a", "repo")))
    assert asked == (*built.FRAME, "a")


def test_each_panel_answers_at_an_address_of_its_own_with_what_it_gives_the_state(served):
    state = served.json("/state.json?project=demo")
    for panel in panels.found():
        said = served.json(f"/panel/{panel.name}.json?project=demo")
        assert sorted(said) == ["at", "data", "panel", "sources"]
        assert (said["panel"], said["at"]) == (panel.name, state["at"])
        assert set(said["data"]) == set(panel.shape)
        live = {"room"} if panel.name == "room" else set()
        for key in set(panel.shape) - live:
            if panel.first:
                assert said["data"][key] == state[key], key
            else:
                assert key not in state, key
        names = {source.name for source in panel.sources}
        assert said["sources"] == [one for one in state["sources"] if one["name"] in names]
    for path in (
        "/panel/nothing.json?project=demo",
        "/panel/pulse",
        "/panel/pulse.json/x",
        "/panel/Pulse.json",
    ):
        assert served.ask(path)[0] == 404, path
    assert served.ask("/panel/pulse.json?project=nobody")[0] == 404
    assert served.json("/panel/pulse.json?project=demo")["panel"] == "pulse"


def test_the_policy_of_the_page_is_the_string_it_was_at_the_commit_before(served):
    """The page has every panel's script inline, so the policy allows no script from a server.
    `POLICY` here is the string of the commit `BEFORE`, copied, with the one widening since,
    `WIDENED`: the page's font from its own server. That copy is the test. A checkout with no
    history, as a runner's, has no more. Where git has the commit, the copy is held to the
    file as it was there, with the widening taken out."""
    assert view.POLICY == POLICY
    assert served.ask("/")[1]["Content-Security-Policy"] == POLICY
    was = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BEFORE}:features/jbus/src/jbus/view/__init__.py"],
        capture_output=True,
        text=True,
    )
    if was.returncode == 0:
        there = re.search(r"^POLICY = \(\n(.*?)\n\)$", was.stdout, re.S | re.M)
        was = "".join(line.strip().strip('"') for line in there[1].splitlines())
        assert was == POLICY.replace(WIDENED, "", 1)


def test_the_font_is_served_at_one_path_beside_its_licence(served):
    """The page's one font is the server's own file, so the phone on the tailnet needs no other
    host, and its licence, the SIL OFL 1.1, is shipped beside it."""
    link = http.client.HTTPConnection("127.0.0.1", served.port, timeout=10)
    try:
        link.request("GET", "/font.woff2", headers={"Host": f"127.0.0.1:{served.port}"})
        answer = link.getresponse()
        status, kind, body = answer.status, answer.getheader("Content-Type"), answer.read()
    finally:
        link.close()
    assert (status, kind, body[:4]) == (200, "font/woff2", b"wOF2")
    assert body == view.FONT.read_bytes()
    licence = view.FONT.with_name("OFL.txt").read_text()
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    assert "The Atkinson Hyperlegible Next Project Authors" in licence
    assert "/font.woff2" in view.FIXED


def raw(process, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{process.port}{path}", timeout=10) as said:
        return dict(said.headers), said.read().decode()


def test_a_folder_added_to_a_copy_of_the_package_is_a_panel_and_no_other_file_is_edited(
    scene, process
):
    folder(process, "sample")
    assert differs(process.src) == [
        "jbus/view/panels/sample/panel.js",
        "jbus/view/panels/sample/panel.py",
    ]
    scene.write("sample.json", {"lines": ["one", f"see {LINKS[0]}"]})
    process.start()
    said = process.ask("/panel/sample.json?project=demo")
    assert (said["panel"], said["data"]) == ("sample", {"count": 2, "lines": ["one", "see [link]"]})
    assert [(one["name"], one["by"], one["state"]) for one in said["sources"]] == [
        ("sample.json", "jbus", "ok")
    ]
    state = process.ask("/state.json?project=demo")
    assert "count" not in state and "lines" not in state
    assert state["sources"][-1]["name"] == "sample.json"
    assert [one for one in state["blind"] if "sample" in one["line"]] == []
    headers, page = raw(process, "/")
    assert headers["Content-Security-Policy"] == POLICY
    assert LINKED in page and '(panels("sample", false));' in page
    script = process.src / "jbus" / "view" / "panels" / "sample" / "panel.js"
    script.write_text(LINKED.replace('"Sample"', '"A sample, edited"'))
    assert '"A sample, edited"' in raw(process, "/")[1]
    assert process.run.poll() is None and process.code()["stale"] is False
    (scene.state / "sample.json").unlink()
    said = process.ask("/panel/sample.json?project=demo")
    assert said["data"] == {"count": 0, "lines": []}
    assert [one["state"] for one in said["sources"]] == ["missing"]
    spot = {"line": "sample.json could not be read", "open": "sample"}
    assert spot in process.ask("/state.json?project=demo")["blind"]


def test_a_folder_added_under_a_running_server_is_served_once_it_loads(scene, process):
    """The server loads its panels when it starts. A folder added later is code on disk that
    is newer: one that does not load keeps the server as it is, which says so, and one that
    loads ends it, for the start that serves it."""
    process.start()
    made = folder(process, "sample", data="raise ValueError('a panel that does not load')\n")
    process.until(lambda: process.code().get("error"))
    assert process.code()["error"].startswith("the code on disk does not start: ValueError")
    assert process.ask("/panel/sample.json?project=demo") is None
    assert process.ask("/panel/pulse.json?project=demo")["panel"] == "pulse"
    assert "sample" not in raw(process, "/")[1]
    (made / "panel.py").write_text(SAMPLE)
    assert process.run.wait(timeout=20) == view.NEWER_CODE
    process.start()
    assert process.ask("/panel/sample.json?project=demo")["panel"] == "sample"


def test_a_panel_asked_for_by_itself_looks_at_its_own_sources_and_no_other(scene, served):
    scene.script("systemctl", f"echo asked >> {scene.root}/systemctl.calls\n")
    served.json("/panel/merged.json?project=demo")
    assert not (scene.root / "systemctl.calls").exists()
    assert scene.asked() == []
    served.json("/panel/pulse.json?project=demo")
    assert (scene.root / "systemctl.calls").exists()


def test_a_folder_whose_second_file_is_written_after_the_first_is_still_served(scene, process):
    """A folder is a panel once it holds both files. A check that sees the first alone
    keeps the server as it is, and the second file ends it, for the start that serves it."""
    process.start()
    made = process.src / "jbus" / "view" / "panels" / "sample"
    made.mkdir()
    (made / "panel.py").write_text(SAMPLE)
    time.sleep(1)
    assert process.run.poll() is None
    assert process.ask("/panel/sample.json?project=demo") is None
    assert process.code()["stale"] is False
    (made / "panel.js").write_text(LINKED)
    assert process.run.wait(timeout=20) == view.NEWER_CODE
    process.start()
    assert process.ask("/panel/sample.json?project=demo")["panel"] == "sample"
    assert process.code()["stale"] is False
