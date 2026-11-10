"""Where the state has a `merge-batch` file, `jmerge` proves the pull requests that main moved past
together: it builds main's tip with each of them merged in, force-pushes that commit to its own
`jmerge/batch` branch under one standing draft pull request, and keeps the tip, the tree and the
members in `batch.json`. CI's check of that pull request leaves the artifact of the two trees
(`green.checked`), and on it `jmerge` squash-merges each member at its own head, in merge order,
with no guards run. A batch holds three members at least (`batch.LEAST`): fewer judged in a run
each take the single path of today, as does each suspect of a failed batch whose half would hold
fewer, while a larger half is narrowed by the checks of the next batches.

The tests run the `jmerge` command (`jmerge.cli`) against a real origin and the fake `gh` of
`test_jmerge_fresh.Kitchen`, which also opens a pull request, refuses one merge by number, and
answers the artifact and run lookups from files of the stub."""

import json
from datetime import UTC, datetime, timedelta

import pytest

import test_home_merge as merge
import test_jmerge_fresh as fresh
from jmerge import batch, green, ready, treeguards
from jmerge.lock import MergeLock
from test_jmerge_fresh import AFTER as LATER
from test_jmerge_fresh import CONFLICT, GH, LINES, Kitchen, git, url
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
    "run rerun")
        if [ -e "$STUB/rerun-refused" ]; then
            echo "run 5 cannot be rerun; its workflow file may be broken" >&2
            exit 1
        fi ;;
"""
BATCH_GH = (
    GH.replace('case "$1 $2" in\n', 'case "$1 $2" in\n' + CREATE, 1)
    .replace(
        'if [ -e "$STUB/merge-refused" ]; then',
        'if [ -e "$STUB/merge-refused" ] || [ -e "$STUB/refuse-$3" ]; then',
        1,
    )
    .replace(
        'echo "$commit" > "$STUB/merged-$3" ;;',
        'echo "$commit" > "$STUB/merged-$3"\n'
        '        if [ -e "$STUB/also-$3" ]; then\n'
        '            again=$(git -C "$ORIGIN" commit-tree "$tree" -p "$commit" -m "by hand")\n'
        '            git -C "$ORIGIN" update-ref refs/heads/main "$again"\n'
        "        fi ;;",
        1,
    )
)
assert BATCH_GH.count("pr create") == 1 and "refuse-$3" in BATCH_GH and "also-$3" in BATCH_GH
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


def more(kitchen, *numbers):
    """A ready pull request for each of `numbers`, each on a new file of its own, after `three`."""
    return [kitchen.crew(f"pr{n}", n, {f"f{n}.txt": OURS}) for n in numbers]


def alone(line, number):
    """Whether `line` merged `number` on the guards of its merged tree, the single path."""
    merged = line.startswith(f"merged {number} ")
    return merged and ", the guards passed on its tree merged over main at " in line


def pushed(kitchen):
    """The commit at `jmerge/batch` on the origin, or None where none was ever pushed."""
    at = git(kitchen.origin, "for-each-ref", "--format=%(objectname)", f"refs/heads/{batch.BRANCH}")
    return at or None


def record(kitchen):
    return json.loads((kitchen.home.state / batch.KEPT).read_text())


def in_batch(number, tip):
    return f"wait {number} {url(number)}: " + ready.IN_BATCH.format(base="main", tip=tip[:12])


def built(size, tip, most=12):
    """The line of a batch of `size` members built over main at `tip`."""
    return batch.BUILT.format(size=size, most=most, base="main", tip=tip[:12])


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
    assert kitchen.run() == [built(3, tip), *(in_batch(number, tip) for number in (6, 7, 8))]
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
    stopped = ready.BATCH_STOPPED.format(base="main", tip=tip[:12], number=7)
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
    assert kitchen.run() == [built(3, moved), *(in_batch(number, moved) for number in (6, 7, 8))]
    assert kitchen.calls() == []
    commit = git(kitchen.origin, "rev-parse", f"refs/heads/{batch.BRANCH}")
    assert record(kitchen)["tip"] == moved and record(kitchen)["commit"] == commit
    assert show(kitchen, commit, "d.txt") == "theirs again"
    assert len((kitchen.home.stub / "created").read_text().splitlines()) == 1


def first(number, tip):
    return f"wait {number} {url(number)}: " + ready.BATCH_FIRST.format(base="main", tip=tip[:12])


def suspects(kitchen):
    return [one["number"] for one in record(kitchen).get("suspects", [])]


def test_a_failed_batch_keeps_its_members_as_suspects_and_builds_the_first_half_of_them(kitchen):
    """A failed batch of six runs no guards: its members are suspects, and the next batch is the
    first half of them, three, over today's tip, on the same branch and pull request."""
    heads = three(kitchen) + more(kitchen, 9, 10, 11)
    kitchen.run()
    listed(kitchen, (merge.FAILED,))
    tip = kitchen.tip()
    said = kitchen.run()
    assert said == [built(3, tip), *(in_batch(n, tip) for n in (6, 7, 8))] + [
        first(n, tip) for n in (9, 10, 11)
    ]
    assert kitchen.calls() == [] and runs(kitchen) == 0
    kept = record(kitchen)
    assert [(one["number"], one["head"]) for one in kept["members"]] == list(
        zip((6, 7, 8), heads[:3], strict=True)
    )
    assert kept["tip"] == tip and kept["failed"] == {}
    assert suspects(kitchen) == [6, 7, 8, 9, 10, 11]
    commit = pushed(kitchen)
    assert kept["commit"] == commit and show(kitchen, commit, "c.txt") == OURS.strip()
    assert "f9.txt" not in git(kitchen.origin, "ls-tree", "--name-only", commit).split()
    assert len((kitchen.home.stub / "created").read_text().splitlines()) == 1


