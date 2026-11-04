"""Has the tree in this checkout already passed the check?

The check workflow's `full` parts run this after their checkout and before anything else. A tree
that passed has a marker: an artifact named `green-tree-<tree id>`. A run of the check uploads it
for the tree it checked out, once the whole suite passed on that tree. Two jobs upload it: the
`full` job, and a pull request's `check` job whose selection was the whole suite. A run's artifact
is the only marker. The desk's refs `refs/jstack/green-tree/<kind>/<tree id>` are not read: nothing
pushes them since #444, and anybody with write to the repo could push one by hand, so a ref would
skip main's suite on nobody's check.

A later run that checks out the same tree tests the same thing, so it skips the suite. The
key is the tree, never the head: on a pull request the checkout is GitHub's merge of the
head over main, so the tree contains main as of that merge.

The script answers in one word, the step's output `marker`:

- `green`: a successful run of this workflow in this repo left a marker for this tree. The line
  it prints names that run.
- `none`: no such run left a marker for it. The line says so when a marker was a fork's.
- `unknown`: the script could not ask (no `gh`, no network, no permission). It prints the
  line as a warning on the run, so that a skip that never works is visible.
- `unasked`: the run is a manual run or a rerun, which always runs the suite.

Its other output is `name`, the name the workflow uploads the marker under.

Only `green` skips the suite. The script never fails: a run that cannot find out runs the
suite as it always did. The script needs no package, so it runs before `uv sync`, with `gh` and
the run's token (`actions: read` for the artifact). The lookup itself is `jmerge.green`, which
the script imports from `features/jmerge/src/`.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "features" / "jmerge" / "src"))

from jmerge import green


def gh(path):
    """What GitHub's API gives for this path, through `gh`."""
    done = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise RuntimeError((done.stderr.strip() or f"gh exited {done.returncode}").splitlines()[0])
    return json.loads(done.stdout)


def answer(tree, env):
    """The marker's word and the line that says why."""
    if env.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return "unasked", "a manual run always runs the suite"
    if env.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        return "unasked", "a run again always runs the suite"
    repo = env["GITHUB_REPOSITORY"]
    try:
        run, fork = green.green_run(lambda path: gh(f"repos/{repo}/{path}"), green.ARTIFACT + tree)
    except Exception as error:
        return "unknown", f"could not ask ({error}), so the suite runs"
    if run:
        return "green", f"passed the check in {run}, so the suite is skipped"
    if fork:
        return "none", "a marker came from a fork's run, so the suite runs"
    return "none", "no green run of the check left a marker, so the suite runs"


def main():
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], capture_output=True, text=True, check=True
    ).stdout.strip()
    marker, why = answer(tree, os.environ)
    print(f"{'::warning::' if marker == 'unknown' else ''}green-tree: tree {tree}: {why}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"name=green-tree-{tree}\nmarker={marker}\n")


if __name__ == "__main__":
    sys.exit(main())
