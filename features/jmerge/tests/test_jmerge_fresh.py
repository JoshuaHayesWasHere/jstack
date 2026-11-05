"""`jmerge` merges a pull request on its passing check while that check ran over today's main.
When main changed any file after its check started, `git merge-tree` of the head onto main
decides how it waits: a clean merge has GitHub merge main into its branch, and the check at the
new head decides, and a conflict waits for a rebase (`test_jmerge_rejudge.py`). When a rebase
drops a line, the pull request waits until its crew says why
(`features/jmerge/tests/test_jmerge_drops.py`), and `jmerge` keeps a branch that moved after its
merge.

The tests run the command against a real origin with several crewmates' worktrees, and a
fake `gh` whose merge is a squash of the head over the origin's main."""

import json
import os
import subprocess
import sys
import time
from datetime import date

import pytest

import test_home_merge as merge
from jmerge import cli, ready, sweep
from test_jmerge_run import ET
from testing.paths import REPO

SOURCE = REPO / "features" / "jmerge" / "src"
PROTECTED = ready.patterns_of((SOURCE / "jmerge" / "protected.txt").read_text())
BEFORE = "1999-06-01T12:00:00Z"
STARTED = {**merge.PASSED, "startedAt": "2000-01-01T12:00:00Z"}
AFTER = {**merge.PASSED, "startedAt": f"{date.today().year + 1}-01-01T00:00:00Z"}
CONFLICT = f"{ready.FRESH_CONFLICT}"
assert BEFORE < STARTED["startedAt"] < AFTER["startedAt"]

GH = """\
#!/bin/sh
echo "$*" >> "$STUB/calls"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
case "$1 $2" in
    "pr list")
        if [ "$3" = "--base" ]; then echo "[]"; else cat "$STUB/list.json"; fi ;;
    "repo view") echo main ;;
    "api --paginate")
        number=${3#*/pulls/}
        cat "$STUB/left-${number%/files}" ;;
    "pr merge")
        [ "$4 $5" = "--squash --match-head-commit" ] || exit 64
        tree=$(git -C "$ORIGIN" merge-tree --write-tree refs/heads/main "$6") || exit 1
        commit=$(git -C "$ORIGIN" commit-tree "$tree" -p refs/heads/main -m "squash (#$3)")
        git -C "$ORIGIN" update-ref refs/heads/main "$commit"
        echo "$commit" > "$STUB/merged-$3" ;;
    "pr view") cat "$STUB/merged-$3" ;;
    "pr close")
        if [ -e "$STUB/no-close" ]; then
            echo "gh: could not close (HTTP 502)" >&2
            exit 1
        fi ;;
    "pr reopen")
        if [ -e "$STUB/no-reopen" ]; then
            echo "gh: could not reopen (HTTP 502)" >&2
            exit 1
        fi ;;
    "api -X")
        number=${4#*/pulls/}
        number=${number%/update-branch}
        echo "$number" >> "$STUB/updated"
        branch=$(cat "$STUB/branch-$number")
        head=$(git -C "$ORIGIN" rev-parse "refs/heads/$branch")
        if [ "$6" != "expected_head_sha=$head" ]; then
            echo '{"message":"expected head sha did not match current head ref."}'
            exit 1
        fi
        if [ -e "$STUB/refuse" ]; then
            echo '{"message":"merge conflict between base and head"}'
            echo "gh: merge conflict between base and head (HTTP 422)" >&2
            exit 1
        fi
        if [ -e "$STUB/down" ]; then
            echo '{"message":"Server Error"}'
            echo "gh: Server Error (HTTP $(cat "$STUB/down"))" >&2
            exit 1
        fi
        tree=$(git -C "$ORIGIN" merge-tree --write-tree refs/heads/main "$head") || exit 1
        commit=$(git -C "$ORIGIN" commit-tree "$tree" -p "$head" -p refs/heads/main -m update)
        git -C "$ORIGIN" update-ref "refs/heads/$branch" "$commit"
        echo '{"message":"Updating pull request branch."}' ;;
    *) exit 64 ;;
esac
"""


