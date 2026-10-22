"""`python -m jdrift.explained [--check]`: the cards of
`features/jdrift/docs/jstack-explained.html`, from the tree.

Run in this repo's root, it reads one card line from each skill's `SKILL.md`, each playbook
and each principle's `SKILL.md`, and writes the page's built parts from them: the text between each
`<!-- built: <kind> <cards or links>, <tile> -->` and the `<!-- built: end -->` after it. The rest
of the page is hand-written and is left as it is. A second run changes nothing.

A card line names its tile, its place in that tile, and its words:

    skill      card: "<tile> | <place> | <what it does> | <when to reach for it> | <who>"
    playbook   <!-- card: <tile> | <place> | <what it is for> -->
    principle  <!-- card: <tile> | <place> | <the rule> | <who leans on it> -->

A skill's line is a key of its front matter, in double quotes. Words in backticks are set as
code. `<who>` is a list of chips, `op: the operator; plain: a step of `feature``, which a playbook
may add as a fourth field. A principle's last field is a list too, with no kinds. A skill or a
playbook may end with one more field, `look: scout`, for a card in a role's colour.

With `--check` it writes nothing, says whether the committed page is behind the tree, and exits
1 when it is. No task edits the page: the docs sweep runs this, last.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from jdrift import Refused

PAGE = "features/jdrift/docs/jstack-explained.html"
RUN = "uv run python -m jdrift.explained"
BUILT = re.compile(
    r"(?P<begin><!-- built: (?P<kind>\w+) (?P<part>cards|links), (?P<tile>.+?) -->\n)"
    r"(?P<body>.*?)"
    r"(?P<end><!-- built: end -->)",
    re.S,
)
FRONT_MATTER = re.compile(r"\A---\n(.*?)^---$", re.M | re.S)
KEY = re.compile(r"^card: (.*)$", re.M)
COMMENT = re.compile(r"^<!-- card: (.*) -->$", re.M)
CODE = re.compile(r"`([^`]+)`")
CHIPS = ("op", "plain", "model", "cmd", "rev")
LOOK = "look: "
LOOKS = ("scout", "rev")


@dataclass(frozen=True)
class Card:
    kind: str
    name: str
    tile: str
    place: int
    words: tuple[str, ...]
    look: str = ""

    @property
    def id(self) -> str:
        return f"{self.kind}-{self.name}"


def _set(text: str) -> str:
    """`text` as the page has it: escaped, with what is in backticks as code."""
    return CODE.sub(r"<code>\1</code>", html.escape(text, quote=False))


def _listed(text: str) -> list[str]:
    return [item.strip() for item in text.split("; ") if item.strip()]


def _who(text: str) -> str:
    chips = []
    for item in _listed(text):
        kind, colon, said = item.partition(": ")
        if not colon or kind not in CHIPS:
            raise Refused(f"`{item}` is not a chip: one of {', '.join(CHIPS)}, then `: `")
        chips.append(f'<span class="chip {kind}">{_set(said)}</span>')
    return f'<div class="who">{"".join(chips)}</div>'


def _article(card: Card, heading: str, inside: str) -> str:
    look = f" {card.look}" if card.look else ""
    return f'<article class="card{look}" id="{card.id}"><h4>{heading}</h4>{inside}</article>'


def _skill(card: Card) -> str:
    what, when, who = card.words
    inside = f'<p>{_set(what)}</p><p class="when">{_set(when)}</p>{_who(who)}'
    return _article(card, f"/{card.name}", inside)


def _playbook(card: Card) -> str:
    what, *who = card.words
    return _article(card, card.name, f"<p>For: {_set(what)}</p>{_who(*who) if who else ''}")


def _principle(card: Card) -> str:
    rule, leans = card.words
    names = "".join(
        _set(item) if CODE.fullmatch(item) else f"<span>{_set(item)}</span>"
        for item in _listed(leans)
    )
    return (
        f'<div id="{card.id}"><b>{card.name}</b><small>{_set(rule)}</small>'
        f'<div class="leans">{names}</div></div>'
    )


@dataclass(frozen=True)
class Kind:
    files: tuple[str, ...]
    name: Callable[[Path], str]
    line: Callable[[str], str | None]
    form: str
    fields: tuple[int, ...]
    looks: tuple[str, ...]
    card: Callable[[Card], str]


def _key(text: str) -> str | None:
    """A skill's card: the key `card:` of its front matter, which is one string in double quotes."""
    front = FRONT_MATTER.match(text)
    found = KEY.search(front.group(1)) if front else None
    if not found:
        return None
    try:
        line = json.loads(found.group(1))
    except ValueError:
        line = None
    if not isinstance(line, str):
        raise Refused("its card line is not one string in double quotes")
    return line


def _comment(text: str) -> str | None:
    found = COMMENT.search(text)
    return found.group(1) if found else None


