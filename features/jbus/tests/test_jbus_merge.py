"""`jbus.merge` leaves the merge to a home that merges. Once a day it asks `jmerge` what a sweep
would remove, and it never runs a sweep that removes. Once a day it also reports a `jmerge` that
cannot read its protected paths. Like `test_jbus_kitchen.py`, the tests run the real pass against
the fakes.
"""

import ast
import contextlib
import os
import string
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import jsettings
from jbus import alert, merge, verbs
from jbus.view import state as view_state
from jmerge import judgement, lock, ready
from test_jbus_kitchen import DAY, NOW, PASS, QUARTER_PAST_FIVE
from test_jbus_leftover import loud
from test_jbus_queue import add
from test_jbus_row_ends import PULL, listed, result, sends


def test_jbus_merges_whatever_the_switch_holds(kitchen):
    """jbus is the only merger: with an id in `home-thread`, the pass still runs `jmerge`, with
    no `--home`, and sends each line it prints."""
    kitchen.set("jmerge.txt", "merged 7 alpha abc1234\n")
    (kitchen.home / "home-thread").write_text("mcp:the-home\n")
    assert not any(line.startswith("skipped") for line in kitchen.poll())
    assert kitchen.log("jmerge") == ["--if-free"]
    assert kitchen.lines("jmerge") == ["merged 7 alpha abc1234"]


REMOVABLE = [
    "removable alpha mcp:thread-1: worktree, local branch, remote branch",
    "removable beta no-thread: remote branch",
]


KEPT = "kept gamma: its pull request is open"


DIES = "wait: could not read origin"


NOT_RUN = f"jmerge --sweep --check did not run ({DIES}), retrying next pass"


def sweeps(kitchen):
    return kitchen.log("jmerge").count("--sweep --check")


def swept(kitchen):
    return kitchen.status()["projects"]["demo"]["sweep"]


def test_once_a_day_what_a_sweep_would_remove_is_one_event(kitchen):
    kitchen.set("sweep.txt", "\n".join([*REMOVABLE, KEPT]) + "\n")
    kitchen.quiet()
    kitchen.poll(QUARTER_PAST_FIVE - timedelta(minutes=1))
    assert kitchen.log("jmerge") == ["--if-free", "--if-free"] and kitchen.events("sweep") == []
    kitchen.poll(QUARTER_PAST_FIVE)
    kitchen.poll(QUARTER_PAST_FIVE + timedelta(hours=3))
    (event,) = kitchen.events("sweep")
    assert (event["line"], event["text"]) == ("sweep demo: 2 to remove", "\n".join(REMOVABLE))
    assert kitchen.log("jmerge").count("--sweep --check") == 1
    assert kitchen.status()["projects"]["demo"]["sweep"] == "2026-10-12: 2 to remove"
    kitchen.set("sweep.txt", f"{REMOVABLE[1]}\n")
    kitchen.poll(QUARTER_PAST_FIVE + DAY)
    assert kitchen.lines("sweep") == ["sweep demo: 2 to remove", "sweep demo: 1 to remove"]
    assert kitchen.status()["projects"]["demo"]["sweep"] == "2026-10-13: 1 to remove"


def test_a_sweep_with_nothing_to_remove_sends_nothing(kitchen):
    kitchen.set("sweep.txt", f"{KEPT}\n")
    kitchen.quiet()
    kitchen.poll(QUARTER_PAST_FIVE)
    assert kitchen.log("jmerge").count("--sweep --check") == 1
    assert kitchen.events("sweep") == []
    assert kitchen.status()["projects"]["demo"]["sweep"] == "2026-10-12: 0 to remove"


def test_a_sweep_that_did_not_run_is_said_in_the_status_file(kitchen):
    kitchen.quiet()
    kitchen.set("jmerge-dies", DIES)
    said = kitchen.poll(QUARTER_PAST_FIVE)
    assert kitchen.events("sweep") == []
    assert swept(kitchen) == f"2026-10-12: {NOT_RUN}"
    assert f"wait demo: 2026-10-12: {NOT_RUN}" in said


def test_a_sweep_that_did_not_run_is_run_again_on_the_next_pass(kitchen):
    kitchen.set("sweep.txt", "\n".join(REMOVABLE) + "\n")
    kitchen.quiet()
    kitchen.set("jmerge-dies", DIES)
    kitchen.poll(QUARTER_PAST_FIVE)
    (kitchen.stub / "jmerge-dies").unlink()
    kitchen.poll(QUARTER_PAST_FIVE + PASS)
    assert sweeps(kitchen) == 2
    assert kitchen.lines("sweep") == ["sweep demo: 2 to remove"]
    assert kitchen.lines("snapshot") == ["snapshot demo: 2026-10-12"]
    assert swept(kitchen) == "2026-10-12: 2 to remove"
    kitchen.poll(QUARTER_PAST_FIVE + 2 * PASS)
    assert sweeps(kitchen) == 2


