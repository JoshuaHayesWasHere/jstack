"""The check workflow runs on main, on the integration branches (`unslop` and any `train/...`)
and on every pull request. The next run never cancels a run on any of them, because each push's
run is a concurrency group of its own. A pull request gets the job `check`, the fast one, which
runs the lint and the tests its change reaches. A push to main or to an integration branch, and
a manual run, get the job `full`, the whole suite. Each runs its tests as four parts side by
side, the jobs `check-shard` and `full-shard`, and passes only when all four did. The workflow
checks a push to an integration branch as it checks a push to main. jmerge holds a pull request
into an integration branch while that branch is red, so jmerge has a check to read on the
branch's tip.

The test reads the workflow file as YAML with two small readers, `mapping` and `block`, which handle
only mappings by their indentation, a scalar, and a list in brackets.

Every job runs on GitHub's hosted runner, the pinned image `ubuntu-24.04`, and none names a runner
of the owner's machine or reads a repo variable for it. The one other image is `macos-15`, for the
workflow `macos-nightly`: the whole suite on macOS, nightly at 04:00 ET, an hour after the browser
run, and by hand, over the branch its `ref` names, `train/macos` unless a manual run names another.
It runs on no pull request and no push, and no merge waits on it.
Each job has a cap that a hung run meets.
The browser workflow names Google Chrome as its test browser, and the check names none.
The tests that open a browser carry the marker `browser`. `make check` leaves them out, and `make
check-browser` runs them: nightly at 03:00 ET, on a `v*` tag or a published release, and by hand,
but never on a pull request or a push to main. Every workflow gets read access to the contents and
no more, and none runs on `pull_request_target`. The check may also read the repo's artifacts, which
is where a green run's marker is.

When a green run already tested the tree of a run of `full`, that run skips the suite. Its
steps do the skipping, never its job or its triggers, so GitHub always reports `full`. Only `full`
asks for a marker. `full` leaves one, and so does a pull request's `check` that ran the whole
suite: a marker says the full suite passed on a tree. A pull request's check also says, in its
summary and its telemetry, whether the suite ran whole and on which tree. This module runs the
script that asks for a marker in a temporary repo, against a `gh` that answers from files.

The drift step keeps jdrift's clone of pstack in the runner's temporary directory, which
does not outlive the job.

Every setup-uv step installs one exact uv, the workflow's own `UV_VERSION`, and every
workflow names the same one: with no version, setup-uv fetches the latest release on each job."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from testing.paths import REPO

WORKFLOWS = REPO / ".github" / "workflows"
CHECK = WORKFLOWS / "check.yml"
DRIFT = WORKFLOWS / "pstack-drift.yml"
BROWSER = WORKFLOWS / "browser.yml"
RELEASE = WORKFLOWS / "release.yml"
BORDERS = WORKFLOWS / "borders.yml"
NIGHTLY = WORKFLOWS / "macos-nightly.yml"
GREEN_TREE = REPO / "scripts" / "green_tree.py"
HOSTED = "ubuntu-24.04"
MACOS = "macos-15"


def scalar(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [scalar(item) for item in text[1:-1].split(",") if item.strip()]
    if len(text) > 1 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return {"true": True, "false": False, "": None}.get(text, text)


def mapping(lines, depth=0):
    """The mapping the lines at this indentation make, and the lines after it."""
    found = {}
    while lines:
        line = lines[0]
        indent = len(line) - len(line.lstrip())
        if indent < depth:
            break
        assert indent == depth and not line.lstrip().startswith("- "), line
        key, _, value = line.strip().partition(":")
        lines = lines[1:]
        deeper = bool(lines) and len(lines[0]) - len(lines[0].lstrip()) > depth
        if deeper and not value.strip():
            found[key], lines = mapping(lines, len(lines[0]) - len(lines[0].lstrip()))
        else:
            found[key] = scalar(value)
    return found, lines


def block(name, path=CHECK):
    """One top-level block of a workflow, as a mapping."""
    lines = [
        line
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    start = lines.index(f"{name}:")
    end = next(
        (at for at in range(start + 1, len(lines)) if not lines[at].startswith(" ")), len(lines)
    )
    return mapping(lines[start:end])[0][name]


def test_the_reader_reads_mappings_scalars_and_lists():
    text = "on:\n  pull_request:\n  push:\n    branches: [main, 'next']\nflag: true\n"
    assert mapping(text.splitlines())[0] == {
        "on": {"pull_request": None, "push": {"branches": ["main", "next"]}},
        "flag": True,
    }


def test_the_check_runs_on_every_pull_request_on_each_push_to_main_or_a_train_and_by_hand():
    assert block("on") == {
        "pull_request": None,
        "push": {"branches": ["main", "unslop", "train/**"]},
        "workflow_dispatch": None,
    }


def worked(expression, values):
    """Return what a workflow expression gives with these values for its names. This function
    works the expression out itself, without GitHub.

    It reads `&&`, `||`, `==`, `!=` and a string in single quotes.
    """
    for name in sorted(values, key=len, reverse=True):
        expression = expression.replace(name, repr(values[name]))
    return eval(expression.replace("&&", " and ").replace("||", " or "), {"__builtins__": {}})


GROUP = "github.event_name == 'pull_request' && github.ref || github.run_id"


def test_a_run_on_main_is_never_cancelled_and_a_pull_requests_older_run_is():
    assert block("concurrency") == {
        "group": "check-${{ " + GROUP + " }}",
        "cancel-in-progress": "${{ github.event_name == 'pull_request' }}",
    }
    cancels = block("concurrency")["cancel-in-progress"].removeprefix("${{ ").removesuffix(" }}")
    events = ("pull_request", "push", "workflow_dispatch")
    assert [worked(cancels, {"github.event_name": e}) for e in events] == [True, False, False]


def test_a_push_and_a_manual_run_are_each_a_group_of_their_own_and_a_pull_request_is_its_ref():
    def group(event, run):
        names = {"github.event_name": event, "github.run_id": run, "github.ref": "refs/pull/9"}
        return worked(GROUP, names)

    assert group("pull_request", 1) == group("pull_request", 2) == "refs/pull/9"
    assert [group("push", 3), group("push", 4)] == [3, 4]
    assert [group("workflow_dispatch", 5), group("workflow_dispatch", 6)] == [5, 6]


def jobs(text):
    """Each job of a workflow and its `runs-on`, as written."""
    found, job, inside = {}, None, False
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent == 0:
            inside = line == "jobs:"
        elif inside and indent == 2:
            job = line.strip().removesuffix(":")
            found[job] = None
        elif inside and indent == 4 and line.strip().startswith("runs-on:"):
            found[job] = line.strip().partition(":")[2].strip()
    return found


def test_every_job_of_every_workflow_runs_on_githubs_hosted_runner():
    assert {path.name: jobs(path.read_text()) for path in sorted(WORKFLOWS.glob("*.yml"))} == {
        "borders.yml": {"borders": HOSTED},
        "browser.yml": {"browser": HOSTED},
        "check.yml": {"check-shard": HOSTED, "check": HOSTED, "full-shard": HOSTED, "full": HOSTED},
        "macos-nightly.yml": {"macos": MACOS},
        "pstack-drift.yml": {"drift": HOSTED},
        "release.yml": {"release": HOSTED},
    }


def test_no_file_under_github_names_a_runner_of_the_owners_machine_or_its_variable():
    for path in sorted(WORKFLOWS.parent.rglob("*")):
        if path.is_file():
            text = path.read_text()
            for name in ("self-hosted", "jstack-fast", "jstack-ephemeral", "RUNS_ON"):
                assert name not in text, (path.name, name)


def test_every_workflow_may_read_the_contents_and_no_more_and_none_runs_for_a_fork_with_secrets():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        more = {"actions": "read"} if path == CHECK else {}
        contents = "write" if path == RELEASE else "read"
        assert block("permissions", path) == {"contents": contents} | more, path.name
        assert "pull_request_target" not in path.read_text(), path.name


CHROME = {"JSTACK_TEST_BROWSER": "/usr/bin/google-chrome"}


def job_env(text, job):
    """The `env` of one job, as written, and None when it has none."""
    found, inside, env = None, False, False
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent <= 2:
            inside = indent == 2 and line.strip() == f"{job}:"
        elif inside and indent == 4:
            env = line.strip() == "env:"
            found = {} if env else found
        elif inside and env and indent == 6:
            key, _, value = line.strip().partition(":")
            found[key] = scalar(value)
    return found


def test_the_browser_job_names_google_chrome_once_and_the_check_jobs_name_no_browser():
    text = BROWSER.read_text()
    assert job_env(text, "browser") == CHROME
    assert text.count("JSTACK_TEST_BROWSER: ") == 1
    named = [step for step in steps(text, "browser")[0] if "env" in step]
    assert named == []
    assert "JSTACK_TEST_BROWSER" not in CHECK.read_text()
    assert "google-chrome" not in CHECK.read_text()


def test_a_job_env_is_read_from_its_own_job_and_not_from_a_step():
    text = (
        "jobs:\n  one:\n    env:\n      A: b\n    steps:\n      - run: true\n"
        "  two:\n    steps:\n      - name: x\n        env:\n          C: d\n"
    )
    assert (job_env(text, "one"), job_env(text, "two")) == ({"A": "b"}, None)


def test_the_browser_is_looked_for_right_before_the_tests_and_its_absence_fails_naming_it(
    tmp_path,
):
    found, _ = steps(BROWSER.read_text(), "browser")
    names = [step.get("name") for step in found]
    look = found[names.index("test browser")]
    assert names.index("make check-browser") == names.index("test browser") + 1
    assert names[-1] == "make check-browser" and "if" not in look
    browser = tmp_path / "google-chrome"

    def ran():
        return subprocess.run(
            ["bash", "-ec", look["run"]],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "JSTACK_TEST_BROWSER": str(browser)},
        )

    absent = ran()
    assert absent.returncode != 0
    assert f"::error::no test browser at {browser}," in absent.stdout
    browser.write_text("#!/bin/sh\n")
    browser.chmod(0o755)
    assert (ran().returncode, ran().stdout) == (0, "")


def test_a_bare_hosted_label_is_read_as_it_is_written():
    text = (
        "on:\n  push:\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
    )
    assert jobs(text) == {"check": "ubuntu-latest"}


def step_env(text, name):
    """The `env` of the step with this name, as written, and None when it has none."""
    found, step, env = None, None, None
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if step is not None and indent <= step:
            step = env = None
        if step is None:
            if line.strip() == f"- name: {name}":
                step = indent
        elif env is not None and indent > env:
            key, _, value = line.strip().partition(":")
            found[key] = scalar(value)
        elif line.strip() == "env:" and indent == step + 2:
            found, env = {}, indent
        else:
            env = None
    return found


TEMP = {"XDG_CACHE_HOME": "${{ runner.temp }}"}


def test_the_drift_step_keeps_its_cache_in_the_runners_temporary_directory():
    assert step_env(DRIFT.read_text(), "make pstack-drift") == TEMP


def test_a_drift_step_with_the_cache_line_gone_or_misspelt_is_not_read_as_having_it():
    text = DRIFT.read_text()
    line = "          XDG_CACHE_HOME: ${{ runner.temp }}\n"
    assert text.count(line) == 1
    for other in (
        "",
        "          XDG_CACHE_HOME:\n",
        "          XDG_CACHE_HOME: ${{ runner.tmp }}\n",
        "          XDG_CACHE_DIR: ${{ runner.temp }}\n",
        "          XDG_CACHE_HOME: ${{ runner.temp }}/cache\n",
    ):
        assert step_env(text.replace(line, other), "make pstack-drift") != TEMP, other
    assert step_env(text.replace("        env:\n", ""), "make pstack-drift") != TEMP


def test_an_env_is_read_from_its_own_step_and_no_other():
    text = (
        "jobs:\n  drift:\n    steps:\n"
        "      - name: one\n        env:\n          A: b\n        run: true\n"
        "      - name: two\n        run: |\n          env:\n"
        "      - name: three\n        env:\n          C: 'd'\n          E: f\n"
    )
    assert step_env(text, "one") == {"A": "b"}
    assert step_env(text, "two") is None
    assert step_env(text, "three") == {"C": "d", "E": "f"}


def steps(text, job):
    """The steps of one job, each as the keys written on it, and the job's own keys."""
    found, keys, inside, at = [], [], False, None
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent <= 2:
            inside, at = line.strip() == f"{job}:" and indent == 2, None
        elif not inside:
            continue
        elif indent == 4:
            keys.append(line.strip().partition(":")[0])
            at = indent if line.strip() == "steps:" else None
        elif at is not None and indent == 6 and line.strip().startswith("- "):
            key, _, value = line.strip()[2:].partition(":")
            found.append({key: scalar(value.partition(" # ")[0])})
        elif at is not None and indent == 8:
            key, _, value = line.strip().partition(":")
            found[-1][key] = scalar(value) if value.strip() else {}
        elif at is not None and indent == 10 and isinstance(found[-1][key], dict):
            under, _, value = line.strip().partition(":")
            found[-1][key][under] = scalar(value)
    return found, keys


