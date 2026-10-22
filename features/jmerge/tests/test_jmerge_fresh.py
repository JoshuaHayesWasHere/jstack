"""`jmerge` merges a pull request only when its passing check still applies to today's main.
When a pull request's check started before main changed one of its files, or a file that CI
reads, the pull request waits for a fresh check. Where the repo asks for it, that check is the
repo's own command on the head merged over today's main, and otherwise it is a rebase. When a
rebase drops a line, the pull request waits until its crew says why
(`features/jmerge/tests/test_jmerge_drops.py`), and `jmerge` keeps a branch that moved after
its merge.

The tests run the command against a real origin with several crewmates' worktrees, and a
fake `gh` whose merge is a squash of the head over the origin's main."""

import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date

import pytest

import test_home_merge as merge
from jmerge import cli, ready, sweep
from test_jmerge_guarded import ET, GUARDED, LISTED
from testing.paths import REPO

SOURCE = REPO / "features" / "jmerge" / "src"
PROTECTED = ready.patterns_of((SOURCE / "jmerge" / "protected.txt").read_text())
CI = ready.patterns_of((SOURCE / "jmerge" / "ci-paths.txt").read_text())
BEFORE = "1999-06-01T12:00:00Z"
STARTED = {**merge.PASSED, "startedAt": "2000-01-01T12:00:00Z"}
AFTER = {**merge.PASSED, "startedAt": f"{date.today().year + 1}-01-01T00:00:00Z"}
STALE = "main changed {} after its check started at 07:00 ET; it needs a fresh check"
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

    def rebase(self, slug, theirs, resolved, before=None):
        """Main changes after the pull request's check, and its crewmate rebases onto main,
        resolves the conflict this way, pushes, and says that the patch changed in those
        files. The check ran again on the rebased head."""
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
        line = f"Rebase: patch changed in {' '.join(resolved)}, before {before or was}, head {head}"
        self.brief(slug, was, f"{line}\n")
        return head

    def run(self, *flags):
        said = self.home.sh(
            f'PYTHONPATH="{self.source}" "{sys.executable}" -m jmerge --home {merge.ME} '
            + " ".join(flags)
        )
        assert (self.home.code, self.home.stderr) == (0, "")
        return said

    def after_check(self, *flags):
        """A run that starts a fresh check says that the check is queued, and returns. When the
        check ends, it records its result, and the next run reads that result."""
        before = known(self)
        queued = self.run(*flags)
        assert any(line.endswith(ready.FRESH_QUEUED) for line in queued), queued
        settled(self, before)
        return self.run(*flags)

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


def test_two_ready_pull_requests_on_other_files_both_merge_each_judged_after_the_last(kitchen):
    """The 20:53 replay: the check of the second pull request started before the first one
    merged."""
    one = kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    two = kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    first, second = kitchen.run()
    assert first.startswith("merged 6 one ") and second.startswith("merged 7 two ")
    about = f"--repo {kitchen.origin}"
    assert merge.calls(kitchen.home) == [
        f"pr list --state open --json {merge.LIST} {about}",
        f"repo view {kitchen.origin} --json defaultBranchRef --jq .defaultBranchRef.name",
        f"pr merge 6 --squash --match-head-commit {one} --subject feat: one (#6)"
        f" --body-file - {about}",
        f"pr view 6 --json mergeCommit --jq .mergeCommit.oid {about}",
        f"pr list --base one --state open --json number {about}",
        f"pr merge 7 --squash --match-head-commit {two} --subject feat: two (#7)"
        f" --body-file - {about}",
        f"pr view 7 --json mergeCommit --jq .mergeCommit.oid {about}",
        f"pr list --base two --state open --json number {about}",
    ]
    assert kitchen.at_main("a.txt") == ("ours\n" + LINES).strip()
    assert kitchen.at_main("b.txt") == (LINES + "ours\n").strip()
    assert git(kitchen.home.main, "rev-parse", "HEAD") == kitchen.tip() == second.split()[3]


def test_a_second_one_that_changes_a_file_the_first_merge_changed_waits_with_it_named(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES, "b.txt": "theirs\n" + LINES})
    two = kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    first, second = kitchen.run()
    assert first.startswith("merged 6 one ")
    assert second == f"wait 7 {url(7)}: {STALE.format('b.txt')}"
    assert kitchen.calls() == [kitchen.calls()[0]] and " 6 " in kitchen.calls()[0]
    assert git(kitchen.origin, "rev-parse", "refs/heads/two") == two
    kitchen.checked("two", AFTER)
    (said,) = [line for line in kitchen.run() if " 7 " in line]
    assert said.startswith("merged 7 two ")
    assert kitchen.at_main("b.txt") == ("theirs\n" + LINES + "ours\n").strip()


