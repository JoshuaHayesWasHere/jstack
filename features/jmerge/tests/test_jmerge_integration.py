"""A project's integration branches are the branches that its state's `integration` file
names, one to a line. `jmerge` merges a pull request into one of them as it merges one into
the default branch. It judges whether the pull request's check is stale and whether the
branch is red against that branch, and squashes the pull request into it. The pull request
that lands an integration branch on the default branch merges with a merge commit, and
`jmerge` keeps the branch. With no such file, `jmerge` holds a pull request into another
branch, as before (`tests/test_home_merge.py`).

The tests run the command against a real origin and a fake `gh` whose merge goes into the
pull request's own base, as `features/jmerge/tests/test_jmerge_fresh.py` runs it."""

import json

import pytest

from jmerge import ready, rows
from test_jmerge_fresh import LINES, STALE, Kitchen, git, url, write
from test_jmerge_order import main_says, queue_of

GH = """\
#!/bin/sh
echo "$*" >> "$STUB/calls"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
case "$1 $2" in
    "pr list")
        if [ "$3" = "--base" ]; then echo "[]"; else cat "$STUB/list.json"; fi ;;
    "repo view") echo main ;;
    "api repos/{owner}/{repo}/commits/"*)
        branch=${2#repos/\\{owner\\}/\\{repo\\}/commits/}
        cat "$STUB/runs-${branch%/check-runs}" 2> /dev/null || echo '{"check_runs": []}' ;;
    "pr merge")
        base=$(jq -r --argjson n "$3" \
            '.[] | select(.number == $n) | .baseRefName' "$STUB/list.json")
        tree=$(git -C "$ORIGIN" merge-tree --write-tree "refs/heads/$base" "$6") || exit 1
        case "$4 $5" in
            "--squash --match-head-commit") parents="-p refs/heads/$base" ;;
            "--merge --match-head-commit") parents="-p refs/heads/$base -p $6" ;;
            *) exit 64 ;;
        esac
        commit=$(git -C "$ORIGIN" commit-tree "$tree" $parents -m "merge (#$3)")
        git -C "$ORIGIN" update-ref "refs/heads/$base" "$commit"
        echo "$commit" > "$STUB/merged-$3" ;;
    "pr view")
        if [ "$5" = "state,headRefOid,baseRefName" ]; then cat "$STUB/view-${3##*/}"
        else cat "$STUB/merged-$3"; fi ;;
    *) exit 64 ;;
esac
"""

TRAIN = "migration"


@pytest.fixture
def kitchen(tmp_path):
    kitchen = Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES, "Makefile": "check:\n"})
    (kitchen.home.stub / "gh").write_text(GH)
    git(kitchen.home.main, "push", "-q", "origin", f"main:{TRAIN}")
    return kitchen


def integration(kitchen, *branches):
    """The project's state names these branches as its integration branches."""
    (kitchen.home.state / "integration").write_text("".join(f"{one}\n" for one in branches))


def into(kitchen, slug, number, files, base=TRAIN):
    """Open a crewmate's pull request into `base` that is ready, and return its head."""
    head = kitchen.crew(slug, number, files)
    kitchen.pulls[slug]["baseRefName"] = base
    kitchen.brief(slug, head)
    return head


