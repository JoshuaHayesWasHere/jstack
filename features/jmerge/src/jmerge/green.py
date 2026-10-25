from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

WORKFLOW = ".github/workflows/check.yml"
ARTIFACT = "green-tree-"
REF = "refs/jstack/green-tree/"

Ask = Callable[[str], Any]


@dataclass(frozen=True)
class Marker:
    source: str
    at: str


def whose(repository: object, head: object) -> str | None:
    if not repository or not head:
        return None
    return "repo" if head == repository else "fork"


def desk_commit(ask: Ask, tree: str) -> str | None:
    name = f"{REF}{tree}"
    for ref in ask(f"git/matching-refs/{name.removeprefix('refs/')}"):
        marked = ref.get("object") or {}
        if ref.get("ref") != name or marked.get("type") != "commit":
            continue
        commit = ask(f"git/commits/{marked['sha']}")
        if (commit.get("tree") or {}).get("sha") == tree:
            return marked["sha"]
    return None


def green_run(ask: Ask, tree: str) -> tuple[str | None, bool]:
    fork = False
    found = ask(f"actions/artifacts?name={ARTIFACT}{tree}&per_page=100")
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
    commit = desk_commit(ask, tree)
    if commit:
        return Marker("desk", commit), False
    run, fork = green_run(ask, tree)
    return (Marker("run", run) if run else None), fork
