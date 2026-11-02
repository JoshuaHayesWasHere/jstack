"""Has a pull request's check already passed on the two trees this run checks?

The check workflow's `reuse` job runs this on a pull request, after a checkout of GitHub's merge
of the head over its base, before any part of the suite:

    PYTHONPATH=features/jmerge/src python3 -m jmerge.reuse

The two trees are the merge's, `HEAD^{tree}`, and its base's, `HEAD^1^{tree}`. The pair fixes what
the check runs: `make check-fast BASE=HEAD^1` selects its tests by the diff between the two, and
tests the merge. A passed check leaves an artifact named by the pair (`green.checked`), and a later
run of the same pair skips the suite and passes on it.

This is what keeps a stacked pull request's move onto main off the merge path. The link is
checked while it sits on its base's branch: the base is its base's tip, and the merge is the
link's own tree. Once the base squash-merged as that tip and jbus replayed the link's own commits
onto it, the run at the moved head checks the same pair, and passes in the time the lookup
takes. Where the move is no clean replay of the same trees (the base took commits after the
link's check, main moved before the base merged, the replay changed the patch), the pair differs,
and the suite runs as it always did.

The step's outputs are `name`, the artifact a passed run leaves, and `reused`: `true` only where a
successful run of the check in this repo, not a fork's, left that artifact. A manual run and a run
again always run the suite. The script never fails: one that cannot ask runs the suite, and says
so as a warning on the run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping

from jmerge import green


def _gh(path: str) -> object:
    done = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise RuntimeError((done.stderr.strip() or f"gh exited {done.returncode}").splitlines()[0])
    return json.loads(done.stdout)


def _tree(commit: str) -> str:
    done = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"], capture_output=True, text=True
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def answer(name: str, env: Mapping[str, str]) -> tuple[bool, str, bool]:
    """Whether the run reuses a pass of `name`, the line that says why, and whether that line
    is a warning."""
    if env.get("GITHUB_EVENT_NAME") != "pull_request":
        return False, "only a pull request's check reuses a pass, so the suite runs", False
    if env.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        return False, "a run again always runs the suite", False
    repo = env["GITHUB_REPOSITORY"]
    try:
        run, fork = green.green_run(lambda path: _gh(f"repos/{repo}/{path}"), name)
    except Exception as error:
        return False, f"could not ask ({error}), so the suite runs", True
    if run:
        return True, f"passed the check in {run}, so the suite is skipped", False
    if fork:
        return False, "only a fork's run passed them, so the suite runs", False
    return False, "no passed check left a marker of them, so the suite runs", False


def main() -> int:
    base, tree = _tree("HEAD^1"), _tree("HEAD")
    if base and tree:
        name = green.checked(base, tree)
        reused, why, warn = answer(name, os.environ)
        said = f"{name}: {why}"
    else:
        name, reused, warn = "", False, True
        said = "the merge or its base has no tree here (a checkout of depth 2 has both)"
        said += ", so the suite runs"
    print(f"{'::warning::' if warn else ''}reuse: {said}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"name={name}\nreused={'true' if reused else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
