"""A pull request that changes a guarded path is merged by `jmerge` itself, under a stricter
gate than any other: a check with a start time, a review finished at the head, a rebase
where main changed one of its paths since the check started, a `jmerge` whose own rules
are main's, and the review's one safety fact proven at the head (`test_gate_skills`). One
that changes a secret path is still the user's, and jbus sends it as a gate.

The command is run against `test_home_merge`'s fake `gh` and real origin, from a copy of
the package that is a git checkout of its own, as the installed one is. The copy's
`guarded.txt` is the list this file writes, `LISTED`: the shipped list is empty since
2026-10-12, and the gate is tested over a list that has lines, as one put back would be."""

import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import jsettings
import test_home_merge as merge
from jbus import merge as jbus_merge
from jmerge import cli, rangediff, ready

SOURCE = Path(__file__).parent.parent / "src" / "jmerge"
LISTED = "acceptance/\n.github/workflows/\nsrc/jmerge/\nsrc/jbus/\nskills/\n"
GUARDED = ready.patterns_of(LISTED)
CI = ready.patterns_of((SOURCE / "ci-paths.txt").read_text())
STARTED = {**merge.PASSED, "startedAt": "2000-01-01T12:00:00Z"}
SKILL = "skills/home/SKILL.md"

ET = jsettings.Settings(zone=ZoneInfo("America/New_York"), label="ET")


def checkout(tmp_path, listed=None):
    """A checkout that holds jmerge's own package, and is what its origin's main has. Its
    `guarded.txt` is the shipped one, or the lines given."""
    origin = tmp_path / "rules.git"
    top = tmp_path / "rules"
    shutil.copytree(SOURCE, top / "src" / "jmerge", ignore=shutil.ignore_patterns("__pycache__"))
    if listed is not None:
        (top / "src" / "jmerge" / "guarded.txt").write_text(listed)
    (top / ".gitignore").write_text("__pycache__/\n")
    merge.git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    merge.git(top, "init", "-q", "-b", "main")
    merge.git(top, "add", ".")
    merge.git(top, "commit", "-q", "-m", "the rules")
    merge.git(top, "remote", "add", "origin", str(origin))
    merge.git(top, "push", "-q", "-u", "origin", "main")
    return top


@pytest.fixture
def rules(tmp_path):
    """The package with a list that guards five paths."""
    return checkout(tmp_path, LISTED)


@pytest.fixture
def shipped(tmp_path):
    """The package as it is shipped, with its own list."""
    return checkout(tmp_path)


PROOF = "Reviewers: 2, A 0, B 0   Proof: uv run pytest tests/test_a.py, exit 0, 3 passed\n"


def proven(verdict, head=merge.REVIEWED):
    """A review that proved the one safety fact at the head it saw."""
    return merge.review(verdict, head) + PROOF


@pytest.fixture
def merged(tmp_path):
    made = merge.Merged(merge.Home(tmp_path), tmp_path)
    (made.home.tasks / "alpha.md").write_text(merge.brief(proven("clean", made.head)))
    return made


def jmerge(merged, rules, *flags):
    said = merged.home.sh(
        f'PYTHONPATH="{rules / "src"}" "{sys.executable}" -m jmerge --home {merge.ME} '
        + " ".join(flags)
    )
    assert (merged.home.code, merged.home.stderr) == (0, "")
    return said


def merges(merged):
    return [call for call in merge.calls(merged.home) if call.startswith("pr merge ")]


def on_main(merged, path):
    """One more commit on the origin's main, after every check started."""
    (merged.home.main / path).parent.mkdir(parents=True, exist_ok=True)
    (merged.home.main / path).write_text("moved\n")
    merge.git(merged.home.main, "add", path)
    merge.git(merged.home.main, "commit", "-q", "-m", f"change {path}")
    merge.git(merged.home.main, "push", "-q")


