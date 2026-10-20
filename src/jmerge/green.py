"""Whether a tree has passed the check: the one lookup of its marker.

A tree that passed has a marker, and there are two, asked for in this order:

- the desk's: a ref `refs/jstack/green-tree/<tree id>` (`sweep.marker`), which `jmerge`
  pushes when its fresh check of a head merged over main passes. It is at the commit that
  passed, and it counts only when that commit's tree is the one asked for. Only somebody who
  may push to the repo can write a ref, so a fork cannot leave one.
- a run's: an artifact named `green-tree-<tree id>`, which a run of the check uploads for
  the tree it checked out once the whole suite passed there: the `full` job on main, and a
  pull request's `check` job when its selection was the whole suite.

The key is the tree, never the head: on a pull request the checkout is GitHub's merge of
the head over main, and a marker counts only for the exact tree it names.

`scripts/green_tree.py` asks it in CI before `uv sync`, and `jmerge`'s fresh check asks it
before it runs the suite on a merge tree, so it needs only the standard library. Each takes
`ask`, which gives what GitHub's API answers for a path under the repo, as JSON, and raises
where it cannot say.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jmerge.sweep import MARKERS as REF

WORKFLOW = ".github/workflows/check.yml"
ARTIFACT = "green-tree-"

Ask = Callable[[str], Any]


@dataclass(frozen=True)
class Marker:
    """A marker that counts: whose it is, `desk` or `run`, and where it is, the desk's
    commit or the address of the run."""

    source: str
    at: str


def whose(repository: object, head: object) -> str | None:
    """Whose run these two ids say it is: `repo`, `fork`, or None when either is missing."""
    if not repository or not head:
        return None
    return "repo" if head == repository else "fork"


def desk_commit(ask: Ask, tree: str) -> str | None:
    """The commit the desk marked this tree with, or None.

    GitHub lists every ref whose name starts with the one asked for, so the name is compared
    whole. The ref's name is only a claim: what counts is the tree of the commit it is at.
    """
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
    """The address of a green run of the check that left a marker for this tree, or None.

    With it, whether a marker was passed over as a fork's.

    A marker counts when it is from a run of the repo itself. A pull request from a fork runs
    the workflow of its own tree and can upload an artifact with any name, so its marker says
    nothing. The run says whose it is, by its head repository, and so does the list of
    artifacts, which is asked first and saves the call for a run it gives as a fork's. A run
    that names no head repository is nobody's. The run must have ended in success: a marker
    is uploaded near a run's end, and a run that failed or was cancelled after it is not green.
    """
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
    """The marker of this tree that counts, the desk's first, or None; and whether a marker
    was passed over as a fork's. Raises where GitHub could not be asked."""
    commit = desk_commit(ask, tree)
    if commit:
        return Marker("desk", commit), False
    run, fork = green_run(ask, tree)
    return (Marker("run", run) if run else None), fork
