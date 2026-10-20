"""Has the tree checked out here already passed the check?

The check workflow runs this after its checkout and before anything else. A tree that passed
has a marker, and there are two, asked for in this order:

- the desk's: a ref `refs/jstack/green-tree/<tree id>`, which `jmerge` pushes when its fresh
  check of a head merged over main passes. It is at the commit that passed, and it counts
  only when that commit's tree is the one checked out. Only somebody who may push to the
  repo can write a ref, so a fork cannot leave one.
- a run's: an artifact named `green-tree-<tree id>`, which a run of the check uploads for
  the tree it checked out once the whole suite passed there: the `full` job, and a pull
  request's `check` job whose selection was the whole suite.

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
token (`contents: read` for the ref, `actions: read` for the artifact). The lookup itself is
`jmerge.green`, imported from `src/` beside it, which jmerge's fresh check asks too.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jmerge import green


def gh(path):
    """What GitHub's API gives for this path, through `gh`."""
    done = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise RuntimeError((done.stderr.strip() or f"gh exited {done.returncode}").splitlines()[0])
    return json.loads(done.stdout)


def answer(tree, env):
    """The marker's word, the line that says why, and whose marker a green one is."""
    if env.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return "unasked", "a manual run always runs the suite", ""
    if env.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        return "unasked", "a run again always runs the suite", ""
    repo = env["GITHUB_REPOSITORY"]
    try:
        found, fork = green.marker(lambda path: gh(f"repos/{repo}/{path}"), tree)
    except Exception as error:
        return "unknown", f"could not ask ({error}), so the suite runs", ""
    if found is None and fork:
        return "none", "a marker came from a fork's run, so the suite runs", ""
    if found is None:
        return "none", "no green run of the check left a marker, so the suite runs", ""
    if found.source == "desk":
        why = f"passed a fresh check on the desk, which marked it with the commit {found.at}"
        return "green", f"{why}, so the suite is skipped", "desk"
    return "green", f"passed the check in {found.at}, so the suite is skipped", "run"


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