def test_a_first_merge_that_changed_only_a_file_ci_reads_makes_the_second_wait(kitchen):
    kitchen.crew("one", 6, {"Makefile": "check:\n\ttrue\n"})
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    first, second = kitchen.run()
    assert first.startswith("merged 6 one ")
    assert second == f"wait 7 {url(7)}: {STALE.format('Makefile')}"


def test_a_file_main_renamed_is_changed_under_the_pull_request_that_changes_it(kitchen):
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    kitchen.on_main({}, rename=("b.txt", "c.txt"))
    assert kitchen.run() == [f"wait 7 {url(7)}: {STALE.format('b.txt')}"]
    assert kitchen.calls() == []


def test_a_file_the_pull_request_renamed_is_one_of_its_paths(kitchen):
    """GitHub lists a rename under its new path alone, so `jmerge` asks for the file's old path."""
    kitchen.crew("two", 7, {"b.txt": None, "c.txt": LINES}, renamed=True)
    (kitchen.home.stub / "left-7").write_text("b.txt\n")
    kitchen.pulls["two"] |= {"files": [merge.file("c.txt", renamed=True)], "changedFiles": 1}
    kitchen.checked("two", STARTED)
    kitchen.on_main({"b.txt": "theirs\n" + LINES})
    assert kitchen.run("--check") == [f"wait 7 {url(7)}: {STALE.format('b.txt')}"]


def test_a_main_that_moved_on_other_files_leaves_the_check_standing(kitchen):
    two = kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    kitchen.on_main({"docs/other.md": "theirs\n", "a.txt": "theirs\n"})
    assert kitchen.run("--check") == [f"ready 7 {two} two two"]
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ")


SELECTOR = REPO / "scripts" / "select_tests.py"
SELECTED = {
    "pyproject.toml": "[project]\nname = 'demo'\n",
    "Makefile": "check:\n",
    "scripts/select_tests.py": SELECTOR.read_text(),
    "features/verify-jstack/project-skill/map.md": "Cross-cutting:\n",
    "src/demo/__init__.py": "",
    "src/demo/one.py": LINES,
    "src/demo/two.py": LINES,
    "conftest.py": "",
    "testing/tests/test_one.py": "import demo.one\n",
    "testing/tests/test_two.py": "import demo.two\n",
    "testing/tests/test_whole.py": "",
}


@pytest.fixture
def selected(tmp_path):
    """A repo with its own `scripts/select_tests.py`, and a pull request whose check passed
    before main changed the module `src/demo/two.py`. The test `testing/tests/test_two.py`
    imports that module. No test file is one that every change selects."""
    kitchen = Kitchen(tmp_path, SELECTED)
    checked = Checked(kitchen, "true", "src/demo/two.py")
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_QUEUED}"]
    settled(kitchen)
    assert checked.known()["7"]["result"] == ready.PASSED
    return kitchen, checked


def test_a_pass_over_an_older_main_stands_when_main_moved_only_off_its_tests(selected):
    kitchen, checked = selected
    now = kitchen.on_main({"src/demo/one.py": "theirs\n" + LINES})
    kept = (
        f"fresh: {checked.command} passed on {checked.head[:12]} over {checked.main[:12]}, "
        f"kept over {now[:12]}: main's change since meets none of its tests"
    )
    assert kitchen.run("--check") == [f"ready 7 {checked.head} two two, {kept}"]
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ") and f", {kept}, revert: " in said
    assert len(checked.ran()) == 1


@pytest.mark.parametrize(
    "theirs",
    [
        pytest.param({"testing/tests/test_two.py": "import demo.two\nimport os\n"}, id="its-tests"),
        pytest.param({"pyproject.toml": "[project]\nname = 'other'\n"}, id="all"),
    ],
)
def test_a_pass_over_an_older_main_is_checked_again_when_main_moved_on_its_tests(selected, theirs):
    kitchen, checked = selected
    kitchen.on_main(theirs)
    before = known(kitchen)
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_QUEUED}"]
    settled(kitchen, before)
    assert len(checked.ran()) == 2 and checked.known()["7"]["main"] == kitchen.tip()


def test_an_import_the_pull_request_adds_is_read_from_the_tree_it_lands_as(tmp_path):
    """In main's checkout `two.py` imports nothing. In the pull request's head, `two.py`
    imports `one.py`, so `testing/tests/test_two.py` also runs `one.py` there. The tests of
    the pull request therefore run main's change to `one.py`."""
    kitchen = Kitchen(tmp_path, SELECTED)
    checked = Checked(kitchen, "true", "src/demo/two.py", LINES + "import demo.one\n")
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_QUEUED}"]
    settled(kitchen)
    kitchen.on_main({"src/demo/one.py": "theirs\n" + LINES})
    before = known(kitchen)
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_QUEUED}"]
    settled(kitchen, before)
    assert len(checked.ran()) == 2


