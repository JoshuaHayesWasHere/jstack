"""`statechart excalidraw` draws each committed chart.mmd as an Excalidraw scene: one box per state,
one arrow per step, each arrow bound at both ends, and no two boxes on top of each other."""

import itertools
import json
import re

import pytest

from statechart_support import statechart_cli
from testing.paths import REPO

READ_SET = ("features/*/spec/*-statechart/chart.mmd",)
CHARTS = sorted(REPO.glob("features/*/spec/*-statechart/chart.mmd"))
COMMON = {
    "id": str,
    "type": str,
    "x": (int, float),
    "y": (int, float),
    "width": (int, float),
    "height": (int, float),
    "angle": (int, float),
    "strokeColor": str,
    "backgroundColor": str,
    "fillStyle": str,
    "strokeWidth": (int, float),
    "strokeStyle": str,
    "roughness": int,
    "opacity": int,
    "groupIds": list,
    "seed": int,
    "version": int,
    "versionNonce": int,
    "isDeleted": bool,
    "boundElements": list,
    "locked": bool,
}
BY_TYPE = {
    "text": {"text": str, "originalText": str, "fontSize": (int, float), "fontFamily": int},
    "arrow": {"points": list, "startBinding": dict, "endBinding": dict},
    "frame": {"name": str},
    "rectangle": {},
    "ellipse": {},
}


def name_of(chart):
    return chart.parent.name.removesuffix("-statechart")


def states_and_steps(chart):
    """The chart's state ids and its count of steps, read from its lines: every id declared with
    `state` that opens no composite, outside the Legend, and every id a step names."""
    states, steps, legend = set(), 0, False
    for line in chart.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if re.match(r"state\b.*\bas legend\s*\{$", line):
            legend = True
            continue
        if legend:
            legend = line != "}"
            continue
        declared = re.match(r'state\s+(?:"[^"]*"\s+as\s+)?(\w+)\s*$', line)
        if declared:
            states.add(declared.group(1))
        step = re.match(r"(\[\*\]|\w+)\s*-->\s*(\[\*\]|\w+)", line)
        if step:
            steps += 1
            states.update(end for end in step.groups() if end != "[*]")
    return states, steps


def build(chart, out):
    assert statechart_cli.main(["excalidraw", str(chart), "--out", str(out)]) == 0
    return json.loads(out.read_text(encoding="utf-8"))


def bounds(e):
    """An element's box on the canvas; an arrow's points are relative to its x and y."""
    if e["type"] == "arrow":
        xs = [e["x"] + p[0] for p in e["points"]]
        ys = [e["y"] + p[1] for p in e["points"]]
        return min(xs), min(ys), max(xs), max(ys)
    return e["x"], e["y"], e["x"] + e["width"], e["y"] + e["height"]


def overlap(a, b):
    return (
        a["x"] < b["x"] + b["width"]
        and b["x"] < a["x"] + a["width"]
        and a["y"] < b["y"] + b["height"]
        and b["y"] < a["y"] + a["height"]
    )


@pytest.mark.parametrize("chart", CHARTS, ids=name_of)
def test_each_chart_draws_as_a_valid_scene_with_a_box_per_state_and_a_bound_arrow_per_step(
    chart, tmp_path
):
    scene = build(chart, tmp_path / "chart.excalidraw")
    assert scene["type"] == "excalidraw"
    assert scene["version"] == 2
    assert isinstance(scene["appState"], dict) and isinstance(scene["files"], dict)
    elements = scene["elements"]
    by_id = {e["id"]: e for e in elements}
    assert len(by_id) == len(elements), "element ids repeat"
    for e in elements:
        for key, kind in {**COMMON, **BY_TYPE[e["type"]]}.items():
            assert isinstance(e[key], kind), f"{e['id']}.{key} is {e.get(key)!r}"
        for bound in e["boundElements"]:
            other = by_id[bound["id"]]
            assert other["type"] == bound["type"]
            if other["type"] == "text":
                assert other["containerId"] == e["id"]
            else:
                ends = (other["startBinding"]["elementId"], other["endBinding"]["elementId"])
                assert e["id"] in ends
        if e["type"] == "text" and e["containerId"]:
            assert {"id": e["id"], "type": "text"} in by_id[e["containerId"]]["boundElements"]
        if e["frameId"]:
            frame = by_id[e["frameId"]]
            assert frame["type"] == "frame"
            assert elements.index(frame) > elements.index(e), "a frame precedes its children"
            left, top, right, bottom = bounds(e)
            f_left, f_top, f_right, f_bottom = bounds(frame)
            assert f_left <= left and f_top <= top and right <= f_right and bottom <= f_bottom, (
                f"{e['id']} lies outside its frame"
            )

    def drawn(kind):
        return [
            e for e in elements if e.get("customData", {}).get("statechart", {}).get("kind") == kind
        ]

    boxes = drawn("state")
    states, steps = states_and_steps(chart)
    assert sorted(b["customData"]["statechart"]["id"] for b in boxes) == sorted(states)
    for box in boxes:
        assert box["type"] == "rectangle"
        labels = [by_id[b["id"]] for b in box["boundElements"] if b["type"] == "text"]
        assert len(labels) == 1 and labels[0]["text"].strip()
    arrows = [e for e in elements if e["type"] == "arrow"]
    assert len(arrows) == len(drawn("step")) == steps
    for arrow in arrows:
        for end in ("startBinding", "endBinding"):
            target = by_id[arrow[end]["elementId"]]
            assert {"id": arrow["id"], "type": "arrow"} in target["boundElements"]
            assert target["type"] in ("rectangle", "ellipse")
    for a, b in itertools.combinations(boxes + drawn("start"), 2):
        assert not overlap(a, b), f"{a['id']} overlaps {b['id']}"
    frames = [e for e in elements if e["type"] == "frame"]
    assert {f["name"] for f in frames} >= {"Legend"}
    for a, b in itertools.combinations(frames, 2):
        assert not overlap(a, b), f"frame {a['name']} overlaps frame {b['name']}"