def git(cwd, *args, at=None):
    """Run git as a crewmate would, with `at` as the time."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    if at:
        env |= {"GIT_AUTHOR_DATE": at, "GIT_COMMITTER_DATE": at}
    ran = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    )
    return ran.stdout.strip()


def write(top, files):
    for path, text in files.items():
        (top / path).parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            (top / path).unlink()
        else:
            (top / path).write_text(text)
    git(top, "add", "-A")


def url(number):
    return f"https://example.test/pull/{number}"


class Kitchen:
    """A main checkout whose origin's main last changed before any check started. For each
    crewmate a test sends out, it has a worktree, a pushed branch, a brief with a clean
    review, and an open pull request."""

    def __init__(self, tmp_path, files):
        self.tmp = tmp_path
        self.home = home = merge.Home(tmp_path)
        (home.stub / "gh").write_text(GH)
        self.origin = home.origin
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(home.main, "remote", "add", "origin", str(self.origin))
        write(home.main, files)
        git(home.main, "commit", "-q", "-m", "what main had", at=BEFORE)
        git(home.main, "push", "-q", "-u", "origin", "main")
        self.pulls = {}
        self.source = SOURCE
        (home.state / "plan.md").write_text("# a demo repo: plan\n")

    def crew(self, slug, number, files, checks=(STARTED,), renamed=False):
        """Open a crewmate's pull request that changes these files and is ready, and return its
        head."""
        tree = self.tmp / "trees" / slug
        git(self.home.main, "worktree", "add", "-q", "-b", slug, str(tree), "origin/main")
        write(tree, files)
        git(tree, "commit", "-q", "-m", slug, at=BEFORE)
        git(tree, "push", "-q", "-u", "origin", slug)
        head = git(tree, "rev-parse", "HEAD")
        (self.home.stub / f"branch-{number}").write_text(slug)
        with (self.home.state / "plan.md").open("a") as plan:
            plan.write(f"\n## {slug}: a task\nStatus: with crewmate\n")
        self.pulls[slug] = {
            "number": number,
            "url": url(number),
            "title": f"feat: {slug}",
            "headRefName": slug,
            "headRefOid": head,
            "baseRefName": "main",
            "mergeable": "MERGEABLE",
            "statusCheckRollup": merge.rollup(checks),
            "files": [merge.file(path, renamed and path == list(files)[-1]) for path in files],
            "changedFiles": len(files),
            "isDraft": False,
        }
        self.brief(slug, head)
        return head

    def brief(self, slug, reviewed, result="", verdict="clean"):
        """The crewmate's brief: its Result, what the test added to it, and a review."""
        pull = self.pulls[slug]
        (self.home.tasks / f"{slug}.md").write_text(
            f'# {slug}: a task\nTask: "do it"\nPull request: open one when done\n\n'
            f"## Result\nStatus: done\nBranch: {slug}   Pull request: {pull['url']}\n{result}"
            + merge.review(verdict, reviewed)
        )
        (self.home.stub / "list.json").write_text(json.dumps(list(self.pulls.values())))

    def checked(self, slug, *checks):
        self.pulls[slug]["statusCheckRollup"] = merge.rollup(checks)
        self.brief(slug, self.pulls[slug]["headRefOid"])

    def on_main(self, files, rename=None):
        """A merge made by hand now, after every check that started in 2000."""
        main = self.home.main
        git(main, "pull", "-q", "--ff-only")
        if rename:
            git(main, "mv", *rename)
        write(main, files)
        git(main, "commit", "-q", "-m", "by hand")
        git(main, "push", "-q")
        return git(main, "rev-parse", "HEAD")

    def rebase(self, slug, theirs, resolved, line=""):
        """Main changes after the pull request's check, and its crewmate rebases onto main,
        resolves the conflict this way and pushes, writing `line` and nothing else about the
        rebase. The check ran again on the rebased head."""
        was = self.pulls[slug]["headRefOid"]
        tree = self.tmp / "trees" / slug
        self.on_main(theirs)
        git(tree, "fetch", "-q", "origin")
        try:
            git(tree, "-c", "core.editor=true", "rebase", "origin/main")
        except subprocess.CalledProcessError:
            write(tree, resolved)
            git(tree, "-c", "core.editor=true", "rebase", "--continue")
        else:
            raise AssertionError("the rebase met no conflict")
        git(tree, "push", "-q", "--force-with-lease", "origin", slug)
        head = git(tree, "rev-parse", "HEAD")
        self.pulls[slug] |= {"headRefOid": head, "statusCheckRollup": merge.rollup([AFTER])}
        self.brief(slug, was, line.format(was=was, head=head))
        return head

    def updated(self, slug, *checks):
        """GitHub after the fake `gh` merged main into the branch: the head it made, with these
        checks, and no pull request that merged still listed."""
        head = git(self.origin, "rev-parse", f"refs/heads/{slug}")
        self.pulls[slug] |= {"headRefOid": head, "statusCheckRollup": merge.rollup(checks)}
        stub = self.home.stub
        listed = [p for p in self.pulls.values() if not (stub / f"merged-{p['number']}").exists()]
        (self.home.stub / "list.json").write_text(json.dumps(listed))
        return head

    def updates(self):
        path = self.home.stub / "updated"
        return path.read_text().split() if path.exists() else []

    def run(self, *flags):
        said = self.home.sh(
            f'PYTHONPATH="{self.source}" "{sys.executable}" -m jmerge ' + " ".join(flags)
        )
        assert (self.home.code, self.home.stderr) == (0, "")
        return said

    def calls(self, verb="pr merge"):
        return [call for call in merge.calls(self.home) if call.startswith(verb)]

    def tip(self):
        return git(self.origin, "rev-parse", "refs/heads/main")

    def at_main(self, path):
        return git(self.origin, "show", f"refs/heads/main:{path}")


