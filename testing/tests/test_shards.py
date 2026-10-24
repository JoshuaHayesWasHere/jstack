"""The check workflow runs the suite as four jobs side by side, each with `--shard K/4`
(`testing/shard.py`). Together the four parts are the whole run: each test the run selected is
in exactly one part, none is in two, and none is left out. That holds for the whole suite, which
`make check` runs, and for the few test files `make check-fast` names.

The test asks pytest itself, as the jobs do: a separate pytest for the whole collection and one for
each part, started side by side, each listing the node ids it would run."""

import subprocess
import sys
from collections import Counter

import pytest

from testing.paths import REPO

PARTS = 4
LIST = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
SOME = ["testing/tests/test_workflows.py", "features/repo-guards/tests/test_one_way.py"]


def listed(*runs):
    """The node ids each of these pytest runs would run, from runs started side by side."""
    started = [
        subprocess.Popen([*LIST, *run], cwd=REPO, stdout=subprocess.PIPE, text=True) for run in runs
    ]
    found = []
    for one in started:
        out, _ = one.communicate(timeout=100)
        assert one.returncode == 0, out[-2000:]
        found.append([line for line in out.splitlines() if "::" in line])
    return found


@pytest.mark.parametrize("selected", [["-m", "not browser"], SOME], ids=["whole", "check-fast"])
def test_the_four_parts_hold_each_selected_test_once_and_miss_none(selected):
    whole, *parts = listed(selected, *([*selected, f"--shard={k}/{PARTS}"] for k in range(1, 5)))
    together = Counter(test for part in parts for test in part)
    assert [test for test, times in together.items() if times > 1] == []
    assert sorted(together) == sorted(whole)
    assert len(whole) > PARTS and all(parts)


def ended(run):
    """The exit status and the output of a pytest started with its output piped."""
    out, _ = run.communicate(timeout=100)
    return run.returncode, out


def parts(*selected):
    """Each of the four parts of this selection, run as CI's jobs run them: on xdist's workers,
    whose controller sets the exit status."""
    run = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "2"]
    started = [
        subprocess.Popen(
            [*run, "--dist", "worksteal", *selected, f"--shard={k}/{PARTS}"],
            cwd=REPO,
            stdout=subprocess.PIPE,
            text=True,
        )
        for k in range(1, PARTS + 1)
    ]
    return [ended(one) for one in started]


def test_a_part_with_none_of_the_selected_tests_passes_and_one_part_runs_each():
    ran = parts(f"{SOME[0]}::test_the_reader_reads_mappings_scalars_and_lists")
    assert [code for code, _ in ran] == [0] * PARTS
    assert sorted("1 passed" in out for _, out in ran) == [False] * (PARTS - 1) + [True]


@pytest.mark.parametrize("workers", [[], ["-n", "2", "--dist", "worksteal"]], ids=["one", "xdist"])
def test_a_selection_with_no_tests_at_all_fails_in_every_part_as_it_does_whole(workers):
    run = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *workers, SOME[0]]
    nothing = ["-k", "no_test_is_named_this"]
    started = [
        subprocess.Popen([*run, *nothing, *shard], cwd=REPO, stdout=subprocess.PIPE, text=True)
        for shard in [[], *([f"--shard={k}/{PARTS}"] for k in range(1, PARTS + 1))]
    ]
    assert [ended(one)[0] for one in started] == [pytest.ExitCode.NO_TESTS_COLLECTED] * (PARTS + 1)


def test_a_shard_that_is_not_k_of_n_is_refused():
    for wrong in ("0/4", "5/4", "4", "a/4"):
        ran = subprocess.run(
            [*LIST, f"--shard={wrong}", SOME[0]], cwd=REPO, capture_output=True, text=True
        )
        assert ran.returncode == 4, wrong
        assert "--shard takes K/N with 1 <= K <= N" in ran.stderr, wrong
