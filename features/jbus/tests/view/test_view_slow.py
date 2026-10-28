"""What slows the work: the rows that wait at each stage, the oldest of each, and the machine's
test slots, on the overview of every project and in the panel of one."""

import fcntl
import json
import os
import shutil

import pytest

from jbus.view.panels.slow import panel as slow
from view.scene import (
    GITHUB,
    Served,
    ago,
    et,
    in_check,
    iso,
    judge_row,
    row,
    slots,
    stacked,
    stacked_pr,
)


def stage(given, key):
    return next(one for one in given["slow"]["stages"] if one["key"] == key)


def test_six_rows_in_check_and_four_of_four_slots_say_so_on_the_overview(scene, monkeypatch):
    in_check(scene)
    slots(scene, monkeypatch, held=4)
    served = Served(scene)
    try:
        given = served.json("/stack.json")
    finally:
        served.close()
    check = stage(given, "check")
    assert (check["rows"], check["checks"], check["cause"]) == (
        6,
        {"failing": 0, "waiting": 6, "passed": 0, "stacked": 0},
        "waiting",
    )
    assert check["oldest"] == {
        "what": "pie-6",
        "project": "demo",
        "since": iso(ago(minutes=60)),
        "open": "#/demo/task/pie-6",
    }
    assert given["slow"]["slots"] == {
        "read": True,
        "used": 4,
        "total": 4,
        "waiting": 0,
        "since": None,
    }


def test_each_stage_counts_its_own_rows_and_you_is_what_needs_you_counts(served):
    given = served.json("/stack.json")
    demo = served.json("/state.json?project=demo")
    by = {one["slug"]: one for one in demo["tasks"]}
    for key, steps in (("check", {"check"}), ("rebase", {"rebase"})):
        mine = [one for one in by.values() if one["step"] in steps]
        assert stage(given, key)["rows"] == len(mine), key
    review = [one for one in by.values() if one["who"] == "rev"]
    assert stage(given, "review")["rows"] == len(review) > 0
    assert stage(given, "rebase")["oldest"]["what"] == "oat-bowl"
    you = stage(given, "you")
    assert you["rows"] == len(given["needs"]) > 0
    first = given["needs"][0]
    assert you["oldest"] == {
        "what": first["what"],
        "project": first["project"],
        "since": first["since"],
        "open": first["open"],
    }
    assert [one["key"] for one in given["slow"]["stages"]] == ["check", "review", "rebase", "you"]


def test_the_stages_count_every_project_and_name_the_oldest_across_them(scene):
    stacked(scene)
    pantry = scene.state_dir / "pantry"
    rows = json.loads((pantry / "queue.json").read_text())
    rows.append(row("fig-pie", "pr", pr="#5", checks="pending", why="wait: check has not passed"))
    (pantry / "queue.json").write_text(json.dumps(rows))
    lines = [judge_row(one, pantry) for one in rows]
    (pantry / "work.json").write_text(json.dumps({"at": iso(scene.now), "work": lines}))
    stamp = et(ago(minutes=300)).removesuffix(" ET")
    with (scene.home_dir / "pantry" / "merge.log").open("a") as log:
        log.write(f"{stamp} wait 5 https://{GITHUB}/acme/pantry/pull/5: check has not passed\n")
    served = Served(scene)
    try:
        given = served.json("/stack.json")
        demo = served.json("/panel/slow.json?project=demo")["data"]
    finally:
        served.close()
    check = stage(given, "check")
    assert check["rows"] == stage(demo, "check")["rows"] + 1
    assert check["checks"]["waiting"] == stage(demo, "check")["checks"]["waiting"] + 1
    assert (check["oldest"]["what"], check["oldest"]["project"]) == ("fig-pie", "pantry")
    assert check["oldest"]["since"] == iso(ago(minutes=300))


def checked(scene, *words):
    in_check(scene, words)
    served = Served(scene)
    try:
        return stage(served.json("/stack.json"), "check")
    finally:
        served.close()


def test_a_failing_check_is_counted_apart_from_one_that_runs_or_waits_and_one_that_passed(scene):
    check = checked(scene, "failed", "failed", "failed", "pending", "none", "passed")
    assert (check["rows"], check["checks"]) == (6, {"failing": 3, "waiting": 2, "passed": 1, "stacked": 0})
    assert check["cause"] == "failing"