def test_steps_are_read_with_their_own_keys_and_the_job_with_its_own():
    text = (
        "jobs:\n  other:\n    if: false\n    steps:\n      - run: true\n"
        "  check:\n    runs-on: x\n    steps:\n      - uses: a/b@1 # v1\n        with:\n"
        "          if: no\n          depth: 2\n      - name: one\n        if: a != 'b'\n"
        "        run: make check\n"
    )
    assert steps(text, "check") == (
        [
            {"uses": "a/b@1", "with": {"if": "no", "depth": "2"}},
            {"name": "one", "if": "a != 'b'", "run": "make check"},
        ],
        ["runs-on", "steps"],
    )
    assert steps(text, "other") == ([{"run": True}], ["if", "steps"])


def cap(text, job):
    """The minutes after which GitHub cancels one job, as the job says them."""
    inside = False
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if indent <= 2 and line.strip() and not line.lstrip().startswith("#"):
            inside = line.strip() == f"{job}:" and indent == 2
        elif inside and indent == 4 and line.strip().startswith("timeout-minutes:"):
            return scalar(line.partition(":")[2])
    return None


CAPS = {
    ("borders.yml", "borders"): "5",
    ("browser.yml", "browser"): "15",
    ("check.yml", "check-shard"): "30",
    ("check.yml", "check"): "5",
    ("check.yml", "full-shard"): "30",
    ("check.yml", "full"): "5",
    ("macos-nightly.yml", "macos"): "90",
    ("pstack-drift.yml", "drift"): "5",
    ("release.yml", "release"): "30",
}


def test_every_job_has_a_cap_that_stops_a_hung_run():
    text = "jobs:\n  other:\n    steps:\n      - timeout-minutes: 1\n  check:\n"
    text += "    timeout-minutes: 25\n"
    assert (cap(text, "check"), cap(text, "other")) == ("25", None)
    caps = {
        (path.name, job): cap(path.read_text(), job)
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for job in jobs(path.read_text())
    }
    assert caps == CAPS


UNLESS_GREEN = "steps.tree.outputs.marker != 'green'"
ZSH = "sudo apt-get update -q && sudo apt-get install -y -q --no-install-recommends zsh"
SUITE = 'make check JUNIT="$RUNNER_TEMP/junit.xml" SHARD=${{ matrix.shard }}/4'
OR_THE_DESKS = f"{UNLESS_GREEN} || steps.tree.outputs.from == 'desk'"


EVENTS = ("pull_request", "push", "workflow_dispatch")


def ran_on(job):
    """Return the events a job of the check runs on. This function works them out from the
    job's `if`."""
    inside, when = False, None
    for line in CHECK.read_text().splitlines():
        indent = len(line) - len(line.lstrip())
        if indent <= 2 and line.strip() and not line.lstrip().startswith("#"):
            inside = indent == 2 and line.strip() == f"{job}:"
        elif inside and indent == 4 and line.startswith("    if: "):
            when = line.partition(": ")[2]
    return [e for e in EVENTS if worked(when, {"always()": True, "github.event_name": e})]


