"""docs/limits.md stays true: a row whose Where is a `path:line` of this repo has, as its
Value, the text on that line, and every machine size and room line has a row."""

import re
from pathlib import Path

from jgauge import limits, sample

REPO = Path(__file__).parent.parent
DOC = REPO / "docs" / "limits.md"
CELL = re.compile(r"`([^`]+)`")
PLACE = re.compile(r"^((?:src|tests|templates)/[\w./-]+|Makefile):(\d+)$")


def rows():
    for line in DOC.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0] != "Limit" and not set(cells[0]) <= {"-"}:
            yield cells


def test_each_row_that_names_a_line_of_this_repo_gives_the_text_on_it():
    checked = 0
    for name, where, value, *_ in rows():
        places = [found for cell in CELL.findall(where) if (found := PLACE.match(cell))]
        if not places:
            continue
        path, number = places[0][1], int(places[0][2])
        (shown,) = CELL.findall(value)
        lines = (REPO / path).read_text().splitlines()
        assert number <= len(lines), f"{name}: {path} has no line {number}"
        assert shown in lines[number - 1], f"{name}: {path}:{number} is {lines[number - 1]!r}"
        checked += 1
    assert checked >= 50


def test_every_machine_size_and_every_room_line_has_a_row():
    text = DOC.read_text()
    for name in limits.Name:
        assert f"`{name}`" in text
    for name in sample.ROOM_LINES:
        assert f"`{name}={sample.room_line(name)}`" in text
