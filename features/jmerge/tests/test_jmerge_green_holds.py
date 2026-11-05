"""Green means five things, and `jmerge` holds a pull request that lacks any one of them (Josh,
2026-11-05): `borders` passed, `macos` passed, every context the live ruleset on main requires
passed, a revert jbus opened is at the head it opened it at, and a review round was written at
the head. Each test takes one away from a pull request that is otherwise ready, sees `jmerge`
print the hold and leave main as it was, gives it back, and sees the same run merge it.

The ruleset's contexts are read from `features/repo-guards/main-ruleset.json`, the body PUT to
ruleset 25665226, which `test_main_ruleset.py` holds, so a context added there is held here with
no edit. `jmerge` reads its required checks from the home's `required-checks` file and never from
the ruleset, so the tests write that file from the ruleset's contexts, as jstack's home has it.

`jmerge` ties no review to the time its checks passed: the crew launches the reviewer only once
`check` passed (`features/crew/the-review.md`). Here a review is held to the head it names: no
review, or one at a head whose content the pull request no longer has, holds it.

The tests run the command against a real origin and a fake `gh` (`test_home_merge.Merged`,
`test_jmerge_rejudge.Replay`)."""

import json

import pytest

import test_home_merge as merge
from jmerge import ready, reverts
from test_jmerge_fresh import url
from test_jmerge_red_main import red_main, revert_pull
from test_jmerge_rejudge import Replay
from testing.paths import REPO

RULESET = REPO / "features" / "repo-guards" / "main-ruleset.json"


def contexts():
    """The contexts the ruleset on main requires, in its order."""
    rules = json.loads(RULESET.read_text())["rules"]
    (checks,) = [one["parameters"] for one in rules if one["type"] == "required_status_checks"]
    return [one["context"] for one in checks["required_status_checks"]]


CONTEXTS = contexts()


def green(name):
    """A passed run of the required check `name`, in the workflow GitHub names it by."""
    return {**merge.run("SUCCESS", name), "workflowName": name}


def all_green():
    """A passed run of each context the ruleset requires, and of macos.yml's `macos-select`."""
    return [*(green(name) for name in CONTEXTS), {**green("macos-select"), "workflowName": "macos"}]


@pytest.fixture
def merged(tmp_path):
    merged = merge.Merged(merge.Home(tmp_path), tmp_path)
    (merged.home.state / "required-checks").write_text("".join(f"{c}\n" for c in CONTEXTS))
    return merged


def listing(merged, checks):
    """GitHub lists `checks` for the pull request, and no other."""
    listed = json.loads((merged.home.stub / "list.json").read_text())
    listed[0]["statusCheckRollup"] = list(checks)
    (merged.home.stub / "list.json").write_text(json.dumps(listed))


def held(merged, reason):
    """`jmerge` holds the pull request for `reason` and leaves main, the branches and the plan."""
    assert merged.run() == [f"wait 7 {merge.URL}: {reason}"]
    assert merged.untouched()


def merges(merged):
    """`jmerge` merges the pull request at its head onto main."""
    (said,) = merged.run()
    commit, _ = merged.on_main()
    assert said == merge.merged_line(commit)
    assert commit != merged.start


def test_the_ruleset_requires_borders_and_macos_beside_check_so_they_hold():
    assert {"check", "borders", "macos"} <= set(CONTEXTS), CONTEXTS


@pytest.mark.parametrize("name", CONTEXTS)
def test_each_ruleset_context_with_no_run_holds_until_it_passed(merged, name):
    listing(merged, [one for one in all_green() if one["name"] != name])
    held(merged, ready.NO_RUN.format(check=name, head=merged.head[:12]))
    listing(merged, all_green())
    merges(merged)


@pytest.mark.parametrize("name", CONTEXTS)
def test_each_ruleset_context_that_failed_holds_until_it_passed(merged, name):
    failed = {**merge.run("FAILURE", name), "workflowName": name}
    listing(merged, [failed if one["name"] == name else one for one in all_green()])
    held(merged, ready.CHECK_FAILED.format(check=name))
    listing(merged, all_green())
    merges(merged)


def test_a_macos_skipped_with_no_select_that_passed_holds_and_one_beside_it_merges(merged):
    skipped = {**merge.run("SKIPPED", "macos"), "workflowName": "macos"}
    others = [one for one in all_green() if one["workflowName"] != "macos"]
    selected = {**merge.run("FAILURE", "macos-select"), "workflowName": "macos"}
    listing(merged, [*others, skipped, selected])
    held(merged, ready.NOT_PASSED.format(check="macos"))
    listing(merged, [*others, skipped, {**selected, "conclusion": "SUCCESS"}])
    merges(merged)


def test_a_green_pull_request_with_no_review_holds_until_its_review_is_written(merged):
    listing(merged, all_green())
    (merged.home.tasks / "alpha.md").write_text(merge.brief())
    held(merged, ready.NO_REVIEW)
    (merged.home.tasks / "alpha.md").write_text(merge.brief(merge.review("clean", merged.head)))
    merges(merged)


def test_a_review_of_a_head_whose_content_changed_holds_until_the_head_is_reviewed(merged):
    reviewed = merged.head
    (merged.tree / "a.txt").write_text("the task, changed after its review\n")
    merge.git(merged.tree, "commit", "-q", "-am", "a change after the review")
    merge.git(merged.tree, "push", "-q")
    merged.head = merge.git(merged.tree, "rev-parse", "HEAD")
    merged.home.open_pull_request(merged.head)
    listing(merged, all_green())
    command = f"git range-diff --no-color {merged.start}..{reviewed} {merged.start}..{merged.head}"
    held(merged, ready.CONTENT_CHANGED.format(command=command))
    (merged.home.tasks / "alpha.md").write_text(merge.brief(merge.review("clean", merged.head)))
    merges(merged)


@pytest.fixture
def replay(tmp_path):
    return Replay(tmp_path)


def test_a_revert_jbus_opened_holds_for_a_review_once_its_head_is_not_the_one_opened(replay):
    tip = red_main(replay)
    head = revert_pull(replay)
    made = reverts.read(replay.state)["r" * 40]

    def record(at):
        kept = reverts.Revert(made.red, made.slug, made.branch, at, made.pull)
        (replay.state / reverts.NAME).write_text(json.dumps({kept.red: reverts.record(kept)}))

    record(tip)
    assert replay.run() == [f"wait 900 {url(900)}: {ready.NO_REVIEW}"]
    record(head)
    assert [line.split()[:2] for line in replay.run()] == [["merged", "900"]]