def test_a_test_every_change_selects_is_one_in_common(selected):
    """A test that reads the whole tree can fail on the two changes together."""
    kitchen, checked = selected
    map_file = "features/verify-jstack/project-skill/map.md"
    whole = {map_file: "Cross-cutting: `testing/tests/test_whole.py`\n"}
    write(kitchen.home.main, whole)
    git(kitchen.home.main, "commit", "-q", "-m", "a whole-tree test")
    git(kitchen.home.main, "push", "-q")
    before = known(kitchen)
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_QUEUED}"]
    settled(kitchen, before)
    assert len(checked.ran()) == 2


def test_a_pass_stands_only_in_a_repo_that_says_what_its_tests_select(kitchen):
    checked = Checked(kitchen, "true")
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_QUEUED}"]
    settled(kitchen)
    kitchen.on_main({"a.txt": "theirs\n" + LINES})
    before = known(kitchen)
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_QUEUED}"]
    settled(kitchen, before)
    assert len(checked.ran()) == 2


def test_more_than_five_files_are_counted_not_named(kitchen):
    files = {f"f{n}.txt": "ours\n" for n in range(7)}
    kitchen.crew("two", 7, files)
    kitchen.on_main({path: "theirs\n" for path in files})
    named = "f0.txt f1.txt f2.txt f3.txt f4.txt and 2 more"
    assert kitchen.run() == [f"wait 7 {url(7)}: {STALE.format(named)}"]


def test_a_protected_pull_request_is_held_for_the_user_and_starts_no_fresh_check(kitchen):
    (kitchen.home.state / "fresh-check").write_text("true\n")
    kitchen.crew("two", 7, {"secrets/prod.json": "{}\n", "b.txt": LINES + "ours\n"})
    kitchen.on_main({"b.txt": "theirs\n" + LINES})
    held = [f"hold 7 {url(7)}: needs user, touches secrets/prod.json"]
    assert kitchen.run() == held
    assert not (kitchen.home.state / "fresh.json").exists()
    kitchen.checked("two", AFTER)
    assert kitchen.run() == held
    assert kitchen.calls() == []


def test_a_guarded_path_main_changed_waits_for_a_rebase_and_gets_no_local_check(kitchen):
    kitchen.source = kitchen.tmp / "listed"
    package = kitchen.source / "jmerge"
    shutil.copytree(SOURCE / "jmerge", package, ignore=shutil.ignore_patterns("__pycache__"))
    (package / "guarded.txt").write_text(LISTED)
    kitchen.crew("two", 7, {"skills/home/SKILL.md": "ours\n"})
    kitchen.on_main({"skills/home/SKILL.md": "theirs\n"})
    (kitchen.home.state / "fresh-check").write_text("true\n")
    assert kitchen.run() == [
        f"wait 7 {url(7)}: guarded (touches skills/home/SKILL.md), main changed "
        "skills/home/SKILL.md after its check started at 07:00 ET; it needs a rebase"
    ]
    assert not (kitchen.home.state / "fresh.json").exists()


def repo(kitchen, monkeypatch, fresh=None):
    """The command's own view of the repo, in this process, with the fake `gh`."""
    home = kitchen.home
    monkeypatch.setenv("PATH", f"{home.stub}:{os.environ['PATH']}")
    monkeypatch.setenv("STUB", str(home.stub))
    monkeypatch.setenv("ORIGIN", str(home.origin))
    return cli.Repo(
        home.main, home.state, merge.ME, False, None, PROTECTED, GUARDED, CI, fresh=fresh, user=ET
    )


def test_a_merge_by_hand_between_the_judgment_and_the_merge_has_it_judged_again(
    kitchen, monkeypatch
):
    head = kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    one = ready.pull_request(kitchen.pulls["two"])
    here = repo(kitchen, monkeypatch)
    slug, verb, why, note, judged = here.waits(one, "main")
    assert (slug, verb, why, judged) == ("two", "", "", ready.Judged(tip=kitchen.tip()))
    by_hand = kitchen.on_main({"a.txt": "theirs\n"})
    said = here.merge(one, slug, note, judged)
    assert said.startswith("merged 7 two ")
    assert git(kitchen.origin, "rev-parse", "refs/heads/main~1") == by_hand
    assert kitchen.calls() == [
        f"pr merge 7 --squash --match-head-commit {head} --subject feat: two (#7)"
        f" --body-file - --repo {kitchen.origin}"
    ]