def test_a_sweep_is_run_on_every_pass_until_one_runs(kitchen):
    kitchen.set("sweep.txt", "\n".join(REMOVABLE) + "\n")
    kitchen.quiet()
    kitchen.set("jmerge-dies", DIES)
    for passes in range(3):
        kitchen.poll(QUARTER_PAST_FIVE + passes * PASS)
        assert swept(kitchen) == f"2026-10-12: {NOT_RUN}"
    (kitchen.stub / "jmerge-dies").unlink()
    kitchen.poll(QUARTER_PAST_FIVE + 3 * PASS)
    assert sweeps(kitchen) == 4
    assert kitchen.lines("sweep") == ["sweep demo: 2 to remove"]
    assert swept(kitchen) == "2026-10-12: 2 to remove"


def test_a_sweep_owed_at_midnight_keeps_its_day_and_the_next_day_sweeps_once(kitchen):
    kitchen.set("sweep.txt", "\n".join(REMOVABLE) + "\n")
    kitchen.quiet()
    kitchen.set("jmerge-dies", DIES)
    late = datetime(2026, 10, 12, 23, 57, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    kitchen.poll(late)
    kitchen.poll(late + PASS)
    assert sweeps(kitchen) == 2
    assert swept(kitchen) == f"2026-10-12: {NOT_RUN}"
    (kitchen.stub / "jmerge-dies").unlink()
    kitchen.poll(QUARTER_PAST_FIVE + DAY)
    kitchen.poll(QUARTER_PAST_FIVE + DAY + PASS)
    assert sweeps(kitchen) == 3
    assert kitchen.lines("sweep") == ["sweep demo: 2 to remove"]
    assert swept(kitchen) == "2026-10-13: 2 to remove"


@pytest.mark.parametrize("home", ["", "mcp:the-home"])
def test_jbus_never_runs_a_sweep_that_removes(kitchen, home):
    """Over three days, with the home off and with it on, every sweep call that jbus makes to
    `jmerge` has `--check`. That holds for the first call of each day, which only checks, and for
    the call after it."""
    (kitchen.home / "home-thread").write_text(f"{home}\n")
    kitchen.set("sweep.txt", "\n".join(REMOVABLE) + "\n")
    for day in range(3):
        kitchen.poll(QUARTER_PAST_FIVE + timedelta(days=day, hours=-6))
        kitchen.set("jmerge-dies", DIES)
        kitchen.poll(QUARTER_PAST_FIVE + timedelta(days=day))
        (kitchen.stub / "jmerge-dies").unlink()
        kitchen.poll(QUARTER_PAST_FIVE + timedelta(days=day) + PASS)
        kitchen.poll(QUARTER_PAST_FIVE + timedelta(days=day, hours=3))
    calls = [call for call in kitchen.log("jmerge") if "sweep" in call]
    assert calls == ["--sweep --check"] * 6


NO_LIST = "condition demo: jmerge has no readable protected-paths list, nothing merges"


@pytest.mark.parametrize(
    "said",
    [
        "jmerge: /somewhere/src/jmerge/protected.txt cannot be read",
        "jmerge: /somewhere/src/jmerge/ci-paths.txt has a pattern that cannot be read, "
        "so nothing is merged: a//b",
        "jmerge: /somewhere/src/jmerge/protected.txt has a pattern that cannot be read, "
        "so nothing is merged: src/**/keys",
    ],
)
def test_a_jmerge_with_no_protected_paths_list_is_a_gate_once_a_day(kitchen, said):
    kitchen.set("jmerge-dies", said)
    printed = kitchen.poll() + kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.log("jmerge") == ["--if-free", "--if-free"]
    assert kitchen.lines() == [NO_LIST]
    assert kitchen.events()[0]["text"] == said
    assert not [line for line in printed if "jmerge did not run" in line]
    kitchen.poll(NOW + DAY)
    assert kitchen.lines() == [NO_LIST] * 2


def test_a_jmerge_that_stops_for_another_reason_is_still_said_on_each_pass(kitchen):
    kitchen.set("jmerge-dies", "jmerge: gh is not installed")
    printed = kitchen.poll() + kitchen.poll(NOW + timedelta(minutes=3))
    assert printed.count("wait demo: jmerge did not run (jmerge: gh is not installed)") == 2
    assert kitchen.lines() == []


LOCKING = """\
#!{python}
import sys, time
from pathlib import Path
from jmerge import lock

stub = Path({stub!r})
if "--sweep" in sys.argv:
    sys.exit(0)
with lock.running(stub, wait="--if-free" not in sys.argv) as free:
    if not free:
        print(lock.BUSY_LINE.format(path=stub / lock.RUN), flush=True)
        sys.exit(lock.BUSY)
    time.sleep(float((stub / "jmerge-sleep").read_text()))
    print((stub / "jmerge.txt").read_text(), end="")
"""


@pytest.fixture
def locking(kitchen, monkeypatch):
    """The kitchen with a `jmerge` that takes the real run lock (`jmerge.lock.running`) in the
    stub directory as the real command does, and a `JMERGE_TIMEOUT` of one second. It is a
    process of its own, so the pass's timeout stops it."""
    script = kitchen.stub / "jmerge"
    script.write_text(LOCKING.format(python=sys.executable, stub=str(kitchen.stub)))
    monkeypatch.setattr(merge, "JMERGE_TIMEOUT", 1)
    kitchen.quiet()
    return kitchen


def held(kitchen):
    """Hold the run lock as another run of `jmerge` does, a tick's or one by hand."""
    return lock.running(kitchen.stub, wait=True)


def streak(kitchen):
    return kitchen.status()["streaks"].get(alert.jmerge("demo"))


def test_a_pass_that_finds_the_run_lock_held_does_nothing_and_counts_no_failure(locking):
    """The pass runs `jmerge --if-free`: with another run holding the run lock, it returns busy
    at once rather than wait inside its own timeout, and the `jmerge` streak is left as it
    was."""
    with held(locking):
        printed = locking.poll()
    assert streak(locking) is None
    assert not [line for line in printed if "jmerge did not run" in line]
    assert "wait demo: jmerge is busy: another run holds its run lock" in printed


def test_a_busy_pass_leaves_a_streak_as_it_was(locking):
    locking.set("jmerge-sleep", "5")
    locking.poll()
    assert streak(locking)["count"] == 1
    locking.set("jmerge-sleep", "0")
    with held(locking):
        locking.poll(NOW + PASS)
    assert streak(locking)["count"] == 1


def test_a_jmerge_that_held_the_lock_past_its_timeout_still_counts_and_alerts(locking):
    locking.set("jmerge-sleep", "5")
    for passes in range(3):
        printed = locking.poll(NOW + passes * PASS)
    assert streak(locking)["count"] == 3
    assert any("jmerge did not run (" in line and "timed out" in line for line in printed)
    (alerted,) = locking.lines("alert")
    assert alerted.startswith("alert: jmerge demo failed 3 times in a row since ")


class Died(Exception):
    """The pass's process ending where the test kills it."""


class _Dying:
    """`os` as `jbus.merge` sees it, but for a `replace` that kills the pass."""

    def __getattr__(self, name):
        return getattr(os, name)

    @staticmethod
    def replace(*args):
        raise Died


def dies(monkeypatch, where):
    """Kill the pass where it reads a run's record: `at the send` of the run's lines, or `before
    the mark`, once they are sent and before the record is marked read."""
    if where == "at the send":

        def killed(*args, **kwargs):
            raise Died

        monkeypatch.setattr(merge, "_sent", killed)
    else:
        monkeypatch.setattr(merge, "os", _Dying())


KILLED = ["at the send", "before the mark"]
WAITS = "wait 7 https://example.test/pull/7: it has no review yet"


def killed_then_passes(kitchen, where):
    """A pass that starts a run and dies `where` while it reads the run's record, then two
    passes that read it, each run ending at its own pass's time as a real run does."""

    def at(now):
        kitchen.monkeypatch.setattr(verbs, "clock", lambda: now)
        kitchen.poll(now)

    with pytest.MonkeyPatch.context() as killing:
        dies(killing, where)
        with pytest.raises(AssertionError):
            at(NOW)
    kitchen.set("jmerge.txt", "")
    (kitchen.stub / "jmerge-dies").unlink(missing_ok=True)
    kitchen.set("jmerge-busy", "")
    at(NOW + PASS)
    at(NOW + 2 * PASS)


@pytest.mark.parametrize("where", KILLED)
def test_a_pass_killed_while_it_reads_a_run_sends_the_run_s_lines_once(kitchen, where):
    """A run's lines reach the user whichever step of the read the pass died at: a record is
    marked read only once its lines are sent, and the next pass, which reads it again, sends
    each line once."""
    kitchen.quiet()
    kitchen.set("jmerge.txt", WAITS + "\n")
    killed_then_passes(kitchen, where)
    assert kitchen.lines("jmerge") == [WAITS]


@pytest.mark.parametrize("where", KILLED)
def test_a_pass_killed_while_it_reads_a_failed_run_counts_the_run_once(kitchen, where):
    """A run that failed is one failure of the `jmerge` streak whichever step of the read the
    pass died at: the next pass reads its record again, and counts no run twice."""
    kitchen.quiet()
    kitchen.set("jmerge-dies", "jmerge: gh is not installed")
    killed_then_passes(kitchen, where)
    assert streak(kitchen)["count"] == 1


STEPS = {name: reason.step for name, reason in ready.reasons().items()}
WORDS = {"REQUIRED", "RULES", "GRAMMAR", "KEPT", "PASSED", "FAILED", "TIMED_OUT", "UNKNOWN"}
WORDS |= {"REVIEW", "NONE", "AFTER", "TWICE", "CLEANUP"}
WORDS |= {"BROWSER", "BROWSER_FAILED", "BROWSER_PENDING"}


def _filled(template):
    """Return a reason with each value it names filled in. A value is a word with no space or
    comma, like a user, a head or a path."""
    fields = {name for _, name, _, _ in string.Formatter().parse(template) if name}
    return template.format(**dict.fromkeys(fields, "x1"))


def test_each_reason_jmerge_names_is_on_the_step_the_rules_give_it():
    """Every reason that `jmerge.ready` holds by name is on the step it is declared with
    (`STEPS`). The test fails on a reason that stops matching its own pattern, on one that an
    earlier rule takes for another step, and on a constant that is no `Reason` and no word.
    `WORDS` are the strings that `ready` names but that are not reasons: the checks' names, the
    rules' path, the section that has the lists' grammar, the words of a note and of a local
    check's result, the code of a reason no rule names, the five review modes a brief's
    `Review:` line says, and the states of a browser run.

    One reason is on no step, and the view shows it as Unknown and tells no home: `OTHER_HOME`,
    a pull request of another home, which that home's own view places. `HAND_DRAFT` is a draft
    someone opened by hand, which jmerge never marks ready: it is on the Result step, since no
    crew handed in a pull request that can merge."""
    named = {
        name
        for name, value in vars(ready).items()
        if name.isupper() and isinstance(value, str) and not name.startswith("_")
    }
    assert named - WORDS == set(STEPS)
    assert (STEPS["OTHER_HOME"], STEPS["HAND_DRAFT"]) == ("", "result")
    reasons = {name: _filled(getattr(ready, name)) for name in STEPS}
    assert {name: judgement.step(f"wait: {reason}") for name, reason in reasons.items()} == STEPS


def test_a_reason_declared_in_ready_is_placed_on_its_step_with_no_other_edit(monkeypatch):
    """A new reason is one declaration in `ready`. `judgement.step` places it on the step it names,
    and a reason that no declaration names is on no step."""
    said = "wait: its frobnicator {name} is not wound"
    assert judgement.step(said.format(name="x1")) == ""
    monkeypatch.setattr(ready, "NOT_WOUND", ready.Reason("findings", said[6:]), raising=False)
    assert judgement.step(said.format(name="x1")) == "findings"


@pytest.mark.parametrize(
    "names",
    [
        "principle-build-the-lever, principle-sequence-verifiable-units",
        "principle-model-the-domain, principle-type-system-discipline",
    ],
)
def test_a_wait_on_skills_artifacts_is_on_the_crew_s_result_step_whatever_it_lists(names):
    """Winnifred #150 and #151: the one rule places the wait on its step whatever skills the wait
    names."""
    said = f"wait: {ready.SKILLS_UNRUN.format(names=names)}"
    assert judgement.step(said) == "result"


BARE = {"", "wait", "hold", ", ", " and ", ".."}


def _returned(function):
    """Return every string literal that a function of `ready.py` returns or formats as a reason.
    That covers what the function returns, what it formats or joins there, and what it assigned
    to a name that it returns. A literal passed as the argument of any other call is an input
    that the function reads, so this leaves it out."""
    assigned = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign) and node.value:
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        assigned.setdefault(name.id, []).append(node.value)
    found, seen = [], set()

    def look(node):
        if isinstance(node, ast.JoinedStr):
            found.append(ast.unparse(node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
        elif isinstance(node, ast.Name) and node.id not in seen:
            seen.add(node.id)
            for value in assigned.get(node.id, []):
                look(value)
        elif isinstance(node, ast.Call):
            called = node.func
            if isinstance(called, ast.Attribute) and called.attr in ("format", "join"):
                if called.attr == "format":
                    look(called.value)
                for argument in [*node.args, *(one.value for one in node.keywords)]:
                    look(argument)
        elif isinstance(node, ast.Tuple | ast.List | ast.Set | ast.Starred | ast.BoolOp):
            for child in ast.iter_child_nodes(node):
                look(child)
        elif isinstance(node, ast.IfExp):
            look(node.body)
            look(node.orelse)
        elif isinstance(node, ast.BinOp):
            look(node.left)
            look(node.right)
        elif isinstance(node, ast.ListComp | ast.GeneratorExp):
            look(node.elt)

    for node in ast.walk(function):
        if isinstance(node, ast.Return) and node.value is not None:
            look(node.value)
    return found


def test_every_reason_ready_returns_is_one_of_its_constants():
    """No test of the steps sees a reason written inline in a function of `ready.py`. So each
    string literal that a function returns or formats must be a constant of the module. Besides
    the constants, a reason may be built from `BARE`: the empty string, the word of a line, and
    what joins the pieces of a reason."""
    tree = ast.parse(Path(ready.__file__).read_text())
    constants = {
        value for name, value in vars(ready).items() if name.isupper() and isinstance(value, str)
    }
    inline = [
        (function.name, literal)
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        for literal in _returned(function)
        if literal not in constants | BARE
    ]
    assert inline == []


@pytest.mark.parametrize(
    ("said", "step"),
    [
        ("wait: no brief has a Result that names it", "result"),
        ("wait: it has no review yet", "review"),
        ("wait: its findings are not handled: the Result has no Fixed line", "findings"),
        (
            "wait: its fix is not reviewed: the scoped review of it is not written",
            "second",
        ),
        ("wait: check has not passed", "check"),
        ("wait: no proven safety fact at 0123456789ab (x)", ""),
        ("wait: it conflicts with its base", "rebase"),
        ("hold: needs user, the rebase dropped 1 of main's lines in src/a.py", "hold"),
        ("wait: its brief says Review: none, so it needs the user's word", "hold"),
        ("wait: another home's", ""),
        ("wait", ""),
    ],
)
def test_a_reason_of_jmerge_is_on_the_step_its_first_rule_names(said, step):
    assert judgement.step(said) == step


UNPLACED = "a reason nobody has printed before"


def unplaced(kitchen, reason=UNPLACED, number=9):
    """Make alpha, whose pull request (#9 unless named) is open and on no step, because `jmerge`
    says a reason that no rule names. Its home has a thread."""
    thread = kitchen.t3.thread("demo", "completed", title="home: demo")
    (kitchen.home / "home-id").write_text(thread["threadId"] + "\n")
    add(kitchen, "alpha")
    opened = kitchen.opened("alpha", number)
    kitchen.brief("alpha", result("none", pull=opened["url"]))
    kitchen.set("open.json", [opened])
    kitchen.set("jmerge.txt", f"wait {number} {opened['url']}: {reason}\n")
    return thread


def test_a_row_the_view_cannot_place_is_told_to_its_home_once(kitchen):
    home = unplaced(kitchen)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=1))
    (sent,) = sends(kitchen)
    assert (sent["threadId"], sent["mode"]) == (home["threadId"], "queue")
    said = sent["message"]
    assert "alpha" in said and f"`wait: {UNPLACED}`" in said
    assert "`rules` in features/jmerge/src/jmerge/ready.py has no rule for it" in said
    assert "Brief the fix" in said
    assert listed(kitchen, "unplaced") == [] and loud(kitchen) == []
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: another reason nobody has printed\n")
    kitchen.poll(NOW + timedelta(minutes=2))
    assert len(sends(kitchen)) == 2


