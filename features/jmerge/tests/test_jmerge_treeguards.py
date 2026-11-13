"""`jmerge.treeguards` on a real origin and checkout: how the fast guards on a pull request's
tree merged over today's base pass, fail, wait and are kept, and how a failed guard is named.
`test_jmerge_cli_merged_tree.py` drives the same through the `jmerge` command."""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from jgauge import slot
from jmerge import green, ready, treeguards
from test_jmerge_fresh import git
from testing.paths import REPO


@pytest.fixture(autouse=True)
def locks(tmp_path, monkeypatch):
    """The test slots a run outside one takes, a machine of one full slot of its own."""
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("TEST_SLOTS", "1")
    return tmp_path / "locks"


def test_merged_tree_guard_named_from_the_output():
    pytest_said = "....\nFAILED features/x/tests/test_y.py::test_z - assert 0\n1 failed\n"
    make_said = "Found 1 error.\nmake[1]: *** [Makefile:53: lint] Error 1\nmake: *** [x] Error 2\n"
    assert treeguards.guard(pytest_said + make_said) == "features/x/tests/test_y.py::test_z"
    assert treeguards.guard(make_said) == "lint"
    assert treeguards.guard("one\nthe last line\n\n") == "the last line"
    assert treeguards.guard("") == treeguards.UNNAMED


def ending(end):
    """Guards that end in 30 s by touching `end` from a process `sh` started, so a stop that kills
    `sh` and not the processes it started still lets them reach that end."""
    return f"(sleep 30; touch {end}) & wait"


def stopped_before_their_end(ran, end):
    """The guards were stopped at their limit and did not run to their end (`ending`). A count of
    seconds would not tell: a runner that stalls `jmerge`'s process for 11 s holds back the stop,
    and with it `Ran.seconds`, while the guards' `sleep 30` runs on (main's run 42910529419,
    `Ran(code=None, seconds=12, ...)`). A stop that stops nothing waits for that end."""
    assert ran.code is None, ran
    assert not end.exists(), f"the guards ran to their end, not stopped at their limit: {ran}"


def test_merged_tree_guards_that_run_past_their_time_are_stopped_with_their_children(tmp_path):
    """The child is judged alive or not once the guards return, and not by a mark it leaves
    later: a runner stalled past the child's own end would leave that mark before any stop."""
    child = tmp_path / "child"
    end = tmp_path / "end"
    command = f"sh -c 'echo $$ > {child}; exec sleep 30' & {ending(end)}"
    ran = treeguards.run_guards(command, tmp_path, {}, timeout=1)
    stopped_before_their_end(ran, end)
    if child.exists():
        pid = child.read_text().strip()
        state = subprocess.run(["ps", "-o", "stat=", "-p", pid], capture_output=True, text=True)
        assert state.stdout.strip()[:1] in ("", "Z"), "the guards' child outlived the stop"


def test_guards_stopped_at_their_time_end_quietly_where_a_stopped_group_answers_eperm(
    tmp_path, monkeypatch
):
    """Darwin answers a kill of a group that holds only zombies with EPERM, where Linux gives
    ESRCH: once the stop at the time limit has killed the group and `sh` is reaped, a second kill
    of it is refused, and the run still ends with the guards stopped (nightly run 42059155018)."""
    kill = os.killpg
    killed = []

    def darwin(group, sig):
        if killed:
            raise PermissionError(1, "Operation not permitted")
        killed.append(group)
        kill(group, sig)

    monkeypatch.setattr(treeguards.os, "killpg", darwin)
    end = tmp_path / "end"
    ran = treeguards.run_guards(ending(end), tmp_path, {}, timeout=1)
    stopped_before_their_end(ran, end)


SCOUT = "features/verify-jstack/tests/test_verify_jstack.py::" + (
    "test_a_scout_goes_from_its_request_to_a_launched_thread_with_no_branch"
)