def test_a_merge_by_hand_that_changed_its_file_keeps_it_from_the_merge(kitchen, monkeypatch):
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    one = ready.pull_request(kitchen.pulls["two"])
    here = repo(kitchen, monkeypatch)
    slug, _, _, note, judged = here.waits(one, "main")
    by_hand = kitchen.on_main({"b.txt": "theirs\n" + LINES})
    assert here.merge(one, slug, note, judged) == (f"wait 7 {url(7)}: {STALE.format('b.txt')}")
    assert kitchen.tip() == by_hand
    assert not (kitchen.home.stub / "calls").exists()


def test_a_main_that_moves_at_every_judgment_is_left_for_the_next_run(kitchen, monkeypatch):
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
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


def test_a_pull_request_held_on_a_drop_starts_no_fresh_check(notes):
    """While the pull request waits for its crew, `jmerge` runs no check, because a check
    could not end the wait."""
    (notes.home.state / "fresh-check").write_text("true\n")
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\nours\n"}
    )
    notes.pulls["two"]["statusCheckRollup"] = merge.rollup([STARTED])
    (notes.home.stub / "list.json").write_text(json.dumps(list(notes.pulls.values())))
    notes.on_main({"n.txt": "zero\none\ntwo\nthree\ntheirs\n"})
    held = f"wait 7 {url(7)}: the rebase dropped 1 of main's lines in n.txt {unsaid(notes)}"
    assert notes.run() == [held]
    assert not (notes.home.state / "fresh.json").exists()
    assert not (notes.home.state / "fresh").exists()


def test_a_line_the_pull_request_deletes_is_not_one_the_rebase_dropped(notes):
    """Main moved the line, so main's diff adds the line at its new place, and the pull
    request's own patch removes that same line. The head is right not to have it."""
    notes.crew("two", 7, {"n.txt": "one\nthree\n"})
    notes.rebase("two", {"n.txt": "two\none\nthree\n"}, {"n.txt": "one\nthree\n"})
    (said,) = notes.run()
    assert said.startswith("merged 7 two ") and ", every line kept, revert: " in said
    assert notes.at_main("n.txt") == "one\nthree"


def test_a_rebase_from_a_commit_the_main_checkout_does_not_have_waits(notes):
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    gone = "c" * 40
    notes.rebase(
        "two",
        {"n.txt": "one\ntwo\nthree\ntheirs\n"},
        {"n.txt": "one\ntwo\nthree\ntheirs\nours\n"},
        before=gone,
    )
    assert notes.run() == [
        f"wait 7 {url(7)}: its Rebase line cannot be checked: "
        f"the patch of {gone} cannot be worked out in the main checkout"
    ]


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


def fix(notes, was, rebased, text):
    """The crewmate commits again after the rebase, for a finding, and says so."""
    tree = notes.tmp / "trees" / "two"
    write(tree, {"n.txt": text})
    git(tree, "commit", "-q", "-m", "the fix")
    git(tree, "push", "-q")
    fixed = git(tree, "rev-parse", "HEAD")
    notes.pulls["two"]["headRefOid"] = fixed
    result = (
        f"Rebase: patch changed in n.txt, before {was}, head {rebased}\n"
        f"Finding: fixed, it is wrong\nFixed: {fixed}\n"
    )
    notes.brief("two", was, result, verdict="findings")


def test_a_line_the_rebase_dropped_and_a_fix_put_back_is_kept(notes):
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    was = notes.pulls["two"]["headRefOid"]
    rebased = notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\nours\n"}
    )
    held = f"wait 7 {url(7)}: the rebase dropped 1 of main's lines in n.txt {unsaid(notes)}"
    assert notes.run("--check") == [held]
    fix(notes, was, rebased, "one\ntwo\nthree\ntheirs\nours\n")
    (said,) = notes.run()
    assert said.startswith("merged 7 two ") and ", every line kept, revert: " in said
    assert notes.at_main("n.txt") == "one\ntwo\nthree\ntheirs\nours"


def test_a_fix_pushed_after_the_rebase_is_not_a_line_the_rebase_dropped(notes):
    """The rebase kept a line, and a `Fixed:` commit took it out afterwards. That is the fix's
    change, in the pull request's own diff, and not the rebase's."""
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    was = notes.pulls["two"]["headRefOid"]
    rebased = notes.rebase(
        "two",
        {"n.txt": "one\ntwo\nthree\ntheirs\n"},
        {"n.txt": "one\ntwo\nthree\ntheirs\nours\n"},
    )
    fix(notes, was, rebased, "one\ntwo\nthree\ntheirs\nours, as the review asked\n")
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


