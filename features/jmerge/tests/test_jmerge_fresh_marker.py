"""`jmerge`'s fresh check treats a green marker for the tree it would test as a pass.

When a pull request's check is stale, `jmerge` merges the pull request's head over today's
main. A green run of the check may already have run the whole suite on that same tree and left
the marker `green-tree-<tree>`. Then GitHub is not asked to update the branch, and the pull
request merges on that run. The line that says so names the tree and the run, both in
`merge.log` and in what jbus logs. A marker for another tree, a marker from a red run, or a
missing marker does not count as a pass, and GitHub is asked to merge main into the branch.

The tests run the command against a real origin with a fake `gh`
(`features/jmerge/tests/test_jmerge_fresh.py`). The fake also answers the API's list of
artifacts and its list of runs from files."""

import json

import pytest

import test_jmerge_fresh as fresh
from test_jmerge_rejudge import MOVED, UPDATE

ASKED = """\
    "api repos/"*)
        path=${2#repos/*/*/}
        case $path in
            git/matching-refs/*) echo "[]" ;;
            "actions/artifacts?name="*)
                name=${path#*name=}
                cat "$STUB/artifacts/${name%%&*}.json" 2> /dev/null || echo '{"artifacts": []}' ;;
            actions/runs/*) cat "$STUB/runs/${path#actions/runs/}.json" ;;
            *) exit 64 ;;
        esac ;;
"""
RUN = 39342620318
URL = f"https://github.com/owner/repo/actions/runs/{RUN}"


@pytest.fixture
def kitchen(tmp_path):
    kitchen = fresh.Kitchen(tmp_path, {"a.txt": fresh.LINES, "b.txt": fresh.LINES})
    stub = kitchen.home.stub
    gh = fresh.GH.replace('case "$1 $2" in\n', 'case "$1 $2" in\n' + ASKED)
    (stub / "gh").write_text(gh.replace("    *) exit 64 ;;\n", UPDATE + "    *) exit 64 ;;\n"))
    (stub / "artifacts").mkdir()
    (stub / "runs").mkdir()
    (kitchen.home.state / "fresh-check").write_text("true\n")
    return kitchen


def stale(kitchen):
    """A pull request whose check passed before main changed its file: its head and main's tip."""
    head = kitchen.crew("two", 7, {"b.txt": fresh.LINES + "ours\n"})
    (kitchen.home.stub / "branch-7").write_text("two")
    return head, kitchen.on_main({"b.txt": "theirs\n" + fresh.LINES})


def updated(kitchen):
    path = kitchen.home.stub / "updated"
    return path.read_text().split() if path.exists() else []


def tree(kitchen, head, tip):
    return fresh.git(kitchen.origin, "merge-tree", "--write-tree", tip, head).splitlines()[0]


def marked(kitchen, of, conclusion="success"):
    """A run of the repo's own check that left the marker of this tree and ended with
    `conclusion`."""
    stub = kitchen.home.stub
    run = {"id": RUN, "repository_id": 1, "head_repository_id": 1}
    listed = {"artifacts": [{"name": f"green-tree-{of}", "expired": False, "workflow_run": run}]}
    (stub / "artifacts" / f"green-tree-{of}.json").write_text(json.dumps(listed))
    (stub / "runs" / f"{RUN}.json").write_text(
        json.dumps(
            {
                "conclusion": conclusion,
                "path": ".github/workflows/check.yml",
                "html_url": URL,
                "repository": {"id": 1},
                "head_repository": {"id": 1},
            }
        )
    )


def skipped(head, main, of):
    return f"fresh: skipped, tree {of} passed in {URL}, on {head[:12]} over {main[:12]}"


def test_a_green_marker_of_the_merge_tree_is_the_pass_and_github_is_not_asked(kitchen):
    head, main = stale(kitchen)
    merged = tree(kitchen, head, main)
    marked(kitchen, merged)
    assert kitchen.run("--check") == [f"ready 7 {head} two two, {skipped(head, main, merged)}"]
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ") and f", {skipped(head, main, merged)}, revert: " in said
    assert updated(kitchen) == []
    log = (kitchen.home.state / "merge.log").read_text().splitlines()
    assert [line for line in log if skipped(head, main, merged) in line] == [log[-1]]
    assert kitchen.at_main("b.txt") == ("theirs\n" + fresh.LINES + "ours\n").strip()
    assert not (kitchen.home.state / "fresh.json").exists()


def test_a_marker_of_another_tree_is_no_proof_and_github_is_asked(kitchen):
    """The pull request's own check ran on its head merged over main as main was when the check
    started."""
    head, main = stale(kitchen)
    before = fresh.git(kitchen.origin, "rev-parse", "refs/heads/main~1")
    marked(kitchen, tree(kitchen, head, before))
    assert kitchen.run() == [f"wait 7 {fresh.url(7)}: {MOVED.format(tip=main[:12])}"]
    assert updated(kitchen) == ["7"]


def test_a_marker_a_red_run_left_is_no_proof_and_github_is_asked(kitchen):
    head, main = stale(kitchen)
    marked(kitchen, tree(kitchen, head, main), conclusion="failure")
    assert kitchen.run() == [f"wait 7 {fresh.url(7)}: {MOVED.format(tip=main[:12])}"]
    assert updated(kitchen) == ["7"]
