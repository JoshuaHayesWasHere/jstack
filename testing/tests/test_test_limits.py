"""Each test has a bound of 120 s (`timeout` in pyproject.toml), and a test may set its own with
`pytest.mark.timeout`, on itself or for its module. A limit over LONG_LIMIT seconds is a choice
somebody made: each place that sets one is on LONG, with the reason, so a new long test is a
change to this list and not a number nobody reads. A place is a test function, named by its file
and its name with no parameters, or a module or class whose `pytestmark` sets it for each of its
tests. The list changes no limit: the limits are where the tests set them.

The test asks pytest itself, as the check's parts do: a pytest that collects the whole suite with
a small plugin that writes, for each test, its closest `timeout` mark and the node that set it."""

import json
import os
import subprocess
import sys

from testing.paths import REPO

LONG_LIMIT = 300

PLUGIN = """
import json
import os


def pytest_collection_modifyitems(items):
    found = {}
    for item in items:
        mark = next(item.iter_markers_with_node("timeout"), None)
        if mark is None:
            continue
        node, mark = mark
        if node is item:
            place = f"{item.nodeid.partition('::')[0]}::{item.originalname}"
        else:
            place = node.nodeid
        found[place] = mark.args[0] if mark.args else mark.kwargs["timeout"]
    with open(os.environ["LIMITS_OUT"], "w") as out:
        json.dump(found, out)
"""

BROWSER = (
    "opens a real browser, under `make check-browser` alone: browser.py's PATIENCE for the "
    "server, then LAUNCH and 5 s for each browse the module makes"
)
TLC = "model checks a spec with TLC, a Java run of minutes on a hosted runner"

LONG = {
    "features/crew/tests/test_crew_check_command.py::"
    "test_a_branch_that_adds_a_line_no_test_runs_fails_the_desk_check": (
        "runs the desk's whole check on a cloned repo, the new-lines guard and the tests it "
        "runs under coverage among it"
    ),
    "features/home/tests/test_home_tree_spec.py::test_the_run_says_what_it_should": TLC,
    "features/jbus/tests/test_main_red_spec.py::"
    "test_a_revert_held_by_its_opener_alone_is_opened_twice": TLC,
    "features/jbus/tests/test_main_red_spec.py::"
    "test_today_s_code_holds_every_rule_but_the_ones_it_breaks": (
        TLC + ", once with the rules the code breaks left out and once for each of those alone"
    ),
    **{
        f"features/jgauge/tests/test_test_slot_spec.py::{name}": TLC
        for name in (
            "test_a_dead_holder_whose_pid_is_taken_reads_as_running",
            "test_a_killed_test_slot_takes_its_command_with_it_today",
            "test_a_run_s_end_is_kept_for_jbus_to_tell_today",
            "test_each_of_today_s_faults_breaks_its_rule",
            "test_the_mode_that_passes_holds_every_rule",
            "test_today_s_code_loses_a_ledger_write",
        )
    },
    "features/jmerge/tests/test_pr_verdict_spec.py::test_the_run_says_what_it_should": TLC,
    "features/jmerge/tests/test_flow_spec.py::"
    "test_today_and_the_design_hold_their_rules_and_each_canary_breaks_its_own": (
        "every canary of the flow spec under TLC: about 650 s on a Linux runner and 1073 s on "
        "a macOS one (2026-11-05)"
    ),
    "features/repo-guards/tests/test_new_lines_run.py::"
    "test_every_line_this_branch_adds_to_a_feature_runs_in_a_test": (
        "runs the tests that name each module the branch changed under coverage, once in "
        "`check` after the parts"
    ),
    "features/skill-library/tests/test_statechart_runs.py::"
    "test_a_run_of_the_worked_example_leaves_no_work_folder_unless_keep_work_keeps_it": (
        "two from-spec runs of the worked example, each a TLC run"
    ),
    "features/skill-library/tests/test_statechart_runs.py::"
    "test_runs_of_two_specs_that_overlap_on_one_output_folder_all_finish_with_one_runs_files": (
        "from-spec runs of two specs side by side, one of them slowed on purpose, each a TLC run"
    ),
    "features/skill-library/tests/test_statechart_runs.py::"
    "test_the_output_folder_model_keeps_every_rule_and_breaks_one_without_each_guard": (
        "the output folder model under TLC whole and once without each guard: 75 s in part 8 "
        "of #1691's check (job 130776916641)"
    ),
    "features/skill-library/tests/test_statechart_specs.py::"
    "test_from_spec_against_compares_the_code_with_the_spec_and_expect_broken_sets_the_exit": (
        "from-spec --against runs TLC on two specs and on their common part"
    ),
    **{
        f"features/jbus/tests/view/page/test_view_page_{name}.py": BROWSER
        for name in (
            "banner",
            "browser",
            "budgets",
            "days",
            "gates",
            "glance",
            "homes",
            "inbox",
            "keys",
            "look",
            "map",
            "matrix_homes",
            "milestones",
            "no_strip",
            "one_stage",
            "overview",
            "panels",
            "pipeline",
            "queue",
            "routes",
            "shot",
            "since",
            "slow",
            "task",
            "throughput",
            "triage",
            "usage",
            "walk",
        )
    },
}


