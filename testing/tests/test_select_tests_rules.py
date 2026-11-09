"""The rules of `scripts/select_tests.py` held against this repo's own tree: one row of a table
for each rule, and the map's tests that read the repo's map, the files git tracks, and the
imports the tests make, then the tests that a change to one of this repo's own files must
select, on a pull request and on a Mac. The mutant of the selector for each rule, which must
fail its row, is in test_select_tests_mutants.py, which runs where a change reaches the selector
or this table.

Each of these runs the selector on today's tree, whose first run in a process takes seconds, so
they sit apart from test_select_tests.py, whose tests run the selector in small repos of their
own."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_home_thread import named
from testing.paths import REPO, skills, sources

SCRIPT = REPO / "scripts" / "select_tests.py"
SPEC = importlib.util.spec_from_file_location("select_tests", SCRIPT)
select = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(select)


OWNED = "scripts/".split()
ALSO = ("install.sh",)

VIEW = "features/jbus/tests/view/"

FLOW_SPEC = "features/jmerge/tests/test_flow_spec.py"

STATECHART_RUNS = (
    "features/skill-library/tests/test_statechart_runs.py",
    "features/skill-library/tests/test_statechart_specs.py",
)

MODEL_CHECKS = (FLOW_SPEC, *STATECHART_RUNS)

TABLE = [
    ("all", ["pyproject.toml"], {"all"}, ()),
    ("all", ["uv.lock"], {"all"}, ()),
    ("all", ["conftest.py"], {"all"}, ()),
    (
        "fixture-asked",
        ["testing/jstack_fixtures.py"],
        {"features/architect/tests/test_architect_skill.py"},
        (),
    ),
    ("imports", ["testing/paths.py"], {"testing/tests/test_select_tests.py"}, ()),
    (
        "imports",
        ["features/jmerge/src/jmerge/reuse.py"],
        {"features/jmerge/tests/test_jmerge_stacked.py"},
        (),
    ),
    (
        "imports",
        ["features/crew/tests/test_crew_needs_go.py"],
        {"features/crew/tests/test_crew_result_template.py"},
        (),
    ),
    (
        "itself",
        ["features/jbus/tests/test_jbus_wakes.py"],
        {"features/jbus/tests/test_jbus_wakes.py"},
        (),
    ),
    (
        "chain",
        ["features/crew/tests/crew_helpers.py"],
        {"features/expert/tests/test_expert_skill.py"},
        (),
    ),
    (
        "process",
        ["features/jgauge/src/jgauge/sizes.py"],
        {"features/jbus/tests/test_needs_replay.py"},
        (),
    ),
    (
        "by-name",
        ["features/jbriefs/src/jbriefs/asks.py"],
        {"features/jbus/tests/test_jbus_bind.py"},
        (),
    ),
    (
        "fixture-asked",
        ["features/jmerge/tests/test_sweep.py"],
        {"features/home/tests/test_quiet_home.py"},
        (),
    ),
    (
        "conftest",
        [f"{VIEW}conftest.py"],
        {f"{VIEW}test_view_answer.py", f"{VIEW}test_view_days.py"},
        (),
    ),
    (
        "test-spelled",
        ["features/jbus/tests/relay_leaves.py"],
        {"features/jbus/tests/test_jbus_relay.py"},
        (),
    ),
    ("beside", ["features/jbus/src/jbus/view/page.html"], {f"{VIEW}test_view_server.py"}, ()),
    (
        "spelled",
        ["features/evals/evals/skill-cut/cases/steps.json"],
        {"features/evals/tests/test_eval_skill_cut.py"},
        (),
    ),
    (
        "skill-index",
        ["features/benchmark-checklist/SKILL.md"],
        {"features/show-me-your-work/tests/test_show_me_your_work.py"},
        (),
    ),
    ("included", ["features/crew/a-gate.md"], {"features/jbus/tests/test_gates.py"}, ()),
    ("included", ["features/expert/an-ask.md"], {"features/expert/tests/test_expert_skill.py"}, ()),
    (
        "skill-index",
        ["features/home/skills/home/SKILL.md"],
        {"features/home/tests/test_quiet_turns.py"},
        (),
    ),
    (
        "fixture",
        ["features/jbriefs/tests/fixtures/findings/two-reviewers.md"],
        {"features/jbriefs/tests/test_jbriefs_findings.py"},
        (),
    ),
    (
        "fixture",
        [
            "features/jgauge/tests/fixtures/projects/-tmp-plain-thread/11111111-1111-4111-8111-111111111111.jsonl"
        ],
        {"features/jgauge/tests/test_session.py"},
        (),
    ),
    (
        "read-set",
        ["features/evals/benchmark/common.sh"],
        {"features/evals/tests/test_benchmark.py"},
        (),
    ),
    (
        "read-set",
        ["features/home/feature.json"],
        {"features/repo-guards/tests/test_no_notes.py"},
        (),
    ),
    (
        "tests-line",
        ["features/scout/templates/scout-report.md"],
        {"features/jbus/tests/test_jbus_scout.py"},
        (),
    ),
    ("page", ["features/grilling/verify.md"], {"features/grilling/tests/test_grilling.py"}, ()),
    ("scripts", ["scripts/jtrees/crawl.py"], {"testing/tests/test_jtrees.py"}, ()),
    (
        "paths",
        ["features/skill-library/skills/statechart/scripts/statechart/lib.py"],
        {"features/skill-library/tests/test_statechart_charts.py"},
        (),
    ),
    ("models", ["features/jmerge/spec/FlowToday.tla"], {FLOW_SPEC}, STATECHART_RUNS),
    (
        "models",
        ["features/skill-library/skills/statechart/scripts/statechart/lib.py"],
        {FLOW_SPEC, *STATECHART_RUNS},
        (),
    ),
    ("models", ["features/jbus/src/jbus/watch.py"], {FLOW_SPEC}, STATECHART_RUNS),
    ("models-only", ["features/jgauge/docs/limits.md"], set(), MODEL_CHECKS),
    ("models-only", ["features/jbus/src/jbus/boxes.py"], set(), MODEL_CHECKS),
    ("models-only", ["features/jmerge/verify.md"], set(), MODEL_CHECKS),
    ("cross-cutting", ["README.md"], set(select.cross_cutting()), ()),
    (
        "browser",
        ["features/crew/SKILL.md"],
        {"features/crew/tests/test_crew_check_command.py"},
        (f"{VIEW}page/test_view_page_browser.py",),
    ),
]

FAILED = ("README.md", "features/jgauge/tests/test_session.py")


def fails(rule, changed, needed, absent, tests, why):
    """Why the selection `tests` for one row of the table is wrong, or `None`."""
    if needed == {"all"}:
        return None if tests == ["all"] else f"{rule}: {changed} selects some, not all"
    if tests == ["all"]:
        return f"{rule}: {changed} selects all, forced by {why['forced-by']}"
    missing, wrong = needed - set(tests), set(absent) & set(tests)
    return (
        f"{rule}: {changed} misses {sorted(missing)}, selects {sorted(wrong)}"
        if missing or wrong
        else None
    )


def failing(picked):
    """The rows of the table, and the row of the failed-on-main tests, that a selector gets
    wrong. `picked` is its `(tests, why)` for each row in order, then for `FAILED`."""
    *rows, (tests, _) = picked
    wrong = [fails(*row, *one) for row, one in zip(TABLE, rows, strict=True)]
    changed, failed = FAILED
    if failed not in tests:
        wrong.append(f"failed-on-main: {changed} with {failed} red on main leaves it out")
    return [one for one in wrong if one]


def asked():
    """The table's questions to a selector: each row's changed paths, then `FAILED`'s."""
    changed, failed = FAILED
    return [[row[1], []] for row in TABLE] + [[[changed], [failed]]]


