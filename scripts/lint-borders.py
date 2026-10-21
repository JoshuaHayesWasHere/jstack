"""Warn where the tree leaves the feature layout: a tracked path with no owner or two, a path a
diff adds outside the layout, and a diff that touches two features with no `cross-cutting`
label. Each warning is a line GitHub reads as an annotation. It exits 0 with warnings, and 1
with them under --hard; 2 when the tree or the base cannot be read. Standard library only,
since CI runs it with no uv sync."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jtrees.crawl import Invalid, borders, crawl, tracked
from jtrees.model import Tree

# Where a new path may go: a feature, the harness copies, the schemas, the repo's scripts, the
# shared test plumbing, and CI.
LAYOUT = ("features/", "harness/", "schemas/", "scripts/", "testing/", ".github/")
# The repo-root files that stay at the root.
INFRA_ROOT = (
    ".gitignore",
    "LICENSE",
    "SECURITY.md",
    "Makefile",
    "pyproject.toml",
    "conftest.py",
    "uv.lock",
    "plugin.json",
    "README.md",
    "skills.json",
)
CROSS = "cross-cutting"


class Refused(Exception):
    """git cannot read the diff from the base."""


def ownership(tree: Tree, paths: list[str]) -> dict[str, list[str]]:
    """Each path with no owner or two, and why."""
    unowned, twice = borders(tree, paths)
    found = {path: ["no owner"] for path in unowned}
    for path, owners in twice.items():
        found[path] = [f"owned twice, by {', '.join(owners[:-1])} and {owners[-1]}"]
    return found


def outside(added: list[str]) -> dict[str, list[str]]:
    """Each added path outside the layout and the root's own files, and why."""
    found = {}
    for path in added:
        if path in INFRA_ROOT or path.startswith(LAYOUT):
            continue
        top, _, rest = path.partition("/")
        where = f"under {top}/" if rest else "at the root"
        found[path] = [f"a new file {where}, outside {', '.join(LAYOUT)} and the root's own files"]
    return found


def features(tree: Tree, changed: list[str], labels: set[str]) -> tuple[str, str] | None:
    """The diff's first changed path and why, when it touches more than one feature."""
    names = {one.name for one in tree.features}
    touched: dict[str, str] = {}
    for path in changed:
        for owner in tree.owners(path):
            if owner in names:
                touched.setdefault(owner, path)
    if len(touched) < 2 or CROSS in labels:
        return None
    named = ", ".join(sorted(touched))
    why = f"the diff touches {len(touched)} features, {named}: split it, or label it {CROSS}"
    return next(iter(touched.values())), why


def annotation(path: str, why: str) -> str:
    """A warning as GitHub reads it, with its property and its message escaped."""

    def escape(text: str, more: bool) -> str:
        text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return text.replace(":", "%3A").replace(",", "%2C") if more else text

    return f"::warning file={escape(path, True)}::{escape(why, False)}"


def diff(root: Path, base: str, only_added: bool) -> list[str]:
    command = ["git", "-C", str(root), "diff", "--name-only", "--no-renames", "-z"]
    command += ["--diff-filter=A"] if only_added else []
    listed = subprocess.run([*command, f"{base}...HEAD"], capture_output=True, text=True)
    if listed.returncode != 0:
        raise Refused(f"lint-borders: git cannot diff from {base}: {listed.stderr.strip()}")
    return [one for one in listed.stdout.split("\0") if one]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lint-borders.py", description=__doc__)
    parser.add_argument("--base", help="the ref the diff rules read the change from")
    parser.add_argument("--labels", default="", help="the pull request's labels, a,b")
    parser.add_argument("--hard", action="store_true", help="exit 1 on any warning")
    args = parser.parse_args(argv)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        print(f"lint-borders: not in a git checkout: {top.stderr.strip()}", file=sys.stderr)
        return 2
    root = Path(top.stdout.strip())
    try:
        tree = crawl(root)
    except Invalid as invalid:
        print("\n".join(f"lint-borders: {fault}" for fault in invalid.faults), file=sys.stderr)
        return 2
    found = ownership(tree, tracked(root))
    lines = []
    try:
        if args.base:
            for path, whys in outside(diff(root, args.base, only_added=True)).items():
                found[path] = found.get(path, []) + whys
            labels = {one.strip() for one in args.labels.split(",")}
            crossing = features(tree, diff(root, args.base, only_added=False), labels)
            lines += [annotation(*crossing)] if crossing else []
    except Refused as refused:
        print(refused, file=sys.stderr)
        return 2
    lines = [annotation(path, "; ".join(whys)) for path, whys in sorted(found.items())] + lines
    print("\n".join(lines), end="\n" if lines else "")
    return 1 if args.hard and lines else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
