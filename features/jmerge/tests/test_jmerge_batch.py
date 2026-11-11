"""Where the state has a `merge-batch` file, `jmerge` proves the pull requests that main moved past
together: it builds main's tip with each of them merged in, force-pushes that commit to its own
`jmerge/batch` branch under one standing draft pull request, and keeps the tip, the tree and the
members in `batch.json`. CI's check of that pull request leaves the artifact of the two trees
(`green.checked`), and on it `jmerge` squash-merges each member at its own head, in merge order,
with no guards run. CI's batch holds five members at least (`batch.LEAST`), and each suspect of a
failed batch whose half would hold fewer takes the single path, while a larger half is narrowed by
the checks of the next batches. Two to four members judged in a run share one guards run on their
tree in that run, pushed nowhere, and one takes the single path.

The tests run the `jmerge` command (`jmerge.cli`) against a real origin and the fake `gh` of
`test_jmerge_fresh.Kitchen`, which also opens a pull request, refuses one merge by number, and
answers the artifact and run lookups from files of the stub."""

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

import test_home_merge as merge
import test_jmerge_fresh as fresh
from jgauge import slot
from jmerge import batch, green, ready, treeguards
from jmerge.lock import MergeLock
from test_jmerge_fresh import AFTER as LATER
from test_jmerge_fresh import CONFLICT, GH, LINES, Kitchen, git, url, write
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


FIVE = (6, 7, 8, 9, 10)
"""The members of `five`, in merge order."""


def five(kitchen, at=None):
    """Five ready pull requests, the fewest CI's batch takes, each on a file of its own, whose
    checks main moved past, by a merge made now, or at `at`."""
    heads = [
        kitchen.crew(slug, number, {name: OURS})
        for slug, number, name in (
            ("one", 6, "a.txt"),
            ("two", 7, "b.txt"),
            ("three", 8, "c.txt"),
            ("four", 9, "e.txt"),
            ("five", 10, "f.txt"),
        )
    ]
    if at is None:
        kitchen.on_main({"d.txt": "theirs\n"})
        return heads
    main = kitchen.home.main
    git(main, "pull", "-q", "--ff-only")
    write(main, {"d.txt": "theirs\n"})
    git(main, "commit", "-qam", "by hand", at=at)
    git(main, "push", "-q")
    return heads


BY_HAND = "2010-01-01T00:00:00Z"
"""When main moved past the checks of `five`, in the tests of a pull request held for the batch."""
HELD = {**merge.PASSED, "startedAt": "2020-01-01T00:00:00Z"}
"""A check that started after main moved at `BY_HAND`, and before the batch's merges, made now:
its pull request would merge alone while the batch is out, and is a member once it merged."""


def more(kitchen, *numbers):
    """A ready pull request for each of `numbers`, each on a new file of its own, after `three`
    or `five`."""
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


def test_five_pull_requests_main_moved_past_are_built_into_one_batch_and_recorded(kitchen):
    heads = five(kitchen)
    tip = kitchen.tip()
    assert kitchen.run() == [built(5, tip), *(in_batch(number, tip) for number in FIVE)]
    commit = git(kitchen.origin, "rev-parse", f"refs/heads/{batch.BRANCH}")
    assert git(kitchen.origin, "rev-list", "--parents", "-n", "1", commit).split() == [commit, tip]
    for name in ("a.txt", "b.txt", "c.txt", "e.txt", "f.txt"):
        assert show(kitchen, commit, name) == OURS.strip()
    assert show(kitchen, commit, "d.txt") == "theirs"
    tree = git(kitchen.origin, "rev-parse", f"{commit}^{{tree}}")
    kept = record(kitchen)
    assert (kept["tip"], kept["tree"], kept["commit"]) == (tip, tree, commit)
    assert [(one["number"], one["head"]) for one in kept["members"]] == list(
        zip(FIVE, heads, strict=True)
    )
    (created,) = (kitchen.home.stub / "created").read_text().splitlines()
    assert "--draft" in created and f"--head {batch.BRANCH}" in created
    assert "--base main" in created
    assert kitchen.calls() == [] and runs(kitchen) == 0
    assert kitchen.tip() == tip


def test_a_batch_whose_check_passed_over_the_same_tip_merges_each_member_at_its_head(kitchen):
    heads = five(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:3] for line in said] == [
        ["merged", "6", "one"],
        ["merged", "7", "two"],
        ["merged", "8", "three"],
        ["merged", "9", "four"],
        ["merged", "10", "five"],
    ]
    passed = batch.PASSED.format(base="main", tip=tip[:12], run=RUN)
    assert all(f", {passed}, " in line for line in said)
    merges = kitchen.calls()
    assert [call.split()[2] for call in merges] == [str(n) for n in FIVE]
    for call, head in zip(merges, heads, strict=True):
        assert f"--squash --match-head-commit {head} " in call
    assert runs(kitchen) == 0
    for name in ("a.txt", "b.txt", "c.txt", "e.txt", "f.txt"):
        assert kitchen.at_main(name) == OURS.strip()
    assert kitchen.at_main("d.txt") == "theirs"
    assert record(kitchen).get("members") is None
    logged = (kitchen.home.state / "merge.log").read_text()
    assert logged.count(passed) == 5


