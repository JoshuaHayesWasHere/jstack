"""The one entry point: `jdrift [--diff] [--strict] [--upstream URL]`, run as `make pstack-drift`.

Run in this repo, it reads the pin and the map from the pstack section of `THIRD_PARTY.md`,
brings a cache clone of the upstream to its `main`, and prints one line per upstream path the
map names: `same`, `changed` with the commits that changed it, or `gone`. Then one `own` line
per file on the `jstack's own:` line, which has no upstream and so never drifts, and one `new`
line per upstream skill or playbook that the map does not name and `Not taken:` does not list.
It changes nothing in this repo. No model reads anything, and no token is used.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from jdrift import FILE, Pinned, Refused, read_section

URL = "https://github.com/cursor/plugins"
SKILLS = "pstack/skills"
PLAYBOOKS = "pstack/skills/poteto-mode/playbooks"
NUMSTAT_OF_A_BINARY_FILE = "-"


@dataclass(frozen=True)
class Line:
    kind: Literal["same", "changed", "gone", "own", "new"]
    upstream: str
    local: tuple[str, ...] = ()
    added: int = 0
    removed: int = 0
    commits: tuple[str, ...] = ()
    diff: str = ""

    def __str__(self) -> str:
        to = f" -> {', '.join(self.local)}"
        if self.kind == "changed":
            said = "".join(f"; {commit}" for commit in self.commits)
            line = f"changed {self.upstream} +{self.added} -{self.removed}{to}{said}"
            return f"{line}\n{self.diff.rstrip()}" if self.diff else line
        if self.kind == "gone":
            return f"gone {self.upstream}{to}"
        if self.kind == "own":
            return f"own {', '.join(self.local)}"
        return f"{self.kind} {self.upstream}"


DRIFTED = ("changed", "gone", "new")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ("git", "-c", "core.quotePath=false", *args)
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


def _out(cwd: Path, *args: str) -> str:
    ran = _git(cwd, *args)
    if ran.returncode:
        lines = (ran.stderr or ran.stdout).strip().splitlines()
        reason = lines[-1].strip() if lines else f"exit {ran.returncode}"
        raise Refused(f"git {args[0]} failed: {reason}")
    return ran.stdout


def cache() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "jstack" / "cursor-plugins"


def fetch(url: str) -> Path:
    """The cache clone, with `origin/main` at the upstream's `main`. Blobs come when a diff asks."""
    clone = cache()
    if (clone / ".git").is_dir():
        _out(clone, "remote", "set-url", "origin", url)
    else:
        clone.parent.mkdir(parents=True, exist_ok=True)
        _out(clone.parent, "clone", "-q", "--filter=blob:none", url, str(clone))
    _out(clone, "fetch", "-q", "origin", "main")
    return clone


def compare(clone: Path, pinned: Pinned, with_diff: bool) -> tuple[str, list[Line]]:
    main_ = _out(clone, "rev-parse", "origin/main").strip()
    found = _git(clone, "rev-parse", "-q", "--verify", f"{pinned.pin}^{{commit}}")
    pin = found.stdout.strip()
    if found.returncode or _git(clone, "merge-base", "--is-ancestor", pin, main_).returncode:
        raise Refused(f"the pin {pinned.pin[:12]} is not in the history of main upstream")
    span = f"{pin}..{main_}"
    count = _out(clone, "rev-list", "--count", span, "--", "pstack/").strip()
    header = f"pstack {pin[:12]} .. {main_[:12]}: {count} commits touch pstack/"

    there = set(_out(clone, "ls-tree", "-r", "--name-only", main_, "--", "pstack/").splitlines())
    counts = {}
    for row in _out(
        clone, "diff", "--no-renames", "--numstat", pin, main_, "--", "pstack/"
    ).splitlines():
        added, removed, path = row.split("\t", 2)
        counts[path] = (
            0 if added == NUMSTAT_OF_A_BINARY_FILE else int(added),
            0 if removed == NUMSTAT_OF_A_BINARY_FILE else int(removed),
        )

    lines = []
    for upstream, local in pinned.sources.items():
        if upstream not in there:
            lines.append(Line("gone", upstream, local))
        elif upstream in counts:
            added, removed = counts[upstream]
            commits = _out(clone, "log", "--format=%h %s", span, "--", upstream).splitlines()
            diff = (
                _out(clone, "diff", "--no-renames", pin, main_, "--", upstream) if with_diff else ""
            )
            lines.append(Line("changed", upstream, local, added, removed, tuple(commits), diff))
        else:
            lines.append(Line("same", upstream))

    lines.extend(Line("own", "", (local,)) for local in pinned.own)
    for directory in (SKILLS, PLAYBOOKS):
        for entry in _out(clone, "ls-tree", "--name-only", main_, f"{directory}/").splitlines():
            reached = any(u == entry or u.startswith(f"{entry}/") for u in pinned.sources)
            if not reached and entry not in pinned.not_taken:
                lines.append(Line("new", entry))
    return header, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jdrift", description=__doc__.split("\n\n")[1])
    parser.add_argument(
        "--diff", action="store_true", help="the unified diff under each changed line"
    )
    parser.add_argument(
        "--strict", action="store_true", help="exit 1 on a changed, gone or new line"
    )
    parser.add_argument("--upstream", default=URL, metavar="URL", help=f"the repo to clone ({URL})")
    args = parser.parse_args(argv)
    try:
        if shutil.which("git") is None:
            raise Refused("git is not on PATH")
        try:
            text = Path(FILE).read_text(encoding="utf-8")
        except OSError as error:
            raise Refused(f"{FILE}: {error.strerror}, run this in the repo's root") from error
        pinned = read_section(text)
        header, lines = compare(fetch(args.upstream), pinned, args.diff)
    except Refused as refused:
        print(f"jdrift: {refused}", file=sys.stderr)
        return 2
    print(header)
    for line in lines:
        print(line)
    return 1 if args.strict and any(line.kind in DRIFTED for line in lines) else 0
