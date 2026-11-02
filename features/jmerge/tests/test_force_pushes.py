"""`features/jmerge/scripts/force_pushes.py` gives each force-push of a merged pull request the
cause jbus told its crew last before it."""

import importlib.util
import subprocess
from collections import Counter
from datetime import datetime, timedelta

import pytest

from testing.paths import REPO

SCRIPT = REPO / "features" / "jmerge" / "scripts" / "force_pushes.py"
SPEC = importlib.util.spec_from_file_location("force_pushes", SCRIPT)
pushes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pushes)

SINCE = datetime.fromisoformat("2026-10-26T14:00:00+00:00")
UNTIL = datetime.fromisoformat("2026-11-02T14:00:00+00:00")


def pull(number, branch, *pushed, merged="2026-10-28T12:00:00Z"):
    return {"number": number, "branch": branch, "merged": merged, "pushes": list(pushed)}


def event(kind, slug, at, line="", text=""):
    return {"event": kind, "slug": slug, "at": at, "line": f"{kind} {slug}: {line}", "text": text}


def test_each_push_takes_the_cause_jbus_told_last_before_it():
    pulls = [
        pull(
            7,
            "seven",
            "2026-10-27T10:30:00Z",
            "2026-10-27T12:30:00Z",
            "2026-10-27T14:30:00Z",
            "2026-10-27T16:30:00Z",
        ),
        pull(8, "eight", "2026-10-27T10:30:00Z"),
    ]
    events = [
        event("failed", "seven", "2026-10-27T10:00:00Z", "told the crew (#7, abc)"),
        event("restack", "seven", "2026-10-27T12:00:00Z", "told the crew one merged (#6, abc)"),
        event(
            "rebase",
            "seven",
            "2026-10-27T14:00:00Z",
            "told the crew (#7, abc)",
            "jbus: main moved under your pull request #7 (it conflicts with its base).",
        ),
        event("review", "seven", "2026-10-27T15:00:00Z", "clean"),
    ]
    assert pushes.causes(pulls, events, SINCE, UNTIL) == {
        "crew fix": 1,
        "stack move": 1,
        "conflict": 1,
        "other": 2,
    }


def test_a_restack_names_the_pull_request_that_merged_and_counts_for_the_stacked_one():
    pulls = [pull(6, "six"), pull(7, "seven", "2026-10-27T12:30:00Z")]
    events = [event("restack", "seven", "2026-10-27T12:00:00Z", "told the crew six merged (#6)")]
    assert pushes.causes(pulls, events, SINCE, UNTIL)["stack move"] == 1


def test_a_push_with_no_event_in_two_hours_takes_the_last_since_the_push_before_it():
    pulls = [pull(7, "seven", "2026-10-27T08:00:00Z", "2026-10-27T20:00:00Z")]
    events = [event("review", "seven", "2026-10-27T09:00:00Z", "findings")]
    assert pushes.causes(pulls, events, SINCE, UNTIL) == {
        "crew fix": 1,
        "stack move": 0,
        "conflict": 0,
        "other": 1,
    }


def test_only_the_pull_requests_merged_in_the_period_are_counted():
    pulls = [
        pull(7, "seven", "2026-10-20T10:00:00Z", merged="2026-10-20T12:00:00Z"),
        pull(8, "eight", "2026-10-27T10:00:00Z", merged=None),
    ]
    assert sum(pushes.causes(pulls, [], SINCE, UNTIL).values()) == 0


def git(repo, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    ran = subprocess.run(["git", *identity, *args], cwd=repo, check=True, capture_output=True)
    return ran.stdout.decode().strip()


def commit(repo, files, message):
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, {"code.py": "one\n", "cite.md": "see a.py:10\n", "a.png": "one\n"}, "start")
    return tmp_path


def branch_over(repo, ours, theirs):
    """A branch and a main that each edit from the start: the two heads."""
    start = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "row", start)
    head = commit(repo, ours, "row")
    git(repo, "checkout", "-q", "main")
    main = commit(repo, theirs, "other (#9)")
    return head, main


def reason(repo, head, main, after=None, branch="row", branches=None):
    said = pushes.reason_of(repo, head, after or head, main, main, branch, branches or {})
    return said[0]


def test_a_conflict_only_in_line_numbers_is_told_from_one_in_text(repo):
    head, main = branch_over(repo, {"cite.md": "see a.py:11\n"}, {"cite.md": "see a.py:12\n"})
    assert reason(repo, head, main) == pushes.NUMBERS