def test_a_failed_batch_of_four_sends_each_member_down_the_single_path(kitchen):
    """Its halves would hold two, under the three a batch holds, so each suspect merges on the
    guards of its merged tree in that run, its head under `failed`, and no batch is pushed."""
    heads = three(kitchen) + more(kitchen, 9)
    kitchen.run()
    assert [one["number"] for one in record(kitchen)["members"]] == [6, 7, 8, 9]
    commit = pushed(kitchen)
    listed(kitchen, (merge.FAILED,))
    said = kitchen.run()
    assert [alone(line, n) for line, n in zip(said, (6, 7, 8, 9), strict=True)] == [True] * 4
    assert runs(kitchen) == 4 and pushed(kitchen) == commit
    assert record(kitchen)["failed"] == {
        str(n): head for n, head in zip((6, 7, 8, 9), heads, strict=True)
    }
    assert suspects(kitchen) == [] and record(kitchen).get("members") is None


def test_the_suspects_left_by_a_proven_half_under_three_go_alone_as_it_merges(kitchen):
    """A failed batch of six narrows to its first half of three; that half proves and merges by
    batch, and the three suspects left, whose half would hold two, merge alone in the same run."""
    three(kitchen)
    more(kitchen, 9, 10, 11)
    kitchen.run()
    listed(kitchen, (merge.FAILED,))
    kitchen.run()
    commit = pushed(kitchen)
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said[:3]] == [["merged", n] for n in ("6", "7", "8")]
    assert all("so no guards ran" in line for line in said[:3])
    assert [alone(line, n) for line, n in zip(said[3:], (9, 10, 11), strict=True)] == [True] * 3
    assert runs(kitchen) == 3 and pushed(kitchen) == commit
    assert suspects(kitchen) == [] and record(kitchen).get("members") is None


@pytest.mark.parametrize("count", [1, 2])
def test_fewer_than_three_members_merge_on_the_guards_with_no_batch(kitchen, count):
    """A batch's check took 209 s at the median, the guards about 98 s, so one or two members
    each take the single path in the run that judged them: no push to `jmerge/batch`, no batch
    pull request, and no pull request waits for a batch."""
    kitchen.crew("one", 6, {"a.txt": OURS})
    if count == 2:
        kitchen.crew("two", 7, {"b.txt": OURS})
    kitchen.on_main({"d.txt": "theirs\n"})
    said = kitchen.run()
    assert [alone(line, n) for line, n in zip(said, (6, 7), strict=False)] == [True] * count
    assert len(said) == count and runs(kitchen) == count
    assert pushed(kitchen) is None and not (kitchen.home.stub / "created").exists()
    assert record(kitchen).get("members") is None and suspects(kitchen) == []


