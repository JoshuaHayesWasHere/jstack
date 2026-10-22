"""A context pack's notes read as data: each note's sources, and the citations in them.

A context pack is a folder in the repo it is about, `docs/context/`. It holds `sources.md`, an
`INDEX.md` of one line per note, and `notes/`, with one note for each question, in the four
parts of `features/expert/templates/expert-answer.md`. `features/jpack/docs/context.md` says
who writes one and how it is read.

A note's sources are the list items (`- ` or `* `) under its `Sources` heading. Each item
takes in the lines that continue it, up to the next blank line, item or heading, as the lint
`lint-notes.sh` reads them. A source writes a citation as `` `path:line` at <sha> `` or
`` `path:first-last` at <sha> ``, with the commit in backticks or bare, and at most one word
between `at` and it, as in `` at Winnifred `3f9c2ab` ``. The first double-quoted fragment
after a citation, before the next one, is what the cited lines say, and `verify` reports a
citation with none. A source with a date and no commit (a doc, a link, a command that was run)
has no citation: the lint requires it to name a revision, and nothing here reads it. `verify`
also reports a source that names a commit and has no citation, since nothing could check what
it claims.

The lint is the one shell copy, `lint-notes.sh` beside this file, for an expert's folder and
for a pack. It checks that every note has a line in the index and lists at least one source,
and that each source names the revision it was read at. The index is `notes/INDEX.md` in an
expert's folder, and `INDEX.md` at the top of a pack, where it is at most 40 lines that are
not blank. A revision is a date written YYYY-MM-DD, or a commit id of 7 to 40 characters from
0-9 and a-f with a digit among them, inside backticks or as the word right after `at`. It is a
word of its own, outside double quotes, so a date or a number inside a path or a link is none,
and neither is a bare number. A source has a revision when it names one, or when the note names
one for all its sources, on a line between its title and the first of its four parts. The lint
prints one line for each thing wrong, `<note>: <what>`, and exits 1. A folder in order prints
nothing and exits 0. A folder with no `notes/` exits 2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

LINT = Path(__file__).parent / "lint-notes.sh"
PARTS = ("Answer", "Sources", "Confidence", "Not checked")
_CITED = re.compile(
    r"`(?P<path>[^`\s:]+):(?P<first>\d+)(?:-(?P<last>\d+))?` at "
    r"(?:[^\s`]+ )?`?(?P<sha>[0-9a-f]{7,40})(?![0-9A-Za-z])`?"
)
_QUOTE = re.compile(r'"([^"]+)"')
_COMMIT = re.compile(r"(?:`|\bat )(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}(?![0-9A-Za-z])")


class Refused(Exception):
    """A folder or a repo that jpack cannot read as a pack: the command exits 2."""


@dataclass(frozen=True)
class Citation:
    note: str
    path: str
    first: int
    last: int
    sha: str
    quote: str

    def __str__(self) -> str:
        lines = str(self.first) if self.first == self.last else f"{self.first}-{self.last}"
        return f"`{self.path}:{lines}` at {self.sha}"


def sources(text: str) -> list[str]:
    """The note's sources, each one item, with the lines that continue it joined to it by
    a space."""
    found: list[str] = []
    item: list[str] = []
    inside = fenced = False

    def close() -> None:
        if item:
            found.append(" ".join(item))
            item.clear()

    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        part = line.lstrip("#").strip()
        if part in PARTS:
            close()
            inside = part == "Sources"
        elif line.startswith("#"):
            close()
            inside = False
        elif not inside:
            continue
        elif line[:2] in ("- ", "* "):
            close()
            item.append(line[2:].strip())
        elif not line.strip():
            close()
        elif item:
            item.append(line.strip())
    close()
    return found


def citations(note: str, text: str) -> list[Citation]:
    """Every citation in the note's sources, in order, each with the quote that follows it."""
    found = []
    for item in sources(text):
        matches = list(_CITED.finditer(item))
        for at, match in enumerate(matches):
            end = matches[at + 1].start() if at + 1 < len(matches) else len(item)
            quoted = _QUOTE.search(item, match.end(), end)
            first = int(match["first"])
            found.append(
                Citation(
                    note=note,
                    path=match["path"],
                    first=first,
                    last=int(match["last"] or first),
                    sha=match["sha"],
                    quote=quoted[1] if quoted else "",
                )
            )
    return found


def uncited(text: str) -> list[str]:
    """The sources that name a commit and cite no line the verifier can check: a claim pinned
    to a commit that nothing reads."""
    return [item for item in sources(text) if _COMMIT.search(item) and not _CITED.search(item)]


def notes(pack: Path) -> dict[str, str]:
    """Each note of the pack by its file name, with its text, except the index."""
    folder = pack / "notes"
    if not folder.is_dir():
        raise Refused(f"jpack: {pack} has no notes folder")
    return {
        path.name: path.read_text(errors="replace")
        for path in sorted(folder.glob("*.md"))
        if path.name != "INDEX.md"
    }


def said(text: str) -> str:
    """The text with each run of white space made one space, so a quote that a note wraps
    over lines still matches."""
    return " ".join(text.split())
