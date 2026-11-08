"""Size and comment limits from the config's `size` and `comments` parts, for any language.

`size` is a list of rules. A rule's `files` globs, less its `exclude` globs, pick the files, and
none of them grows past `cap` lines unless `over` lists it with its length when the cap was set.
A listed file that is back under the cap, or gone, fails until it leaves the list, so the list
only shrinks.

`comments` picks files the same way, and none of them holds a plain comment. The comment reader
comes from the file's extension: the config's `readers` first, then `lexers.BY_EXTENSION`, and a
file whose extension neither names is refused rather than passed unread. A comment passes when
it is a shebang on the first line, when it starts with one of `allow` (a tool's instruction,
such as `# type:`), or when its file's extension is one of `links` and it holds an `https://`
link, the page that documents the fact it states.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from repo_standard import lexers
from repo_standard.config import Config, Refused
from repo_standard.tree import Fault, chosen

LINK = "https://"


def lengths(root: Path, names: list[str]) -> dict[str, int]:
    return {name: len((root / name).read_text(errors="replace").splitlines()) for name in names}


def sizes(root: Path, config: Config, paths: list[str]) -> list[Fault]:
    faults = []
    for rule in config.part("size"):
        found = lengths(root, chosen(paths, rule.files, rule.exclude))
        faults += [
            Fault(name, None, f"has {length} lines, over {rule.cap}: split it")
            for name, length in found.items()
            if length > rule.cap and name not in rule.over
        ]
        faults += [
            Fault(name, None, f"has {found[name]} lines, under {rule.cap}: take it off `over`")
            if name in found
            else Fault(name, None, "is gone: take it off `over`")
            for name in rule.over
            if found.get(name, 0) <= rule.cap
        ]
    return faults


def comments(root: Path, config: Config, paths: list[str]) -> list[Fault]:
    part = config.part("comments")
    known = {**lexers.BY_EXTENSION, **part.readers}
    faults = []
    for name in chosen(paths, part.files, part.exclude):
        suffix = PurePosixPath(name).suffix
        if suffix not in known:
            raise Refused(f"{name}: no comment reader for {suffix or 'no extension'}: map it")
        read = lexers.READERS[known[suffix]]
        faults += [
            Fault(name, at, f"a plain comment: {comment}")
            for at, comment in read((root / name).read_text(errors="replace"))
            if not comment.startswith(part.allow)
            and not (at == 1 and comment.startswith("#!"))
            and not (suffix in part.links and LINK in comment)
        ]
    return faults
