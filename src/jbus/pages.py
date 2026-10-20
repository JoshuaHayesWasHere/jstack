"""`python -m jbus.pages [--check]`: the index of `docs/jbus.md` and the event table, from the tree.

Run in this repo's root, it writes the built parts of two pages: the text between
`<!-- built: <part> -->` and the `<!-- built: end -->` after it. `pages`, in `docs/jbus.md`, is
one line a page of `docs/jbus/`, `- [<heading>](jbus/<file>)`, the heading being the page's
first line, `# <heading>`. `events`, in `docs/jbus/events-and-the-webhook.md`, is the table of
the kinds of event, one row a level, its kinds sorted, read off `wake.LOUDNESS`. The rest of
each page is hand-written and is left as it is. A second run changes nothing.

With `--check` it writes nothing, says whether a committed page is behind the tree, and exits
1 when one is.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from jbus import LEVELS, wake

INDEX = "docs/jbus.md"
FOLDER = "docs/jbus"
EVENTS_PAGE = f"{FOLDER}/events-and-the-webhook.md"
RUN = "uv run python -m jbus.pages"
BUILT = re.compile(
    r"(?P<begin><!-- built: (?P<part>\w+) -->\n)(?P<body>.*?)(?P<end><!-- built: end -->)", re.S
)
HEADING = re.compile(r"\A# (.+)\n")
HAPPENS = {
    "user": (
        "It starts a POST. The event has `say`, the line for the chat, which begins with the "
        "project's name, but for a `sign-in`, which is the machine's. The top-level `say` holds "
        "those lines in order."
    ),
    "quiet": "It is never posted. It is in the log, which `jbus events` prints and the view shows.",
}


class Refused(Exception):
    """The tree cannot be built from: a page with no heading, a part with no maker."""


def index(root: Path) -> str:
    """One line a page of the folder, in the order of its file names."""
    lines = []
    for path in sorted((root / FOLDER).glob("*.md")):
        found = HEADING.match(path.read_text(encoding="utf-8"))
        if not found:
            raise Refused(f"{FOLDER}/{path.name}: its first line is not `# <heading>`")
        lines.append(f"- [{found[1]}](jbus/{path.name})\n")
    return "".join(lines)


def events() -> str:
    """The table of the kinds of event, one row a level, as `wake.LOUDNESS` has them."""
    rows = ["| `loud` | Kinds | What happens |\n", "|---|---|---|\n"]
    for level in LEVELS:
        kinds = ", ".join(f"`{kind}`" for kind, at in sorted(wake.LOUDNESS.items()) if at == level)
        rows.append(f"| `{level}` | {kinds} | {HAPPENS[level]} |\n")
    return "".join(rows)


def build(root: Path) -> dict[str, str]:
    """Each page with a built part, by its path, made again from the tree at `root`."""
    makers = {"pages": lambda: index(root), "events": events}
    built = {}
    for name, part in ((INDEX, "pages"), (EVENTS_PAGE, "events")):
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
