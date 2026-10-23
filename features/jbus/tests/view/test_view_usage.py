"""What the page of `jbus view` opens, counted on this machine: each route it shows, each
drawer it opens and the first click after it loads, as one line each, and `jbus view usage`,
which counts them."""

import json
from datetime import timedelta

import pytest

from jbus import cli
from jbus.view import usage
from view.scene import EVIL, Served, et


def lines(scene):
    path = scene.state_dir / usage.FILE
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_a_route_a_drawer_and_a_first_click_each_append_one_line(served, scene):
    for kind, name in (("route", "project"), ("drawer", "task"), ("click", "task")):
        status, said = served.write({"kind": kind, "name": name, "project": "demo"}, path="/usage")
        assert status == 200, said
    status, said = served.write({"kind": "route", "name": "stack", "project": ""}, path="/usage")
    assert status == 200, said
    at = scene.now.isoformat(timespec="seconds")
    assert lines(scene) == [
        {"at": at, "kind": "route", "name": "project", "project": "demo"},
        {"at": at, "kind": "drawer", "name": "task", "project": "demo"},
        {"at": at, "kind": "click", "name": "task", "project": "demo"},
        {"at": at, "kind": "route", "name": "stack", "project": None},
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "drawer", "name": "task:oat-milk", "project": "demo"},
        {"kind": "drawer", "name": "oat-milk", "project": "demo"},
        {"kind": "drawer", "name": "task", "project": "demo", "slug": "oat-milk"},
        {"kind": "drawer", "name": "task", "project": "demo", "thread": "mcp:oat"},
        {"kind": "drawer", "name": "task", "project": "demo", "text": "Oat milk, frothed"},
        {"kind": "route", "name": "task", "project": "demo"},
        {"kind": "click", "name": "Oat milk, frothed", "project": "demo"},
        {"kind": "scroll", "name": "task", "project": "demo"},
        {"kind": "drawer", "name": "task", "project": "mcp:oat"},
        {"kind": "drawer", "name": "task"},
        ["drawer", "task", "demo"],
        "not json",
    ],
)
def test_a_line_carries_none_of_what_the_page_shows_and_anything_else_is_refused(
    served, scene, body
):
    """The server writes a line from names it already has: the kinds, its routes, its panels
    and its projects. A name it does not have, or any field more, is refused, and nothing is
    written."""
    status, _ = served.write(body, path="/usage")
    assert status == 400
    assert lines(scene) == []


def test_a_line_holds_the_time_the_kind_the_name_and_the_project_and_nothing_more(served, scene):
    served.write({"kind": "drawer", "name": "task", "project": "demo"}, path="/usage")
    (line,) = (scene.state_dir / usage.FILE).read_text().splitlines()
    assert set(json.loads(line)) == {"at", "kind", "name", "project"}
    for never in ("127.0.0.1", str(served.port), "oat-milk", "mcp:", "slug", "thread", "ip"):
        assert never not in line, never


def test_only_the_servers_own_page_counts(served, scene):
    body = {"kind": "drawer", "name": "task", "project": "demo"}
    assert served.write(body, origin=EVIL, path="/usage")[0] == 403
    assert served.write(body, origin="", path="/usage")[0] == 403
    assert served.ask("/usage")[0] == served.ask("/answer")[0] == 404
    assert lines(scene) == []


def test_past_its_cap_the_file_drops_its_oldest_lines(served, scene, monkeypatch):
    monkeypatch.setattr(usage, "CAP", 2000)
    monkeypatch.setattr(usage, "KEEP", 1000)
    path = scene.state_dir / usage.FILE
    old = [
        {"at": f"2026-10-01T00:00:{n:02}+00:00", "kind": "route", "name": "stack"}
        for n in range(40)
    ]
    path.write_text("".join(json.dumps(one | {"project": None}) + "\n" for one in old))
    assert path.stat().st_size > 2000
    body = {"kind": "drawer", "name": "task", "project": "demo"}
    for _ in range(3):
        assert served.write(body, path="/usage")[0] == 200
        assert path.stat().st_size <= 2000
    kept = lines(scene)
    assert kept[-1]["name"] == "task"
    assert kept[0] != old[0] | {"project": None}
    assert [one for one in kept if one["kind"] == "route"] == [
        one | {"project": None} for one in old[-len(kept) + 3 :]
    ]


def test_jbus_view_usage_counts_each_route_drawer_and_click_in_its_window(
    scene, monkeypatch, capsys
):
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    long_ago, lately = scene.now - timedelta(days=30), scene.now - timedelta(hours=2)
    made = [
        (long_ago, "drawer", "gate", "demo"),
        (lately, "route", "project", "demo"),
        (lately, "route", "project", "demo"),
        (lately, "route", "stack", None),
        (lately, "drawer", "task", "demo"),
        (lately, "click", "task", "demo"),
    ]
    rows = [{"at": at.isoformat(), "kind": k, "name": n, "project": p} for at, k, n, p in made]
    text = "".join(json.dumps(one) + "\n" for one in rows) + "not a line\n"
    (scene.state_dir / usage.FILE).write_text(text)
    since = et(scene.now - timedelta(days=1))
    assert cli.main(["view", "usage", "--since", since]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("jbus view usage: 5 since ")
    assert [line.split() for line in out[1:]] == [
        ["route", "project", "2"],
        ["route", "stack", "1"],
        ["drawer", "task", "1"],
        ["click", "task", "1"],
    ]


def test_a_window_is_for_the_counts_and_not_for_the_server(scene, capsys):
    assert cli.main(["view", "--since", "2026-10-01"]) != 0
    assert "--since is for jbus view usage" in capsys.readouterr().out


def test_jbus_view_usage_over_no_file_says_nothing_was_counted(scene, monkeypatch, capsys):
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    assert cli.main(["view", "usage"]) == 0
    assert capsys.readouterr().out.startswith("jbus view usage: 0 since ")


def test_the_counts_post_to_the_servers_own_origin_and_the_policy_is_unchanged(scene):
    served = Served(scene)
    try:
        _, headers, page = served.ask("/")
    finally:
        served.close()
    assert 'ask("/usage", ' in page
    assert headers["Content-Security-Policy"] == (
        "default-src 'none'; font-src 'self'; script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    )