@pytest.mark.parametrize(
    "said",
    [
        'the merge failed: non-200 OK status code: 502 Bad Gateway body: "<html>..."',
        "the merge failed: GraphQL: Merge already in progress (mergePullRequest)",
    ],
)
def test_a_merge_github_refused_is_on_the_check_step_and_not_unknown(kitchen, said):
    """context-packs #56, 2026-10-20: GitHub refused the merge call twice, first with a 502 and
    then with a merge already in progress, and the next run looks again. The view placed the pull
    request in the Unknown lane and told its home, since no rule named the reason."""
    unplaced(kitchen, said, number=56)
    kitchen.poll()
    sources = view_state.Sources(kitchen.state_dir, kitchen.root / "home", user=jsettings.load())
    built = view_state.build(sources, "demo", NOW, lambda _: {})
    (alpha,) = [one for one in built["tasks"] if one["slug"] == "alpha"]
    assert (alpha["step"], alpha["state"]["say"]) == ("check", said)
    assert sends(kitchen) == []


def test_a_row_on_its_step_or_of_another_home_tells_its_home_nothing(kitchen):
    unplaced(kitchen, ready.FIX_UNREVIEWED)
    kitchen.poll()
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: {ready.OTHER_HOME}\n")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert sends(kitchen) == []