class Checked:
    """A repo that asks for a fresh check, and a pull request with a file that main also
    changed since the check. Main changed other lines of the file, so the pull request and
    main merge cleanly. The command is a script that counts its runs."""

    def __init__(self, kitchen, script, path="b.txt", ours=LINES + "ours\n"):
        self.kitchen = kitchen
        self.runs = kitchen.tmp / "runs"
        self.script = kitchen.tmp / "check.sh"
        self.wrote(script)
        self.command = f"sh {self.script}"
        (kitchen.home.state / "fresh-check").write_text(f"{self.command}\n")
        self.head = kitchen.crew("two", 7, {path: ours})
        self.main = kitchen.on_main({path: "theirs\n" + LINES})

    def wrote(self, script):
        self.script.write_text(f'pwd >> "{self.runs}"\n{script}\n')

    def ran(self):
        return self.runs.read_text().splitlines() if self.runs.exists() else []

    def over(self, head=None, main=None):
        return f"on {(head or self.head)[:12]} over today's main {(main or self.main)[:12]}"

    def passed(self):
        return f"fresh: {self.command} passed on {self.head[:12]} over {self.main[:12]}"

    def known(self):
        return json.loads((self.kitchen.home.state / "fresh.json").read_text())


BOTH = "grep -qx theirs b.txt && grep -qx ours b.txt"


def test_a_stale_pull_request_whose_head_passes_over_todays_main_is_merged(kitchen):
    checked = Checked(kitchen, BOTH)
    state = kitchen.home.state
    assert kitchen.run("--check") == [f"wait 7 {url(7)}: {STALE.format('b.txt')}"]
    assert checked.ran() == [] and not (state / "fresh.json").exists()
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ") and f", {checked.passed()}, revert: " in said
    assert checked.ran() == [str(state / "fresh" / "7")]
    assert not (state / "fresh" / "7").exists()
    assert git(kitchen.home.main, "worktree", "list", "--porcelain").count("worktree ") == 1
    record = checked.known()["7"]
    assert record.pop("at").startswith(str(date.today().year))
    assert record == {
        "head": checked.head,
        "main": checked.main,
        "command": checked.command,
        "result": "passed",
    }
    assert kitchen.at_main("b.txt") == ("theirs\n" + LINES + "ours\n").strip()


def test_a_pass_is_remembered_for_that_head_over_that_main(kitchen):
    checked = Checked(kitchen, BOTH)
    (kitchen.home.state / "merge-off").write_text("")
    off = [f"wait 7 {url(7)}: auto-merge is off for this repo"]
    assert kitchen.run() == [f"wait 7 {url(7)}: {ready.FRESH_QUEUED}"]
    settled(kitchen)
    assert kitchen.run() == off
    assert kitchen.run() == off
    (kitchen.home.state / "merge-off").unlink()
    assert kitchen.run("--check") == [f"ready 7 {checked.head} two two, {checked.passed()}"]
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ") and f", {checked.passed()}, revert: " in said
    assert len(checked.ran()) == 1


def test_a_head_that_fails_over_todays_main_waits_and_is_not_checked_twice(kitchen):
    checked = Checked(kitchen, "echo it broke; exit 3")
    fails = [f"wait 7 {url(7)}: {checked.command} fails {checked.over()}"]
    assert kitchen.after_check() == fails
    assert kitchen.run() == fails
    assert kitchen.run("--check") == fails
    assert len(checked.ran()) == 1 and checked.known()["7"]["result"] == "failed"
    assert (kitchen.home.state / "fresh" / "7.log").read_text() == "it broke\n"
    assert kitchen.calls() == []
    checked.wrote(BOTH)
    again = kitchen.on_main({"a.txt": "theirs\n"})
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ") and f"over {again[:12]}, revert: " in said
    assert len(checked.ran()) == 2


