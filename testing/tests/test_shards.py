"""The check workflow runs the suite as eight jobs side by side, each with `--shard K/8`
(`testing/shard.py`). Together the eight parts are the whole run: each test the run selected is
in exactly one part, none is in two, and none is left out. That holds for the whole suite, which
`make check` runs, and for the few test files `make check-fast` names. The parts are split by
each test's time in `testing/shard-times.tsv`, so they end together: no part holds more than the
slowest test's time over another.

The test asks pytest itself, as the jobs do: a separate pytest for the whole collection and one for
each part, started side by side, each listing the node ids it would run."""

import importlib.util
import os
import subprocess
import sys
from collections import Counter
from xml.sax.saxutils import quoteattr

import pytest

from testing.paths import REPO
from testing.shard import FLOOR, TIMES, WORKERS, key, mangled, read_times, recorded, seconds, split

PARTS = 8
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
def test_the_parts_hold_each_selected_test_once_and_miss_none(selected):
    whole, *parts = listed(
        selected, *([*selected, f"--shard={k}/{PARTS}"] for k in range(1, PARTS + 1))
    )
    together = Counter(test for part in parts for test in part)
    assert [test for test, times in together.items() if times > 1] == []
    assert sorted(together) == sorted(whole)
    assert len(whole) > PARTS and all(parts)


def test_the_whole_suite_s_parts_end_together():
    """Time, not count: the parts of the whole suite, by the table's seconds, are no further apart
    than their slowest test, and the merge flow's TLC test, at the warm time CI runs it at, shares
    its part."""
    whole, *parts = listed(
        ["-m", "not browser"],
        *(["-m", "not browser", f"--shard={k}/{PARTS}"] for k in range(1, PARTS + 1)),
    )
    times = read_times(TIMES)
    assert sum(key(test) in times for test in whole) > len(whole) / 3
    assert [FLOW] not in parts
    each = [sum(seconds(times, test) for test in part) for part in parts]
    assert max(each) - min(each) <= max(seconds(times, test) for part in parts for test in part)
    assert max(each) - min(each) < sum(each) / len(parts) / 20


def test_a_test_that_outlasts_the_others_share_has_a_part_alone_and_one_that_does_not_has_company():
    """A part ends at its tests' time over `WORKERS`, and never before its slowest test. A test
    of 50 s among 300 tests of 1 s over 4 parts outlasts the others' share (300 / 3 / 4 = 25 s),
    so it is alone. A test of 10 s does not, and its part takes tests of 1 s until it would end
    later than the rest."""
    quick = [f"t.py::test_{n:03}" for n in range(300)]
    for slow, alone in ((50, True), (10, False)):
        times = {key("t.py::test_slow"): slow} | {key(test): 1 for test in quick}
        parts = split(["t.py::test_slow", *quick], times, 4)
        (mine,) = [part for part in parts if "t.py::test_slow" in part]
        assert (mine == ["t.py::test_slow"]) == alone
        others = [len(part) / WORKERS for part in parts if part is not mine]
        assert max(others) - min(others) <= 1 / WORKERS


def test_tests_that_move_no_part_s_end_spread_over_the_parts_and_do_not_pile_onto_one():
    """Two parts that each end at a test of 100 s have room for ten tests of 10 s, which end no
    part later. They go five and five, by seconds, and not all to one part: two slow tests that
    each run a check of their own in one part ran past their time limit in CI."""
    quick = [f"t.py::test_{n}" for n in range(10)]
    times = {key("t.py::test_a"): 100, key("t.py::test_b"): 100} | {key(t): 10 for t in quick}
    parts = split(["t.py::test_a", "t.py::test_b", *quick], times, 2)
    assert sorted(len(part) for part in parts) == [6, 6]
    assert all({"t.py::test_a", "t.py::test_b"} - set(part) for part in parts)


FLOW = (
    "features/jmerge/tests/test_flow_spec.py::"
    "test_today_and_the_design_hold_their_rules_and_each_canary_breaks_its_own"
)


def test_the_flow_spec_test_counts_its_warm_time():
    """The merge flow's TLC test takes minutes when TLC runs (524 to 899 s in CI on 2026-11-03)
    and a second or two where its cache holds the runs, as every part of the check restores
    main's. The table holds its warm time, which CI's full runs on main record, so the split does
    not give it a part of its own that ends minutes before the others; a table recorded with TLC
    run cold fails here."""
    (whole,) = listed([FLOW.partition("::")[0]])
    assert FLOW in whole
    assert FLOOR < seconds(read_times(TIMES), FLOW) < 60


def test_a_slow_test_has_a_part_to_itself_where_a_split_by_count_would_add_to_it(tmp_path):
    """One test of 100 s among tests of 1 s: its part holds it alone, and the others share the
    rest evenly, one apart at most."""
    (whole,) = listed([SOME[0]])
    slow, *rest = whole
    table = tmp_path / "times.tsv"
    table.write_text("".join(f"{100 if test == slow else 1}\t{key(test)}\n" for test in whole))
    parts = listed(
        *([SOME[0], f"--shard-times={table}", f"--shard={k}/{PARTS}"] for k in range(1, PARTS + 1))
    )
    assert [slow] in parts
    others = [len(part) for part in parts if slow not in part]
    assert len(rest) >= 2 * PARTS and max(others) - min(others) <= 1