def test_each_kind_of_change_selects_the_tests_that_read_it():
    """One row for each rule of the selector, on today's tree: a changed path, the test files its
    rule must select, and the ones the selection must leave out. Each row names a test that
    the row's rule selects, so a test the rule stops selecting shows here. A row that names a
    cross-cutting test would pass whatever its rule did, since every change runs those."""
    cross = set(select.cross_cutting())
    assert [row for row in TABLE if row[0] != "cross-cutting" and row[2] & cross] == []
    assert failing([select.selection(*one) for one in asked()]) == []


SELECTOR_TESTS = "testing/tests/test_select_tests.py"


@pytest.mark.parametrize(
    ("changed", "runs"),
    [
        ([], False),
        (["features/grilling/SKILL.md"], False),
        (["features/jbus/src/jbus/wake.py"], False),
        (["features/jmerge/src/jmerge/ready.py"], True),
        (["features/jsettings/src/jsettings/__init__.py"], True),
    ],
    ids=[
        "no change",
        "a skill",
        "a package it does not copy",
        "jmerge's reader",
        "a copied package",
    ],
)
def test_the_selectors_own_tests_run_only_where_a_change_reaches_the_selector(changed, runs):
    """`test_select_tests.py` takes minutes and is on no `Cross-cutting:` list: a change runs it
    where it reaches the selector, its script or a package its small repos copy, and not else."""
    tests, _ = select.selection(changed)

    assert (tests == ["all"] or SELECTOR_TESTS in tests) == runs


