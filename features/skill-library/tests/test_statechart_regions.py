"""Reference lanes (`statechart site --lanes`): MainRed's and RowLife's mappings name their lanes,
and the lanes module draws a chart's graph with every step on one arrow, table cell or row, no
two lines crossing and no label on a line. The full graphs are drawn and checked only by
`make charts`, never here: these tests run on a lamp of a few states, with no TLC and no browser,
and on a state folder written in the test, never the real one."""

import importlib
import json
import re
from types import SimpleNamespace

import pytest

import statechart_support  # noqa: F401  (puts the port's package on the path)
from testing.paths import REPO

L = importlib.import_module("statechart.lanes")
ChartError = importlib.import_module("statechart.lib").ChartError
load_mapping = importlib.import_module("statechart.mapping").load_mapping

SPEC = REPO / "features" / "jbus" / "spec"


def test_mainred_names_four_lanes_with_one_box_for_a_red_with_a_newer_run():
    m = load_mapping(SPEC / "MainRed.map.py")
    assert list(m.lanes) == ["main", "rev", "fix", "mac"]
    assert list(m.lanes["main"]["boxes"]) == ["green", "running", "rerun", "red", "red_newer"]
    # A red whose newest commit's run is going is the merged box, not a box of its own.
    red_tip = {"check": ["failed", "pending"], "rec": {"broken": 1, "green": 0}}
    assert m.main_box(red_tip) == "red_newer"
    assert m.main_box({"check": ["failed"], "rec": {"broken": 1, "green": 0}}) == "red"


def test_rowlife_names_six_superstates_and_counts_a_relaunched_queued_row_at_work():
    m = load_mapping(SPEC / "RowLife.map.py")
    assert list(m.lanes["status"]["boxes"]) == [
        "notlaunched",
        "question",
        "atwork",
        "review",
        "final",
        "removed",
    ]
    queued = {"status": "queued", "go": "approved", "launched": False}
    requeued = dict(queued, launched=True)
    assert m.superstate(queued) == "notlaunched"
    assert m.superstate(requeued) == "atwork"
    running = dict(requeued, status="running")
    assert m.lane_moves(running, requeued, "Thread") == (
        [("status", "atwork", "atwork", "running>requeued")],
        None,
    )


def test_a_count_is_only_on_what_a_log_records(tmp_path):
    m = load_mapping(SPEC / "MainRed.map.py")
    assert m.seen(tmp_path / "no-such-folder") == {}
    jstack = tmp_path / "jstack"
    jstack.mkdir()
    run = {
        "branch": "main",
        "event": "push",
        "name": "check (ubuntu)",
        "sha": "a",
        "created": "2026-11-01T00:00:00Z",
    }
    lines = [
        dict(run, run=1, attempt=1, conclusion="success"),
        dict(run, run=2, attempt=1, conclusion="failure"),
        dict(run, run=2, attempt=2, conclusion="success"),
    ]
    (jstack / "ci.jsonl").write_text("\n".join(map(json.dumps, lines)) + "\nnot json\n")
    seen = m.seen(tmp_path)
    assert {k: n for k, (n, _) in seen.items()} == {
        ("main", "running", "green", "run_passes"): 1,
        ("main", "running", "rerun", "pass"): 1,
        ("main", "rerun", "green", "rerun_passes"): 1,
    }


# A lamp: off, on and broken, a wall switch in a lane of its own, and a bulb change inside "broken".


LAMP = SimpleNamespace(
    lanes={
        "lamp": {
            "name": "The lamp",
            "about": "what you see",
            "start": "off",
            "boxes": {"off": "Off", "on": "On", "broken": "Broken"},
            "chips": {"broken": {"dark": "dark", "flicker": "flickers"}},
        },
        "wall": {
            "name": "The wall",
            "about": "its switch",
            "start": "up",
            "boxes": {"up": "Up", "down": "Down"},
        },
    },
    who={"you": "you", "bulb": "the bulb"},
    arrows={
        ("lamp", "off", "on", "Press"): ("you", "you press it", None),
        ("lamp", "on", "off", "Press"): ("you", "you press it again", None),
        ("lamp", "on", "broken", "Burn"): ("bulb", "the bulb burns out", "after a long night"),
        ("lamp", "broken", "off", "Change"): ("you", "you change the bulb", None),
        ("wall", "up", "down", "Flip"): ("you", "you flip the switch", None),
        ("wall", "down", "up", "Flip"): ("you", "you flip it back", None),
    },
    still={"lamp:Wait": ("bulb", "lamp", "nothing happens")},
)


def lamp_box(v):
    return "broken" if v["lamp"] in ("dark", "flicker") else v["lamp"]