KINDS = {
    "skill": Kind(
        ("skills/*/SKILL.md", "features/*/SKILL.md", "features/*/skills/*/SKILL.md"),
        lambda p: p.parent.name,
        _key,
        'card: "<tile> | <place> | <what it does> | <when to reach for it> | <who>"',
        (3,),
        LOOKS,
        _skill,
    ),
    "playbook": Kind(
        ("playbooks/*.md", "features/*/playbooks/*.md", "features/*/skills/*/playbooks/*.md"),
        lambda p: p.stem,
        _comment,
        "<!-- card: <tile> | <place> | <what it is for> -->",
        (1, 2),
        LOOKS,
        _playbook,
    ),
    "principle": Kind(
        ("features/*/skills/principle-*/SKILL.md",),
        lambda p: p.parent.name,
        _comment,
        "<!-- card: <tile> | <place> | <the rule> | <who leans on it> -->",
        (2,),
        (),
        _principle,
    ),
}


def _card(kind: str, path: Path, root: Path) -> Card:
    where, of = path.relative_to(root), KINDS[kind]
    try:
        line = of.line(path.read_text(encoding="utf-8"))
        if line is None:
            in_ = "in its front matter" if of.line is _key else "on a line of its own"
            raise Refused(f"has no card line: give it one {in_}, as `{of.form}`")
        tile, *rest = (field.strip() for field in line.split(" | "))
        look = rest.pop()[len(LOOK) :] if rest and rest[-1].startswith(LOOK) else ""
        if not rest or not rest[0].isdigit() or len(rest) - 1 not in of.fields:
            raise Refused(f"its card line is not a tile, a place and its words, as `{of.form}`")
        if look and look not in of.looks:
            raise Refused(f"`{LOOK}{look}` is not a look: {' or '.join(of.looks) or 'it has none'}")
        card = Card(kind, of.name(path), tile, int(rest[0]), tuple(rest[1:]), look)
        of.card(card)
    except Refused as refused:
        raise Refused(f"{where}: {refused}") from refused
    return card


def _files(kind: str, root: Path) -> list[Path]:
    """The files of `kind` under `root`: a principle is a skill too, and its card is a
    principle's."""
    found = {path for files in KINDS[kind].files for path in root.glob(files)}
    if kind == "skill":
        found -= set(_files("principle", root))
    return sorted(found)


def cards(root: Path) -> list[Card]:
    """Every card the tree asks for, in the order its tile shows it."""
    found = [_card(kind, path, root) for kind in KINDS for path in _files(kind, root)]
    return sorted(found, key=lambda card: (card.place, card.name))


def build(root: Path) -> str:
    """The page at `root` with each built part made again from the tree at `root`."""
    try:
        text = (root / PAGE).read_text(encoding="utf-8")
    except OSError as error:
        raise Refused(f"{PAGE}: {error.strerror}, run this in the repo's root") from error
    every = cards(root)
    shown = set()

    def part(found: re.Match[str]) -> str:
        kind, tile = found["kind"], found["tile"]
        if kind not in KINDS:
            raise Refused(f"{PAGE}: `{found['begin'].strip()}` is not of {', '.join(KINDS)}")
        here = [card for card in every if (card.kind, card.tile) == (kind, tile)]
        if found["part"] == "links":
            body = "".join(f'<a href="#{card.id}">{card.name}</a>' for card in here)
            body += "\n" if here else ""
        else:
            shown.update(here)
            body = "".join(KINDS[kind].card(card) + "\n" for card in here)
        return found["begin"] + body + found["end"]

    built = BUILT.sub(part, text)
    for card in every:
        if card not in shown:
            tiles = sorted({m["tile"] for m in BUILT.finditer(text) if m["kind"] == card.kind})
            raise Refused(
                f"{card.id} names the tile `{card.tile}`, and {PAGE} has no cards of it: "
                f"it has {'; '.join(tiles) or 'none'}"
            )
    return built


def _ids(text: str) -> set[str]:
    kinds = "|".join(KINDS)
    return {
        m[1]
        for part in BUILT.finditer(text)
        for m in re.finditer(rf'id="((?:{kinds})-[^"]+)"', part["body"])
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m jdrift.explained", description=(__doc__ or "").split("\n\n")[1]
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing: say whether the page is behind the tree, and exit 1 when it is",
    )
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        built = build(root)
    except Refused as refused:
        print(f"jdrift.explained: {refused}", file=sys.stderr)
        return 2
    page = root / PAGE
    text = page.read_text(encoding="utf-8")
    if built == text:
        print(f"current: {PAGE} has what the tree has")
        return 0
    if not args.check:
        page.write_text(built, encoding="utf-8")
        print(f"built: {PAGE}")
        return 0
    lacks, gone = sorted(_ids(built) - _ids(text)), sorted(_ids(text) - _ids(built))
    why = "; ".join(
        f"{label} {', '.join(names)}"
        for label, names in (("lacks", lacks), ("still has", gone))
        if names
    )
    print(f"behind: {PAGE} {why or 'has other words than the tree'}: run {RUN}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
