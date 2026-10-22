"""A repo's merge gate is the one-line command in a `merge-gate` file of its state. `jmerge`
runs it before every merge, once every other reason is clear, in a checkout of the head.
`jmerge` passes the merge base and the head as the gate's last two arguments, and also as
the environment variables `BASE` and `HEAD`. A non-zero exit holds the pull request, and the
hold line quotes the first line of the gate's output. `merge.log` keeps the whole output. A
repo with no such file merges as before (`features/jmerge/tests/test_jmerge_fresh.py`).

The tests run the command against a real origin and a fake `gh`, as
`features/jmerge/tests/test_jmerge_fresh.py` runs it."""

import fcntl
import json
import os
import sys
import time

import pytest

import test_home_merge as merge
from jbus import expedite, wake
from jmerge import cli, lines, ready
from test_jmerge_fresh import LINES, Kitchen, git, url

GATE = """\
#!/bin/sh
printf '%s\\n' "$@" > "$RECORD/args"
printf '%s %s\\n' "$BASE" "$HEAD" > "$RECORD/env"
git rev-parse HEAD > "$RECORD/cwd"
{say}
exit {code}
"""


@pytest.fixture
def kitchen(tmp_path):
    return Kitchen(tmp_path, {"a.txt": LINES, "b.txt": LINES, "Makefile": "check:\n"})


def gate(kitchen, code=0, say=""):
    """Write a gate script that records how it was called, prints `say` and exits with `code`.
    Name the script in the repo's `merge-gate` file, and return the directory it records in."""
    record = kitchen.tmp / "record"
    record.mkdir(exist_ok=True)
    script = kitchen.tmp / "gate.sh"
    script.write_text(GATE.format(say=say, code=code))
    script.chmod(0o755)
    (kitchen.home.state / "merge-gate").write_text(f"RECORD={record} {script}\n")
    return record


def log(kitchen):
    return (kitchen.home.state / "merge.log").read_text()


def test_a_gate_that_passes_lets_the_merge_go_on_and_the_merged_line_says_so(kitchen):
    head = kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    base = git(kitchen.origin, "rev-parse", "refs/heads/main")
    record = gate(kitchen)
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ") and ", gate: ok, " in said
    assert (record / "args").read_text().split() == [base, head]
    assert (record / "env").read_text().split() == [base, head]
    assert (record / "cwd").read_text().strip() == head
    assert len(kitchen.calls()) == 1
    assert not (kitchen.home.state / "gate" / "6").exists()


def test_the_base_is_where_the_pull_request_left_main_not_main_today(kitchen):
    base = git(kitchen.origin, "rev-parse", "refs/heads/main")
    head = kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    kitchen.on_main({"c.txt": "theirs\n"})
    record = gate(kitchen)
    kitchen.run("--check")
    assert (record / "args").read_text().split() == [base, head]


def test_a_gate_that_fails_holds_the_pull_request_with_its_first_line_and_merges_nothing(
    kitchen,
):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    gate(kitchen, 1, "echo 'no receipt for a.txt'; echo 'replay it first' >&2")
    assert kitchen.run() == [f"hold 6 {url(6)}: its merge gate failed: no receipt for a.txt"]
    assert kitchen.calls() == []
    logged = log(kitchen)
    assert "its merge gate failed: no receipt for a.txt\n" in logged
    assert "  | no receipt for a.txt\n  | replay it first\n" in logged
    holds = kitchen.home.state / "holds.json"
    assert not holds.exists() or json.loads(holds.read_text()) == {}


