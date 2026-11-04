"""`jmerge` run as a command on a pull request whose review proved its safety fact: a secret
path is still the user's, and jbus sends it as a gate; a check is judged by its start and by
whether main changed since. The other test files run `jmerge` with this file's helpers.

The tests run the command against the fake `gh` and real origin of `test_home_merge`, from a
copy of the package, `rules`."""

import shutil
import sys
from datetime import UTC, date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import jsettings
import test_home_merge as merge
from jbus import merge as jbus_merge
from jmerge import cli, ready
from testing.paths import REPO

SOURCE = REPO / "features" / "jmerge" / "src" / "jmerge"
STARTED = {**merge.PASSED, "startedAt": "2000-01-01T12:00:00Z"}
SKILL = "skills/home/SKILL.md"

ET = jsettings.Settings(zone=ZoneInfo("America/New_York"), label="ET")


def checkout(tmp_path):
    """A copy of jmerge's own package, as `rules / "src" / "jmerge"`."""
    top = tmp_path / "rules"
    shutil.copytree(SOURCE, top / "src" / "jmerge", ignore=shutil.ignore_patterns("__pycache__"))
    return top


PROOF = "Reviewers: 2, A 0, B 0   Proof: uv run pytest tests/test_a.py, exit 0, 3 passed\n"


def proven(verdict, head=merge.REVIEWED):
    """A review that proved the one safety fact at the head it saw."""
    return merge.review(verdict, head) + PROOF


def jmerge(proven_merged, rules, *flags):
    said = proven_merged.home.sh(
        f'PYTHONPATH="{rules / "src"}" "{sys.executable}" -m jmerge ' + " ".join(flags)
    )
    assert (proven_merged.home.code, proven_merged.home.stderr) == (0, "")
    return said


def merges(proven_merged):
    return [call for call in merge.calls(proven_merged.home) if call.startswith("pr merge ")]


def on_main(proven_merged, path):
    """One more commit on the origin's main, after every check started."""
    (proven_merged.home.main / path).parent.mkdir(parents=True, exist_ok=True)
    (proven_merged.home.main / path).write_text("moved\n")
    merge.git(proven_merged.home.main, "add", path)
    merge.git(proven_merged.home.main, "commit", "-q", "-m", f"change {path}")
    merge.git(proven_merged.home.main, "push", "-q")


@pytest.mark.parametrize(
    "path", ["deploy/id.key", "secrets/x.json", "features/jmerge/src/jmerge/protected.txt"]
)
def test_a_secret_path_and_the_list_itself_are_held_for_the_user(proven_merged, rules, path):
    proven_merged.home.open_pull_request(proven_merged.head, checks=(STARTED,), files=[SKILL, path])
    assert jmerge(proven_merged, rules) == [f"hold 7 {merge.URL}: needs user, touches {path}"]
    assert proven_merged.untouched()


def test_jbus_sends_a_hold_line_and_the_other_lines_as_they_were(tmp_path):
    hold = f"hold 9 {merge.URL}: needs user, touches secrets/x.json"
    wait = f"wait 8 {merge.URL}: check has not passed"
    done = 'merged 7 alpha abc1234 "the task", revert: gh pr revert x'
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


def test_a_review_with_a_finding_that_has_no_ending_is_not_finished(proven_merged, rules):
    declined = "Fixed: none needed, the finding is about code the task does not own\n"
    brief = merge.brief(proven("findings", proven_merged.head), declined)
    (proven_merged.home.tasks / "alpha.md").write_text(brief)
    proven_merged.home.open_pull_request(proven_merged.head, checks=(STARTED,), files=[SKILL])
    unended = ready.UNENDED.format(left=1, found=1)
    assert jmerge(proven_merged, rules) == [f"wait 7 {merge.URL}: {unended}"]
    assert proven_merged.untouched()
    ended = "Finding: not fixed, it is wrong, because the task does not own that code\n"
    (proven_merged.home.tasks / "alpha.md").write_text(brief + ended)
    (said,) = jmerge(proven_merged, rules)
    assert said.startswith("merged 7 alpha ")


def test_a_check_that_has_not_passed_at_the_head_waits(proven_merged, rules):
    failed = {**merge.FAILED, "startedAt": STARTED["startedAt"]}
    proven_merged.home.open_pull_request(proven_merged.head, checks=(failed,), files=[SKILL])
    assert jmerge(proven_merged, rules) == [f"wait 7 {merge.URL}: check has failed"]
    assert proven_merged.untouched()