UNFOLLOWED = (
    "the tool jstack was not reinstalled after its package list changed "
    "(uv tool install --editable /code/jstack --reinstall: error: no network)"
)


def test_a_merge_whose_tool_was_not_reinstalled_is_an_alert(kitchen):
    kitchen.set(
        "jmerge.txt", f'merged 7 alpha abc1234 "a move", {UNFOLLOWED}, kept: y, revert: x\n'
    )
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=1))
    assert kitchen.lines("alert") == [f"alert: demo: {UNFOLLOWED}"]
    assert kitchen.wakes.said == [f"alert: demo: {UNFOLLOWED}"]


NOT_INSTALLED = (
    "the install was not run again after the merge changed what it assembles "
    "(sh install.sh: old hard layout codex /y -> stale: skills/demo/SKILL.md)"
)


def test_a_merge_whose_install_was_not_run_again_is_an_alert(kitchen):
    kitchen.set(
        "jmerge.txt", f'merged 7 alpha abc1234 "a move", {NOT_INSTALLED}, kept: y, revert: x\n'
    )
    kitchen.poll()
    assert kitchen.lines("alert") == [f"alert: demo: {NOT_INSTALLED}"]


NOT_PULLED = (
    "the main checkout was not pulled after the merge "
    "(fatal: Not possible to fast-forward, aborting.)"
)