def test_a_gate_with_no_output_names_its_exit_code(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    gate(kitchen, 3)
    assert kitchen.run() == [f"hold 6 {url(6)}: its merge gate failed: exit 3"]


def test_a_gate_is_run_again_on_every_run_so_a_fix_outside_git_is_seen(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    record = gate(kitchen, say='[ -f "$RECORD/receipt" ] || { echo missing; exit 1; }')
    assert kitchen.run() == [f"hold 6 {url(6)}: its merge gate failed: missing"]
    (record / "receipt").write_text("")
    (said,) = kitchen.run()
    assert said.startswith("merged 6 one ") and ", gate: ok, " in said


@pytest.mark.parametrize("executable", [False, True])
def test_a_gate_that_cannot_start_is_a_hold_that_says_so(kitchen, executable):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    script = kitchen.tmp / "gate.sh"
    if not executable:
        script.write_text("#!/bin/sh\nexit 0\n")
    (kitchen.home.state / "merge-gate").write_text(f"{script}\n")
    (said,) = kitchen.run()
    assert said.startswith(f"hold 6 {url(6)}: its merge gate could not start: ")
    assert str(script) in said
    assert kitchen.calls() == []


def test_check_runs_the_gate_and_prints_the_hold_and_the_output_and_merges_nothing(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    gate(kitchen, 1, "echo 'no receipt'")
    assert kitchen.run("--check") == [
        f"hold 6 {url(6)}: its merge gate failed: no receipt",
        "  | no receipt",
    ]
    assert kitchen.calls() == []
    assert not (kitchen.home.state / "merge.log").exists()


def test_a_passing_gate_is_on_the_ready_line_of_check(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    gate(kitchen)
    (said,) = kitchen.run("--check")
    assert said.startswith("ready 6 ") and said.endswith(f", {lines.GATE_OK}")


def test_a_gate_that_keeps_failing_holds_no_other_pull_request_back(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    gate(kitchen, say='[ "$2" = "$TWO" ] && exit 0; echo no; exit 1')
    two = kitchen.pulls["two"]["headRefOid"]
    (kitchen.home.state / "merge-gate").write_text(
        f"TWO={two} " + (kitchen.home.state / "merge-gate").read_text()
    )
    first, second = kitchen.run()
    assert first == f"hold 6 {url(6)}: its merge gate failed: no"
    assert second.startswith("merged 7 two ") and ", gate: ok, " in second


def test_a_run_whose_gates_took_their_time_starts_no_more_and_the_next_run_does(kitchen):
    one = kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    two = kitchen.crew("two", 7, {"b.txt": LINES + "ours\n"})
    gate(kitchen, 1, "echo no")
    found = cli.Gate(kitchen.home.main, kitchen.home.state, budget=0)
    assert found.of(6, one, "main").why == ready.GATE_FAILED.format(first="no")
    assert found.of(6, one, "main").why == ready.GATE_FAILED.format(first="no")
    assert (found.of(7, two, "main").verb, found.of(7, two, "main").why) == (
        "wait",
        ready.GATE_BUSY,
    )
    again = cli.Gate(kitchen.home.main, kitchen.home.state, budget=0)
    assert again.of(7, two, "main").why == ready.GATE_FAILED.format(first="no")


def test_a_gate_hold_is_not_lifted_by_accept(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    gate(kitchen, 1, "echo no")
    (said,) = kitchen.home.sh(
        f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge --home {merge.ME} '
        "--accept 6 --check"
    )
    assert kitchen.home.code == 1
    assert said == (
        f"refused 6 {url(6)}: its merge gate failed: no, "
        "and a gate that passes lifts it, not --accept"
    )


def test_a_gate_over_its_limit_is_stopped_and_held(kitchen):
    head = kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    pid = kitchen.tmp / "pid"
    (kitchen.home.state / "merge-gate").write_text(f"echo $$ > {pid}; sleep 30; echo late\n")
    started = time.monotonic()
    found = cli.Gate(kitchen.home.main, kitchen.home.state, timeout=1).of(6, head, "main")
    assert time.monotonic() - started < 10
    assert (found.verb, found.why) == ("hold", ready.GATE_TIMED_OUT.format(limit="1 s"))
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid.read_text()), 0)


def test_jbus_tells_the_crew_of_each_gate_hold():
    for why in (
        ready.GATE_FAILED.format(first="no receipt"),
        ready.GATE_UNSTARTED.format(why="not found"),
        ready.GATE_TIMED_OUT.format(limit="10 minutes"),
    ):
        said = lines.one(lines.waits("hold", 6, url(6), why))
        assert said is not None
        row = expedite.short_of(said)
        assert row is not None and row.kind == "gate"


def test_a_gate_ends_before_jbus_stops_the_jmerge_that_runs_it():
    """A run starts no new gate once its gates have used up their budget. The budget plus one
    gate's time limit is less than the time that a pass gives `jmerge`. `jmerge` stops and
    holds a gate that runs over its limit, so jbus does not kill the gate when it stops
    `jmerge`."""
    assert cli.Gate.BUDGET + cli.Gate.TIMEOUT < wake.JMERGE_TIMEOUT


def test_a_gate_another_run_holds_is_waited_for_and_its_checkout_is_left_alone(kitchen):
    head = kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    record = gate(kitchen)
    with (kitchen.home.state / "gate.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        found = cli.Gate(kitchen.home.main, kitchen.home.state).of(6, head, "main")
        assert (found.verb, found.why) == ("wait", ready.GATE_LOCKED)
        assert not (record / "args").exists()
    assert cli.Gate(kitchen.home.main, kitchen.home.state).of(6, head, "main").note == lines.GATE_OK