def test_the_hardest_file_that_conflicted_is_the_reason(repo):
    head, main = branch_over(
        repo, {"a.png": "two\n", "code.py": "two\n"}, {"a.png": "three\n", "code.py": "three\n"}
    )
    assert reason(repo, head, main) == pushes.ROWS
    head, main = (
        git(repo, "rev-parse", "row"),
        commit(repo, {"code.py": "two\n"}, "other (#10)"),
    )
    assert reason(repo, head, main) == pushes.GENERATED


def test_a_push_with_no_conflict_is_a_rewrite_or_a_rebase(repo):
    head, main = branch_over(repo, {"mine.txt": "mine\n"}, {"theirs.txt": "theirs\n"})
    git(repo, "checkout", "-q", "-b", "amended", head)
    git(repo, "commit", "-q", "--amend", "-m", "amended")
    amended = git(repo, "rev-parse", "HEAD")
    assert reason(repo, head, main, amended) == pushes.REWRITTEN
    git(repo, "rebase", "-q", main)
    assert reason(repo, head, main, git(repo, "rev-parse", "HEAD")) == pushes.REBASED


def test_code_is_said_to_conflict_against_the_row_whose_merge_touched_it(repo):
    head, main = branch_over(repo, {"code.py": "two\n"}, {"code.py": "three\n"})
    assert reason(repo, head, main, branch="cleanup-other", branches={9: "other"}) == pushes.PARENT
    assert reason(repo, head, main, branch="fl-one", branches={9: "fl-two"}) == pushes.WAVE
    assert reason(repo, head, main, branch="fl-one", branches={9: "else"}) == pushes.ROWS


def test_the_table_adds_up_to_each_cause(repo):
    counted = {"conflict": Counter({pushes.ROWS: 2, pushes.LIST: 1}), "crew fix": Counter()}
    lines = pushes.table(
        counted,
        {pushes.ROWS: Counter({"code.py": 2})}
        | {reason: Counter() for reason in pushes.REASONS if reason != pushes.ROWS},
    )
    assert lines[-1] == "| all | 3 | 0 | |"
    assert f"| {pushes.ROWS} | 2 | 0 | `code.py` 2 |" in lines


def test_a_commit_git_cannot_read_is_not_known_and_never_a_push_with_no_conflict(repo):
    head, main = branch_over(repo, {"mine.txt": "mine\n"}, {"theirs.txt": "theirs\n"})
    gone = "0" * 40
    assert reason(repo, gone, main, head) == pushes.UNKNOWN
    assert reason(repo, head, main, gone) == pushes.UNKNOWN
    assert pushes.reason_of(repo, head, head, gone, main, "row", {}) == (pushes.UNKNOWN, [])


def stamp(moment):
    return moment.isoformat().replace("+00:00", "Z")


def test_explained_joins_each_told_push_to_its_commits_and_main_then(repo, monkeypatch):
    """The path the table is made by: a push of a merged pull request, the event jbus told before
    it, the commits GitHub gives for it and the main of that moment, from `origin/main`."""
    head, main = branch_over(repo, {"code.py": "two\n"}, {"code.py": "three\n"})
    git(repo, "update-ref", "refs/remotes/origin/main", main)
    landed = datetime.fromisoformat(git(repo, "log", "-1", "--format=%cI", main))
    told_at, pushed_at = landed + timedelta(minutes=1), landed + timedelta(minutes=5)
    pulls = [
        pull(7, "row", stamp(pushed_at), merged=stamp(pushed_at + timedelta(hours=1))),
        pull(8, "lost", stamp(pushed_at), merged=stamp(pushed_at + timedelta(hours=1))),
    ]
    rebase = "jbus: main moved under your pull request #7 (it conflicts with its base)."
    events = [
        event("rebase", "row", stamp(told_at), "told (#7)", rebase),
        event("failed", "lost", stamp(told_at), "told (#8)"),
    ]
    asked = []

    def from_github(_repo, numbers):
        asked.append(numbers)
        return {(7, pushes.when(stamp(pushed_at))): (head, head)}

    monkeypatch.setattr(pushes, "pushed_commits", from_github)
    since, until = landed - timedelta(days=1), landed + timedelta(days=1)
    counted, files = pushes.explained(repo, pulls, events, since, until)
    assert asked == [[7, 8]]
    assert counted["conflict"] == Counter({pushes.ROWS: 1})
    assert counted["crew fix"] == Counter({pushes.UNKNOWN: 1})
    assert files[pushes.ROWS] == Counter({"code.py": 1})
