from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

WORKFLOW = ".github/workflows/check.yml"
ARTIFACT = "green-tree-"
CHECKED = "checked-tree-"
"""The artifact a pull request's passed check leaves for the trees it checked: GitHub's merge of
the head over its base, and that base (`checked`). A later run of the same two trees selects the
same tests on the same files, so it reuses the pass (`jmerge.reuse`)."""
REF = "refs/jstack/green-tree/"
FULL = "full"
SELECTED = "selected"

Ask = Callable[[str], Any]


@dataclass(frozen=True)
class Marker:
    source: str
    at: str
    covers: str = FULL


def ref(tree: str, kind: str) -> str:
    """The desk's marker of a tree that a check of this kind passed."""
    return f"{REF}{kind}/{tree}"


def whose(repository: object, head: object) -> str | None:
    if not repository or not head:
        return None
    return "repo" if head == repository else "fork"


def desk_commit(ask: Ask, tree: str, kind: str) -> str | None:
    name = ref(tree, kind)
    for listed in ask(f"git/matching-refs/{name.removeprefix('refs/')}"):
        marked = listed.get("object") or {}
        if listed.get("ref") != name or marked.get("type") != "commit":
            continue
        commit = ask(f"git/commits/{marked['sha']}")
        if (commit.get("tree") or {}).get("sha") == tree:
            return marked["sha"]
    return None


def checked(base: str, tree: str) -> str:
    """The name of the artifact a passed check of the pull request leaves: `base` is the tree
    of its base's tip, and `tree` that of GitHub's merge of its head over it."""
    return f"{CHECKED}{base}-{tree}"


def green_run(ask: Ask, name: str) -> tuple[str | None, bool]:
    """The address of a successful run of the check in this repo that left the artifact `name`,
    and whether a fork's run left one."""
    fork = False
    found = ask(f"actions/artifacts?name={name}&per_page=100")
    for artifact in found["artifacts"]:
        run = artifact.get("workflow_run") or {}
        if artifact.get("expired") or not run.get("id"):
            continue
        listed = whose(run.get("repository_id"), run.get("head_repository_id"))
        if listed != "repo":
            fork = fork or listed == "fork"
            continue
        ran = ask(f"actions/runs/{run['id']}")
        read = whose(
            (ran.get("repository") or {}).get("id"), (ran.get("head_repository") or {}).get("id")
        )
        if read != "repo":
            fork = fork or read == "fork"
            continue
        if ran.get("conclusion") == "success" and ran.get("path") == WORKFLOW:
            return ran["html_url"], fork
    return None, fork


def marker(ask: Ask, tree: str) -> tuple[Marker | None, bool]:
    """The tree's marker, the one of a whole suite first: the desk's, then a green run's, and
    last the desk's marker of a selection. And whether a fork's run left one."""
    commit = desk_commit(ask, tree, FULL)
    if commit:
        return Marker("desk", commit), False
    run, fork = green_run(ask, f"{ARTIFACT}{tree}")
    if run:
        return Marker("run", run), fork
    commit = desk_commit(ask, tree, SELECTED)
    return (Marker("desk", commit, SELECTED) if commit else None), fork
