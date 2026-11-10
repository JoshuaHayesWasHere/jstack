"""A crew's or a scout's worktree, which jbus makes itself before it launches the thread into it.

jbus makes it where T3 Code would have: `<cleanup.worktrees()>/<checkout name>/<slug>`, on a new
branch named for the slug, made with no upstream from the base's commit as `git fetch` just
brought it from origin. In it jbus writes `.claude/settings.json`, from
`jroles.mirror.worktree_settings`, and `.claude/.gitignore`, which holds `*` and so keeps both files
out of `git status`. The crew launches with `existing_worktree`, and its reviewer launches into
the same worktree, so both read the file before their first request. A home launches in the main
checkout, which has no such file, and keeps every tool.

A scout gets a worktree too (`make_scout`), beside a crew's at `scout+<slug>`, a name no slug can
have: detached at the default branch as `git fetch` just brought it, with no branch, since a
scout commits nothing, and with the same two files, the skills listed in full being a scout's.
jbus removes it itself (`remove_scout`) once the scout's Report says `Status: done` and no thread
of the scout is at work (`jbus.scouts`). With no launch record there is no thread in it, so a
launch removes whatever an earlier pass left at the path and makes it again.

A row launched again on its branch (`jbus.dispatch`, a resume) gets the worktree of that branch
(`reopen`): the one still at `path`, as the crew before left it, its uncommitted work too, or a
new one made from the branch, never with `-b`, from origin's copy where only origin has it. A
resume that fails removes only a worktree it made itself, and never the branch.

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
SCOUT = "scout+"
IGNORE = Path(".claude") / ".gitignore"


def path(run: Pass, slug: str) -> Path:
    """Return the path of the slug's worktree, the one T3 Code would have made for its branch."""
    return cleanup.worktrees() / run.project.checkout.name / slug.replace("/", "-")


def holding(run: Pass, directory: Path) -> str:
    """Return the slug whose crew's or scout's worktree holds `directory`, at its top or in a
    folder of it, or nothing for a directory in no such worktree."""
    try:
        parts = directory.resolve().relative_to(path(run, "").resolve()).parts
    except ValueError:
        return ""
    return parts[0].removeprefix(SCOUT) if parts else ""


def scout_path(run: Pass, slug: str) -> Path:
    """Return the path of the scout `slug`'s worktree, beside the crews'."""
    return cleanup.worktrees() / run.project.checkout.name / f"{SCOUT}{slug}"


def scout_strategy(run: Pass, slug: str) -> dict[str, str]:
    """Return the `workspaceStrategy` of the scout's launch: the detached worktree jbus made."""
    return {"type": "existing_worktree", "worktreePath": str(scout_path(run, slug))}


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
        sha, why = _fetched(run, base)
        if why:
            return "", why
        tree.parent.mkdir(parents=True, exist_ok=True)
        added = run.run("git", "worktree", "add", "-q", "--no-track", "-b", slug, str(tree), sha)
        if added.returncode:
            remove(run, slug)
            return "", f"the worktree {tree} could not be made: {added.stderr.strip()}"
    why = _fill(run, tree, "crew")
    if why:
        remove(run, slug)
        return "", why
    return sha, ""


def reopen(run: Pass, slug: str) -> tuple[str, str]:
    """Give a resumed row the worktree of its branch `slug`, at `path`: the one there, or a new
    one made from the branch. Write its two files, and return the commit the branch is at, and
    nothing, or nothing and why not. A worktree of the branch elsewhere is why not."""
    tree = path(run, slug).resolve()
    run.run("git", "worktree", "prune")
    listed = run.run("git", "worktree", "list", "--porcelain")
    if listed.returncode:
        return "", f"git could not list the worktrees: {listed.stderr.strip()}"
    there = ""
    for entry in listed.stdout.split("\n\n"):
        parts = (line.partition(" ") for line in entry.splitlines())
        lines = {key: value for key, _, value in parts}
        if lines.get("branch") == f"refs/heads/{slug}":
            there = lines.get("worktree", "")
    made = False
    if there and Path(there).resolve() != tree:
        return "", f"the branch {slug} is checked out at {there}, not at {tree}"
    if not there:
        if tree.exists():
            return "", f"{tree} is there and is no worktree of the branch {slug}"
        ref = f"refs/remotes/origin/{slug}"
        run.run("git", "fetch", "-q", "origin", f"+refs/heads/{slug}:{ref}")
        known = (f"refs/heads/{slug}", ref)
        if all(run.run("git", "rev-parse", "-q", "--verify", one).returncode for one in known):
            return "", f"the branch {slug} is neither here nor on origin"
        tree.parent.mkdir(parents=True, exist_ok=True)
        added = run.run("git", "worktree", "add", "-q", str(tree), slug)
        if added.returncode:
            return "", f"the worktree {tree} could not be made: {added.stderr.strip()}"
        made = True
    why = _fill(run, tree, "crew", clean=False)
    head = run.run("git", "-C", str(tree), "rev-parse", "HEAD").stdout.strip()
    if why or not head:
        if made:
            run.run("git", "worktree", "remove", "--force", str(tree))
        return "", why or f"the worktree {tree} names no commit"
    return head, ""


