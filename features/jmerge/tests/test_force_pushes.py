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


def test_a_commit_git_cannot_read_is_not_known_and_never_a_push_with_no_conflict(repo):
    head, main = branch_over(repo, {"mine.txt": "mine\n"}, {"theirs.txt": "theirs\n"})
    gone = "0" * 40
    assert reason(repo, gone, main, head) == pushes.UNKNOWN
    assert reason(repo, head, main, gone) == pushes.UNKNOWN
    assert pushes.reason_of(repo, head, head, gone, main, "row", {}) == (pushes.UNKNOWN, [], {})


def test_a_merge_or_a_merge_base_git_cannot_work_out_is_not_known(repo):
    """conflict-rebase-cut F6: a commit that shares no history with the head is readable, but git
    can neither merge the head over it, as main at the told event, nor find its merge base with
    main, as the head after the push."""
    head, main = branch_over(repo, {"mine.txt": "mine\n"}, {"theirs.txt": "theirs\n"})
    git(repo, "checkout", "-q", "--orphan", "alone")
    alone = commit(repo, {"alone.txt": "alone\n"}, "alone")
    assert pushes.reason_of(repo, head, head, main, alone, "row", {}) == (pushes.UNKNOWN, [], {})
    assert pushes.reason_of(repo, head, alone, main, main, "row", {}) == (pushes.UNKNOWN, [], {})


def stamp(moment):
    return moment.isoformat().replace("+00:00", "Z")


def test_explained_joins_each_told_push_to_its_commits_and_main_then(repo, monkeypatch):
    """The path the table is made by: a push of a merged pull request, the event jbus told before
    it, the commits GitHub gives for it and the main of that moment, from `origin/main`."""
    head, main = branch_over(repo, {"code.py": "two\n"}, {"code.py": "three\n"})
    git(repo, "update-ref", "refs/remotes/origin/main", main)
    git(repo, "checkout", "-q", "-b", "train", head)
    into_train = commit(repo, {"train.txt": "train\n"}, "a merge into the train")
    landed = datetime.fromisoformat(git(repo, "log", "-1", "--format=%cI", main))
    told_at, pushed_at = landed + timedelta(minutes=1), landed + timedelta(minutes=5)
    pulls = [
        pull(7, "row", stamp(pushed_at), merged=stamp(pushed_at + timedelta(hours=1))),
        pull(8, "lost", stamp(pushed_at), merged=stamp(pushed_at + timedelta(hours=1))),
        pull(10, "on-a-train", stamp(pushed_at), merged=stamp(pushed_at + timedelta(hours=1)))
        | {"merge_commit": into_train},
    ]
    rebase = "jbus: main moved under your pull request #7 (it conflicts with its base)."
    events = [
        event("rebase", "row", stamp(told_at), "told (#7)", rebase),
        event("failed", "lost", stamp(told_at), "told (#8)"),
        event("rebase", "on-a-train", stamp(told_at), "told (#10)", rebase),
    ]
    asked = []

    def from_github(_repo, numbers):
        asked.append(numbers)
        pushed = pushes.when(stamp(pushed_at))
        return {(7, pushed): (head, head), (10, pushed): (head, head)}

    monkeypatch.setattr(pushes, "pushed_commits", from_github)
    since, until = landed - timedelta(days=1), landed + timedelta(days=1)
    counted, files, hunks_of, elsewhere = pushes.explained(repo, pulls, events, since, until)
    assert asked == [[7, 8, 10]]
    assert counted["conflict"] == Counter({pushes.ROWS: 2})
    assert counted["crew fix"] == Counter({pushes.UNKNOWN: 1})
    assert files[pushes.ROWS] == Counter({"code.py": 2})
    assert hunks_of == {"code.py": [(pushes.when(stamp(pushed_at)), 7, ["edit"])]}
    assert elsewhere == 1, "#10 merged into another row's branch: main was never its base"
    assert "1 push of pull requests merged into another row's branch" in "\n".join(
        pushes.by_file(hunks_of, pulls, until, elsewhere)
    )


def hunks(repo, ours, theirs, start=None):
    """The kinds of the hunks of each file that conflicts where a row and main each change the
    start: a branch and a main that each commit over it."""
    if start:
        commit(repo, start, "start (#8)")
    head, main = branch_over(repo, ours, theirs)
    return pushes.reason_of(repo, head, head, main, main, "row", {})[2]


def test_two_rows_that_each_append_to_one_list_conflict_by_an_insert(repo):
    start = {"kinds.py": "KINDS = [\n    'one',\n]\n"}
    ours = {"kinds.py": "KINDS = [\n    'one',\n    'two',\n]\n"}
    theirs = {"kinds.py": "KINDS = [\n    'one',\n    'three',\n]\n"}
    assert hunks(repo, ours, theirs, start) == {"kinds.py": ["insert"]}


def test_two_rows_that_change_only_a_number_conflict_by_a_renumber(repo):
    start = {"limit.py": "LIMIT = 10  # the pushes a day\n"}
    ours = {"limit.py": "LIMIT = 11  # the pushes a day\n"}
    theirs = {"limit.py": "LIMIT = 12  # the pushes a day\n"}
    assert hunks(repo, ours, theirs, start) == {"limit.py": ["renumber"]}


def test_two_rows_that_each_add_a_file_to_one_package_do_not_conflict(repo):
    start = {"pkg/__init__.py": "", "pkg/one.py": "ONE = 1\n"}
    commit(repo, start, "start (#8)")
    head, main = branch_over(repo, {"pkg/two.py": "TWO = 2\n"}, {"pkg/three.py": "THREE = 3\n"})
    assert pushes.reason_of(repo, head, head, main, main, "row", {}) == (pushes.REWRITTEN, [], {})