def test_a_command_that_runs_over_its_time_is_stopped_and_queued_again_not_failed(
    kitchen, monkeypatch
):
    """The limit counts the wait for a test slot too, so a run that goes over the limit shows
    nothing about the tree. The pull request waits for a fresh check, which `jmerge` starts
    again."""
    checked = Checked(kitchen, "sleep 30")
    home = kitchen.home
    fresh = cli.Fresh(home.main, home.state, timeout=0.5)
    here = repo(kitchen, monkeypatch, fresh)
    one = ready.pull_request(kitchen.pulls["two"])
    assert here.waits(one, "main")[1:3] == ("wait", ready.FRESH_QUEUED)
    settled(kitchen)
    assert checked.known()["7"]["result"] == "timed out"
    assert markers(kitchen) == {} and not (home.state / "fresh" / "7").exists()
    here = repo(kitchen, monkeypatch, cli.Fresh(home.main, home.state, timeout=0.5))
    assert here.waits(one, "main")[1:] == ("wait", ready.FRESH_QUEUED, "", None)
    end = time.monotonic() + 60
    while len(checked.ran()) < 2:
        assert time.monotonic() < end, "no second check was started"
        time.sleep(0.05)
    settled(kitchen)
    here = repo(kitchen, monkeypatch, cli.Fresh(home.main, home.state, run=False))
    assert here.waits(one, "main")[1:] == ("wait", ready.FRESH_QUEUED, "", None)
    asleep = subprocess.run(["pgrep", "-f", "^sleep 30$"], capture_output=True, text=True)
    assert [
        pid
        for pid in asleep.stdout.split()
        if os.readlink(f"/proc/{pid}/cwd").startswith(str(home.state))
    ] == []


def test_a_head_that_does_not_merge_over_todays_main_waits_and_runs_nothing(kitchen):
    (kitchen.home.state / "fresh-check").write_text("true\n")
    kitchen.crew("two", 7, {"b.txt": "ours\n" + LINES})
    kitchen.on_main({"b.txt": "theirs\n" + LINES})
    assert kitchen.run() == [f"wait 7 {url(7)}: it conflicts with today's main"]
    assert not (kitchen.home.state / "fresh.json").exists()
    assert not (kitchen.home.state / "fresh").exists()


def test_one_fresh_check_is_run_in_a_run_and_the_others_are_queued(kitchen):
    checked = Checked(kitchen, "exit 1")
    kitchen.crew("three", 8, {"a.txt": LINES + "ours\n"})
    kitchen.on_main({"a.txt": "theirs\n" + LINES})
    checked.main = kitchen.tip()
    queued = [
        f"wait 7 {url(7)}: a fresh check is queued",
        f"wait 8 {url(8)}: a fresh check is queued",
    ]
    assert kitchen.run() == queued
    settled(kitchen)
    assert len(checked.ran()) == 1
    checked.wrote("true")
    before = known(kitchen)
    fails = f"wait 7 {url(7)}: {checked.command} fails {checked.over()}"
    assert kitchen.run() == [fails, f"wait 8 {url(8)}: a fresh check is queued"]
    settled(kitchen, before)
    first, second = kitchen.run()
    assert first == fails
    assert second.startswith("merged 8 three ")
    assert len(checked.ran()) == 2