def limits(tmp_path, *args):
    """Each place that sets its tests' own limit, and the seconds, as pytest collects them from
    the repo's config, with `args` passed to it."""
    (tmp_path / "limits_plugin.py").write_text(PLUGIN)
    out = tmp_path / "limits.json"
    path = os.pathsep.join(filter(None, [str(tmp_path), os.environ.get("PYTHONPATH")]))
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
        + ["-p", "limits_plugin", *args],
        cwd=REPO,
        env=os.environ | {"PYTHONPATH": path, "LIMITS_OUT": str(out)},
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stdout[-4000:] + ran.stderr[-4000:]
    return json.loads(out.read_text())


def unlisted(found, listed):
    """Each place over LONG_LIMIT that `listed` gives no reason for, with its seconds."""
    return {
        place: seconds
        for place, seconds in found.items()
        if seconds > LONG_LIMIT and not listed.get(place, "").strip()
    }


def test_a_test_with_its_own_limit_over_300_s_fails_until_the_list_gives_its_reason(tmp_path):
    """A test of a module made here, which sets 301 s on itself, and a module that sets 900 s for
    its tests, are read from pytest's collection; 300 s is not over the line."""
    made = tmp_path / "made"
    made.mkdir()
    (made / "test_made.py").write_text(
        "import pytest\n\n\n@pytest.mark.timeout(301)\n@pytest.mark.parametrize('n', [1, 2])\n"
        "def test_long(n):\n    pass\n\n\n@pytest.mark.timeout(300)\ndef test_at_the_line():\n"
        "    pass\n"
    )
    (made / "test_module.py").write_text(
        "import pytest\n\npytestmark = pytest.mark.timeout(900)\n\n\ndef test_one():\n    pass\n"
    )
    found = limits(tmp_path, "--rootdir", str(made), "-c", os.devnull, str(made))
    assert found == {
        "test_made.py::test_long": 301,
        "test_made.py::test_at_the_line": 300,
        "test_module.py": 900,
    }
    assert unlisted(found, {}) == {
        "test_made.py::test_long": 301,
        "test_module.py": 900,
    }
    assert unlisted(found, {"test_module.py": " "}) == {
        "test_made.py::test_long": 301,
        "test_module.py": 900,
    }
    reasons = {"test_made.py::test_long": "why", "test_module.py": "why"}
    assert unlisted(found, reasons) == {}


def test_every_test_of_the_suite_with_its_own_limit_over_300_s_is_on_the_list(tmp_path):
    """Each place of the suite over LONG_LIMIT is on LONG with its reason, and each place on LONG
    is one that still sets a limit over it, so the list says what the suite does."""
    found = limits(tmp_path)
    assert unlisted(found, LONG) == {}
    assert [place for place in LONG if found.get(place, 0) <= LONG_LIMIT] == []
