"""`python -m jbus.pages [--check]`: build the event table of `features/jbus/docs/jbus/`
out of the code.

Run it in this repo's root. It writes the built part of one page,
`features/jbus/docs/jbus/events-and-wakes.md`: the text between `<!-- built: events -->`
and the `<!-- built: end -->` after it. That part is the table of the kinds of event, one row
for each level, with the level's kinds sorted, read from `wake.LOUDNESS`. It leaves the rest of
the page, which a person wrote by hand, as it is. A second run changes nothing.
`scripts/generate-jstack-trees.py` writes the index of `features/jbus/docs/jbus.md` from the
tree, and needs no import of jbus.

With `--check` it writes nothing, says whether a committed page is behind the tree, and exits
1 when a page is behind.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from jbus import LEVELS, wake

EVENTS_PAGE = "features/jbus/docs/jbus/events-and-wakes.md"
RUN = "uv run python -m jbus.pages"
BUILT = re.compile(
    r"(?P<begin><!-- built: (?P<part>\w+) -->\n)(?P<body>.*?)(?P<end><!-- built: end -->)", re.S
)
HAPPENS = {
    "user": (
        "It starts a wake of the home thread. The event has `say`, the line for the chat, which "
        "begins with the project's name, but for a `sign-in`, which is the machine's. The "
        "top-level `say` holds those lines in order."
    ),
    "quiet": "It wakes no thread. It is in the log, which `jbus events` prints and the view shows.",
}


class Refused(Exception):
    """`build` cannot build from the tree: it found a page with no part, or a part with no
    maker."""


def events() -> str:
    """Return the table of the kinds of event, one row for each level, as `wake.LOUDNESS`
    lists them."""
    rows = ["| `loud` | Kinds | What happens |\n", "|---|---|---|\n"]
    for level in LEVELS:
        kinds = ", ".join(f"`{kind}`" for kind, at in sorted(wake.LOUDNESS.items()) if at == level)
        rows.append(f"| `{level}` | {kinds} | {HAPPENS[level]} |\n")
    return "".join(rows)


def build(root: Path) -> dict[str, str]:
    """Return each page that has a built part, by its path, with that part built again from
    the code."""
    makers = {"events": events}
    built = {}
    for name, part in ((EVENTS_PAGE, "events"),):
        try:
            text = (root / name).read_text(encoding="utf-8")
        except OSError as error:
            raise Refused(f"{name}: {error.strerror}, run this in the repo's root") from error
        if not any(found["part"] == part for found in BUILT.finditer(text)):
            raise Refused(f"{name}: has no `<!-- built: {part} -->` part")

        def fill(found: re.Match[str], name: str = name) -> str:
            if found["part"] not in makers:
                raise Refused(f"{name}: `{found['begin'].strip()}` is not of {', '.join(makers)}")
            return found["begin"] + makers[found["part"]]() + found["end"]

        built[name] = BUILT.sub(fill, text)
    return built


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m jbus.pages", description=(__doc__ or "").split("\n\n")[1]
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing: say whether a page is behind the tree, and exit 1 when one is",
    )
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        built = build(root)
    except Refused as refused:
        print(f"jbus.pages: {refused}", file=sys.stderr)
        return 2
    behind = [name for name, text in built.items() if (root / name).read_text("utf-8") != text]
    if not behind:
        print(f"current: {', '.join(built)} have what the tree has")
        return 0
    if args.check:
        print(f"behind: {', '.join(behind)}: run {RUN}")
        return 1
    for name in behind:
        (root / name).write_text(built[name], encoding="utf-8")
        print(f"built: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
