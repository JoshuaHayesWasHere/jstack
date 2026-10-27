"""A project's integration branches are the branches that its state's `integration` file
names, one to a line. `jmerge` merges a pull request into one of them as it merges one into
the default branch. It judges against that branch whether the pull request's check is stale
and whether the branch is red, and it squashes the pull request into that branch. The pull
request that lands an integration branch on the default branch merges with a merge commit
where the repo allows one, and as a squash where it allows only that, and `jmerge` keeps the
branch. With no such file, `jmerge` holds a pull request into another
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
    "api repos/{owner}/{repo}") cat "$STUB/repo.json" ;;
    "api repos/{owner}/{repo}/commits/"*)
        branch=${2#repos/\\{owner\\}/\\{repo\\}/commits/}
        cat "$STUB/runs-${branch%/check-runs}" 2> /dev/null || echo '{"check_runs": []}' ;;
    "pr merge")
        base=$(jq -r --argjson n "$3" \
            '.[] | select(.number == $n) | .baseRefName' "$STUB/list.json")
        tree=$(git -C "$ORIGIN" merge-tree --write-tree "refs/heads/$base" "$6") || exit 1
        case "$4 $5" in
            "--squash --match-head-commit") parents="-p refs/heads/$base" ;;
            "--merge --match-head-commit") parents="-p refs/heads/$base -p $6"
                if ! jq -e .allow_merge_commit "$STUB/repo.json" > /dev/null; then
                    echo "GraphQL: Merge commits are not allowed on this repository." >&2
                    exit 1
                fi ;;
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

BRANCH = "migration"
READ = "api repos/{owner}/{repo}"


@pytest.fixture
def kitchen(tmp_path):
    kitchen = Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES, "Makefile": "check:\n"})
    (kitchen.home.stub / "gh").write_text(GH)
    allows(kitchen, merge=True, squash=True, rebase=True)
    git(kitchen.home.main, "push", "-q", "origin", f"main:{BRANCH}")
    return kitchen


def allows(kitchen, merge, squash, rebase):
    """The repo's settings say which merge methods it allows, as GitHub's repo endpoint gives
    them: https://docs.github.com/en/rest/repos/repos#get-a-repository"""
    said = {"allow_merge_commit": merge, "allow_squash_merge": squash, "allow_rebase_merge": rebase}
    (kitchen.home.stub / "repo.json").write_text(json.dumps(said))


def reads(kitchen):
    """Each time this run asked GitHub for the repo's settings."""
    return [call for call in kitchen.calls(READ) if call == READ]


def integration(kitchen, *branches):
    """The project's state names these branches as its integration branches."""
    (kitchen.home.state / "integration").write_text("".join(f"{one}\n" for one in branches))


def into(kitchen, slug, number, files, base=BRANCH):
    """Open a crewmate's pull request into `base`, ready to merge, and return its head."""
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
    held = ready.BASE.format(base=BRANCH, default="main")
    assert kitchen.run() == [f"wait 6 {url(6)}: {held}"]
    assert kitchen.calls() == []


def test_a_pull_request_into_an_integration_branch_is_ready_and_check_merges_nothing(kitchen):
    head = into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    assert kitchen.run("--check") == [f"ready 6 {head} one one"]
    assert kitchen.calls() == []


def test_a_pull_request_into_an_integration_branch_waits_on_no_check_of_its_own(kitchen):
    """check.yml runs a pull request's check only into main: work into an integration branch is
    checked on each push to the branch, whose red hold stands for it, and once more at main's gate
    when the branch lands. So a pull request into the branch is ready with no `check` run, and one
    into main is not."""
    head = kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES}, checks=())
    kitchen.pulls["one"]["baseRefName"] = BRANCH
    kitchen.brief("one", head)
    integration(kitchen, BRANCH)
    assert kitchen.run("--check") == [f"ready 6 {head} one one"]
    kitchen.pulls["one"]["baseRefName"] = "main"
    kitchen.brief("one", head)
    no_run = ready.NO_RUN.format(check="check", head=head[:12])
    assert kitchen.run("--check") == [f"wait 6 {url(6)}: {no_run}"]


def test_it_squashes_into_that_branch_and_the_merged_line_names_it(kitchen):
    main = tip(kitchen, "main")
    head = into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    (said,) = kitchen.run()
    commit = tip(kitchen, BRANCH)
    assert said.startswith(f'merged 6 one {commit} "feat: one", into {BRANCH}, ')
    assert kitchen.calls() == [
        f"pr merge 6 --squash --match-head-commit {head} --subject feat: one (#6)"
        f" --body-file - --repo {kitchen.origin}"
    ]
    assert git(kitchen.origin, "show", f"refs/heads/{BRANCH}:a.txt") == ("ours\n" + LINES).strip()
    assert tip(kitchen, "main") == main