def test_a_batch_still_checked_holds_its_members_and_the_rest_wait_for_it(kitchen):
    three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    listed(kitchen, (merge.RUNNING,))
    kitchen.crew("four", 9, {"e.txt": OURS})
    kitchen.crew("five", 10, {"f.txt": OURS}, checks=(LATER,))
    listed(kitchen, (merge.RUNNING,))
    after = ready.BATCH_FIRST.format(base="main", tip=tip[:12])
    assert kitchen.run() == [
        f"wait 10 {url(10)}: {after}",
        *(in_batch(number, tip) for number in (6, 7, 8)),
        f"wait 9 {url(9)}: {after}",
    ]
    assert kitchen.calls() == [] and runs(kitchen) == 0


def test_a_batch_left_with_fewer_than_three_members_holds_no_pull_request_for_it(kitchen):
    """#8's head moved while the batch was checked, so two of its members are judged: no batch
    is built again, and #10, which would merge alone, merges in that run with #6 and #7 rather
    than wait for a batch that is gone."""
    three(kitchen)
    kitchen.run()
    commit = pushed(kitchen)
    tree = kitchen.tmp / "trees" / "three"
    (tree / "c.txt").write_text("changed after the review\n" + LINES)
    git(tree, "commit", "-qam", "late")
    git(tree, "push", "-q")
    kitchen.pulls["three"]["headRefOid"] = git(tree, "rev-parse", "HEAD")
    kitchen.crew("five", 10, {"f.txt": OURS}, checks=(LATER,))
    listed(kitchen, (merge.RUNNING,), at=commit)
    said = kitchen.run()
    assert not [line for line in said if "merges first" in line]
    assert [line.split()[:2] for line in said] == [
        ["wait", "8"],
        ["merged", "10"],
        ["merged", "6"],
        ["merged", "7"],
    ]
    assert alone(said[2], 6) and alone(said[3], 7)
    assert pushed(kitchen) == commit and record(kitchen).get("members") is None


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
    three(kitchen)
    kitchen.crew("revert-it", 9, {"e.txt": OURS})
    named(jbus, ("revert-it", url(9)))
    first, *second = kitchen.run()
    assert first.startswith("merged 9 revert-it ")
    tip = kitchen.tip()
    assert second == [built(3, tip), *(in_batch(n, tip) for n in (6, 7, 8))]
    assert [one["number"] for one in record(kitchen)["members"]] == [6, 7, 8]


def test_a_second_migration_stays_out_of_the_batch(kitchen):
    queue_of(kitchen.home, [], DIRECTORY)
    kitchen.crew("one", 6, {"db/migrations/0005_one.up.sql": "select 1;\n"})
    kitchen.crew("two", 7, {"db/migrations/0006_two.up.sql": "select 2;\n"})
    more(kitchen, 8, 9)
    for pull in kitchen.pulls.values():
        for one in pull["files"]:
            one["changeType"] = "ADDED"
    (kitchen.home.stub / "list.json").write_text(json.dumps(list(kitchen.pulls.values())))
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    merging = ready.MIGRATION_MERGING.format(number=6)
    assert kitchen.run() == [
        f"wait 7 {url(7)}: {merging}",
        built(3, tip),
        *(in_batch(n, tip) for n in (6, 8, 9)),
    ]
    assert [one["number"] for one in record(kitchen)["members"]] == [6, 8, 9]


