"""The cases of the workflows' tests that run a shell a Mac runs: on `testing/macos-quick.txt`,
so the `macos-part` jobs run them on macOS. They run the steps of the `macos-part` jobs and of
`macos-nightly`, which run on `macos-15` under its bash 3.2 and its system `python3`, and the
`make release` targets a desk runs, on a Mac under its make 3.81 and its BSD tools. Every other
case of the workflows, the `macos-select` job's selection among them, reads a workflow or runs a
step of `ubuntu-24.04`, and is in `test_workflows.py`, which Linux runs and the Mac does not.

The handed tests step's case takes its input from a real selection, `merged`, so the selection
runs there as its setup: what the case tests is the step a Mac runs."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from test_workflows import (
    DARWIN_SOURCE,
    MAC,
    NIGHTLY,
    OUTCOMES,
    REACHED,
    URL,
    marker,
    merged,
    run,
    steps,
    summary_step,
    worked,
)
from testing.paths import REPO

__all__ = ["merged"]


def test_a_macos_part_runs_its_share_of_the_reached_tests_on_three_workers_into_its_report(
    tmp_path,
):
    """The step runs pytest itself and not `make check`: this runs its shell against a `uv` that
    writes down what it was given. pytest reads the arguments of `@<file>` from that file, one a
    line, so the paths the selection step wrote there are the tests the parts run, and
    `--shard K/N` keeps the part's share of them (testing/shard.py)."""
    found, _ = steps(MAC.read_text(), "macos-part")
    (suite,) = [step for step in found if step.get("id") == "suite"]
    (listed,) = [step for step in found if step.get("name") == "failed tests"]
    bin, said = tmp_path / "bin", tmp_path / "said"
    bin.mkdir()
    (bin / "uv").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > {said}\n')
    (bin / "uv").chmod(0o755)
    subprocess.run(
        ["bash", "-e", "-c", suite["run"]],
        cwd=REPO,
        env={"PATH": f"{bin}:/usr/bin:/bin", "RUNNER_TEMP": str(tmp_path), "PART": "2/3"},
        check=True,
    )
    assert suite["env"] == {"PART": "${{ matrix.part }}/${{ strategy.job-total }}"}
    given = said.read_text().splitlines()
    assert given[:2] == ["run", "pytest"]
    assert given[given.index("-n") + 1] == "3"
    assert given[given.index("--shard") + 1] == "2/3"
    report = listed["env"]["JUNIT"].replace("${{ runner.temp }}", str(tmp_path))
    assert f"--junitxml={report}" in given
    (read,) = [arg for arg in given if arg.startswith("@")]
    assert read == f"@{tmp_path}/{REACHED}"


@pytest.mark.parametrize("result", ["success", "failure", "cancelled"])
def test_the_macos_job_writes_the_tests_handed_on_for_pytest_and_fails_on_a_failed_selection(
    merged, tmp_path, result
):
    """The `macos` job's first step writes the tests `macos-select` handed on, as the runner
    gives the output, to the file pytest reads, the same lines the selection wrote. Where the
    selection did not succeed, or handed on nothing, the step fails the job, and so the
    required check."""
    reached, _, handed = merged(DARWIN_SOURCE)
    (step,) = [
        one for one in steps(MAC.read_text(), "macos-part")[0] if one.get("name") == "handed tests"
    ]
    assert step["env"] == {
        "SELECTED": "${{ needs.macos-select.result }}",
        "TESTS": "${{ needs.macos-select.outputs.tests }}",
    }
    for tests in (handed["tests"], ""):
        (tmp_path / REACHED).unlink(missing_ok=True)
        ran = subprocess.run(
            ["bash", "-e", "-c", summary_step("handed tests", MAC)],
            env={"PATH": "/usr/bin:/bin", "RUNNER_TEMP": str(tmp_path)}
            | {"SELECTED": result, "TESTS": tests},
            capture_output=True,
            text=True,
        )
        if result == "success" and tests:
            assert ran.returncode == 0
            assert (tmp_path / REACHED).read_text().splitlines() == reached
        else:
            assert ran.returncode == 1
            assert ran.stdout == f"::error::macos-select ended {result} and handed on no test\n"
            assert not (tmp_path / REACHED).exists()