def test_a_fresh_check_another_run_is_making_is_not_started_again(kitchen):
    checked = Checked(kitchen, BOTH)
    with (kitchen.home.state / "fresh.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert kitchen.run() == [f"wait 7 {url(7)}: a fresh check is queued"]
        assert checked.ran() == [] and not (kitchen.home.state / "fresh" / "7").exists()
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ")


def test_the_command_holds_the_lock_itself_for_as_long_as_any_of_it_runs(kitchen, monkeypatch):
    """A jmerge that is stopped leaves its command running. The command holds the lock too, so
    the next run starts no second command while the first one runs. Here a background
    process of the command keeps running after the check ends."""
    checked = Checked(kitchen, "sleep 3 > /dev/null 2>&1 &")
    home = kitchen.home
    here = repo(kitchen, monkeypatch, cli.Fresh(home.main, home.state))
    one = ready.pull_request(kitchen.pulls["two"])
    assert here.waits(one, "main")[1:3] == ("wait", ready.FRESH_QUEUED)
    recorded(kitchen, 7)
    *_, judged = here.waits(one, "main")
    assert judged.fresh == checked.passed()
    other = cli.Fresh(home.main, home.state)
    assert other.of(8, checked.head, checked.main, ("b.txt",)) == (ready.FRESH_QUEUED, "")


def test_a_fresh_check_pushes_nothing_and_leaves_the_crewmates_worktree_alone(kitchen):
    checked = Checked(kitchen, "echo scratch > scratch.txt; echo more >> b.txt; exit 1")
    tree = kitchen.tmp / "trees" / "two"
    real = shutil.which("git")
    (kitchen.home.stub / "git").write_text(
        f'#!/bin/sh\necho "$*" >> "$STUB/git-calls"\nexec {real} "$@"\n'
    )
    (kitchen.home.stub / "git").chmod(0o755)

    def seen():
        files = {
            str(path.relative_to(tree)): (path.stat().st_mtime_ns, path.read_bytes())
            for path in sorted(tree.rglob("*"))
            if path.is_file()
        }
        refs = git(kitchen.origin, "for-each-ref", "--format=%(refname) %(objectname)")
        local = git(kitchen.home.main, "for-each-ref", "--format=%(refname) %(objectname)")
        return (
            files,
            refs,
            local,
            git(tree, "status", "--porcelain"),
            git(tree, "rev-parse", "HEAD"),
        )

    before = seen()
    assert kitchen.after_check() == [f"wait 7 {url(7)}: {checked.command} fails {checked.over()}"]
    assert seen() == before
    ran = (kitchen.home.stub / "git-calls").read_text().splitlines()
    assert any(call.startswith("merge-tree --write-tree ") for call in ran)
    assert any(call.startswith("worktree add -q --detach ") for call in ran)
    assert [call for call in ran if "push" in call.split()] == []
    assert [call for call in ran if str(tree) in call] == []
    assert len(checked.ran()) == 1


def settled(kitchen, before=None, limit=60.0):
    """A run started a fresh check in the background. Wait until that check ends. The check ends
    when it records something newer than what `fresh.json` had `before`. It then releases
    `fresh.lock`, which it holds until it pushes its marker."""
    fresh = cli.Fresh(kitchen.home.main, kitchen.home.state)
    end = time.monotonic() + limit
    while fresh.known() == (before or {}):
        assert time.monotonic() < end, "the fresh check recorded nothing"
        time.sleep(0.05)
    with (kitchen.home.state / "fresh.lock").open("w") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError:
                assert time.monotonic() < end, "the fresh check did not end"
                time.sleep(0.05)


def known(kitchen):
    return cli.Fresh(kitchen.home.main, kitchen.home.state).known()


def recorded(kitchen, number, limit=60.0):
    """Wait until the fresh check records what it found. A run started that check in the
    background."""
    end = time.monotonic() + limit
    while str(number) not in cli.Fresh(kitchen.home.main, kitchen.home.state).known():
        assert time.monotonic() < end, "the fresh check recorded nothing"
        time.sleep(0.05)


def checked_of(kitchen, fresh, checked):
    """What `Fresh.of` says of the pull request once the fresh check that it started has ended."""
    before = known(kitchen)
    assert fresh.of(7, checked.head, checked.main, ("b.txt",)) == (ready.FRESH_QUEUED, "")
    settled(kitchen, before)
    return fresh.of(7, checked.head, checked.main, ("b.txt",))


def markers(kitchen):
    """The trees marked on the origin, each with the commit its ref points at."""
    listed = git(kitchen.origin, "for-each-ref", "--format=%(refname) %(objectname)", sweep.MARKERS)
    return dict(line.split() for line in listed.splitlines())


def test_a_pass_marks_its_tree_on_the_origin_before_it_is_said(kitchen):
    checked = Checked(kitchen, BOTH)
    home = kitchen.home
    assert markers(kitchen) == {}
    said = checked_of(kitchen, cli.Fresh(home.main, home.state), checked)
    ((ref, commit),) = markers(kitchen).items()
    assert said == ("", checked.passed())
    tree = git(kitchen.origin, "rev-parse", f"{commit}^{{tree}}")
    assert ref == f"refs/jstack/green-tree/{tree}"
    assert git(kitchen.origin, "log", "-1", "--format=%P %s", commit) == (
        f"{checked.main} {checked.head} jmerge: {checked.head} over {checked.main}"
    )
    assert "unmarked" not in checked.known()["7"]
    (merged,) = kitchen.run()
    assert merged.startswith("merged 7 two ") and f", {checked.passed()}, revert: " in merged
    assert git(kitchen.origin, "rev-parse", "refs/heads/main^{tree}") == tree
    assert markers(kitchen) == {ref: commit}


def test_a_fail_marks_no_tree(kitchen):
    checked = Checked(kitchen, "exit 3")
    home = kitchen.home
    why, note = checked_of(kitchen, cli.Fresh(home.main, home.state), checked)
    assert (why.startswith(f"{checked.command} fails "), note) == (True, "")
    assert checked.known()["7"]["result"] == "failed"
    assert markers(kitchen) == {}


def test_a_marker_the_origin_refuses_leaves_the_check_passed_and_the_note_says_why(kitchen):
    checked = Checked(kitchen, BOTH)
    home = kitchen.home
    hook = kitchen.origin / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\nwhile read -r was now ref; do\n"
        '    case $ref in refs/jstack/*) echo "no markers here" >&2; exit 1 ;; esac\ndone\n'
    )
    hook.chmod(0o755)
    unmarked = f"{checked.passed()}, its tree is not marked (pre-receive hook declined)"
    assert checked_of(kitchen, cli.Fresh(home.main, home.state), checked) == ("", unmarked)
    assert markers(kitchen) == {}
    record = checked.known()["7"]
    assert (record["result"], record["unmarked"]) == ("passed", "pre-receive hook declined")
    assert kitchen.run("--check") == [f"ready 7 {checked.head} two two, {unmarked}"]
    (merged,) = kitchen.run()
    assert merged.startswith("merged 7 two ") and f", {unmarked}, revert: " in merged
    assert len(checked.ran()) == 1


