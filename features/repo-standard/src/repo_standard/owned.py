"""Which of a repo's files a version of the standard owns, and that version's copy of each.

A repo starts as a copy of `features/repo-standard/skeleton/` with its adapters' folders over it
(`features/repo-standard/docs/skeleton.md`). From then on each file it took is one of two kinds,
set by one rule over the file's path in the folder it came from, `RULES`:

- `owned`: the version's. The repo keeps it equal to the copy at the tag it pins, and
  `repo-standard upgrade` writes the next version's copy over it. From the skeleton these are the
  `Makefile`, `.github/workflows/*.yml`, `schemas/**` and `scripts/**`, and from an adapter its
  `scripts/**`.
- `seeded`: written once, and the repo's from then on, such as `.repo-standard.yml`, `.gitignore`,
  the setup action and the example feature.

A path the rule does not place has no kind, and the test of the rule fails on it, so a file added
to the skeleton or an adapter is placed when it is added.

A repo's adapters are its `stacks:` adapters, or, with no `stacks:`, each adapter whose scripts
(`repo_standard.adapters.COMMANDS`) the repo holds. A repo of several stacks takes no `stack.mk`,
since its Makefile hands the targets to the standard's driver.

A repo's `.repo-standard.yml` may keep an owned file as its own under `local:`, with a reason, and
neither the drift rule nor `upgrade` touches it. A repo's own make targets go in `local.mk`, which
the skeleton's Makefile includes when it is there, so they need no edit of the owned Makefile.
"""

from __future__ import annotations

import os
import re
import subprocess
from enum import Enum
from pathlib import Path

from repo_standard import TAG, VERSION
from repo_standard.adapters import COMMANDS
from repo_standard.config import Config
from repo_standard.tree import Unreadable, matches, tracked

CLONE_SECONDS = 60
STACK_MK = "scripts/stack.mk"
CALLER = ".github/workflows/check.yml"
LABEL = re.compile(r"^(\s*(?:runner|runs-on):[ \t]*)(\S.*)$", re.M)


class Kind(Enum):
    OWNED = "owned"
    SEEDED = "seeded"


RULES: dict[str, tuple[tuple[str, Kind], ...]] = {
    "skeleton": (
        ("Makefile", Kind.OWNED),
        (".github/workflows/*.yml", Kind.OWNED),
        ("schemas/**", Kind.OWNED),
        ("scripts/**", Kind.OWNED),
        (".repo-standard.yml", Kind.SEEDED),
        (".gitignore", Kind.SEEDED),
        ("README.md", Kind.SEEDED),
        (".github/actions/setup/action.yml", Kind.SEEDED),
        ("features/**", Kind.SEEDED),
    ),
    "adapter": (
        ("scripts/**", Kind.OWNED),
        (".repo-standard.yml", Kind.SEEDED),
        (".github/actions/setup/action.yml", Kind.SEEDED),
        ("features/**", Kind.SEEDED),
        ("pyproject.toml", Kind.SEEDED),
        ("uv.lock", Kind.SEEDED),
        ("conftest.py", Kind.SEEDED),
    ),
}
"""For the skeleton and for any adapter, each glob over a path from the folder's root, and the
kind of the files it matches. The first glob that matches a path sets its kind."""


def kind(origin: str, path: str) -> Kind | None:
    """The kind of a file at `path` in the skeleton (`origin` "skeleton") or in an adapter."""
    return next((one for glob, one in RULES[origin] if matches(path, (glob,))), None)


def adapters(config: Config, paths: list[str]) -> tuple[str, ...]:
    """The adapters the repo copied: its stacks', or each whose scripts it holds."""
    if config.stacks:
        return tuple(sorted({stack.adapter for stack in config.stacks.values()}))
    held = set(paths)
    return tuple(name for name, one in COMMANDS.items() if set(one.scripts) <= held)


def folders(feature: Path, config: Config, paths: list[str]) -> list[tuple[str, Path]]:
    """The skeleton and each of the repo's adapters, in the order a repo copies them."""
    found = [("skeleton", feature / "skeleton")]
    return found + [("adapter", feature / "adapters" / name) for name in adapters(config, paths)]


def files(feature: Path, config: Config, paths: list[str], want: Kind) -> dict[str, Path]:
    """Each file of the kind `want` the repo takes from the version at `feature`, as a path from
    the repo's root, and the version's copy of it. A later folder's copy wins, as in the copy."""
    found = {}
    for origin, folder in folders(feature, config, paths):
        for path in tracked(folder):
            if kind(origin, path) is want and not (config.stacks and path == STACK_MK):
                found[path] = folder / path
    return found


def masked(path: str, text: str) -> str:
    """The text as the drift rule compares it: in the caller's check.yml, the runner's label is
    the repo's own, so the values of `runner:` and `runs-on:` read as one placeholder."""
    return LABEL.sub(r"\1<label>", text) if path == CALLER else text


def carried(path: str, mine: str, theirs: str) -> str:
    """The version's copy `theirs`, with the runner's labels of the repo's copy `mine` kept."""
    if path != CALLER:
        return theirs
    labels = iter(found[2] for found in LABEL.finditer(mine))
    return LABEL.sub(lambda found: found[1] + next(labels, found[2]), theirs)


def tree(version: int, root: Path, upstream: str | None) -> Path:
    """`features/repo-standard` at the tag of `version`.

    It is this tool's own tree when the tool is that version and its tree holds the skeleton, as
    the clone the Makefile and the shared check make does. Otherwise it is the clone in the
    repo's `.cache/`, where the Makefile puts it, cloned from `upstream` when it is not there."""
    own = Path(__file__).resolve().parents[2]
    if version == VERSION and (own / "skeleton").is_dir():
        return own
    clone = root / ".cache" / f"{TAG}{version}"
    if not clone.is_dir():
        if not upstream:
            raise Unreadable(f"no copy of {TAG}{version} here, and no upstream to clone it from")
        command = ["git", "-c", "advice.detachedHead=false", "clone", "-q", "--depth", "1"]
        command += ["--branch", f"{TAG}{version}", upstream, str(clone)]
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            cloned = subprocess.run(
                command, capture_output=True, text=True, env=env, timeout=CLONE_SECONDS
            )
        except subprocess.TimeoutExpired as error:
            raise Unreadable(f"git clone {upstream} took over {CLONE_SECONDS}s") from error
        if cloned.returncode != 0:
            raise Unreadable(f"git clone {upstream} at {TAG}{version}: {cloned.stderr.strip()}")
    feature = clone / "features" / "repo-standard"
    if not (feature / "skeleton").is_dir():
        raise Unreadable(f"{clone} holds no features/repo-standard/skeleton to compare with")
    return feature
