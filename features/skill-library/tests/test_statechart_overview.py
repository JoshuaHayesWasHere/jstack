"""`statechart overview` draws a chart at the level of its groups: ten boxes or fewer, one per group
of each region and one for a region's states in no group, every state in a box, and every step
inside a box or on an arrow that counts it. Each overview is drawn again from the charts under
features/home/docs/charts/: on the page, above its chart, and as an Excalidraw file beside the
chart's own. A chart is held to its model by test_statechart_current.py, and the overviews are held
to their charts here, so a group that moves fails the drift check."""

import importlib
import json
import re
import shutil

import pytest

from statechart_support import node, read, statechart_cli, write
from testing.paths import REPO

site = importlib.import_module("statechart.site")
READ_SET = ("features/*/spec/*-statechart/chart.mmd", "features/home/docs/charts/")
CHARTS = sorted(REPO.glob("features/*/spec/*-statechart/chart.mmd"))
DRAWN = REPO / "features" / "home" / "docs" / "charts"
FLOW = DRAWN / "flow.toml"
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


def stale_overviews(root, page, drawn, scratch):
    """The drift check: each chart under `root` whose overview is not the one its chart.mmd draws
    now, in `page` or in `drawn`/NAME.overview.excalidraw. The parts of the page it compares hold
    no code a chart cites, so they stay current while that code moves."""
    flow = site.load_flow(root / FLOW.relative_to(REPO))
    root, charts = site.read_all(root, flow)
    fresh = site.overviews(charts, flow)
    committed = read(page)
    stale = [name for name, part in fresh.items() if part not in committed]
    for chart in charts:
        out = scratch / f"{chart.name}.overview.excalidraw"
        built = statechart_cli.main(
            ["overview", str(chart.folder / "chart.mmd"), "--out", str(out)]
        )
        assert built == 0
        if out.read_bytes() != (drawn / f"{chart.name}.overview.excalidraw").read_bytes():
            stale.append(f"{chart.name}.overview.excalidraw")
    return stale


def test_each_committed_overview_is_the_one_its_chart_draws(tmp_path):
    stale = stale_overviews(REPO, DRAWN / "index.html", DRAWN, tmp_path)
    assert not stale, (
        f"stale overviews: {', '.join(stale)}. Draw them again: statechart site --out"
        f" {(DRAWN / 'index.html').relative_to(REPO)} --flow {FLOW.relative_to(REPO)}, and for"
        " each chart statechart overview CHART.mmd --out"
        f" {DRAWN.relative_to(REPO)}/NAME.overview.excalidraw"
    )


def test_the_drift_check_fails_once_a_state_moves_to_another_group(tmp_path):
    for chart in CHARTS:
        copy = tmp_path / chart.relative_to(REPO)
        copy.parent.mkdir(parents=True)
        shutil.copy(chart, copy)
    shutil.copytree(DRAWN, tmp_path / DRAWN.relative_to(REPO))
    drawn = tmp_path / DRAWN.relative_to(REPO)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    assert stale_overviews(tmp_path, drawn / "index.html", drawn, scratch) == []
    moved = tmp_path / "features/jmerge/spec/FlowToday-statechart/chart.mmd"
    text = read(moved)
    first = re.search(r"^  class s\d+ group0$", text, re.M)[0]
    write(moved, text.replace(first, first.replace("group0", "group1"), 1))
    assert stale_overviews(tmp_path, drawn / "index.html", drawn, scratch) == [
        "FlowToday",
        "FlowToday.overview.excalidraw",
    ]


@pytest.mark.parametrize("chart", CHARTS, ids=name_of)
def test_each_overview_file_is_a_scene_with_a_box_per_group_beside_the_charts_own(chart):
    scene = json.loads(read(DRAWN / f"{name_of(chart)}.overview.excalidraw"))
    assert (DRAWN / f"{name_of(chart)}.excalidraw").exists()
    boxes = [
        e
        for e in scene["elements"]
        if e.get("customData", {}).get("statechart", {}).get("kind") == "state"
    ]
    out = node("statechart", ["overview", str(chart)], REPO).stdout
    assert len(boxes) == len(BOX.findall(out))
    arrows = [e for e in scene["elements"] if e["type"] == "arrow"]
    assert len(arrows) == len(ARROW.findall(out)) + out.count("[*] -->")
