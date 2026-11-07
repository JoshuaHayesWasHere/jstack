"""`jbus ci` reads macos.yml's jobs apart from main's check: its Mac tests run in parts,
`macos K of N`, each on its own Mac, and the required `macos` is a Linux gate over them that
passes only when every part did. Before the parts, `macos` ran the Mac tests itself."""

import ast
from datetime import timedelta
from pathlib import Path

import pytest

from jbus import watch
from jbus.ci import macjobs, numbers
from test_jbus_ci import NOW, SLICE_NOW, SLICE_START, hosted, row


@pytest.mark.parametrize("mac", ["macos", "macos 2 of 3"])
def test_numbers_count_a_red_macos_job_on_main_as_no_red_main(mac):
    """macos.yml runs on each push to main, beside main's check, and is never main's check:
    neither its job `macos` nor a part `macos K of N` of its Mac tests."""
    jobs = [
        hosted(1, "m1", "main", "success", event="push"),
        hosted(2, "m1", "main", "failure", event="push", name=mac, tests=["tests/test_m.py"]),
        hosted(3, "m1", "main", "success", event="push", name="macos-select"),
    ]
    facts = numbers.Facts(jobs, [], [], NOW)
    assert facts.intervals == []
    assert numbers.mainred(facts, NOW - timedelta(days=7), NOW).shown == "0 min"


def test_numbers_end_no_red_main_at_a_green_macos_job():
    red_at = NOW - timedelta(days=1) + timedelta(minutes=6)
    jobs = [
        hosted(0, "m1", "main", "failure", event="push"),
        hosted(1, "m2", "main", "success", event="push", name="macos"),
    ]
    assert numbers.Facts(jobs, [], [], NOW).intervals == [(red_at, NOW)]


def test_the_macos_yml_job_names_are_one_list_in_jbus_watch():
    """`jbus.ci.numbers` judges main's runs by the test `jbus.watch` judges main by, not a copy."""
    src = Path(watch.__file__).parent
    defined = [
        str(path.relative_to(src))
        for path in sorted(src.rglob("*.py"))
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "MAC_JOBS" for t in node.targets)
    ]
    assert defined == ["watch.py"]
    assert numbers.mac_job is watch.mac_job and macjobs.MAC_PART is watch.MAC_PART


def test_the_macos_wait_counts_the_mac_parts_and_not_the_linux_gate_macos():
    """Run 101 has parts, so its `macos` is the gate, on Linux, and its wait is no Mac's queue.
    Run 102 is from before the parts: its `macos` ran on a Mac and counts."""
    jobs = [
        row(1, 101, "macos 1 of 3", 10, "a1", 1, wait=40),
        row(2, 101, "macos 2 of 3", 10, "a1", 1, wait=60),
        row(3, 101, "macos 3 of 3", 10, "a1", 1, wait=80),
        row(4, 101, "macos", 10, "a1", 1, wait=900),
        row(5, 101, "macos-select", 10, "a1", 1, wait=700),
        row(6, 102, "macos", 20, "b1", 1, wait=20),
    ]
    found = numbers.wait_p90_macos(numbers.Facts(jobs, [], [], SLICE_NOW), SLICE_START, SLICE_NOW)
    assert (found.value, found.shown, found.n) == (74.0, "74 s (p50 50 s)", 4)