LINES = "".join(f"{n}\n" for n in range(1, 10))


@pytest.fixture
def kitchen(tmp_path):
    return Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES, "Makefile": "check:\n"})


def asked(number, tip):
    """The line of a pull request whose check ran before main moved to `tip`, once GitHub was
    asked to merge main into its branch."""
    return f"wait {number} {url(number)}: " + ready.BASE_MOVED_ASKED.format(
        base="main", tip=tip[:12]
    )


def test_two_ready_pull_requests_on_other_files_the_second_waits_for_a_check_over_the_first(
    kitchen,
):
    """The 20:53 replay: the check of the second pull request started before the first one
    merged, so it never ran over the first's merge, and its own files are no proof that it would
    pass there."""
    one = kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    two = kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    first, second = kitchen.run()
    assert first.startswith("merged 6 one ")
    assert second == asked(7, kitchen.tip())
    about = f"--repo {kitchen.origin}"
    assert merge.calls(kitchen.home) == [
        f"pr list --state open --limit 100 --json {merge.LIST} {about}",
        f"repo view {kitchen.origin} --json defaultBranchRef --jq .defaultBranchRef.name",
        f"pr merge 6 --squash --match-head-commit {one} --subject feat: one (#6)"
        f" --body-file - {about}",
        f"pr view 6 --json mergeCommit --jq .mergeCommit.oid {about}",
        f"pr list --base one --state open --limit 100 --json number {about}",
        f"api -X PUT repos/{{owner}}/{{repo}}/pulls/7/update-branch -f expected_head_sha={two}"
        " --include",
    ]
    updated = kitchen.updated("two", AFTER)
    (said,) = kitchen.run()
    assert said.startswith(f"merged 7 two {kitchen.tip()} ")
    assert f"--match-head-commit {updated} " in kitchen.calls()[1]
    assert kitchen.at_main("a.txt") == ("ours\n" + LINES).strip()
    assert kitchen.at_main("b.txt") == (LINES + "ours\n").strip()


def test_a_second_one_whose_file_the_first_merge_changed_cleanly_waits_for_a_check_over_it(
    kitchen,
):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES, "b.txt": "theirs\n" + LINES})
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    first, second = kitchen.run()
    assert first.startswith("merged 6 one ") and second == asked(7, kitchen.tip())
    kitchen.updated("two", AFTER)
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ")
    assert kitchen.at_main("b.txt") == ("theirs\n" + LINES + "ours\n").strip()


