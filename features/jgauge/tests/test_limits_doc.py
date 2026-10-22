"""features/jgauge/docs/limits.md stays true. When a row's Where column names a `path:line` of
this repo, that file holds the row's Value as text. Every machine size and room line has a
row. The
test treats the line number as a pointer and does not check it: a change to any other line of
the file would move it, and a test that pinned it would fail every pull request that touched
that file."""

import re

from jgauge import sample, sizes
from testing.paths import REPO

DOC = REPO / "features" / "jgauge" / "docs" / "limits.md"
CELL = re.compile(r"`([^`]+)`")
PLACE = re.compile(r"^((?:src|tests|templates|features)/[\w./-]+|Makefile):(\d+)$")


def rows():
    for line in DOC.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0] != "Limit" and not set(cells[0]) <= {"-"}:
            yield cells


def test_each_row_that_names_a_file_of_this_repo_gives_text_it_holds():
    checked = 0
    for name, where, value, *_ in rows():
        places = [found for cell in CELL.findall(where) if (found := PLACE.match(cell))]
        if not places:
            continue
        path = places[0][1]
        (shown,) = CELL.findall(value)
        assert shown in (REPO / path).read_text(), f"{name}: {path} has no {shown!r}"
        checked += 1
    assert checked >= 50


def test_every_machine_size_and_every_room_line_has_a_row():
    text = DOC.read_text()
    for name in sizes.Name:
        assert f"`{name}`" in text
    for name in sample.ROOM_LINES:
        assert f"`{name}={sample.room_line(name)}`" in text
