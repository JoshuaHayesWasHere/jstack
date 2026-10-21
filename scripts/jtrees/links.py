"""The relative links of a Markdown file that is copied somewhere else in the tree.

A link is read from where its file sits in the repo. A target the copy holds becomes the link
from the file's place in the copy to the target's; a repo file or folder the copy leaves out
becomes its GitHub address; anything else dangles, and is a fault. A link in fenced or inline
code is no link, and an address with a scheme, or an anchor alone, is left as it is.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

LINK = re.compile(r"(?P<head>!?\[[^\]\n]*\]\()(?P<href>[^)\s]+)(?P<tail>(?:\s+\"[^\"\n]*\")?\))")
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
    """Where the copy puts the folder `target`, when it puts a file under it at the same depth."""
    for source, copied in placed.items():
        if source.startswith(f"{target}/"):
            rest = source[len(target) :]
            if copied.endswith(rest):
                return copied[: -len(rest)]
    return None


def rewrite(
    text: str, at: str, copy_at: str, placed: dict[str, str], root: Path, base: str
) -> tuple[str, list[str]]:
    """`text`, the file at repo path `at` copied to `copy_at`, with each relative link pointed
    at the copy's target or at `base`/{blob|tree}/main/<path>; and each link that dangles, as
    the href it has."""
    dangling: list[str] = []

    def one(match: re.Match[str]) -> str:
        href = match["href"]
        if href.startswith(("#", "<")) or SCHEME.match(href):
            return match[0]
        found = _target(href, at)
        if found is None:
            dangling.append(href)
            return match[0]
        target, anchor = found
        suffix = f"#{anchor}" if anchor else ""
        copied = placed.get(target) or _folder(target, placed)
        if copied is not None:
            if _target(href, copy_at) == (copied, anchor):
                return match[0]
            moved = posixpath.relpath(copied, posixpath.dirname(copy_at) or ".")
            return f"{match['head']}{moved}{suffix}{match['tail']}"
        if (root / target).is_file():
            return f"{match['head']}{base}/blob/main/{target}{suffix}{match['tail']}"
        if (root / target).is_dir():
            return f"{match['head']}{base}/tree/main/{target}{suffix}{match['tail']}"
        dangling.append(href)
        return match[0]

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
        spans = line.split("`")
        spans[::2] = [LINK.sub(one, span) for span in spans[::2]]
        lines.append("`".join(spans))
    return "".join(lines), dangling