def lamp_moves(before, after, action):
    if before["lamp"] != after["lamp"]:
        f, t = lamp_box(before), lamp_box(after)
        return [("lamp", f, t, action if f != t else f"{before['lamp']}>{after['lamp']}")], None
    if before["wall"] != after["wall"]:
        return [("wall", before["wall"], after["wall"], action)], None
    return [], f"lamp:{action}"


LAMP.lane_moves = lamp_moves


def lanes():
    return L.Lanes.of(LAMP, "Lamp.tla")


def graph(*steps):
    states = {}
    for f, t, _ in steps:
        states.setdefault(f, None)
        states.setdefault(t, None)

    def vars_of(s):
        lamp, wall = s.split("/")
        return {"lamp": lamp, "wall": wall}

    return {
        "nodes": {s: {"vars": vars_of(s)} for s in states},
        "edges": [{"from": f, "to": t, "action": a} for f, t, a in steps if f != t],
        "loops": [{"from": f, "to": t, "action": a} for f, t, a in steps if f == t],
    }


STEPS = [
    ("off/up", "on/up", "Press"),
    ("on/up", "off/up", "Press"),
    ("on/up", "dark/up", "Burn"),
    ("dark/up", "flicker/up", "Wiggle"),
    ("flicker/up", "off/up", "Change"),
    ("off/up", "off/down", "Flip"),
    ("off/down", "off/up", "Flip"),
    ("off/up", "off/up", "Wait"),
]


def drawn(steps):
    """The lamp's lanes panel drawn from these steps, as a page holds it."""
    p = L.project(lanes(), [("Lamp.cfg", graph(*steps))])
    body, drawings = L.panel("Lamp", lanes(), p, {("lamp", "off", "on", "Press"): (3, "a log")})
    return f'<section data-chart="Lamp">{body}</section>', drawings


def test_every_step_of_the_lamp_has_one_place_and_every_place_a_step():
    page, _ = drawn(STEPS)
    found = L.coverage(page, "Lamp", L.project(lanes(), [("Lamp.cfg", graph(*STEPS))]))
    assert (found["steps"], found["steps_without_place"], found["places_without_step"]) == (
        8,
        0,
        [],
    )
    # The one move a log records carries its count, on the wide and the narrow drawing; no other.
    assert re.findall(r">seen [\d,]+</tspan>", page) == [">seen 3</tspan>"] * 2


def test_coverage_fails_on_a_step_with_no_arrow():
    page, _ = drawn([s for s in STEPS if s[2] != "Burn"])
    found = L.coverage(page, "Lamp", L.project(lanes(), [("Lamp.cfg", graph(*STEPS))]))
    # The burn is on no arc of either drawing.
    assert found["steps_without_place"] == 2


def test_coverage_fails_on_an_arrow_with_no_step():
    page, _ = drawn(STEPS)
    fewer = [s for s in STEPS if s[2] not in ("Burn", "Wiggle")]
    found = L.coverage(page, "Lamp", L.project(lanes(), [("Lamp.cfg", graph(*fewer))]))
    assert found["steps_without_place"] == 0
    assert any("lamp.on.broken" in p for p in found["places_without_step"])
    assert any("dark-flicker" in p for p in found["places_without_step"])


def test_a_step_the_mapping_has_no_words_for_is_refused():
    with pytest.raises(ChartError, match="no words"):
        L.project(lanes(), [("Lamp.cfg", graph(("broken/up", "on/up", "Fix")))])


def test_the_lamp_is_drawn_with_no_crossing_and_no_label_on_a_line_or_a_label():
    _, drawings = drawn(STEPS)
    for d in drawings:
        assert {k: len(v) for k, v in L.faults(d).items()} == dict.fromkeys(
            ("crossings", "label_on_line", "label_on_label", "label_on_box"), 0
        )


def test_the_geometry_check_sees_a_crossing_and_a_label_on_a_line():
    _, drawings = drawn(STEPS)
    d = drawings[0]
    _, _, it, _, _ = d.lanes[0]
    a, b = it["arcs"][0], it["arcs"][1]
    # Run the first arc's horizontal through the second's sides, and its label onto that line.
    y = (b["points"][0][1] + b["points"][1][1]) / 2
    x0, x1 = (
        min(b["points"][0][0], b["points"][2][0]) - 30,
        max(b["points"][0][0], b["points"][2][0]) + 30,
    )
    a["points"] = [(x0, a["points"][0][1]), (x0, y), (x1, y), (x1, a["points"][3][1])]
    a["label_x"], a["label_y0"] = (x0 + x1) / 2, y - L.LH / 2
    found = L.faults(d)
    assert found["crossings"] and found["label_on_line"]


def test_a_lane_that_holds_k5_is_refused():
    boxes = ["a", "b", "c", "d", "e"]
    arcs = [{"from": x, "to": y} for i, x in enumerate(boxes) for y in boxes[i + 1 :]]
    with pytest.raises(ChartError, match="without two crossing"):
        L.choose(boxes, arcs)