def test_a_pull_request_whose_merge_after_is_unmet_stays_out_of_the_batch(kitchen):
    rows = [row(slug, pr=f"#{n}") for slug, n in (("one", 6), ("two", 7), ("three", 8))]
    queue_of(kitchen.home, [*rows, row("pr9", pr="#9", merge_after=["one"])])
    three(kitchen)
    more(kitchen, 9)
    tip = kitchen.tip()
    first, *second = kitchen.run()
    assert first.startswith(f"wait 9 {url(9)}: merges after one ")
    assert second == [built(3, tip), *(in_batch(n, tip) for n in (6, 7, 8))]
    assert [one["number"] for one in record(kitchen)["members"]] == [6, 7, 8]


def late(kitchen, checks):
    """The batch out was pushed `PENDING_MINUTES` and a second ago, with no artifact found, and
    GitHub lists its pull request with these checks."""
    at = datetime.now(UTC) - timedelta(minutes=batch.PENDING_MINUTES, seconds=1)
    kept = record(kitchen)
    (kitchen.home.state / batch.KEPT).write_text(json.dumps({**kept, "at": at.isoformat()}))
    listed(kitchen, checks)


TIMED_OUT = pytest.mark.parametrize(
    "checks",
    [(merge.RUNNING,), (merge.PASSED,)],
    ids=["check still running", "passed, no artifact"],
)


@TIMED_OUT
def test_a_batch_that_timed_out_is_built_again_whole_and_merges_by_batch_once_proven(
    kitchen, checks
):
    """A timeout is no evidence against a member: the batch is built again whole over today's
    tip, keeps no suspects, and merges by batch on its pass."""
    three(kitchen)
    kitchen.run()
    late(kitchen, checks)
    tip = kitchen.tip()
    assert kitchen.run() == [built(3, tip), *(in_batch(number, tip) for number in (6, 7, 8))]
    assert [one["number"] for one in record(kitchen)["members"]] == [6, 7, 8]
    assert suspects(kitchen) == [] and record(kitchen)["failed"] == {}
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", n] for n in ("6", "7", "8")]
    assert all("so no guards ran" in line for line in said)
    assert runs(kitchen) == 0 and suspects(kitchen) == []


@TIMED_OUT
def test_a_batch_that_timed_out_twice_in_a_row_sends_its_three_members_alone(kitchen, checks):
    """The second timeout fails the batch, and its half of three would hold two."""
    three(kitchen)
    kitchen.run()
    late(kitchen, checks)
    kitchen.run()
    late(kitchen, checks)
    said = kitchen.run()
    assert [alone(line, n) for line, n in zip(said, (6, 7, 8), strict=True)] == [True] * 3
    assert runs(kitchen) == 3 and suspects(kitchen) == []


def failed_in(job):
    """The batch's check failed in job `job` of its workflow run 5: a new attempt of the run gives
    its jobs new ids."""
    return {**merge.FAILED, "detailsUrl": f"https://github.com/o/r/actions/runs/5/job/{job}"}


def reruns(kitchen):
    return [call.split()[:4] for call in kitchen.calls("run rerun")]


def test_a_failed_batch_reruns_its_failed_jobs_once_and_merges_by_batch_when_they_pass(kitchen):
    """A flake is no evidence against a member: the failed jobs of the batch's run are started
    again once, the batch is pending while they run, from the rerun and not its push, and on
    their pass its members merge by the batch with no suspects kept."""
    three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    late(kitchen, (failed_in(1),))
    assert kitchen.run() == [in_batch(number, tip) for number in (6, 7, 8)]
    assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
    listed(kitchen, (merge.RUNNING,))
    assert kitchen.run() == [in_batch(number, tip) for number in (6, 7, 8)]
    assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
    assert suspects(kitchen) == [] and record(kitchen)["again"] is False
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", n] for n in ("6", "7", "8")]
    assert all("so no guards ran" in line for line in said)
    assert runs(kitchen) == 0 and suspects(kitchen) == [] and record(kitchen)["failed"] == {}