def test_a_pull_request_runs_check_and_a_push_to_main_and_a_manual_run_run_full():
    assert jobs(CHECK.read_text()) == {
        "check-shard": HOSTED,
        "check": HOSTED,
        "full-shard": HOSTED,
        "full": HOSTED,
    }
    pull, push = ["pull_request"], ["push", "workflow_dispatch"]
    assert [ran_on(job) for job in ("check-shard", "check", "full-shard", "full")] == [
        pull,
        pull,
        push,
        push,
    ]


def job_section(job, key):
    """One mapping key of a job, `strategy` or `outputs`, as a mapping."""
    lines, inside, at = [], False, None
    for line in CHECK.read_text().splitlines():
        indent = len(line) - len(line.lstrip())
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent <= 2:
            inside = indent == 2 and line.strip() == f"{job}:"
        elif inside and indent == 4:
            at = line.strip() == f"{key}:"
        elif inside and at:
            lines.append(line)
    return mapping(lines, 6)[0]


def job_line(job, key):
    """One scalar key of a job, as written, or None."""
    inside = False
    for line in CHECK.read_text().splitlines():
        indent = len(line) - len(line.lstrip())
        if indent <= 2 and line.strip() and not line.lstrip().startswith("#"):
            inside = indent == 2 and line.strip() == f"{job}:"
        elif inside and indent == 4 and line.strip().startswith(f"{key}:"):
            return scalar(line.partition(":")[2])
    return None


PARTS = ["1", "2", "3", "4"]
RESULTS = ("success", "failure", "cancelled", "skipped")


@pytest.mark.parametrize("gate,parts", [("check", "check-shard"), ("full", "full-shard")])
def test_the_suite_runs_as_four_parts_side_by_side_and_one_job_passes_only_when_all_four_did(
    gate, parts, tmp_path
):
    """The ruleset and jmerge require the job named `check`, so it stays one job: it waits on the
    four parts whatever they did, and this runs its first step on each result GitHub can give."""
    assert job_section(parts, "strategy") == {"fail-fast": False, "matrix": {"shard": PARTS}}
    assert job_line(parts, "name") == f"{gate} ${{{{ matrix.shard }}}} of 4"
    assert job_line(gate, "needs") == parts
    assert job_line(gate, "if").startswith("always() && ")
    (every, *_), _ = steps(CHECK.read_text(), gate)
    assert every["env"] == {"PARTS": f"${{{{ needs.{parts}.result }}}}"}
    ran = {
        result: subprocess.run(
            ["sh", "-c", every["run"]], env={"PARTS": result}, capture_output=True, text=True
        )
        for result in RESULTS
    }
    assert [result for result in RESULTS if ran[result].returncode == 0] == ["success"]
    assert all("::error::" in ran[result].stdout for result in RESULTS[1:])
    assert "SHARD=${{ matrix.shard }}/4" in " ".join(map(str, steps(CHECK.read_text(), parts)[0]))


def test_the_fast_check_reads_two_commits_and_runs_the_tests_its_change_reaches_over_main():
    found, keys = steps(CHECK.read_text(), "check-shard")
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in found][:6] == [
        "actions/checkout",
        "astral-sh/setup-uv",
        "uv sync --locked",
        ZSH,
        'echo "name=green-tree-$(git rev-parse HEAD^{tree})" >> "$GITHUB_OUTPUT"',
        "make check-fast BASE=HEAD^1 SHARD=${{ matrix.shard }}/4",
    ]
    assert found[0]["with"] == {"persist-credentials": False, "fetch-depth": "2"}
    assert all("if" not in step for step in found[:6])
    assert found[5]["id"] == "suite"


def test_only_full_asks_for_a_marker_and_both_jobs_leave_one():
    """A pull request's check skips nothing: its own run is the proof that the suite passed,
    and a marker records that. The parts ask, and the one job over them leaves it."""
    asking = ("green_tree.py", "steps.tree.outputs.marker")
    leaving = ("green-tree", "upload-artifact", "needs.", "steps.marker")
    for job, gate, asks in (("check-shard", "check", False), ("full-shard", "full", True)):
        said = " ".join(map(str, steps(CHECK.read_text(), job)[0]))
        assert [word for word in asking if word in said] == (list(asking) if asks else []), job
        assert "upload-artifact" not in said, job
        said = " ".join(map(str, steps(CHECK.read_text(), gate)[0]))
        assert [word for word in leaving if word in said] == list(leaving), gate


def test_a_pull_requests_check_leaves_a_marker_only_when_it_ran_the_whole_suite_and_passed():
    *_, mark, upload = steps(CHECK.read_text(), "check")[0]
    assert job_section("check-shard", "outputs") == {
        "selection": "${{ steps.suite.outputs.selection }}",
        "tree": "${{ steps.tree.outputs.name }}",
    }
    assert [
        (result, selection)
        for result in RESULTS
        for selection in ("all", "some", "")
        if worked(
            mark["if"],
            {
                "needs.check-shard.result": result,
                "needs.check-shard.outputs.selection": selection,
            },
        )
    ] == [("success", "all")]
    assert (mark["id"], mark["env"]) == (
        "marker",
        {"NAME": "${{ needs.check-shard.outputs.tree }}"},
    )
    assert (
        mark["run"] == 'mkdir -p "$RUNNER_TEMP/green-tree" && touch "$RUNNER_TEMP/green-tree/$NAME"'
    )
    assert [o for o in OUTCOMES if worked(upload["if"], {"steps.marker.outcome": o})] == ["success"]
    assert (upload["id"], upload["continue-on-error"]) == ("upload", True)
    assert upload["with"] == {
        "name": "${{ needs.check-shard.outputs.tree }}",
        "path": "${{ runner.temp }}/green-tree/${{ needs.check-shard.outputs.tree }}",
        "retention-days": "7",
        "if-no-files-found": "error",
    }


def test_a_pull_requests_check_says_whether_the_suite_ran_whole_and_on_which_tree(tmp_path):
    """This runs the step as the runner runs it, with a `uv` that records what it was asked."""
    *_, report = steps(CHECK.read_text(), "check-shard")[0]
    assert report["continue-on-error"] is True
    assert [
        o
        for o in OUTCOMES
        if worked(report["if"], {"!cancelled()": True, "steps.suite.outcome": o})
    ] == ["success", "failure", "cancelled", ""]
    assert report["env"]["FULL"] == "${{ steps.suite.outputs.selection == 'all' }}"
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "uv").write_text(f'#!/bin/sh\necho "$*" >> "{tmp_path}/uv"\n')
    (bin / "uv").chmod(0o755)
    tree = "ab" * 20
    said = {}
    for full in ("true", "false"):
        summary = tmp_path / f"summary-{full}"
        env = {"PATH": f"{bin}:/usr/bin:/bin", "GITHUB_STEP_SUMMARY": str(summary)}
        env |= {"FULL": full, "NAME": f"green-tree-{tree}"}
        subprocess.run(["sh", "-c", report["run"]], env=env, check=True)
        said[full] = summary.read_text()
    assert said == {
        "true": f"full suite: yes, tree {tree}\n",
        "false": f"full suite: no, tree {tree}\n",
    }
    assert (tmp_path / "uv").read_text().splitlines() == [
        f"run jbus ci --notice full=true tree={tree}",
        f"run jbus ci --notice full=false tree={tree}",
    ]


def test_a_green_tree_skips_the_suite_by_its_steps_and_the_job_always_runs():
    found, keys = steps(CHECK.read_text(), "full-shard")
    assert "if" in keys and ran_on("full-shard") == ["push", "workflow_dispatch"]
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in found] == [
        "actions/checkout",
        "python3 scripts/green_tree.py",
        "astral-sh/setup-uv",
        "uv sync --locked",
        ZSH,
        SUITE,
        "|",
    ]
    gate, _ = steps(CHECK.read_text(), "full")
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in gate][1:] == [
        'mkdir -p "$RUNNER_TEMP/green-tree" && touch "$RUNNER_TEMP/green-tree/$NAME"',
        "actions/upload-artifact",
        'echo "::warning::green-tree, the lookup ended ${{ needs.full-shard.outputs.lookup }} and'
        " the upload ${{ steps.upload.outcome }}, so a later run of this tree may not skip the"
        ' suite"',
    ]
    checkout, ask, setup, sync, zsh, suite, *_ = found
    assert "if" not in checkout
    assert (ask.get("if"), ask["id"], ask["continue-on-error"]) == (None, "tree", True)
    assert [step["if"] for step in (setup, sync, zsh, suite)] == [
        OR_THE_DESKS,
        OR_THE_DESKS,
        UNLESS_GREEN,
        UNLESS_GREEN,
    ]
    assert suite["id"] == "suite"
    assert [
        word
        for word in ("green", "none", "unknown", "unasked", "")
        if not worked(UNLESS_GREEN, {"steps.tree.outputs.marker": word})
    ] == ["green"]


