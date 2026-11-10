"""A crew's worktree, which jbus makes itself before it launches the crew into it.

jbus makes it where T3 Code would have: `<cleanup.worktrees()>/<checkout name>/<slug>`, on a new
branch named for the slug, made with no upstream from the base's commit as `git fetch` just
brought it from origin. In it jbus writes `.claude/settings.json`, from
`jroles.mirror.crew_settings`, and `.claude/.gitignore`, which holds `*` and so keeps both files
out of `git status`. The crew launches with `existing_worktree`, and its reviewer launches into
the same worktree, so both read the file before their first request. Homes and scouts launch in
the main checkout, which has no such file, and keep every tool.

T3 Code's storage cleanup removes a worktree by its thread's `worktreePath` under its own
worktrees folder, whoever made it, so a finished crew's worktree goes as it did when T3 Code
made it.

jbus writes the launch record (`jbus.launches`) once the worktree is made, with the commit it
made the branch at, as `sha`. A launch whose connection dropped before any reply, and that made
no thread, is tried once more (`dispatch.settle_lost`): that retry takes the worktree as it is
(`kept`) where the branch is still at that commit and nothing in it changed, and makes no second
one. Any other branch of the slug's name still stops a launch, as one a pass left when it
stopped between the worktree and the record does.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import jroles
import jroles.mirror
from jbus import cleanup
from jbus.passes import Pass

SETTINGS = Path(".claude") / "settings.json"
IGNORE = Path(".claude") / ".gitignore"


def path(run: Pass, slug: str) -> Path:
    """Return the path of the slug's worktree, the one T3 Code would have made for its branch."""
    return cleanup.worktrees() / run.project.checkout.name / slug.replace("/", "-")


def strategy(run: Pass, slug: str) -> dict[str, str]:
    """Return the `workspaceStrategy` of the crew's launch: the worktree jbus made, on `slug`."""
    return {"type": "existing_worktree", "worktreePath": str(path(run, slug)), "branch": slug}


def kept(run: Pass, slug: str, record: dict[str, Any]) -> str:
    """Return the commit jbus made the branch `slug` at for the launch `record`, a launch to try
    again, where the branch is still checked out at `path` at that commit with nothing changed in
    it, and nothing otherwise."""
    tree, sha = path(run, slug).resolve(), str(record.get("sha") or "")
    listed = run.run("git", "worktree", "list", "--porcelain")
    if record.get("state") != "retry" or not sha or listed.returncode:
        return ""
    for entry in listed.stdout.split("\n\n"):
        parts = (line.partition(" ") for line in entry.splitlines())
        lines = {key: value for key, _, value in parts}
        if Path(lines.get("worktree", "/")).resolve() == tree:
            if lines.get("branch") != f"refs/heads/{slug}" or lines.get("HEAD") != sha:
                return ""
            status = run.run("git", "-C", str(tree), "status", "--porcelain")
            return sha if status.returncode == 0 and not status.stdout.strip() else ""
    return ""


def make(run: Pass, slug: str, base: str, sha: str = "") -> tuple[str, str]:
    """Make the slug's worktree off origin's `base` and write its two files. With `sha`, the
    worktree `kept` found is taken as it is. Return the commit the branch starts at, and nothing,
    or nothing and why no worktree was made; a worktree that failed partway is removed."""
    tree = path(run, slug)
    if not sha:
        run.run("git", "worktree", "prune")
        ref = f"refs/remotes/origin/{base}"
        fetched = run.run("git", "fetch", "-q", "origin", f"+refs/heads/{base}:{ref}")
        if fetched.returncode:
            return "", f"origin's {base} could not be fetched: {fetched.stderr.strip()}"
        sha = run.run("git", "rev-parse", "-q", "--verify", f"{ref}^{{commit}}").stdout.strip()
        tree.parent.mkdir(parents=True, exist_ok=True)
        added = run.run("git", "worktree", "add", "-q", "--no-track", "-b", slug, str(tree), sha)
        if not sha or added.returncode:
            remove(run, slug)
            return "", f"the worktree {tree} could not be made: {added.stderr.strip()}"
    try:
        settings = jroles.mirror.crew_settings(jroles.mirror.Main.of(Path.home()))
    except jroles.Refused as error:
        remove(run, slug)
        return "", f"its settings file could not be made: {error}"
    _write(tree / SETTINGS, json.dumps(settings, indent=2) + "\n")
    _write(tree / IGNORE, "*\n")
    status = run.run("git", "-C", str(tree), "status", "--porcelain")
    if status.returncode or status.stdout.strip():
        remove(run, slug)
        return "", f"the worktree {tree} is not clean once its files are written"
    return sha, ""


def remove(run: Pass, slug: str) -> None:
    """Remove the slug's worktree and its branch, which jbus made and no thread has used."""
    run.run("git", "worktree", "remove", "--force", str(path(run, slug)))
    run.run("git", "branch", "-D", slug)


def _write(at: Path, text: str) -> None:
    at.parent.mkdir(parents=True, exist_ok=True)
    temporary = at.with_name(at.name + ".jbus")
    temporary.write_text(text)
    os.replace(temporary, at)