def jbus_environment():
    """The environment jbus's merge unit gives `jmerge`, and with it the guards: systemd's few
    variables and the unit's PATH, with this run's uv on it, as a machine with jbus has its
    own in ~/.local/bin."""
    unit = (REPO / "features" / "jbus" / "units" / "jbus-merge.service").read_text()
    path = re.search(r"^Environment=PATH=(.*)$", unit, re.MULTILINE)[1]
    path = path.replace("%h", os.environ["HOME"])
    uv = os.path.dirname(shutil.which("uv"))
    names = ("HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "JGAUGE_LOCKS_DIR", "TEST_SLOTS")
    return {name: os.environ[name] for name in names if name in os.environ} | {
        "PATH": path if uv in path.split(":") else f"{uv}:{path}"
    }


def test_merged_tree_guards_drive_the_sandbox_on_the_path_jbus_gives_them(monkeypatch):
    """The guards run where jbus runs `jmerge`, on its unit's short PATH, and still find what a
    desk's shell finds: on Arch the drive's `shasum` is in /usr/bin/core_perl, off that PATH,
    and a guard that missed it held every pull request with this test."""
    monkeypatch.setattr(os, "environ", jbus_environment())
    command = f"uv run pytest -q -p no:cacheprovider {SCOUT}"
    ran = treeguards.run_guards(command, REPO, {"BASE": "HEAD"}, treeguards.LIMIT_SECONDS)
    assert ran.code == 0, ran.said
    assert treeguards.guard(ran.said).startswith("1 passed")


class Tree:
    """A main checkout whose origin's main moved past a pull request's head: `tip` is main's,
    and `head` the pull request's, which does not hold it."""

    def __init__(self, tmp_path, ours="b\n", theirs="c\n", path="b.txt"):
        self.origin = tmp_path / "origin.git"
        self.main = tmp_path / "main"
        self.state = tmp_path / "state"
        self.state.mkdir()
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp_path, "clone", "-q", str(self.origin), str(self.main))
        self.commit({"a.txt": "a\n"})
        git(self.main, "push", "-q", "origin", "HEAD:main")
        base = git(self.main, "rev-parse", "HEAD")
        self.head = self.commit({path: ours})
        git(self.main, "checkout", "-q", base)
        self.tip = self.commit({"c.txt" if path == "b.txt" else path: theirs})
        git(self.main, "push", "-q", "origin", "HEAD:main")
        self.one = SimpleNamespace(number=7, head=self.head, base="main")

    def commit(self, files):
        for path, text in files.items():
            (self.main / path).write_text(text)
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "x")
        return git(self.main, "rev-parse", "HEAD")

    def guards(self, command, ask=None):
        (self.state / treeguards.NAME).write_text(command + "\n")
        return treeguards.Guards(self.main, self.state, True, ask or unchecked)


def unchecked(path):
    """GitHub with no check that left an artifact."""
    return {"artifacts": []}


def values(tree):
    return {"base": "main", "tip": tree.tip[:12]}


def test_merged_tree_guards_that_passed_are_not_run_again(tmp_path):
    tree = Tree(tmp_path)
    guards = tree.guards('test -e b.txt && test -e c.txt && test "$BASE" = ' + tree.tip)
    said, note = guards.of(tree.one, tree.tip)
    assert said == "" and note.startswith(treeguards.PASSED.format(**values(tree), seconds="")[:-3])
    guards.command = "false"
    assert guards.of(tree.one, tree.tip) == ("", note)
    assert not (tree.state / treeguards.TREE).exists()


def test_merged_tree_guards_see_the_merge_base_of_the_head_and_the_tip(tmp_path):
    """The guards get `MERGE_BASE`, the commit the pull request's check ran over, beside `BASE`,
    so `make check-fast PART=guards` also runs the test files main changed since then, which that
    check never saw (#1584 over #1588, spell 41)."""
    tree = Tree(tmp_path)
    merge_base = git(tree.main, "merge-base", tree.tip, tree.head)
    guards = tree.guards(f'test "$BASE" = {tree.tip} && test "$MERGE_BASE" = {merge_base}')

    said, note = guards.of(tree.one, tree.tip)

    assert merge_base not in (tree.tip, tree.head)
    assert said == "" and note.startswith(treeguards.PASSED.format(**values(tree), seconds="")[:-3])


