"""The view's colour tokens meet WCAG 2.2 AA in both themes. The tests read the tokens out of
`page.html` itself.

Each token of the page's `:root` is `light-dark(<light>, <dark>)`. Text meets 4.5:1 on every ground
it is set on. A control's border and the focus ring meet 3:1 (SC 1.4.11). Each status (ok, run,
due, missed, held, stacked) is text too: it meets 4.5:1 on every ground and on its own tint, and
ink and ink-2 meet 4.5:1 on every tint. Each status and the first six categorical colours meet 3:1
on every ground as a mark (a bar, a dot, a stripe). The text of the brand button meets 4.5:1 on the
button, as do the brand's text on the ok fill of a merged milestone and the canvas token set as
text on the ink and due tokens (the stopped banner, a count). The test prints the table of every
pair, and `-s` shows it.
"""

import re

from jbus.view import PAGE

THEMES = ("light", "dark")
GROUNDS = ("canvas", "surface", "sunk")
STATUS = ("ok", "run", "due", "missed", "held", "stacked")
TEXT = ("ink", "ink-2", "ink-3", *STATUS)
BOUNDS = ("line", "focus")
MARKS = (*STATUS, *(f"cat-{n}" for n in range(1, 7)))
PAIRS = (
    *((ink, ground, 4.5) for ink in TEXT for ground in GROUNDS),
    *((status, f"{status}-tint", 4.5) for status in STATUS),
    *((ink, f"{status}-tint", 4.5) for ink in ("ink", "ink-2") for status in STATUS),
    *((bound, ground, 3.0) for bound in BOUNDS for ground in GROUNDS),
    *((mark, ground, 3.0) for mark in MARKS for ground in GROUNDS),
    ("on-brand", "brand", 4.5),
    ("on-brand", "ok", 4.5),
    ("canvas", "ink", 4.5),
    ("canvas", "due", 4.5),
)
_TOKEN = re.compile(
    r"--([a-z0-9-]+):\s*light-dark\(\s*(#[0-9a-fA-F]{6})\s*,\s*(#[0-9a-fA-F]{6})\s*\)"
)
_ROOT = re.compile(r"^\s*:root\s*\{(.*?)\}", re.S | re.M)


def tokens(page: str) -> dict[str, dict[str, str]]:
    """Return the tokens of the page's first `:root` block, by theme."""
    block = _ROOT.search(page)
    found = _TOKEN.findall(block[1]) if block else []
    return {theme: {name: pair[at] for name, *pair in found} for at, theme in enumerate(THEMES)}


def luminance(colour: str) -> float:
    def linear(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(int(colour[i : i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(one: str, other: str) -> float:
    high, low = sorted((luminance(one), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def measured(page: str) -> list[tuple[str, str, str, float | None, float]]:
    """Return every pair in both themes: the theme, the two tokens, the ratio (None where a token
    is missing) and what it needs."""
    sets = tokens(page)
    return [
        (
            theme,
            fore,
            back,
            round(ratio(t[fore], t[back]), 2) if {fore, back} <= t.keys() else None,
            need,
        )
        for theme, t in sets.items()
        for fore, back, need in PAIRS
    ]


def failing(rows):
    return [row for row in rows if row[3] is None or row[3] < row[4]]


def test_every_token_pair_meets_its_contrast_in_both_themes():
    rows = measured(PAGE.read_text())
    for theme, fore, back, got, need in rows:
        said = "missing" if got is None else f"{got:5.2f}"
        print(f"{theme:5} {fore:9} on {back:11} {said}  needs {need}")
    assert failing(rows) == []


def test_a_border_under_three_to_one_fails():
    """The check does not pass on anything: the light line of the page before these tokens,
    #d4d4d8, fails on every ground."""
    page = re.sub(
        r"--line: light-dark\(#[0-9A-Fa-f]{6}", "--line: light-dark(#d4d4d8", PAGE.read_text()
    )
    rows = failing(measured(page))
    assert [(row[0], row[1], row[2]) for row in rows] == [("light", "line", g) for g in GROUNDS]
    assert max(row[3] for row in rows) < 1.5


def test_a_page_with_no_tokens_fails():
    assert len(failing(measured(":root { --bg: #fcfcfc; }"))) == 2 * len(PAIRS)