def test_a_run_skipped_on_the_desks_marker_still_proves_the_lock_and_skips_only_the_suite():
    """The desk's `make check` ran in an environment nobody locked, so the run still syncs."""
    found, _ = steps(CHECK.read_text(), "full-shard")
    _, _, setup, sync, _, suite, *_ = found
    assert (sync["run"], suite["run"]) == ("uv sync --locked", SUITE)
    ran = {
        (marker, by): [
            step.get("run", step.get("uses", "")).partition("@")[0]
            for step in (setup, sync, suite)
            if worked(
                step["if"], {"steps.tree.outputs.marker": marker, "steps.tree.outputs.from": by}
            )
        ]
        for marker, by in (("green", "desk"), ("green", "run"), ("none", ""), ("unknown", ""))
    }
    everything = ["astral-sh/setup-uv", "uv sync --locked", SUITE]
    assert ran == {
        ("green", "desk"): everything[:2],
        ("green", "run"): [],
        ("none", ""): everything,
        ("unknown", ""): everything,
    }


OUTCOMES = ("success", "failure", "cancelled", "skipped", "")


def test_the_marker_is_left_only_after_the_suite_ran_and_passed():
    *_, mark, upload, warn = steps(CHECK.read_text(), "full")[0]
    assert job_section("full-shard", "outputs") == {
        "tree": "${{ steps.tree.outputs.name }}",
        "lookup": "${{ steps.tree.outcome }}",
        "suite": "${{ steps.suite.outcome }}",
    }
    assert [
        (result, outcome, name)
        for result in RESULTS
        for outcome in OUTCOMES
        for name in ("green-tree-1", "")
        if worked(
            mark["if"],
            {
                "needs.full-shard.result": result,
                "needs.full-shard.outputs.suite": outcome,
                "needs.full-shard.outputs.tree": name,
            },
        )
    ] == [("success", "success", "green-tree-1")]
    assert mark["id"] == "marker"
    assert [o for o in OUTCOMES if worked(upload["if"], {"steps.marker.outcome": o})] == ["success"]
    tree = "${{ needs.full-shard.outputs.tree }}"
    assert mark["env"] == {"NAME": tree}
    assert upload["with"]["name"] == tree
    assert upload["with"]["path"] == f"${{{{ runner.temp }}}}/green-tree/{tree}"


def test_a_lookup_or_an_upload_that_failed_never_fails_the_run_and_is_a_warning_on_it():
    *_, upload, warn = steps(CHECK.read_text(), "full")[0]
    assert (upload["id"], upload["continue-on-error"]) == ("upload", True)
    assert [
        (tree, sent)
        for tree in ("success", "failure")
        for sent in ("success", "failure", "skipped")
        if worked(
            warn["if"], {"needs.full-shard.outputs.lookup": tree, "steps.upload.outcome": sent}
        )
    ] == [
        ("success", "failure"),
        ("failure", "success"),
        ("failure", "failure"),
        ("failure", "skipped"),
    ]


JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4" time="100.0">
<testcase classname="tests.test_a" name="test_one" time="30.0" />
<testcase classname="tests.test_a" name="test_two" time="20.0" />
<testcase classname="tests.test_b.TestThings" name="test_three" time="40.0" />
<testcase classname="tests.test_c" name="test_four" time="10.0"><failure message="no" /></testcase>
</testsuite></testsuites>
"""


def summary_step(name="suite summary", path=CHECK):
    """The shell of one step's block `run`, by default the `suite summary` step of `full`, as the
    runner gets it."""
    lines = path.read_text().splitlines()
    at = lines.index(f"      - name: {name}")
    start = lines.index("        run: |", at) + 1
    end = next(
        (n for n in range(start, len(lines)) if lines[n] and lines[n][:10].strip()), len(lines)
    )
    return "\n".join(line[10:] for line in lines[start:end]) + "\n"


def test_the_suite_summary_is_one_line_of_workers_quota_wall_test_time_tail_and_pressure(tmp_path):
    """This runs the step on a report of 100 seconds of test time, in 100 seconds of wall-clock
    time, on 4 workers under a quota of 4 CPUs."""
    found, _ = steps(CHECK.read_text(), "full-shard")
    (summary,) = [step for step in found if step.get("name") == "suite summary"]
    ran = {"!cancelled()": True}
    assert [o for o in OUTCOMES if worked(summary["if"], ran | {"steps.suite.outcome": o})] == [
        "success",
        "failure",
    ]
    cancelled = {"!cancelled()": False}
    assert not any(worked(summary["if"], cancelled | {"steps.suite.outcome": o}) for o in OUTCOMES)
    assert summary["continue-on-error"] is True
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "make").write_text("#!/bin/sh\necho 'uv run pytest -n 4 --dist worksteal -m x'\n")
    (bin / "make").chmod(0o755)
    files = {name: tmp_path / name for name in ("junit.xml", "cpu.max", "host", "cgroup", "out")}
    files["junit.xml"].write_text(JUNIT)
    files["cpu.max"].write_text("400000 100000\n")
    files["host"].write_text("some avg10=1.00 avg60=2.00 avg300=3.00 total=4\nfull x\n")
    files["cgroup"].write_text("some avg10=5.00 avg60=6.00 avg300=7.00 total=8\nfull y\n")
    ran = subprocess.run(
        ["bash", "-e", "-c", summary_step()],
        env={"PATH": f"{bin}:/usr/bin:/bin", "JUNIT": str(files["junit.xml"])}
        | {"CPU_MAX": str(files["cpu.max"]), "HOST_PRESSURE": str(files["host"])}
        | {"CGROUP_PRESSURE": str(files["cgroup"]), "GITHUB_STEP_SUMMARY": str(files["out"])},
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    line = (
        "suite: 4 workers, quota 4, wall 100.0 s, test time 100.0 s, tail 75.0 s,"
        " slowest tests/test_a.py 50.0 s,"
        " host cpu some avg10=1.00 avg60=2.00 avg300=3.00 total=4,"
        " cgroup cpu some avg10=5.00 avg60=6.00 avg300=7.00 total=8"
    )
    assert (ran.stdout, files["out"].read_text()) == (line + "\n", line + "\n")
    files["cpu.max"].write_text("max 100000\n")
    ran = subprocess.run(
        ["bash", "-e", "-c", summary_step()],
        env={"PATH": f"{bin}:/usr/bin:/bin", "JUNIT": str(files["junit.xml"])}
        | {"CPU_MAX": str(files["cpu.max"]), "HOST_PRESSURE": str(tmp_path / "gone")}
        | {"CGROUP_PRESSURE": str(tmp_path / "gone"), "GITHUB_STEP_SUMMARY": str(files["out"])},
        capture_output=True,
        text=True,
        check=True,
    )
    assert ", quota none, " in ran.stdout and ran.stdout.endswith("cpu none, cgroup cpu none\n")


def green_tree(tmp_path, answers, python=(sys.executable,), **env):
    """Run the script in a new repo against a `gh` that answers from these files.

    `answers` maps each path to its answer, or is a function that gives the answers for the repo's
    tree. When no answer exists for the tree, the tree has no ref: the desk left no marker.

    Return the step's outputs, what it printed, the tree, and the paths `gh` was asked for.
    """
    repo, bin, said = tmp_path / "repo", tmp_path / "bin", tmp_path / "said"
    for made in (repo, bin, said):
        made.mkdir()
    git = ["git", "-c", "user.name=a", "-c", "user.email=a@example.com", "-C", str(repo)]
    (repo / "file").write_text("one\n")
    for command in (["init", "-q"], ["add", "file"], ["commit", "-q", "-m", "one"]):
        subprocess.run([*git, *command], check=True)
    tree = subprocess.run(
        [*git, "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if callable(answers):
        answers = answers(tree)
    for path, body in ({f"{FULL}/{tree}": [], f"{SELECTED}/{tree}": []} | (answers or {})).items():
        (said / path.replace("/", "_")).write_text(json.dumps(body))
    (bin / "git").symlink_to(shutil.which("git"))
    if answers is not None:
        (bin / "gh").write_text(
            f"#!{sys.executable}\n"
            "import pathlib, sys\n"
            f"here = pathlib.Path({str(tmp_path)!r})\n"
            "with open(here / 'asked', 'a') as asked:\n"
            "    asked.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "answer = here / 'said' / sys.argv[2].partition('?')[0].replace('/', '_')\n"
            "if not answer.exists():\n"
            "    sys.exit('HTTP 403: Resource not accessible by integration')\n"
            "print(answer.read_text())\n"
        )
        (bin / "gh").chmod(0o755)
    ran = subprocess.run(
        [*python, str(GREEN_TREE)],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            "PATH": str(bin),
            "GITHUB_OUTPUT": str(tmp_path / "output"),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_RUN_ATTEMPT": "1",
            **env,
        },
    )
    assert ran.returncode == 0, ran.stderr
    asked = tmp_path / "asked"
    return (
        dict(line.split("=", 1) for line in (tmp_path / "output").read_text().splitlines()),
        ran.stdout.strip(),
        tree,
        asked.read_text().splitlines() if asked.exists() else [],
    )


REFS = "repos/owner/repo/git/matching-refs/jstack/green-tree"
FULL, SELECTED = f"{REFS}/full", f"{REFS}/selected"
COMMIT = "repos/owner/repo/git/commits/c0ffee"
ARTIFACTS = "repos/owner/repo/actions/artifacts"
RUN = "repos/owner/repo/actions/runs/7"
URL = "https://github.com/owner/repo/actions/runs/7"


def marker(**changed):
    """What GitHub lists for one marker, left by run 7 of the repo itself."""
    run = {"id": 7, "repository_id": 1, "head_repository_id": 1} | changed.pop("workflow_run", {})
    return {"artifacts": [{"expired": False, "workflow_run": run} | changed]}


def run(**changed):
    """What GitHub gives for run 7, a green run of the check in the repo itself."""
    return {
        "conclusion": "success",
        "path": ".github/workflows/check.yml",
        "html_url": URL,
        "repository": {"id": 1},
        "head_repository": {"id": 1},
    } | changed


def test_a_tree_with_a_marker_is_green_and_the_log_names_the_run_it_is_from(tmp_path):
    outputs, printed, tree, asked = green_tree(tmp_path, {ARTIFACTS: marker(), RUN: run()})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "green", "from": "run"}
    assert printed == f"green-tree: tree {tree}: passed the check in {URL}, so the suite is skipped"
    assert asked == [
        f"api {FULL}/{tree}",
        f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100",
        f"api {RUN}",
    ]


@pytest.mark.skipif(not Path("/usr/bin/python3").is_file(), reason="no system python3")
def test_the_lookup_runs_on_the_runners_bare_python_before_uv_sync(tmp_path):
    """The step runs before `uv sync`, on the system's python3, isolated and with no site
    packages, so an import of anything installed fails here."""
    bare = ("/usr/bin/python3", "-I", "-S")
    outputs, printed, tree, _ = green_tree(tmp_path, {ARTIFACTS: marker(), RUN: run()}, bare)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "green", "from": "run"}
    assert printed == f"green-tree: tree {tree}: passed the check in {URL}, so the suite is skipped"


def test_a_tree_with_no_marker_runs_the_suite(tmp_path):
    outputs, printed, tree, _ = green_tree(tmp_path, {ARTIFACTS: {"artifacts": []}})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none", "from": ""}
    assert printed.endswith(": no green run of the check left a marker, so the suite runs")


def test_a_run_that_is_refused_the_answer_runs_the_suite(tmp_path):
    outputs, printed, tree, asked = green_tree(tmp_path, {})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unknown", "from": ""}
    assert printed == (
        f"::warning::green-tree: tree {tree}: could not ask"
        " (HTTP 403: Resource not accessible by integration), so the suite runs"
    )
    assert asked == [f"api {FULL}/{tree}", f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100"]


def test_a_runner_with_no_gh_runs_the_suite(tmp_path):
    outputs, printed, tree, _ = green_tree(tmp_path, None)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unknown", "from": ""}
    assert printed.startswith("::warning::green-tree: ") and ": could not ask (" in printed


@pytest.mark.parametrize(
    "answers",
    [
        {ARTIFACTS: marker(workflow_run={"head_repository_id": 2}), RUN: run()},
        {
            ARTIFACTS: marker(workflow_run={"head_repository_id": None, "repository_id": None}),
            RUN: run(),
        },
        {ARTIFACTS: marker(expired=True), RUN: run()},
        {ARTIFACTS: marker(), RUN: run(conclusion="cancelled")},
        {ARTIFACTS: marker(), RUN: run(conclusion="failure")},
        {ARTIFACTS: marker(), RUN: run(conclusion=None)},
        {ARTIFACTS: marker(), RUN: run(path=".github/workflows/other.yml")},
    ],
)
def test_a_marker_counts_only_from_a_green_run_of_the_check_in_the_repo_itself(tmp_path, answers):
    outputs, _, tree, _ = green_tree(tmp_path, answers)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none", "from": ""}


@pytest.mark.parametrize(
    "answers",
    [
        {ARTIFACTS: marker(), RUN: run(head_repository={"id": 2})},
        {ARTIFACTS: marker(workflow_run={"head_repository_id": 2}), RUN: run()},
    ],
)
def test_a_marker_whose_run_is_a_forks_runs_the_suite_and_the_log_says_so(tmp_path, answers):
    outputs, printed, tree, _ = green_tree(tmp_path, answers)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none", "from": ""}
    assert printed == f"green-tree: tree {tree}: a marker came from a fork's run, so the suite runs"


def test_a_forks_marker_listed_before_the_repos_own_does_not_stop_the_skip(tmp_path):
    listed = [
        {"expired": False, "workflow_run": {"id": 5, "repository_id": 1, "head_repository_id": 2}},
        {"expired": False, "workflow_run": {"id": 6, "repository_id": 1, "head_repository_id": 1}},
        *marker()["artifacts"],
    ]
    answers = {
        ARTIFACTS: {"artifacts": listed},
        RUN.replace("/7", "/6"): run(head_repository={"id": 2}),
        RUN: run(),
    }
    outputs, printed, tree, _ = green_tree(tmp_path, answers)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "green", "from": "run"}
    assert printed == f"green-tree: tree {tree}: passed the check in {URL}, so the suite is skipped"


def test_a_marker_whose_run_cannot_be_read_runs_the_suite(tmp_path):
    outputs, printed, tree, asked = green_tree(tmp_path, {ARTIFACTS: marker()})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unknown", "from": ""}
    assert printed.startswith("::warning::green-tree: ") and ": could not ask (" in printed
    assert asked[2:] == [f"api {RUN}"]


@pytest.mark.parametrize("gone", [{"head_repository": None}, {"head_repository": {}}])
def test_a_marker_whose_run_names_no_head_repository_runs_the_suite(tmp_path, gone):
    outputs, printed, tree, _ = green_tree(tmp_path, {ARTIFACTS: marker(), RUN: run(**gone)})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none", "from": ""}
    assert printed.endswith(": no green run of the check left a marker, so the suite runs")


@pytest.mark.parametrize(
    ("env", "why"),
    [
        ({"GITHUB_EVENT_NAME": "workflow_dispatch"}, "a manual run always runs the suite"),
        ({"GITHUB_RUN_ATTEMPT": "2"}, "a run again always runs the suite"),
    ],
)
def test_a_manual_run_and_a_run_again_never_ask_and_run_the_suite(tmp_path, env, why):
    outputs, printed, tree, asked = green_tree(tmp_path, {ARTIFACTS: marker(), RUN: run()}, **env)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unasked", "from": ""}
    assert (printed, asked) == (f"green-tree: tree {tree}: {why}", [])


def ref(tree, kind="full", **changed):
    """What GitHub lists for the ref the desk pushed for a tree after a check of this kind, at
    the commit c0ffee."""
    name = f"refs/jstack/green-tree/{kind}/{tree}"
    return [{"ref": name, "object": {"sha": "c0ffee", "type": "commit"}} | changed]


def test_a_tree_the_desk_marked_is_green_and_the_log_names_the_desk(tmp_path):
    outputs, printed, tree, asked = green_tree(
        tmp_path, lambda tree: {f"{FULL}/{tree}": ref(tree), COMMIT: {"tree": {"sha": tree}}}
    )
    assert outputs == {"name": f"green-tree-{tree}", "marker": "green", "from": "desk"}
    assert printed == (
        f"green-tree: tree {tree}: passed a fresh check on the desk, which marked it with the"
        " commit c0ffee, so the suite is skipped"
    )
    assert asked == [f"api {FULL}/{tree}", f"api {COMMIT}"]


@pytest.mark.parametrize(
    "listed",
    [
        lambda tree: {f"{FULL}/{tree}": ref(tree), COMMIT: {"tree": {"sha": "0ther"}}},
        lambda tree: {f"{FULL}/{tree}": ref(tree), COMMIT: {}},
        lambda tree: {f"{FULL}/{tree}": ref(tree, ref=f"refs/jstack/green-tree/full/{tree}0")},
        lambda tree: {f"{FULL}/{tree}": ref(tree, object={"sha": "c0ffee", "type": "tag"})},
    ],
)
def test_a_ref_whose_commit_has_another_tree_is_no_marker_and_the_artifact_is_asked_for(
    tmp_path, listed
):
    outputs, printed, tree, asked = green_tree(
        tmp_path,
        lambda tree: {ARTIFACTS: {"artifacts": []}, COMMIT: {"tree": {"sha": tree}}} | listed(tree),
    )
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none", "from": ""}
    assert printed.endswith(": no green run of the check left a marker, so the suite runs")
    assert asked[-2:] == [
        f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100",
        f"api {SELECTED}/{tree}",
    ]


def test_a_tree_the_desk_marked_after_selected_tests_only_runs_the_suite_and_the_log_says_so(
    tmp_path,
):
    """On 2026-10-23 the desk's `make check-fast` pass skipped main's suite on a tree whose
    whole suite failed."""
    outputs, printed, tree, asked = green_tree(
        tmp_path,
        lambda tree: {
            f"{SELECTED}/{tree}": ref(tree, "selected"),
            COMMIT: {"tree": {"sha": tree}},
            ARTIFACTS: {"artifacts": []},
        },
    )
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none", "from": ""}
    assert printed == (
        f"green-tree: tree {tree}: passed only selected tests on the desk, which marked it with"
        " the commit c0ffee, so the suite runs"
    )
    assert asked == [
        f"api {FULL}/{tree}",
        f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100",
        f"api {SELECTED}/{tree}",
        f"api {COMMIT}",
    ]


def test_a_ref_whose_commit_cannot_be_read_runs_the_suite(tmp_path):
    outputs, printed, tree, asked = green_tree(tmp_path, lambda tree: {f"{FULL}/{tree}": ref(tree)})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unknown", "from": ""}
    assert printed.startswith("::warning::green-tree: ") and ": could not ask (" in printed
    assert asked == [f"api {FULL}/{tree}", f"api {COMMIT}"]


def test_a_manual_run_and_a_run_again_run_the_suite_on_a_tree_the_desk_marked(tmp_path):
    def marked(tree):
        return {f"{FULL}/{tree}": ref(tree), COMMIT: {"tree": {"sha": tree}}}

    for at, env in enumerate(
        ({"GITHUB_EVENT_NAME": "workflow_dispatch"}, {"GITHUB_RUN_ATTEMPT": "2"})
    ):
        (tmp_path / str(at)).mkdir()
        outputs, _, tree, asked = green_tree(tmp_path / str(at), marked, **env)
        assert outputs == {"name": f"green-tree-{tree}", "marker": "unasked", "from": ""}
        assert asked == []


def triggers(text):
    """Each event in a workflow's `on` block, and what narrows it. What narrows an event is a
    mapping of keys. For a schedule, it is a list with one mapping for each item."""
    lines = [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    start = lines.index("on:")
    end = next(
        (at for at in range(start + 1, len(lines)) if not lines[at].startswith(" ")), len(lines)
    )
    found, event = {}, None
    for line in lines[start + 1 : end]:
        indent, said = len(line) - len(line.lstrip()), line.strip()
        if indent == 2:
            event = said.partition(":")[0]
            found[event] = None
        elif said.startswith("- "):
            key, _, value = said[2:].partition(":")
            found[event] = [*(found[event] or []), {key: scalar(value)}]
        else:
            key, _, value = said.partition(":")
            found[event] = (found[event] or {}) | {key: scalar(value)}
    return found


def test_a_workflows_triggers_are_read_with_the_list_a_schedule_has():
    text = "on:\n  schedule:\n    - cron: '0 7 * * *'\n  push:\n    tags: ['v*']\n  other:\n"
    assert triggers(text) == {
        "schedule": [{"cron": "0 7 * * *"}],
        "push": {"tags": ["v*"]},
        "other": None,
    }


def test_the_browser_tests_run_nightly_on_a_release_and_by_hand_and_on_nothing_else():
    assert triggers(BROWSER.read_text()) == {
        "schedule": [{"cron": "0 7 * * *"}],
        "push": {"tags": ["v*"]},
        "release": {"types": ["published"]},
        "workflow_dispatch": None,
    }


def test_the_nightly_is_three_oclock_in_the_morning_eastern_time_every_day():
    (night,) = triggers(BROWSER.read_text())["schedule"]
    minute, hour, *every = night["cron"].split()
    assert every == ["*", "*", "*"]
    at = datetime(2026, 10, 18, int(hour), int(minute), tzinfo=UTC)
    assert at.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M") == "03:00"


def test_a_push_runs_the_browser_tests_for_a_version_tag_and_never_for_a_branch():
    push = triggers(BROWSER.read_text())["push"]
    assert list(push) == ["tags"]
    (pattern,) = push["tags"]
    assert [fnmatch(name, pattern) for name in ("v1.0.0", "v0.2", "main", "release-1")] == [
        True,
        True,
        False,
        False,
    ]


def test_the_browser_job_runs_only_the_marked_tests_and_the_checks_jobs_never_name_that_target():
    found, _ = steps(BROWSER.read_text(), "browser")
    assert found[-1] == {"name": "make check-browser", "run": "make check-browser"}
    for job in ("check-shard", "check", "full-shard", "full"):
        assert "check-browser" not in " ".join(map(str, steps(CHECK.read_text(), job)[0]))


TRAIN = "train/macos"


def dispatch_inputs(path):
    """The inputs of a workflow's `workflow_dispatch`, as a mapping of each input's keys."""
    lines = [
        line
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    start = lines.index("    inputs:") + 1
    end = next(at for at in range(start, len(lines)) if not lines[at].startswith("      "))
    return mapping(lines[start:end], 6)[0]


def test_the_macos_nightly_runs_on_a_schedule_and_by_hand_and_on_no_pull_request_or_push():
    found = triggers(NIGHTLY.read_text())
    assert list(found) == ["schedule", "workflow_dispatch"]
    assert "concurrency" not in NIGHTLY.read_text()


def test_the_macos_nightly_runs_every_day_an_hour_after_the_browser_run():
    (browser,) = triggers(BROWSER.read_text())["schedule"]
    (night,) = triggers(NIGHTLY.read_text())["schedule"]
    minute, hour, *every = night["cron"].split()
    assert every == ["*", "*", "*"]
    at = datetime(2026, 10, 18, int(hour), int(minute), tzinfo=UTC)
    assert at.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M") == "04:00"
    assert browser["cron"].split()[:2] == [minute, str(int(hour) - 1)]


def test_the_macos_nightly_checks_out_the_train_unless_a_manual_run_names_another_ref():
    """A scheduled run has no inputs, so the checkout's own fallback is the input's default."""
    assert list(dispatch_inputs(NIGHTLY)) == ["ref"]
    assert dispatch_inputs(NIGHTLY)["ref"]["default"] == TRAIN
    found, _ = steps(NIGHTLY.read_text(), "macos")
    checkout = found[0]
    assert checkout["uses"].partition("@")[0] == "actions/checkout"
    assert checkout["with"]["persist-credentials"] is False
    ref = checkout["with"]["ref"].removeprefix("${{").removesuffix("}}")
    assert [worked(ref, {"inputs.ref": given}) for given in ("", "fix-branch")] == [
        TRAIN,
        "fix-branch",
    ]


def test_a_run_of_the_train_is_titled_as_jbus_files_it_and_a_run_on_another_ref_is_not():
    """Every run of the nightly is on main, so the title is what tells jbus which ref it ran."""
    from jbus import watch

    lines = NIGHTLY.read_text().splitlines()
    (named,) = [line for line in lines if line.startswith("run-name: ")]
    title = named.removeprefix("run-name: ")
    head, _, rest = title.partition("${{")
    expression = rest.removesuffix("}}")
    titled = [head + worked(expression, {"inputs.ref": given}) for given in ("", "fix-branch")]
    assert titled[0] == watch.MACOS.title and titled[1] != watch.MACOS.title
    assert watch.MACOS.file == NIGHTLY.name and watch.MACOS in watch.NIGHTLIES


def test_the_macos_nightly_installs_as_the_macos_job_does_and_runs_make_check_into_a_report():
    from jmerge import ready

    found, _ = steps(NIGHTLY.read_text(), "macos")
    assert [
        step.get("uses", step.get("run", step.get("name"))).partition("@")[0] for step in found
    ][:3] == ["actions/checkout", "astral-sh/setup-uv", "uv sync --locked"]
    assert [step.get("name") for step in found][3:5] == ["tools", "make check"]
    assert "brew install bash; } && zsh --version" in NIGHTLY.read_text()
    (suite,) = [step for step in found if step.get("id") == "suite"]
    (listed,) = [step for step in found if step.get("name") == "failed tests"]
    assert suite["run"] == 'make check JUNIT="$RUNNER_TEMP/junit.xml"'
    assert listed["env"]["JUNIT"] == "${{ runner.temp }}/junit.xml"
    assert int(suite["timeout-minutes"]) < int(cap(NIGHTLY.read_text(), "macos"))
    assert found.index(listed) == found.index(suite) + 1
    assert "continue-on-error" not in NIGHTLY.read_text()
    assert "macos" not in ready.REQUIRED and "macos-nightly" not in ready.REQUIRED


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


def test_every_action_is_pinned_to_one_commit_with_its_version_beside_it():
    pins = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text().splitlines():
            if line.strip().startswith("- uses: "):
                used, _, version = line.strip()[len("- uses: ") :].partition(" # ")
                action, _, commit = used.partition("@")
                assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit), line
                assert version.startswith("v"), line
                pins.setdefault(action, set()).add(used)
    assert pins and all(len(used) == 1 for used in pins.values()), pins


PIN = "${{ env.UV_VERSION }}"


def uv_versions(path):
    """The uv version that each setup-uv step of a workflow installs. Where a step's `version` is
    `PIN`, it is the workflow's own `UV_VERSION`, and otherwise the step's own `version`. It is None
    when the step gives no version, which setup-uv reads as the latest release."""
    text = path.read_text()
    pinned = (block("env", path) if "env:" in text.splitlines() else {}).get("UV_VERSION")
    found = []
    for job in jobs(text):
        for step in steps(text, job)[0]:
            if str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
                version = (step.get("with") or {}).get("version")
                found.append(pinned if version == PIN else version)
    return found


def test_every_setup_uv_step_installs_one_exact_uv_named_once_in_each_workflow():
    found = {path.name: uv_versions(path) for path in sorted(WORKFLOWS.glob("*.yml"))}
    found = {name: versions for name, versions in found.items() if versions}
    assert {name: len(versions) for name, versions in found.items()} == {
        "browser.yml": 1,
        "check.yml": 2,
        "macos-nightly.yml": 1,
        "pstack-drift.yml": 1,
        "release.yml": 1,
    }
    (version,) = {version for versions in found.values() for version in versions}
    assert version is not None and version.count(".") == 2, version
    assert all(part.isdigit() for part in version.split(".")), version
    for name in found:
        assert (WORKFLOWS / name).read_text().count("UV_VERSION:") == 1, name


def test_a_setup_uv_step_with_no_version_or_a_workflow_with_no_pin_reads_as_the_latest(tmp_path):
    path = tmp_path / "flow.yml"
    step = "      - uses: astral-sh/setup-uv@1 # v1\n"
    path.write_text(f"jobs:\n  one:\n    steps:\n{step}")
    assert uv_versions(path) == [None]
    path.write_text(f"jobs:\n  one:\n    steps:\n{step}        with:\n          version: {PIN}\n")
    assert uv_versions(path) == [None]
    path.write_text("env:\n  UV_VERSION: '0.1.2'\n" + path.read_text())
    assert uv_versions(path) == ["0.1.2"]


def test_a_release_runs_on_a_pushed_version_tag_and_on_nothing_else():
    assert triggers(RELEASE.read_text()) == {"push": {"tags": ["v*"]}}


def test_a_release_checks_the_tag_then_the_tree_builds_installs_the_wheel_and_then_publishes():
    found, _ = steps(RELEASE.read_text(), "release")
    named = [step.get("name") for step in found if step.get("name")]
    assert named == [
        "make release-tag",
        "zsh",
        "make check",
        "make dist",
        "jinstall --check",
        "gh release create",
    ]
    by = {step["name"]: step for step in found if step.get("name")}
    assert by["make release-tag"]["run"] == 'make release-tag TAG="$TAG"'
    assert by["make release-tag"]["env"] == {"TAG": "${{ github.ref_name }}"}
    text = RELEASE.read_text()
    smoke = text[text.index("name: jinstall --check") : text.index("name: gh release create")]
    assert "uv tool install dist/*.whl" in smoke
    assert smoke.rstrip().splitlines()[-2].endswith('/jinstall" --check')
    assert by["gh release create"]["run"].startswith('gh release create "$TAG" dist/* --verify-tag')


def refused(text):
    """The lines whose value YAML refuses, by line number: an unquoted value that holds `: ` or ends
    with `:`, which YAML reads as a second mapping on one line. GitHub cannot use such a file. On
    every push it reports a run that has the file's path as its name and no jobs, whatever the
    file's triggers say. A block scalar starts after `|` or `>`, and its lines are indented past its
    key, not past a list item's dash. Those lines hold shell code, not YAML."""
    found, under = [], None
    for number, line in enumerate(text.splitlines(), 1):
        indent = len(line) - len(line.lstrip())
        if under is not None and (not line.strip() or indent > under):
            continue
        under = None
        content = line.strip()
        if not content or content.startswith("#"):
            continue
        item = content.removeprefix("- ").lstrip()
        column, content = indent + len(content) - len(item), item
        if ": " not in content:
            continue
        value = content.partition(": ")[2].strip()
        if not value or value[0] in "#'\"[{&*!":
            continue
        value = value.partition(" #")[0].strip()
        if value[0] in "|>":
            under = column
        elif ": " in value or value.endswith(":"):
            found.append(number)
    return found