def test_a_main_that_changed_its_file_into_a_conflict_after_its_check_waits(proven_merged, rules):
    on_main(proven_merged, "a.txt")
    proven_merged.home.open_pull_request(
        proven_merged.head, checks=(STARTED,), files=["a.txt", SKILL]
    )
    assert jmerge(proven_merged, rules) == [f"wait 7 {merge.URL}: {ready.FRESH_CONFLICT}"]
    assert merges(proven_merged) == []


def moved(proven_merged):
    """The line of a pull request whose check started before main's tip, in a run that asks
    GitHub nothing."""
    tip = merge.git(proven_merged.home.main, "rev-parse", "HEAD")
    return f"wait 7 {merge.URL}: " + ready.BASE_MOVED_DUE.format(base="main", tip=tip[:12])


@pytest.mark.parametrize("path", ["docs/other.md", "Makefile"])
def test_a_main_that_moved_only_on_other_files_waits_for_a_check_over_it(
    proven_merged, rules, path
):
    on_main(proven_merged, path)
    proven_merged.home.open_pull_request(
        proven_merged.head, checks=(STARTED,), files=["a.txt", SKILL]
    )
    assert jmerge(proven_merged, rules, "--check") == [moved(proven_merged)]
    assert merges(proven_merged) == []


def test_strict_a_check_that_started_after_main_moved_waits_while_its_head_lacks_main_s_tip(
    proven_merged, rules
):
    """Main's ruleset is strict: a check that started after main's last commit is no check over
    today's main while the head lacks that commit, since GitHub merges no such head."""
    on_main(proven_merged, SKILL)
    later = {**merge.PASSED, "startedAt": f"{date.today().year + 1}-01-01T00:00:00Z"}
    proven_merged.home.open_pull_request(proven_merged.head, checks=(later,), files=[SKILL])
    assert jmerge(proven_merged, rules, "--check") == [moved(proven_merged)]
    assert merges(proven_merged) == []


def test_merge_off_still_merges_nothing(proven_merged, rules):
    (proven_merged.home.state / "merge-off").write_text("")
    proven_merged.home.open_pull_request(proven_merged.head, checks=(STARTED,), files=[SKILL])
    assert jmerge(proven_merged, rules) == [merge.OFF]
    assert proven_merged.untouched()


def pull_request(
    *files, head=merge.PUSHED, checks=(STARTED,), rollup=merge.rollup, required=ready.REQUIRED
):
    listed = {
        "number": 7,
        "url": merge.URL,
        "headRefName": "alpha",
        "headRefOid": head,
        "baseRefName": "main",
        "mergeable": "MERGEABLE",
        "title": merge.TITLE,
        "statusCheckRollup": rollup(checks),
        "files": [merge.file(path) for path in files],
        "changedFiles": len(files),
    }
    return ready.pull_request(listed, required)


def test_the_start_of_a_check_is_its_latest_run_named_check():
    runs = (
        {**merge.PASSED, "startedAt": "2026-10-11T22:05:00Z"},
        {**merge.PASSED, "startedAt": "2026-10-11T22:01:00Z"},
        {**merge.OTHER_PASSED, "startedAt": "2026-10-11T23:00:00Z"},
    )
    assert pull_request("a.txt", checks=runs).started == datetime(2026, 10, 11, 22, 5, tzinfo=UTC)
    assert pull_request("a.txt", checks=(merge.OTHER_PASSED,)).started is None


def test_the_start_of_a_check_that_waits_on_its_parts_is_the_first_part_s_start():
    """The check workflow runs its tests as four parts, and the job `check` starts once they
    have ended: the check is as old as the earliest job of the same workflow run."""

    def job(name, at, run=7):
        url = f"https://github.com/o/r/actions/runs/{run}/job/1"
        return {**merge.run("SUCCESS", name), "startedAt": at, "detailsUrl": url}

    runs = (
        job("check 1 of 4", "2026-10-24T16:14:34Z"),
        job("check 2 of 4", "2026-10-24T16:14:33Z"),
        job("check", "2026-10-24T16:28:50Z"),
        job("borders", "2026-10-24T16:10:00Z", run=8),
    )
    assert pull_request("a.txt", checks=runs).started == datetime(
        2026, 10, 24, 16, 14, 33, tzinfo=UTC
    )


