"""`repo-standard upgrade --to N`: move a repo to version N of the standard.

It runs from the tool at `repo-standard-vN`, since only that version's tool reads that version's
config, and it refuses any other N. It reads the version's files from the tool's own tree, or
from the clone in the repo's `.cache/` (`repo_standard.owned.tree`). It then writes:

- the `standard:` line of `.repo-standard.yml`, as `standard: N`;
- every file the version owns (`repo_standard.owned`), as the version's copy, keeping the labels
  of the runner in the caller's `.github/workflows/check.yml`;
- the tag of each workflow's `uses:` of the shared check, as `@repo-standard-vN`, which reaches a
  caller the repo keeps as its own too.

It leaves each `local:` file as it is, and every seeded file, and prints each with why, and each
waiver whose `until` version N reaches. It writes a file only where its text differs, through a
temporary file renamed into place, so a second run, or a run after one that stopped part way,
writes only what is left. It ends with the count of files it wrote.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from repo_standard import TAG, VERSION, owned
from repo_standard.config import NAME, Config, Refused
from repo_standard.rules import SHARED_CHECK, WORKFLOWS

STANDARD_LINE = re.compile(r"^standard:[ \t]*\d+", re.M)
CALLED_TAG = re.compile(rf"@{re.escape(TAG)}\d+")


def _pinned(text: str, to: int) -> str:
    if STANDARD_LINE.search(text):
        return STANDARD_LINE.sub(f"standard: {to}", text, count=1)
    return f"standard: {to}\n{text}"


def _called(text: str, to: int) -> str:
    return SHARED_CHECK.sub(lambda found: CALLED_TAG.sub(f"@{TAG}{to}", found[0]), text)


def _write(path: Path, text: str, mode_from: Path | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
            out.write(text)
        if mode_from is not None:
            shutil.copymode(mode_from, temporary)
        elif path.exists():
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def run(root: Path, config: Config, paths: list[str], to: int, upstream: str | None) -> list[str]:
    """Move the repo at `root` to version `to`, and every line the run prints."""
    if to != VERSION:
        raise Refused(f"this tool is {TAG}{VERSION}: run upgrade from the tool at {TAG}{to}")
    if config.standard is not None and config.standard > to:
        raise Refused(f"{NAME} pins v{config.standard}, past {TAG}{to}: a pin only moves up")
    feature = owned.tree(to, root, upstream)

    def read(path: str) -> str | None:
        try:
            return (root / path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    wanted: dict[str, tuple[str, Path | None]] = {}
    lines = []
    copies = owned.files(feature, config, paths, owned.Kind.OWNED)
    for path, copy in sorted(copies.items()):
        if path in config.local:
            lines.append(f"left {path}: local, {config.local[path] or 'with no reason'}")
            continue
        theirs = copy.read_text(encoding="utf-8")
        wanted[path] = (owned.carried(path, read(path) or theirs, theirs), copy)
    callers = {path for path in paths if path.startswith(WORKFLOWS)} | set(wanted)
    for path in sorted(callers):
        text, mode = wanted.get(path, (read(path), None))
        if text is not None and path.startswith(WORKFLOWS):
            wanted[path] = (_called(text, to), mode)
    wanted[NAME] = (_pinned(read(NAME) or "", to), None)

    wrote = 0
    for path, (text, mode) in sorted(wanted.items()):
        if read(path) != text:
            _write(root / path, text, mode)
            lines.append(f"wrote {path}")
            wrote += 1

    seeded = owned.files(feature, config, paths, owned.Kind.SEEDED)
    for path, copy in sorted(seeded.items()):
        mine = read(path)
        if path != NAME and mine is not None and mine != copy.read_text(encoding="utf-8"):
            lines.append(f"left {path}: seeded, so the repo's own; {TAG}{to}'s copy is {copy}")
    lines += [
        f"left waiver {waiver.rule}: is until {TAG}{waiver.until}: meet the rule and drop it"
        for waiver in config.waivers
        if waiver.until is not None and waiver.until <= to
    ]
    if not owned.adapters(config, paths):
        lines.append("left the adapters' scripts: the repo sets no stacks and holds none of them")
    done = f"{wrote} files written" if wrote else "nothing to write"
    lines.append(f"upgrade to {TAG}{to}: {done}; run `make lint` next")
    return lines
