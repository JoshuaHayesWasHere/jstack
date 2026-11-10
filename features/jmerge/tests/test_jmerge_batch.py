"""Where the state has a `merge-batch` file, `jmerge` proves the pull requests that main moved past
together: it builds main's tip with each of them merged in, force-pushes that commit to its own
`jmerge/batch` branch under one standing draft pull request, and keeps the tip, the tree and the
members in `batch.json`. CI's check of that pull request leaves the artifact of the two trees
(`green.checked`), and on it `jmerge` squash-merges each member at its own head, in merge order,
with no guards run. A batch whose check failed sends each member down the single path of today.

The tests run the `jmerge` command against a real origin and the fake `gh` of
`test_jmerge_fresh.Kitchen`, which also opens a pull request, refuses one merge by number, and
answers the artifact and run lookups from files of the stub."""

import json

import pytest

import test_home_merge as merge
from jmerge import batch, green, ready, treeguards
from jmerge.lock import MergeLock
from test_jmerge_fresh import GH, LINES, Kitchen, git, url
from test_jmerge_order import DIRECTORY, queue_of, row
from test_jmerge_revert_line import named

RUN = "https://example.test/actions/runs/5"
CREATE = """\
    "pr create")
        echo "$*" >> "$STUB/created"
        echo "https://example.test/pull/99" ;;
    "api repos/"*)
        case "$2" in
            *actions/artifacts\\?name=*)
                name=${2#*name=}
                name=${name%%&*}
                if [ -e "$STUB/artifact-$name" ]; then
                    cat "$STUB/artifact-$name"
                else
                    echo '{"artifacts": []}'
                fi ;;
            *actions/runs/*) cat "$STUB/run-${2##*/}" ;;
            *) exit 64 ;;
        esac ;;
"""
BATCH_GH = GH.replace('case "$1 $2" in\n', 'case "$1 $2" in\n' + CREATE, 1).replace(
    'if [ -e "$STUB/merge-refused" ]; then',
    'if [ -e "$STUB/merge-refused" ] || [ -e "$STUB/refuse-$3" ]; then',
    1,
)
assert BATCH_GH.count("pr create") == 1 and "refuse-$3" in BATCH_GH
MAKEFILE = "guards:\n\t@echo ran >> {ran}\n"
OURS = "ours\n" + LINES


@pytest.fixture
def kitchen(tmp_path):
    ran = tmp_path / "guards-ran"
    files = dict.fromkeys(("a.txt", "b.txt", "c.txt", "d.txt"), LINES)
    made = Kitchen(tmp_path, {**files, "Makefile": MAKEFILE.format(ran=ran)})
    (made.home.stub / "gh").write_text(BATCH_GH)
    (made.home.state / treeguards.NAME).write_text("make -s guards\n")
    (made.home.state / batch.SWITCH).write_text("")
    made.ran = ran
    return made


def runs(kitchen):
    """How many times the guards ran on a merged tree."""
    return len(kitchen.ran.read_text().split()) if kitchen.ran.exists() else 0


def three(kitchen):
    """Three ready pull requests, each on a file of its own, whose checks main moved past."""
    heads = [
        kitchen.crew(slug, number, {name: OURS})
        for slug, number, name in (("one", 6, "a.txt"), ("two", 7, "b.txt"), ("three", 8, "c.txt"))
    ]
    kitchen.on_main({"d.txt": "theirs\n"})
    return heads


def record(kitchen):
    return json.loads((kitchen.home.state / batch.KEPT).read_text())


def in_batch(number, tip):
    return f"wait {number} {url(number)}: " + batch.IN_BATCH.format(base="main", tip=tip[:12])


def show(kitchen, commit, path):
    return git(kitchen.origin, "show", f"{commit}:{path}")


def listed(kitchen, checks, at=None):
    """GitHub lists the batch pull request at `at`, the head jmerge pushed by default, with these
    checks, beside every pull request not merged yet."""
    stub = kitchen.home.stub
    head = at or git(kitchen.origin, "rev-parse", f"refs/heads/{batch.BRANCH}")
    pull = {
        "number": 99,
        "url": url(99),
        "title": "jmerge: batch",
        "headRefName": batch.BRANCH,
        "headRefOid": head,
        "baseRefName": "main",
        "mergeable": "MERGEABLE",
        "statusCheckRollup": merge.rollup(checks),
        "files": [merge.file("a.txt")],
        "changedFiles": 1,
        "isDraft": True,
    }
    open_ = [p for p in kitchen.pulls.values() if not (stub / f"merged-{p['number']}").exists()]
    (stub / "list.json").write_text(json.dumps([*open_, pull]))