@pytest.mark.parametrize("path", ["deploy/id.key", "secrets/x.json", "src/jmerge/guarded.txt"])
def test_a_secret_path_and_the_lists_themselves_are_held_for_the_user(merged, rules, path):
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=[SKILL, path])
    assert jmerge(merged, rules) == [f"hold 7 {merge.URL}: needs user, touches {path}"]
    assert merged.untouched()


def test_the_shipped_list_guards_no_path_so_a_ready_one_merges_with_no_proof(merged, shipped):
    assert ready.patterns_of((SOURCE / "guarded.txt").read_text()) == ()
    (merged.home.tasks / "alpha.md").write_text(merge.brief(merge.review("clean", merged.head)))
    files = ["a.txt", SKILL, "src/jbus/merge.py", "src/jmerge/ready.py"]
    merged.home.open_pull_request(merged.head, files=files)
    assert jmerge(merged, shipped, "--check") == [f"ready 7 {merged.head} alpha alpha"]
    (said,) = jmerge(merged, shipped)
    commit, _ = merged.on_main()
    assert said == merge.merged_line(commit)
    assert "guarded" not in said


@pytest.mark.parametrize("path", ["src/jmerge/guarded.txt", "src/jmerge/protected.txt"])
def test_the_shipped_lists_still_hold_a_change_to_either_list_for_the_user(merged, shipped, path):
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=[SKILL, path])
    assert jmerge(merged, shipped) == [f"hold 7 {merge.URL}: needs user, touches {path}"]
    assert merged.untouched()


def test_jbus_sends_a_hold_line_and_the_other_lines_as_they_were(tmp_path):
    hold = f"hold 9 {merge.URL}: needs user, touches secrets/x.json"
    wait = f"wait 8 {merge.URL}: guarded (touches {SKILL}), its check has no start time"
    done = f'merged 7 alpha abc1234 "the task", guarded: {SKILL}, revert: gh pr revert x'
    sent = []
    run = SimpleNamespace(
        home=tmp_path,
        config=SimpleNamespace(state_dir=tmp_path),
        user=ET,
        project=SimpleNamespace(name="demo"),
        say=sent.append,
        run=lambda *command, timeout=None: SimpleNamespace(
            stdout=f"{done}\n{wait}\n{hold}\n", returncode=0
        ),
        find=lambda slug, kind, line, text="", *, key="": sent.append((slug, kind, line, key)),
    )
    assert jbus_merge.merge(run) == [done, wait, hold]
    assert sent == [
        ("alpha", "jmerge", done, f"7 {done}"),
        ("#8", "jmerge", wait, f"8 {wait}"),
        ("#9", "jmerge", hold, f"9 {hold}"),
    ]


@pytest.mark.parametrize("path", [SKILL, "src/jbus/merge.py"])
def test_a_guarded_path_with_every_gate_met_is_merged_at_the_head_it_was_judged_at(
    merged, rules, path
):
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=["a.txt", path])
    assert jmerge(merged, rules, "--check") == [
        f"ready 7 {merged.head} alpha alpha, guarded: {path}"
    ]
    assert merged.untouched()
    (said,) = jmerge(merged, rules)
    commit, pulled = merged.on_main()
    assert said == merge.merged_line(commit, f"guarded: {path}")
    assert pulled == commit
    assert merges(merged) == [
        f"pr merge 7 --squash --match-head-commit {merged.head} --repo {merged.origin}"
    ]


def guarded(why, path=SKILL):
    return [f"wait 7 {merge.URL}: guarded (touches {path}), {why}"]


def test_a_review_with_a_finding_that_has_no_ending_is_not_finished(merged, rules):
    declined = "Fixed: none needed, the finding is about code the task does not own\n"
    brief = merge.brief(proven("findings", merged.head), declined)
    (merged.home.tasks / "alpha.md").write_text(brief)
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=[SKILL])
    assert jmerge(merged, rules) == guarded("1 of its 1 findings have no Finding line")
    assert merged.untouched()
    ended = "Finding: not fixed, it is wrong, because the task does not own that code\n"
    (merged.home.tasks / "alpha.md").write_text(brief + ended)
    (said,) = jmerge(merged, rules)
    assert said.startswith("merged 7 alpha ")