def test_a_second_one_that_conflicts_with_the_first_merge_waits_for_its_rebase(kitchen):
    kitchen.crew("one", 6, {"b.txt": LINES + "theirs\n"})
    two = kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    first, second = kitchen.run()
    assert first.startswith("merged 6 one ")
    assert second == f"wait 7 {url(7)}: {CONFLICT}"
    assert kitchen.calls() == [kitchen.calls()[0]] and " 6 " in kitchen.calls()[0]
    assert git(kitchen.origin, "rev-parse", "refs/heads/two") == two


def test_a_file_main_renamed_under_the_pull_request_is_merged_into_it_as_git_merges_it(kitchen):
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    kitchen.on_main({}, rename=("b.txt", "c.txt"))
    assert kitchen.run() == [asked(7, kitchen.tip())]
    tree = git(kitchen.origin, "show", "refs/heads/two:c.txt")
    assert tree == (LINES + "ours").strip()


def test_main_changing_a_file_the_pull_request_renamed_away_conflicts(kitchen):
    """GitHub lists a rename under its new path alone, and `git merge-tree` sees the old one."""
    kitchen.crew("two", 7, {"b.txt": None, "c.txt": LINES + "ours\n"}, renamed=True)
    (kitchen.home.stub / "left-7").write_text("b.txt\n")
    kitchen.pulls["two"] |= {"files": [merge.file("c.txt", renamed=True)], "changedFiles": 1}
    kitchen.checked("two", STARTED)
    kitchen.on_main({"b.txt": LINES + "theirs\n"})
    assert kitchen.run("--check") == [f"wait 7 {url(7)}: {CONFLICT}"]


def test_a_main_that_moved_only_on_other_files_has_its_check_run_over_today_s_main(kitchen):
    """#923 and #935 changed no file main had changed since their checks, and broke main."""
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    tip = kitchen.on_main({"docs/other.md": "theirs\n", "a.txt": "theirs\n"})
    due = ready.BASE_MOVED_DUE.format(base="main", tip=tip[:12])
    assert kitchen.run("--check") == [f"wait 7 {url(7)}: {due}"]
    assert kitchen.updates() == []
    assert kitchen.run() == [asked(7, tip)]
    assert kitchen.updates() == ["7"]
    updated = kitchen.updated("two", {**merge.RUNNING, "startedAt": AFTER["startedAt"]})
    assert kitchen.run("--check") == [f"wait 7 {url(7)}: check has not passed"]
    kitchen.updated("two", AFTER)
    (ready_line,) = kitchen.run("--check")
    assert ready_line.startswith(f"ready 7 {updated} two two, review carried over: ")
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ")
    assert kitchen.updates() == ["7"]


def test_a_protected_pull_request_is_held_for_the_user_over_a_moved_main(kitchen):
    kitchen.crew("two", 7, {"secrets/prod.json": "{}\n", "b.txt": LINES + "ours\n"})
    kitchen.on_main({"b.txt": "theirs\n" + LINES})
    held = [f"hold 7 {url(7)}: needs user, touches secrets/prod.json"]
    assert kitchen.run() == held
    kitchen.checked("two", AFTER)
    assert kitchen.run() == held
    assert kitchen.calls() == []


def repo(kitchen, monkeypatch):
    """The command's own view of the repo, in this process, with the fake `gh`."""
    home = kitchen.home
    monkeypatch.setenv("PATH", f"{home.stub}:{os.environ['PATH']}")
    monkeypatch.setenv("STUB", str(home.stub))
    monkeypatch.setenv("ORIGIN", str(home.origin))
    home.desk_checked()
    return cli.Repo(home.main, home.state, merge.ME, False, PROTECTED, user=ET)