def test_merged_tree_of_a_head_that_conflicts_with_the_tip_waits_for_a_rebase(tmp_path):
    tree = Tree(tmp_path, ours="ours\n", theirs="theirs\n", path="a.txt")
    assert tree.guards("true").of(tree.one, tree.tip) == (ready.FRESH_CONFLICT, "")


def test_merged_tree_that_cannot_be_built_says_why(tmp_path):
    tree = Tree(tmp_path)
    said, _ = tree.guards("true").of(tree.one, "f" * 40)
    assert said.startswith(ready.MERGED_TREE_UNBUILT.format(base="main", tip="f" * 12, why="")[:-2])
    (tree.state / treeguards.TREE).write_text("in the way\n")
    said, _ = tree.guards("true").of(tree.one, tree.tip)
    assert said.startswith(ready.MERGED_TREE_UNBUILT.format(**values(tree), why="")[:-2])
    assert said.endswith("already exists)")


def test_merged_tree_guards_past_their_limit_are_kept_until_the_head_or_the_tip_moves(
    tmp_path, monkeypatch
):
    """Guards stopped at their limit are kept for the head over the tip, as a pass or a failure
    is: the next run does not start them again on the same tree, so one slow tree does not take
    every run's time (#1103 over 21bdee0d25ca, six runs stopped on 2026-11-05), and another pull
    request of that run gets its guards. A new head or a new tip runs them again."""
    monkeypatch.setattr(treeguards, "LIMIT_SECONDS", 1)
    tree = Tree(tmp_path)
    base = git(tree.main, "rev-parse", f"{tree.tip}^")
    git(tree.main, "checkout", "-q", base)
    other = SimpleNamespace(number=8, head=tree.commit({"e.txt": "e\n"}), base="main")
    unended = ready.MERGED_TREE_UNENDED.format(**values(tree), minutes=0)
    assert tree.guards("sleep 20").of(tree.one, tree.tip) == (unended, "")
    kept = json.loads((tree.state / treeguards.KEPT).read_text())["7"]
    assert (kept["head"], kept["tip"], kept["said"]) == (tree.head, tree.tip, unended)

    marker = tmp_path / "ran"
    again = tree.guards(f"touch {marker}")
    assert again.kept(tree.one, tree.tip) == unended
    assert again.of(tree.one, tree.tip) == (unended, "")
    assert not marker.exists(), "the stopped tree's guards ran again on the same head and tip"
    said, note = again.of(other, tree.tip)
    assert said == "" and note and marker.exists()

    marker.unlink()
    git(tree.main, "checkout", "-q", tree.head)
    tree.one.head = tree.commit({"b.txt": "b2\n"})
    said, note = tree.guards(f"touch {marker}").of(tree.one, tree.tip)
    assert said == "" and note and marker.exists()

    marker.unlink()
    tree.one.head = tree.head
    git(tree.main, "checkout", "-q", tree.tip)
    tip = tree.commit({"f.txt": "f\n"})
    git(tree.main, "push", "-q", "origin", "HEAD:main")
    (tree.state / treeguards.KEPT).write_text(json.dumps({"7": kept}))
    said, note = tree.guards(f"touch {marker}").of(tree.one, tip)
    assert said == "" and note and marker.exists()


def later(monkeypatch, minutes):
    """Move `treeguards`' clock `minutes` past the real one."""

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(minutes=minutes)

    monkeypatch.setattr(treeguards, "datetime", Later)


def runs(tree, then):
    """Guards that count each run of theirs in a file beside the tree, then run `then`."""
    count = tree.state.parent / "runs"
    return f"echo >> {count} && {then}", lambda: len(count.read_text().splitlines())