def test_every_workflow_is_a_file_yaml_reads():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        assert refused(path.read_text()) == [], path.name


def test_an_unquoted_value_with_a_colon_and_a_space_is_refused_and_a_quoted_or_block_one_is_not():
    step = "    steps:\n      - name: notes\n"
    bad = 'run: gh release create --notes "Install: curl"\n'
    assert refused(f"jobs:\n  one:\n{step}        {bad}") == [5]
    assert refused(f"jobs:\n  one:\n{step}        - run: echo a:\n") == [5]
    assert refused(f"jobs:\n  one:\n{step}        run: >-\n          {bad}") == []
    assert refused(f"jobs:\n  one:\n{step}        run: '{bad.strip()}'\n") == []
    assert refused("on:\n  push:\n    tags: v* # a: tag\n") == []
    assert refused("on:\n  push: # note: x\n    tags: v*\n") == []


def test_a_bad_line_after_a_block_scalar_is_still_refused():
    steps = "jobs:\n  one:\n    steps:\n"
    block = "      - run: |\n          echo a: b\n"
    assert refused(f"{steps}{block}        name: Install: x\n") == [6]
    assert refused(f"{steps}{block}      - name: Install: x\n") == [6]
    assert refused(f"{steps}{block}        name: install\n") == []
    keyed = "      - name: x\n        run: |\n          echo a: b\n"
    assert refused(f"{steps}{keyed}        if: a: b\n") == [7]


