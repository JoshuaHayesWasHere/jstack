"""`jbus forget [--dir] <path>...`: delete the files a skill's step names, and nothing else.

Claude Code asks the user before it runs a command that removes files, even in full access, so a
step a thread runs holds no `rm` (`features/repo-guards/tests/test_blocks_ask_nothing.py`). A
step that clears a file of the homes' state or of the repo's git directory calls this verb.

It deletes a path only when the path is inside the homes' state, `JBUS_HOME_DIR` or
`~/.local/state/home`, or inside the git directory of the repo it runs in. The parent of each
path is resolved, so a link or a `..` cannot lead it out of those. It checks every path before it
deletes any: one that is outside is refused with a line that names it, nothing is deleted, and
the exit is 2. A directory is refused too, but with `--dir`, which removes it when it is empty. A
path that is not there is no error, as with `rm -f`. It prints each path it removed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import jbus
from jbus import verbs

REFUSED = 2


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("paths", nargs="+", metavar="path", help="a file to delete")
    parser.add_argument(
        "--dir", action="store_true", help="also remove a path that is an empty directory"
    )


def roots() -> list[Path]:
    """The homes' state, and the git directories of the repo this runs in, resolved."""
    home = os.environ.get("JBUS_HOME_DIR") or Path.home() / ".local" / "state" / "home"
    found = [Path(os.path.realpath(home))]
    asked = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    if asked.returncode == 0:
        found += [Path(os.path.realpath(line)) for line in asked.stdout.splitlines() if line]
    return found


def placed(given: str) -> Path | None:
    """The path with its parent resolved, or None where its last part is no name."""
    path = Path(os.path.abspath(given))
    if path.name in ("", ".", ".."):
        return None
    return Path(os.path.realpath(path.parent)) / path.name


def _run(args: argparse.Namespace, _: jbus.Config) -> int:
    inside = roots()
    refused = []
    for given in args.paths:
        path = placed(given)
        if path is None or not any(path != root and path.is_relative_to(root) for root in inside):
            refused.append(
                f"refused: {given} is not inside the homes' state or this repo's git dir"
            )
        elif path.is_dir() and not path.is_symlink() and not args.dir:
            refused.append(f"refused: {given} is a directory, and only --dir removes one")
    if refused:
        print("\n".join([*refused, "nothing is deleted"]), file=sys.stderr)
        return REFUSED
    failed = False
    for given in args.paths:
        path = placed(given)
        assert path is not None
        try:
            if path.is_dir() and not path.is_symlink():
                path.rmdir()
            else:
                path.unlink()
        except FileNotFoundError:
            continue
        except OSError as error:
            print(f"not removed: {given}: {error.strerror}", file=sys.stderr)
            failed = True
            continue
        print(given)
    return 1 if failed else 0


VERBS = (
    verbs.Verb(
        "forget",
        "delete files of the homes' state or of this repo's git dir, and nothing else",
        _arguments,
        _run,
        config=False,
    ),
)