def test_a_merge_whose_main_checkout_was_not_pulled_is_an_alert(kitchen):
    kitchen.set(
        "jmerge.txt", f'merged 7 alpha abc1234 "a move", {NOT_PULLED}, kept: y, revert: x\n'
    )
    kitchen.poll()
    assert kitchen.lines("alert") == [f"alert: demo: {NOT_PULLED}"]


def test_a_merge_whose_tool_was_reinstalled_is_no_alert(kitchen):
    done = "reinstalled the tool jstack from /code/jstack: its package list changed"
    kitchen.set("jmerge.txt", f'merged 7 alpha abc1234 "a move", {done}, revert: x\n')
    kitchen.poll()
    assert kitchen.lines("alert") == []


CHANGED = 'merged 7 alpha abc1234def5 "a skill", skills changed: crew home, revert: x\n'


def test_a_merge_that_changes_a_skill_tells_each_thread_out_once(kitchen):
    """notes.md lines 31 and 266: a thread keeps the skill text it loaded, so after a merge that
    changed a skill it runs the old text until told, and the home told 19 crews by hand. Each
    thread out that loaded a changed skill is told once, naming only those; a reviewer, which
    loaded neither, a thread started after the merge, a settled one and one whose title gives no
    role are not. Each runs a turn, since the notice starts none (`outbox`'s `idle` rule)."""
    crew = kitchen.t3.thread("alpha")
    reviewer = kitchen.t3.thread("beta", title="review: beta")
    home = kitchen.t3.thread("demo", title="home: demo")
    kitchen.t3.thread("gamma", "completed", idle=timedelta(1), settled=True)
    kitchen.t3.thread("chat", "completed", idle=timedelta(1), title="a chat of the user's")
    kitchen.set("jmerge.txt", CHANGED)
    kitchen.poll()
    told = {one["threadId"]: one["message"] for one in sends(kitchen)}
    assert set(told) == {crew["threadId"], home["threadId"]}
    assert reviewer["threadId"] not in told
    for thread, name in ((crew, "crew"), (home, "home")):
        message = told[thread["threadId"]]
        assert "#7" in message and f"skills: {name}." in message and "\n" not in message
    kitchen.t3.thread("delta", age=-timedelta(minutes=1))
    kitchen.poll(NOW + timedelta(minutes=1))
    assert len(sends(kitchen)) == 2