def on(kitchen, branch, files):
    """Push a commit to `branch` by hand now, after every check that started in 2000."""
    tree = kitchen.tmp / "trees" / f"by-hand-{branch}"
    git(kitchen.home.main, "fetch", "-q", "origin")
    git(kitchen.home.main, "worktree", "add", "-q", "--detach", str(tree), f"origin/{branch}")
    write(tree, files)
    git(tree, "commit", "-q", "-m", "by hand")
    git(tree, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    return git(tree, "rev-parse", "HEAD")


def tip(kitchen, branch):
    return git(kitchen.origin, "rev-parse", f"refs/heads/{branch}")


def runs(kitchen, branch, *conclusions):
    """What GitHub says of the check runs of the branch's tip."""
    sha = tip(kitchen, branch)
    listed = [
        {"name": f"check {n}", "head_sha": sha, "status": "completed", "conclusion": one}
        for n, one in enumerate(conclusions)
    ]
    (kitchen.home.stub / f"runs-{branch}").write_text(json.dumps({"check_runs": listed}))
    return sha


def test_with_no_integration_file_a_pull_request_into_another_branch_is_held_as_before(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    held = ready.BASE.format(base=TRAIN, default="main")
    assert kitchen.run() == [f"wait 6 {url(6)}: {held}"]
    assert kitchen.calls() == []


def test_a_pull_request_into_an_integration_branch_is_ready_and_check_merges_nothing(kitchen):
    head = into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    assert kitchen.run("--check") == [f"ready 6 {head} one one"]
    assert kitchen.calls() == []


def test_it_squashes_into_that_branch_and_the_merged_line_names_it(kitchen):
    main = tip(kitchen, "main")
    head = into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    (said,) = kitchen.run()
    commit = tip(kitchen, TRAIN)
    assert said.startswith(f'merged 6 one {commit} "feat: one", into {TRAIN}, ')
    assert kitchen.calls() == [
        f"pr merge 6 --squash --match-head-commit {head} --repo {kitchen.origin}"
    ]
    assert git(kitchen.origin, "show", f"refs/heads/{TRAIN}:a.txt") == ("ours\n" + LINES).strip()
    assert tip(kitchen, "main") == main


def test_a_merge_into_the_default_branch_still_names_no_base(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ") and ", into " not in said


def test_it_waits_when_its_own_base_changed_its_file_after_the_check(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    on(kitchen, TRAIN, {"a.txt": LINES + "theirs\n"})
    (said,) = kitchen.run()
    assert said == f"wait 6 {url(6)}: " + STALE.replace("main", TRAIN, 1).format("a.txt")
    assert kitchen.calls() == []


def test_main_changing_its_file_does_not_make_a_pull_request_into_the_train_stale(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    kitchen.on_main({"a.txt": LINES + "theirs\n"})
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ")


def test_a_red_main_holds_a_pull_request_into_main_and_not_one_into_the_train(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    integration(kitchen, TRAIN)
    queue_of(kitchen.home, [])
    main_says(kitchen.home, red="c" * 40, green="a" * 40)
    one, two = kitchen.run()
    assert one.startswith("merged 6 one ")
    assert two == f"wait 7 {url(7)}: " + ready.MAIN_RED.format(sha="c" * 12)


def test_a_red_train_holds_a_pull_request_into_it_and_not_one_into_main(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    integration(kitchen, TRAIN)
    red = runs(kitchen, TRAIN, "success", "failure")
    one, two = kitchen.run()
    assert one == f"wait 6 {url(6)}: " + ready.BASE_RED.format(base=TRAIN, sha=red[:12])
    assert two.startswith("merged 7 two ")


@pytest.mark.parametrize("conclusions", [(), ("success", "skipped", "neutral", "cancelled")])
def test_a_train_whose_latest_check_did_not_fail_holds_nothing(kitchen, conclusions):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    runs(kitchen, TRAIN, *conclusions)
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ")


def test_the_landing_of_the_train_on_main_is_a_merge_commit_and_keeps_the_branch(kitchen):
    main = tip(kitchen, "main")
    head = kitchen.crew(TRAIN, 9, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    (said,) = kitchen.run()
    commit = tip(kitchen, "main")
    assert said.startswith(f'merged 9 {TRAIN} {commit} "feat: {TRAIN}", ')
    assert kitchen.calls() == [
        f"pr merge 9 --merge --match-head-commit {head} --repo {kitchen.origin}"
    ]
    assert git(kitchen.origin, "rev-list", "--parents", "-n", "1", commit).split()[1:] == [
        main,
        head,
    ]
    assert tip(kitchen, TRAIN) == head
    assert TRAIN in git(kitchen.home.main, "branch", "--format=%(refname:short)").split()


def test_blank_lines_and_spaces_in_the_file_name_no_branch(kitchen):
    head = into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    (kitchen.home.state / "integration").write_text(f"\n  {TRAIN}  \n\n")
    assert kitchen.run("--check") == [f"ready 6 {head} one one"]


def check_run(name, conclusion, started, sha="d" * 40):
    return {
        "name": name,
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "started_at": started,
    }


def test_a_check_that_failed_and_then_passed_on_a_rerun_is_no_red_train():
    reran = [
        check_run("check", "success", "2026-10-21T10:05:00Z"),
        check_run("check", "failure", "2026-10-21T10:00:00Z"),
    ]
    assert rows.base_red(TRAIN, reran, "one") == ""
    failed_last = [*reran, check_run("check", "failure", "2026-10-21T10:10:00Z")]
    assert rows.base_red(TRAIN, failed_last, "one") == ready.BASE_RED.format(
        base=TRAIN, sha="d" * 12
    )


def test_a_check_still_running_is_no_red_train():
    running = {**check_run("check", None, "2026-10-21T10:00:00Z"), "status": "in_progress"}
    assert rows.base_red(TRAIN, [running], "one") == ""


def test_the_fix_of_a_red_main_is_not_held_by_a_red_train():
    failed = [check_run("check", "failure", "2026-10-21T10:00:00Z")]
    assert rows.base_red(TRAIN, failed, "main-red-cccccccccccc") == ""


def viewed(kitchen, number, head, base):
    """What GitHub says of a merged pull request, which a sweep asks for."""
    said = {"state": "MERGED", "headRefOid": head, "baseRefName": base}
    (kitchen.home.stub / f"view-{number}").write_text(json.dumps(said))


def test_a_sweep_keeps_the_integration_branch_after_its_landing_merged(kitchen):
    head = kitchen.crew(TRAIN, 9, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    kitchen.run()
    viewed(kitchen, 9, head, "main")
    said = kitchen.run("--sweep", "--check")
    assert f"kept {TRAIN}: it is an integration branch" in said
    assert not [line for line in said if line.startswith(f"removable {TRAIN} ")]


def test_a_sweep_counts_a_pull_request_merged_into_the_train_as_merged(kitchen):
    head = into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, TRAIN)
    kitchen.brief("one", head, "Left: none\n")
    git(kitchen.home.main, "worktree", "remove", str(kitchen.tmp / "trees" / "one"))
    (kitchen.home.stub / "list.json").write_text("[]")
    viewed(kitchen, 6, head, TRAIN)
    said = kitchen.run("--sweep", "--check")
    assert [line for line in said if line.startswith("removable one ")], said