def make_scout(run: Pass, slug: str, base: str) -> tuple[str, str]:
    """Make the scout's worktree, detached at origin's `base`, and write its two files, in place
    of any an earlier pass left. Return the commit it is at, and nothing, or nothing and why no
    worktree was made; a worktree that failed partway is removed."""
    tree = scout_path(run, slug)
    remove_scout(run, slug)
    sha, why = _fetched(run, base)
    if why:
        return "", why
    tree.parent.mkdir(parents=True, exist_ok=True)
    added = run.run("git", "worktree", "add", "-q", "--detach", str(tree), sha)
    why = (
        f"the worktree {tree} could not be made: {added.stderr.strip()}" if added.returncode else ""
    )
    why = why or _fill(run, tree, "scout")
    if why:
        remove_scout(run, slug)
        return "", why
    return sha, ""


def remove(run: Pass, slug: str) -> None:
    """Remove the slug's worktree and its branch, which jbus made and no thread has used."""
    run.run("git", "worktree", "remove", "--force", str(path(run, slug)))
    run.run("git", "branch", "-D", slug)


def remove_scout(run: Pass, slug: str) -> None:
    """Remove the scout's worktree, and forget it where its folder is already gone."""
    run.run("git", "worktree", "remove", "--force", str(scout_path(run, slug)))
    run.run("git", "worktree", "prune")


def scouts(run: Pass) -> list[str]:
    """Return the slug of each scout's worktree there is a folder for."""
    trees = scout_path(run, "").parent.glob(f"{SCOUT}*")
    return sorted(tree.name.removeprefix(SCOUT) for tree in trees if tree.is_dir())


def _fetched(run: Pass, base: str) -> tuple[str, str]:
    """Fetch origin's `base` and return its commit, and nothing, or nothing and why not."""
    run.run("git", "worktree", "prune")
    ref = f"refs/remotes/origin/{base}"
    fetched = run.run("git", "fetch", "-q", "origin", f"+refs/heads/{base}:{ref}")
    if fetched.returncode:
        return "", f"origin's {base} could not be fetched: {fetched.stderr.strip()}"
    sha = run.run("git", "rev-parse", "-q", "--verify", f"{ref}^{{commit}}").stdout.strip()
    return (sha, "") if sha else ("", f"origin's {base} names no commit")


def _fill(run: Pass, tree: Path, role: str, *, clean: bool = True) -> str:
    """Write the role's two files in `tree`, and return why the worktree is not fit to launch
    into, or nothing. With `clean`, a worktree with changes is not fit: a resumed one keeps the
    work its crew left."""
    try:
        settings = jroles.mirror.worktree_settings(jroles.mirror.Main.of(Path.home()), role)
    except jroles.Refused as error:
        return f"its settings file could not be made: {error}"
    _write(tree / SETTINGS, json.dumps(settings, indent=2) + "\n")
    _write(tree / IGNORE, "*\n")
    if not clean:
        return ""
    status = run.run("git", "-C", str(tree), "status", "--porcelain")
    if status.returncode or status.stdout.strip():
        return f"the worktree {tree} is not clean once its files are written"
    return ""


def _write(at: Path, text: str) -> None:
    at.parent.mkdir(parents=True, exist_ok=True)
    temporary = at.with_name(at.name + ".jbus")
    temporary.write_text(text)
    os.replace(temporary, at)
