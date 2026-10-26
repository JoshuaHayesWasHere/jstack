"""What the page of `jbus view` does, kept as events on this machine: the view opened, each
route it shows, each item it opens and each action it takes, with the seconds from page load to
the first of each item and action, and whether a headless browser loaded it, and the two commands
that read them: `jbus view usage`, which counts them, and `jbus view pace`, which gives the median
seconds to each first action, this week against last week. Both count a person's loads only."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from jbus import cli
from jbus.view import usage
from view.scene import EVIL, Served, et


def lines(scene):
    path = scene.state_dir / usage.FILE
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def event(kind, name, route="project", project="demo", seconds=None, headless=False):
    return {
        "kind": kind,
        "name": name,
        "project": project,
        "route": route,
        "seconds": seconds,
        "headless": headless,
    }


def test_the_view_opened_a_route_an_item_and_an_action_each_append_one_line(served, scene):
    for body in (
        event("open", "project"),
        event("route", "project"),
        event("item", "task", seconds=2.4),
        event("action", "answer", seconds=7),
        event("action", "approve", route="stack", project=""),
        event("route", "triage", route="triage", project=""),
        event("open", "stack", route="stack", project="", headless=True),
    ):
        status, said = served.write(body, path="/usage")
        assert status == 200, said
    at = scene.now.isoformat(timespec="seconds")
    assert lines(scene) == [
        {"at": at, **event("open", "project")},
        {"at": at, **event("route", "project")},
        {"at": at, **event("item", "task", seconds=2.4)},
        {"at": at, **event("action", "answer", seconds=7)},
        {"at": at, **event("action", "approve", route="stack", project=None)},
        {"at": at, **event("route", "triage", route="triage", project=None)},
        {"at": at, **event("open", "stack", route="stack", project=None, headless=True)},
    ]


@pytest.mark.parametrize(
    "body",
    [
        event("item", "task:oat-milk"),
        event("item", "oat-milk"),
        event("item", "task") | {"slug": "oat-milk"},
        event("item", "task") | {"thread": "mcp:oat"},
        event("item", "task") | {"text": "Oat milk, frothed"},
        event("item", "task") | {"ip": "127.0.0.1"},
        event("route", "task"),
        event("action", "Oat milk, frothed"),
        event("action", "task"),
        event("scroll", "task"),
        event("item", "task", project="mcp:oat"),
        event("item", "task", route="#/demo"),
        event("item", "task", seconds=-1),
        event("item", "task", seconds=True),
        event("item", "task", seconds="4"),
        event("item", "task", seconds=usage.LONGEST + 1),
        event("item", "task", headless=None),
        event("item", "task", headless="no"),
        {"kind": "item", "name": "task", "project": "demo", "route": "project", "seconds": None},
        {"kind": "item", "name": "task", "project": "demo"},
        ["item", "task", "demo"],
        "not json",
    ],
)
def test_a_line_carries_none_of_what_the_page_shows_and_anything_else_is_refused(
    served, scene, body
):
    """The server writes a line from names it already has: the kinds, its routes, its panels,
    its actions and its projects, and a number of seconds. A name it does not have, any field
    more or fewer, or seconds that are no number of a page's life, is refused, and nothing is
    written."""
    status, _ = served.write(body, path="/usage")
    assert status == 400
    assert lines(scene) == []


def test_every_action_the_server_takes_is_a_name_a_line_may_have(served, scene):
    """An action is a write the page sends: an answer, or a steer by its action."""
    for name in ("answer", "approve", "message", "hold", "redirect"):
        assert served.write(event("action", name), path="/usage")[0] == 200, name
    assert [one["name"] for one in lines(scene)] == [
        "answer",
        "approve",
        "message",
        "hold",
        "redirect",
    ]


def test_a_line_holds_its_fields_and_no_content_and_no_address(served, scene):
    served.write(event("item", "task", seconds=3.5), path="/usage")
    (line,) = (scene.state_dir / usage.FILE).read_text().splitlines()
    assert set(json.loads(line)) == {
        "at",
        "kind",
        "name",
        "project",
        "route",
        "seconds",
        "headless",
    }
    for never in ("127.0.0.1", str(served.port), "oat-milk", "mcp:", "slug", "thread", "ip"):
        assert never not in line, never


def test_only_the_servers_own_page_counts(served, scene):
    body = event("item", "task")
    assert served.write(body, origin=EVIL, path="/usage")[0] == 403
    assert served.write(body, origin="", path="/usage")[0] == 403
    assert served.ask("/usage")[0] == served.ask("/answer")[0] == 404
    assert lines(scene) == []


def test_a_line_is_kept_90_days_and_then_dropped(served, scene):
    path = scene.state_dir / usage.FILE
    old = scene.now - usage.KEPT - timedelta(days=2)
    young = scene.now - usage.KEPT + timedelta(days=1)
    made = [
        {"at": moment.isoformat(timespec="seconds"), **event("route", "stack", "stack", None)}
        for moment in (old, old, young)
    ]
    path.write_text("".join(json.dumps(one) + "\n" for one in made))
    assert served.write(event("item", "task"), path="/usage")[0] == 200
    kept = lines(scene)
    assert kept[0] == made[2]
    assert [one["name"] for one in kept] == ["stack", "task"]


def test_past_its_cap_the_file_drops_its_oldest_lines(served, scene, monkeypatch):
    """However young its lines, the file never grows past `CAP`: a page that posted in a loop
    costs the disk no more than that."""
    monkeypatch.setattr(usage, "CAP", 2000)
    monkeypatch.setattr(usage, "KEEP", 1000)
    path = scene.state_dir / usage.FILE
    young = (scene.now - timedelta(hours=1)).isoformat(timespec="seconds")
    old = [{"at": young, **event("route", "stack", "stack", None)} for _ in range(40)]
    path.write_text("".join(json.dumps(one) + "\n" for one in old))
    assert path.stat().st_size > 2000
    for _ in range(3):
        assert served.write(event("item", "task"), path="/usage")[0] == 200
        assert path.stat().st_size <= 2000
    kept = lines(scene)
    assert kept[-1]["name"] == "task"
    assert len(kept) < len(old)


def write_lines(scene, made):
    rows = [{"at": at.isoformat(), **one} for at, one in made]
    text = "".join(json.dumps(one) + "\n" for one in rows) + "not a line\n"
    (scene.state_dir / usage.FILE).write_text(text)


def test_jbus_view_usage_counts_each_kind_and_name_in_its_window(scene, monkeypatch, capsys):
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    long_ago, lately = scene.now - timedelta(days=30), scene.now - timedelta(hours=2)
    write_lines(
        scene,
        [
            (long_ago, event("item", "gate")),
            (lately, event("open", "project")),
            (lately, event("route", "project")),
            (lately, event("route", "project")),
            (lately, event("route", "stack", "stack", None)),
            (lately, event("item", "task", seconds=3)),
            (lately, event("action", "answer", seconds=9)),
            (lately, event("open", "stack", "stack", None, headless=True)),
            (lately, event("item", "task", seconds=1, headless=True)),
        ],
    )
    since = et(scene.now - timedelta(days=1))
    assert cli.main(["view", "usage", "--since", since]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("jbus view usage: 6 since ")
    assert out[0].endswith(", and 2 headless left out")
    assert [line.split() for line in out[1:]] == [
        ["open", "project", "1"],
        ["route", "project", "2"],
        ["route", "stack", "1"],
        ["item", "task", "1"],
        ["action", "answer", "1"],
    ]


def test_a_window_is_for_the_counts_and_not_for_the_server(scene, capsys):
    assert cli.main(["view", "--since", "2026-10-01"]) != 0
    assert "--since is for jbus view usage" in capsys.readouterr().out


def test_jbus_view_usage_skips_a_line_it_cannot_read_and_counts_the_rest(
    scene, monkeypatch, capsys
):
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    lately = (scene.now - timedelta(hours=2)).isoformat()
    bad = [
        {"at": "2026-10-12T18:00:00", "kind": "route", "name": "stack"},
        {"at": lately, "kind": ["route"], "name": "stack"},
        {"at": lately, "kind": "route", "name": {"stack": 1}},
        {"at": 1760000000, "kind": "route", "name": "stack"},
        ["route", "stack"],
    ]
    good = {"at": lately, **event("item", "task")}
    text = "".join(json.dumps(one) + "\n" for one in [*bad, good])
    (scene.state_dir / usage.FILE).write_text(text)
    since = et(scene.now - timedelta(days=1))
    assert cli.main(["view", "usage", "--since", since]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("jbus view usage: 1 since ")
    assert [line.split() for line in out[1:]] == [["item", "task", "1"]]


def test_jbus_view_usage_over_no_file_says_nothing_was_counted(scene, monkeypatch, capsys):
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    assert cli.main(["view", "usage"]) == 0
    assert capsys.readouterr().out.startswith("jbus view usage: 0 since ")


def test_jbus_view_pace_gives_the_median_to_each_first_action_this_week_against_last(
    scene, monkeypatch, capsys
):
    """Per route and action, the median seconds from page load to the first of it: this week,
    the last 7 days, against the 7 before them. A line with no seconds was not the first of its
    action in its page, and a line older than two weeks is in neither week."""
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    now = datetime.now(UTC)
    this, last, older = (now - timedelta(days=d) for d in (1, 9, 20))
    write_lines(
        scene,
        [
            (older, event("item", "task", seconds=1)),
            (last, event("item", "task", seconds=10)),
            (last, event("item", "task", seconds=20)),
            (last, event("item", "task", seconds=30)),
            (this, event("item", "task", seconds=4)),
            (this, event("item", "task", seconds=6)),
            (this, event("item", "task")),
            (this, event("action", "answer", "stack", None, seconds=12.5)),
            (last, event("action", "answer", seconds=40)),
            (this, event("route", "project")),
            (this, event("open", "project")),
            (this, event("item", "task", seconds=0.5, headless=True)),
            (this, event("action", "hold", seconds=3, headless=True)),
        ],
    )
    assert cli.main(["view", "pace"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("jbus view pace: median seconds from page load to the first ")
    assert [line.split() for line in out[1:]] == [
        ["route", "action", "this", "week", "last", "week", "change"],
        ["project", "action", "answer", "-", "40.0", "(1)", "-"],
        ["project", "item", "task", "5.0", "(2)", "20.0", "(3)", "-15.0"],
        ["stack", "action", "answer", "12.5", "(1)", "-", "-"],
    ]


def test_jbus_view_pace_over_no_file_says_there_is_nothing_to_time(scene, monkeypatch, capsys):
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    assert cli.main(["view", "pace"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("jbus view pace: ")
    assert out[1:] == ["no first action in the last two weeks"]


def test_the_page_has_one_listener_that_posts_to_its_own_origin_and_the_policy_holds(scene):
    """One listener reads what was tapped from its data attribute, and one hook reads each
    write the page sends: nothing else on the page posts an event."""
    served = Served(scene)
    try:
        _, headers, page = served.ask("/")
    finally:
        served.close()
    assert page.count('ask("/usage", ') == 1
    assert page.count('closest("[data-open]")') >= 1
    assert headers["Content-Security-Policy"] == (
        "default-src 'none'; font-src 'self'; script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    )