def test_merged_tree_guards_that_failed_run_once_more_after_30_minutes(tmp_path, monkeypatch):
    """A failure of the guards on a head over a tip stands for 30 minutes, then they run once more
    on the same tree, and a second failure stands until the head or the tip moves: #1876 waited
    45 minutes with main still on a guard of the live desk that passed 0.16 s later, and a real
    failure fails again."""
    tree = Tree(tmp_path)
    command, ran = runs(tree, "false")
    held, _ = tree.guards(command).of(tree.one, tree.tip)
    assert ready.MERGED_TREE_FAILS.fields(held), held
    later(monkeypatch, 29)
    assert tree.guards(command).of(tree.one, tree.tip) == (held, "")
    assert ran() == 1

    later(monkeypatch, 31)
    again = tree.guards(command)
    assert again.kept(tree.one, tree.tip) == ""
    assert again.of(tree.one, tree.tip) == (held, "")
    assert ran() == 2

    later(monkeypatch, 31 + 31)
    last = tree.guards(command)
    assert last.kept(tree.one, tree.tip) == held
    assert last.of(tree.one, tree.tip) == (held, "")
    assert ran() == 2, "the guards ran a third time on the same head and tip"


def test_merged_tree_guards_that_failed_once_and_pass_on_their_rerun_let_it_merge(
    tmp_path, monkeypatch
):
    tree = Tree(tmp_path)
    held, _ = tree.guards("false").of(tree.one, tree.tip)
    assert held
    later(monkeypatch, 31)
    said, note = tree.guards("true").of(tree.one, tree.tip)
    assert said == "" and note.startswith(treeguards.PASSED.format(**values(tree), seconds="")[:-3])


def test_merged_tree_guards_that_passed_or_were_stopped_are_not_run_after_30_minutes(
    tmp_path, monkeypatch
):
    """Only a failure runs once more: a pass stands, and a stop at the time limit stays kept, since
    a rerun of the same tree spends that run's time (#1103)."""
    tree = Tree(tmp_path)
    passed = tree.guards("true").of(tree.one, tree.tip)
    later(monkeypatch, 31)
    command, ran = runs(tree, "false")
    assert tree.guards(command).of(tree.one, tree.tip) == passed
    assert not (tree.state.parent / "runs").exists()

    monkeypatch.setattr(treeguards, "LIMIT_SECONDS", 1)
    other = SimpleNamespace(number=8, head=tree.head, base="main")
    later(monkeypatch, 0)
    unended = ready.MERGED_TREE_UNENDED.format(**values(tree), minutes=0)
    assert tree.guards("sleep 20").of(other, tree.tip) == (unended, "")
    later(monkeypatch, 31)
    again = tree.guards(command)
    assert again.kept(other, tree.tip) == unended
    assert again.of(other, tree.tip) == (unended, "")
    assert not (tree.state.parent / "runs").exists(), "a stopped tree ran again"


def test_merged_tree_that_passed_while_main_moved_waits_for_the_next_run(tmp_path):
    tree = Tree(tmp_path)
    later = tree.commit({"d.txt": "d\n"})
    guards = tree.guards(f"git -C {tree.main} push -q origin {later}:refs/heads/main")
    assert guards.of(tree.one, tree.tip) == (ready.MAIN_MOVED.format(base="main"), "")


def test_merged_tree_records_of_pull_requests_no_longer_open_are_dropped(tmp_path):
    tree = Tree(tmp_path)
    guards = tree.guards("false")
    held, _ = guards.of(tree.one, tree.tip)
    assert held and guards.kept(tree.one, tree.tip) == held
    guards.open_only({"8": "x"})
    assert json.loads((tree.state / treeguards.KEPT).read_text()) == {}
    assert treeguards.Guards(tree.main, tree.state, True, unchecked).kept(tree.one, tree.tip) == ""