def test_the_cause_is_the_larger_count_and_a_tie_names_the_failing_checks(scene):
    assert checked(scene, "failed", "passed", "passed", "passed", "passed")["cause"] == "passed"
    assert checked(scene, "failed", "failed", "failed")["cause"] == "failing"
    assert checked(scene, "failed", "failed", "failed", "passed", "passed", "passed")["cause"] == (
        "failing"
    )


def test_a_check_that_will_not_run_or_a_draft_is_in_check_and_in_none_of_the_three(scene):
    check = checked(scene, "unrun", "draft", "failed", "failed", "passed", "passed")
    assert (check["rows"], check["checks"]) == (6, {"failing": 2, "waiting": 0, "passed": 2, "stacked": 0})


def test_a_stacked_pull_request_is_counted_as_stacked_whatever_its_own_checks_say(scene):
    """`jam-top`'s checks passed and `jam-lid`'s failed, and both merge after `jam-base`: each is
    stacked, by its line's code or, with none, by its text. `jam-pot` passed and is not."""
    stacked_pr(scene)
    served = Served(scene)
    try:
        check = stage(served.json("/stack.json"), "check")
    finally:
        served.close()
    assert (check["rows"], check["checks"]) == (
        3,
        {"failing": 0, "waiting": 0, "passed": 1, "stacked": 2},
    )
    assert check["cause"] == "stacked"


def test_no_stage_but_check_has_counts_of_checks(served):
    given = served.json("/stack.json")
    assert [one["key"] for one in given["slow"]["stages"] if one["checks"] is not None] == ["check"]
    assert [one["key"] for one in given["slow"]["stages"] if one["cause"] is not None] == ["check"]


def test_the_threads_that_wait_for_a_slot_are_counted_with_the_oldest_wait(scene, monkeypatch):
    locks = slots(scene, monkeypatch, held=4)
    waits = [
        {
            "thread": "mcp:a",
            "lane": "full",
            "slots": 4,
            "command": "make check",
            "since": "2026-10-12T19:20:00+00:00",
            "id": "w1",
            "woken": "",
        },
        {
            "thread": "mcp:b",
            "lane": "full",
            "slots": 4,
            "command": "make check",
            "since": "2026-10-12T19:40:00+00:00",
            "id": "w2",
            "woken": "",
        },
        {
            "thread": "mcp:c",
            "lane": "short",
            "slots": 3,
            "command": "pytest",
            "since": "2026-10-12T19:00:00+00:00",
            "id": "w3",
            "woken": "",
        },
    ]
    (locks / "test-slot-waiters.json").write_text(json.dumps(waits))
    served = Served(scene)
    try:
        given = served.json("/stack.json")["slow"]["slots"]
    finally:
        served.close()
    assert (given["waiting"], given["since"]) == (2, "2026-10-12T19:20:00+00:00")


def test_slots_the_machine_does_not_list_are_not_known(scene, monkeypatch):
    slots(scene, monkeypatch, held=1)
    (scene.proc / "locks").unlink()
    served = Served(scene)
    try:
        given = served.json("/stack.json")["slow"]["slots"]
    finally:
        served.close()
    assert given["read"] is False and given["used"] is None
    assert given["total"] == 4


def test_a_held_flock_is_found_in_the_kernel_s_own_list_of_locks(tmp_path, monkeypatch):
    """The real `/proc/locks`, read while this process holds two of three slots."""
    if not os.path.exists("/proc/locks"):
        pytest.skip("this machine has no /proc/locks")
    locks, proc = tmp_path / "locks", tmp_path / "proc"
    locks.mkdir()
    proc.mkdir()
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(locks))
    held = []
    try:
        for n in (1, 2, 3):
            opened = os.open(locks / f"test-slot.{n}.lock", os.O_RDWR | os.O_CREAT, 0o644)
            if n < 3:
                fcntl.flock(opened, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held.append(opened)
        shutil.copyfile("/proc/locks", proc / "locks")
    finally:
        for opened in held:
            os.close(opened)
    assert slow.used(proc, locks, 3) == 2
