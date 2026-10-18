"""`jbus.merge` leaves the merge to a home that merges, asks `jmerge` once a day what a sweep
would remove and never runs one that removes, and says a `jmerge` that cannot read its
protected paths once a day. Run as `tests/test_jbus_kitchen.py` runs: the real pass, against
the fakes.
"""

import ast
import string
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from jbus import merge
from jmerge import ready
from test_jbus_kitchen import DAY, NOW, PASS, QUARTER_PAST_FIVE
from test_jbus_leftover import loud
from test_jbus_queue import add
from test_jbus_row_ends import PULL, listed, result, sends


def test_with_the_home_on_jbus_leaves_the_merge_to_it(kitchen):
    kitchen.set("jmerge.txt", "merged 7 alpha abc1234\n")
    (kitchen.home / "home-thread").write_text("mcp:the-home\n")
    assert "skipped demo: the home mcp:the-home merges" in kitchen.poll()
    assert kitchen.log("jmerge") == [] and kitchen.events("jmerge") == []


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
    assert kitchen.log("jmerge") == ["", ""] and kitchen.events("sweep") == []
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
    """Over three days, with the home off and with it on, every call of `jmerge` that
    sweeps has `--check`: the first of each day, which does not run, and the one after."""
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
        "jmerge: /somewhere/src/jmerge/guarded.txt cannot be read",
        "jmerge: /somewhere/src/jmerge/ci-paths.txt has a pattern that cannot be read, "
        "so nothing is merged: a//b",
        "jmerge: /somewhere/src/jmerge/protected.txt has a pattern that cannot be read, "
        "so nothing is merged: src/**/keys",
    ],
)
def test_a_jmerge_with_no_protected_paths_list_is_a_gate_once_a_day(kitchen, said):
    kitchen.set("jmerge-dies", said)
    printed = kitchen.poll() + kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.log("jmerge") == ["", ""]
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


STEPS = {
    "OTHER_HOME": "",
    "DRAFT": "",
    "MERGE_OFF": "hold",
    "NO_BRIEF": "result",
    "RULES_CHANGED": "check",
    "MAIN_MOVED": "check",
    "FRESH_QUEUED": "check",
    "FRESH_CONFLICT": "rebase",
    "NO_HEAD": "second",
    "BASE": "hold",
    "IN_STACK": "hold",
    "IN_UNNAMED_STACK": "hold",
    "REVIEW_NONE": "hold",
    "NO_REVIEW": "review",
    "NO_VERDICT": "review",
    "NO_FIXED": "findings",
    "NOT_PUSHED": "findings",
    "SECOND_UNWRITTEN": "second",
    "FIX_UNREVIEWED": "second",
    "UNENDED": "findings",
    "FIXED_NO_COMMIT": "findings",
    "REBASE_UNSAID": "rebase",
    "REBASE_UNTRUE": "rebase",
    "CANNOT_CHECK": "rebase",
    "DROPPED": "rebase",
    "NOT_UPHELD": "hold",
    "UNRULED_DROPS": "hold",
    "SCOPED_UNRULED": "second",
    "CONTENT_CHANGED": "second",
    "NOT_PASSED": "check",
    "CONFLICTS": "rebase",
    "UNDECIDED": "check",
    "TOUCHES": "hold",
    "RENAMES_UNSAID": "hold",
    "UNLISTED": "hold",
    "NO_START": "check",
    "GUARDED_UNENDED": "findings",
    "NOT_SEEN": "second",
    "MAIN_CHANGED": "check",
    "FRESH_FAILS": "rebase",
    "REBASE_HELD": "hold",
    "SKILLS_UNRUN": "result",
    "ROW_HELD": "hold",
    "MERGES_AFTER": "check",
    "MIGRATION_TAKEN": "rebase",
    "MIGRATION_MERGING": "check",
    "MIGRATION_REBASING": "check",
    "QUEUE_UNREADABLE": "hold",
}
WORDS = {"REQUIRED", "RULES", "KEPT", "PASSED", "FAILED", "TIMED_OUT", "FRESH_CHECK"}


def _filled(template):
    """A reason with each value it names filled in: a word with no space or comma, as a
    user, a head or a path is, but for what a stale check needs, which is `ready`'s own."""
    filled = {"needs": getattr(ready, "FRESH_CHECK", "")}
    fields = {name for _, name, _, _ in string.Formatter().parse(template) if name}
    return template.format(**{name: filled.get(name, "x1") for name in fields})