VERSION = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]


def released(tmp_path, plugin=VERSION):
    """A repo of the Makefile, pyproject.toml and a plugin.json, on main, pushed to a bare
    origin, for `make release` and `make release-tag` to run in."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
    subprocess.run([*git, "init", "-q", "--bare", origin], check=True)
    subprocess.run([*git, "init", "-q", repo], check=True)
    shutil.copy(REPO / "Makefile", repo)
    shutil.copy(REPO / "pyproject.toml", repo)
    (repo / "plugin.json").write_text(json.dumps({"version": plugin}))
    for args in (["add", "."], ["commit", "-qm", "one"], ["remote", "add", "origin", origin]):
        subprocess.run([*git, "-C", repo, *args], check=True)
    subprocess.run([*git, "-C", repo, "push", "-q", "origin", "main"], check=True)
    return repo, origin, git


def make(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env |= {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(
        ["make", "-s", "-C", repo, *args], env=env, capture_output=True, text=True
    )


def test_the_tag_must_be_the_version_of_pyproject_and_of_plugin_json(tmp_path):
    repo, _, _ = released(tmp_path / "same")
    assert make(repo, "release-tag", f"TAG=v{VERSION}").returncode == 0
    assert make(repo, "release-tag", "TAG=v9.9.9").returncode != 0
    skewed, _, _ = released(tmp_path / "skewed", plugin="9.9.9")
    refused = make(skewed, "release-tag", f"TAG=v{VERSION}")
    assert refused.returncode != 0
    assert "v9.9.9, plugin.json's" in refused.stdout


def test_make_release_tags_a_clean_main_that_is_origins_and_refuses_anything_else(tmp_path):
    repo, origin, git = released(tmp_path)

    def tags():
        listed = subprocess.run(
            ["git", "ls-remote", "--tags", origin], capture_output=True, text=True, check=True
        )
        return [line.split("refs/tags/")[1] for line in listed.stdout.splitlines()]

    subprocess.run([*git, "-C", repo, "checkout", "-qb", "side"], check=True)
    assert "release: not on main" in make(repo, "release").stdout
    subprocess.run([*git, "-C", repo, "checkout", "-q", "main"], check=True)
    (repo / "loose").write_text("")
    assert "release: the checkout is not clean" in make(repo, "release").stdout
    (repo / "loose").unlink()
    subprocess.run([*git, "-C", repo, "commit", "-q", "--allow-empty", "-m", "two"], check=True)
    assert "release: main is not origin/main" in make(repo, "release").stdout
    assert tags() == []
    subprocess.run([*git, "-C", repo, "push", "-q", "origin", "main"], check=True)
    done = make(repo, "release")
    assert done.returncode == 0, done.stderr
    assert tags() == [f"v{VERSION}", f"v{VERSION}^{{}}"]


def test_each_check_jmerge_requires_is_a_job_of_a_pull_request_and_borders_fails_on_a_warning():
    from jmerge import ready

    pulled = {"check": CHECK, "borders": BORDERS}
    assert set(ready.REQUIRED) <= set(pulled)
    for name, workflow in pulled.items():
        assert name in jobs(workflow.read_text())
    (*_, lint), _ = steps(BORDERS.read_text(), "borders")
    assert lint["run"].startswith("python3 scripts/lint-borders.py --hard ")


NO_AI_TRAILERS = REPO / "scripts" / "no_ai_trailers.py"
CLAUDE = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
HUMAN = "Co-authored-by: Ada Lovelace <ada@example.com>"


def test_a_pull_requests_check_fails_on_an_ai_trailer_after_the_suite_whatever_it_said():
    found, _ = steps(CHECK.read_text(), "check-shard")
    (trailer,) = [step for step in found if step.get("name") == "no AI co-author trailer"]
    assert trailer["run"] == "uv run python scripts/no_ai_trailers.py"
    assert trailer["if"] == (
        "!cancelled() && steps.suite.outcome != 'skipped' && matrix.shard == 1"
    )
    assert trailer["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
    assert found.index(trailer) > [step.get("id") for step in found].index("suite")


class Compare:
    """GitHub's compare API for one range, served on localhost a page at a time."""

    def __init__(self, messages):
        import http.server
        import threading
        from urllib.parse import parse_qs, urlsplit

        listed = [{"sha": f"{at:040x}", "commit": {"message": m}} for at, m in enumerate(messages)]
        self.asked = []
        asked = self.asked

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                url = urlsplit(self.path)
                asked.append((url.path, self.headers.get("Authorization")))
                query = parse_qs(url.query)
                size, page = int(query["per_page"][0]), int(query["page"][0])
                body = {"total_commits": len(listed), "commits": listed[(page - 1) * size :][:size]}
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()


