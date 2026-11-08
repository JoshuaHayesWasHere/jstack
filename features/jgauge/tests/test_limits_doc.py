"""features/jgauge/docs/limits.md stays true. When a row's Where column names a file of this repo,
that file holds the row's Value as text. The page gives no line numbers, since a change to any other
line of the file would move them. A Where cell that gives one anyway, `path:line` or
`path:first-last`, holds the Value on that line or in that range, with runs of spaces read as one.
Every machine size and room line has a row."""

import re

from jgauge import sample, sizes
from testing.paths import REPO

DOC = REPO / "features" / "jgauge" / "docs" / "limits.md"
CELL = re.compile(r"`([^`]+)`")
PLACE = re.compile(
    r"^((?:src|tests|templates|features|scripts|testing|\.github)/[\w./-]+|Makefile|\.repo-standard\.yml)"
    r"(?::(\d+)(?:-(\d+))?)?$"
)


def rows(text):
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0] != "Limit" and not set(cells[0]) <= {"-"}:
            yield cells


def flat(text):
    return " ".join(text.split())


def faults(text, root=REPO):
    """Each row whose Where file, or the line that the Where cell names, lacks the row's Value,
    and the count of rows that name a file."""
    found, checked = [], 0
    for name, where, value, *_ in rows(text):
        places = [hit for cell in CELL.findall(where) if (hit := PLACE.match(cell))]
        if not places:
            continue
        path, first, last = places[0].groups()
        (shown,) = CELL.findall(value)
        checked += 1
        if not (root / path).is_file():
            found.append(f"{name}: {path} is no file")
            continue
        lines = (root / path).read_text().splitlines()
        if not first:
            if shown not in "\n".join(lines):
                found.append(f"{name}: {path} has no {shown!r}")
            continue
        span = lines[int(first) - 1 : int(last or first)]
        if flat(shown) not in flat(" ".join(span)):
            now = [n for n, line in enumerate(lines, 1) if flat(shown) in flat(line)]
            at = f"it is at line {now[0]}" if now else "the file has no such text"
            found.append(f"{name}: {places[0][0]} does not hold {shown!r}, {at}")
    return found, checked


def test_each_row_that_names_a_file_of_this_repo_gives_text_it_holds():
    found, checked = faults(DOC.read_text())
    assert found == []
    assert checked >= 50


def test_a_value_out_of_its_file_or_off_a_line_it_names_is_found(tmp_path):
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "a.sh").write_text("# a\nLOAD=200\n  CPU=90\n")
    row = "| {} | `{}` | `{}` | x | x |\n"
    text = "".join(
        [
            "| Limit | Where | Value | Protects | Basis |\n",
            "|---|---|---|---|---|\n",
            row.format("in its file", "features/a.sh", "CPU=90"),
            row.format("on its line", "features/a.sh:2", "LOAD=200"),
            row.format("in its range", "features/a.sh:1-3", "CPU=90"),
            row.format("moved", "features/a.sh:3", "LOAD=200"),
            row.format("past the end", "features/a.sh:9", "LOAD=200"),
            row.format("gone from the line", "features/a.sh:2", "LOAD=150"),
            row.format("gone from the file", "features/a.sh", "LOAD=150"),
            row.format("no file", "features/b.sh", "LOAD=200"),
            row.format("elsewhere", "~/.config/jstack/machine.toml", "LOAD=1"),
        ]
    )
    assert faults(text, tmp_path) == (
        [
            "moved: features/a.sh:3 does not hold 'LOAD=200', it is at line 2",
            "past the end: features/a.sh:9 does not hold 'LOAD=200', it is at line 2",
            "gone from the line: features/a.sh:2 does not hold 'LOAD=150', "
            "the file has no such text",
            "gone from the file: features/a.sh has no 'LOAD=150'",
            "no file: features/b.sh is no file",
        ],
        8,
    )


def test_every_machine_size_and_every_room_line_has_a_row():
    text = DOC.read_text()
    for name in sizes.Name:
        assert f"`{name}`" in text
    for name in sample.ROOM_LINES:
        assert f"`{name}={sample.room_line(name)}`" in text
