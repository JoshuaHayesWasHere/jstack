"""--png draws a chart too big for scale 2 at a scale that keeps each side of its PNG within
16384 px, so the PNG opens in any viewer, and draws all of it."""

import math
import os
import re
import shutil
import subprocess

import pytest
from PIL import Image

from statechart_support import read, statechart_cli, write

LIMIT = 16384


def test_png_of_home_tree_today_size_asks_mermaid_for_a_scale_that_keeps_each_side_within_16384(
    tmp_path, monkeypatch
):
    """a chart of HomeTreeToday's size, 12165 by 5793 px at scale 1, which `-s 2` drew 24330 px
    wide, is drawn at a scale that keeps each side of its PNG within 16384 px"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    write(
        bin_dir / "npx",
        f"""#!/bin/sh
printf '%s\\n' "$*" >> '{calls}'
while [ $# -gt 0 ]; do
  case "$1" in
    -o) case "$2" in
      *.svg) echo '<svg width="12164.90625" viewBox="4 4 12164.90625 5793"></svg>' > "$2" ;;
      *) touch "$2" ;;
    esac ;;
  esac
  shift
done
""",
        0o755,
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    chart = tmp_path / "chart.mmd"
    write(chart, "stateDiagram-v2\n  [*] --> A\n")

    assert statechart_cli.render([str(chart)], str) == [str(tmp_path / "chart.png")]

    drawn = [c for c in read(calls).splitlines() if f" -o {tmp_path / 'chart.png'} " in c]
    assert len(drawn) == 1, read(calls)
    scale = float(re.search(r" -s (\S+)", drawn[0])[1])
    assert math.ceil(12164.90625) * scale <= LIMIT, scale
    assert 5793 * scale <= LIMIT, scale
    assert math.ceil(12164.90625) * scale > LIMIT * 0.99, f"{scale} draws it smaller than it must"


@pytest.mark.browser
@pytest.mark.timeout(600)
@pytest.mark.skipif(shutil.which("npx") is None, reason="no npx to run mermaid-cli with")
def test_png_of_a_chart_wider_than_8192_px_keeps_each_side_within_16384_and_draws_it_all(
    tmp_path,
):
    """a chart wider than 8192 px at scale 1, which `-s 2` would draw past 16384 px, renders to
    a PNG with no side over 16384 px, and its far right is drawn, not blank"""
    states = [f"Waiting_on_the_reviewer_of_pull_request_{i:03}" for i in range(30)]
    chart = tmp_path / "chart.mmd"
    natural_width = "---\nconfig:\n  state:\n    useMaxWidth: false\n---\n"
    write(chart, natural_width + "stateDiagram-v2\n" + "".join(f"  [*] --> {s}\n" for s in states))
    svg = tmp_path / "natural.svg"
    subprocess.run(
        ["npx", "-y", statechart_cli.MERMAID_CLI, "-i", str(chart), "-o", str(svg)],
        check=True,
        capture_output=True,
    )
    view_box = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) [\d.]+"', svg.read_text())
    assert view_box and float(view_box[1]) > LIMIT / 2, view_box and view_box[0]

    pngs = statechart_cli.render([str(chart)], str)

    assert pngs == [str(tmp_path / "chart.png")]
    with Image.open(pngs[0]) as png:
        width, height = png.size
        assert max(width, height) <= LIMIT, png.size
        assert width > LIMIT / 2, png.size
        right = png.convert("L").crop((width * 9 // 10, 0, width, height))
        assert right.getextrema()[0] < 128, "the right tenth of the chart is blank"