def no_ai_trailers(tmp_path, messages, title="feat: a change", body="Why it changed."):
    """Run the check's script on a pull request with these commits, as the step runs it."""
    event = tmp_path / "event.json"
    pull = {"title": title, "body": body, "base": {"sha": "b" * 40}, "head": {"sha": "h" * 40}}
    event.write_text(json.dumps({"pull_request": pull}))
    compare = Compare(messages)
    try:
        ran = subprocess.run(
            [sys.executable, str(NO_AI_TRAILERS)],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "GITHUB_EVENT_PATH": str(event),
                "GITHUB_API_URL": compare.url,
                "GITHUB_REPOSITORY": "owner/repo",
                "GITHUB_TOKEN": "t0ken",
            },
        )
    finally:
        compare.close()
    return ran.returncode, ran.stdout.splitlines(), compare.asked


@pytest.mark.parametrize(
    "line",
    [
        CLAUDE,
        "co-authored-by: claude <claude@example.com>",
        "Co-authored-by: Someone <someone@anthropic.com>",
        "Co-authored-by: Codex <codex@example.com>",
        "Co-authored-by: OpenAI <noreply@openai.com>",
        "Co-authored-by: Cursor Agent <cursoragent@cursor.com>",
        "Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ],
)
def test_a_commit_with_an_ai_trailer_fails_the_check_naming_the_commit_and_the_line(tmp_path, line):
    code, printed, asked = no_ai_trailers(tmp_path, ["feat: one", f"fix: two\n\nWhy.\n\n{line}"])
    assert code == 1
    sha = f"{1:040x}"[:12]
    assert printed[0] == f"::error title=AI co-author trailer::commit {sha} line 5: {line}"
    assert len(printed) == 2
    path = f"/repos/owner/repo/compare/{'b' * 40}...{'h' * 40}"
    assert asked == [(path, "Bearer t0ken")]


def test_a_title_or_a_body_with_an_ai_trailer_fails_the_check_naming_where(tmp_path):
    code, printed, _ = no_ai_trailers(
        tmp_path, ["feat: one"], title="feat: a change", body=f"Why.\n\n{CLAUDE}"
    )
    assert (code, printed[:1]) == (
        1,
        [f"::error title=AI co-author trailer::body line 3: {CLAUDE}"],
    )


def test_a_clean_range_with_a_human_co_author_passes_and_every_page_is_read(tmp_path):
    messages = [f"feat: {at}" for at in range(150)] + [f"fix: last\n\n{HUMAN}"]
    code, printed, asked = no_ai_trailers(tmp_path, messages, body=f"Paired.\n\n{HUMAN}")
    assert (code, printed) == (
        0,
        ["no-ai-trailers: the title, the body and 151 commits carry none"],
    )
    assert len(asked) == 2


def test_a_range_that_cannot_be_read_fails_the_check(tmp_path):
    event = tmp_path / "event.json"
    pull = {"title": "t", "body": None, "base": {"sha": "b"}, "head": {"sha": "h"}}
    event.write_text(json.dumps({"pull_request": pull}))
    env = {**os.environ, "GITHUB_EVENT_PATH": str(event), "GITHUB_REPOSITORY": "owner/repo"}
    ran = subprocess.run(
        [sys.executable, str(NO_AI_TRAILERS)],
        capture_output=True,
        text=True,
        env=env | {"GITHUB_API_URL": "http://127.0.0.1:9"},
    )
    assert ran.returncode == 2
    assert ran.stdout.startswith("::error::no-ai-trailers: the commits could not be read: ")