def test_a_merge_into_the_default_branch_still_names_no_base(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ") and ", into " not in said


def test_it_waits_when_its_own_base_changed_its_file_after_the_check(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    on(kitchen, BRANCH, {"a.txt": LINES + "theirs\n"})
    (said,) = kitchen.run()
    assert said == f"wait 6 {url(6)}: " + STALE.replace("main", BRANCH, 1).format("a.txt")
    assert kitchen.calls() == []


def test_main_changing_its_file_does_not_make_a_pull_request_into_the_branch_stale(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    kitchen.on_main({"a.txt": LINES + "theirs\n"})
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ")


def test_a_red_main_holds_a_pull_request_into_main_and_not_one_into_the_branch(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    integration(kitchen, BRANCH)
    queue_of(kitchen.home, [])
    main_says(kitchen.home, red="c" * 40, green="a" * 40)
    one, two = kitchen.run()
    assert one.startswith("merged 6 one ")
    assert two == f"wait 7 {url(7)}: " + ready.MAIN_RED.format(sha="c" * 12)


def test_a_red_branch_holds_a_pull_request_into_it_and_not_one_into_main(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    integration(kitchen, BRANCH)
    red = runs(kitchen, BRANCH, "success", "failure")
    one, two = kitchen.run()
    assert one == f"wait 6 {url(6)}: " + ready.BASE_RED.format(base=BRANCH, sha=red[:12])
    assert two.startswith("merged 7 two ")


@pytest.mark.parametrize("conclusions", [(), ("success", "skipped", "neutral", "cancelled")])
def test_a_branch_whose_latest_check_did_not_fail_holds_nothing(kitchen, conclusions):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    runs(kitchen, BRANCH, *conclusions)
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ")


def test_the_landing_of_the_branch_on_main_is_a_merge_commit_and_keeps_the_branch(kitchen):
    main = tip(kitchen, "main")
    head = kitchen.crew(BRANCH, 9, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    (said,) = kitchen.run()
    commit = tip(kitchen, "main")
    assert said.startswith(f'merged 9 {BRANCH} {commit} "feat: {BRANCH}", ')
    assert kitchen.calls() == [
        f"pr merge 9 --merge --match-head-commit {head} --body-file - --repo {kitchen.origin}"
    ]
    assert git(kitchen.origin, "rev-list", "--parents", "-n", "1", commit).split()[1:] == [
        main,
        head,
    ]
    assert ", landed with a merge commit, " in said
    assert tip(kitchen, BRANCH) == head
    assert BRANCH in git(kitchen.home.main, "branch", "--format=%(refname:short)").split()


def test_a_repo_that_allows_only_squashes_lands_the_branch_as_a_squash_and_keeps_it(kitchen):
    main = tip(kitchen, "main")
    head = kitchen.crew(BRANCH, 9, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    allows(kitchen, merge=False, squash=True, rebase=False)
    (said,) = kitchen.run()
    commit = tip(kitchen, "main")
    assert said.startswith(f'merged 9 {BRANCH} {commit} "feat: {BRANCH}", ')
    squashed = f"landed as a squash: each unit's pull request into {BRANCH} is its own record"
    assert f", {squashed}, " in said
    assert f", kept: {BRANCH} is an integration branch, " in said
    assert kitchen.calls() == [
        f"pr merge 9 --squash --match-head-commit {head} --subject feat: {BRANCH} (#9)"
        f" --body-file - --repo {kitchen.origin}"
    ]
    assert reads(kitchen) == [READ]
    assert git(kitchen.origin, "rev-list", "--parents", "-n", "1", commit).split()[1:] == [main]
    assert git(kitchen.origin, "show", "refs/heads/main:a.txt") == ("ours\n" + LINES).strip()
    assert tip(kitchen, BRANCH) == head
    assert BRANCH in git(kitchen.home.main, "branch", "--format=%(refname:short)").split()


def test_a_pull_request_into_the_branch_does_not_read_the_repos_settings(kitchen):
    into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    allows(kitchen, merge=False, squash=True, rebase=False)
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ") and ", landed " not in said
    assert reads(kitchen) == []


def test_a_repo_that_allows_neither_a_merge_commit_nor_a_squash_waits_and_says_so(kitchen):
    kitchen.crew(BRANCH, 9, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    allows(kitchen, merge=False, squash=False, rebase=True)
    main = tip(kitchen, "main")
    (said,) = kitchen.run()
    assert said == f"wait 9 {url(9)}: " + ready.LANDING_UNALLOWED.format(allowed="rebase merges")
    assert said.endswith(": the repo allows rebase merges only, not a merge commit or a squash")
    assert kitchen.calls() == []
    assert tip(kitchen, "main") == main


def test_a_landing_waits_when_the_repos_settings_cannot_be_read(kitchen):
    kitchen.crew(BRANCH, 9, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    (kitchen.home.stub / "repo.json").unlink()
    (said,) = kitchen.run()
    assert said.startswith(f"wait 9 {url(9)}: {ready.NO_SETTINGS}: ")
    assert kitchen.calls() == []
    (kitchen.home.stub / "repo.json").write_text("[]")
    (said,) = kitchen.run()
    assert said == f"wait 9 {url(9)}: {ready.NO_SETTINGS}: GitHub's answer is not a repo"
    assert kitchen.calls() == []


def test_a_repo_answer_with_no_allow_keys_waits_as_unread_and_keeps_the_branch(kitchen):
    """GitHub leaves the allow_* keys out of the repo it gives a token without push access, so
    the answer says nothing of the merge methods, and the landing waits as unread."""
    kitchen.crew(BRANCH, 9, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    said = {"name": "jstack", "full_name": "o/jstack", "default_branch": "main"}
    (kitchen.home.stub / "repo.json").write_text(json.dumps(said))
    main, branch = tip(kitchen, "main"), tip(kitchen, BRANCH)
    (said,) = kitchen.run()
    unread = "GitHub gives them to a token with push access only"
    assert said == f"wait 9 {url(9)}: {ready.NO_SETTINGS}: {unread}"
    assert kitchen.calls() == []
    assert tip(kitchen, "main") == main
    assert tip(kitchen, BRANCH) == branch
    assert BRANCH in git(kitchen.home.main, "branch", "--format=%(refname:short)").split()


def test_blank_lines_and_spaces_in_the_file_name_no_branch(kitchen):
    head = into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    (kitchen.home.state / "integration").write_text(f"\n  {BRANCH}  \n\n")
    assert kitchen.run("--check") == [f"ready 6 {head} one one"]


def check_run(name, conclusion, started, sha="d" * 40):
    return {
        "name": name,
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "started_at": started,
    }


def test_a_check_that_failed_and_then_passed_on_a_rerun_is_no_red_branch():
    reran = [
        check_run("check", "success", "2026-10-21T10:05:00Z"),
        check_run("check", "failure", "2026-10-21T10:00:00Z"),
    ]
    assert rows.base_red(BRANCH, reran, "one") == ""
    failed_last = [*reran, check_run("check", "failure", "2026-10-21T10:10:00Z")]
    assert rows.base_red(BRANCH, failed_last, "one") == ready.BASE_RED.format(
        base=BRANCH, sha="d" * 12
    )


def test_a_check_still_running_is_no_red_branch():
    running = {**check_run("check", None, "2026-10-21T10:00:00Z"), "status": "in_progress"}
    assert rows.base_red(BRANCH, [running], "one") == ""


def test_the_fix_of_a_red_main_is_not_held_by_a_red_branch():
    failed = [check_run("check", "failure", "2026-10-21T10:00:00Z")]
    assert rows.base_red(BRANCH, failed, "main-red-cccccccccccc") == ""


def fixes(text, line):
    """The brief `text` with `line` in its head."""
    return text.replace("Pull request:", f"{line}\nPull request:", 1)


@pytest.mark.parametrize(
    ("slug", "line"),
    [
        (f"integration-red-{BRANCH}-{'d' * 12}", ""),
        ("sync-main", f"Fixes red: {BRANCH} at {'d' * 12}"),
        ("sync-main", f"Fixes red: {BRANCH} at {'d' * 40}"),
    ],
)
def test_the_fix_of_a_red_branch_at_its_tip_is_not_held_by_it(slug, line):
    failed = [check_run("check", "failure", "2026-10-21T10:00:00Z")]
    assert rows.base_red(BRANCH, failed, slug, fixes(f"# {slug}\nPull request: x\n", line)) == ""


@pytest.mark.parametrize(
    ("slug", "line"),
    [
        (f"integration-red-other-{'d' * 12}", ""),
        (f"integration-red-{BRANCH}-{'e' * 12}", ""),
        (f"integration-red-{BRANCH}", ""),
        ("sync-main", f"Fixes red: other at {'d' * 12}"),
        ("sync-main", f"Fixes red: {BRANCH} at {'e' * 12}"),
        ("sync-main", f"Fixes red: {BRANCH} at {'d' * 6}"),
        ("sync-main", f"Fixes red: {BRANCH}"),
        ("sync-main", f"Fixes: {BRANCH} at {'d' * 12}"),
    ],
)
def test_a_fix_of_another_red_is_held_by_a_red_branch(slug, line):
    failed = [check_run("check", "failure", "2026-10-21T10:00:00Z")]
    hold = ready.BASE_RED.format(base=BRANCH, sha="d" * 12)
    assert rows.base_red(BRANCH, failed, slug, fixes(f"# {slug}\nPull request: x\n", line)) == hold


def test_a_fixes_red_line_under_the_result_is_no_fix():
    failed = [check_run("check", "failure", "2026-10-21T10:00:00Z")]
    text = f"# one\nPull request: x\n\n## Result\nFixes red: {BRANCH} at {'d' * 12}\n"
    assert rows.base_red(BRANCH, failed, "one", text) == ready.BASE_RED.format(
        base=BRANCH, sha="d" * 12
    )


@pytest.mark.parametrize("named", ["slug", "line"])
def test_a_red_branch_lets_only_its_fix_through_and_a_green_tip_judges_all_again(kitchen, named):
    integration(kitchen, BRANCH)
    red = runs(kitchen, BRANCH, "success", "failure")
    fix = f"integration-red-{BRANCH}-{red[:12]}" if named == "slug" else "sync"
    heads = {
        "one": into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES}),
        "two": into(kitchen, "two", 7, {"b.txt": LINES + "ours\n"}),
        fix: into(kitchen, fix, 8, {"c.txt": "fixed\n"}),
    }
    if named == "line":
        brief = kitchen.home.tasks / f"{fix}.md"
        brief.write_text(fixes(brief.read_text(), f"Fixes red: {BRANCH} at {red[:12]}"))
    hold = ready.BASE_RED.format(base=BRANCH, sha=red[:12])
    assert kitchen.run("--check") == [
        f"wait 6 {url(6)}: {hold}",
        f"wait 7 {url(7)}: {hold}",
        f"ready 8 {heads[fix]} {fix} {fix}",
    ]
    runs(kitchen, BRANCH, "success", "success")
    assert kitchen.run("--check") == [
        f"ready {number} {heads[slug]} {slug} {slug}"
        for number, slug in ((6, "one"), (7, "two"), (8, fix))
    ]


def viewed(kitchen, number, head, base):
    """What GitHub returns when a sweep asks about a merged pull request."""
    said = {"state": "MERGED", "headRefOid": head, "baseRefName": base}
    (kitchen.home.stub / f"view-{number}").write_text(json.dumps(said))


@pytest.mark.parametrize("merge", [True, False])
def test_a_sweep_keeps_the_integration_branch_after_its_landing_merged(kitchen, merge):
    head = kitchen.crew(BRANCH, 9, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    allows(kitchen, merge=merge, squash=True, rebase=False)
    (said,) = kitchen.run()
    assert said.startswith(f"merged 9 {BRANCH} ")
    viewed(kitchen, 9, head, "main")
    said = kitchen.run("--sweep", "--check")
    assert f"kept {BRANCH}: it is an integration branch" in said
    assert not [line for line in said if line.startswith(f"removable {BRANCH} ")]


def test_a_sweep_counts_a_pull_request_merged_into_the_branch_as_merged(kitchen):
    head = into(kitchen, "one", 6, {"a.txt": "ours\n" + LINES})
    integration(kitchen, BRANCH)
    kitchen.brief("one", head, "Left: none\n")
    git(kitchen.home.main, "worktree", "remove", str(kitchen.tmp / "trees" / "one"))
    (kitchen.home.stub / "list.json").write_text("[]")
    viewed(kitchen, 6, head, BRANCH)
    said = kitchen.run("--sweep", "--check")
    assert [line for line in said if line.startswith("removable one ")], said


@pytest.mark.parametrize(
    ("branch", "slug"),
    [
        ("release/macos", "integration-red-release-macos-aaaaaaaaaaaa"),
        ("release/Mac OS+x", "integration-red-release-mac-os-x-aaaaaaaaaaaa"),
        ("-é.", "integration-red-branch-aaaaaaaaaaaa"),
    ],
)
def test_the_fix_row_of_a_branch_is_named_by_its_branch_and_its_red_tip(branch, slug):
    """jmerge lets through the row by the name jbus files it under, the one rule both read
    (`integration_fix`, `jbus.sidered.integration_branches`)."""
    assert rows.integration_fix(branch, "a" * 40) == slug
    assert rows.integration_fix(branch, "") == slug.removesuffix("a" * 12)