@pytest.mark.parametrize("case", ["fails again", "rerun refused", "first attempt still listed"])
def test_a_batch_that_fails_again_after_its_rerun_fails_as_a_failed_check_does(kitchen, case):
    """A second failure, a new job of the run, and a rerun GitHub refuses each fail the batch as
    a failed check did before the rerun: its members are suspects and the next batch is the first
    half of them. A listing that still shows the first attempt's failed job is no second failure:
    the batch stays pending, and is not rerun again."""
    three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    if case == "rerun refused":
        (kitchen.home.stub / "rerun-refused").write_text("")
    listed(kitchen, (failed_in(1),))
    said = kitchen.run()
    if case != "rerun refused":
        assert said == [in_batch(number, tip) for number in (6, 7, 8)]
        listed(kitchen, (failed_in(2 if case == "fails again" else 1),))
        said = kitchen.run()
    assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
    if case == "first attempt still listed":
        assert said == [in_batch(number, tip) for number in (6, 7, 8)]
        assert suspects(kitchen) == []
        assert runs(kitchen) == 0 and kitchen.calls() == []
    else:
        assert [alone(line, n) for line, n in zip(said, (6, 7, 8), strict=True)] == [True] * 3
        assert runs(kitchen) == 3 and suspects(kitchen) == []


BORDERS_FAILED = {
    **merge.run("FAILURE", "borders"),
    "detailsUrl": "https://github.com/o/r/actions/runs/6/job/9",
}


@pytest.mark.parametrize("check", ["running", "passed", "failed"])
def test_a_batch_is_judged_by_its_check_and_never_by_borders_on_its_own_diff(kitchen, check):
    """The repo requires `check` and `borders`, and the batch's pull request fails `borders`, as
    one whose members touch two features does: each member passed `borders` at its own head. The
    batch waits while `check` runs or passed with no artifact found, and merges once the artifact
    is found, with no rerun asked for. A failed `check` reruns its own run alone, once, and its
    second failure sends each of the three members down the single path, as with no `borders`
    failure beside it."""
    (kitchen.home.state / "required-checks").write_text("check\nborders\n")
    heads = three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    waiting = [in_batch(number, tip) for number in (6, 7, 8)]
    if check == "failed":
        listed(kitchen, (BORDERS_FAILED, failed_in(1)))
        assert kitchen.run() == waiting
        assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
        listed(kitchen, (BORDERS_FAILED, failed_in(2)))
        said = kitchen.run()
        assert [alone(line, n) for line, n in zip(said, (6, 7, 8), strict=True)] == [True] * 3
        assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
        assert record(kitchen)["failed"] == dict(zip(("6", "7", "8"), heads, strict=True))
        assert suspects(kitchen) == []
        return
    listed(kitchen, (BORDERS_FAILED, merge.RUNNING if check == "running" else merge.PASSED))
    assert kitchen.run() == waiting
    assert reruns(kitchen) == [] and suspects(kitchen) == []
    proven(kitchen)
    listed(kitchen, (BORDERS_FAILED, merge.PASSED))
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", n] for n in ("6", "7", "8")]
    assert reruns(kitchen) == [] and suspects(kitchen) == [] and runs(kitchen) == 0


def test_a_batch_that_passed_with_no_artifact_found_waits_and_merges_once_it_is_found(kitchen):
    three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    listed(kitchen, (merge.PASSED,))
    assert kitchen.run() == [in_batch(number, tip) for number in (6, 7, 8)]
    assert kitchen.calls() == [] and runs(kitchen) == 0
    assert record(kitchen)["failed"] == {}
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [
        ["merged", "6"],
        ["merged", "7"],
        ["merged", "8"],
    ]
    assert runs(kitchen) == 0


def test_a_member_that_conflicts_with_one_before_it_waits_for_the_batch(kitchen):
    three(kitchen)
    kitchen.crew("four", 9, {"a.txt": "theirs too\n" + LINES})
    tip = kitchen.tip()
    assert kitchen.run() == [built(3, tip), *(in_batch(n, tip) for n in (6, 7, 8)), first(9, tip)]
    assert [one["number"] for one in record(kitchen)["members"]] == [6, 7, 8]