def test_a_review_of_another_head_does_not_cover_a_guarded_path(merged, rules):
    """An older `Rebase:` line names the head and claims nothing the command can check."""
    brief = merge.brief(merge.review("clean"), f"Rebase: range-diff empty, head {merged.head}\n")
    (merged.home.tasks / "alpha.md").write_text(brief)
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=["a.txt"])
    assert jmerge(merged, rules, "--check") == [f"ready 7 {merged.head} alpha alpha"]
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=[SKILL])
    assert jmerge(merged, rules) == guarded("its head is not the one its review saw")
    assert merged.untouched()


def test_a_check_that_has_not_passed_at_the_head_waits_as_it_does_for_any_path(merged, rules):
    failed = {**merge.FAILED, "startedAt": STARTED["startedAt"]}
    merged.home.open_pull_request(merged.head, checks=(failed,), files=[SKILL])
    assert jmerge(merged, rules) == [f"wait 7 {merge.URL}: check has not passed"]
    assert merged.untouched()


@pytest.mark.parametrize("at", [None, "", "0001-01-01T00:00:00Z", "yesterday"])
def test_a_check_with_no_start_time_cannot_be_compared_with_main(merged, rules, at):
    check = merge.PASSED if at is None else {**merge.PASSED, "startedAt": at}
    merged.home.open_pull_request(merged.head, checks=(check,), files=[SKILL])
    assert jmerge(merged, rules) == guarded("its check has no start time")
    assert merged.untouched()


STALE = "main changed {} after its check started at 07:00 ET; it needs a rebase"


@pytest.mark.parametrize("path", [SKILL, "Makefile"])
def test_a_main_that_changed_one_of_its_files_or_a_ci_path_after_its_check_waits(
    merged, rules, path
):
    on_main(merged, path)
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=["a.txt", SKILL])
    assert jmerge(merged, rules) == guarded(STALE.format(path))
    assert merges(merged) == []
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=["a.txt"])
    (said,) = jmerge(merged, rules)
    if path == SKILL:
        assert said.startswith("merged 7 alpha ")
    else:
        assert said == f"wait 7 {merge.URL}: {STALE.format(path)[: -len('a rebase')]}a fresh check"


def test_a_main_that_moved_only_on_other_files_leaves_the_check_standing(merged, rules):
    on_main(merged, "docs/other.md")
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=["a.txt", SKILL])
    (said,) = jmerge(merged, rules)
    assert said.startswith("merged 7 alpha ") and f", guarded: {SKILL}, revert: " in said


def test_a_check_that_started_after_main_changed_the_file_is_fresh(merged, rules):
    on_main(merged, SKILL)
    later = {**merge.PASSED, "startedAt": f"{date.today().year + 1}-01-01T00:00:00Z"}
    merged.home.open_pull_request(merged.head, checks=(later,), files=[SKILL])
    (said,) = jmerge(merged, rules)
    assert said.startswith("merged 7 alpha ")


def test_merge_off_still_merges_nothing(merged, rules):
    (merged.home.state / "merge-off").write_text("")
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=[SKILL])
    assert jmerge(merged, rules) == [merge.OFF]
    assert merged.untouched()


def pull_request(*files, head=merge.PUSHED, checks=(STARTED,)):
    listed = {
        "number": 7,
        "url": merge.URL,
        "headRefName": "alpha",
        "headRefOid": head,
        "baseRefName": "main",
        "mergeable": "MERGEABLE",
        "title": merge.TITLE,
        "statusCheckRollup": list(checks),
        "files": [merge.file(path) for path in files],
        "changedFiles": len(files),
    }
    return ready.pull_request(listed)


