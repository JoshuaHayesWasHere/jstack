"""What slows the work: the rows that wait at each stage, the oldest of each, and the machine's
test slots, on the overview of every project and in the panel of one."""

import fcntl
import json
import os
import shutil

import pytest

from jbus.view.panels.slow import panel as slow
from view.scene import GITHUB, Served, ago, et, iso, judge_row, logged, row, stacked

IN_CHECK = [(f"pie-{n}", 20 + n, 10 * n) for n in range(1, 7)]


def in_check(scene):
    """Six pull requests whose check has not passed: `pie-6`'s wait is the oldest, an hour."""
    scene.queue(
        [
            row(slug, "pr", pr=f"#{number}", checks="pending", why="wait: check has not passed")
            for slug, number, _ in IN_CHECK
        ]
    )
    scene.merge_log(
        *(
            logged(minutes, "wait", number, "check has not passed")
            for _, number, minutes in IN_CHECK
        )
    )


def slots(scene, monkeypatch, held, total=4):
    """`total` full test slots, of which the first `held` are held, as `/proc/locks` lists a
    held flock: by the device and the inode of its lock file."""
    locks = scene.root / "locks"
    locks.mkdir(exist_ok=True)
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(locks))
    monkeypatch.setenv("TEST_SLOTS", str(total))
    lines = []
    for n in range(1, total + 1):
        path = locks / f"test-slot.{n}.lock"
        path.touch()
        if n <= held:
            seen = path.stat()
            where = f"{os.major(seen.st_dev):02x}:{os.minor(seen.st_dev):02x}:{seen.st_ino}"
            lines.append(f"{n}: FLOCK  ADVISORY  WRITE {4000 + n} {where} 0 EOF")
    (scene.proc / "locks").write_text("".join(line + "\n" for line in lines))
    return locks


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
    runner = stage(given, "runner")
    assert (runner["rows"], runner["running"]) == (6, 0)
    assert runner["oldest"] == {
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
    for key, steps in (("runner", {"check"}), ("rebase", {"rebase"})):
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
    assert [one["key"] for one in given["slow"]["stages"]] == ["runner", "review", "rebase", "you"]


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
    runner = stage(given, "runner")
    assert runner["rows"] == stage(demo, "runner")["rows"] + 1
    assert (runner["oldest"]["what"], runner["oldest"]["project"]) == ("fig-pie", "pantry")
    assert runner["oldest"]["since"] == iso(ago(minutes=300))


def test_a_check_with_a_runner_is_counted_apart_from_one_that_waits_for_it(scene, monkeypatch):
    in_check(scene)
    seen = {
        "pie-1": {
            "check": {"name": "check", "state": "in_progress", "started": iso(ago(minutes=3))}
        },
        "pie-2": {"check": {"name": "check", "state": "queued", "started": None}},
    }
    scene.passed(seconds_ago=20, rows=seen)
    served = Served(scene)
    try:
        runner = stage(served.json("/stack.json"), "runner")
    finally:
        served.close()
    assert (runner["rows"], runner["running"]) == (6, 1)


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