BORDERS_PASSED = merge.run("SUCCESS", "borders")


@pytest.mark.parametrize(
    ("checks", "short"),
    [
        ((merge.PASSED, BORDERS_PASSED), ""),
        ((merge.PASSED,), "borders has no run at {head}"),
        ((merge.PASSED, merge.run("FAILURE", "borders")), "borders has failed"),
        ((BORDERS_PASSED,), "check has no run at {head}"),
        ((merge.FAILED, merge.run("FAILURE", "borders")), "check has failed"),
    ],
)
def test_it_waits_on_each_required_check_until_it_has_passed(checks, short):
    required = ready.required_of("check\nborders\n")
    one = pull_request("a.txt", checks=checks, rollup=list, required=required)
    assert ready.short_on_github(one) == short.format(head=one.head[:12])


def mac(conclusion, name="macos"):
    return {**merge.run(conclusion, name), "workflowName": "macos"}


@pytest.mark.parametrize(
    ("macos", "short"),
    [
        ((mac("SKIPPED"), mac("SUCCESS", "macos-select")), ""),
        ((mac("SUCCESS"), mac("SUCCESS", "macos-select")), ""),
        ((mac("SKIPPED"),), "macos has not passed"),
        ((mac("SKIPPED"), mac("FAILURE", "macos-select")), "macos has not passed"),
        ((merge.run("SKIPPED", "macos"), mac("SUCCESS", "macos-select")), "macos has not passed"),
        ((mac("FAILURE"), mac("SUCCESS", "macos-select")), "macos has failed"),
    ],
    ids=[
        "skipped by its selection",
        "ran and passed",
        "skipped alone",
        "skipped after its selection failed",
        "skipped with no workflow named",
        "ran and failed",
    ],
)
def test_a_required_check_its_own_workflow_skipped_after_a_job_of_it_passed_counts_as_passed(
    macos, short
):
    """macos.yml skips its `macos` job by an `if:` where `macos-select` finds no Mac test the
    change reaches, and GitHub's required checks take the skip as a pass. jmerge takes it so
    only where the rest of that workflow passed: a skip on its own, or after a failed job, is
    no pass."""
    required = ready.required_of("check\nborders\nmacos\n")
    checks = (merge.PASSED, BORDERS_PASSED, *macos)
    one = pull_request("a.txt", checks=checks, rollup=list, required=required)
    assert ready.short_on_github(one) == short


def repo(proven_merged, monkeypatch):
    """The command's own view of the repo, in this process, with the fake `gh`."""
    home = proven_merged.home
    monkeypatch.setenv("PATH", f"{home.stub}:{merge.os.environ['PATH']}")
    monkeypatch.setenv("STUB", str(home.stub))
    monkeypatch.setenv("ORIGIN", str(home.origin))
    monkeypatch.setenv("LOG", str(home.state / "merge.log"))
    return cli.Repo(home.main, home.state, merge.ME, False, user=ET)


def test_a_main_that_moved_while_it_was_judged_has_it_judged_again_before_the_merge(
    proven_merged, monkeypatch
):
    proven_merged.home.open_pull_request(proven_merged.head, checks=(STARTED,), files=[SKILL])
    one = pull_request("a.txt", SKILL, head=proven_merged.head)
    here = repo(proven_merged, monkeypatch)
    *_, judged = here.waits(one, "main")
    assert judged == ready.Judged(proven_merged.start)
    on_main(proven_merged, "a.txt")
    said = here.merge(one, "alpha", "", judged)
    assert said == f"wait 7 {merge.URL}: {ready.FRESH_CONFLICT}"
    assert not (proven_merged.home.stub / "calls").exists()


def test_a_main_that_moved_on_another_path_while_it_was_judged_waits_for_a_check_over_it(
    proven_merged, monkeypatch
):
    proven_merged.home.open_pull_request(proven_merged.head, checks=(STARTED,), files=[SKILL])
    one = pull_request(SKILL, head=proven_merged.head)
    here = repo(proven_merged, monkeypatch)
    *_, judged = here.waits(one, "main")
    on_main(proven_merged, "docs/other.md")
    assert here.merge(one, "alpha", "", judged) == moved(proven_merged)
    assert not (proven_merged.home.stub / "calls").exists()
