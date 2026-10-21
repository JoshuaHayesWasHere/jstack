"""The relative links of a Markdown file that a harness's layout places somewhere else.

A link is read from where its file sits in the source. A target the layout holds becomes the
link from the file's place in the layout to the target's; a source file or folder it leaves out
becomes its GitHub address; anything else dangles, and is a fault. A link in fenced or inline
code is no link, though a link whose text is code is one, and an address with a scheme, or an
anchor alone, is left as it is.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

LINK = re.compile(r"(?P<head>!?\[[^\]\n]*\]\()(?P<href>[^)\s]+)(?P<tail>(?:\s+\"[^\"\n]*\")?\))")
CODE = re.compile(r"(?<!`)(`+)(?!`)(?P<code>.*?)(?<!`)\1(?!`)")
FENCE = re.compile(r"^\s*(```|~~~)")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _target(href: str, at: str) -> tuple[str, str] | None:
    """The repo path a relative `href` of the file at `at` names, and its anchor; None for one
    that climbs out of the repo."""
    path, _, anchor = href.partition("#")
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(at), path))
    if joined == ".." or joined.startswith("../"):
        return None
    return joined, anchor


def _folder(target: str, placed: dict[str, str]) -> str | None:
    """Where the layout puts folder `target`, when it puts a file under it at the same depth."""
    for source, copied in placed.items():
        if source.startswith(f"{target}/"):
            rest = source[len(target) :]
            if copied.endswith(rest):
                return copied[: -len(rest)]
    return None


def rewrite(
    text: str, at: str, copy_at: str, placed: dict[str, str], root: Path, base: str
) -> tuple[str, list[str]]:
    """`text`, the file at source path `at` placed at `copy_at`, with each relative link pointed
    at the layout's target or at `base`/{blob|tree}/main/<path>; and each link that dangles, as
    the href it has."""
    dangling: list[str] = []

    def one(head: str, href: str, tail: str) -> str:
        link = f"{head}{href}{tail}"
        if href.startswith(("#", "<")) or SCHEME.match(href):
            return link
        found = _target(href, at)
        if found is None:
            dangling.append(href)
            return link
        target, anchor = found
        suffix = f"#{anchor}" if anchor else ""
        copied = placed.get(target) or _folder(target, placed)
        if copied is not None:
            if _target(href, copy_at) == (copied, anchor):
                return link
            moved = posixpath.relpath(copied, posixpath.dirname(copy_at) or ".")
            return f"{head}{moved}{suffix}{tail}"
        if (root / target).is_file():
            return f"{head}{base}/blob/main/{target}{suffix}{tail}"
        if (root / target).is_dir():
            return f"{head}{base}/tree/main/{target}{suffix}{tail}"
        dangling.append(href)
        return link

    def links(line: str) -> str:
        """`line` with each link outside a code span rewritten: the spans' text is masked,
        so a link inside one is none, and a link around one still matches whole."""
        masked = CODE.sub(lambda span: span[1] + "x" * len(span["code"]) + span[1], line)
        out, last = [], 0
        for match in LINK.finditer(masked):
            head, href, tail = (
                line[match.start(g) : match.end(g)] for g in ("head", "href", "tail")
            )
            out += [line[last : match.start()], one(head, href, tail)]
            last = match.end()
        return "".join(out) + line[last:]

    lines, fenced = [], None
    for line in text.splitlines(keepends=True):
        fence = FENCE.match(line)
        if fence and fenced in (None, fence[1]):
            fenced = None if fenced else fence[1]
            lines.append(line)
            continue
        if fenced:
            lines.append(line)
            continue
        lines.append(links(line))
    return "".join(lines), dangling
