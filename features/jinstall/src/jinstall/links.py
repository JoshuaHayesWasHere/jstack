"""The relative links of a Markdown file that a harness's layout places somewhere else.

This module reads a link from where its file sits in the source, and each link's target is
one of three cases. When the layout holds the target, the module rewrites the link as a path
from the file's place in the layout to the target's place in the layout. When the target is a
source file or folder that the layout leaves out, the module rewrites the link as the target's
GitHub address. Any other link dangles, and that is a fault.

A link inside fenced or inline code is not a link, but a link whose text is code is still a
link. The module leaves an address with a scheme, or an anchor alone, as it is.
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
    """The repo path and the anchor that a relative `href` in the file at `at` names, or None
    when the href resolves to a path outside the repo."""
    path, _, anchor = href.partition("#")
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(at), path))
    if joined == ".." or joined.startswith("../"):
        return None
    return joined, anchor


def _folder(target: str, placed: dict[str, str]) -> str | None:
    """Where the layout puts folder `target`, when the layout puts a file of that folder at
    the same depth."""
    for source, copied in placed.items():
        if source.startswith(f"{target}/"):
            rest = source[len(target) :]
            if copied.endswith(rest):
                return copied[: -len(rest)]
    return None


def rewrite(
    text: str, at: str, copy_at: str, placed: dict[str, str], root: Path, base: str
) -> tuple[str, list[str]]:
    """`text` and the links in it that dangle, each as its href.

    `text` is the file at source path `at`, placed at `copy_at`. The function rewrites each
    of its relative links to point at the layout's target, or at
    `base`/{blob|tree}/main/<path>."""
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
        """`line` with each link outside a code span rewritten. The function masks the text
        of each span, so a link inside a span does not match and a link around a span still
        matches whole."""
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
