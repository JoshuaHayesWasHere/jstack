"""--png draws a chart too big for scale 2 at a scale that keeps each side of its PNG within
16384 px, so the PNG opens in any viewer. A real render needs Chromium, which only the tests of
jbus's page start (`browser`), so a stand-in for mermaid-cli gives the chart's size here."""

import math
import os
import re

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
