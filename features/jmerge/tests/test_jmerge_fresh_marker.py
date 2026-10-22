"""`jmerge`'s fresh check treats a green marker for the tree it would test as a pass.

When a pull request's check is stale, `jmerge` merges the pull request's head over today's
main and tests the result. A green run of the check may already have run the whole suite on
that same tree and left the marker `green-tree-<tree>`. Then the suite does not run again,
and the pull request merges on that run. The line that says so names the tree and the run,
both in `merge.log` and in what jbus logs. A marker for another tree, a marker from a red
run, or a missing marker does not count as a pass, and the check runs as before.

The tests run the command against a real origin with a fake `gh`
(`features/jmerge/tests/test_jmerge_fresh.py`). The fake also answers the API's list of
artifacts and its list of runs from files."""

import json

import pytest

import test_jmerge_fresh as fresh
from jmerge import ready

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
    (stub / "gh").write_text(fresh.GH.replace('case "$1 $2" in\n', 'case "$1 $2" in\n' + ASKED))
    (stub / "artifacts").mkdir()
    (stub / "runs").mkdir()
    return kitchen


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


def skipped(checked, of):
    on = f"on {checked.head[:12]} over {checked.main[:12]}"
    return f"fresh: skipped, tree {of} passed in {URL}, {on}"


def test_a_green_marker_of_the_merge_tree_is_the_pass_and_the_suite_is_not_run(kitchen):
    checked = fresh.Checked(kitchen, fresh.BOTH)
    merged = tree(kitchen, checked.head, checked.main)
    marked(kitchen, merged)
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ") and f", {skipped(checked, merged)}, revert: " in said
    assert checked.ran() == []
    log = (kitchen.home.state / "merge.log").read_text().splitlines()
    assert [line for line in log if skipped(checked, merged) in line] == [log[-1]]
    assert kitchen.at_main("b.txt") == ("theirs\n" + fresh.LINES + "ours\n").strip()


def test_a_skip_is_remembered_and_said_the_same_way_on_a_later_run(kitchen):
    checked = fresh.Checked(kitchen, fresh.BOTH)
    merged = tree(kitchen, checked.head, checked.main)
    marked(kitchen, merged)
    (kitchen.home.state / "merge-off").write_text("")
    assert kitchen.run() == [f"wait 7 {fresh.url(7)}: auto-merge is off for this repo"]
    (kitchen.home.state / "merge-off").unlink()
    (kitchen.home.stub / "artifacts" / f"green-tree-{merged}.json").unlink()
    assert kitchen.run("--check") == [f"ready 7 {checked.head} two two, {skipped(checked, merged)}"]
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ") and skipped(checked, merged) in said
    assert checked.ran() == []
    assert checked.known()["7"] | {"at": ""} == {
        "head": checked.head,
        "main": checked.main,
        "command": checked.command,
        "result": ready.PASSED,
        "tree": merged,
        "marker": URL,
        "at": "",
    }


def test_a_marker_of_another_tree_is_no_proof_and_the_check_runs(kitchen):
    """The pull request's own check ran on its head merged over the main it had then."""
    checked = fresh.Checked(kitchen, fresh.BOTH)
    before = fresh.git(kitchen.origin, "rev-parse", "refs/heads/main~1")
    marked(kitchen, tree(kitchen, checked.head, before))
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ") and f", {checked.passed()}, revert: " in said
    assert len(checked.ran()) == 1


def test_a_marker_a_red_run_left_is_no_proof_and_the_check_runs(kitchen):
    checked = fresh.Checked(kitchen, fresh.BOTH)
    marked(kitchen, tree(kitchen, checked.head, checked.main), conclusion="failure")
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ") and f", {checked.passed()}, revert: " in said
    assert len(checked.ran()) == 1


def test_no_marker_runs_the_check_and_a_failure_there_still_waits(kitchen):
    checked = fresh.Checked(kitchen, "exit 3")
    assert kitchen.after_check() == [
        f"wait 7 {fresh.url(7)}: {checked.command} fails {checked.over()}"
    ]
    assert len(checked.ran()) == 1
    assert kitchen.calls() == []


def test_a_skip_never_stands_over_a_main_that_moved_and_the_new_tree_is_checked(tmp_path):
    """A pass that ran still counts after main gains commits that do not touch its tests
    (`features/jmerge/tests/test_jmerge_fresh.py`). A skip does not. Its marker names the
    tree it was taken on, and the new main makes another tree, which has no marker."""
    kitchen = fresh.Kitchen(tmp_path, fresh.SELECTED)
    stub = kitchen.home.stub
    (stub / "gh").write_text(fresh.GH.replace('case "$1 $2" in\n', 'case "$1 $2" in\n' + ASKED))
    (stub / "artifacts").mkdir()
    (stub / "runs").mkdir()
    checked = fresh.Checked(kitchen, "true", "src/demo/two.py")
    merged = tree(kitchen, checked.head, checked.main)
    marked(kitchen, merged)
    (kitchen.home.state / "merge-off").write_text("")
    kitchen.run()
    assert checked.known()["7"]["marker"] == URL and checked.ran() == []
    (kitchen.home.state / "merge-off").unlink()
    now = kitchen.on_main({"src/demo/one.py": "theirs\n" + fresh.LINES})
    assert kitchen.run("--check") == [
        f"wait 7 {fresh.url(7)}: {fresh.STALE.format('src/demo/two.py')}"
    ]
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ")
    assert (
        f", fresh: {checked.command} passed on {checked.head[:12]} over {now[:12]}, revert: "
        in said
    )
    assert len(checked.ran()) == 1