def test_merged_tree_guards_see_none_of_the_environment_jbus_service_gives_jmerge(
    tmp_path, monkeypatch
):
    """jbus.service gives `jmerge` its unit's variables, and systemd its own: a guard test that
    reads one, as `JBUS_TICK_TIMER` held #1283 and `INVOCATION_ID` #1159, fails on the merged
    tree alone. The guards see the machine's login, their `BASE` and their slot, and no more."""
    monkeypatch.delenv(slot.HELD, raising=False)
    monkeypatch.setenv("JBUS_TICK_TIMER", "jbus-merge.timer")
    monkeypatch.setenv("INVOCATION_ID", "0123456789abcdef")
    command = 'test -z "$JBUS_TICK_TIMER$INVOCATION_ID" && test "$BASE" = tip && test -n "$HOME"'
    ran = treeguards.run_guards(command, tmp_path, {"BASE": "tip"}, 60)
    assert ran.code == 0, ran.said


def test_merged_tree_guards_that_fail_keep_the_end_of_what_they_printed(tmp_path):
    """A hold names one guard, or the last line printed where none is named, as `lint` held
    #1290 and #1298: the record keeps the last `TAIL` lines, which say why."""
    tree = Tree(tmp_path)
    printed = "; ".join(f"echo line {n}" for n in range(1, 61))
    held, _ = tree.guards(f"{printed}; exit 1").of(tree.one, tree.tip)
    kept = json.loads((tree.state / treeguards.KEPT).read_text())["7"]
    assert kept["said"] == held
    assert kept["tail"] == "\n".join(f"line {n}" for n in range(21, 61))


HOLDS_THE_SLOT = (
    f'test "$JGAUGE_TEST_SLOT" = full && "{sys.executable}" -c'
    ' "from jgauge import slot; raise SystemExit(slot.free(slot.full(1)))"'
)
"""Guards that pass only where they run inside the machine's one full test slot, and hold it."""


def test_merged_tree_guards_outside_a_slot_run_inside_a_full_one(tmp_path, monkeypatch):
    """A `jmerge` that holds no slot runs the guards, a suite at `-n 6`, inside one of the full
    lane's, so the machine runs no suite the slot count does not see. One that holds a slot
    already runs them in it, and takes no second, which would wait on its own."""
    monkeypatch.delenv(slot.HELD, raising=False)
    tree = Tree(tmp_path)
    said, note = tree.guards(HOLDS_THE_SLOT).of(tree.one, tree.tip)
    assert said == "" and note.startswith(treeguards.PASSED.format(**values(tree), seconds="")[:-3])
    monkeypatch.setenv(slot.HELD, "full")
    ran = treeguards.run_guards('test "$JGAUGE_TEST_SLOT" = full', tmp_path, {}, 60)
    assert ran.code == 0, ran.said


def test_merged_tree_guards_with_every_slot_taken_wait_for_the_next_run(tmp_path, monkeypatch):
    """With every full slot taken past `SLOT_SECONDS`, the guards do not start, and the pull
    request waits for the next run, which keeps nothing of this one and runs them once a slot
    is free. The rest of the run tries no more trees."""
    monkeypatch.delenv(slot.HELD, raising=False)
    monkeypatch.setattr(treeguards, "SLOT_SECONDS", 1)
    tree = Tree(tmp_path)
    marker = tmp_path / "ran"
    guards = tree.guards(f"touch {marker}")
    held, _ = slot.take(slot.full(1))
    try:
        unslotted = ready.MERGED_TREE_NO_SLOT.format(**values(tree), seconds=1)
        assert guards.of(tree.one, tree.tip) == (unslotted, "")
        guards.command = "true"
        assert guards.of(tree.one, tree.tip) == (unslotted, "")
    finally:
        os.close(held)
    assert not marker.exists() and guards.kept(tree.one, tree.tip) == ""
    assert not (tree.state / treeguards.TREE).exists()
    said, note = treeguards.Guards(tree.main, tree.state, True, unchecked).of(tree.one, tree.tip)
    assert said == "" and note
    assert marker.exists()