def test_each_reason_jmerge_names_is_on_the_step_the_rules_give_it():
    """Every reason `jmerge.ready` holds by name, each on its step (`STEPS`). One that is
    added with no rule, or that stops matching its rule, fails here, and so does a constant
    that is named nowhere. `WORDS` are what `ready` names that is no reason: the check's
    name, the rules' path, and the words of a note and of a local check's result.

    Two reasons are on no step, and the view shows them as Unknown and tells no home:
    `OTHER_HOME` is a pull request of another home, which that home's own view places, and
    `DRAFT` is one its author has not said is done, which no rule of a merge's steps is
    about."""
    named = {
        name
        for name, value in vars(ready).items()
        if name.isupper() and isinstance(value, str) and not name.startswith("_")
    }
    assert named - WORDS == set(STEPS)
    reasons = {name: _filled(getattr(ready, name)) for name in STEPS}
    assert {name: merge.step(f"wait: {reason}") for name, reason in reasons.items()} == STEPS


@pytest.mark.parametrize(
    "names",
    [
        "principle-build-the-lever, principle-sequence-verifiable-units",
        "principle-model-the-domain, principle-type-system-discipline",
    ],
)
def test_a_wait_on_skills_artifacts_is_on_the_crew_s_result_step_whatever_it_lists(names):
    """Winnifred #150 and #151: the one rule places the wait whatever skills it names."""
    said = f"wait: {ready.SKILLS_UNRUN.format(names=names)}"
    assert merge.step(said) == "result"


BARE = {"", "wait", "hold", ", ", " and ", ".."}


def _returned(function):
    """Every string literal a function of `ready.py` returns or formats as a reason: in what
    it returns, in what it formats or joins there, and in what it assigned to a name it
    returns. A literal that is the argument of any other call is read, not returned."""
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
    """A reason written inline in a function of `ready.py` is one no test of the steps sees:
    each string literal a function returns or formats is a constant of the module. `BARE`
    is what a reason may be built with besides: the empty string, the word of a line, and
    what joins the pieces of one."""
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
            "wait: its fix changed more than the findings named: the second pass is not written",
            "second",
        ),
        (
            "wait: guarded (touches src/a.py), the rebase changed the patch after its review",
            "second",
        ),
        ("wait: a check has not finished", "check"),
        ("wait: guarded (touches src/a.py), no proven safety fact at 0123456789ab (x)", "proof"),
        ("wait: it conflicts with its base", "rebase"),
        (
            "wait: guarded (touches a), main changed b after its check started; it needs a rebase",
            "rebase",
        ),
        ("hold: needs user, the rebase dropped 1 of main's lines in src/a.py", "hold"),
        ("wait: its brief says Review: none, so it needs the user's word", "hold"),
        ("wait: another home's", ""),
        ("wait", ""),
    ],
)
def test_a_reason_of_jmerge_is_on_the_step_its_first_rule_names(said, step):
    assert merge.step(said) == step


UNPLACED = "a reason nobody has printed before"


def unplaced(kitchen, reason=UNPLACED):
    """Alpha, whose pull request #9 is open and on no step: `jmerge` says a reason no rule
    names. Its home has a thread."""
    thread = kitchen.t3.thread("demo", "completed", title="home: demo")
    (kitchen.home / "home-id").write_text(thread["threadId"] + "\n")
    add(kitchen, "alpha")
    kitchen.brief("alpha", result("none", pull=PULL))
    kitchen.set("open.json", [kitchen.opened("alpha", 9)])
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: {reason}\n")
    return thread


def test_a_row_the_view_cannot_place_is_told_to_its_home_once(kitchen):
    home = unplaced(kitchen)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=1))
    (sent,) = sends(kitchen)
    assert (sent["threadId"], sent["mode"]) == (home["threadId"], "queue")
    said = sent["message"]
    assert "alpha" in said and f"`wait: {UNPLACED}`" in said
    assert "`merge.RULES` in src/jbus/merge.py has no rule for it" in said
    assert "Brief the fix" in said
    assert listed(kitchen, "unplaced") == [] and loud(kitchen) == []
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: another reason nobody has printed\n")
    kitchen.poll(NOW + timedelta(minutes=2))
    assert len(sends(kitchen)) == 2


def test_a_row_on_its_step_or_of_another_home_tells_its_home_nothing(kitchen):
    unplaced(kitchen, ready.FIX_UNREVIEWED)
    kitchen.poll()
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: {ready.OTHER_HOME}\n")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert sends(kitchen) == []
