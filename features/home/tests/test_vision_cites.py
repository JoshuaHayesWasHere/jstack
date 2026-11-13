"""Each `path:line` cite in the vision points at the code it names.

Every scout re-derives the Vision from vision.md, so a cite one line off sends it to the wrong
text. `QUOTED` names, by the path cited, the text its cite's first and last line must hold; a cite whose range
has moved, or a new cite with no text named here, fails.
"""

import re

from testing.paths import REPO

VISION = REPO / "features" / "home" / "docs" / "vision.md"
CITE = re.compile(r"`([\w./-]+\.\w+):(\d+)(?:-(\d+))?`")

QUOTED = {
    ".github/workflows/borders.yml": ("lint-borders.py --hard", "lint-borders.py --hard"),
    "features/jbus/src/jbus/dispatch.py": ("`max_running` is one cap", "pass, in every project."),
    "features/jbus/src/jbus/live.py": ("QUIET_MINUTES = 10", "HUNG_MINUTES = 20"),
}


def cites():
    return [
        (path, int(first), int(last or first))
        for path, first, last in CITE.findall(VISION.read_text())
    ]


def test_each_cite_points_at_the_text_it_names():
    stale = []
    for path, first, last in cites():
        assert path in QUOTED, f"vision.md cites {path}: name the text its lines hold in QUOTED"
        lines = (REPO / path).read_text().splitlines()
        opens, closes = QUOTED[path]
        if not (last <= len(lines) and opens in lines[first - 1] and closes in lines[last - 1]):
            span = f"{first}-{last}" if last != first else f"{first}"
            stale.append(f"{path}:{span} no longer opens on {opens!r} and closes on {closes!r}")
    assert not stale, "\n".join(stale)


def test_each_quoted_text_is_still_cited():
    assert set(QUOTED) == {path for path, _, _ in cites()}