def test_merged_tree_guards_time_limit_counts_from_the_slot_not_the_wait(tmp_path, monkeypatch):
    """The guards wait 4 s for the slot and run 1 s under a limit of 3 s: they pass, since the
    limit and the seconds of the merge line count the run alone."""
    monkeypatch.delenv(slot.HELD, raising=False)
    monkeypatch.setattr(treeguards, "LIMIT_SECONDS", 3)
    tree = Tree(tmp_path)
    held, _ = slot.take(slot.full(1))
    threading.Timer(4, os.close, (held,)).start()
    began = time.monotonic()
    said, note = tree.guards("sleep 1").of(tree.one, tree.tip)
    assert time.monotonic() - began >= 4
    assert said == ""
    seconds = int(note.rsplit(" in ", 1)[1].removesuffix(" s"))
    assert note == treeguards.PASSED.format(**values(tree), seconds=seconds) and seconds < 4


def test_merged_tree_guards_whose_slot_command_fails_say_why_and_do_not_run(tmp_path, monkeypatch):
    """A `jgauge test-slot` that ends before the guards start, here on a slot count it refuses,
    is why the guards did not run, and nothing of it is a guard that failed."""
    monkeypatch.delenv(slot.HELD, raising=False)
    monkeypatch.setenv("TEST_SLOTS", "none")
    marker = tmp_path / "ran"
    why = treeguards.run_guards(f"touch {marker}", tmp_path, {}, 60)
    assert isinstance(why, str) and "none" in why
    assert not marker.exists()


class Checks:
    """GitHub's artifacts API for a check of this repo that passed in run 5 and left `names`,
    with every path it was asked."""

    URL = "https://github.com/o/r/actions/runs/5"

    def __init__(self, *names):
        self.names = names
        self.asked = []

    def __call__(self, path):
        self.asked.append(path)
        if path.startswith("actions/runs/5"):
            mine = {"id": 1}
            return {
                "conclusion": "success",
                "path": green.WORKFLOW,
                "html_url": self.URL,
                "repository": mine,
                "head_repository": mine,
            }
        name = path.split("name=", 1)[1].split("&", 1)[0]
        run = {"id": 5, "repository_id": 1, "head_repository_id": 1}
        found = [{"workflow_run": run}] if name in self.names else []
        return {"artifacts": found}


def checked_name(tree):
    """The artifact CI's check leaves for the pull request's head merged over the tip."""
    base = git(tree.main, "rev-parse", f"{tree.tip}^{{tree}}")
    merged = git(tree.main, "merge-tree", "--write-tree", tree.tip, tree.head).split()[0]
    return green.checked(base, merged)


def test_merged_tree_a_green_check_tested_runs_no_guards(tmp_path):
    """A tree that a successful check of this repo already tested over the same tip, by the
    artifact it left for the two trees, merges with no guards run, and its merge line says so.
    A tree no check covers, and one whose lookup fails, run the guards."""
    tree = Tree(tmp_path)
    marker = tmp_path / "ran"
    checks = Checks(checked_name(tree))
    said, note = tree.guards(f"touch {marker}", checks).of(tree.one, tree.tip)
    assert (said, note) == ("", treeguards.CHECKED.format(**values(tree), run=Checks.URL))
    assert not marker.exists(), "the guards ran on a tree CI's check passed"
    assert len(checks.asked) == 2
    (tree.state / treeguards.KEPT).unlink()

    said, note = tree.guards(f"touch {marker}", Checks("checked-tree-other")).of(tree.one, tree.tip)
    assert said == "" and note.startswith("the guards passed") and marker.exists()
    marker.unlink()
    (tree.state / treeguards.KEPT).unlink()

    def refused(path):
        raise RuntimeError("HTTP 502")

    said, note = tree.guards(f"touch {marker}", refused).of(tree.one, tree.tip)
    assert said == "" and note.startswith("the guards passed") and marker.exists()


