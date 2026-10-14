"""`jbus.merge` leaves the merge to a home that merges, asks `jmerge` once a day what a sweep
would remove and never runs one that removes, and says a `jmerge` that cannot read its
protected paths once a day. Run as `tests/test_jbus_kitchen.py` runs: the real pass, against
the fakes.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jbus import merge
from jmerge import ready
from test_jbus_kitchen import DAY, NOW, PASS, QUARTER_PAST_FIVE


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


def test_each_reason_jmerge_names_is_on_the_step_the_rules_give_it():
    """The reasons `jmerge.ready` holds by name. One that is added, or that stops matching
    its rule, fails here: a reason no rule names is given by name too, as no step."""
    steps = {
        "OTHER_HOME": "",
        "DRAFT": "",
        "MERGE_OFF": "hold",
        "NO_BRIEF": "result",
        "RULES_CHANGED": "check",
        "MAIN_MOVED": "check",
        "FRESH_QUEUED": "check",
        "FRESH_CONFLICT": "rebase",
        "NO_HEAD": "second",
    }
    words = {"REQUIRED", "RULES", "KEPT", "PASSED", "FAILED", "TIMED_OUT"}
    named = {
        name
        for name, value in vars(ready).items()
        if name.isupper() and isinstance(value, str) and not name.startswith("_")
    }
    assert named - words == set(steps)
    assert {name: merge.step(f"wait: {getattr(ready, name)}") for name in steps} == steps


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