def test_a_skill_its_brief_names_is_one_the_thread_loaded(kitchen):
    kitchen.brief("alpha", "Skills: architect\n")
    kitchen.brief("beta")
    named = kitchen.t3.thread("alpha")
    kitchen.t3.thread("beta")
    kitchen.set("jmerge.txt", CHANGED.replace("crew home", "architect"))
    kitchen.poll()
    (told,) = sends(kitchen)
    assert told["threadId"] == named["threadId"] and "skills: architect." in told["message"]


def test_a_skill_note_t3_did_not_take_is_sent_on_the_next_pass(kitchen):
    crew = kitchen.t3.thread("alpha")
    kitchen.set("jmerge.txt", CHANGED)
    kitchen.t3.lose_send = True
    kitchen.poll()
    kitchen.t3.lose_send = False
    kitchen.set("jmerge.txt", "")
    kitchen.poll(NOW + timedelta(minutes=1))
    kitchen.poll(NOW + timedelta(minutes=2))
    went = [one for one in sends(kitchen) if one["threadId"] == crew["threadId"]]
    assert len({one["clientRequestId"] for one in went}) == 1
    assert "skills: crew." in went[-1]["message"]


def test_a_skill_note_whose_pass_stops_partway_is_kept_for_the_next(kitchen, monkeypatch):
    """A pass that stops while it sends still keeps the merge, since jmerge prints its line
    once: the pass fails, and the next one sends the note."""
    from jbus import outbox

    crew = kitchen.t3.thread("alpha")
    kitchen.set("jmerge.txt", CHANGED)
    real = outbox.send

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(outbox, "send", broken)
    with pytest.raises(AssertionError):
        kitchen.poll()
    monkeypatch.setattr(outbox, "send", real)
    kitchen.set("jmerge.txt", "")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert [one["threadId"] for one in sends(kitchen)] == [crew["threadId"]]