FAILED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4" time="9.0">
<testcase classname="features.jgauge.tests.test_room" name="test_go" time="1.0" />
<testcase classname="features.jgauge.tests.test_room" name="test_load[idle]" time="1.0">
<failure message="no /proc/loadavg" /></testcase>
<testcase classname="features.crew.tests.test_check.TestSetsid" name="test_starts" time="1.0">
<error message="setsid: command not found" /></testcase>
<testcase classname="features.jbus.tests.test_view" name="test_skipped" time="0.0">
<skipped message="linux only" /></testcase>
</testsuite></testsuites>
"""


def test_the_macos_job_lists_each_failed_test_in_its_summary_and_warns_with_the_count(tmp_path):
    found, _ = steps(MAC.read_text(), "macos-part")
    (listed,) = [step for step in found if step.get("name") == "failed tests"]
    assert found.index(listed) > [step.get("id") for step in found].index("suite")
    for outcome in OUTCOMES:
        ran = {"steps.suite.outcome": outcome}
        assert worked(listed["if"], {"!cancelled()": True} | ran) is (outcome != "skipped")
        assert worked(listed["if"], {"!cancelled()": False} | ran) is False
    assert listed["env"] == {
        "JUNIT": "${{ runner.temp }}/junit.xml",
        "SUITE": "${{ steps.suite.outcome }}",
    }

    def run(junit):
        out = tmp_path / "summary"
        out.write_text("")
        ran = subprocess.run(
            ["bash", "-e", "-c", summary_step("failed tests", MAC)],
            env={"PATH": "/usr/bin:/bin", "JUNIT": str(junit), "SUITE": "failure"}
            | {"GITHUB_STEP_SUMMARY": str(out)},
            capture_output=True,
            text=True,
            check=True,
        )
        return ran.stdout, out.read_text()

    junit = tmp_path / "junit.xml"
    junit.write_text(FAILED)
    assert run(junit) == (
        "::warning::macOS: 2 tests failed, the suite step ended failure\n",
        "macOS: 2 tests failed, the suite step ended failure\n"
        "- `features/jgauge/tests/test_room.py::test_load[idle]`\n"
        "- `features/crew/tests/test_check.py::TestSetsid::test_starts`\n",
    )
    assert run(tmp_path / "gone") == (
        "::warning::macOS: no test report, the suite step ended failure\n",
        "macOS: no test report, the suite step ended failure\n",
    )


def test_the_macos_nightly_names_each_failed_test_in_its_log_and_summary_after_any_suite(tmp_path):
    """jbus reads the failed tests of a red run from its log's `FAILED <test>` lines, so the step
    prints one for each failed test of the report, also when the suite stopped at its cap and
    pytest printed no summary of its own."""
    found, _ = steps(NIGHTLY.read_text(), "macos")
    (listed,) = [step for step in found if step.get("name") == "failed tests"]
    assert (
        worked(listed["if"], {"!cancelled()": True}),
        worked(listed["if"], {"!cancelled()": False}),
    ) == (True, False)
    assert listed["env"]["SUITE"] == "${{ steps.suite.outcome }}"

    def run(junit):
        out = tmp_path / "summary"
        out.write_text("")
        ran = subprocess.run(
            ["bash", "-e", "-c", summary_step("failed tests", NIGHTLY)],
            env={"PATH": "/usr/bin:/bin", "JUNIT": str(junit), "SUITE": "failure"}
            | {"GITHUB_STEP_SUMMARY": str(out)},
            capture_output=True,
            text=True,
            check=True,
        )
        return ran.stdout, out.read_text()

    junit = tmp_path / "junit.xml"
    junit.write_text(FAILED)
    room = "features/jgauge/tests/test_room.py::test_load[idle]"
    setsid = "features/crew/tests/test_check.py::TestSetsid::test_starts"
    assert run(junit) == (
        "::warning::macOS: 2 tests failed, the suite step ended failure\n"
        f"FAILED {room}\nFAILED {setsid}\n",
        f"macOS: 2 tests failed, the suite step ended failure\n- `{room}`\n- `{setsid}`\n",
    )
    assert run(tmp_path / "gone") == (
        "::warning::macOS: no test report, the suite step ended failure\n",
        "macOS: no test report, the suite step ended failure\n",
    )


VERSION = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]


def released(tmp_path, plugin=VERSION):
    """A repo of the Makefile, pyproject.toml, jmerge's green-tree lookup, `repo-standard
    green` and a plugin.json, on main, pushed to a bare origin, for `make release`, `make
    release-tag` and `make release-green` to run in."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
    subprocess.run([*git, "init", "-q", "--bare", origin], check=True)
    subprocess.run([*git, "init", "-q", repo], check=True)
    shutil.copy(REPO / "Makefile", repo)
    shutil.copy(REPO / "pyproject.toml", repo)
    lookup = Path("features", "jmerge", "src", "jmerge")
    (repo / lookup).mkdir(parents=True)
    for name in ("__init__.py", "green.py"):
        shutil.copy(REPO / lookup / name, repo / lookup)
    standard = Path("features", "repo-standard", "src", "repo_standard")
    shutil.copytree(REPO / standard, repo / standard, ignore=shutil.ignore_patterns("__pycache__"))
    (repo / "plugin.json").write_text(json.dumps({"version": plugin}))
    for args in (["add", "."], ["commit", "-qm", "one"], ["remote", "add", "origin", origin]):
        subprocess.run([*git, "-C", repo, *args], check=True)
    subprocess.run([*git, "-C", repo, "push", "-q", "origin", "main"], check=True)
    return repo, origin, git


ASKED = "repos/{owner}/{repo}/"
"""What `make release-green` asks `gh api` for begins with this: gh fills in the repo, from
GH_REPO on the runner and from the checkout's origin on the desk."""


def make(repo, *args, answers=None, gh=True):
    """Run make in the repo, with a `gh` that answers each path under ASKED from `answers` and
    refuses any other, or with no `gh` on the PATH. Return the run and the paths `gh` was asked
    for."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env |= {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    stub = repo.parent / "gh-stub"
    shutil.rmtree(stub, ignore_errors=True)
    stub.mkdir()
    if gh:
        (stub / "answers.json").write_text(json.dumps(answers or {}))
        (stub / "gh").write_text(
            f"#!{sys.executable}\n"
            "import json, pathlib, sys\n"
            f"here = pathlib.Path({str(stub)!r})\n"
            "with open(here / 'asked', 'a') as asked:\n"
            "    asked.write(sys.argv[2] + '\\n')\n"
            "path, _, _ = sys.argv[2].partition('?')\n"
            f"under = path.removeprefix({ASKED!r})\n"
            "answer = json.loads((here / 'answers.json').read_text()).get(under)\n"
            "if sys.argv[1] != 'api' or under == path or answer is None:\n"
            "    sys.exit('HTTP 403: Resource not accessible by integration')\n"
            "print(json.dumps(answer))\n"
        )
        (stub / "gh").chmod(0o755)
        env["PATH"] = os.pathsep.join([str(stub), env["PATH"]])
    else:
        for tool in ("make", "git", "python3"):
            (stub / tool).symlink_to(shutil.which(tool))
        env["PATH"] = str(stub)
    done = subprocess.run(
        ["make", "-s", "-C", repo, *args], env=env, capture_output=True, text=True
    )
    asked = stub / "asked"
    return done, asked.read_text().splitlines() if asked.exists() else []


def tree_of(repo):
    return subprocess.run(
        ["git", "-C", repo, "rev-parse", "HEAD^{tree}"], capture_output=True, text=True, check=True
    ).stdout.strip()


def green(**changed):
    """GitHub's answers for a marker, left by run 7, a green run of check.yml in the
    repo itself, with the run's fields changed as given."""
    return {
        "actions/artifacts": marker(),
        "actions/runs/7": run(**changed),
    }


def test_the_tag_must_be_the_version_of_pyproject_and_of_plugin_json(tmp_path):
    repo, _, _ = released(tmp_path / "same")
    assert make(repo, "release-tag", f"TAG=v{VERSION}")[0].returncode == 0
    assert make(repo, "release-tag", "TAG=v9.9.9")[0].returncode != 0
    skewed, _, _ = released(tmp_path / "skewed", plugin="9.9.9")
    refused, _ = make(skewed, "release-tag", f"TAG=v{VERSION}")
    assert refused.returncode != 0
    assert "v9.9.9, plugin.json's" in refused.stdout


def test_a_release_passes_on_a_tree_main_s_green_run_of_the_check_left_a_marker_for(tmp_path):
    repo, _, _ = released(tmp_path)
    tree = tree_of(repo)
    done, asked = make(repo, "release-green", answers=green())
    assert done.returncode == 0, done.stdout + done.stderr
    assert URL in done.stdout and tree in done.stdout
    assert asked[0] == f"{ASKED}actions/artifacts?name=green-tree-{tree}&per_page=100"


FIX = "make release-green REF=<the tag>"


@pytest.mark.parametrize(
    "answers, why",
    [
        ({"actions/artifacts": {"artifacts": []}}, "no green run of check.yml left"),
        (green(conclusion="failure"), "no green run of check.yml left"),
        (green(path=".github/workflows/other.yml"), "no green run of check.yml left"),
        (green(head_repository={"id": 2}), "a fork's"),
        ({}, "could not ask GitHub"),
        (None, "could not ask GitHub"),
    ],
    ids=["none", "red", "other workflow", "fork", "refused", "no gh"],
)
def test_a_release_fails_closed_naming_the_fix_on_a_tree_with_no_green_marker(
    tmp_path, answers, why
):
    repo, _, _ = released(tmp_path)
    done, _ = make(repo, "release-green", answers=answers, gh=answers is not None)
    said = done.stdout + done.stderr
    assert done.returncode != 0, said
    assert why in said and f"green-tree-{tree_of(repo)}" in said and FIX in said, said
    assert "Traceback" not in said, said


def test_make_release_runs_repo_standard_green_first_and_tags_only_a_tree_it_passed(tmp_path):
    repo, origin, git = released(tmp_path)

    def tags():
        listed = subprocess.run(
            ["git", "ls-remote", "--tags", origin], capture_output=True, text=True, check=True
        )
        return [line.split("refs/tags/")[1] for line in listed.stdout.splitlines()]

    def refused(answers=None):
        done = make(repo, "release", answers=answers or green())[0]
        assert done.returncode != 0, done.stdout + done.stderr
        return done.stdout

    (repo / "loose").write_text("")
    assert "repo-standard green: refused: the checkout is not clean" in refused()
    (repo / "loose").unlink()
    subprocess.run([*git, "-C", repo, "commit", "-q", "--allow-empty", "-m", "two"], check=True)
    assert "is not origin's main" in refused()
    subprocess.run([*git, "-C", repo, "push", "-q", "origin", "main"], check=True)
    none = {"actions/artifacts": {"artifacts": []}, "actions/workflows/check.yml/runs": {}}
    assert "has not passed the check" in refused(none)
    assert tags() == []
    assert subprocess.run([*git, "-C", repo, "tag"], capture_output=True, text=True).stdout == ""
    done, asked = make(repo, "release", answers=green())
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith("repo-standard green: green: "), done.stdout
    assert asked[0] == f"{ASKED}actions/artifacts?name=green-tree-{tree_of(repo)}&per_page=100"
    assert tags() == [f"v{VERSION}", f"v{VERSION}^{{}}"]