def proven(kitchen):
    """CI's check passed the batch pull request: it lists green, and its run left the artifact of
    the recorded tip's tree and the batch's tree."""
    kept = record(kitchen)
    listed(kitchen, (merge.PASSED,))
    base = git(kitchen.origin, "rev-parse", f"{kept['tip']}^{{tree}}")
    name = green.checked(base, kept["tree"])
    run = {"id": 5, "repository_id": 1, "head_repository_id": 1}
    found = {"artifacts": [{"name": name, "expired": False, "workflow_run": run}]}
    (kitchen.home.stub / f"artifact-{name}").write_text(json.dumps(found))
    ran = {
        "conclusion": "success",
        "path": green.WORKFLOW,
        "html_url": RUN,
        "repository": {"id": 1},
        "head_repository": {"id": 1},
    }
    (kitchen.home.stub / "run-5").write_text(json.dumps(ran))


def test_three_pull_requests_main_moved_past_are_built_into_one_batch_and_recorded(kitchen):
    heads = three(kitchen)
    tip = kitchen.tip()
    assert kitchen.run() == [in_batch(number, tip) for number in (6, 7, 8)]
    commit = git(kitchen.origin, "rev-parse", f"refs/heads/{batch.BRANCH}")
    assert git(kitchen.origin, "rev-list", "--parents", "-n", "1", commit).split() == [commit, tip]
    for name in ("a.txt", "b.txt", "c.txt"):
        assert show(kitchen, commit, name) == OURS.strip()
    assert show(kitchen, commit, "d.txt") == "theirs"
    tree = git(kitchen.origin, "rev-parse", f"{commit}^{{tree}}")
    kept = record(kitchen)
    assert (kept["tip"], kept["tree"], kept["commit"]) == (tip, tree, commit)
    assert [(one["number"], one["head"]) for one in kept["members"]] == list(
        zip((6, 7, 8), heads, strict=True)
    )
    (created,) = (kitchen.home.stub / "created").read_text().splitlines()
    assert "--draft" in created and f"--head {batch.BRANCH}" in created
    assert "--base main" in created
    assert kitchen.calls() == [] and runs(kitchen) == 0
    assert kitchen.tip() == tip


def test_a_batch_whose_check_passed_over_the_same_tip_merges_each_member_at_its_head(kitchen):
    heads = three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:3] for line in said] == [
        ["merged", "6", "one"],
        ["merged", "7", "two"],
        ["merged", "8", "three"],
    ]
    passed = batch.PASSED.format(base="main", tip=tip[:12], run=RUN)
    assert all(f", {passed}, " in line for line in said)
    merges = kitchen.calls()
    assert [call.split()[2] for call in merges] == ["6", "7", "8"]
    for call, head in zip(merges, heads, strict=True):
        assert f"--squash --match-head-commit {head} " in call
    assert runs(kitchen) == 0
    for name in ("a.txt", "b.txt", "c.txt"):
        assert kitchen.at_main(name) == OURS.strip()
    assert kitchen.at_main("d.txt") == "theirs"
    assert record(kitchen).get("members") is None
    logged = (kitchen.home.state / "merge.log").read_text()
    assert logged.count(passed) == 3


def test_a_proven_batch_stops_at_the_first_merge_github_refuses(kitchen):
    three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    proven(kitchen)
    (kitchen.home.stub / "refuse-7").write_text("")
    first, second, third = kitchen.run()
    assert first.startswith("merged 6 one ")
    assert second.startswith(f"wait 7 {url(7)}: {ready.MERGE_FAILED}: GraphQL")
    stopped = batch.STOPPED.format(base="main", tip=tip[:12], number=7)
    assert third == f"wait 8 {url(8)}: {stopped}"
    assert [call.split()[2] for call in kitchen.calls()] == ["6", "7"]
    assert runs(kitchen) == 0


def test_a_proven_batch_whose_merge_lock_another_run_holds_stays_proven_for_the_next_run(kitchen):
    three(kitchen)
    kitchen.run()
    proven(kitchen)
    held = MergeLock(kitchen.home.state)
    assert held.take()
    try:
        merging = f"{ready.MERGING}"
        assert kitchen.run() == [f"wait {n} {url(n)}: {merging}" for n in (6, 7, 8)]
    finally:
        held.give()
    assert kitchen.calls() == []
    assert [line.split()[:2] for line in kitchen.run()] == [
        ["merged", "6"],
        ["merged", "7"],
        ["merged", "8"],
    ]