def test_a_merge_by_hand_between_the_judgment_and_the_merge_has_it_judged_again(
    kitchen, monkeypatch
):
    """Its check did not run over the merge made by hand, so it waits for one that does."""
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    one = ready.pull_request(kitchen.pulls["two"])
    here = repo(kitchen, monkeypatch)
    slug, verb, why, note, judged = here.waits(one, "main")
    assert (slug, verb, why, judged) == ("two", "", "", ready.Judged(tip=kitchen.tip()))
    by_hand = kitchen.on_main({"a.txt": "theirs\n"})
    due = ready.BASE_MOVED_DUE.format(base="main", tip=by_hand[:12])
    assert here.merge(one, slug, note, judged) == f"wait 7 {url(7)}: {due}"
    assert kitchen.tip() == by_hand
    assert not (kitchen.home.stub / "calls").exists()


def test_a_merge_by_hand_that_conflicts_with_it_keeps_it_from_the_merge(kitchen, monkeypatch):
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    one = ready.pull_request(kitchen.pulls["two"])
    here = repo(kitchen, monkeypatch)
    slug, _, _, note, judged = here.waits(one, "main")
    by_hand = kitchen.on_main({"b.txt": LINES + "theirs\n"})
    assert here.merge(one, slug, note, judged) == f"wait 7 {url(7)}: {CONFLICT}"
    assert kitchen.tip() == by_hand
    assert not (kitchen.home.stub / "calls").exists()


def test_a_main_that_moves_at_every_judgment_is_left_for_the_next_run(kitchen, monkeypatch):
    """Its check is dated after each move, so only the tip read before the merge tells it."""
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"}, checks=(AFTER,))
    one = ready.pull_request(kitchen.pulls["two"])
    here = repo(kitchen, monkeypatch)
    judge, moves = here.waits, []

    def waits(*asked):
        found = judge(*asked)
        moves.append(kitchen.on_main({"a.txt": f"move {len(moves)}\n"}))
        return found

    monkeypatch.setattr(here, "waits", waits)
    slug, _, _, note, judged = here.waits(one, "main")
    assert here.merge(one, slug, note, judged) == (
        f"wait 7 {url(7)}: main moved while it was judged"
    )
    assert len(moves) == 3 and kitchen.tip() == moves[-1]
    assert not (kitchen.home.stub / "calls").exists()


@pytest.fixture
def notes(tmp_path):
    return Kitchen(tmp_path, {"n.txt": "one\ntwo\nthree\n"})


def unsaid(notes):
    """Why a pull request held on a drop still waits: at its current head, its crew has not
    said why the rebase dropped the line."""
    return f"with no Dropped on rebase line at {notes.pulls['two']['headRefOid'][:12]}"


def test_a_resolution_that_keeps_both_sides_is_merged_and_says_every_line_kept(notes):
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    head = notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\ntheirs\nours\n"}
    )
    (said,) = notes.run("--check")
    assert said.startswith(f"ready 7 {head} two two, review carried over: range-diff ")
    assert said.endswith(" clean, every line kept")
    kept = said.removeprefix(f"ready 7 {head} two two, ")
    (said,) = notes.run()
    assert said.startswith("merged 7 two ") and f", {kept}, revert: " in said
    assert notes.at_main("n.txt") == "one\ntwo\nthree\ntheirs\nours"


def test_a_resolution_that_took_its_own_side_over_a_line_main_added_waits_on_its_crew(notes):
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\nours\n"}
    )
    held = f"wait 7 {url(7)}: the rebase dropped 1 of main's lines in n.txt {unsaid(notes)}"
    assert notes.run("--check") == [held]
    assert notes.run() == [held]
    assert notes.calls() == []


def test_a_resolution_that_dropped_a_line_the_pull_request_added_waits_on_its_crew(notes):
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\nours too\n"})
    notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\ntheirs\nours\n"}
    )
    assert notes.run() == [
        f"wait 7 {url(7)}: the rebase dropped 1 of its own in n.txt {unsaid(notes)}"
    ]
    assert notes.calls() == []