def test_a_proven_batch_stops_at_the_first_merge_github_refuses(kitchen):
    five(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    proven(kitchen)
    (kitchen.home.stub / "refuse-7").write_text("")
    first, second, *rest = kitchen.run()
    assert first.startswith("merged 6 one ")
    assert second.startswith(f"wait 7 {url(7)}: {ready.MERGE_FAILED}: GraphQL")
    stopped = ready.BATCH_STOPPED.format(base="main", tip=tip[:12], number=7)
    assert rest == [f"wait {n} {url(n)}: {stopped}" for n in (8, 9, 10)]
    assert [call.split()[2] for call in kitchen.calls()] == ["6", "7"]
    assert runs(kitchen) == 0


def test_a_proven_batch_whose_merge_lock_another_run_holds_stays_proven_for_the_next_run(kitchen):
    """#12, which would merge alone, came ready while the batch was checked: it waits for the batch
    while another run holds the merge lock, and merges after it in the run that merges it."""
    five(kitchen, BY_HAND)
    tip = kitchen.tip()
    kitchen.run()
    kitchen.crew("seven", 12, {"h.txt": OURS}, checks=(HELD,))
    proven(kitchen)
    held = MergeLock(kitchen.home.state)
    assert held.take()
    try:
        merging = f"{ready.MERGING}"
        assert kitchen.run() == [first(12, tip), *(f"wait {n} {url(n)}: {merging}" for n in FIVE)]
    finally:
        held.give()
    assert kitchen.calls() == []
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", str(n)] for n in (*FIVE, 12)]
    assert alone(said[-1], 12)


def test_a_pull_request_held_for_a_proven_batch_merges_alone_in_the_run_that_merges_it(kitchen):
    """#12 would merge alone while the batch of five was checked, so it waited for it. The run
    that merges the batch judges it again over the tip the batch left, and it merges there on
    the guards of its own tree, with no wait on a batch that is gone."""
    five(kitchen, BY_HAND)
    kitchen.run()
    kitchen.crew("seven", 12, {"h.txt": OURS}, checks=(HELD,))
    proven(kitchen)
    said = kitchen.run()
    assert not [line for line in said if "merges first" in line]
    assert [line.split()[:2] for line in said] == [["merged", str(n)] for n in (*FIVE, 12)]
    assert alone(said[-1], 12) and runs(kitchen) == 1
    assert kitchen.at_main("h.txt") == OURS.strip()
    assert record(kitchen).get("members") is None


def test_a_held_pull_request_and_a_late_member_share_a_guards_run_after_the_batch_merges(kitchen):
    """#12 was held for the batch, and #11 came ready after it was built, a member it had no
    room for: once the batch merges, the two are judged over the tip it left and share one
    guards run on their tree in that run."""
    five(kitchen, BY_HAND)
    kitchen.run()
    kitchen.crew("six", 11, {"g.txt": OURS})
    kitchen.crew("seven", 12, {"h.txt": OURS}, checks=(HELD,))
    proven(kitchen)
    said = kitchen.run()
    assert not [line for line in said if "merges first" in line]
    tip = git(kitchen.origin, "rev-parse", "refs/heads/main~2")
    assert [line.split()[:2] for line in said] == [
        *(["merged", str(n)] for n in FIVE),
        ["batch:", "guards"],
        ["merged", "11"],
        ["merged", "12"],
    ]
    assert said[5].startswith(guards_batch(2, tip, "passed")) and runs(kitchen) == 1


def test_a_held_pull_request_that_conflicts_with_the_batch_says_so_once_it_merged(kitchen):
    """#12 merged over the tip the batch was built on, and conflicts with #6 in it: once the batch
    merges, #12 waits for its rebase, and no longer for the batch."""
    five(kitchen, BY_HAND)
    kitchen.run()
    kitchen.crew("seven", 12, {"a.txt": "mine\n" + LINES}, checks=(HELD,))
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said[:5]] == [["merged", str(n)] for n in FIVE]
    assert said[5:] == [f"wait 12 {url(12)}: {ready.FRESH_CONFLICT}"]


