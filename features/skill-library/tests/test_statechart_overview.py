"""`statechart overview` draws a chart at the level of its groups: ten boxes or fewer, one per group
of each region and one for a region's states in no group, every state in a box, and every step
inside a box or on an arrow that counts it. Each overview is drawn on the page, above its chart, and
`make charts` writes it as an Excalidraw scene beside the chart's own, none of them committed."""

import importlib
import json
import re

import pytest

from statechart_support import node, read, statechart_cli
from testing.paths import REPO

site = importlib.import_module("statechart.site")
READ_SET = ("features/*/spec/*-statechart/chart.mmd",)
CHARTS = sorted(REPO.glob("features/*/spec/*-statechart/chart.mmd"))
BOX = re.compile(r'^\s*state "(.*?)<br/>(\d+) states?(?:, (\d+) steps? inside)?" as (\w+)$', re.M)
ARROW = re.compile(r"^\s*(\w+) --> (\w+) : (\d+) steps?$", re.M)


def name_of(chart):
    return chart.parent.name.removesuffix("-statechart")


def drawn_counts(chart):
    """The chart's states and steps as the page counts them."""
    regions = site.read_text(read(chart), name_of(chart)).regions
    return sum(len(r.states) for r in regions), sum(len(r.steps) for r in regions)


@pytest.mark.parametrize("chart", CHARTS, ids=name_of)
def test_the_overview_has_a_box_per_group_and_counts_every_state_and_step(chart):
    r = node("statechart", ["overview", str(chart)], REPO)
    assert r.returncode == 0, r.stderr
    boxes = BOX.findall(r.stdout)
    arrows = ARROW.findall(r.stdout)
    assert 1 <= len(boxes) <= 10, f"{name_of(chart)} has {len(boxes)} boxes"
    states, steps = drawn_counts(chart)
    assert sum(int(n) for _, n, _, _ in boxes) == states
    assert sum(int(n or 0) for _, _, n, _ in boxes) + sum(int(n) for *_, n in arrows) == steps
    groups = json.loads(read(chart.parent / "summary.json"))["chartGroups"]
    named = {name for name, *_ in boxes}
    assert {g["name"] for g in groups} <= named
    keys = {key for *_, key in boxes}
    assert all(a in keys and b in keys and a != b for a, b, _ in arrows)


@pytest.mark.parametrize("chart", CHARTS, ids=name_of)
def test_each_overview_file_is_a_scene_with_a_box_per_group(chart, tmp_path):
    out = tmp_path / f"{name_of(chart)}.overview.excalidraw"
    assert statechart_cli.main(["overview", str(chart), "--out", str(out)]) == 0
    scene = json.loads(read(out))
    boxes = [
        e
        for e in scene["elements"]
        if e.get("customData", {}).get("statechart", {}).get("kind") == "state"
    ]
    out = node("statechart", ["overview", str(chart)], REPO).stdout
    assert len(boxes) == len(BOX.findall(out))
    arrows = [e for e in scene["elements"] if e["type"] == "arrow"]
    assert len(arrows) == len(ARROW.findall(out)) + out.count("[*] -->")