def test_a_pull_request_held_on_a_drop_waits_on_its_crew_over_a_moved_main(notes):
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\nours\n"}
    )
    notes.pulls["two"]["statusCheckRollup"] = merge.rollup([STARTED])
    (notes.home.stub / "list.json").write_text(json.dumps(list(notes.pulls.values())))
    notes.on_main({"n.txt": "zero\none\ntwo\nthree\ntheirs\n"})
    held = f"wait 7 {url(7)}: the rebase dropped 1 of main's lines in n.txt {unsaid(notes)}"
    assert notes.run() == [held]


def test_a_line_the_pull_request_deletes_is_not_one_the_rebase_dropped(notes):
    """Main moved the line, so main's diff adds the line at its new place, and the pull
    request's own patch removes that same line. The head is right not to have it."""
    notes.crew("two", 7, {"n.txt": "one\nthree\n"})
    notes.rebase("two", {"n.txt": "two\none\nthree\n"}, {"n.txt": "one\nthree\n"})
    (said,) = notes.run()
    assert said.startswith("merged 7 two ") and ", every line kept, revert: " in said
    assert notes.at_main("n.txt") == "one\nthree"


@pytest.mark.parametrize(
    "line",
    [
        "",
        f"Rebase: patch changed in n.txt, before {'c' * 40}, head {{head}}\n",
        "Rebase: patch unchanged, before {was:.7} (local, unpushed), head {head:.7}\n",
        "Rebase: patch unchanged, onto origin/main after it gained 1 commit, before the push\n",
    ],
    ids=["none", "a commit the checkout lacks", "short commits", "no commit"],
)
def test_a_rebase_line_a_crew_wrote_is_read_as_no_line(notes, line):
    """`jmerge` works out the rebase from git, the head the review saw to the head, so a
    `Rebase:` line, true or not, well formed or not, changes nothing of what it says."""
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    notes.rebase(
        "two",
        {"n.txt": "one\ntwo\nthree\ntheirs\n"},
        {"n.txt": "one\ntwo\nthree\ntheirs\nours\n"},
        line,
    )
    (said,) = notes.run("--check")
    assert said.startswith("ready 7 ") and said.endswith(", every line kept"), said


def test_main_is_fetched_before_its_lines_are_looked_for(notes):
    """A merge made on GitHub that the main checkout never fetched. The rebase is onto that
    merge, and the lines that the merge added still count as main's."""
    seen = notes.tip()
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\nours\n"}
    )
    git(notes.home.main, "update-ref", "refs/remotes/origin/main", seen)
    assert notes.run("--check") == [
        f"wait 7 {url(7)}: the rebase dropped 1 of main's lines in n.txt {unsaid(notes)}"
    ]


def fix(notes, was, text):
    """The crewmate commits again after the rebase, for a finding, and says so."""
    tree = notes.tmp / "trees" / "two"
    write(tree, {"n.txt": text})
    git(tree, "commit", "-q", "-m", "the fix")
    git(tree, "push", "-q")
    fixed = git(tree, "rev-parse", "HEAD")
    notes.pulls["two"]["headRefOid"] = fixed
    result = f"Finding: fixed, it is wrong\nFixed: {fixed}\n"
    notes.brief("two", was, result, verdict="findings")


def test_a_line_the_rebase_dropped_and_a_fix_put_back_is_kept(notes):
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    was = notes.pulls["two"]["headRefOid"]
    notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\nours\n"}
    )
    held = f"wait 7 {url(7)}: the rebase dropped 1 of main's lines in n.txt {unsaid(notes)}"
    assert notes.run("--check") == [held]
    fix(notes, was, "one\ntwo\nthree\ntheirs\nours\n")
    (said,) = notes.run()
    assert said.startswith("merged 7 two ") and ", every line kept, revert: " in said
    assert notes.at_main("n.txt") == "one\ntwo\nthree\ntheirs\nours"


def test_a_fix_pushed_after_the_rebase_is_not_a_line_the_rebase_dropped(notes):
    """The rebase kept a line, and a `Fixed:` commit took it out afterwards. That is the fix's
    change, in the pull request's own diff, and not the rebase's."""
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    was = notes.pulls["two"]["headRefOid"]
    notes.rebase(
        "two",
        {"n.txt": "one\ntwo\nthree\ntheirs\n"},
        {"n.txt": "one\ntwo\nthree\ntheirs\nours\n"},
    )
    fix(notes, was, "one\ntwo\nthree\ntheirs\nours, as the review asked\n")
    (said,) = notes.run()
    assert said.startswith(
        f"wait 7 {url(7)}: the rebase changed the content after its review; scoped review of "
    )


