"""--png draws a chart too big for Chromium at the usual scale whole: no side of its PNG passes
16384 px, Chromium's texture limit, past which the screenshot comes out partly blank."""

import re
import shutil
import subprocess

import pytest
from PIL import Image

from statechart_support import statechart_cli, write

pytestmark = [
    pytest.mark.browser,
    pytest.mark.timeout(600),
    pytest.mark.skipif(shutil.which("npx") is None, reason="no npx to run mermaid-cli with"),
]

LIMIT = 16384


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