def test_the_start_of_a_check_is_its_earliest_run_named_check():
    runs = (
        {**merge.PASSED, "startedAt": "2026-10-11T22:05:00Z"},
        {**merge.PASSED, "startedAt": "2026-10-11T22:01:00Z"},
        {**merge.OTHER_PASSED, "startedAt": "2026-10-11T21:00:00Z"},
    )
    assert pull_request("a.txt", checks=runs).started == datetime(2026, 10, 11, 22, 1, tzinfo=UTC)
    assert pull_request("a.txt", checks=(merge.OTHER_PASSED,)).started is None


UNCHANGED = ready.Rebase("unchanged", (), merge.REVIEWED, merge.PUSHED)
CHANGED = ready.Rebase("changed", ("a.txt",), merge.REVIEWED, merge.PUSHED)
ENDED = "Finding: fixed, it is wrong\n"
NOT_SEEN = "its head is not the one its review saw"

REVIEWS = {
    "a clean review of the head": (merge.review("clean", merge.PUSHED), None, ""),
    "findings, each ended, fixed at the head": (
        merge.review("findings") + f"Fixed: {merge.PUSHED}\n{ENDED}",
        None,
        "",
    ),
    "findings fixed at the head with no Finding line": (
        merge.review("findings") + f"Fixed: {merge.PUSHED}\n",
        None,
        "1 of its 1 findings have no Finding line",
    ),
    "a rebase the command found to leave the patch as it was": (
        merge.review("clean"),
        UNCHANGED,
        "",
    ),
    "an unchanged rebase that ended on another head": (
        merge.review("clean"),
        ready.Rebase("unchanged", (), merge.REVIEWED, "c" * 40),
        NOT_SEEN,
    ),
    "a rebase that changed the patch, whose content the review carried over to": (
        merge.review("clean"),
        CHANGED,
        "",
    ),
    "a rebase that changed the patch, and a review of the rebased head": (
        merge.review("clean") + merge.review("clean", merge.PUSHED),
        CHANGED,
        "",
    ),
}
CARRIED = rangediff.Verdict(
    True, "", "", f"{'1' * 40}..{merge.REVIEWED}", f"{'2' * 40}..{merge.PUSHED}"
)


@pytest.mark.parametrize("case", REVIEWS)
def test_the_review_of_a_guarded_path_is_finished_and_of_the_head(case):
    result, rebase, short = REVIEWS[case]
    text = merge.brief(result)
    compared = ready.to_range_diff(rebase, text, merge.PUSHED) is not None
    carried = compared and rebase.did == "changed"
    note = ready.rebase_note(CARRIED if carried else None)
    assert carried == case.endswith("carried over to")
    assert ready.short_of_guarded(pull_request(SKILL), text, rebase, note) == short


def test_stale_paths_are_the_ones_main_changed_that_the_pull_request_changes_or_ci_reads():
    ours = ("a.txt", SKILL)
    assert ready.stale_paths(ours, (), ("docs/x.md", SKILL), CI) == (SKILL,)
    assert ready.stale_paths(ours, (), ("old/a.txt", "a.txt"), CI) == ("a.txt",)
    assert ready.stale_paths(ours, ("docs/first.md",), ("docs/first.md",), CI) == ("docs/first.md",)
    assert ready.stale_paths(ours, (), ("Makefile", "uv.lock", "docs/Makefile"), CI) == (
        "Makefile",
        "uv.lock",
    )
    assert ready.stale_paths(ours, (), (".github/workflows/check.yml",), CI) == (
        ".github/workflows/check.yml",
    )
    assert ready.stale_paths(ours, (), ("docs/x.md", "src/jgauge/cli.py"), CI) == ()
    assert ready.stale_paths(ours, ("docs/first.md",), (), CI) == ()