def test_a_run_writes_the_table_the_split_reads_with_the_tests_that_took_the_floor_or_more(
    tmp_path,
):
    """`--shard-record` writes each test that took `FLOOR` or more, with its seconds, in the shape
    --shard-times reads, also from xdist's workers. A quicker one counts as `FLOOR` unlisted."""
    (tmp_path / "test_two.py").write_text(
        "import time\n\n"
        f"def test_slow():\n    time.sleep({FLOOR * 5})\n\n"
        "def test_quick():\n    pass\n"
    )
    table = tmp_path / "times.tsv"
    run = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "testing.shard"]
    ran = subprocess.run(
        [*run, "-n", "2", f"--shard-record={table}", "test_two.py"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stdout[-2000:]
    times = read_times(table)
    assert list(times) == [key("test_two.py::test_slow")]
    assert seconds(times, "test_two.py::test_slow") >= FLOOR * 4


def test_a_run_writes_a_test_s_pinned_seconds_in_place_of_the_time_it_took_here(tmp_path):
    """A test whose CI time this machine does not see, as the merge flow's TLC test runs warm in
    well under `FLOOR` where its cache holds the runs, pins its seconds with `shard_seconds`, and
    `--shard-record` writes them, also from xdist's workers and also where the test is skipped,
    so a refresh by the command alone keeps its row at its cold time."""
    (tmp_path / "test_pinned.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.shard_seconds(653.60)\n"
        "def test_warm():\n    pass\n\n"
        "@pytest.mark.shard_seconds(42)\n"
        "@pytest.mark.skip(reason='no Java')\n"
        "def test_skipped():\n    pass\n\n"
        "def test_quick():\n    pass\n"
    )
    table = tmp_path / "times.tsv"
    run = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "testing.shard"]
    ran = subprocess.run(
        [*run, "--strict-markers", "-n", "2", f"--shard-record={table}", "test_pinned.py"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stdout[-2000:]
    assert read_times(table) == {
        key("test_pinned.py::test_warm"): 653.60,
        key("test_pinned.py::test_skipped"): 42,
    }


def test_a_file_dealt_by_test_runs_each_of_its_tests_in_exactly_one_part(tmp_path):
    """The job `select` deals a file whose tests sum past a part's share out by test, and hands
    each part its files and the word `--shard-tests=<keys>`: pytest, given each part's words as
    `make test TESTS=` gives them, runs every test of the files once, and a part with the file
    whole beside it runs all of that one."""
    spec = importlib.util.spec_from_file_location("select_tests", REPO / "scripts/select_tests.py")
    select_tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(select_tests)
    (big,) = listed([SOME[0]])
    (small,) = listed([SOME[1]])
    times = {key(test): 10 for test in big}
    words, _ = select_tests.dealt(big + small, times, 3)
    assert sum(SOME[0] in part for part in words) == 3
    assert any(word.startswith("--shard-tests=") for part in words for word in part)
    ran = listed(*words)
    together = Counter(test for part in ran for test in part)
    assert [test for test, times in together.items() if times > 1] == []
    assert sorted(together) == sorted(big + small)


def test_the_table_is_each_test_s_median_over_ci_s_junit_reports(tmp_path):
    """`python -m testing.shard` writes the table from the junit reports of the full runs, each
    run its parts' reports: a test's row is its median over the runs that ran it, so one cold
    run of the merge flow's TLC test among warm ones leaves it at its warm time. A test that
    took under `FLOOR` has no row, and one no collected node id matches is counted."""
    tests = ["a/test_x.py::test_one", "a/test_x.py::TestB::test_two[a b's]", FLOW]
    took = [[0.5, 3, 900], [0.7, 4, 2], [0.6, 5, 3]]
    runs = []
    for n, row in enumerate(took):
        report = tmp_path / f"{n}.xml"
        report.write_text(
            "<testsuites><testsuite>"
            + "".join(
                f'<testcase classname={quoteattr(c)} name={quoteattr(m)} time="{t}"/>'
                for (c, m), t in zip(map(mangled, tests), row, strict=True)
            )
            + '<testcase classname="gone" name="test_gone" time="1"/>'
            + '<testcase classname="a.test_x" name="test_quick" time="0.01"/>'
            + "</testsuite></testsuites>"
        )
        runs.append([report])
    table, read, unknown = recorded(runs, [*tests, "a/test_x.py::test_quick"])
    (tmp_path / "t.tsv").write_text(table)
    times = read_times(tmp_path / "t.tsv")
    assert [seconds(times, test) for test in tests] == [0.6, 4, 3]
    assert len(times) == 3
    assert (read, unknown) == (15, 3)


def ended(run):
    """The exit status and the output of a pytest started with its output piped."""
    out, _ = run.communicate(timeout=100)
    return run.returncode, out


def parts(*selected):
    """Each of the parts of this selection, run as CI's jobs run them: on xdist's workers,
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