def test_a_held_pull_request_whose_head_failed_a_batch_merges_alone_after_it(kitchen):
    """#12's head was in a failed batch, so it joins none at that head: once the batch merges, it
    merges alone, and #11, a member that came after the batch was built, does too, with no guards
    run of the two."""
    five(kitchen, BY_HAND)
    kitchen.run()
    kitchen.crew("six", 11, {"g.txt": OURS})
    head = kitchen.crew("seven", 12, {"h.txt": OURS}, checks=(HELD,))
    kept = record(kitchen)
    (kitchen.home.state / batch.KEPT).write_text(json.dumps({**kept, "failed": {"12": head}}))
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", str(n)] for n in (*FIVE, 12, 11)]
    assert alone(said[5], 12) and alone(said[6], 11) and runs(kitchen) == 2


def test_a_batch_whose_tip_moved_merges_nothing_and_is_built_again_over_the_new_tip(kitchen):
    five(kitchen)
    kitchen.run()
    proven(kitchen)
    moved = kitchen.on_main({"d.txt": "theirs again\n"})
    assert kitchen.run() == [built(5, moved), *(in_batch(number, moved) for number in FIVE)]
    assert kitchen.calls() == []
    commit = git(kitchen.origin, "rev-parse", f"refs/heads/{batch.BRANCH}")
    assert record(kitchen)["tip"] == moved and record(kitchen)["commit"] == commit
    assert show(kitchen, commit, "d.txt") == "theirs again"
    assert len((kitchen.home.stub / "created").read_text().splitlines()) == 1


def first(number, tip):
    return f"wait {number} {url(number)}: " + ready.BATCH_FIRST.format(base="main", tip=tip[:12])


def suspects(kitchen):
    return [one["number"] for one in record(kitchen).get("suspects", [])]


TEN = (*FIVE, 11, 12, 13, 14, 15)
"""The members of `five` and five more, a batch whose first half holds five."""


def test_a_failed_batch_keeps_its_members_as_suspects_and_builds_the_first_half_of_them(kitchen):
    """A failed batch of ten runs no guards: its members are suspects, and the next batch is the
    first half of them, five, over today's tip, on the same branch and pull request."""
    heads = five(kitchen) + more(kitchen, *TEN[5:])
    kitchen.run()
    listed(kitchen, (merge.FAILED,))
    tip = kitchen.tip()
    said = kitchen.run()
    assert said == [built(5, tip), *(in_batch(n, tip) for n in FIVE)] + [
        first(n, tip) for n in TEN[5:]
    ]
    assert kitchen.calls() == [] and runs(kitchen) == 0
    kept = record(kitchen)
    assert [(one["number"], one["head"]) for one in kept["members"]] == list(
        zip(FIVE, heads[:5], strict=True)
    )
    assert kept["tip"] == tip and kept["failed"] == {}
    assert suspects(kitchen) == list(TEN)
    commit = pushed(kitchen)
    assert kept["commit"] == commit and show(kitchen, commit, "f.txt") == OURS.strip()
    assert "f11.txt" not in git(kitchen.origin, "ls-tree", "--name-only", commit).split()
    assert len((kitchen.home.stub / "created").read_text().splitlines()) == 1


def test_a_failed_batch_of_five_sends_each_member_down_the_single_path(kitchen):
    """Its first half would hold three, under the five CI's batch holds, so each suspect merges
    on the guards of its own merged tree in that run, its head under `failed`, and no batch is
    pushed: the suspects hold a failure, so they share no guards run either."""
    heads = five(kitchen)
    kitchen.run()
    assert [one["number"] for one in record(kitchen)["members"]] == list(FIVE)
    commit = pushed(kitchen)
    listed(kitchen, (merge.FAILED,))
    said = kitchen.run()
    assert [alone(line, n) for line, n in zip(said, FIVE, strict=True)] == [True] * 5
    assert runs(kitchen) == 5 and pushed(kitchen) == commit
    assert record(kitchen)["failed"] == {str(n): head for n, head in zip(FIVE, heads, strict=True)}
    assert suspects(kitchen) == [] and record(kitchen).get("members") is None


def test_the_suspects_left_by_a_proven_half_under_five_go_alone_as_it_merges(kitchen):
    """A failed batch of ten narrows to its first half of five; that half proves and merges by
    batch, and the five suspects left, whose half would hold three, merge alone in the same run."""
    five(kitchen)
    more(kitchen, *TEN[5:])
    kitchen.run()
    listed(kitchen, (merge.FAILED,))
    kitchen.run()
    commit = pushed(kitchen)
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said[:5]] == [["merged", str(n)] for n in FIVE]
    assert all("so no guards ran" in line for line in said[:5])
    assert [alone(line, n) for line, n in zip(said[5:], TEN[5:], strict=True)] == [True] * 5
    assert runs(kitchen) == 5 and pushed(kitchen) == commit
    assert suspects(kitchen) == [] and record(kitchen).get("members") is None


