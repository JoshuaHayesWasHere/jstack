"""Has the tree checked out here already passed the check?

The check workflow runs this after its checkout and before anything else. A tree that passed
has a marker, and there are two, asked for in this order:

- the desk's: a ref `refs/jstack/green-tree/<tree id>`, which `jmerge` pushes when its fresh
  check of a head merged over main passes. It is at the commit that passed, and it counts
  only when that commit's tree is the one checked out. Only somebody who may push to the
  repo can write a ref, so a fork cannot leave one.
- a run's: an artifact named `green-tree-<tree id>`, which a run of the check that ends
  green uploads for the tree it checked out.

A later run that checks out the same tree tests the same thing, so it skips the suite. The
key is the tree, never the head: on a pull request the checkout is GitHub's merge of the
head over main, so the tree holds main as it was.

It answers in one word, the step's output `marker`:

- `green`: the desk marked this tree, or a run of this workflow, of this repo, that ended
  in success left a marker for it. The line it prints names the desk's commit or that run.
- `none`: no such run did. The line says so when a marker was a fork's.
- `unknown`: the question could not be asked (no `gh`, no network, no permission). The line
  is printed as a warning on the run, so a skip that never works is seen.
- `unasked`: the run is a manual one or a run again, which always run the suite.

Its other outputs are `name`, the marker's name, which the workflow uploads under, and
`from`, whose marker a `green` is: `desk` or `run`. The desk's check ran in an environment
nobody locked, so a run that skips on it still runs `uv sync --locked`.

Only `green` skips the suite. It never fails: a run that cannot find out runs the suite as
it always did. It needs no package, so it runs before `uv sync`, with `gh` and the run's
token (`contents: read` for the ref, `actions: read` for the artifact).
"""

import json
import os
import subprocess
import sys

WORKFLOW = ".github/workflows/check.yml"


def gh(path):
    """What GitHub's API gives for this path, through `gh`."""
    done = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise RuntimeError((done.stderr.strip() or f"gh exited {done.returncode}").splitlines()[0])
    return json.loads(done.stdout)


def whose(repository, head):
    """Whose run these two ids say it is: `repo`, `fork`, or None when either is missing."""
    if not repository or not head:
        return None
    return "repo" if head == repository else "fork"


def desk_commit(repo, tree):
    """The commit the desk marked this tree with, or None.

    GitHub lists every ref whose name starts with the one asked for, so the name is compared
    whole. The ref's name is only a claim: what counts is the tree of the commit it is at.
    """
    name = f"refs/jstack/green-tree/{tree}"
    for ref in gh(f"repos/{repo}/git/matching-refs/jstack/green-tree/{tree}"):
        marked = ref.get("object") or {}
        if ref.get("ref") != name or marked.get("type") != "commit":
            continue
        commit = gh(f"repos/{repo}/git/commits/{marked['sha']}")
        if (commit.get("tree") or {}).get("sha") == tree:
            return marked["sha"]
    return None


def green_run(repo, tree):
    """The address of a green run of the check that left a marker for this tree, or None.

    With it, whether a marker was passed over as a fork's.

    A marker counts when it is from a run of the repo itself. A pull request from a fork runs
    the workflow of its own tree and can upload an artifact with any name, so its marker says
    nothing. The run says whose it is, by its head repository, and so does the list of
    artifacts, which is asked first and saves the call for a run it gives as a fork's. A run
    that names no head repository is nobody's. The run must have ended in success: a marker
    is uploaded by a run's last step, and a run cancelled after it is not green.
    """
    fork = False
    found = gh(f"repos/{repo}/actions/artifacts?name=green-tree-{tree}&per_page=100")
    for artifact in found["artifacts"]:
        run = artifact.get("workflow_run") or {}
        if artifact.get("expired") or not run.get("id"):
            continue
        listed = whose(run.get("repository_id"), run.get("head_repository_id"))
        if listed != "repo":
            fork = fork or listed == "fork"
            continue
        ran = gh(f"repos/{repo}/actions/runs/{run['id']}")
        read = whose(
            (ran.get("repository") or {}).get("id"), (ran.get("head_repository") or {}).get("id")
        )
        if read != "repo":
            fork = fork or read == "fork"
            continue
        if ran.get("conclusion") == "success" and ran.get("path") == WORKFLOW:
            return ran["html_url"], fork
    return None, fork


def answer(tree, env):
    """The marker's word, the line that says why, and whose marker a green one is."""
    if env.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return "unasked", "a manual run always runs the suite", ""
    if env.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        return "unasked", "a run again always runs the suite", ""
    try:
        commit = desk_commit(env["GITHUB_REPOSITORY"], tree)
        if commit:
            why = f"passed a fresh check on the desk, which marked it with the commit {commit}"
            return "green", f"{why}, so the suite is skipped", "desk"
        run, fork = green_run(env["GITHUB_REPOSITORY"], tree)
    except Exception as error:
        return "unknown", f"could not ask ({error}), so the suite runs", ""
    if run is None and fork:
        return "none", "a marker came from a fork's run, so the suite runs", ""
    if run is None:
        return "none", "no green run of the check left a marker, so the suite runs", ""
    return "green", f"passed the check in {run}, so the suite is skipped", "run"


def main():
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], capture_output=True, text=True, check=True
    ).stdout.strip()
    marker, why, whose_marker = answer(tree, os.environ)
    print(f"{'::warning::' if marker == 'unknown' else ''}green-tree: tree {tree}: {why}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"name=green-tree-{tree}\nmarker={marker}\nfrom={whose_marker}\n")


if __name__ == "__main__":
    sys.exit(main())