DIFF = "diff --git a/n b/n\n--- a/n\n+++ b/n\n@@ -1,0 +2 @@\n{}"


def test_lines_are_counted_as_text_with_blank_ones_and_trailing_space_left_out():
    theirs = DIFF.format("+theirs  \n+\n+theirs\n+++ not a header\n")
    ours = DIFF.format("+ours\n-gone\n")
    assert ready.dropped(theirs, ours, "theirs\ntheirs\t\n++ not a header\nours\n") == (0, 0)
    assert ready.dropped(theirs, ours, "theirs\n++ not a header\n") == (1, 1)
    assert ready.dropped(DIFF.format("+gone\n"), ours, "ours\n") == (0, 0)
    assert ready.dropped(DIFF.format("-ours\n"), ours, "") == (0, 0)


def markers(kitchen):
    """The trees marked on the origin, each with the commit its ref points at."""
    listed = git(kitchen.origin, "for-each-ref", "--format=%(refname) %(objectname)", sweep.MARKERS)
    return dict(line.split() for line in listed.splitlines())


def test_a_sweep_deletes_a_marker_on_the_origin_that_is_more_than_seven_days_old(kitchen):
    """Another clone pushed the old marker, so its commit is not in the main checkout. The
    clone that sweeps need not be the clone that pushed the marker. A marker pushed before a
    marker named what ran is swept the same way."""
    main, other = kitchen.home.main, kitchen.tmp / "other"
    git(kitchen.tmp, "clone", "-q", str(kitchen.origin), str(other))
    aged = {}
    for days, repo, kind in ((8, other, "selected/"), (6, main, "")):
        at = f"{int(time.time()) - days * 86400} +0000"
        write(repo, {"a.txt": f"{days} days ago\n"})
        marked = git(repo, "write-tree")
        commit = git(repo, "commit-tree", marked, "-p", "HEAD", "-m", "a pass", at=at)
        git(repo, "push", "-q", "origin", f"{commit}:refs/jstack/green-tree/{kind}{marked}")
        git(repo, "reset", "-q", "--hard")
        aged[days] = (f"refs/jstack/green-tree/{kind}{marked}", commit, kind + marked[:12])
    old, young = aged[8], aged[6]
    kept = {young[0]: young[1]}
    assert markers(kitchen) == {old[0]: old[1]} | kept
    removable = (
        f"removable green-tree/{old[2]} no-thread: the marker of a tree that passed 8 days ago"
    )
    assert [line for line in kitchen.run("--sweep", "--check") if "green-tree" in line] == [
        removable
    ]
    assert markers(kitchen) == {old[0]: old[1]} | kept
    removed = removable.replace("removable", "removed", 1)
    assert [line for line in kitchen.run("--sweep") if "green-tree" in line] == [removed]
    assert markers(kitchen) == kept
    assert [line for line in kitchen.run("--sweep") if "green-tree" in line] == []


def test_a_remote_branch_that_moved_after_the_merge_is_kept(kitchen):
    head = kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    other = kitchen.tmp / "other"
    git(kitchen.tmp, "clone", "-q", "-b", "two", str(kitchen.origin), str(other))
    write(other, {"late.txt": "after the review\n"})
    git(other, "commit", "-q", "-m", "late")
    git(other, "push", "-q")
    late = git(other, "rev-parse", "HEAD")
    (said,) = kitchen.run()
    kept = (
        "kept: the remote branch two, the worktree and the local branch are removed "
        "(it is not at the merged head on the origin)"
    )
    assert said.startswith("merged 7 two ") and f", {kept}, revert: " in said
    assert git(kitchen.origin, "rev-parse", "refs/heads/two") == late != head
    assert not (kitchen.tmp / "trees" / "two").exists()