def test_one_member_merges_on_the_guards_of_its_own_tree_with_no_batch(kitchen):
    """One member is the single path itself: it merges on the guards of its merged tree in the
    run that judged it, with no push to `jmerge/batch`, no batch pull request, and no line of a
    guards batch."""
    kitchen.crew("one", 6, {"a.txt": OURS})
    kitchen.on_main({"d.txt": "theirs\n"})
    said = kitchen.run()
    assert len(said) == 1 and alone(said[0], 6) and runs(kitchen) == 1
    assert pushed(kitchen) is None and not (kitchen.home.stub / "created").exists()
    assert record(kitchen).get("members") is None and suspects(kitchen) == []


def test_a_batch_still_checked_holds_its_members_and_the_rest_wait_for_it(kitchen):
    five(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    listed(kitchen, (merge.RUNNING,))
    kitchen.crew("six", 11, {"g.txt": OURS})
    kitchen.crew("seven", 12, {"h.txt": OURS}, checks=(LATER,))
    listed(kitchen, (merge.RUNNING,))
    after = ready.BATCH_FIRST.format(base="main", tip=tip[:12])
    assert kitchen.run() == [
        f"wait 12 {url(12)}: {after}",
        *(in_batch(number, tip) for number in FIVE),
        f"wait 11 {url(11)}: {after}",
    ]
    assert kitchen.calls() == [] and runs(kitchen) == 0


def test_a_batch_left_with_fewer_than_five_members_holds_no_pull_request_for_it(kitchen):
    """#8's head moved while the batch was checked, so four of its members are judged: no CI
    batch is built again, #12, which would merge alone, merges in that run rather than wait for
    a batch that is gone, and the four share one guards run and merge after it."""
    five(kitchen)
    kitchen.run()
    commit = pushed(kitchen)
    tree = kitchen.tmp / "trees" / "three"
    (tree / "c.txt").write_text("changed after the review\n" + LINES)
    git(tree, "commit", "-qam", "late")
    git(tree, "push", "-q")
    kitchen.pulls["three"]["headRefOid"] = git(tree, "rev-parse", "HEAD")
    kitchen.crew("seven", 12, {"h.txt": OURS}, checks=(LATER,))
    listed(kitchen, (merge.RUNNING,), at=commit)
    said = kitchen.run()
    assert not [line for line in said if "merges first" in line]
    tip = git(kitchen.origin, "rev-parse", "refs/heads/main~4")
    assert [line.split()[:2] for line in said] == [
        ["wait", "8"],
        ["merged", "12"],
        ["batch:", "guards"],
        ["merged", "6"],
        ["merged", "7"],
        ["merged", "9"],
        ["merged", "10"],
    ]
    assert said[2].startswith(guards_batch(4, tip, "passed")) and runs(kitchen) == 1
    assert pushed(kitchen) == commit and record(kitchen).get("members") is None


@pytest.mark.parametrize("on", [True, False], ids=["batching on", "batching off"])
def test_jmerge_never_judges_the_batch_pull_request(kitchen, on):
    five(kitchen)
    kitchen.run()
    if not on:
        (kitchen.home.state / batch.SWITCH).unlink()
    listed(kitchen, (merge.RUNNING,))
    said = kitchen.run("--check") + kitchen.run()
    assert [line for line in said if " 99 " in f"{line} "] == []


def test_a_revert_stays_out_of_the_batch_and_merges_first_on_its_own_path(kitchen):
    jbus = queue_of(kitchen.home, []).parent
    five(kitchen)
    kitchen.crew("revert-it", 11, {"g.txt": OURS})
    named(jbus, ("revert-it", url(11)))
    first, *second = kitchen.run()
    assert first.startswith("merged 11 revert-it ")
    tip = kitchen.tip()
    assert second == [built(5, tip), *(in_batch(n, tip) for n in FIVE)]
    assert [one["number"] for one in record(kitchen)["members"]] == list(FIVE)


def test_a_second_migration_stays_out_of_the_batch(kitchen):
    queue_of(kitchen.home, [], DIRECTORY)
    kitchen.crew("one", 6, {"db/migrations/0005_one.up.sql": "select 1;\n"})
    kitchen.crew("two", 7, {"db/migrations/0006_two.up.sql": "select 2;\n"})
    more(kitchen, 8, 9, 10, 11)
    for pull in kitchen.pulls.values():
        for one in pull["files"]:
            one["changeType"] = "ADDED"
    (kitchen.home.stub / "list.json").write_text(json.dumps(list(kitchen.pulls.values())))
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    merging = ready.MIGRATION_MERGING.format(number=6)
    assert kitchen.run() == [
        f"wait 7 {url(7)}: {merging}",
        built(5, tip),
        *(in_batch(n, tip) for n in (6, 8, 9, 10, 11)),
    ]
    assert [one["number"] for one in record(kitchen)["members"]] == [6, 8, 9, 10, 11]


def test_a_pull_request_whose_merge_after_is_unmet_stays_out_of_the_batch(kitchen):
    slugs = ("one", "two", "three", "four", "five")
    rows = [row(slug, pr=f"#{n}") for slug, n in zip(slugs, FIVE, strict=True)]
    queue_of(kitchen.home, [*rows, row("pr11", pr="#11", merge_after=["one"])])
    five(kitchen)
    more(kitchen, 11)
    tip = kitchen.tip()
    first, *second = kitchen.run()
    assert first.startswith(f"wait 11 {url(11)}: merges after one ")
    assert second == [built(5, tip), *(in_batch(n, tip) for n in FIVE)]
    assert [one["number"] for one in record(kitchen)["members"]] == list(FIVE)


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
    five(kitchen)
    kitchen.run()
    late(kitchen, checks)
    tip = kitchen.tip()
    assert kitchen.run() == [built(5, tip), *(in_batch(number, tip) for number in FIVE)]
    assert [one["number"] for one in record(kitchen)["members"]] == list(FIVE)
    assert suspects(kitchen) == [] and record(kitchen)["failed"] == {}
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", str(n)] for n in FIVE]
    assert all("so no guards ran" in line for line in said)
    assert runs(kitchen) == 0 and suspects(kitchen) == []


@TIMED_OUT
def test_a_batch_that_timed_out_twice_in_a_row_sends_its_five_members_alone(kitchen, checks):
    """The second timeout fails the batch, and its half of five would hold three."""
    five(kitchen)
    kitchen.run()
    late(kitchen, checks)
    kitchen.run()
    late(kitchen, checks)
    said = kitchen.run()
    assert [alone(line, n) for line, n in zip(said, FIVE, strict=True)] == [True] * 5
    assert runs(kitchen) == 5 and suspects(kitchen) == []


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
    five(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    late(kitchen, (failed_in(1),))
    assert kitchen.run() == [in_batch(number, tip) for number in FIVE]
    assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
    listed(kitchen, (merge.RUNNING,))
    assert kitchen.run() == [in_batch(number, tip) for number in FIVE]
    assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
    assert suspects(kitchen) == [] and record(kitchen)["again"] is False
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", str(n)] for n in FIVE]
    assert all("so no guards ran" in line for line in said)
    assert runs(kitchen) == 0 and suspects(kitchen) == [] and record(kitchen)["failed"] == {}


@pytest.mark.parametrize("case", ["fails again", "rerun refused", "first attempt still listed"])
def test_a_batch_that_fails_again_after_its_rerun_fails_as_a_failed_check_does(kitchen, case):
    """A second failure, a new job of the run, and a rerun GitHub refuses each fail the batch as
    a failed check did before the rerun: its members are suspects and the next batch is the first
    half of them. A listing that still shows the first attempt's failed job is no second failure:
    the batch stays pending, and is not rerun again."""
    five(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    if case == "rerun refused":
        (kitchen.home.stub / "rerun-refused").write_text("")
    listed(kitchen, (failed_in(1),))
    said = kitchen.run()
    if case != "rerun refused":
        assert said == [in_batch(number, tip) for number in FIVE]
        listed(kitchen, (failed_in(2 if case == "fails again" else 1),))
        said = kitchen.run()
    assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
    if case == "first attempt still listed":
        assert said == [in_batch(number, tip) for number in FIVE]
        assert suspects(kitchen) == []
        assert runs(kitchen) == 0 and kitchen.calls() == []
    else:
        assert [alone(line, n) for line, n in zip(said, FIVE, strict=True)] == [True] * 5
        assert runs(kitchen) == 5 and suspects(kitchen) == []


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
    second failure sends each of the five members down the single path, as with no `borders`
    failure beside it."""
    (kitchen.home.state / "required-checks").write_text("check\nborders\n")
    heads = five(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    waiting = [in_batch(number, tip) for number in FIVE]
    if check == "failed":
        listed(kitchen, (BORDERS_FAILED, failed_in(1)))
        assert kitchen.run() == waiting
        assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
        listed(kitchen, (BORDERS_FAILED, failed_in(2)))
        said = kitchen.run()
        assert [alone(line, n) for line, n in zip(said, FIVE, strict=True)] == [True] * 5
        assert reruns(kitchen) == [["run", "rerun", "5", "--failed"]]
        assert record(kitchen)["failed"] == dict(zip(map(str, FIVE), heads, strict=True))
        assert suspects(kitchen) == []
        return
    listed(kitchen, (BORDERS_FAILED, merge.RUNNING if check == "running" else merge.PASSED))
    assert kitchen.run() == waiting
    assert reruns(kitchen) == [] and suspects(kitchen) == []
    proven(kitchen)
    listed(kitchen, (BORDERS_FAILED, merge.PASSED))
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", str(n)] for n in FIVE]
    assert reruns(kitchen) == [] and suspects(kitchen) == [] and runs(kitchen) == 0


def test_a_batch_that_passed_with_no_artifact_found_waits_and_merges_once_it_is_found(kitchen):
    five(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    listed(kitchen, (merge.PASSED,))
    assert kitchen.run() == [in_batch(number, tip) for number in FIVE]
    assert kitchen.calls() == [] and runs(kitchen) == 0
    assert record(kitchen)["failed"] == {}
    proven(kitchen)
    said = kitchen.run()
    assert [line.split()[:2] for line in said] == [["merged", str(n)] for n in FIVE]
    assert runs(kitchen) == 0


def test_a_member_that_conflicts_with_one_before_it_waits_for_the_batch(kitchen):
    five(kitchen)
    kitchen.crew("six", 11, {"a.txt": "theirs too\n" + LINES})
    tip = kitchen.tip()
    assert kitchen.run() == [built(5, tip), *(in_batch(n, tip) for n in FIVE), first(11, tip)]
    assert [one["number"] for one in record(kitchen)["members"]] == list(FIVE)


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
    five(kitchen)
    tip = kitchen.tip()
    unmade, *said = kitchen.run()
    assert unmade.startswith(f"batch: not made over main at {tip[:12]} (")
    assert [line.split()[:2] for line in said] == [["merged", str(n)] for n in FIVE]
    assert runs(kitchen) == 5


def test_a_ci_batch_of_two_to_four_once_conflicts_are_left_out_is_a_guards_batch(kitchen):
    """#8 and #9 clash with #6's line, so two of the five merge over the tip: no batch is pushed,
    the two that merge share one guards run and merge on it, and the two left out go down the
    single path after, where they wait for their rebase, their heads not under `failed`."""
    kitchen.crew("one", 6, {"a.txt": OURS})
    kitchen.crew("two", 7, {"b.txt": OURS})
    kitchen.crew("three", 8, {"a.txt": "theirs three\n" + LINES})
    kitchen.crew("four", 9, {"a.txt": "theirs four\n" + LINES})
    kitchen.crew("five", 10, {"a.txt": "theirs five\n" + LINES})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    line, *said = kitchen.run()
    assert line.startswith(guards_batch(2, tip, "passed"))
    assert [one.split()[:2] for one in said[:2]] == [["merged", "6"], ["merged", "7"]]
    assert said[2:] == [f"wait {n} {url(n)}: {CONFLICT}" for n in (8, 9, 10)]
    assert pushed(kitchen) is None and runs(kitchen) == 1 and record(kitchen)["failed"] == {}


def test_a_proven_batch_stops_at_a_member_no_longer_ready_at_its_head(kitchen):
    five(kitchen)
    tip = kitchen.tip()
    kitchen.run()
    tree = kitchen.tmp / "trees" / "two"
    (tree / "b.txt").write_text("changed after the review\n" + LINES)
    git(tree, "commit", "-qam", "late")
    git(tree, "push", "-q")
    kitchen.pulls["two"]["headRefOid"] = git(tree, "rev-parse", "HEAD")
    proven(kitchen)
    own, merged, *stopped = kitchen.run()
    assert own.startswith(f"wait 7 {url(7)}: ")
    assert merged.startswith("merged 6 one ")
    why = ready.BATCH_STOPPED.format(base="main", tip=tip[:12], number=7)
    assert stopped == [f"wait {n} {url(n)}: {why}" for n in (8, 9, 10)]
    assert [call.split()[2] for call in kitchen.calls()] == ["6"]


def test_a_proven_batch_stops_where_another_hand_moved_main_between_its_merges(kitchen):
    five(kitchen)
    kitchen.run()
    proven(kitchen)
    (kitchen.home.stub / "also-6").write_text("")
    merged, *said = kitchen.run()
    assert merged.startswith("merged 6 one ")
    moved = ready.MAIN_MOVED.format(base="main")
    assert said == [f"wait {n} {url(n)}: {moved}" for n in FIVE[1:]]
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
    halves it when it fails after its rerun, to 5 at least. A batch of fewer, a narrowed batch of
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
    five(kitchen)
    unmade, *_ = kitchen.run()
    assert unmade.startswith("batch: not made over main ")
    assert most(kitchen) == 24
    assert [ends(kitchen, n, "fail") for n in (24, 12, 6, 5)] == [12, 6, 5, 5]


def test_building_a_batch_says_its_size_and_the_most(kitchen):
    """The line is about no pull request, so jbus reads nothing of it, and merge.log keeps it. A
    most kept under five is read as five, the fewest CI's batch holds."""
    (kitchen.home.state / batch.KEPT).write_text(json.dumps({"most": 2}))
    five(kitchen)
    more(kitchen, 11)
    tip = kitchen.tip()
    line = f"batch: built over main at {tip[:12]}, 5 of 5 members at most"
    assert kitchen.run() == [line, *(in_batch(n, tip) for n in FIVE), first(11, tip)]
    log = (kitchen.home.state / "merge.log").read_text().splitlines()
    assert sum(one.endswith(" " + line) for one in log) == 1


def guards_batch(size, tip, outcome):
    """The start of the line of a guards batch of `size` over main at `tip`, up to its seconds."""
    return f"batch: guards on {size} members over main at {tip[:12]}, {outcome} in "


def guards_lines(kitchen):
    """The lines of merge.log that say what a guards batch did."""
    log = kitchen.home.state / "merge.log"
    said = log.read_text().splitlines() if log.exists() else []
    return [one for one in said if " batch: guards on " in f" {one}"]


@pytest.mark.parametrize("size", [2, 3, 4])
def test_two_to_four_members_share_one_guards_run_on_their_tree_and_merge_in_that_run(
    kitchen, size
):
    """Two to four members judged in one run cost one guards run, on main's tip with each merged
    in, where each alone cost one each: on its pass each merges at its own head in that run, with
    no push to `jmerge/batch`, no batch pull request, and no wait on a batch."""
    names = ("a.txt", "b.txt", "c.txt", "e.txt")
    heads = [
        kitchen.crew(f"pr{n}", n, {name: OURS})
        for n, name in zip(range(6, 6 + size), names[:size], strict=True)
    ]
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    said = kitchen.run()
    line, *merged = said
    assert line.startswith(guards_batch(size, tip, "passed"))
    seconds = line.removeprefix(guards_batch(size, tip, "passed")).removesuffix(" s")
    assert seconds.isdigit()
    note = batch.GUARDS_PASSED.format(size=size, base="main", tip=tip[:12], seconds=seconds)
    assert [one.split()[:2] for one in merged] == [["merged", str(n)] for n in range(6, 6 + size)]
    assert all(f", {note}" in one for one in merged)
    assert runs(kitchen) == 1
    calls = kitchen.calls()
    for call, head in zip(calls, heads, strict=True):
        assert f"--squash --match-head-commit {head} " in call
    for name in names[:size]:
        assert kitchen.at_main(name) == OURS.strip()
    assert pushed(kitchen) is None and not (kitchen.home.stub / "created").exists()
    assert record(kitchen).get("members") is None and record(kitchen)["failed"] == {}
    assert [one.endswith(f" {line}") for one in guards_lines(kitchen)] == [True]


CLASH = "make -s guards && ! { grep -q ours a.txt && grep -q ours b.txt; }"
"""Guards that pass on #6's tree and on #7's, and fail on a tree that holds both."""


def test_guards_that_fail_on_the_batch_tree_send_each_member_down_the_single_path(kitchen):
    """The batch of #6 and #7 fails its guards, so neither merges by it: each takes the single
    path in that run, where #6 merges on its own tree and #7 fails on its tree over #6. Each head
    is kept under `failed`, so #7 joins no batch at that head: the next run, with #8 ready too,
    runs no guards batch, and #8, made over today's main, merges on its own check."""
    (kitchen.home.state / treeguards.NAME).write_text(CLASH + "\n")
    heads = [kitchen.crew(f"pr{n}", n, {name: OURS}) for n, name in ((6, "a.txt"), (7, "b.txt"))]
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    line, first, second = kitchen.run()
    assert line.startswith(guards_batch(2, tip, "failed"))
    assert alone(first, 6)
    assert second.startswith(f"wait 7 {url(7)}: merged over today's main at ")
    assert runs(kitchen) == 3 and [call.split()[2] for call in kitchen.calls()] == ["6"]
    assert record(kitchen)["failed"] == {"6": heads[0], "7": heads[1]}
    del kitchen.pulls["pr6"]
    kitchen.crew("pr8", 8, {"c.txt": OURS})
    said = kitchen.run()
    assert [one.split()[:2] for one in said] == [["wait", "7"], ["merged", "8"]]
    assert len(guards_lines(kitchen)) == 1
    assert record(kitchen)["failed"] == {"7": heads[1]}


def test_two_members_of_which_one_merges_over_the_tip_each_take_the_single_path(kitchen):
    """#7 clashes with #6's line, so one of the two merges over the tip: no guards batch runs,
    #6 merges on the guards of its own tree, and #7 waits for its rebase, its head not under
    `failed`."""
    kitchen.crew("one", 6, {"a.txt": OURS})
    kitchen.crew("two", 7, {"a.txt": "theirs two\n" + LINES})
    kitchen.on_main({"d.txt": "theirs\n"})
    first, second = kitchen.run()
    assert alone(first, 6) and second == f"wait 7 {url(7)}: {CONFLICT}"
    assert runs(kitchen) == 1 and guards_lines(kitchen) == [] and record(kitchen)["failed"] == {}


@pytest.mark.parametrize("case", ["stopped", "no time", "unbuilt"])
def test_the_guards_on_a_batch_tree_say_what_they_did_under_the_single_path_s_rules(
    kitchen, monkeypatch, case
):
    """Guards stopped at their limit say so, and count toward the run's seconds; a run that spent
    `RUN_SECONDS` starts none; and a commit no worktree can be made of runs none. Neither of the
    last two is evidence against a member (`treeguards.UNRUN`)."""
    monkeypatch.setattr(treeguards, "LIMIT_SECONDS", 1)
    guards = treeguards.Guards(kitchen.home.main, kitchen.home.state, True, lambda path: {})
    guards.command = "sleep 5"
    tip = git(kitchen.home.main, "rev-parse", "HEAD")
    if case == "no time":
        guards.spent = treeguards.RUN_SECONDS
    tried = guards.on_batch("0" * 40 if case == "unbuilt" else tip, tip, [tip])
    if case == "stopped":
        assert (tried.outcome, tried.seconds) == (treeguards.STOPPED, 1)
        assert guards.spent >= 1
    else:
        assert tried.outcome in treeguards.UNRUN and tried.outcome.startswith(case[:2])
        assert tried.why and guards.spent == (treeguards.RUN_SECONDS if case == "no time" else 0)
    assert not (kitchen.home.state / treeguards.KEPT).exists()


def test_guards_on_a_batch_tree_that_find_no_slot_run_no_more_in_that_run(
    kitchen, tmp_path, monkeypatch
):
    """With every full slot taken past `SLOT_SECONDS`, the guards on a batch's tree do not start,
    the wait counts toward the run's seconds, and a later batch of the run waits for none."""
    monkeypatch.delenv(slot.HELD, raising=False)
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("TEST_SLOTS", "1")
    monkeypatch.setattr(treeguards, "SLOT_SECONDS", 1)
    guards = treeguards.Guards(kitchen.home.main, kitchen.home.state, True, lambda path: {})
    guards.command = "true"
    tip = git(kitchen.home.main, "rev-parse", "HEAD")
    held, _ = slot.take(slot.full(1))
    try:
        assert guards.on_batch(tip, tip, [tip]) == treeguards.Tried(treeguards.NO_SLOT, 1)
    finally:
        os.close(held)
    assert guards.on_batch(tip, tip, [tip]) == treeguards.Tried(treeguards.NO_SLOT, 0)
    assert guards.spent == 1


def test_a_batch_tree_the_guards_cannot_run_on_is_not_made_and_its_members_go_alone(kitchen):
    """A worktree of the batch's commit that cannot be made is no evidence against a member: the
    run says `batch: not made` with why, and each member takes the single path, its head not under
    `failed`."""
    (kitchen.home.state / treeguards.TREE).write_text("in the way\n")
    kitchen.crew("one", 6, {"a.txt": OURS})
    kitchen.crew("two", 7, {"b.txt": OURS})
    tip = kitchen.on_main({"d.txt": "theirs\n"})
    unmade, *said = kitchen.run()
    assert unmade.startswith(f"batch: not made over main at {tip[:12]} (")
    assert [one.split()[:2] for one in said] == [["wait", "6"], ["wait", "7"]]
    assert runs(kitchen) == 0 and record(kitchen)["failed"] == {}


def test_the_guards_on_a_batch_tree_run_what_main_changed_since_the_oldest_member_s_check(kitchen):
    """#6 left main before #7 did, so the guards on their tree get `MERGE_BASE` at #6's fork
    point: they run every test file main changed since either member's check ran."""
    seen = kitchen.tmp / "merge-bases"
    command = f'make -s guards && echo "$MERGE_BASE" >> {seen}'
    (kitchen.home.state / treeguards.NAME).write_text(command + "\n")
    oldest = kitchen.tip()
    kitchen.crew("one", 6, {"a.txt": OURS})
    kitchen.on_main({"d.txt": "theirs\n"})
    kitchen.crew("two", 7, {"b.txt": OURS})
    tip = kitchen.on_main({"e.txt": "theirs\n"})
    line, *merged = kitchen.run()
    assert line.startswith(guards_batch(2, tip, "passed")) and len(merged) == 2
    assert seen.read_text().split() == [oldest]