def test_the_reason_names_at_most_five_paths_and_the_time_in_et():
    since = datetime(2026, 10, 12, 2, 18, tzinfo=UTC)
    assert ready.short_on_main((), since, user=ET) == ""
    assert ready.short_on_main(("a.py", "b.py"), since, user=ET) == (
        "main changed a.py b.py after its check started at 22:18 ET; it needs a fresh check"
    )
    seven = tuple(f"{n}.py" for n in range(7))
    assert ready.short_on_main(seven, since, "trunk", "a rebase", user=ET) == (
        "trunk changed 0.py 1.py 2.py 3.py 4.py and 2 more after its check started at "
        "22:18 ET; it needs a rebase"
    )


def test_rules_that_are_what_main_has_let_a_guarded_pull_request_through(rules):
    assert cli.rules_are_mains(rules / "src" / "jmerge") == ""


def edit(rules, text="skills/\n"):
    (rules / "src" / "jmerge" / "guarded.txt").write_text(text)


def push(rules, branch="main"):
    merge.git(rules, "commit", "-q", "-a", "-m", "other rules")
    merge.git(rules, "push", "-q", "origin", f"HEAD:{branch}")


def test_rules_that_differ_from_mains_make_a_guarded_pull_request_wait(rules, tmp_path):
    package = rules / "src" / "jmerge"
    edit(rules)
    assert cli.rules_are_mains(package) == "jmerge's own rules have a change that is not committed"
    merge.git(rules, "commit", "-q", "-a", "-m", "weaker")
    assert cli.rules_are_mains(package) == (
        "jmerge's own rules are not main's: their checkout is not behind origin/main"
    )
    merge.git(rules, "switch", "-q", "-c", "weaker")
    assert cli.rules_are_mains(package) == (
        "jmerge's own rules are not main's: their checkout is on weaker"
    )
    merge.git(rules, "switch", "-q", "--detach")
    assert cli.rules_are_mains(package) == (
        "jmerge's own rules are not main's: their checkout is on no branch"
    )
    merge.git(rules, "switch", "-q", "--detach", "origin/main")
    assert cli.rules_are_mains(package) == ""
    (package / "more.py").write_text("")
    assert cli.rules_are_mains(package) == "jmerge's own rules have a change that is not committed"
    shutil.copytree(SOURCE, tmp_path / "copy" / "jmerge")
    assert cli.rules_are_mains(tmp_path / "copy" / "jmerge") == (
        "jmerge's own rules are not in a git checkout"
    )
    (rules / ".gitignore").write_text("installed/\n")
    shutil.copytree(SOURCE, rules / "installed" / "jmerge")
    assert cli.rules_are_mains(rules / "installed" / "jmerge") == (
        "jmerge's own rules are not tracked in a git checkout"
    )


def test_rules_that_are_only_behind_are_pulled_and_judge_on_the_next_run(rules, tmp_path):
    package = rules / "src" / "jmerge"
    other = tmp_path / "other"
    merge.git(tmp_path, "clone", "-q", str(tmp_path / "rules.git"), str(other))
    edit(other)
    push(other)
    behind = "jmerge's own rules are behind main's, and a run that merges pulls them"
    assert cli.rules_are_mains(package, pull=False) == behind
    assert (package / "guarded.txt").read_text() != "skills/\n"
    assert cli.rules_are_mains(package) == "jmerge pulled main's rules; judged on the next run"
    assert (package / "guarded.txt").read_text() == "skills/\n"
    assert cli.rules_are_mains(package) == ""


def test_jmerge_merges_no_guarded_path_on_rules_that_are_not_mains(merged, rules):
    edit(rules, LISTED + "docs/\n")
    why = "jmerge's own rules have a change that is not committed"
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=[SKILL])
    assert jmerge(merged, rules) == guarded(why)
    assert merged.untouched()
    merged.home.open_pull_request(merged.head, files=[SKILL, "id.key"])
    assert jmerge(merged, rules) == [f"hold 7 {merge.URL}: needs user, touches id.key"]
    merged.home.open_pull_request(merged.head, files=["a.txt"])
    (said,) = jmerge(merged, rules)
    assert said.startswith("merged 7 alpha ")