def test_a_batch_whose_tip_moved_merges_nothing_and_is_built_again_over_the_new_tip(kitchen):
    three(kitchen)
    kitchen.run()
    proven(kitchen)
    moved = kitchen.on_main({"d.txt": "theirs again\n"})
    assert kitchen.run() == [in_batch(number, moved) for number in (6, 7, 8)]
    assert kitchen.calls() == []
    commit = git(kitchen.origin, "rev-parse", f"refs/heads/{batch.BRANCH}")
    assert record(kitchen)["tip"] == moved and record(kitchen)["commit"] == commit
    assert show(kitchen, commit, "d.txt") == "theirs again"
    assert len((kitchen.home.stub / "created").read_text().splitlines()) == 1


def test_a_batch_whose_check_failed_sends_each_member_down_the_single_path(kitchen):
    three(kitchen)
    kitchen.run()
    listed(kitchen, (merge.FAILED,))
    said = kitchen.run()
    assert [line.split()[:3] for line in said] == [
        ["merged", "6", "one"],
        ["merged", "7", "two"],
        ["merged", "8", "three"],
    ]
    assert all(", the guards passed on its tree merged over main at " in line for line in said)
    assert runs(kitchen) == 3


def test_a_batch_still_checked_holds_its_members_and_the_rest_wait_for_it(kitchen):
    three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    listed(kitchen, (merge.RUNNING,))
    kitchen.crew("four", 9, {"e.txt": OURS})
    listed(kitchen, (merge.RUNNING,))
    after = batch.AFTER.format(base="main", tip=tip[:12])
    assert kitchen.run() == [in_batch(number, tip) for number in (6, 7, 8)] + [
        f"wait 9 {url(9)}: {after}"
    ]
    assert kitchen.calls() == [] and runs(kitchen) == 0


@pytest.mark.parametrize("on", [True, False], ids=["batching on", "batching off"])
def test_jmerge_never_judges_the_batch_pull_request(kitchen, on):
    three(kitchen)
    kitchen.run()
    if not on:
        (kitchen.home.state / batch.SWITCH).unlink()
    listed(kitchen, (merge.RUNNING,))
    said = kitchen.run("--check") + kitchen.run()
    assert [line for line in said if " 99 " in f"{line} "] == []


def test_a_revert_stays_out_of_the_batch_and_merges_first_on_its_own_path(kitchen):
    jbus = queue_of(kitchen.home, []).parent
    kitchen.crew("one", 6, {"a.txt": OURS})
    kitchen.crew("revert-it", 9, {"b.txt": OURS})
    named(jbus, ("revert-it", url(9)))
    kitchen.on_main({"d.txt": "theirs\n"})
    first, second = kitchen.run()
    assert first.startswith("merged 9 revert-it ")
    assert second == in_batch(6, kitchen.tip())
    assert [one["number"] for one in record(kitchen)["members"]] == [6]


def test_a_second_migration_stays_out_of_the_batch(kitchen):
    queue_of(kitchen.home, [], DIRECTORY)
    kitchen.crew("one", 6, {"db/migrations/0005_one.up.sql": "select 1;\n"})
    kitchen.crew("two", 7, {"db/migrations/0006_two.up.sql": "select 2;\n"})
    for pull in kitchen.pulls.values():
        for one in pull["files"]:
            one["changeType"] = "ADDED"
    (kitchen.home.stub / "list.json").write_text(json.dumps(list(kitchen.pulls.values())))
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    merging = ready.MIGRATION_MERGING.format(number=6)
    assert kitchen.run() == [f"wait 7 {url(7)}: {merging}", in_batch(6, tip)]
    assert [one["number"] for one in record(kitchen)["members"]] == [6]


def test_a_pull_request_whose_merge_after_is_unmet_stays_out_of_the_batch(kitchen):
    queue_of(kitchen.home, [row("one", pr="#6"), row("two", pr="#7", merge_after=["one"])])
    kitchen.crew("one", 6, {"a.txt": OURS})
    kitchen.crew("two", 7, {"b.txt": OURS})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    first, second = kitchen.run()
    assert first.startswith(f"wait 7 {url(7)}: merges after one ")
    assert second == in_batch(6, tip)
    assert [one["number"] for one in record(kitchen)["members"]] == [6]