WORKFLOW_TESTS = "testing/tests/test_workflows.py"


@pytest.mark.parametrize(
    ("changed", "runs"),
    [
        ([], False),
        (["features/grilling/SKILL.md"], False),
        (["features/jdrift/src/jdrift/__init__.py"], False),
        ([".github/workflows/added.yml"], True),
        ([".github/CODEOWNERS"], True),
        (["features/jmerge/spec/Added.tla"], True),
    ],
    ids=[
        "no change",
        "a skill",
        "a module no workflow test runs",
        "a new workflow",
        "a file under .github",
        "a spec the tlc cache hashes",
    ],
)
def test_the_workflow_tests_run_only_where_a_change_reaches_what_they_read(changed, runs):
    """`test_workflows.py` takes minutes and is on no `Cross-cutting:` list: a change runs it
    where it reaches a file under `.github/`, a file the TLC cache's key hashes, or a path it
    spells or imports, and not else."""
    tests, _ = select.selection(changed)

    assert (tests == ["all"] or WORKFLOW_TESTS in tests) == runs


def test_every_python_file_under_features_selects_a_test():
    """A change to a module runs a test of its own, beside the cross-cutting tests and the
    catch-all, which every change runs: a test file selects itself, and any other file a test
    that imports it, names it or reads it, or `all`."""
    lone = [
        path
        for path in sorted(select.tracked())
        if path.startswith("features/") and path.endswith(".py")
        if not set(select.ruled([path], cross=False)[0])
        - (set() if select.TEST.fullmatch(path) else {path})
    ]
    assert lone == []


def tracked(*paths):
    """The files git has or would add under `paths`."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *paths],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return listed.stdout.splitlines()


def test_every_path_is_owned_by_a_feature():
    owned = [paths for paths, _ in select.features().values()]

    assert [
        path
        for path in tracked(*OWNED, *ALSO)
        if not any(select.owns(patterns, path) for patterns in owned)
    ] == []


def test_every_root_the_ownership_test_reads_holds_a_file():
    """Whoever moves the last file out of a root folder must also drop the folder here.
    Otherwise the ownership test reads a folder that is gone and names it as covered."""
    assert [root for root in (*OWNED, *ALSO) if not tracked(root)] == []


def test_every_test_file_the_map_names_is_there():
    named = [test for _, tests in select.features().values() for test in tests]

    missing = [test for test in [*named, *select.cross_cutting()] if not tracked(test)]
    assert missing == []


def test_every_feature_has_both_lines_and_patterns_jmerge_can_read():
    for name, page in select.pages().items():
        lines = (REPO / page).read_text().splitlines()
        for label in ("Paths:", "Tests:"):
            assert any(line.startswith(label) for line in lines), f"{name} has no {label}"
        paths = select.features()[name][0]
        assert paths, f"{name} has no Paths"
        assert select.ready().patterns_of("\n".join(paths)) == tuple(paths)


def test_a_features_tests_line_names_only_what_no_import_and_no_name_selects(monkeypatch):
    """The tests of a feature come from what they import and what they name. A `Tests:` entry names
    a test that reads a feature's files without naming them in a string, such as with a glob over a
    tree of files. If, with the entry gone, a change to each path the feature owns still selects
    that test, the entry is redundant. An import or a name that selects the test for one of those
    paths alone does not make it so: the skill tests name their skill, and read files beside it."""
    features, pages, shown = select.features(), select.pages(), []
    for name, (owned, listed_tests) in features.items():
        mine = [one for one, path in select.modules().items() if owns_module(owned, path)]
        seen = select.test_files(select.importers(mine))
        for path in tracked():
            if select.owns(owned, path) and path not in select.modules().values():
                seen |= select.readers(path)
        for test in set(listed_tests) & seen:
            rest = {**features, name: (owned, [one for one in listed_tests if one != test])}
            monkeypatch.setattr(select, "features", lambda rest=rest: rest)
            ruled = [
                select.ruled([path])[0]
                for path in select.tracked()
                if select.owns(owned, path) and path != pages[name]
            ]
            if all(tests == ["all"] or test in tests for tests in ruled):
                shown.append(f"{name} lists {test}")
    assert shown == []


def owns_module(owned, path):
    return path.startswith("src/") and select.owns(owned, path)


def test_every_test_file_is_run_by_a_change_to_another_path():
    """A changed test file selects itself, so that change does not count. A test that no change
    to any other path selects is owned by no rule, and a change that breaks it would merge with
    it unrun. The selector's catch-all runs each such test on every change, so none is left."""
    run = set()
    for path in sorted(select.tracked()):
        tests, _ = select.selection([path])
        if tests != ["all"]:
            run |= set(tests) - {path}
    left = [
        test
        for test in tracked("testing/tests/", "features/")
        if select.TEST.fullmatch(test) and test not in run and not select.opens_browser(test)
    ]
    assert left == []


