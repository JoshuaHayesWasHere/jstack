"""Whether a pull request's change to a fork's `packaging/` folder (`jbriefs.proved.FORK_FILE`)
changes the fork's tests alone, and so none of the code they run.

A fork's tests are inside its patches, so the proof block runs them over the base's series and
over the head's (`features/crew/templates/proved.sh`). Where the change adds or edits only patches
that touch the fork's test files, the base's series runs the same code as the head's, and the
tests pass there as they do at the head: a base run that passes proves nothing wrong. jmerge then
does not hold the pull request on it (`ready.changed_code`). Any other change of the folder is
code: a patch that touches any other file, a binary one, a patch removed, a series reordered, and
a `PKGBUILD` changed outside its series, its checksums, `pkgver` and `pkgrel`, its `_tag` above
all."""

from __future__ import annotations

import functools
import re
import subprocess
from collections.abc import Callable
from fnmatch import fnmatchcase

TEST = re.compile(r"\.test\.[cm]?[jt]sx?$")
"""A fork's test file, as the proof block finds them in a patch."""
PROSE = "*.md"
"""The one other kind of file a patch may touch and still change no code: a fork's `package.json`,
`tsconfig.json` and build configs are code there, unlike this repo's config."""
PKGBUILD = "PKGBUILD"

_TOUCHED = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)
_BINARY = re.compile(r"^(?:GIT binary patch|Binary files )", re.MULTILINE)
_SERIES = re.compile(r"^_patches=\((?P<names>[^)]*)\)", re.MULTILINE)
_SUMS = re.compile(r"^sha256sums=\([^)]*\)", re.MULTILINE)
_VERSION = re.compile(r"^pkg(?:ver|rel)=.*$", re.MULTILINE)

Show = Callable[[str], str | None]
"""A file's text at one side of the pull request by its path, None where it has none there."""


def tests_alone(patch: str | None) -> bool:
    """Whether a patch touches the fork's test files and docs alone: a text patch with at least
    one file, each a `TEST` or `PROSE`. None, a patch the side does not have, touches nothing."""
    if patch is None:
        return True
    touched = [path for pair in _TOUCHED.findall(patch) for path in pair]
    return (
        bool(touched)
        and not _BINARY.search(patch)
        and all(TEST.search(path) or fnmatchcase(path, PROSE) for path in touched)
    )


def series(pkgbuild: str) -> tuple[str, ...]:
    """The patches a `PKGBUILD` lays over its tag, in order."""
    found = _SERIES.search(pkgbuild)
    return tuple(found["names"].split()) if found else ()


def _rest(pkgbuild: str) -> str:
    """The `PKGBUILD` with its series, its checksums and its version lines taken out."""
    return _VERSION.sub("", _SUMS.sub("", _SERIES.sub("", pkgbuild)))


def fork_tests_alone(path: str, base: Show, head: Show) -> bool:
    """Whether a fork file's change from the base to the head changes the fork's tests alone.

    A `.patch` does where it touches tests and docs alone at both sides (`tests_alone`): one the
    pull request adds has no base, and one it deletes is code, since the series loses it. A
    `PKGBUILD` does where it is the same outside its series, checksums and version lines, and
    its series, with each patch that touches tests alone at its side taken out, is the same list
    in the same order. Any other file is code."""
    name = path.rsplit("/", 1)[-1]
    if path.endswith(".patch"):
        at_head = head(path)
        return at_head is not None and tests_alone(at_head) and tests_alone(base(path))
    if name != PKGBUILD:
        return False
    before, after = base(path), head(path)
    if before is None or after is None or _rest(before) != _rest(after):
        return False
    folder = path[: -len(name)]

    def code(names: tuple[str, ...], side: Show) -> list[str]:
        return [one for one in names if not tests_alone(side(folder + one) or "")]

    return code(series(before), base) == code(series(after), head)


def _show(root: str, *command: str) -> str | None:
    said = subprocess.run(["git", "-C", root, *command], capture_output=True, text=True)
    return said.stdout if said.returncode == 0 else None


def in_repo(root: str, on: str, head: str) -> Callable[[str], bool]:
    """`fork_tests_alone` of a path in the repo at `root`, from the merge-base of `on` and `head`
    to `head`, as `jbriefs.proved.prose_in` reads a `.py` file. git is asked only for the paths
    asked of, and with no merge-base every path is code."""

    @functools.cache
    def base() -> str:
        return (_show(root, "merge-base", on, head) or "").strip()

    def alone(path: str) -> bool:
        if not base():
            return False
        return fork_tests_alone(
            path,
            lambda at: _show(root, "show", f"{base()}:{at}"),
            lambda at: _show(root, "show", f"{head}:{at}"),
        )

    return alone