def test_a_batch_holds_its_most_members_and_leaves_the_rest_out(kitchen):
    heads = three(kitchen)
    tip = kitchen.tip()
    git(kitchen.home.main, "fetch", "-q", "origin")
    members = [batch.Member(n, head) for n, head in zip((6, 7, 8), heads, strict=True)]
    built = batch.build(kitchen.home.main, "main", tip, members, 2)
    assert built.members == tuple(members[:2])
    assert git(kitchen.home.main, "show", f"{built.commit}:b.txt") == OURS.strip()
    assert git(kitchen.home.main, "show", f"{built.commit}:c.txt") == LINES.strip()


def refuses_batches(kitchen):
    """The origin refuses every push to the batch's branch."""
    hook = kitchen.origin / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "while read -r old new ref; do\n"
        f'    [ "$ref" = refs/heads/{batch.BRANCH} ] && echo "no batch here" >&2 && exit 1\n'
        "done\n"
        "exit 0\n"
    )
    hook.chmod(0o755)


def test_a_batch_the_origin_refuses_sends_each_member_down_the_single_path(kitchen):
    refuses_batches(kitchen)
    three(kitchen)
    tip = kitchen.tip()
    unmade, *said = kitchen.run()
    assert unmade.startswith(f"batch: not made over main at {tip[:12]} (")
    assert [line.split()[:2] for line in said] == [
        ["merged", "6"],
        ["merged", "7"],
        ["merged", "8"],
    ]
    assert runs(kitchen) == 3


def test_a_batch_of_fewer_than_three_once_conflicts_are_left_out_sends_them_alone(kitchen):
    """#8 and #9 clash with #6's line, so two of the four merge over the tip: no batch is pushed,
    and each member goes down the single path, where #8 and #9 wait for their rebase."""
    kitchen.crew("one", 6, {"a.txt": OURS})
    kitchen.crew("two", 7, {"b.txt": OURS})
    kitchen.crew("three", 8, {"a.txt": "theirs three\n" + LINES})
    kitchen.crew("four", 9, {"a.txt": "theirs four\n" + LINES})
    tip = kitchen.on_main({"d.txt": "theirs\n"})[:12]
    unmade, *said = kitchen.run()
    why = f"2 merge over main at {tip}, and a batch holds 3 at least"
    assert unmade == batch.UNMADE.format(base="main", tip=tip, why=why)
    assert alone(said[0], 6) and alone(said[1], 7)
    assert said[2:] == [f"wait 8 {url(8)}: {CONFLICT}", f"wait 9 {url(9)}: {CONFLICT}"]
    assert pushed(kitchen) is None


