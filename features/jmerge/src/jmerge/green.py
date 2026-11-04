from __future__ import annotations

from collections.abc import Callable
from typing import Any

WORKFLOW = ".github/workflows/check.yml"
ARTIFACT = "green-tree-"
CHECKED = "checked-tree-"
"""The artifact a pull request's passed check leaves for the trees it checked: GitHub's merge of
the head over its base, and that base (`checked`). A later run of the same two trees selects the
same tests on the same files, so it reuses the pass (`jmerge.reuse`)."""
MACOS = ".github/workflows/macos.yml"
MACOS_CHECKED = "macos-checked-"
"""The artifact a pull request's passed macos job leaves for the same two trees (`macos_checked`).
The pair fixes the tests `macos-select` hands on and the files they run on, so a later run of it
starts no Mac."""

Ask = Callable[[str], Any]


def whose(repository: object, head: object) -> str | None:
    if not repository or not head:
        return None
    return "repo" if head == repository else "fork"


def checked(base: str, tree: str) -> str:
    """The name of the artifact a passed check of the pull request leaves: `base` is the tree
    of its base's tip, and `tree` that of GitHub's merge of its head over it."""
    return f"{CHECKED}{base}-{tree}"


def macos_checked(base: str, tree: str) -> str:
    """The name of the artifact a passed macos job of the pull request leaves, of the two trees
    `checked` names."""
    return f"{MACOS_CHECKED}{base}-{tree}"


def green_run(ask: Ask, name: str) -> tuple[str | None, bool]:
    """The address of a successful run in this repo of the workflow that leaves the artifact
    `name`, macos.yml for a `macos_checked` name and the check for any other, and whether a fork's
    run left one."""
    workflow = MACOS if name.startswith(MACOS_CHECKED) else WORKFLOW
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
        if ran.get("conclusion") == "success" and ran.get("path") == workflow:
            return ran["html_url"], fork
    return None, fork