@pytest.mark.parametrize(
    ("skill", "role"),
    [("home", "home"), ("handoff", "home"), ("crew", "crew"), ("pr-review", "review")],
)
def test_a_merge_tells_only_the_role_that_loads_its_skill(kitchen, skill, role):
    """scout-token-review: three merges that changed only the home or handoff skill went to 56
    threads, most of them crews. A home skill tells no crew or reviewer, and a crew skill no
    home."""
    threads = {
        "crew": kitchen.t3.thread("alpha"),
        "review": kitchen.t3.thread("beta", title="review: beta"),
        "home": kitchen.t3.thread("demo", title="home: demo"),
    }
    kitchen.set("jmerge.txt", CHANGED.replace("crew home", skill))
    kitchen.poll()
    assert [one["threadId"] for one in sends(kitchen)] == [threads[role]["threadId"]]


def test_merges_that_land_within_one_pass_are_one_tell_a_thread(kitchen):
    crew = kitchen.t3.thread("alpha")
    later = CHANGED.replace("merged 7", "merged 8").replace("abc1234def5", "fed4321cba9")
    kitchen.set("jmerge.txt", CHANGED + later)
    kitchen.poll()
    (told,) = sends(kitchen)
    assert told["threadId"] == crew["threadId"] and "skills: crew." in told["message"]
    assert "#7 at abc1234def5, #8 at fed4321cba9" in told["message"]
    kitchen.set("jmerge.txt", CHANGED + later)
    kitchen.poll(NOW + timedelta(minutes=1))
    assert len(sends(kitchen)) == 1
    assert (kitchen.state / "reload.json").read_text().strip() == "[]"


def test_a_merge_the_tick_keeps_while_a_pass_tells_is_told_on_the_next_pass(kitchen, monkeypatch):
    """merge-loop F6: the tick keeps a merge in reload.json while a pass's `tell` asks T3 Code
    for the threads out, and `tell`'s write of what it read before must not drop it."""
    from types import SimpleNamespace

    import jbus
    from jbus import passes, reload, t3

    crew = kitchen.t3.thread("alpha")
    later = CHANGED.replace("merged 7", "merged 8").replace("abc1234def5", "fed4321cba9")
    real = t3.listed

    def ticked(*args, **kwargs):
        monkeypatch.setattr(reload, "t3", t3)
        config = jbus.load()
        reload.keep(passes.Pass(config, config.projects[0], NOW, lambda _: None), [later])
        return real(*args, **kwargs)

    monkeypatch.setattr(reload, "t3", SimpleNamespace(listed=ticked))
    kitchen.set("jmerge.txt", CHANGED)
    kitchen.poll()
    kitchen.set("jmerge.txt", "")
    kitchen.poll(NOW + timedelta(minutes=1))
    told = [one["message"] for one in sends(kitchen) if one["threadId"] == crew["threadId"]]
    assert len(told) == 2 and "#7 at abc1234def5" in told[0] and "#8 at fed4321cba9" in told[1]
    assert (kitchen.state / "reload.json").read_text().strip() == "[]"


NO_RECORD = "wait demo: jmerge did not run (its run ended with no record: it said nothing)"


class Died(BaseException):
    """The pass's process dies here, as a timeout, a reboot or an OOM kill stops it."""


def merge_at(kitchen, monkeypatch, at, said=None):
    """Run the pass's `merge` step alone at `at`, adding what it says to `said`, and return
    `said`."""
    import jbus
    from jbus import passes, verbs

    monkeypatch.setattr(verbs, "clock", lambda: at)
    config = jbus.load()
    said = [] if said is None else said
    merge.merge(passes.Pass(config, config.project("demo"), at, said.append))
    return said


def stamp(kitchen):
    path = kitchen.state / merge.RUNS / merge.STARTED
    return path.read_text().strip() if path.exists() else None


def deaths(kitchen):
    """The lines of the log that tell of a run that ended with no record."""
    return [one for one in kitchen.lines() if "ended with no record" in one]