ORACLE = """
import builtins, importlib, json, sys
from pathlib import Path

at = sys.argv.index("--")
tests, folders = sys.argv[1:at], sys.argv[at + 1 :]
sys.path[:0] = [*tests, *folders]
seen, named, failed = set(), set(), []
real = builtins.__import__


def hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = real(name, globals, locals, fromlist, level)
    importer = (globals or {}).get("__name__")
    if importer and not level:
        seen.add((importer, name))
        seen.update((importer, f"{name}.{one}") for one in fromlist or ())
    return module


def by_name(name, package=None):
    named.add(name)
    return load(name, package)


builtins.__import__ = hook
load, importlib.import_module = importlib.import_module, by_name
for folder, path in sorted((one, path) for one in tests for path in Path(one).rglob("*.py")):
    name = ".".join(path.relative_to(folder).with_suffix("").parts).removesuffix(".__init__")
    if name.startswith("fixtures."):
        continue
    try:
        load(name)
    except BaseException as error:
        failed.append(f"{name}: {error!r}")
files = {
    name: module.__file__
    for name, module in sorted(sys.modules.items())
    if getattr(module, "__file__", None)
}
print(json.dumps({"seen": sorted(seen), "named": sorted(named), "failed": failed, "files": files}))
"""


def test_the_import_graph_has_every_import_that_importing_the_tests_makes():
    ran = subprocess.run(
        [
            sys.executable,
            "-c",
            ORACLE,
            str(REPO / "testing" / "tests"),
            *map(str, sorted(REPO.glob("features/*/tests"))),
            "--",
            *map(str, sources()),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    found = json.loads(ran.stdout.splitlines()[-1])
    graph = select.edges()
    missing = [
        f"{importer} imports {name}"
        for importer, name in found["seen"]
        if importer in graph
        for reached in sorted(select.parents(name) & select.modules().keys())
        if reached != importer and reached not in graph[importer]
    ]
    imported = {name for _, name in found["seen"]} | set(found["named"])
    unread = [
        f"{name} from {Path(file).relative_to(REPO)}"
        for name, file in found["files"].items()
        if name in imported
        and Path(file).is_relative_to(REPO)
        and not Path(file).is_relative_to(REPO / ".venv")
        and select.modules().get(name.removesuffix(".__init__"))
        != Path(file).relative_to(REPO).as_posix()
    ]
    assert (missing, found["failed"], unread) == ([], [], [])


def test_a_change_to_the_home_skill_selects_the_tests_that_reach_it_and_not_most_of_them():
    """210 tests import `test_home_thread`, whose helpers name the home, crew, handoff and scout
    skills. Those that take no helper that reads the home skill do not run its blocks: once,
    their imports alone made a change to it select 315 of 400 test files.
    `test_crew_reviewing.py` takes `blocks` from it and reads the crew skill alone."""
    home, _ = select.selection(["features/home/skills/home/SKILL.md"])
    crew, _ = select.selection(["features/crew/SKILL.md"])

    assert "features/crew/tests/test_crew_reviewing.py" in set(crew) - set(home)
    assert len(home) < len(select.collected()) * 2 / 3


def test_the_selector_finds_the_skills_the_index_finds():
    assert select.skills() == {
        name: folder.relative_to(REPO).as_posix() for name, folder in skills().items()
    }


@pytest.mark.parametrize(
    "path, reader",
    [
        ("features/home/skills/home/SKILL.md", "features/home/tests/test_home_start.py"),
        ("features/home/skills/handoff/SKILL.md", "features/home/tests/test_handoff_mail.py"),
        ("features/ketchup/SKILL.md", "features/home/tests/test_home_needs.py"),
    ],
)
def test_a_change_to_a_skill_selects_the_tests_that_run_its_shell_blocks(path, reader):
    """Each test runs a block of the skill that `test_home_thread` takes from
    `skills()[name] / "SKILL.md"`, with the files that skill folds in. A break of the home skill's
    turn-end block once failed `test_quiet_turns.py`, and the selection ran without it."""
    tests, _ = select.selection([path])

    assert reader in tests


def test_the_selector_follows_the_includes_the_tests_fold_in():
    """`as_read` folds in each file beside a skill that a line of it says to read now. The
    selector must find the same files, or a change to one runs none of the tests that read it."""
    folded = {
        (path, found.relative_to(REPO).as_posix())
        for path in select.tracked()
        if path.endswith(".md") and (REPO / path).is_file()
        for found in named(REPO / path)
    }
    found = {(includer, path) for path, by in select.included().items() for includer in by}

    assert folded
    assert found == folded


@pytest.mark.parametrize(
    ("changed", "reader"),
    [
        (
            "features/lessons/skills/reflect/references/synthesizer.md",
            "features/lessons/tests/test_lessons.py",
        ),
        ("features/crew/playbooks/bug-fix.md", "features/tdd/tests/test_tdd_skill.py"),
    ],
    ids=["a skill's own file", "a playbook a skill names"],
)
def test_a_change_to_a_file_a_test_of_this_repo_globs_selects_that_test(changed, reader):
    """`test_lessons.py` declares the folders of the lessons skills in its `READ_SET`, and a
    change to a file in one of them selects it. `test_tdd_skill.py` checks each playbook the tdd
    skill names, through `skill_blocks`. Neither feature lists the test, and no test spells the
    file."""
    tests, _ = select.selection([changed])

    assert reader in tests


@pytest.mark.parametrize(
    ("path", "readers"),
    [
        (
            "scripts/select_tests.py",
            {
                "testing/tests/test_select_tests.py",
                "testing/tests/test_select_tests_mutants.py",
                "testing/tests/test_select_tests_rules.py",
            },
        ),
        ("Makefile", {"features/repo-standard/tests/test_check_workflow.py"}),
        (
            ".github/workflows/check.yml",
            {"testing/tests/test_workflows.py", "testing/tests/test_shards.py"},
        ),
        ("testing/shard.py", {"testing/tests/test_shards.py"}),
    ],
    ids=["the selector", "the Makefile", "the check", "a plugin of testing"],
)
def test_in_this_repo_a_change_to_what_picks_and_runs_the_tests_selects_the_tests_that_read_it(
    path, readers
):
    """Only the dependencies and the root conftest.py force the whole suite on a pull request:
    the selector, the Makefile, the check and the plugins reach the tests that import or name
    them, and the whole suite runs on main, nightly and before a release."""
    tests, why = select.selection([path])

    assert tests != ["all"], why
    assert readers <= set(tests)


@pytest.mark.parametrize("path", ["pyproject.toml", "uv.lock", "conftest.py"])
def test_in_this_repo_a_change_to_what_every_run_loads_selects_all(path):
    assert select.selection([path]) == (["all"], {"forced-by": path})


def test_a_change_to_the_view_selects_its_tests_but_not_the_browser_drive_of_its_page():
    selected, _ = select.selection(["features/jbus/src/jbus/view/page.html"])

    assert "features/jbus/tests/view/test_view_server.py" in selected
    assert not [one for one in selected if one.startswith("features/jbus/tests/view/page/")]
    assert set(select.cross_cutting()) <= set(selected)
    assert "features/jroles/tests/test_jroles_mirror.py" not in selected


@pytest.mark.parametrize("panel", ["bus", "checks", "slow", "you"])
def test_a_change_to_a_panel_selects_the_tests_of_the_view_under_tests_view(panel):
    selected, _ = select.selection([f"features/jbus/src/jbus/view/panels/{panel}/panel.py"])

    assert f"features/jbus/tests/view/test_view_{panel}.py" in selected
    assert not [one for one in selected if one.startswith("features/jbus/tests/view/page/")]


def test_a_change_to_the_crawl_of_jtrees_selects_the_tests_that_import_it():
    selected, why = select.selection(["scripts/jtrees/crawl.py"])

    assert {
        "testing/tests/test_jtrees.py",
        "testing/tests/test_jtrees_one_feature.py",
        "features/jinstall/tests/test_layout.py",
    } <= set(selected)
    assert why["imports"]


STATECHART_TESTS = {
    "features/home/tests/test_home_tree_spec.py",
    "features/skill-library/tests/test_statechart_charts.py",
    "features/skill-library/tests/test_statechart_runs.py",
    "features/skill-library/tests/test_statechart_specs.py",
    "features/skill-library/tests/test_statechart_tlc_bounds.py",
    "features/skill-library/tests/test_statechart_tlc_cache.py",
}


def test_a_change_to_a_statechart_script_selects_the_tests_that_put_its_folder_on_the_path():
    script = "features/skill-library/skills/statechart/scripts/statechart/lib.py"

    for selected, why in [select.selection([script]), select.ruled([script], cross=False)]:
        assert set(selected) >= STATECHART_TESTS
        assert set(why["imports"]) | set(why["models"]) >= STATECHART_TESTS


MERGED = {
    "#330": (
        [
            "features/jbus/docs/jbus/the-sign-in.md",
            "features/jbus/docs/jbus/when-jbus-fails.md",
            "features/jbus/src/jbus/alert.py",
            "features/jbus/src/jbus/signin.py",
            "features/jbus/src/jbus/wake.py",
            "features/jbus/tests/test_jbus_wake_home.py",
        ],
        "features/repo-guards/tests/test_module_size.py",
    ),
    "#337": (
        [
            "features/jbus/tests/fixtures/jbus-view/probe.js",
            "features/jbus/tests/view/page/browser.py",
            "features/jbus/tests/view/page/test_view_page_budgets.py",
        ],
        "features/jbus/tests/view/test_view_sources.py",
    ),
}


@pytest.mark.parametrize(("changed", "broken"), MERGED.values(), ids=MERGED.keys())
def test_a_pull_request_selects_the_test_that_reads_the_whole_tree_its_change_broke(
    changed, broken
):
    """The paths each pull request changed. Its check ran neither test, and main went red after
    the merge: #330 pushed `jbus/wake.py` over the cap of lines, #337 put a URL in a view test."""
    tests, _ = select.selection(changed)

    assert broken in tests


MAC_LIST = "testing/macos-quick.txt"
CLI = "features/jmerge/src/jmerge/cli.py"


def mac_within(path, strict=False):
    """The tests of the macOS quick list a change to `path` in this repo reaches on a Mac."""
    entries = (REPO / MAC_LIST).read_text().split()
    return select.within(entries, [path], MAC_LIST, strict)


def test_strict_within_is_a_part_of_within_for_every_tracked_path():
    """A pull request's macos job selects with `--strict`, and the run on each merge commit with
    `--within` alone. Each test a pull request runs on a Mac is one its merge's run runs again,
    so no path reaches a Mac test on a pull request that its merge's run would leave out. Where
    `within` is `all`, the merge's run runs the whole list."""
    wider = []
    for path in sorted(select.tracked()):
        within, strict = mac_within(path), mac_within(path, strict=True)
        assert strict == ["all"] or within == ["all"] or set(strict) <= set(within), path
        wider += [path] if strict != within and strict != ["all"] else []
    assert wider, "strict narrows nothing"


@pytest.mark.parametrize(
    "path",
    ["features/crew/verify.md", "features/jbus/verify.md", "README.md", "features/crew/SKILL.md"],
    ids=["a feature's page", "jbus's page", "a doc a test names", "a skill tests read"],
)
def test_strict_within_reaches_no_mac_test_through_a_feature_or_a_name_of_code_off_darwin(path):
    """A feature's paths and its page reach its listed tests in `--within`, and a doc or skill
    reaches the tests that spell it. A change to neither runs differently on a Mac, so with
    `--strict` it reaches no Mac test, and the merge's run checks it on a Mac minutes later."""
    assert mac_within(path)
    assert mac_within(path, strict=True) == []


@pytest.mark.parametrize(
    ("path", "test"),
    [
        ("features/jbus/src/jbus/launchd.py", "features/jbus/tests/test_jbus_launchd.py"),
        (
            "features/jgauge/tests/test_machine_sizes.py",
            "features/jgauge/tests/test_machine_sizes.py",
        ),
    ],
    ids=["code that names Darwin", "a listed test"],
)
def test_strict_within_keeps_what_darwin_code_and_the_tests_reach(path, test):
    """An import or a name from code that names Darwin, or from the tests, reaches a Mac test
    with `--strict` as it does without it."""
    assert test in mac_within(path, strict=True)
    assert mac_within(path, strict=True) == mac_within(path)


@pytest.mark.parametrize("strict", [False, True], ids=["within", "strict"])
def test_within_is_all_only_for_what_changes_every_run(strict):
    """A Mac selection runs the whole list only for the dependencies and the root conftest.py,
    which change every run of the tests: the plugins, the Makefile, check.yml and this script
    reach the Mac tests that import or name them, a part of the whole list."""
    for path in ["pyproject.toml", "uv.lock", "conftest.py"]:
        assert mac_within(path, strict=strict) == ["all"], path
    for path in [
        "scripts/select_tests.py",
        "Makefile",
        ".github/workflows/check.yml",
        "testing/jstack_fixtures.py",
    ]:
        tests = mac_within(path, strict=strict)
        assert tests != ["all"] and set(tests) <= set(select.tracked()), path


@pytest.mark.parametrize("path", [MAC_LIST])
def test_strict_within_is_all_where_within_is(path):
    assert mac_within(path, strict=True) == mac_within(path) == ["all"]


def test_strict_darwin_reaches_the_importers_of_an_edit_inside_clis_darwin_branch():
    """In this repo, an edit to the function of jmerge's CLI that branches on Darwin reaches every
    listed test that imports the CLI, as the run on each merge commit does, and an edit away from
    it reaches none of them."""
    text = (REPO / CLI).read_text()
    branch = next(at for at, one in enumerate(text.splitlines(), 1) if "sys.platform ==" in one)
    entries = (REPO / MAC_LIST).read_text().split()

    def reached(line):
        edit = [({line}, text), ({line}, text)]
        return select.within(entries, [CLI], MAC_LIST, strict=True, edited={CLI: edit})

    assert reached(branch) == mac_within(CLI)
    assert len(reached(branch)) > 10
    assert reached(10) == []


TICK = "features/jbus/src/jbus/tick.py"


def test_on_a_pull_request_an_edit_deep_in_jbus_selects_its_own_tests_and_not_the_jbus_suite():
    """A pull request's check reaches through imports only the tests near a change: an edit to
    `tick.tick` selects the tests that import `jbus.tick` and those that import a module that
    calls `tick.tick`, with the tests near a module that reads every jbus module through
    `jbus.__path__`. The wide rule selects nearly every test of jbus, which reach `tick` through
    `jbus.cli` and the modules it imports, and main's full run still runs them."""
    text = (REPO / TICK).read_text()
    line = next(at for at, one in enumerate(text.splitlines(), 1) if one.startswith("def tick("))
    wide, _ = select.selection([TICK])
    near, why = select.selection([TICK], edited={TICK: [({line}, text), ({line}, text)]})

    suite = {one for one in wide if one.startswith("features/jbus/tests/")}
    assert {
        "features/jbus/tests/test_jbus_tick.py",
        "features/jbus/tests/test_work.py",
    } <= set(why["imports"])
    assert set(near) < set(wide)
    assert len(suite & set(near)) * 2 < len(suite)


def test_on_a_pull_request_an_edit_to_a_private_helper_reaches_the_tests_of_what_calls_it():
    """An edit to `tick._asks`, which `tick.tick` calls, selects through imports what an edit to
    `tick.tick` selects: a module that calls `tick.tick` carries the change on, as it does when
    the edit is in `tick.tick` itself."""
    text = (REPO / TICK).read_text()

    def near(start):
        line = next(at for at, one in enumerate(text.splitlines(), 1) if one.startswith(start))
        _, why = select.selection([TICK], edited={TICK: [({line}, text), ({line}, text)]})
        return set(why["imports"])

    assert near("def _asks(") == near("def tick(")