def test_a_file_with_no_markers_conflicted_as_a_whole(repo):
    start = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "row", start)
    git(repo, "rm", "-q", "code.py")
    git(repo, "commit", "-qm", "row")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    main = commit(repo, {"code.py": "three\n"}, "other (#9)")
    assert pushes.reason_of(repo, head, head, main, main, "row", {})[2] == {
        "code.py": ["whole-file"]
    }


def test_a_binary_file_that_conflicted_has_no_markers_and_conflicted_as_a_whole(repo):
    start = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "row", start)
    (repo / "a.png").write_bytes(b"\x89PNG\r\n\x00two")
    git(repo, "commit", "-qam", "row")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    (repo / "a.png").write_bytes(b"\x89PNG\r\n\x00three")
    git(repo, "commit", "-qam", "other (#9)")
    main = git(repo, "rev-parse", "HEAD")
    assert pushes.reason_of(repo, head, head, main, main, "row", {})[1:] == (
        ["a.png"],
        {"a.png": ["whole-file"]},
    )


AT = datetime.fromisoformat("2026-11-02T12:00:00+00:00")


def test_a_push_from_before_mains_rewrite_replays_against_the_main_it_saw(repo):
    """Main was rewritten on 2026-10-23: today's main has other commits for the merges before it.
    A row's main then is the merge commit of the last pull request merged into main before it,
    and a merge into another row's branch is not main."""
    start = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "train")
    commit(repo, {"train.txt": "a row\n"}, "a row on the train")
    train = commit(repo, {"train.txt": "train\n"}, "into a train (#5)")
    git(repo, "checkout", "-q", "main")
    seen = commit(repo, {"cite.md": "see a.py:20\n"}, "seen (#6)")
    git(repo, "checkout", "-q", "-b", "today", start)
    rewritten = commit(repo, {"code.py": "rewritten\n"}, "seen (#6)")
    later = commit(repo, {"code.py": "later\n"}, "a push to main with no pull request")
    git(repo, "update-ref", "refs/remotes/origin/main", later)
    stamps = {c: git(repo, "log", "-1", "--format=%cI", c) for c in (train, seen, later)}
    pulls = [
        {"number": 5, "branch": "five", "merged": stamps[train], "merge_commit": train},
        {"number": 6, "branch": "six", "merged": stamps[seen], "merge_commit": seen},
    ]
    moves = [commit for _, commit in pushes.main_moves(repo, pulls)]
    assert seen in moves and later in moves
    assert train not in moves and rewritten not in moves


ABSENT = "0123456789abcdef0123456789abcdef01234567"


def test_a_merge_commit_git_lacks_leaves_the_readable_merges_on_main(repo):
    """GitHub can name a merge commit the clone never fetched: `main_moves` reads past it, and
    a merge git can read, which is main only by its first parent, still lands on main."""
    start = git(repo, "rev-parse", "HEAD")
    seen = commit(repo, {"cite.md": "see a.py:20\n"}, "seen (#6)")
    git(repo, "checkout", "-q", "-b", "today", start)
    later = commit(repo, {"code.py": "later\n"}, "a push to main with no pull request")
    git(repo, "update-ref", "refs/remotes/origin/main", later)
    at = git(repo, "log", "-1", "--format=%cI", seen)
    pulls = [
        {"number": 6, "branch": "six", "merged": at, "merge_commit": seen},
        {"number": 11, "branch": "gone", "merged": at, "merge_commit": ABSENT},
    ]
    moves = [commit for _, commit in pushes.main_moves(repo, pulls)]
    assert seen in moves and later in moves and ABSENT not in moves


def test_a_push_whose_merge_commit_git_lacks_keeps_its_hunks(repo, monkeypatch):
    """A merge commit git cannot read is not known to be off main, so its push keeps its hunks
    and is not one of a pull request merged into another row's branch."""
    head, main = branch_over(repo, {"code.py": "two\n"}, {"code.py": "three\n"})
    git(repo, "update-ref", "refs/remotes/origin/main", main)
    landed = datetime.fromisoformat(git(repo, "log", "-1", "--format=%cI", main))
    told_at, pushed_at = landed + timedelta(minutes=1), landed + timedelta(minutes=5)
    merged = stamp(pushed_at + timedelta(hours=1))
    pulls = [pull(11, "row", stamp(pushed_at), merged=merged) | {"merge_commit": ABSENT}]
    rebase = "jbus: main moved under your pull request #11 (it conflicts with its base)."
    events = [event("rebase", "row", stamp(told_at), "told (#11)", rebase)]
    pushed = pushes.when(stamp(pushed_at))
    monkeypatch.setattr(pushes, "pushed_commits", lambda _r, _n: {(11, pushed): (head, head)})
    since, until = landed - timedelta(days=1), landed + timedelta(days=1)
    counted, _, hunks_of, elsewhere = pushes.explained(repo, pulls, events, since, until)
    assert counted["conflict"] == Counter({pushes.ROWS: 1})
    assert hunks_of == {"code.py": [(pushed, 11, ["edit"])]}
    assert elsewhere == 0


def test_files_of_gives_each_conflicted_file_its_pull_requests_and_its_hunks_by_kind():
    """`--json` prints `files_of`, which `jbus.collisions` reads for the weekly report."""
    hunks_of = {
        "list.md": [(AT, 6, ["insert", "insert"]), (AT, 5, ["insert", "renumber"])],
        "code.py": [(AT, 5, ["edit"])],
    }
    assert pushes.files_of(hunks_of) == [
        {"path": "code.py", "pulls": [5], "pushes": 1, "hunks": {"edit": 1}},
        {"path": "list.md", "pulls": [5, 6], "pushes": 2, "hunks": {"insert": 3, "renumber": 1}},
    ]