def test_a_sweep_deletes_a_marker_on_the_origin_that_is_more_than_seven_days_old(kitchen):
    """Another clone pushed the old marker, so its commit is not in the main checkout. The
    clone that sweeps need not be the clone that pushed the marker."""
    main, other = kitchen.home.main, kitchen.tmp / "other"
    git(kitchen.tmp, "clone", "-q", str(kitchen.origin), str(other))
    aged = {}
    for days, repo in ((8, other), (6, main)):
        at = f"{int(time.time()) - days * 86400} +0000"
        write(repo, {"a.txt": f"{days} days ago\n"})
        marked = git(repo, "write-tree")
        commit = git(repo, "commit-tree", marked, "-p", "HEAD", "-m", "a pass", at=at)
        git(repo, "push", "-q", "origin", f"{commit}:refs/jstack/green-tree/{marked}")
        git(repo, "reset", "-q", "--hard")
        aged[days] = (f"refs/jstack/green-tree/{marked}", commit, marked[:12])
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


def test_a_repo_with_no_fresh_check_file_runs_none(kitchen):
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    kitchen.on_main({"b.txt": "theirs\n" + LINES})
    assert kitchen.run() == [f"wait 7 {url(7)}: {STALE.format('b.txt')}"]
    assert not (kitchen.home.state / "fresh.json").exists()
    assert not (kitchen.home.state / "fresh").exists()


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


def test_a_slow_fresh_check_is_queued_at_once_and_a_later_run_reads_its_pass(kitchen):
    """The 03:26 outage: the suite ran longer than the 300 s that jbus gives jmerge, so the
    check never recorded its result. The run now returns while the check goes on, and the check
    records when it ends."""
    checked = Checked(kitchen, f"sleep 3; {BOTH}")
    began = time.monotonic()
    assert kitchen.run() == [f"wait 7 {url(7)}: a fresh check is queued"]
    assert time.monotonic() - began < 2.5
    assert not (kitchen.home.state / "fresh.json").exists()
    assert kitchen.run() == [f"wait 7 {url(7)}: a fresh check is queued"]
    settled(kitchen)
    assert checked.known()["7"]["result"] == "passed"
    (said,) = kitchen.run()
    assert said.startswith("merged 7 two ") and f", {checked.passed()}, revert: " in said
    assert len(checked.ran()) == 1


def test_the_check_is_a_transient_user_unit_with_the_runs_environment(kitchen, monkeypatch):
    checked = Checked(kitchen, BOTH)
    calls = kitchen.tmp / "systemd-run-calls"
    monkeypatch.setenv("SYSTEMD_RUN_CALLS", str(calls))
    monkeypatch.setenv("INVOCATION_ID", "the pass's own")
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ") and f", {checked.passed()}, revert: " in said
    (call,) = calls.read_text().splitlines()
    unit = f"jmerge-fresh-{kitchen.home.state.name.replace(' ', '-')}-7"
    assert call.startswith(f"--user --quiet --collect --unit={unit} --setenv=")
    assert " --setenv=PATH " in call and " --setenv=STUB " in call
    assert "INVOCATION_ID" not in call


def test_where_systemd_cannot_start_a_unit_the_check_is_a_process_of_its_own(
    kitchen, no_user_units, monkeypatch
):
    """This test covers a check that runs outside a systemd unit. Inside a unit, such as a
    pass, a plain process would end when the unit ends."""
    (no_user_units / "systemd-run").write_text("#!/bin/sh\necho no user manager >&2\nexit 1\n")
    checked = Checked(kitchen, f"sleep 1; {BOTH}")
    monkeypatch.setenv("INVOCATION_ID", "the pass's own")
    could_not = f"wait 7 {url(7)}: a fresh check could not be run (no user manager)"
    assert kitchen.run() == [could_not]
    assert kitchen.run() == [could_not] and checked.ran() == []
    monkeypatch.delenv("INVOCATION_ID")
    (said,) = kitchen.after_check()
    assert said.startswith("merged 7 two ") and f", {checked.passed()}, revert: " in said
    assert len(checked.ran()) == 1
