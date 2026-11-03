"""`python -m jbus.pages [--check]`: build the lists of `features/jbus/docs/jbus/` out of the code.

Run it in this repo's root. It writes the built parts of two pages: the text between
`<!-- built: <part> -->` and the `<!-- built: end -->` after it. Each part is a list, sorted and one
on a line, so that two pull requests that each add to it merge with no conflict. The part `events`
of `features/jbus/docs/jbus/events-and-wakes.md` lists the kinds of event for each level, read from
`wake.LOUDNESS`. The parts `here`, `none` and `piped` of `features/jbus/docs/jbus/the-verbs.md`
list the verbs that `verbs.reads` finds acting on the repo's project, taking no project, and
reading stdin. It leaves the rest of each page, which a person wrote by hand, as it is. A second
run changes nothing.
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

import jbus
from jbus import LEVELS, verbs, wake

EVENTS_PAGE = "features/jbus/docs/jbus/events-and-wakes.md"
VERBS_PAGE = "features/jbus/docs/jbus/the-verbs.md"
PARTS = {EVENTS_PAGE: ("events",), VERBS_PAGE: ("here", "none", "piped")}
PATHS = jbus.__path__
RUN = "uv run python -m jbus.pages"
BUILT = re.compile(
    r"(?P<begin><!-- built: (?P<part>\w+) -->\n)(?P<body>.*?)(?P<end><!-- built: end -->)", re.S
)
HAPPENS = {
    "user": (
        "It is a decision of yours.\nIt is in the log, and the one list carries it to a home "
        "as an item (`jbus.wakes`)."
    ),
    "quiet": (
        "It wakes no thread.\nIt is in the log, which `jbus events` prints and the view shows."
    ),
}


class Refused(Exception):
    """`build` cannot build from the tree: it found a page with no part, or a part with no
    maker."""


def events() -> str:
    """Return what each level does and its kinds, one on a line, as `wake.LOUDNESS` lists them."""
    parts = []
    for level in LEVELS:
        kinds = "".join(
            f"- `{kind}`\n" for kind, at in sorted(wake.LOUDNESS.items()) if at == level
        )
        parts.append(f"`{level}`: {HAPPENS[level]}\n\n{kinds}\n")
    return "".join(parts)


def listed(names: tuple[str, ...]) -> str:
    """Return the verbs, one on a line, as `jbus <verb>`."""
    return "".join(f"- `jbus {name}`\n" for name in names)


def build(root: Path) -> dict[str, str]:
    """Return each page that has a built part, by its path, with that part built again from
    the code, the verbs from the modules under `PATHS`."""
    said = verbs.reads(PATHS)
    makers = {
        "events": events,
        "here": lambda: listed(said.here),
        "none": lambda: listed(said.none),
        "piped": lambda: listed(said.piped),
    }
    built = {}
    for name, parts in PARTS.items():
        try:
            text = (root / name).read_text(encoding="utf-8")
        except OSError as error:
            raise Refused(f"{name}: {error.strerror}, run this in the repo's root") from error
        there = {one["part"] for one in BUILT.finditer(text)}
        for part in parts:
            if part not in there:
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
