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

`green_tree.py --last-checked <workflow>` answers the other question a push to main asks: what
did main's check last check? A push run of check.yml or macos.yml on main selects its tests over
`<last checked>..<the pushed commit>`, not over the merge alone, since its pushes share one
concurrency group that keeps one run going and only the newest waiting: GitHub cancels a waiting
run that a newer push displaces, before it has a job, and the newer run checks its change. The
last checked commit is the newest of main's commits at or under HEAD, HEAD left out, whose push
run of `<workflow>` on main ran to an end, `success` or `failure`. A failure counts, since its
failed tests are FAILED_ON_MAIN's, which every later selection adds; a cancelled run checked
nothing whole. It is an ancestor of HEAD however the runs were ordered, so a run again of an old
commit selects over its own range. The script fetches that one commit, depth 1, since the diff
reads only the two trees, and gives it as the step's output `base`. Where no such run is in reach
(the last `REACH` commits or runs) or GitHub does not answer, `base` is git's empty tree, whose
diff to HEAD names every file, so the selection is the whole list, with a warning.
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


REACH = 100
"""How many of main's newest commits, and of the workflow's newest push runs, the lookup reads."""
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
"""git's empty tree: a diff from it to HEAD names every file."""
RAN = ("success", "failure")
"""The conclusions of a run whose jobs ran to an end."""


def last_checked(ask, workflow, head):
    """The newest commit under `head` whose push run of `workflow` on main ran to an end, or None
    where none of the last `REACH` commits has one. `ask` gives GitHub's answer for a path of the
    repo's API."""
    runs = ask(
        f"actions/workflows/{workflow}/runs?branch=main&event=push&status=completed"
        f"&per_page={REACH}"
    )["workflow_runs"]
    checked = {run["head_sha"] for run in runs if run.get("conclusion") in RAN}
    commits = ask(f"commits?sha={head}&per_page={REACH}")
    return next((c["sha"] for c in commits if c["sha"] != head and c["sha"] in checked), None)


def base(workflow, env):
    """The `base` output and the line that says why: the last checked commit, fetched, or the
    empty tree."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    repo = env["GITHUB_REPOSITORY"]
    try:
        found = last_checked(lambda path: gh(f"repos/{repo}/{path}"), workflow, head)
    except Exception as error:
        return EMPTY_TREE, f"::warning::last checked: could not ask ({error}), so the whole list"
    if found is None:
        why = f"no push run of {workflow} in the last {REACH} commits ran, so the whole list"
        return EMPTY_TREE, f"::warning::last checked: {why}"
    fetched = subprocess.run(
        ["git", "fetch", "--no-tags", "--depth=1", "origin", found], capture_output=True, text=True
    )
    if fetched.returncode:
        why = f"{found} could not be fetched ({fetched.stderr.strip()}), so the whole list"
        return EMPTY_TREE, f"::warning::last checked: {why}"
    return (
        found,
        f"last checked: {workflow} last checked {found}, so it selects over {found}..{head}",
    )


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


def main(argv):
    if argv[:1] == ["--last-checked"] and len(argv) == 2:
        found, why = base(argv[1], os.environ)
        print(why)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write(f"base={found}\n")
        return
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], capture_output=True, text=True, check=True
    ).stdout.strip()
    marker, why = answer(tree, os.environ)
    print(f"{'::warning::' if marker == 'unknown' else ''}green-tree: tree {tree}: {why}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"name=green-tree-{tree}\nmarker={marker}\n")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