def test_a_proven_batch_stops_at_a_member_no_longer_ready_at_its_head(kitchen):
    three(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    tree = kitchen.tmp / "trees" / "two"
    (tree / "b.txt").write_text("changed after the review\n" + LINES)
    git(tree, "commit", "-qam", "late")
    git(tree, "push", "-q")
    kitchen.pulls["two"]["headRefOid"] = git(tree, "rev-parse", "HEAD")
    proven(kitchen)
    own, merged, stopped = kitchen.run()
    assert own.startswith(f"wait 7 {url(7)}: ")
    assert merged.startswith("merged 6 one ")
    assert stopped == f"wait 8 {url(8)}: " + ready.BATCH_STOPPED.format(
        base="main", tip=tip[:12], number=7
    )
    assert [call.split()[2] for call in kitchen.calls()] == ["6"]


def test_a_proven_batch_stops_where_another_hand_moved_main_between_its_merges(kitchen):
    three(kitchen)
    kitchen.run()
    proven(kitchen)
    (kitchen.home.stub / "also-6").write_text("")
    merged, *said = kitchen.run()
    assert merged.startswith("merged 6 one ")
    moved = ready.MAIN_MOVED.format(base="main")
    assert said == [f"wait {n} {url(n)}: {moved}" for n in (7, 8)]
    assert [call.split()[2] for call in kitchen.calls()] == ["6"]


def test_a_squash_whose_messages_cannot_be_read_waits_and_gives_no_commit(kitchen, monkeypatch):
    """`Repo.squash`, which a single merge and each merge of a batch end in, merges nothing
    where git cannot list the branch's messages for the squash's body, and gives no commit, so
    a batch stops there."""
    kitchen.crew("one", 6, {"a.txt": OURS})
    here = fresh.repo(kitchen, monkeypatch)
    monkeypatch.setattr(here, "messages", lambda one: None)
    one = ready.pull_request(kitchen.pulls["one"])
    assert here.squash(one, "one", []) == (f"wait 6 {url(6)}: {ready.NO_MESSAGES}", "")
    assert not (kitchen.home.stub / "calls").exists()


PRINTED = (
    "it is in jmerge's batch over main at eca6f811b913, whose check decides its merge",
    "jmerge's batch over main at eca6f811b913 is checked and merges first: a merge before it "
    "would undo that check",
    "jmerge's batch over main at eca6f811b913 stopped at #7, which did not merge: the next batch "
    "takes it",
)
"""Each wait jmerge prints of a pull request held by a batch, as `jmerge` printed the first of
#1574 on 2026-11-10: a printed line has no code, so jbus reads its step off the text."""


@pytest.mark.parametrize("said", PRINTED)
def test_a_batch_wait_as_jmerge_prints_it_is_on_the_step_of_a_wait_on_its_own_check(said):
    """CI's check of the batch decides its members' merge, so a wait on the batch is on the step
    of a pull request that waits on its own check, and a rule of `rules` names it."""
    assert ready.step_of(ready.code_of(said)) == ready.LIVE_RUN.step == "check"


def most(kitchen):
    return record(kitchen)["most"]


def ends(kitchen, size, how, narrowed=False):
    """The batch out holds `size` members and ends `how` (a method of `batch.Record`), in a run
    that reads `batch.json` and writes it back."""
    kept = batch.Record.read(kitchen.home.state)
    members = tuple(batch.Member(n, f"{n:040x}") for n in range(1, size + 1))
    at = datetime.now(UTC)
    kept.batch = batch.Batch("1" * 40, "2" * 40, "3" * 40, members, at, narrowed=narrowed)
    getattr(kept, how)()
    kept.write()
    return most(kitchen)


def test_the_most_a_batch_takes_doubles_after_a_pass_and_halves_after_a_fail(kitchen):
    """The most starts at 12. A batch of that many doubles it when it proves, to 48 at most, and
    halves it when it fails after its rerun, to 3 at least. A batch of fewer, a narrowed batch of
    suspects, a timeout and a batch never made leave it, and a proven batch that waits for the
    merge lock across runs counts once."""
    assert batch.Record.read(kitchen.home.state).most == 12
    assert ends(kitchen, 12, "prove") == 24
    assert ends(kitchen, 24, "prove") == 24 * 2 == ends(kitchen, 24, "prove")
    assert ends(kitchen, 48, "prove") == 48
    assert ends(kitchen, 47, "fail") == 48
    assert ends(kitchen, 48, "fail") == 24
    assert ends(kitchen, 23, "prove") == 24
    assert ends(kitchen, 24, "late") == 24 == ends(kitchen, 24, "late")
    assert ends(kitchen, 24, "fail", narrowed=True) == 24
    assert ends(kitchen, 24, "prove", narrowed=True) == 24
    refuses_batches(kitchen)
    three(kitchen)
    unmade, *_ = kitchen.run()
    assert unmade.startswith("batch: not made over main ")
    assert most(kitchen) == 24
    assert [ends(kitchen, n, "fail") for n in (24, 12, 6, 3)] == [12, 6, 3, 3]


def test_building_a_batch_says_its_size_and_the_most(kitchen):
    """The line is about no pull request, so jbus reads nothing of it, and merge.log keeps it. A
    most kept under three is read as three, the fewest a batch holds."""
    (kitchen.home.state / batch.KEPT).write_text(json.dumps({"most": 2}))
    three(kitchen)
    more(kitchen, 9)
    tip = kitchen.tip()
    line = f"batch: built over main at {tip[:12]}, 3 of 3 members at most"
    assert kitchen.run() == [line, *(in_batch(n, tip) for n in (6, 7, 8)), first(9, tip)]
    log = (kitchen.home.state / "merge.log").read_text().splitlines()
    assert sum(one.endswith(" " + line) for one in log) == 1
