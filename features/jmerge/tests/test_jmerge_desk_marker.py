"""A desk marker from a run of selected tests never stands in for main's whole suite.

On 2026-10-23 jmerge's fresh check, `make check-fast BASE=origin/main`, passed on #332's head
merged over main, and jmerge pushed the desk's marker of that tree. Main's `full` job found the
marker and skipped `make check` in 17 s, though the tree broke a test that check-fast had not
selected. Main read green, its red cleared, and jmerge merged four more pull requests onto it.

The replay builds the same shape from small made-up commits: a tree whose `make check-fast`
passes and whose `make check` fails, then the next pull request. jmerge runs the fresh check and
marks the tree, and main's `full` job runs as check.yml says: `scripts/green_tree.py` asks a
`gh` that answers from the origin, and the job runs `make check` unless the script says
`green`. What jbus then records of main's check is what that run ended with, and jmerge holds
the next merge while main is red. A fresh check whose command is `make check` leaves a marker
that does skip main's suite."""

import json
import subprocess
import sys

import test_jmerge_fresh as fresh
import test_jmerge_order as order
import test_workflows as workflows
from jmerge import mainjson

LONG = "".join(f"{n}\n" for n in range(1, 9))
MAKEFILE = (
    "check-fast:\n\tgrep -q . wake.py\n\n"
    "check: check-fast\n"
    "\ttest $$(wc -l < wake.py) -le 5 || { echo 'wake.py is too long'; exit 1; }\n"
)
GH = f"""#!{sys.executable}
import json, subprocess, sys
origin = sys.argv[0].rsplit("/", 2)[0] + "/origin.git"
path = sys.argv[2].partition("?")[0].split("/", 3)[3]


def git(*args):
    return subprocess.run(["git", "-C", origin, *args], capture_output=True, text=True).stdout


if path.startswith("git/matching-refs/"):
    prefix = "refs/" + path.removeprefix("git/matching-refs/")
    listed = git("for-each-ref", "--format=%(refname) %(objectname) %(objecttype)")
    refs = [line.split() for line in listed.splitlines()]
    found = [
        {{"ref": ref, "object": {{"sha": sha, "type": kind}}}}
        for ref, sha, kind in refs
        if ref.startswith(prefix)
    ]
    print(json.dumps(found))
elif path.startswith("git/commits/"):
    sha = path.removeprefix("git/commits/")
    print(json.dumps({{"tree": {{"sha": git("rev-parse", sha + "^{{tree}}").strip()}}}}))
elif path.startswith("actions/artifacts"):
    print(json.dumps({{"artifacts": []}}))
else:
    sys.exit("HTTP 404: Not Found")
"""


def kitchen_of(tmp_path, command):
    """A repo whose `wake.py` may have five lines: check-fast does not test that, and `make
    check` does. The repo's fresh check is `command`, and jbus knows the repo as `demo`."""
    kitchen = fresh.Kitchen(tmp_path, {"wake.py": "1\n", "Makefile": MAKEFILE})
    (kitchen.home.state / "fresh-check").write_text(f"{command}\n")
    return kitchen


def full_job(kitchen, tip):
    """Main's `full` job at `tip`, as check.yml runs it: whether it ran the suite, whether the
    run passed, and the line the marker's lookup printed."""
    here = kitchen.tmp / "ci"
    bin = here / "bin"
    bin.mkdir(parents=True)
    (bin / "gh").write_text(GH)
    (bin / "gh").chmod(0o755)
    (here / "origin.git").symlink_to(kitchen.origin)
    checkout = here / "checkout"
    fresh.git(kitchen.tmp, "clone", "-q", str(kitchen.origin), str(checkout))
    fresh.git(checkout, "checkout", "-q", "--detach", tip)
    output = here / "output"
    env = {
        "PATH": f"{bin}:/usr/bin:/bin",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    looked = subprocess.run(
        [sys.executable, str(workflows.GREEN_TREE)],
        cwd=checkout,
        capture_output=True,
        text=True,
        env=env,
    )
    assert looked.returncode == 0, looked.stderr
    said = dict(line.split("=", 1) for line in output.read_text().splitlines())
    found, _ = workflows.steps(workflows.CHECK.read_text(), "full-shard")
    (suite,) = [step for step in found if step.get("id") == "suite"]
    asked = {"steps.tree.outputs.marker": said["marker"], "steps.tree.outputs.from": said["from"]}
    if not workflows.worked(suite["if"], asked):
        return False, True, looked.stdout.strip()
    ran = subprocess.run(["make", "check"], cwd=checkout, capture_output=True, text=True)
    return True, ran.returncode == 0, looked.stdout.strip()


def main_judged(kitchen, tip, passed):
    """What jbus records in `main.json` once main's check at `tip` ended this way."""
    order.queue_of(kitchen.home, [order.row("next", pr="#9")])
    check = "green" if passed else "failed"
    record = mainjson.record(
        main=tip, at="2026-10-23T14:24:00-04:00", check=check, broken="" if passed else tip
    )
    state = kitchen.home.user / ".local" / "state" / "jbus" / "demo"
    (state / mainjson.NAME).write_text(json.dumps(record))


def merged_on_the_desk(kitchen):
    """#332's shape: its head makes `wake.py` too long, and main changed `wake.py` after its
    check started, so jmerge runs the fresh check on the head merged over today's main and,
    when it passes, marks that tree and merges. Return main's tip after the merge."""
    kitchen.crew("long", 332, {"wake.py": "1\n" + LONG})
    kitchen.on_main({"wake.py": "0\n1\n"})
    (said,) = kitchen.after_check()
    assert said.startswith("merged 332 long "), said
    del kitchen.pulls["long"]
    return kitchen.tip()


def test_a_tree_only_check_fast_passed_runs_the_whole_suite_on_main_and_main_red_holds_the_next(
    tmp_path,
):
    kitchen = kitchen_of(tmp_path, "make check-fast")
    tip = merged_on_the_desk(kitchen)
    assert fresh.markers(kitchen), "jmerge marked no tree"
    suite, passed, line = full_job(kitchen, tip)
    assert (suite, passed) == (True, False), line
    assert "so the suite runs" in line
    main_judged(kitchen, tip, passed)
    kitchen.crew("next", 9, {"a.txt": "next\n"}, checks=(fresh.AFTER,))
    assert kitchen.run() == [
        f"wait 9 {fresh.url(9)}: main is red at {tip[:12]}, its fix merges first"
    ]
    assert kitchen.tip() == tip


def test_a_tree_the_whole_suite_passed_on_the_desk_skips_mains_suite(tmp_path):
    kitchen = kitchen_of(tmp_path, "make check")
    (kitchen.home.main / "Makefile").write_text(MAKEFILE.replace("-le 5", "-le 50"))
    fresh.git(kitchen.home.main, "commit", "-qam", "a longer cap")
    fresh.git(kitchen.home.main, "push", "-q")
    tip = merged_on_the_desk(kitchen)
    suite, passed, line = full_job(kitchen, tip)
    assert (suite, passed) == (False, True), line
    assert "passed a fresh check on the desk" in line and "so the suite is skipped" in line
