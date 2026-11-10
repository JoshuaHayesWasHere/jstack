"""`statechart site` writes one page that explores every committed chart: each chart and each of
its states is on it, it fetches nothing when viewed, and it shows each chart's stories."""

import html
import re

from statechart_support import node, read, write
from testing.paths import REPO

CHARTS = sorted((REPO / "features").glob("*/spec/*-statechart/chart.mmd"))
LEAF = re.compile(r'^\s*state "([^"]*)" as (\w+)\s*$', re.M)


def declared_states(chart):
    """Each state the chart declares, as `id: caption`, its legend left out."""
    return {
        state_id: re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", caption)).strip()
        for caption, state_id in LEAF.findall(read(chart))
        if not state_id.startswith("legendGroup")
    }


def site(root, out, *extra):
    return node("statechart", ["site", "--out", str(out), "--root", str(root), *extra], root)


def test_the_page_holds_each_committed_chart_and_each_of_its_states(tmp_path):
    out = tmp_path / "charts" / "index.html"
    r = site(REPO, out)
    assert r.returncode == 0, r.stderr
    page = read(out)
    names = {c.parent.name.removesuffix("-statechart") for c in CHARTS}
    assert names >= {"HomeTreeToday", "RowLife", "MainRed", "ThreadLife", "PrVerdict", "FlowToday"}
    for chart in CHARTS:
        name = chart.parent.name.removesuffix("-statechart")
        assert f'class="tab" role="tab" data-chart="{name}"' in page
        assert f'<section class="chart-panel" data-chart="{name}"' in page
        states = declared_states(chart)
        assert states, chart
        for state_id, caption in states.items():
            assert page.count(f'id="{name}-{state_id}"') == 1, (name, state_id)
            assert html.escape(caption, quote=True) in page or caption in page, (name, caption)
    total = sum(len(declared_states(c)) for c in CHARTS)
    assert r.stdout == f"wrote {out}: {len(CHARTS)} charts, {total} states\n"


def test_the_page_fetches_nothing_when_it_is_viewed(tmp_path):
    out = tmp_path / "index.html"
    assert site(REPO, out).returncode == 0
    page = read(out)
    assert not re.search(r"<script[^>]*\bsrc=|<link\b|@import|url\(\s*['\"]?https?:", page)
    assert re.findall(r"https?://[^\s\"'<>]+", page) == ["http://www.w3.org/2000/svg"] * len(CHARTS)


CHART = """---
title: "Does the lamp light?"
---
stateDiagram-v2
  classDef group0 fill:#d1f2eb,stroke:#697976,color:#1b2631
  [*] --> off
  state "Off (lamp.py:2, the switch is down)" as off
  state "On" as on
  off --> on : you flip the switch
  on --> off : you flip it back
  class off group0
"""


def lamp(root, stories):
    folder = root / "features" / "lamp" / "spec" / "Lamp-statechart"
    folder.mkdir(parents=True)
    write(folder / "chart.mmd", CHART)
    write(folder / "stories.md", stories)
    src = root / "features" / "lamp" / "src"
    src.mkdir()
    write(src / "lamp.py", "def lamp():\n    return 'down'\n")
    return folder


def test_the_page_tells_a_charts_bug_paths_and_says_so_when_it_has_none(tmp_path):
    lamp(tmp_path / "a", "## Bug 1: NeverDark\n\nYou flip the switch, and the lamp `stays` on.\n")
    out = tmp_path / "a" / "index.html"
    assert site(tmp_path / "a", out).returncode == 0
    page = read(out)
    assert "<h4>Bug 1: NeverDark</h4>" in page
    assert "the lamp <code>stays</code> on." in page
    assert "Does the lamp light?" in page
    assert "return &#x27;down&#x27;" in page or "return 'down'" in page
    lamp(tmp_path / "b", "")
    out = tmp_path / "b" / "index.html"
    assert site(tmp_path / "b", out).returncode == 0
    assert "No bug paths" in read(out)


def test_check_says_whether_the_written_page_is_the_one_the_charts_make(tmp_path):
    folder = lamp(tmp_path, "")
    out = tmp_path / "index.html"
    assert site(tmp_path, out).returncode == 0
    current = site(tmp_path, out, "--check")
    assert (current.returncode, current.stdout) == (0, f"{out} is current\n")
    write(folder / "chart.mmd", CHART.replace('"On"', '"Lit"'))
    stale = site(tmp_path, out, "--check")
    assert stale.returncode == 1
    assert stale.stdout == f"{out} is stale: run statechart site --out {out}\n"