def test_merged_tree_guards_past_the_run_budget_wait_unless_a_green_check_covers_the_tree(tmp_path):
    """A run that has spent `RUN_SECONDS` on guards starts no more: a tree no check covers waits
    for the next run, and one a green check covers still merges, since it runs nothing."""
    tree = Tree(tmp_path)
    marker = tmp_path / "ran"
    guards = tree.guards(f"touch {marker}")
    guards.spent = treeguards.RUN_SECONDS
    assert guards.of(tree.one, tree.tip) == (ready.MERGED_TREE_NO_TIME.format(**values(tree)), "")
    assert not marker.exists() and guards.kept(tree.one, tree.tip) == ""

    covered = tree.guards(f"touch {marker}", Checks(checked_name(tree)))
    covered.spent = treeguards.RUN_SECONDS
    said, note = covered.of(tree.one, tree.tip)
    assert (said, note) == ("", treeguards.CHECKED.format(**values(tree), run=Checks.URL))
    assert not marker.exists()


MAIN_AT_1297 = "342ce51efac01e4c2a8c838395a6bdb6f2f3a40a"
SQUASHED_1307 = "a5bb19a754409bae2f2ecd84a9851ccb7d549060"
BASE_OF_1307 = "376202f250c4ba3ff65415ecf508cf5e8efac51f"
"""main at #1297, #1307 as it merged, and the main #1307's check ran over. Both passed their
checks alone, and on 2026-11-09 #1307 merged five minutes after #1297 with no guards on its
merged tree: main went red on test_scope_root, since #1297's root makes `uncategorized`, a scope
#1307's scopes do not count."""
HOME_GUARDS = (
    'python3 scripts/select_tests.py --part guards "$BASE" HEAD | tr " " "\\n" '
    "| grep '^features/home/tests/' "
    "| xargs uv run pytest -q -n 4 -p no:cacheprovider -p no:randomly"
)
"""`make check-fast PART=guards` with the lint left out and only the home's guard files run,
since the rest takes minutes: the repo's own guard selection, which names test_scope_root."""


def test_merged_tree_guards_hold_1307_over_main_at_1297_on_test_scope_root(tmp_path):
    """#1307, at the main its check ran over, merged over main at #1297 fails the guards on
    test_scope_root, so it waits for its crew's rebase instead of turning main red."""
    if any(
        subprocess.run(["git", "cat-file", "-e", sha], cwd=REPO, capture_output=True).returncode
        for sha in (MAIN_AT_1297, SQUASHED_1307, BASE_OF_1307)
    ):
        pytest.skip("this checkout lacks main's history at #1297 and #1307 (CI's is 2 deep)")
    main = tmp_path / "main"
    git(tmp_path, "clone", "-q", "--shared", "--no-checkout", str(REPO), str(main))
    replayed = git(
        main,
        "merge-tree",
        "--write-tree",
        "--merge-base",
        f"{SQUASHED_1307}^",
        BASE_OF_1307,
        SQUASHED_1307,
    )
    head = git(main, "commit-tree", replayed, "-p", BASE_OF_1307, "-m", "#1307 at its check")
    state = tmp_path / "state"
    state.mkdir()
    (state / treeguards.NAME).write_text(HOME_GUARDS + "\n")
    one = SimpleNamespace(number=1307, head=head, base="main")
    guards = treeguards.Guards(main, state, True, unchecked)

    said, note = guards.of(one, MAIN_AT_1297)

    guard = "features/home/tests/test_scope_root.py::test_the_scopes_the_root_reads_on_status"
    held = ready.MERGED_TREE_FAILS.format(base="main", tip=MAIN_AT_1297[:12], guard=guard)
    assert said.startswith(held.split(guard)[0] + guard), guards.known()["1307"].get("tail")
    assert note == ""
