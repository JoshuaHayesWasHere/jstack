"""Each committed statechart was drawn from its spec as the spec is now.

A chart under `features/*/spec/*-statechart/` is a picture of a TLA+ spec, and a reader takes it
for what the spec says today. `statechart from-spec` writes `drawnFrom` into the folder's
`summary.json`: the command that drew it, the sha256 of each spec, config and mapping it read, by
its path from the folder that holds the chart folder, and the sha256 of `chart.mmd`. The test
hashes those files again and fails, naming the folder and the command that draws it again, when
one of them changed or is gone, or when `chart.mmd` is not the one the command drew.

It compares hashes and never runs TLC: FlowToday alone takes about 7M states and 14 GB to draw,
which no check can afford.
"""

import hashlib
import json
from pathlib import Path

import pytest

from testing.paths import REPO

READ_SET = ("features/*/spec/",)
CHARTS = sorted(REPO.glob("features/*/spec/*-statechart"))


def sha256(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


@pytest.mark.parametrize("chart", CHARTS, ids=lambda chart: chart.name)
def test_each_chart_was_drawn_from_its_spec_as_it_is_now(chart):
    folder = chart.relative_to(REPO)
    drawn = json.loads((chart / "summary.json").read_text(encoding="utf-8")).get("drawnFrom")
    readme = chart.parent / "README.md"
    recipe = f", as {readme.relative_to(REPO)} says" if readme.exists() else ""
    if drawn is None:
        pytest.fail(
            f"{folder}/summary.json has no drawnFrom: draw the chart again with statechart"
            f" from-spec{recipe}."
        )
    changed = [
        f"{name} is gone" if not (chart.parent / name).is_file() else f"{name} changed"
        for name, digest in drawn["inputs"].items()
        if not (chart.parent / name).is_file() or sha256(chart.parent / name) != digest
    ]
    if sha256(chart / "chart.mmd") != drawn["chart"]:
        changed.append("chart.mmd is not the one the command drew")
    assert not changed, (
        f"{folder} was drawn from files that have changed since: {'; '.join(changed)}."
        f" Draw it again: in {folder.parent}, run {drawn['command']}{recipe}."
    )