def repo(merged, monkeypatch, asked):
    """The command's own view of the repo, in this process, with the fake `gh`."""
    home = merged.home
    monkeypatch.setenv("PATH", f"{home.stub}:{merge.os.environ['PATH']}")
    monkeypatch.setenv("STUB", str(home.stub))
    monkeypatch.setenv("ORIGIN", str(home.origin))
    monkeypatch.setenv("LOG", str(home.state / "merge.log"))

    def rules():
        asked.append("rules")
        return ""

    return cli.Repo(home.main, home.state, merge.ME, False, None, (), GUARDED, CI, rules, user=ET)


def test_a_main_that_moved_while_it_was_judged_has_it_judged_again_before_the_merge(
    merged, monkeypatch
):
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=[SKILL])
    one = pull_request(SKILL, head=merged.head)
    here = repo(merged, monkeypatch, [])
    *_, judged = here.waits(one, "main")
    assert judged == ready.Judged(SKILL, merged.start)
    on_main(merged, SKILL)
    assert [here.merge(one, "alpha", "", judged)] == guarded(STALE.format(SKILL))
    assert not (merged.home.stub / "calls").exists()


def test_a_main_that_moved_on_another_path_while_it_was_judged_does_not_keep_it(
    merged, monkeypatch
):
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=[SKILL])
    one = pull_request(SKILL, head=merged.head)
    here = repo(merged, monkeypatch, [])
    *_, judged = here.waits(one, "main")
    on_main(merged, "docs/other.md")
    assert here.merge(one, "alpha", "", judged).startswith("merged 7 alpha ")


def test_after_a_merge_that_changes_jmerge_every_later_guarded_one_waits(merged, monkeypatch):
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=["src/jmerge/ready.py"])
    asked = []
    here = repo(merged, monkeypatch, asked)
    one = pull_request("src/jmerge/ready.py", head=merged.head)
    slug, verb, why, note, judged = here.waits(one, "main")
    assert (slug, verb, why, note) == ("alpha", "", "", "")
    assert judged == ready.Judged("src/jmerge/ready.py", merged.start, True)
    assert here.merge(one, slug, note, judged).startswith("merged 7 alpha ")
    *_, why, _, judged = here.waits(pull_request(SKILL, head=merged.head), "main")
    assert (why, judged) == (f"guarded (touches {SKILL}), jmerge's rules changed in this run", None)
    assert asked == ["rules"]


def test_a_repo_that_does_not_hold_the_rules_merges_any_other_path_without_asking(
    merged, monkeypatch
):
    asked = []
    here = repo(merged, monkeypatch, asked)
    one = pull_request("a.txt", head=merged.head)
    slug, _, why, note, judged = here.waits(one, "main")
    assert here.merge(one, slug, note, judged).startswith("merged 7 alpha ")
    assert asked == []
    assert here.waits(pull_request("b.txt", head=merged.head), "main")[1:3] == ("", "")


def test_the_rules_are_asked_about_before_a_merge_can_pull_their_checkout(merged, monkeypatch):
    """In jmerge's own repo the main checkout holds the rules, and the pull after any merge
    brings rules that were behind up to date: asked only then, old code would pass for new."""
    here = repo(merged, monkeypatch, [])
    here.own = True
    pulled = merged.home.stub / "merged"
    here.rules = lambda: "" if pulled.exists() else "jmerge pulled main's rules"
    merged.home.open_pull_request(merged.head, checks=(STARTED,), files=["a.txt"])
    one = pull_request("a.txt", head=merged.head)
    slug, _, why, note, judged = here.waits(one, "main")
    assert (why, judged) == ("", ready.Judged(tip=merged.start))
    assert here.merge(one, slug, note, judged).startswith("merged 7 alpha ")
    *_, why, _, judged = here.waits(pull_request(SKILL, head=merged.head), "main")
    assert (why, judged) == (f"guarded (touches {SKILL}), jmerge pulled main's rules", None)