@pytest.mark.parametrize("dies", ["moved", "told", "unlinked"])
def test_a_run_that_died_is_told_once_wherever_the_pass_dies_around_its_tell(
    kitchen, monkeypatch, dies
):
    """A run that has not taken its lock past `STARTING` is told dead. The pass that finds its
    stamp dies just after it moves the stamp aside, just after the log tells of the run, or just
    after it removes a stamp. The run, slower still, then takes its lock and runs nothing, so
    the tell was true. The death is told once, by the dying pass or the one after, and the
    streak never counts it twice."""
    from jbus import wake

    kitchen.quiet()
    (kitchen.stub / "jmerge.log").unlink()
    stamps = []
    monkeypatch.setattr(merge, "start", lambda run: stamps.append(stamp(kitchen)) or "")
    merge_at(kitchen, monkeypatch, NOW)
    late = NOW + merge.STARTING + timedelta(seconds=1)
    send, unlink, replace = wake.Box.send, type(kitchen.state).unlink, merge.os.replace

    def told(box, slug, kind, line, *args, **kwargs):
        went = send(box, slug, kind, line, *args, **kwargs)
        if dies == "told" and "ended with no record" in line:
            raise Died
        return went

    def unlinked(path, *args, **kwargs):
        unlink(path, *args, **kwargs)
        if dies == "unlinked" and path.name in (merge.STARTED, getattr(merge, "DIED", "")):
            raise Died

    def moved(source, target):
        replace(source, target)
        if dies == "moved" and Path(target).name == getattr(merge, "DIED", ""):
            raise Died

    with monkeypatch.context() as patched:
        patched.setattr(wake.Box, "send", told)
        patched.setattr(type(kitchen.state), "unlink", unlinked)
        patched.setattr(merge.os, "replace", moved)
        with contextlib.suppress(Died):
            merge_at(kitchen, monkeypatch, late)
    merge.keep(kitchen.state / merge.RUNS, kitchen.checkout, stamp=stamps[0])
    assert kitchen.log("jmerge") == []
    merge_at(kitchen, monkeypatch, late)
    assert len(deaths(kitchen)) == 1
    counted = alert.streaks(kitchen.state_dir).get(alert.jmerge("demo"), {})
    assert counted.get("count", 0) <= 1


def test_a_slow_run_whose_death_was_told_runs_nothing_and_leaves_the_next_runs_stamp(
    kitchen, monkeypatch
):
    """Two runs back to back. Run A starts slower than `STARTING`, and the pass tells its death
    and starts run B. A then takes its lock: its stamp is gone, so it runs nothing and keeps no
    record, and B's stamp stands. B dies too, and its death is told on the next pass. Each death
    is told once, and each of them truly left no record."""
    kitchen.quiet()
    (kitchen.stub / "jmerge.log").unlink()
    stamps = []
    monkeypatch.setattr(merge, "start", lambda run: stamps.append(stamp(kitchen)) or "")
    merge_at(kitchen, monkeypatch, NOW)
    late = NOW + merge.STARTING + timedelta(seconds=1)
    said = merge_at(kitchen, monkeypatch, late)
    first, second = stamps
    assert first != second and stamp(kitchen) == second
    kitchen.set("jmerge.txt", f"wait 7 {PULL}: it has no review yet\n")
    merge.keep(kitchen.state / merge.RUNS, kitchen.checkout, stamp=first)
    assert kitchen.log("jmerge") == [] and stamp(kitchen) == second
    assert not list((kitchen.state / merge.RUNS).glob("ran-*.json"))
    said += merge_at(kitchen, monkeypatch, late + merge.STARTING + timedelta(seconds=1))
    assert said.count(NO_RECORD) == 2 and len(deaths(kitchen)) == 2
    assert kitchen.lines("jmerge") == []


def test_a_run_that_kept_its_record_and_died_before_its_stamp_went_is_no_death(
    kitchen, monkeypatch
):
    """The run writes its record and dies before it removes its stamp. The next pass past
    `STARTING` reads the record's line and says no run ended with no record."""
    import merge_in_pass

    kitchen.quiet()
    line = f"wait 7 {PULL}: it has no review yet"
    kitchen.set("jmerge.txt", f"{line}\n")

    def dies_before_its_stamp_goes(run):
        left = stamp(kitchen)
        merge_in_pass.start(run)
        (kitchen.state / merge.RUNS / merge.STARTED).write_text(left)
        return ""

    monkeypatch.setattr(merge, "start", dies_before_its_stamp_goes)
    merge_at(kitchen, monkeypatch, NOW)
    monkeypatch.setattr(merge, "start", lambda run: "")
    said = merge_at(kitchen, monkeypatch, NOW + merge.STARTING + timedelta(seconds=1))
    assert not [one for one in said if "jmerge did not run" in one] and deaths(kitchen) == []
    assert kitchen.lines("jmerge") == [line]
