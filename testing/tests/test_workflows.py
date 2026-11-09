"""The check workflow runs on main and on each push of a pull request, a draft too. The
next run never cancels a run on either, because each push's run is a concurrency group of its
own. A pull request gets the job `check`, the fast one, which runs the lint and the tests its
change reaches. A push to main, and a manual run, get the job `full`, the whole suite. Each runs
its tests as parts side by side, eight in the job `check-shard` and four in `full-shard`, and
passes only when all of them did.

The test reads the workflow file as YAML with two small readers, `mapping` and `block`, which handle
only mappings by their indentation, a scalar, and a list in brackets.

Every job runs on GitHub's hosted runner, the pinned image `ubuntu-24.04`, and none names a runner
of the owner's machine or reads a repo variable for it. The one exception is the repo standard's
shared check workflow, `repo-standard-check.yml`, which runs only when another repo calls it, on
the runner that caller names. The one other image is `macos-15`, for
two workflows. The workflow `macos`: on each pull request and each push to main its job
`macos-select`, on Linux, picks the test files listed in `testing/macos-quick.txt`, the ones whose
code branches on macOS or that guard a break only a Mac has, that the change reaches, and its job
`macos` runs them on a Mac. A pull request picks with `--strict`, a part of what a push picks.
Where the change reaches none, `macos` is skipped by its `if:` and no Mac starts. No `paths:`
filter skips the workflow, and no push run on main is cancelled. Its check
fails when those tests do, so the home can name it in `required-checks`, and a skip passes it.
The workflow `macos-nightly`: the whole suite on macOS, nightly at 04:00 ET, an hour after the
browser run, and by hand, over the branch its `ref` names, `main` unless a manual run
names another. It runs on no pull request and no push, and no merge waits on it.
Each job has a cap that a hung run meets.
Each context main's ruleset requires (`features/repo-guards/main-ruleset.json`) is the id of a
job in a workflow that runs on every pull request into main, with no `paths:` or `branches:`
filter, and the job skips only by its own `if:`, so no required check stays "Expected".
The browser workflow names its test browser, one Chrome for Testing build pinned by its exact
version and the SHA-256 of its zip, and the check names none.
The tests that open a browser carry the marker `browser`. `make check` leaves them out, and `make
check-browser` runs them: nightly at 03:00 ET, on a `v*` tag or a published release, by hand, and
on a pull request into main that changes the view, its browser tests, their kept shots or the
browser workflow and is not a draft, but
never on a push to main. Every workflow gets read access to the contents and
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
workflow names the same one: with no version, setup-uv fetches the latest release on each job.

The module reads every file under `.github/` and the files the TLC cache's key hashes, the spec
files and statechart's scripts, through globs: its `READ_SET` names them, so a change runs these
tests only where it reaches one of them, or a path the tests spell or import, and not else.

This module is not on `testing/macos-quick.txt`: what it tests reads a workflow or runs on
`ubuntu-24.04`, `macos-select`'s selection among them. The cases that run a step of `macos-15`,
or a `make release` target a desk runs, are `test_workflows_mac.py`, which the Mac runs."""

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
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
MAC = WORKFLOWS / "macos.yml"
SHARED = WORKFLOWS / "repo-standard-check.yml"
MAC_QUICK = REPO / "testing" / "macos-quick.txt"
GREEN_TREE = REPO / "scripts" / "green_tree.py"
READ_SET = ("/.github/", "spec/", "statechart/")
HOSTED = "ubuntu-24.04"
CALLERS = "${{ inputs.runner }}"
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
    return text_block(name, path.read_text())


def text_block(name, text):
    """One top-level block of a workflow's text, as a mapping."""
    lines = [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
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


def test_the_check_runs_on_a_pull_request_into_any_branch_on_each_push_to_main_and_by_hand():
    """A pull request into any branch gets a run: one into main or a merge base, so jmerge can
    merge it there on a green check, and one stacked on a parent row's branch, so it is checked
    while it is stacked and its move onto main reuses the pass (`reuse`). Of a pull request, a
    push, a reopen and the mark that it is ready start one: the mark is browser.yml's, which
    has these types and skips a draft."""
    assert block("on") == {
        "pull_request": {"types": ["opened", "synchronize", "reopened", "ready_for_review"]},
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }


def worked(expression, values):
    """Return what a workflow expression gives with these values for its names. This function
    works the expression out itself, without GitHub.

    It reads `&&`, `||`, `!`, `==`, `!=` and a string in single quotes.
    """
    for name in sorted(values, key=len, reverse=True):
        expression = expression.replace(name, repr(values[name]))
    expression = re.sub(r"!(?!=)", " not ", expression)
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
        "check.yml": {
            "reuse": HOSTED,
            "lint": HOSTED,
            "check-shard": HOSTED,
            "check": HOSTED,
            "select-facts": HOSTED,
            "full-shard": HOSTED,
            "full": HOSTED,
        },
        "macos-nightly.yml": {"macos": MACOS},
        "macos.yml": {"macos-select": HOSTED, "macos-part": MACOS, "macos": HOSTED},
        "pstack-drift.yml": {"drift": HOSTED},
        "release.yml": {"release": HOSTED},
        "repo-standard-check.yml": dict.fromkeys(
            ("plan", "lint", "test", "command", "passed"), CALLERS
        ),
    }


def test_no_file_under_github_names_a_runner_of_the_owners_machine_or_its_variable():
    for path in sorted(WORKFLOWS.parent.rglob("*")):
        if path.is_file():
            text = path.read_text()
            for name in ("self-hosted", "jstack-fast", "jstack-ephemeral", "RUNS_ON"):
                assert name not in text, (path.name, name)


def test_every_workflow_may_read_the_contents_and_no_more_and_none_runs_for_a_fork_with_secrets():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        more = {"actions": "read"} if path in (CHECK, MAC, RELEASE, SHARED) else {}
        contents = "write" if path == RELEASE else "read"
        assert block("permissions", path) == {"contents": contents} | more, path.name
        assert "pull_request_target" not in path.read_text(), path.name


CHROME = {"JSTACK_TEST_BROWSER": "/tmp/chrome-for-testing/chrome-linux64/chrome"}


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


def test_the_browser_job_names_chrome_for_testing_once_and_the_check_jobs_name_no_browser():
    text = BROWSER.read_text()
    assert job_env(text, "browser") == CHROME | {"JSTACK_SHOTS_OUT": "/tmp/jbus-view-shots"}
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
    from jbus import shots

    found, _ = steps(BROWSER.read_text(), "browser")
    names = [step.get("name") for step in found]
    look = found[names.index("test browser")]
    assert names.index("make check-browser") == names.index("test browser") + 1
    assert names.index("test browser") == names.index("chrome for testing") + 1
    assert names[-2:] == ["make check-browser", "the view's shots"] and "if" not in look
    assert found[-1]["if"] == "failure()"
    assert found[-1]["with"]["name"] == shots.ARTIFACT
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


def test_the_browser_is_one_exact_chrome_for_testing_build_named_once():
    """The image's own Chrome moves under a rollout, from one runner to the next, and every shot
    of the view then fails on the runners whose build is not the shots'. The workflow names one
    build, by its exact version and the SHA-256 of its zip, once each."""
    text = BROWSER.read_text()
    pin = block("env", BROWSER)
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", pin["CHROME_VERSION"]), pin["CHROME_VERSION"]
    assert re.fullmatch(r"[0-9a-f]{64}", pin["CHROME_SHA256"]), pin["CHROME_SHA256"]
    assert text.count("CHROME_VERSION:") == text.count("CHROME_SHA256:") == 1


@pytest.mark.parametrize("zip_is", ["the pinned one", "another"])
def test_the_chrome_step_unpacks_the_pinned_build_only_when_its_zip_is_the_pinned_one(
    tmp_path, zip_is
):
    """The step runs here as written, under bash, with a stand-in `curl` that serves a zip made
    here and logs the address it was asked for: it fetches the pinned version from Google's
    bucket, and unpacks and runs the browser only when the zip's SHA-256 is the pinned one."""
    (step,) = [
        s for s in steps(BROWSER.read_text(), "browser")[0] if s.get("name") == "chrome for testing"
    ]
    served = tmp_path / "served.zip"
    with zipfile.ZipFile(served, "w") as made:
        chrome = zipfile.ZipInfo("chrome-linux64/chrome")
        chrome.external_attr = 0o100755 << 16
        made.writestr(chrome, '#!/bin/sh\necho "Google Chrome for Testing 1.2.3.4"\n')
    bin, temp, log = tmp_path / "bin", tmp_path / "temp", tmp_path / "log"
    bin.mkdir()
    temp.mkdir()
    (bin / "curl").write_text(
        "#!/bin/sh\nwhile [ $# -gt 0 ]; do case $1 in\n"
        '-o) out=$2; shift;; http*) echo "$1" >> "$LOG";;\n'
        'esac; shift; done\ncp "$SERVED" "$out"\n'
    )
    (bin / "curl").chmod(0o755)
    for name in ("sha256sum", "unzip", "cp", "sh"):
        (bin / name).symlink_to(shutil.which(name))
    pinned = block("env", BROWSER)
    digest = subprocess.run(["sha256sum", str(served)], capture_output=True, text=True, check=True)
    sha = digest.stdout.split()[0] if zip_is == "the pinned one" else pinned["CHROME_SHA256"]
    browser = tmp_path / "cft" / "chrome-linux64" / "chrome"
    env = {
        **pinned,
        "CHROME_SHA256": sha,
        "PATH": str(bin),
        "RUNNER_TEMP": str(temp),
        "LOG": str(log),
        "SERVED": str(served),
        "JSTACK_TEST_BROWSER": str(browser),
    }
    ran = subprocess.run(
        [shutil.which("bash"), "-ec", step["run"]], env=env, capture_output=True, text=True
    )
    version = pinned["CHROME_VERSION"]
    assert log.read_text().split() == [
        f"https://storage.googleapis.com/chrome-for-testing-public/{version}/linux64/chrome-linux64.zip"
    ]
    if zip_is == "the pinned one":
        assert ran.returncode == 0, ran.stderr
        assert ran.stdout.splitlines()[-1] == "Google Chrome for Testing 1.2.3.4"
    else:
        assert ran.returncode != 0
        assert not browser.exists()


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
    """The steps of one job, each as the keys written on it, and the job's own keys. A value
    folded with `>-` is read as its lines joined by spaces."""
    found, keys, inside, at, folded = [], [], False, None, None
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent < 10:
            folded = None
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
        elif at is not None and indent == 10 and found[-1][key] == ">-":
            found[-1][key], folded = line.strip(), key
        elif at is not None and indent == 10 and key == folded:
            found[-1][key] += " " + line.strip()
    return found, keys


def test_steps_are_read_with_their_own_keys_and_the_job_with_its_own():
    text = (
        "jobs:\n  other:\n    if: false\n    steps:\n      - run: true\n"
        "  check:\n    runs-on: x\n    steps:\n      - uses: a/b@1 # v1\n        with:\n"
        "          if: no\n          depth: 2\n      - name: one\n        if: a != 'b'\n"
        "        run: make check\n      - run: >-\n          make\n          check\n"
    )
    assert steps(text, "check") == (
        [
            {"uses": "a/b@1", "with": {"if": "no", "depth": "2"}},
            {"name": "one", "if": "a != 'b'", "run": "make check"},
            {"run": "make check"},
        ],
        ["runs-on", "steps"],
    )
    assert steps(text, "other") == ([{"run": True}], ["if", "steps"])


def job_value(text, job, key):
    """One key of a job, as the job says it, and None when the job has no such key."""
    inside = False
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if indent <= 2 and line.strip() and not line.lstrip().startswith("#"):
            inside = line.strip() == f"{job}:" and indent == 2
        elif inside and indent == 4 and line.strip().startswith(f"{key}:"):
            return scalar(line.partition(":")[2])
    return None


def cap(text, job):
    """The minutes after which GitHub cancels one job, as the job says them."""
    return job_value(text, job, "timeout-minutes")


CAPS = {
    ("borders.yml", "borders"): "5",
    ("browser.yml", "browser"): "15",
    ("check.yml", "reuse"): "5",
    ("check.yml", "lint"): "10",
    ("check.yml", "check-shard"): "30",
    ("check.yml", "check"): "20",
    ("check.yml", "select-facts"): "5",
    ("check.yml", "full-shard"): "30",
    ("check.yml", "full"): "5",
    ("macos-nightly.yml", "macos"): "90",
    ("macos.yml", "macos-select"): "5",
    ("macos.yml", "macos-part"): "25",
    ("macos.yml", "macos"): "5",
    ("pstack-drift.yml", "drift"): "5",
    ("release.yml", "release"): "15",
    ("repo-standard-check.yml", "plan"): "10",
    ("repo-standard-check.yml", "lint"): "15",
    ("repo-standard-check.yml", "test"): "${{ inputs.timeout-minutes }}",
    ("repo-standard-check.yml", "command"): "${{ inputs.timeout-minutes }}",
    ("repo-standard-check.yml", "passed"): "5",
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
ZSH = (
    'cd "$RUNNER_TEMP" && set -- $ZSH_DEBS && printf "%s  %s\\n" $ZSH_DEBS > zsh.sha256'
    ' && curl -fsSL --retry 3 --remote-name-all "$ZSH_POOL/$2" "$ZSH_POOL/$4"'
    ' && sha256sum -c zsh.sha256 && sudo dpkg -i "$2" "$4" && zsh --version'
)
SUITE = 'make check JUNIT="$RUNNER_TEMP/junit.xml" SHARD=${{ matrix.shard }}/4'
TLC = "~/.cache/jstack/tlc"
KEPT = (
    'RUNS=$(LC_ALL=C ls "$HOME/.cache/jstack/tlc" 2> /dev/null) || exit 0;'
    ' NAMES=$(printf "%s\\n" "$RUNS" | sha256sum | cut -c1-16);'
    ' [ -z "$RUNS" ] || [ "$NAMES" = "${RESTORED##*-}" ]'
    ' || echo "key=$KEY$NAMES" >> "$GITHUB_OUTPUT"'
)


EVENTS = ("pull_request", "push", "workflow_dispatch")


def ran_on(job, draft=False, reused=""):
    """Return the events a job of the check runs on, for a pull request that is a draft or not,
    in a run that is not cancelled and whose `reuse` gave `reused`. This function works them out
    from the job's `if`."""
    inside, when = False, None
    for line in CHECK.read_text().splitlines():
        indent = len(line) - len(line.lstrip())
        if indent <= 2 and line.strip() and not line.lstrip().startswith("#"):
            inside = indent == 2 and line.strip() == f"{job}:"
        elif inside and indent == 4 and line.startswith("    if: "):
            when = line.partition(": ")[2].strip('"')
    return [
        e
        for e in EVENTS
        if worked(
            when,
            {
                "always()": True,
                "!cancelled()": True,
                "needs.reuse.outputs.reused": reused,
                "github.event_name": e,
                "github.event.pull_request.draft": draft if e == "pull_request" else None,
            },
        )
    ]


def test_a_pull_request_runs_check_and_a_push_to_main_and_a_manual_run_run_full():
    assert jobs(CHECK.read_text()) == {
        "reuse": HOSTED,
        "lint": HOSTED,
        "check-shard": HOSTED,
        "check": HOSTED,
        "select-facts": HOSTED,
        "full-shard": HOSTED,
        "full": HOSTED,
    }
    pull, push = ["pull_request"], ["push", "workflow_dispatch"]
    named = ("reuse", "lint", "check-shard", "check", "select-facts", "full-shard", "full")
    assert [ran_on(job) for job in named] == [pull, pull, pull, pull, push, push, push]


def test_a_draft_runs_the_check_as_any_pull_request_does():
    """A crew opens its pull request ready (fl-no-draft), and the check guards no draft: a draft
    someone opened by hand is checked on each push too, so jmerge reads its checks as any
    pull request's."""
    pull, push = ["pull_request"], ["push", "workflow_dispatch"]
    named = ("reuse", "lint", "check-shard", "check", "select-facts", "full-shard", "full")
    ran = [pull, pull, pull, pull, push, push, push]
    assert [ran_on(job, draft=True) for job in named] == ran
    assert [ran_on(job, draft=False) for job in named] == ran


def job_section(job, key, path=CHECK):
    """One mapping key of a job, `strategy` or `outputs`, as a mapping."""
    lines, inside, at = [], False, None
    for line in path.read_text().splitlines():
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


PARTS = {"check-shard": [str(k) for k in range(1, 9)], "full-shard": ["1", "2", "3", "4"]}
RESULTS = ("success", "failure", "cancelled", "skipped")


@pytest.mark.parametrize("gate,parts", [("check", "check-shard"), ("full", "full-shard")])
def test_the_suite_runs_as_parts_side_by_side_and_one_job_passes_only_when_all_did(
    gate, parts, tmp_path
):
    """The ruleset and jmerge require the job named `check`, so it stays one job: it waits on the
    parts whatever they did, and this runs its first step on each result GitHub can give. The
    check runs eight parts, so that its wall is half of four's, and the full run four."""
    count = len(PARTS[parts])
    assert job_section(parts, "strategy") == {"fail-fast": False, "matrix": {"shard": PARTS[parts]}}
    assert job_line(parts, "name") == f"{gate} ${{{{ matrix.shard }}}} of {count}"
    assert job_line(gate, "needs") == (
        ["reuse", "lint", "check-shard"] if gate == "check" else parts
    )
    assert job_line(gate, "if").startswith("always() && ")
    (every, *_), _ = steps(CHECK.read_text(), gate)
    assert every["env"]["PARTS"] == f"${{{{ needs.{parts}.result }}}}"
    ran = {
        result: subprocess.run(
            ["sh", "-c", every["run"]],
            env={"PARTS": result, "LINT": "success", "REUSE": "success"},
            capture_output=True,
            text=True,
        )
        for result in RESULTS
    }
    assert [result for result in RESULTS if ran[result].returncode == 0] == ["success"]
    assert all("::error::" in ran[result].stdout for result in RESULTS[1:])
    suite = " ".join(map(str, steps(CHECK.read_text(), parts)[0]))
    assert (f"SHARD=${{{{ matrix.shard }}}}/{count}" in suite) == (gate == "full")


MAC_GROUP = "github.event_name == 'push' && github.sha || github.ref"


def test_macos_runs_on_each_pull_request_and_each_push_to_main_and_never_cancels_one_on_main():
    """Each merge commit into main gets a macos run of its own, which no later merge cancels, so a
    Mac red names its merge. A pull request's newer run cancels its older one."""
    assert block("on", MAC) == {"pull_request": None, "push": {"branches": ["main"]}}
    assert block("concurrency", MAC) == {
        "group": "macos-${{ " + MAC_GROUP + " }}",
        "cancel-in-progress": "${{ github.event_name == 'pull_request' }}",
    }
    cancels = block("concurrency", MAC)["cancel-in-progress"]
    cancels = cancels.removeprefix("${{ ").removesuffix(" }}")
    assert [worked(cancels, {"github.event_name": e}) for e in ("pull_request", "push")] == [
        True,
        False,
    ]

    def group(event, sha):
        names = {"github.event_name": event, "github.sha": sha, "github.ref": "refs/pull/9/merge"}
        return worked(MAC_GROUP, names)

    assert group("pull_request", "a") == group("pull_request", "b") == "refs/pull/9/merge"
    assert [group("push", "a"), group("push", "b")] == ["a", "b"]


def path_filters(text):
    """Each line of a workflow that sets a `paths:` or `paths-ignore:` key, comments left out."""
    return [
        line
        for line in text.splitlines()
        if re.match(r"\s*(paths|paths-ignore)\s*:", line.split("#")[0])
    ]


def test_macos_has_no_paths_filter_so_its_required_check_always_posts():
    """A run a `paths:` filter leaves out posts no `macos` check at all, and jmerge waits on a
    required check that never ran (`jmerge.ready.passed`): the line is stuck. The macos workflow
    skips its Mac only by the selection and the job's `if:`, a skip that passes the check."""
    assert path_filters(MAC.read_text()) == []
    assert path_filters("on:\n  pull_request:\n    paths: ['a/**']\n") != []
    assert path_filters("on:\n  push:\n    paths-ignore:\n      - docs/**\n") != []


RULESET = REPO / "features" / "repo-guards" / "main-ruleset.json"
EVERY_PUSH = {"opened", "synchronize", "reopened"}


def ruleset_contexts():
    """The contexts main's ruleset file requires."""
    rules = json.loads(RULESET.read_text())["rules"]
    (found,) = [rule["parameters"] for rule in rules if rule["type"] == "required_status_checks"]
    return sorted(one["context"] for one in found["required_status_checks"])


def events(text):
    """The events a workflow runs on, the keys of its `on:` block."""
    lines, inside = [], False
    for line in text.splitlines():
        if line.strip() and not line.startswith(" "):
            inside = line.strip() == "on:"
        elif inside and re.match(r"  [a-z_]+:", line):
            lines.append(line.strip().partition(":")[0])
    return lines


def unreported(context, workflows):
    """Why a required context could fail to post on a pull request into main, given each
    workflow's name and text: nothing when one workflow that runs on every pull request, with no
    `paths:` and no `branches:` filter, has a job with that id, and the job skips only by its own
    `if:`. A check that never posts stays "Expected" and no pull request can merge."""
    found = [
        (name, text)
        for name, text in workflows.items()
        if context in jobs(text) and "pull_request" in events(text)
    ]
    if len(found) != 1:
        return [f"{context}: {len(found)} pull_request workflows have a job of that id"]
    (name, text), why = found[0], []
    on = text_block("on", text)["pull_request"] or {}
    why += [f"{name}: pull_request has {key}" for key in on if key != "types"]
    if "types" in on and not set(on["types"]) >= EVERY_PUSH:
        why.append(f"{name}: pull_request types {on['types']} leave out a push")
    why += [f"{name}: {line.strip()}" for line in path_filters(text)]
    if job_value(text, context, "name") is not None:
        why.append(f"{name}: job {context} posts as its name, not its id")
    gate = str(job_value(text, context, "if") or "")
    if job_value(text, context, "needs") and not gate.startswith(("always()", "!cancelled()")):
        why.append(f"{name}: job {context} skips when a job it needs does, not by its own if:")
    return why


def test_every_context_the_ruleset_requires_posts_on_every_pull_request_into_main():
    """A required context is a job id that posts on every pull request into main, so requiring
    it can never stall the line: no `paths:` or `branches:` filter leaves its workflow out, and
    the job skips only by its own `if:`, a skip that passes the check."""
    workflows = {path.name: path.read_text() for path in sorted(WORKFLOWS.glob("*.yml"))}
    assert ruleset_contexts() == ["borders", "check", "macos"]
    assert {context: unreported(context, workflows) for context in ruleset_contexts()} == {
        context: [] for context in ruleset_contexts()
    }

    def changed(name, old, new):
        assert workflows[name].count(old) == 1, (name, old)
        return {**workflows, name: workflows[name].replace(old, new)}

    pr = "  pull_request:\n"
    assert unreported("macos", changed("macos.yml", pr, pr + "    paths: ['a/**']\n"))
    assert unreported("macos", changed("macos.yml", pr, pr + "    branches: [main]\n"))
    assert unreported(
        "macos",
        changed(
            "macos.yml",
            'macos-part]\n    if: "!cancelled() && needs.macos-select',
            'macos-part]\n    if: "needs.macos-select',
        ),
    )
    assert unreported("borders", changed("borders.yml", "\n  borders:\n", "\n  lint:\n"))
    assert unreported("borders", changed("borders.yml", "opened, synchronize, ", "opened, "))
    assert unreported("check", changed("check.yml", "  check:\n", "  check:\n    name: c\n"))


def test_the_macos_job_fails_its_check_when_the_suite_fails_so_a_merge_can_wait_on_it():
    """macOS on Apple Silicon is supported, so `macos` is a required check: the home's
    `required-checks` names it beside `check` and `borders`, and jmerge waits on it. A job's or a
    step's `continue-on-error` reports the check as passed whatever the suite did, so neither a
    part nor `macos` nor any step that sets up or runs the tests carries it. Only the part's step
    that lists the failed tests does, and the upload of the marker of passed parts, which run
    after the tests and change nothing they decided. A part's tests' step cap is then a failure
    of the check too, so it leaves the slowest run of the whole list on one Mac twice its time:
    the step took 423 to 639 s on twelve runs, and the list grows with each mac- fix."""
    from jmerge import ready

    rollup = [
        {"name": name, "status": "COMPLETED", "conclusion": "SUCCESS"}
        for name in ("check", "borders")
    ] + [{"name": "macos", "status": "COMPLETED", "conclusion": "FAILURE"}]
    assert ready.waiting(rollup, ready.required_of("check\nborders\nmacos\n")) == ("macos",)
    text = MAC.read_text()
    assert job_value(text, "macos", "continue-on-error") is None
    assert job_value(text, "macos-part", "continue-on-error") is None
    found, _ = steps(text, "macos-part")
    held = [step.get("name", step.get("uses")) for step in found if "continue-on-error" in step]
    assert held == ["failed tests"]
    gate, _ = steps(text, "macos")
    held = [step.get("name", step.get("uses")) for step in gate if "continue-on-error" in step]
    assert held == [gate[-1]["uses"]]
    assert gate[-1]["uses"].startswith("actions/upload-artifact@")
    (suite,) = [step for step in found if step.get("id") == "suite"]
    assert 2 * 639 <= 60 * int(suite["timeout-minutes"]) < 60 * int(cap(text, "macos-part")) - 120


REACHED = "macos-reached.txt"


def outputs(text):
    """A step's outputs, as GitHub reads them from `$GITHUB_OUTPUT`: `name=value` lines, and
    `name<<DELIMITER` with the value's lines up to the delimiter's own line."""
    found, lines = {}, iter(text.splitlines())
    for line in lines:
        if "<<" in line and "=" not in line.partition("<<")[0]:
            name, _, end = line.partition("<<")
            found[name] = "\n".join(iter(lines.__next__, end))
        else:
            name, _, value = line.partition("=")
            found[name] = value
    return found


QUEUE = "features/jbus/src/jbus/queue.py"
DARWIN_LISTED = "features/jgauge/tests/test_machine_sizes.py"
DARWIN_SOURCE = "features/jbus/src/jbus/launchd.py"
DARWIN_CODE = '\n\ndef on_a_mac():\n    return sys.platform == "darwin"\n'
"""A function that branches on Darwin: a pull request's `--strict` counts a change to a module
on a Mac only where it edits one."""


@pytest.fixture(scope="module")
def merged(tmp_path_factory):
    """Run the macos-select job's selection step, as the runner does, on a pull request's merge
    commit whose one change over main is text added to a path: a blank line by default, and
    `DARWIN_CODE` to `DARWIN_SOURCE`, so that change is to code that branches on Darwin. main is
    this repo's HEAD with the selection's files as they are here. It gives the paths the step
    wrote, its summary and its outputs, read as GitHub reads them."""
    root = tmp_path_factory.mktemp("mac")
    repo, bin = root / "repo", root / "bin"
    git = ["git", "-c", "user.name=a", "-c", "user.email=a@example.com", "-C", str(repo)]
    subprocess.run(["git", "clone", "-q", "--shared", str(REPO), str(repo)], check=True)
    for path in ("scripts/select_tests.py", "testing/macos-quick.txt"):
        shutil.copy(REPO / path, repo / path)
    subprocess.run([*git, "commit", "-qam", "main", "--allow-empty"], check=True)
    main = subprocess.run(
        [*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    bin.mkdir()
    (bin / "uv").write_text(f'#!/bin/sh\n[ "$1" = run ] && shift 2\nexec {sys.executable} "$@"\n')
    (bin / "uv").chmod(0o755)
    shell = summary_step("reached tests", MAC)

    def run(path, text=None, event="pull_request"):
        text = text or (DARWIN_CODE if path == DARWIN_SOURCE else "\n")
        subprocess.run([*git, "reset", "-q", "--hard", main], check=True)
        with (repo / path).open("a") as file:
            file.write(text)
        subprocess.run([*git, "commit", "-qam", f"change {path}"], check=True)
        temp = root / path.replace("/", "-")
        temp.mkdir(exist_ok=True)
        out = {name: temp / name for name in ("summary", "output")}
        for one in out.values():
            one.write_text("")
        subprocess.run(
            ["bash", "-e", "-c", shell],
            cwd=repo,
            env={"PATH": f"{bin}:/usr/bin:/bin", "RUNNER_TEMP": str(temp)}
            | {"GITHUB_STEP_SUMMARY": str(out["summary"]), "GITHUB_OUTPUT": str(out["output"])}
            | {"GITHUB_EVENT_NAME": event},
            capture_output=True,
            check=True,
        )
        reached = (temp / REACHED).read_text().splitlines()
        return reached, out["summary"].read_text(), outputs(out["output"].read_text())

    return run


def dealt(reached):
    """The parts `macos-select` hands on for these test files: one a file, at most three."""
    return "[" + ",".join(str(k) for k in range(1, min(3, len(reached)) + 1)) + "]"


def test_the_macos_job_starts_no_mac_for_a_change_to_a_jbus_queue_module(merged):
    """A change to code that names no Darwin, as most of flow's pull requests make to jbus's
    queue, reaches no test of the list on a Mac: the selection hands on no test and `run` false,
    which skips the `macos` job, and its summary says so in one line."""
    assert merged(QUEUE) == (
        [],
        "macOS: the change reaches no test of testing/macos-quick.txt, so no Mac starts\n",
        {"run": "false", "parts": "[1]", "tests": ""},
    )


@pytest.mark.parametrize(
    ("path", "test", "unreached"),
    [
        (DARWIN_LISTED, DARWIN_LISTED, "features/jgauge/tests/test_room.py"),
        (DARWIN_SOURCE, "features/jbus/tests/test_jbus_launchd.py", None),
    ],
    ids=["a listed test", "a module"],
)
def test_the_macos_job_runs_the_tests_of_the_list_a_change_to_darwin_code_reaches(
    merged, path, test, unreached
):
    """A change to a test of the list that branches on Darwin runs that test, and only tests of
    the list. A change to a module that names Darwin runs the tests of the list that import it.
    The summary names each test it runs. A test that reads the whole tree runs on Linux, and a
    change to Darwin code reaches it on a Mac only through an import."""
    entries = MAC_QUICK.read_text().split()
    reached, summary, output = merged(path)
    assert test in reached
    assert unreached not in reached
    assert all(
        one in entries or any(e.endswith("/") and one.startswith(e) for e in entries)
        for one in reached
    )
    assert summary.splitlines() == [
        f"macOS: the change reaches {len(reached)} test files of testing/macos-quick.txt:",
        *(f"- `{one}`" for one in reached),
    ]
    assert output == {"run": "true", "parts": dealt(reached), "tests": "\n".join(reached)}


@pytest.mark.parametrize("event", ["pull_request", "push"], ids=["its pull request", "its push"])
@pytest.mark.parametrize(
    "path", ["features/crew/verify.md", "README.md"], ids=["a feature's page", "a doc"]
)
def test_a_pull_requests_macos_selects_strictly_and_the_push_of_its_merge_runs_the_rest(
    merged, path, event
):
    """A pull request selects with `--strict`: a change to code off Darwin starts no Mac there.
    The push of its merge commit into main selects with `--within` alone and runs the list's tests
    that the change reaches by a feature or a name. Each case runs one selection of the whole tree,
    and that the push runs every test the pull request ran is
    `test_a_pull_requests_strict_macos_selects_a_part_of_what_the_push_of_its_merge_does`."""
    reached, summary, output = merged(path, event=event)
    if event == "pull_request":
        assert (reached, output["run"]) == ([], "false")
        assert summary.startswith("macOS: the change reaches no test")
    else:
        assert reached and output == {
            "run": "true",
            "parts": dealt(reached),
            "tests": "\n".join(reached),
        }
        assert summary.startswith(f"macOS: the change reaches {len(reached)} test files")


@pytest.mark.parametrize("path", [DARWIN_LISTED, DARWIN_SOURCE], ids=["a listed test", "a module"])
def test_a_pull_requests_strict_macos_selects_a_part_of_what_the_push_of_its_merge_does(
    merged, path
):
    """A change to Darwin code that reaches tests of the list on a pull request reaches each of
    them on the push of its merge too: `--strict` selects a part of what `--within` does, so the
    push runs every test the pull request ran."""
    reached = merged(path)[0]
    assert reached and set(reached) <= set(merged(path, event="push")[0])


@pytest.mark.parametrize(
    "path", ["Makefile", "testing/paths.py"], ids=["the Makefile", "a module of the fixtures"]
)
def test_a_pull_requests_strict_macos_runs_the_whole_list_for_no_plumbing_its_push_does(
    merged, path
):
    """A change to a file every test loads, but that changes no Mac run by itself, runs the whole
    list on the push of its merge, and on its pull request only the list's tests that import or
    name it."""
    whole = MAC_QUICK.read_text().splitlines()
    assert merged(path, event="push")[0] == whole
    reached, summary, _ = merged(path)
    assert reached != whole
    assert not summary.startswith("macOS: the selection is all")


ADDED = "features/jbus/tests/test_item.py"


@pytest.mark.parametrize(
    ("path", "text", "listed"),
    [
        ("uv.lock", "\n", []),
        ("testing/macos-quick.txt", f"{ADDED}\n", [ADDED]),
        (QUEUE, "def (\n", []),
    ],
    ids=["a lock file", "the list itself", "a module that does not parse"],
)
def test_the_macos_job_runs_the_whole_list_where_the_selection_is_all(merged, path, text, listed):
    """A change to the list runs the whole list as the change leaves it, the new entry included.
    A change the selection cannot read, here a module with a syntax error, also runs it whole."""
    reached, summary, output = merged(path, text)
    assert reached == MAC_QUICK.read_text().splitlines() + listed
    assert summary == "macOS: the selection is all, so every test of testing/macos-quick.txt runs\n"
    assert output == {"run": "true", "parts": dealt(reached), "tests": "\n".join(reached)}


def test_the_macos_job_runs_only_where_the_selection_handed_on_a_test_or_failed():
    """The parts and `macos` wait on `macos-select`, and their `if:` skips them, with no Mac
    started, only where the selection ended with no test or reused a passed macos job of the same
    two trees: a skip passes the required check. A failed or cancelled selection gives no `run`
    and no `reused`, so they run then, unless the run was cancelled, and a part's first step
    fails it. Every step of a part that sets up or runs the tests runs once it starts."""
    text = MAC.read_text()
    assert job_value(text, "macos-part", "needs") == "macos-select"
    assert job_value(text, "macos", "needs") == ["macos-select", "macos-part"]
    assert job_value(text, "macos-select", "runs-on") == HOSTED
    when = job_value(text, "macos-part", "if")
    assert job_value(text, "macos", "if") == when
    for run, reused, cancelled, runs in (
        ("true", "false", False, True),
        ("false", "false", False, False),
        ("", "", False, True),
        ("", "false", False, True),
        ("", "true", False, False),
        ("true", "true", False, False),
        ("true", "false", True, False),
    ):
        values = {"!cancelled()": not cancelled, "needs.macos-select.outputs.run": run}
        values["needs.macos-select.outputs.reused"] = reused
        assert worked(when, values) is runs, (run, reused, cancelled)
    found, _ = steps(text, "macos-part")
    assert found[0]["name"] == "handed tests"
    assert [step["name"] for step in found if "if" in step] == ["failed tests"]


@pytest.mark.parametrize("files", [0, 1, 2, 3, 31])
def test_macos_deals_the_selection_into_up_to_three_parts_and_fails_when_one_part_fails(
    tmp_path, files
):
    """The tests `macos-select` hands on run on a Mac for each part it names, one a test file
    and at most three, side by side: each part keeps its share with `--shard K/N`, dealt by
    testing/shard.py from the recorded times, so the parts end together. The required check
    `macos` is one job on Linux that waits on the parts whatever they did, and this runs its
    first step on each result GitHub gives the matrix: it passes only when every part passed,
    so one part that fails, is cancelled or never ran fails the check."""
    shell = summary_step("reached tests", MAC)
    bin = tmp_path / "bin"
    bin.mkdir()
    listed = MAC_QUICK.read_text().splitlines()[:files]
    said = "\n".join(listed)
    (bin / "uv").write_text(f"#!/bin/sh\nprintf '%s' '{said}'\n")
    (bin / "uv").chmod(0o755)
    out = {name: tmp_path / name for name in ("summary", "output")}
    for one in out.values():
        one.write_text("")
    subprocess.run(
        ["bash", "-e", "-c", shell],
        cwd=REPO,
        env={"PATH": f"{bin}:/usr/bin:/bin", "RUNNER_TEMP": str(tmp_path)}
        | {"GITHUB_STEP_SUMMARY": str(out["summary"]), "GITHUB_OUTPUT": str(out["output"])}
        | {"GITHUB_EVENT_NAME": "pull_request"},
        check=True,
    )
    handed = outputs(out["output"].read_text())
    assert json.loads(handed["parts"]) == list(range(1, max(1, min(3, files)) + 1))
    assert handed["run"] == ("true" if files else "false")
    assert job_section("macos-part", "strategy", MAC) == {
        "fail-fast": False,
        "matrix": {"part": "${{ fromJSON(needs.macos-select.outputs.parts || '[1]') }}"},
    }
    assert job_value(MAC.read_text(), "macos-part", "name") == (
        "macos ${{ matrix.part }} of ${{ strategy.job-total }}"
    )
    (every, *_), _ = steps(MAC.read_text(), "macos")
    assert every["env"] == {"PARTS": "${{ needs.macos-part.result }}"}
    ran = {
        result: subprocess.run(
            ["sh", "-c", every["run"]], env={"PARTS": result}, capture_output=True, text=True
        )
        for result in RESULTS
    }
    assert [result for result in RESULTS if ran[result].returncode == 0] == ["success"]
    assert all("::error::" in ran[result].stdout for result in RESULTS[1:])


MAC_WORKFLOW = ".github/workflows/macos.yml"
OTHER_TREE = "0" * 40


def mac_reuse(tmp_path, left, **env):
    """Run the `reuse` step of `macos-select`, as the runner does, in a repo of two commits, a
    base and a merge over it, against a `gh` that answers as GitHub does: `left(base, merge)`, of
    the two trees, maps each artifact run 7 left to that run's answer, and a name it does not map
    has no artifact. Return the step's outputs, what it printed, its summary, the name of this
    pair's marker, and the paths it asked."""
    repo, bin = tmp_path / "repo", tmp_path / "bin"
    for made in (repo, bin):
        made.mkdir()
    git = ["git", "-c", "user.name=a", "-c", "user.email=a@example.com", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True)
    for text in ("base\n", "merge\n"):
        (repo / "file").write_text(text)
        subprocess.run([*git, "add", "file"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", text.strip()], check=True)
    trees = subprocess.run(
        [*git, "rev-parse", "HEAD^1^{tree}", "HEAD^{tree}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    (repo / "features").symlink_to(REPO / "features")
    answers = {}
    for name, ran in left(*trees).items():
        answers[f"{ARTIFACTS}?name={name}&per_page=100"] = marker()
        if ran is not None:
            answers[RUN] = ran
    (tmp_path / "answers.json").write_text(json.dumps(answers))
    (bin / "python3").symlink_to(sys.executable)
    (bin / "git").symlink_to(shutil.which("git"))
    (bin / "gh").write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        f"here = pathlib.Path({str(tmp_path)!r})\n"
        "with open(here / 'asked', 'a') as asked:\n"
        "    asked.write(sys.argv[2] + '\\n')\n"
        "answers = json.loads((here / 'answers.json').read_text())\n"
        "if sys.argv[2] in answers:\n"
        "    print(json.dumps(answers[sys.argv[2]]))\n"
        "elif '/artifacts?' in sys.argv[2]:\n"
        "    print(json.dumps({'total_count': 0, 'artifacts': []}))\n"
        "else:\n"
        "    sys.exit('HTTP 404: Not Found')\n"
    )
    (bin / "gh").chmod(0o755)
    out = {name: tmp_path / name for name in ("summary", "output")}
    for one in out.values():
        one.write_text("")
    ran = subprocess.run(
        ["bash", "-e", "-c", summary_step("reuse", MAC)],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin}:/usr/bin:/bin",
            "GITHUB_OUTPUT": str(out["output"]),
            "GITHUB_STEP_SUMMARY": str(out["summary"]),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_RUN_ATTEMPT": "1",
            **env,
        },
    )
    assert ran.returncode == 0, ran.stderr
    asked = tmp_path / "asked"
    return (
        outputs(out["output"].read_text()),
        ran.stdout.strip(),
        out["summary"].read_text(),
        "macos-checked-{}-{}".format(*trees),
        asked.read_text().splitlines() if asked.exists() else [],
    )


def test_the_macos_reuse_skips_the_mac_for_the_two_trees_a_passed_macos_job_ran():
    """The reuse step looks up `macos-checked-<base tree>-<merge tree>` before any `uv sync`, on
    the checkout of two commits the selection reads, with the run's token, which may read
    another run's artifacts. A successful macos.yml run of this repo that left it is a hit: the
    step gives `reused` true, the selection's steps are skipped, and so is the Mac."""
    found, _ = steps(MAC.read_text(), "macos-select")
    checkout, look, *rest = found
    assert checkout["with"] == {"fetch-depth": "2", "persist-credentials": False}
    assert (look["name"], look["id"], look["continue-on-error"]) == ("reuse", "reuse", True)
    assert look["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert block("permissions", MAC) == {"contents": "read", "actions": "read"}
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in rest] == [
        "astral-sh/setup-uv",
        "uv sync --locked",
        "|",
    ]
    for step in rest:
        reused = {r: {"steps.reuse.outputs.reused": r} for r in ("true", "false", "")}
        assert [r for r in reused if worked(step["if"], reused[r])] == ["false", ""]
    assert step_outputs(MAC, "macos-select") == {
        "run": "${{ steps.reached.outputs.run }}",
        "parts": "${{ steps.reached.outputs.parts }}",
        "tests": "${{ steps.reached.outputs.tests }}",
        "name": "${{ steps.reuse.outputs.name }}",
        "reused": "${{ steps.reuse.outputs.reused }}",
    }


def step_outputs(path, job):
    """The `outputs` of one job of a workflow, as written."""
    found, inside, at = {}, False, False
    for line in path.read_text().splitlines():
        indent = len(line) - len(line.lstrip())
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent <= 2:
            inside = indent == 2 and line.strip() == f"{job}:"
        elif inside and indent == 4:
            at = line.strip() == "outputs:"
        elif inside and at and indent == 6:
            key, _, value = line.strip().partition(":")
            found[key] = scalar(value)
    return found


def test_a_pair_a_passed_macos_job_ran_is_reused_and_the_summary_names_its_run(tmp_path):
    outputs, printed, summary, name, asked = mac_reuse(
        tmp_path, lambda base, merge: {f"macos-checked-{base}-{merge}": run(path=MAC_WORKFLOW)}
    )
    assert outputs == {"name": name, "reused": "true"}
    assert printed == f"reuse: {name}: passed the check in {URL}, so the suite is skipped"
    assert summary == (
        f"macOS: {name}: passed the check in {URL}, so the suite is skipped, and no Mac starts\n"
    )
    assert asked == [f"{ARTIFACTS}?name={name}&per_page=100", RUN]


@pytest.mark.parametrize(
    "left",
    [
        lambda base, merge: {f"macos-checked-{OTHER_TREE}-{merge}": run(path=MAC_WORKFLOW)},
        lambda base, merge: {f"macos-checked-{base}-{OTHER_TREE}": run(path=MAC_WORKFLOW)},
        lambda base, merge: {f"macos-checked-{merge}-{base}": run(path=MAC_WORKFLOW)},
        lambda base, merge: {f"checked-tree-{base}-{merge}": run()},
        lambda base, merge: {f"checked-tree-{base}-{merge}": run(path=MAC_WORKFLOW)},
        lambda base, merge: {f"macos-checked-{base}-{merge}": run()},
        lambda base, merge: {
            f"macos-checked-{base}-{merge}": run(path=MAC_WORKFLOW, conclusion="failure")
        },
        lambda base, merge: {
            f"macos-checked-{base}-{merge}": run(path=MAC_WORKFLOW, head_repository={"id": 2})
        },
    ],
    ids=[
        "another base tree",
        "another merge tree",
        "the trees swapped",
        "the check's marker of the pair",
        "the check's name from a macos run",
        "the pair's name from a check run",
        "a failed macos run",
        "a fork's macos run",
    ],
)
def test_a_pair_whose_trees_differ_or_no_passed_macos_run_of_this_repo_left_runs_the_mac(
    tmp_path, left
):
    """A marker of trees that differ in any way, the check's own marker of the same pair, or the
    pair's name from any run that is not a successful macos.yml run of this repo, is no hit: the
    step gives `reused` false and the Mac runs, and the summary is the selection's alone."""
    outputs, printed, summary, name, _ = mac_reuse(tmp_path, left)
    assert outputs == {"name": name, "reused": "false"}
    assert printed.startswith(f"reuse: {name}: "), printed
    assert summary == ""


@pytest.mark.parametrize(
    "env",
    [
        {"GITHUB_RUN_ATTEMPT": "2"},
        {"GITHUB_EVENT_NAME": "workflow_dispatch"},
        {"GITHUB_EVENT_NAME": "push"},
    ],
)
def test_a_macos_run_again_never_reuses_and_asks_nothing(tmp_path, env):
    """A run again, and a push to main, run the Mac: a push run selects with `--within`, more
    than the `--strict` run of a pull request that may have left the marker of the same trees."""

    def left(base, merge):
        return {f"macos-checked-{base}-{merge}": run(path=MAC_WORKFLOW)}

    outputs, _, summary, name, asked = mac_reuse(tmp_path, left, **env)
    assert (outputs, summary, asked) == ({"name": name, "reused": "false"}, "", [])


def test_a_macos_lookup_that_cannot_ask_runs_the_mac_and_warns(tmp_path):
    """Here the marker is listed and its run cannot be read."""
    outputs, printed, summary, name, _ = mac_reuse(
        tmp_path, lambda base, merge: {f"macos-checked-{base}-{merge}": None}
    )
    assert (outputs, summary) == ({"name": name, "reused": "false"}, "")
    assert printed.startswith(f"::warning::reuse: {name}: could not ask (HTTP 404"), printed


def test_a_passed_macos_job_leaves_the_marker_of_its_two_trees():
    """Only parts that all passed leave `macos-checked-<base tree>-<merge tree>`, the name the
    selection's lookup gave, for a later run of the pair to reuse: `macos` leaves it, on the
    parts' result. A marker that cannot be kept costs that reuse and nothing else."""
    found, _ = steps(MAC.read_text(), "macos")
    mark, upload = found[-2:]
    assert mark["name"] == "checked trees marker"
    assert [
        (result, name)
        for result in RESULTS
        for name in ("macos-checked-a-b", "")
        if worked(
            mark["if"],
            {"needs.macos-part.result": result, "needs.macos-select.outputs.name": name},
        )
    ] == [("success", "macos-checked-a-b")]
    assert mark["env"] == {"NAME": "${{ needs.macos-select.outputs.name }}"}
    assert upload["uses"].partition("@")[0] == "actions/upload-artifact"
    assert [o for o in OUTCOMES if worked(upload["if"], {"steps.checked.outcome": o})] == [
        "success"
    ]
    assert upload["continue-on-error"] is True
    assert upload["with"]["name"] == "${{ needs.macos-select.outputs.name }}"
    assert upload["with"]["if-no-files-found"] == "error"


def test_every_path_in_the_macos_quick_list_is_a_test_file_or_a_tests_directory_of_the_repo():
    """A path that moved or went would make pytest stop with no test run."""
    paths = MAC_QUICK.read_text().splitlines()
    assert paths and len(paths) == len(set(paths))
    for path in paths:
        found = REPO / path
        assert (
            found.is_file()
            and fnmatch(found.name, "test_*.py")
            or (found.is_dir() and found.name == "tests")
        ), path


def test_the_fast_check_selects_in_reuse_and_lints_beside_it_and_runs_neither_in_a_part():
    """The job `reuse`, where it reuses nothing, reads the diff over main, HEAD^1 on GitHub's
    merge, once a run, and hands each of the eight parts its files, in the runner's python3 with
    no `uv sync` and no collection, so no job of its own stands between it and the parts. The
    lint is a job of its own beside it, which waits on nothing and nothing waits on but `check`.
    The parts run neither the selection nor the lint."""
    found, _ = steps(CHECK.read_text(), "reuse")
    named = [step.get("uses", step.get("name")).partition("@")[0] for step in found]
    assert named == [
        "actions/checkout",
        "reuse",
        "actions/cache",
        "failed on main",
        "green tree",
        "actions/cache",
        "select",
        "selection",
        "actions/upload-artifact",
        "actions/upload-artifact",
        "no AI co-author trailer",
    ]
    tree, select = found[4], found[6]
    assert tree["run"] == 'echo "name=green-tree-$(git rev-parse HEAD^{tree})" >> "$GITHUB_OUTPUT"'
    assert select["run"] == "python3 scripts/select_tests.py --parts 8 HEAD^1 HEAD"
    assert "uv" not in " ".join(str(step.get("run", "")) for step in found)
    assert (tree["id"], select["id"]) == ("tree", "select")
    assert tree["if"] == select["if"] == "steps.reuse.outputs.reused != 'true'"
    assert "continue-on-error" not in select
    assert select["env"] == {
        "FAILED_ON_MAIN": "${{ steps.failed.outputs.tests }}",
        "SELECTED": "${{ runner.temp }}/selected-tests.txt",
    }
    outputs = job_section("reuse", "outputs")
    assert {
        key: outputs[key] for key in outputs if key not in ("name", "reused", "failed", "lookup")
    } == {
        "selection": "${{ steps.select.outputs.selection }}",
        "files": "${{ steps.select.outputs.files }}",
        "forced_by": "${{ steps.select.outputs.forced_by }}",
        "tree": "${{ steps.tree.outputs.name }}",
    } | {f"part{k}": f"${{{{ steps.select.outputs.part{k} }}}}" for k in range(1, 9)}
    lint, keys = steps(CHECK.read_text(), "lint")
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in lint] == [
        "actions/checkout",
        "astral-sh/setup-uv",
        "uv sync --locked",
        "python3 features/writing/scripts/prose_lint.py HEAD^1",
        "make lint BASE=HEAD^1",
        "uv run repo-standard conform",
    ]
    assert lint[0]["with"] == {"persist-credentials": False, "fetch-depth": "2"}
    assert "needs" not in keys and job_line("lint", "needs") is None
    assert all("if" not in step for step in lint)
    assert ran_on("lint", reused="true") == ran_on("lint", reused="") == ["pull_request"]
    parts, _ = steps(CHECK.read_text(), "check-shard")
    said = " ".join(map(str, parts))
    assert "select_tests" not in said and "check-fast" not in said and "lint" not in said
    assert [
        step.get("uses", step.get("name", step.get("run"))).partition("@")[0] for step in parts
    ][:8] == [
        "actions/checkout",
        "astral-sh/setup-uv",
        "uv sync --locked",
        "zsh",
        "actions/cache/restore",
        "selection",
        "part",
        "make test",
    ]
    assert parts[0]["with"] == {"persist-credentials": False, "fetch-depth": "2"}
    assert parts[7]["id"] == "suite"


def test_the_select_step_starts_from_the_facts_a_run_of_the_same_selector_kept():
    """select_tests.py keeps what it read of each module in `KEPT` under the git directory, and
    parses again only a module whose text changed. The job `reuse` restores that file right
    before the selection and saves it after, under a key that hashes the selector and ends in the
    run, so each run saves an entry of its own and a run restores the latest one only of the
    same selector: a changed script starts cold and never reads facts an older one wrote. A
    reuse selects nothing, and restores nothing."""
    found, _ = steps(CHECK.read_text(), "reuse")
    at = next(n for n, step in enumerate(found) if step.get("id") == "select") - 1
    cache = found[at]
    assert re.fullmatch(r"actions/cache@[0-9a-f]{40}", cache["uses"])
    assert cache["if"] == "steps.reuse.outputs.reused != 'true'"
    script = (REPO / "scripts" / "select_tests.py").read_text()
    kept = re.search(r'^KEPT = "([^"]+)"$', script, re.M)
    selector = "select-facts-${{ hashFiles('scripts/select_tests.py') }}-"
    assert cache["with"] == {
        "path": f".git/{kept[1]}",
        "key": selector + "${{ github.run_id }}-${{ github.run_attempt }}",
        "restore-keys": selector,
    }


def test_a_run_on_main_saves_the_facts_under_the_key_a_pull_requests_select_restores():
    """A cache saved on a pull request's ref is seen by that pull request only, and one saved on
    main by every pull request. So a run on main, and only there, builds the facts on main's
    tree and saves them as `reuse` does: the same file, under the same key, so the restore-keys
    of a pull request's first run find main's entry. It builds them in the runner's python3, as
    `reuse` selects, since the facts are kept under a salt that holds the Python's version."""
    assert ran_on("select-facts") == ["push", "workflow_dispatch"]
    reuse, _ = steps(CHECK.read_text(), "reuse")
    found, _ = steps(CHECK.read_text(), "select-facts")
    names = [step.get("uses", step.get("run")).partition("@")[0] for step in found]
    assert names[:2] == ["actions/checkout", "actions/cache"]
    assert "uv" not in " ".join(str(step.get("run", "")) for step in found)
    assert found[0]["with"] == {"persist-credentials": False}
    at = names.index("actions/cache")
    restores = next(
        step
        for step in reuse
        if step.get("uses", "").startswith("actions/cache@")
        and "select_tests" in str(step.get("with"))
    )
    assert {key: found[at][key] for key in ("uses", "with")} == {
        key: restores[key] for key in ("uses", "with")
    }
    assert "if" not in found[at]
    assert found[at + 1]["run"].startswith("python3 -c ")
    assert "select_tests.facts()" in found[at + 1]["run"]


PART = "${{ steps.selection.outputs[format('part{0}', matrix.shard)] }}"


@pytest.mark.parametrize(
    "part,ends,made",
    [
        ("", 1, None),
        ("none", 0, None),
        (
            "testing/tests/test_a.py testing/tests/test_b.py",
            0,
            "test TESTS=testing/tests/test_a.py testing/tests/test_b.py"
            " NEW_LINES_PART=/runner/temp/new-lines",
        ),
    ],
)
def test_a_part_runs_only_its_own_files_and_fails_on_no_selection(tmp_path, part, ends, made):
    """Each part reads its own entry of the selection `reuse` handed it, and its steps run here as
    the runner runs them, with a `make` that records what it was asked: a part runs `make test` on
    its files alone, so it collects only those; a part the selection left empty (`none`) passes;
    and a part that got nothing fails before `make test`, which with no files runs the whole
    suite. A reuse runs neither."""
    found, _ = steps(CHECK.read_text(), "check-shard")
    guard, test = (
        next(step for step in found if step.get("name") == n) for n in ("part", "make test")
    )
    assert guard["env"] == test["env"] == {"PART": PART}
    for step in (guard, test):
        assert [
            r
            for r in ("true", "false", "")
            if worked(step["if"], {"steps.selection.outputs.reused": r})
        ] == ["false", ""]
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "make").write_text(f'#!/bin/sh\necho "$*" >> "{tmp_path}/make"\n')
    (bin / "make").chmod(0o755)
    env = {"PATH": f"{bin}:/usr/bin:/bin", "PART": part, "RUNNER_TEMP": "/runner/temp"}
    first = subprocess.run(["sh", "-c", guard["run"]], env=env, capture_output=True, text=True)
    assert first.returncode == ends
    if ends:
        assert "::error::" in first.stdout
        return
    subprocess.run(["sh", "-c", test["run"]], env=env, check=True)
    asked = tmp_path / "make"
    assert (asked.read_text().strip() if asked.exists() else None) == made


def hand_over(tmp_path, select, reused, ready, status, newest=""):
    """Run `reuse`'s `selection` step and a part's, as the runner runs them, with a `gh` that
    serves the run's artifacts as GitHub does: none for the asks before `ready`, then the file
    `reuse` wrote. The `reuse` job's status in this attempt is `status` (`none` where it is not
    of this attempt), and the newest selection of the run, of any attempt, is `newest`. Return
    how the part's step ended, its outputs, and what it asked of `gh`."""
    (wrote,) = [s for s in steps(CHECK.read_text(), "reuse")[0] if s.get("name") == "selection"]
    (asks,) = [
        s for s in steps(CHECK.read_text(), "check-shard")[0] if s.get("name") == "selection"
    ]
    assert wrote["if"] == "!cancelled()"
    assert wrote["env"] == {
        "SELECT": "${{ toJSON(steps.select.outputs) }}",
        "TREE": "${{ steps.tree.outputs.name }}",
        "REUSED": "${{ steps.reuse.outputs.reused }}",
    }
    assert asks["env"] == {"GH_TOKEN": "${{ github.token }}"}
    (upload,) = [
        s for s in steps(CHECK.read_text(), "reuse")[0] if "selection-" in str(s.get("with"))
    ]
    assert upload["with"]["name"] == "selection-${{ github.run_attempt }}"
    assert upload["with"]["path"] == "${{ runner.temp }}/selection/selection.json"
    reuse = tmp_path / "reuse"
    reuse.mkdir()
    env = {"PATH": "/usr/bin:/bin", "RUNNER_TEMP": str(reuse), "TREE": "green-tree-ab"}
    env |= {"SELECT": json.dumps(select), "REUSED": reused}
    subprocess.run(["bash", "-e", "-c", wrote["run"]], env=env, check=True)
    with zipfile.ZipFile(tmp_path / "artifact.zip", "w") as kept:
        kept.write(reuse / "selection" / "selection.json", "selection.json")
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "sleep").write_text("#!/bin/sh\n")
    (bin / "gh").write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{tmp_path}/asked"\n'
        'case "$2" in\n'
        "*/artifacts?name=selection-3)\n"
        f'  echo x >> "{tmp_path}/lists"\n'
        f'  [ "$(wc -l < "{tmp_path}/lists")" -lt {ready} ] || echo 77 ;;\n'
        f'*/runs/9/attempts/3/jobs?per_page=100) echo "{status}" ;;\n'
        f"*/runs/9/artifacts?per_page=100) echo {newest} ;;\n"
        f'*/actions/artifacts/77/zip) cat "{tmp_path}/artifact.zip" ;;\n'
        "*) exit 1 ;;\n"
        "esac\n"
    )
    for name in ("sleep", "gh"):
        (bin / name).chmod(0o755)
    part = tmp_path / "part"
    part.mkdir()
    out = tmp_path / "output"
    env = {"PATH": f"{bin}:/usr/bin:/bin", "RUNNER_TEMP": str(part), "GITHUB_OUTPUT": str(out)}
    env |= {"GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "9", "GITHUB_RUN_ATTEMPT": "3"}
    ran = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", asks["run"]], env=env, capture_output=True, text=True
    )
    outputs = (
        dict(line.split("=", 1) for line in out.read_text().splitlines()) if out.exists() else {}
    )
    asked = (tmp_path / "asked").read_text().splitlines()
    return ran, outputs, asked


SELECTED = {f"part{k}": f"testing/tests/test_{k}.py" for k in range(1, 9)} | {
    "part8": "none",
    "selection": "some",
    "files": "7",
    "forced_by": "",
}


def test_a_part_sets_up_while_reuse_selects_and_waits_only_for_the_selection():
    """The parts need no job, so they set up while `reuse` runs; `reuse` uploads its selection
    the moment it has one, and a part, its setup done, asks for that artifact until it is there
    and takes it as its outputs, before its tests and after its setup."""
    found, _ = steps(CHECK.read_text(), "check-shard")
    named = [step.get("name", step.get("uses", "")) for step in found]
    assert named.index("selection") > max(
        i
        for i, step in enumerate(found)
        if "setup-uv" in step.get("uses", "") or step.get("name") == "zsh"
    )
    assert named.index("selection") < named.index("part") < named.index("make test")
    assert job_line("check-shard", "needs") is None
    reuse = [
        step.get("name", step.get("uses", "")) for step in steps(CHECK.read_text(), "reuse")[0]
    ]
    assert reuse.index("select") + 1 == reuse.index("selection")


@pytest.mark.parametrize("ready", [1, 4, 12])
def test_a_part_takes_the_selection_reuse_handed_over_once_it_is_there(tmp_path, ready):
    ran, outputs, asked = hand_over(tmp_path, SELECTED, "false", ready, "in_progress")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert outputs == SELECTED | {"tree": "green-tree-ab", "reused": "false"}
    lists = [line for line in asked if "artifacts?name=" in line]
    assert len(lists) == ready
    assert asked[-1].startswith("api repos/o/r/actions/artifacts/77/zip")


def test_a_reuse_hands_the_parts_no_files_and_says_it_reused(tmp_path):
    ran, outputs, _ = hand_over(tmp_path, {}, "true", 1, "in_progress")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert outputs == {"tree": "green-tree-ab", "reused": "true"}


@pytest.mark.parametrize("status", ["completed", "none"])
def test_a_part_run_again_alone_reads_the_selection_reuse_left_in_its_own_attempt(tmp_path, status):
    """Where only the failed jobs run again, `reuse` is carried over from the attempt it ran in,
    and no `selection-<attempt>` of this attempt comes: on the fifth ask the part finds `reuse`
    ended, or not of this attempt, and takes the newest selection of the run."""
    ran, outputs, asked = hand_over(tmp_path, SELECTED, "false", 10**6, status, newest="77")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert outputs == SELECTED | {"tree": "green-tree-ab", "reused": "false"}
    assert len([line for line in asked if "artifacts?name=" in line]) == 5
    assert len([line for line in asked if "artifacts?per_page=" in line]) == 1


def test_a_part_fails_soon_when_reuse_ended_with_no_selection(tmp_path):
    """A `reuse` that ended before it uploaded its selection, as when its checkout failed, and
    left none in an earlier attempt, fails the part on the fifth ask, not at its timeout."""
    ran, outputs, asked = hand_over(tmp_path, SELECTED, "false", 10**6, "completed")
    assert ran.returncode == 1
    assert "::error::the job reuse ended with no selection for this part" in ran.stdout
    assert outputs == {}
    assert len([line for line in asked if "artifacts?name=" in line]) == 5
    assert len([line for line in asked if "artifacts?per_page=" in line]) == 1
    assert len([line for line in asked if "/jobs" in line]) == 1


@pytest.mark.parametrize("job", ["check-shard", "full-shard"])
def test_every_part_restores_one_tlc_cache_by_the_spec_files_and_keeps_what_it_added(job):
    """The cache of TLC's output (statechart's `kept`) is one for every part, since a test's part
    changes with the selection: its keys name no part. It is restored right before the suite,
    where only a part of the check's wait for its selection comes between them, the latest of
    the same spec files first, else the latest of any. A part of the check saves what it added
    after the suite, under a key `tlc kept` gives; a part of `full` uploads its runs for `full`
    to save, which the next test pins. The files its key hashes are every file a kept run reads
    from the repo, TLC's pinned jar in statechart's tools.py among them, so a change to any of
    them misses. The save's key starts with the very key the restore looked for, hashed once
    before the suite: the suite writes `__pycache__` under the hashed paths, so a hash taken
    after it names an entry no later run's key finds."""
    text = CHECK.read_text()
    found, _ = steps(text, job)
    found = [step for step in found if step.get("name") not in ("selection", "part")]
    names = [
        step.get("uses", step.get("name", step.get("run"))).partition("@")[0] for step in found
    ]
    at = names.index("actions/cache/restore")
    restore = found[at]
    assert re.fullmatch(r"actions/cache/(restore|save)@[0-9a-f]{40}", restore["uses"])
    assert "matrix.shard" not in str(restore)
    specs = re.fullmatch(r"tlc-\$\{\{ (hashFiles\(.*\)) \}\}-", restore["with"]["key"])[1]
    assert (restore["id"], restore["with"]["path"], restore["with"]["restore-keys"]) == (
        "tlc",
        TLC,
        "|",
    )
    assert f"\n            tlc-${{{{ {specs} }}}}-\n            tlc-\n" in text
    if job == "check-shard":
        assert names[at : at + 4] == [
            "actions/cache/restore",
            "make test",
            "tlc kept",
            "actions/cache/save",
        ]
        _, _, kept, save = found[at : at + 4]
        assert restore["uses"].partition("@")[2] == save["uses"].partition("@")[2]
        assert "matrix.shard" not in str([kept, save])
        assert "hashFiles" not in str([kept, save])
        assert kept["env"] == {
            "KEY": "${{ steps.tlc.outputs.cache-primary-key }}",
            "RESTORED": "${{ steps.tlc.outputs.cache-matched-key }}",
        }
        assert (kept["id"], kept["if"], kept["run"]) == (
            "kept",
            "!cancelled() && steps.suite.outcome != 'skipped'",
            KEPT,
        )
        assert save["if"] == "!cancelled() && steps.kept.outputs.key != ''"
        assert save["with"] == {"path": TLC, "key": "${{ steps.kept.outputs.key }}"}
    else:
        assert names[at : at + 3] == [
            "actions/cache/restore",
            "make check",
            "actions/upload-artifact",
        ]
        assert "actions/cache/save" not in names
    globs = [f":(glob){one}" for one in re.findall(r"'([^']+)'", specs)]
    hashed = subprocess.run(
        ["git", "ls-files", "--", *globs], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    reads = [
        "*/spec/*.tla",
        "*/spec/*.cfg",
        "*/spec/canary/*.tla",
        "*/spec/*canaries.py",
        "*/statechart/tools.py",
    ]
    read = subprocess.run(
        ["git", "ls-files", "--", *reads], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert read
    assert set(read) - set(hashed) == set()


def test_mains_full_run_saves_one_tlc_entry_that_holds_every_parts_runs():
    """A pull request's part restores only the newest entry under the spec files' key. When each
    part of main's full run saved its own, that newest entry held one part's runs, and a pull
    request ran the other parts' TLC scenes cold, at 60 to 271 s a scene where the dealer
    weighed them at their warm 0.1 to 1.8 s (run 42531437810, 2026-11-08). So no part of `full`
    saves: each uploads every run it holds, passed or failed, and `full`, which runs once after
    them all, downloads every part's into the one folder and saves it, under the key the parts
    restored with and the hash of the names it holds, as a part of the check does. Parts that
    skipped the suite on a green marker restored nothing, so `full` saves nothing."""
    parts, _ = steps(CHECK.read_text(), "full-shard")
    (upload,) = [
        step
        for step in parts
        if step.get("uses", "").startswith("actions/upload-artifact@")
        and step["with"]["path"] == TLC
    ]
    assert upload["if"] == "!cancelled() && steps.suite.outcome != 'skipped'"
    assert upload["with"]["name"] == "tlc-${{ github.run_attempt }}-${{ matrix.shard }}"
    assert upload["continue-on-error"] is True
    assert upload["with"]["if-no-files-found"] == "ignore"
    outputs = job_section("full-shard", "outputs")
    assert (outputs["tlc"], outputs["restored"]) == (
        "${{ steps.tlc.outputs.cache-primary-key }}",
        "${{ steps.tlc.outputs.cache-matched-key }}",
    )
    found, _ = steps(CHECK.read_text(), "full")
    names = [step.get("uses", step.get("name")).partition("@")[0] for step in found]
    at = names.index("actions/download-artifact")
    assert names[at : at + 3] == ["actions/download-artifact", "tlc kept", "actions/cache/save"]
    runs, kept, save = found[at : at + 3]
    assert runs["with"] == {"pattern": "tlc-*", "path": TLC, "merge-multiple": True}
    assert [
        key
        for key in ("tlc-1", "")
        if worked(runs["if"], {"!cancelled()": True, "needs.full-shard.outputs.tlc": key})
    ] == ["tlc-1"]
    assert not worked(runs["if"], {"!cancelled()": False, "needs.full-shard.outputs.tlc": "x"})
    assert (runs["id"], runs["continue-on-error"]) == ("runs", True)
    ran = {"!cancelled()": True}
    assert [o for o in OUTCOMES if worked(kept["if"], ran | {"steps.runs.outcome": o})] == [
        "success"
    ]
    assert kept["env"] == {
        "KEY": "${{ needs.full-shard.outputs.tlc }}",
        "RESTORED": "${{ needs.full-shard.outputs.restored }}",
    }
    assert (kept["id"], kept["run"]) == ("kept", KEPT)
    assert save["if"] == "!cancelled() && steps.kept.outputs.key != ''"
    assert save["with"] == {"path": TLC, "key": "${{ steps.kept.outputs.key }}"}
    assert save["continue-on-error"] is True
    restore = [step for step in parts if step.get("id") == "tlc"][0]
    assert save["uses"].partition("@")[2] == restore["uses"].partition("@")[2]


def kept_key(home, restored):
    """The key `tlc kept` gives the save, run here as the runner runs it, or "" for no save. It
    runs on this PATH, where the test's skip found sha256sum: on macOS that is Homebrew's, which
    /usr/bin does not hold."""
    output = home / "output"
    output.write_text("")
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "KEY": "tlc-abc-",
        "RESTORED": restored,
        "GITHUB_OUTPUT": str(output),
    }
    subprocess.run(["sh", "-c", KEPT], env=env, check=True)
    return output.read_text().strip().removeprefix("key=")


@pytest.mark.skipif(
    not shutil.which("sha256sum"), reason="the step runs on ubuntu, whose coreutils have sha256sum"
)
def test_a_part_saves_tlc_runs_only_when_it_added_some_under_the_spec_files_and_what_it_holds(
    tmp_path,
):
    """A part with no cache folder, or an empty one, saves nothing. A part that ran TLC saves
    under the key it restored with, the spec files' hash, and a hash of its runs' names, and a
    part that holds just what it restored, by that key's end, saves nothing: so a part that ran
    no TLC never takes the key of one that did. A run added changes the key, and the same runs
    give the same key."""
    assert kept_key(tmp_path, "") == ""
    tlc = tmp_path / ".cache" / "jstack" / "tlc"
    tlc.mkdir(parents=True)
    assert kept_key(tmp_path, "") == ""
    (tlc / "b1").write_text("out")
    (tlc / "a2").write_text("out")
    first = kept_key(tmp_path, "")
    assert re.fullmatch(r"tlc-abc-[0-9a-f]{16}", first)
    assert kept_key(tmp_path, "tlc-abc-0123") == first
    assert kept_key(tmp_path, first) == ""
    assert kept_key(tmp_path, first.replace("abc", "older")) == ""
    assert kept_key(tmp_path, "tlc-3-abc-41659054270") == first
    (tlc / "c3").write_text("out")
    assert kept_key(tmp_path, first) not in ("", first)


ZSH_STUBS = {
    "sudo": '"$@"',
    "apt-get": 'echo "apt-get $*" >> "$LOG"; case " $* " in *" install "*) installs;; esac',
    "dpkg": 'echo "dpkg $*" >> "$LOG"; installs',
    "curl": 'echo "curl $*" >> "$LOG"; for a; do case $a in http*) echo x >"${a##*/}";; esac; done',
    "sha256sum": "exit 0",
}


@pytest.mark.parametrize("ends", ["installed", "not installed", "not the pinned file"])
def test_the_zsh_steps_update_no_unnamed_source_and_fail_unless_zsh_runs(tmp_path, ends):
    """`apt-get update` with no source named reads every list the image names, from its Azure
    mirror, which took the step 140 to 270 seconds a part job. Each zsh step runs here as
    written, under sh, with stand-ins for what it calls on a PATH that holds nothing else:
    it passes only when zsh runs at its end, and installs nothing that is not the pinned file."""
    runs = [
        step["run"]
        for job in ("check-shard", "full-shard")
        for step in steps(CHECK.read_text(), job)[0]
        if step.get("name") == "zsh"
    ]
    assert len(runs) == 2
    for at, run in enumerate(runs):
        bin, temp, log = tmp_path / f"bin{at}", tmp_path / f"temp{at}", tmp_path / f"log{at}"
        bin.mkdir()
        temp.mkdir()
        zsh = tmp_path / f"zsh{at}"
        zsh.write_text('#!/bin/sh\necho "zsh $*" >> "$LOG"\n')
        zsh.chmod(0o755)
        installs = "" if ends == "not installed" else f"{shutil.which('cp')} -p {zsh} {bin}/zsh"
        for name, body in ZSH_STUBS.items():
            (bin / name).write_text(f"#!/bin/sh\ninstalls() {{ {installs or ':'}; }}\n{body}\n")
            (bin / name).chmod(0o755)
        if ends == "not the pinned file":
            (bin / "sha256sum").unlink()
            (bin / "sha256sum").symlink_to(shutil.which("sha256sum"))
        env = {**block("env"), "PATH": str(bin), "RUNNER_TEMP": str(temp), "LOG": str(log)}
        ran = subprocess.run(["/bin/sh", "-c", run], env=env, capture_output=True, text=True)
        called = log.read_text().splitlines() if log.exists() else []
        assert [
            line
            for line in called
            if line.startswith("apt-get") and " update" in line and "sourcelist=" not in line
        ] == []
        if ends == "installed":
            assert ran.returncode == 0, ran.stderr
            assert called[-1] == "zsh --version"
        else:
            assert ran.returncode != 0
        if ends == "not the pinned file":
            assert [line for line in called if not line.startswith("curl")] == []


def test_only_full_asks_for_a_marker_and_both_jobs_leave_one():
    """A pull request's check skips nothing: its own run is the proof that the suite passed,
    and a marker records that. The parts ask, and the one job over them leaves it."""
    asking = ("green_tree.py", "steps.tree.outputs.marker")
    leaving = ("green-tree", "upload-artifact", "needs.", "steps.marker")
    for job, gate, asks in (("check-shard", "check", False), ("full-shard", "full", True)):
        said = " ".join(map(str, steps(CHECK.read_text(), job)[0]))
        assert [word for word in asking if word in said] == (list(asking) if asks else []), job
        uploads = [
            step
            for step in steps(CHECK.read_text(), job)[0]
            if "upload-artifact" in step.get("uses", "")
        ]
        assert [step for step in uploads if "green-tree" in str(step)] == [], job
        said = " ".join(map(str, steps(CHECK.read_text(), gate)[0]))
        assert [word for word in leaving if word in said] == list(leaving), gate


def test_a_pull_requests_check_leaves_a_marker_only_when_it_ran_the_whole_suite_and_passed():
    *_, mark, upload = steps(CHECK.read_text(), "check")[0]
    assert [
        (result, lint, reuse, selection)
        for result in RESULTS
        for lint in RESULTS
        for reuse in RESULTS
        for selection in ("all", "some", "")
        if worked(
            mark["if"],
            {
                "needs.check-shard.result": result,
                "needs.lint.result": lint,
                "needs.reuse.result": reuse,
                "needs.reuse.outputs.selection": selection,
            },
        )
    ] == [("success", "success", "success", "all")]
    assert (mark["id"], mark["env"]) == (
        "marker",
        {"NAME": "${{ needs.reuse.outputs.tree }}"},
    )
    assert (
        mark["run"] == 'mkdir -p "$RUNNER_TEMP/green-tree" && touch "$RUNNER_TEMP/green-tree/$NAME"'
    )
    assert [o for o in OUTCOMES if worked(upload["if"], {"steps.marker.outcome": o})] == ["success"]
    assert (upload["id"], upload["continue-on-error"]) == ("upload", True)
    assert upload["with"] == {
        "name": "${{ needs.reuse.outputs.tree }}",
        "path": "${{ runner.temp }}/green-tree/${{ needs.reuse.outputs.tree }}",
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
    assert report["env"] == {
        "FULL": "${{ steps.selection.outputs.selection == 'all' }}",
        "NAME": "${{ steps.selection.outputs.tree }}",
        "FILES": "${{ steps.selection.outputs.files }}",
        "FORCED": "${{ steps.selection.outputs.forced_by }}",
    }
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "uv").write_text(f'#!/bin/sh\necho "$*" >> "{tmp_path}/uv"\n')
    (bin / "uv").chmod(0o755)
    (bin / "df").write_text('#!/bin/sh\n[ -n "$NODF" ] || printf "IUse%%\\n 37%%\\n"\n')
    (bin / "df").chmod(0o755)
    tree = "ab" * 20
    said = {}
    picked = {"true": ("all", "pyproject.toml"), "false": ("212", "")}
    for full, df in (("true", True), ("false", True), ("true", False)):
        summary = tmp_path / f"summary-{full}-{df}"
        env = {"PATH": f"{bin}:/usr/bin:/bin", "GITHUB_STEP_SUMMARY": str(summary)}
        env |= {"FULL": full, "NAME": f"green-tree-{tree}", "NODF": "" if df else "yes"}
        env |= dict(zip(("FILES", "FORCED"), picked[full], strict=True))
        subprocess.run(["sh", "-c", report["run"]], env=env, check=True)
        said[full, df] = summary.read_text()
    assert said == {
        ("true", True): f"full suite: yes, tree {tree}\n",
        ("false", True): f"full suite: no, tree {tree}\n",
        ("true", False): f"full suite: yes, tree {tree}\n",
    }
    assert (tmp_path / "uv").read_text().splitlines() == [
        f"run jbus ci --notice full=true tree={tree} selection=all reason=pyproject.toml"
        " tmp_inode_pct=37",
        f"run jbus ci --notice full=false tree={tree} selection=212 tmp_inode_pct=37",
        f"run jbus ci --notice full=true tree={tree} selection=all reason=pyproject.toml",
    ]


def test_a_pull_requests_check_keeps_the_list_of_tests_it_selected_as_an_artifact():
    """select_tests.py writes the selection it printed to the file `$SELECTED` names, and the
    job `reuse` keeps that file for each attempt where it selected, also where the selection
    failed, so a red on main can be checked against what its pull request's check ran."""
    found = steps(CHECK.read_text(), "reuse")[0]
    (kept,) = [step for step in found if "selected-tests" in str(step.get("with"))]
    assert re.fullmatch(r"actions/upload-artifact@[0-9a-f]{40}", kept["uses"])
    assert kept["continue-on-error"] is True
    assert [
        (c, reused)
        for c in (True, False)
        for reused in ("true", "false", "")
        if worked(kept["if"], {"!cancelled()": c, "steps.reuse.outputs.reused": reused})
    ] == [(True, "false"), (True, "")]
    assert kept["with"] == {
        "name": "selected-tests-${{ github.run_attempt }}",
        "path": "${{ runner.temp }}/selected-tests.txt",
        "retention-days": "30",
        "if-no-files-found": "error",
    }


def test_a_green_tree_skips_the_suite_by_its_steps_and_the_job_always_runs():
    found, keys = steps(CHECK.read_text(), "full-shard")
    assert "if" in keys and ran_on("full-shard") == ["push", "workflow_dispatch"]
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in found] == [
        "actions/checkout",
        "python3 scripts/green_tree.py",
        'echo "::warning::green-tree, the lookup ended failure, so the suite runs and a later run'
        ' of this tree may not skip it"',
        "astral-sh/setup-uv",
        "uv sync --locked",
        ZSH,
        "actions/cache/restore",
        SUITE,
        "actions/upload-artifact",
        "|",
        "actions/upload-artifact",
    ]
    assert found[-1]["if"] == "steps.suite.outcome == 'success'"
    assert found[-1]["with"] == {
        "name": "junit-${{ github.run_attempt }}-${{ matrix.shard }}",
        "path": "${{ runner.temp }}/junit.xml",
        "retention-days": "30",
        "if-no-files-found": "error",
    }
    gate, _ = steps(CHECK.read_text(), "full")
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in gate][1:] == [
        "actions/download-artifact",
        KEPT,
        "actions/cache/save",
        "actions/checkout",
        "actions/cache",
        "python3 scripts/select_tests.py --failed-on-main 30 ~/.cache/jstack/failed-on-main.json",
        'mkdir -p "$RUNNER_TEMP/green-tree" && touch "$RUNNER_TEMP/green-tree/$NAME"',
        "actions/upload-artifact",
        'echo "::warning::green-tree, the upload ended failure, so a later run of this tree may'
        ' not skip the suite"',
    ]
    checkout, ask, _, setup, sync, zsh, kept, suite, *_ = found
    assert "if" not in checkout
    assert (ask.get("if"), ask["id"], ask["continue-on-error"]) == (None, "tree", True)
    assert [step["if"] for step in (setup, sync, zsh, kept, suite)] == [
        UNLESS_GREEN,
        UNLESS_GREEN,
        UNLESS_GREEN,
        UNLESS_GREEN,
        UNLESS_GREEN,
    ]
    assert suite["id"] == "suite"
    assert [
        word
        for word in ("green", "none", "unknown", "unasked", "")
        if not worked(UNLESS_GREEN, {"steps.tree.outputs.marker": word})
    ] == ["green"]


OUTCOMES = ("success", "failure", "cancelled", "skipped", "")


def test_the_marker_is_left_only_after_every_part_passed():
    """When the parts of a matrix write one output, the one that ends last wins. So the parts
    give only the tree, which is the same in all of them, and the marker waits on the result,
    which is success only when every part ran its share and passed or skipped on a marker."""
    *_, mark, upload, warn = steps(CHECK.read_text(), "full")[0]
    assert job_section("full-shard", "outputs") == {
        "tree": "${{ steps.tree.outputs.name }}",
        "tlc": "${{ steps.tlc.outputs.cache-primary-key }}",
        "restored": "${{ steps.tlc.outputs.cache-matched-key }}",
    }
    assert [
        (result, name)
        for result in RESULTS
        for name in ("green-tree-1", "")
        if worked(
            mark["if"], {"needs.full-shard.result": result, "needs.full-shard.outputs.tree": name}
        )
    ] == [("success", "green-tree-1")]
    assert mark["id"] == "marker"
    assert [o for o in OUTCOMES if worked(upload["if"], {"steps.marker.outcome": o})] == ["success"]
    tree = "${{ needs.full-shard.outputs.tree }}"
    assert mark["env"] == {"NAME": tree}
    assert upload["with"]["name"] == tree
    assert upload["with"]["path"] == f"${{{{ runner.temp }}}}/green-tree/{tree}"


def test_a_lookup_or_an_upload_that_failed_never_fails_the_run_and_is_a_warning_on_it():
    """Each part warns of its own lookup, so one part's failed lookup is never hidden behind
    another's that worked."""
    _, ask, told, *_ = steps(CHECK.read_text(), "full-shard")[0]
    assert (ask["id"], ask["continue-on-error"]) == ("tree", True)
    assert [o for o in OUTCOMES if worked(told["if"], {"steps.tree.outcome": o})] == ["failure"]
    *_, upload, warn = steps(CHECK.read_text(), "full")[0]
    assert (upload["id"], upload["continue-on-error"]) == ("upload", True)
    assert [o for o in OUTCOMES if worked(warn["if"], {"steps.upload.outcome": o})] == ["failure"]


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
    tree. A path with no answer is refused.

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
    for path, body in (answers or {}).items():
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


FULL = "repos/owner/repo/git/matching-refs/jstack/green-tree/full"
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
    assert outputs == {"name": f"green-tree-{tree}", "marker": "green"}
    assert printed == f"green-tree: tree {tree}: passed the check in {URL}, so the suite is skipped"
    assert asked == [f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100", f"api {RUN}"]


@pytest.mark.skipif(not Path("/usr/bin/python3").is_file(), reason="no system python3")
def test_the_lookup_runs_on_the_runners_bare_python_before_uv_sync(tmp_path):
    """The step runs before `uv sync`, on the system's python3, isolated and with no site
    packages, so an import of anything installed fails here."""
    bare = ("/usr/bin/python3", "-I", "-S")
    outputs, printed, tree, _ = green_tree(tmp_path, {ARTIFACTS: marker(), RUN: run()}, bare)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "green"}
    assert printed == f"green-tree: tree {tree}: passed the check in {URL}, so the suite is skipped"


def test_a_tree_with_no_marker_runs_the_suite(tmp_path):
    outputs, printed, tree, _ = green_tree(tmp_path, {ARTIFACTS: {"artifacts": []}})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none"}
    assert printed.endswith(": no green run of the check left a marker, so the suite runs")


def test_a_run_that_is_refused_the_answer_runs_the_suite(tmp_path):
    outputs, printed, tree, asked = green_tree(tmp_path, {})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unknown"}
    assert printed == (
        f"::warning::green-tree: tree {tree}: could not ask"
        " (HTTP 403: Resource not accessible by integration), so the suite runs"
    )
    assert asked == [f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100"]


def test_a_runner_with_no_gh_runs_the_suite(tmp_path):
    outputs, printed, tree, _ = green_tree(tmp_path, None)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unknown"}
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
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none"}


@pytest.mark.parametrize(
    "answers",
    [
        {ARTIFACTS: marker(), RUN: run(head_repository={"id": 2})},
        {ARTIFACTS: marker(workflow_run={"head_repository_id": 2}), RUN: run()},
    ],
)
def test_a_marker_whose_run_is_a_forks_runs_the_suite_and_the_log_says_so(tmp_path, answers):
    outputs, printed, tree, _ = green_tree(tmp_path, answers)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none"}
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
    assert outputs == {"name": f"green-tree-{tree}", "marker": "green"}
    assert printed == f"green-tree: tree {tree}: passed the check in {URL}, so the suite is skipped"


def test_a_marker_whose_run_cannot_be_read_runs_the_suite(tmp_path):
    outputs, printed, tree, asked = green_tree(tmp_path, {ARTIFACTS: marker()})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unknown"}
    assert printed.startswith("::warning::green-tree: ") and ": could not ask (" in printed
    assert asked[1:] == [f"api {RUN}"]


@pytest.mark.parametrize("gone", [{"head_repository": None}, {"head_repository": {}}])
def test_a_marker_whose_run_names_no_head_repository_runs_the_suite(tmp_path, gone):
    outputs, printed, tree, _ = green_tree(tmp_path, {ARTIFACTS: marker(), RUN: run(**gone)})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none"}
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
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unasked"}
    assert (printed, asked) == (f"green-tree: tree {tree}: {why}", [])


def test_a_ref_pushed_under_green_tree_full_skips_nothing_and_is_never_asked_for(tmp_path):
    """Nothing pushes `refs/jstack/green-tree/full/<tree>` since #444, and anybody with write
    to the repo could push one by hand. Such a ref skipped main's suite; now only a green run's
    artifact does."""

    def pushed(tree):
        name = f"refs/jstack/green-tree/full/{tree}"
        return {
            f"{FULL}/{tree}": [{"ref": name, "object": {"sha": "c0ffee", "type": "commit"}}],
            COMMIT: {"tree": {"sha": tree}},
            ARTIFACTS: {"artifacts": []},
        }

    outputs, printed, tree, asked = green_tree(tmp_path, pushed)
    assert outputs == {"name": f"green-tree-{tree}", "marker": "none"}
    assert printed.endswith(": no green run of the check left a marker, so the suite runs")
    assert asked == [f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100"]


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


VIEW_PATHS = [
    "features/jbus/src/jbus/view/**",
    "features/jbus/tests/view/**",
    "features/jbus/tests/fixtures/jbus-view/**",
    ".github/workflows/browser.yml",
]


def test_the_browser_tests_run_nightly_on_a_release_by_hand_and_on_a_pull_request_into_main():
    """#464 merged with 19 browser tests red, as no pull request ran them: one into main that
    touches the view, or its browser tests, now does, on the same events as the check's."""
    assert triggers(BROWSER.read_text()) == {
        "pull_request": {
            "branches": ["main"],
            "types": triggers(CHECK.read_text())["pull_request"]["types"],
            "paths": VIEW_PATHS,
        },
        "schedule": [{"cron": "0 7 * * *"}],
        "push": {"tags": ["v*"]},
        "release": {"types": ["published"]},
        "workflow_dispatch": None,
    }


def test_a_pull_request_runs_the_browser_tests_only_for_the_view_its_tests_shots_or_workflow():
    """The view, its tests, their fixtures (the kept shots) and this workflow, which names the
    browser that draws them: a pin bumped with no run of its own would land shots unproven."""
    paths = triggers(BROWSER.read_text())["pull_request"]["paths"]
    changed = {
        "features/jbus/src/jbus/view/page.py": True,
        "features/jbus/src/jbus/view/static/board.js": True,
        "features/jbus/tests/view/test_view_board.py": True,
        "features/jbus/tests/view/page/browser.py": True,
        "features/jbus/tests/fixtures/jbus-view/shots/all-390-dark.png": True,
        ".github/workflows/browser.yml": True,
        ".github/workflows/check.yml": False,
        "features/jbus/tests/fixtures/jbus-watch/run.json": False,
        "features/jbus/src/jbus/watch.py": False,
        "features/jbus/tests/test_jbus_watch.py": False,
        "testing/tests/test_workflows.py": False,
    }
    assert {path: any(fnmatch(path, one) for one in paths) for path in changed} == changed


def test_a_draft_runs_no_browser_job_and_every_other_trigger_runs_it():
    """The browser job skips a draft, which only a hand opens, and runs once it is marked
    ready."""
    when = job_value(BROWSER.read_text(), "browser", "if")
    assert when is not None, "the browser job has no `if`"
    events = ("pull_request", "schedule", "push", "release", "workflow_dispatch")

    def runs(draft):
        return [
            e
            for e in events
            if worked(
                when,
                {
                    "github.event_name": e,
                    "github.event.pull_request.draft": draft if e == "pull_request" else None,
                },
            )
        ]

    assert runs(draft=True) == list(events[1:])
    assert runs(draft=False) == list(events)


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
    assert found[-2] == {"name": "make check-browser", "run": "make check-browser"}
    for job in ("reuse", "lint", "check-shard", "check", "full-shard", "full"):
        assert "check-browser" not in " ".join(map(str, steps(CHECK.read_text(), job)[0]))


NIGHTLY_REF = "main"


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


def test_the_macos_nightly_checks_out_main_unless_a_manual_run_names_another_ref():
    """A scheduled run has no inputs, so the checkout's own fallback is the input's default."""
    assert list(dispatch_inputs(NIGHTLY)) == ["ref"]
    assert dispatch_inputs(NIGHTLY)["ref"]["default"] == NIGHTLY_REF
    found, _ = steps(NIGHTLY.read_text(), "macos")
    checkout = found[0]
    assert checkout["uses"].partition("@")[0] == "actions/checkout"
    assert checkout["with"]["persist-credentials"] is False
    ref = checkout["with"]["ref"].removeprefix("${{").removesuffix("}}")
    assert [worked(ref, {"inputs.ref": given}) for given in ("", "fix-branch")] == [
        NIGHTLY_REF,
        "fix-branch",
    ]


def test_a_run_of_main_is_titled_as_jbus_files_it_and_a_run_on_another_ref_is_not():
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
        "check.yml": 4,
        "macos-nightly.yml": 1,
        "macos.yml": 2,
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


def test_a_release_checks_the_tag_and_main_s_verdict_on_its_tree_builds_installs_and_publishes():
    found, _ = steps(RELEASE.read_text(), "release")
    named = [step.get("name") for step in found if step.get("name")]
    assert named == [
        "make release-tag",
        "make release-green",
        "make dist",
        "jinstall --check",
        "gh release create",
    ]
    by = {step["name"]: step for step in found if step.get("name")}
    assert by["make release-tag"]["run"] == 'make release-tag TAG="$TAG"'
    assert by["make release-tag"]["env"] == {"TAG": "${{ github.ref_name }}"}
    assert by["make release-green"]["run"] == "make release-green"
    assert by["make release-green"]["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "GH_REPO": "${{ github.repository }}",
    }
    text = RELEASE.read_text()
    smoke = text[text.index("name: jinstall --check") : text.index("name: gh release create")]
    assert "uv tool install dist/*.whl" in smoke
    assert smoke.rstrip().splitlines()[-2].endswith('/jinstall" --check')
    assert by["gh release create"]["run"].startswith('gh release create "$TAG" dist/* --verify-tag')


def test_a_release_runs_no_check_of_its_own_and_installs_nothing_the_check_needs():
    runs = [step.get("run", "") for step in steps(RELEASE.read_text(), "release")[0]]
    for word in ("make check", "uv sync", "zsh"):
        assert not [run for run in runs if word in run], word


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


def test_each_check_jmerge_requires_is_a_job_of_a_pull_request_and_borders_fails_on_a_warning():
    from jmerge import ready

    pulled = {"check": CHECK, "borders": BORDERS}
    assert set(ready.REQUIRED) <= set(pulled)
    for name, workflow in pulled.items():
        assert name in jobs(workflow.read_text())
    found, _ = steps(BORDERS.read_text(), "borders")
    (lint,) = [step for step in found if step.get("name") == "lint borders"]
    assert lint["run"].startswith("python3 scripts/lint-borders.py --hard ")


def test_borders_fails_a_pull_request_that_changes_a_kept_shot_and_another_file_after_any_lint():
    """The kept shots are the shots row's alone (`jbus.shots`): borders, a check jmerge requires,
    runs the rule over the pull request's diff from the tip of its base, after the lint whatever
    the lint said."""
    found, _ = steps(BORDERS.read_text(), "borders")
    names = [step.get("name") for step in found]
    assert names[-2:] == ["lint borders", "kept shots"]
    assert found[-1]["run"] == "python3 features/jbus/scripts/kept_shots.py --base HEAD^1"
    assert found[-1]["if"] == "${{ !cancelled() }}"


NO_AI_TRAILERS = REPO / "scripts" / "no_ai_trailers.py"
CLAUDE = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
HUMAN = "Co-authored-by: Ada Lovelace <ada@example.com>"


def test_every_pull_request_run_checks_for_an_ai_trailer_a_reuse_included():
    """The two trees a reuse keys on fix the files, not the title, the body or a commit's
    message, so the trailer check runs in `reuse`, on every run, also where the selection there
    failed, and no part runs it again."""
    found, _ = steps(CHECK.read_text(), "reuse")
    (trailer,) = [step for step in found if step.get("name") == "no AI co-author trailer"]
    assert trailer["run"] == (
        "PYTHONPATH=features/jmerge/src:features/jleak/src python3 scripts/no_ai_trailers.py"
    )
    assert found[-1] is trailer and "continue-on-error" not in trailer
    assert [c for c in (True, False) if worked(trailer["if"], {"!cancelled()": c})] == [True]
    assert trailer["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
    assert "no_ai_trailers" not in " ".join(map(str, steps(CHECK.read_text(), "check-shard")[0]))


class Compare:
    """GitHub's compare API for one range, served on localhost a page at a time. It records
    the requests for that range's path and answers 404 to any other, such as a stray probe of
    local ports from another process on the desk."""

    def __init__(self, messages, path):
        import http.server
        import threading
        from urllib.parse import parse_qs, urlsplit

        listed = [{"sha": f"{at:040x}", "commit": {"message": m}} for at, m in enumerate(messages)]
        self.asked = []
        asked = self.asked

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                url = urlsplit(self.path)
                if url.path != path:
                    self.send_error(404)
                    return
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


def no_ai_trailers(tmp_path, messages, title="feat: a change", body="Why it changed.", strays=()):
    """Run the check's script on a pull request with these commits, as the step runs it, after
    the fake server is sent a GET for each stray path, as another process on the desk may."""
    import urllib.error
    import urllib.request

    event = tmp_path / "event.json"
    base, head = "b" * 40, "h" * 40
    pull = {"title": title, "body": body, "base": {"sha": base}, "head": {"sha": head}}
    event.write_text(json.dumps({"pull_request": pull}))
    compare = Compare(messages, f"/repos/owner/repo/compare/{base}...{head}")
    try:
        for stray in strays:
            with pytest.raises(urllib.error.HTTPError) as refused:
                urllib.request.urlopen(compare.url + stray, timeout=10)
            assert refused.value.code == 404
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


def test_a_stray_local_request_to_the_fake_compare_server_leaves_the_ai_trailer_check_alone(
    tmp_path,
):
    """A bare `GET /` from another process probing local ports is answered 404 and not
    recorded, so the check still reads the one compare request it made."""
    code, printed, asked = no_ai_trailers(
        tmp_path, ["feat: one", f"fix: two\n\nWhy.\n\n{CLAUDE}"], strays=["/"]
    )
    assert code == 1
    sha = f"{1:040x}"[:12]
    assert printed[0] == f"::error title=AI co-author trailer::commit {sha} line 5: {CLAUDE}"
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


def test_a_reuse_skips_the_parts_tests_and_check_passes_on_it_and_a_miss_runs_them():
    """A pull request's run whose two trees a passed check already checked runs no test in its
    eight parts, and `check`, the required check, passes on the reuse. The parts start with
    `reuse`, needing no job, so that they set up while it selects. A lookup that failed or found
    nothing runs the tests, and `check` then passes only when every part did. A `reuse` job that
    failed, as on an AI co-author trailer, fails `check` whatever the parts did."""
    assert (
        ran_on("check-shard", reused="true") == ran_on("check-shard", reused="") == ["pull_request"]
    )
    assert job_line("check-shard", "needs") is None
    (every, *_), _ = steps(CHECK.read_text(), "check")
    assert every["env"]["REUSED"] == "${{ needs.reuse.outputs.reused }}"
    assert every["env"]["REUSE"] == "${{ needs.reuse.result }}"
    assert every["env"]["LINT"] == "${{ needs.lint.result }}"
    passes = [
        (reuse, reused, lint, result)
        for reuse in RESULTS
        for reused in ("true", "false", "")
        for lint in RESULTS
        for result in RESULTS
        if subprocess.run(
            ["sh", "-c", every["run"]],
            env={"PARTS": result, "LINT": lint, "REUSE": reuse, "REUSED": reused},
            capture_output=True,
            text=True,
        ).returncode
        == 0
    ]
    assert passes == [("success", "true", "success", result) for result in RESULTS] + [
        ("success", "false", "success", "success"),
        ("success", "", "success", "success"),
    ]


def test_a_run_whose_parts_passed_leaves_the_marker_of_its_two_trees_and_a_reuse_leaves_none():
    found, _ = steps(CHECK.read_text(), "check")
    at = next(k for k, step in enumerate(found) if step.get("id") == "checked")
    mark, upload = found[at : at + 2]
    outputs = job_section("reuse", "outputs")
    assert {key: outputs[key] for key in ("name", "reused", "failed", "lookup")} == {
        "name": "${{ steps.reuse.outputs.name }}",
        "reused": "${{ steps.reuse.outputs.reused }}",
        "failed": "${{ steps.failed.outputs.tests }}",
        "lookup": "${{ steps.failed.outcome }}",
    }
    assert [
        (result, lint, reuse, name, reused)
        for result in RESULTS
        for lint in RESULTS
        for reuse in RESULTS
        for name in ("checked-tree-a-b", "")
        for reused in ("true", "false", "")
        if worked(
            mark["if"],
            {
                "needs.check-shard.result": result,
                "needs.lint.result": lint,
                "needs.reuse.result": reuse,
                "needs.reuse.outputs.name": name,
                "needs.reuse.outputs.reused": reused,
            },
        )
    ] == [
        ("success", "success", "success", "checked-tree-a-b", "false"),
        ("success", "success", "success", "checked-tree-a-b", ""),
    ]
    assert mark["env"] == {"NAME": "${{ needs.reuse.outputs.name }}"}
    assert [o for o in OUTCOMES if worked(upload["if"], {"steps.checked.outcome": o})] == [
        "success"
    ]
    assert upload["continue-on-error"] is True
    assert upload["with"]["name"] == "${{ needs.reuse.outputs.name }}"


def test_the_reuse_lookup_is_plain_python_after_a_checkout_of_two_commits():
    """It reads the merge's base, HEAD^1, so the checkout has two commits of history, and it runs
    before any `uv sync`, with nothing but the runner's python3."""
    (checkout, look, *_), keys = steps(CHECK.read_text(), "reuse")
    assert checkout["with"] == {"persist-credentials": False, "fetch-depth": "2"}
    assert look["run"] == "PYTHONPATH=features/jmerge/src python3 -m jmerge.reuse"
    assert (look["id"], look["continue-on-error"]) == ("reuse", True)
    assert look["env"] == {"GH_TOKEN": "${{ github.token }}"}


def reuse(tmp_path, answers, **env):
    """Run the lookup in a new repo of two commits, a base and a merge over it, against a `gh`
    that answers from `answers`, which maps a path to its answer or is a function of the
    artifact's name that gives them. Return its outputs, what it printed, and the artifact's
    name."""
    repo, bin, said = tmp_path / "repo", tmp_path / "bin", tmp_path / "said"
    for made in (repo, bin, said):
        made.mkdir()
    git = ["git", "-c", "user.name=a", "-c", "user.email=a@example.com", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True)
    for text in ("base\n", "merge\n"):
        (repo / "file").write_text(text)
        subprocess.run([*git, "add", "file"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", text.strip()], check=True)

    def tree(commit):
        done = subprocess.run([*git, "rev-parse", f"{commit}^{{tree}}"], capture_output=True)
        return done.stdout.decode().strip()

    name = f"checked-tree-{tree('HEAD^1')}-{tree('HEAD')}"
    if callable(answers):
        answers = answers(name)
    for path, body in answers.items():
        (said / path.replace("/", "_")).write_text(json.dumps(body))
    (bin / "git").symlink_to(shutil.which("git"))
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
        [sys.executable, "-m", "jmerge.reuse"],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            "PATH": str(bin),
            "PYTHONPATH": str(REPO / "features" / "jmerge" / "src"),
            "GITHUB_OUTPUT": str(tmp_path / "output"),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_RUN_ATTEMPT": "1",
            **env,
        },
    )
    assert ran.returncode == 0, ran.stderr
    outputs = dict(line.split("=", 1) for line in (tmp_path / "output").read_text().splitlines())
    return outputs, ran.stdout.strip(), name


def pair(git, base, head):
    """The artifact a pull request's check names, as GitHub's merge of `head` over `base` and the
    lookup give it: the base's tree and the merge's."""
    from jmerge import green

    def said(*args):
        return subprocess.run([*git, *args], check=True, capture_output=True, text=True).stdout

    merged = said("merge-tree", "--write-tree", base, head).split()[0]
    return green.checked(said("rev-parse", f"{base}^{{tree}}").strip(), merged)


@pytest.mark.parametrize("main_moved", [False, True])
def test_a_clean_move_onto_main_checks_the_pair_its_stacked_run_checked(tmp_path, main_moved):
    """The premise the reuse rests on, on real commits: a child stacked on beta, beta squashed onto
    main, and the child's own commit replayed onto the squash. Its run at the moved head checks
    the pair its stacked run checked. Where main took a commit before beta merged, the squash
    holds it, and the pair differs, so the suite runs."""
    git = ["git", "-c", "user.name=a", "-c", "user.email=a@example.com", "-C", str(tmp_path)]

    def commit(name, text, *more):
        (tmp_path / name).write_text(text)
        subprocess.run([*git, "add", name], check=True)
        subprocess.run([*git, "commit", "-q", "-m", name, *more], check=True)
        return subprocess.run(
            [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()

    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    start = commit("a", "start\n")
    subprocess.run([*git, "switch", "-q", "-c", "beta"], check=True)
    commit("b", "beta one\n")
    beta = commit("b", "beta two\n")
    child = commit("c", "the child\n")
    stacked = pair(git, beta, child)
    subprocess.run([*git, "switch", "-q", "--detach", start], check=True)
    if main_moved:
        commit("d", "another task\n")
    subprocess.run([*git, "merge", "-q", "--squash", beta], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "beta (#8)"], check=True)
    subprocess.run([*git, "cherry-pick", child], check=True, capture_output=True)
    moved = pair(git, "HEAD^", "HEAD")
    assert (moved == stacked) is not main_moved


def test_the_trees_a_passed_check_checked_are_reused_and_the_log_names_its_run(tmp_path):
    """The stacked link's move onto main, a clean replay: the run at the moved head checks the
    base and merge trees its stacked run passed, so it reuses that pass."""
    outputs, printed, name = reuse(tmp_path, {ARTIFACTS: marker(), RUN: run()})
    assert outputs == {"name": name, "reused": "true"}
    assert printed == f"reuse: {name}: passed the check in {URL}, so the suite is skipped"
    asked = (tmp_path / "asked").read_text().splitlines()
    assert asked == [f"api {ARTIFACTS}?name={name}&per_page=100", f"api {RUN}"]


@pytest.mark.parametrize(
    ("answers", "why"),
    [
        ({ARTIFACTS: {"artifacts": []}}, "no passed check left a marker of them"),
        ({ARTIFACTS: marker(), RUN: run(conclusion="failure")}, "no passed check left a marker"),
        (
            {ARTIFACTS: marker(), RUN: run(head_repository={"id": 2})},
            "only a fork's run passed them",
        ),
    ],
)
def test_trees_no_passed_check_of_this_repo_checked_run_the_suite(tmp_path, answers, why):
    """A move that is no clean replay checks other trees, whose name no run left: the suite runs
    as it always did. So does a pair only a failed run, or a fork's, left."""
    outputs, printed, name = reuse(tmp_path, answers)
    assert outputs == {"name": name, "reused": "false"}
    assert printed.startswith(f"reuse: {name}: {why}"), printed


@pytest.mark.parametrize(
    ("env", "why"),
    [
        ({"GITHUB_RUN_ATTEMPT": "2"}, "a run again always runs the suite"),
        ({"GITHUB_EVENT_NAME": "push"}, "only a pull request's check reuses a pass"),
    ],
)
def test_a_run_again_and_a_push_never_reuse_and_ask_nothing(tmp_path, env, why):
    outputs, printed, _ = reuse(tmp_path, {ARTIFACTS: marker(), RUN: run()}, **env)
    assert outputs["reused"] == "false"
    assert why in printed
    assert not (tmp_path / "asked").exists()


def test_a_lookup_that_cannot_ask_runs_the_suite_and_warns(tmp_path):
    outputs, printed, name = reuse(tmp_path, {})
    assert outputs == {"name": name, "reused": "false"}
    assert printed.startswith(f"::warning::reuse: {name}: could not ask (HTTP 403"), printed


@pytest.mark.parametrize(
    "path,changed",
    [("features/jbus/src/jbus/tick.py", True), ("features/jbus/docs/jbus.md", False)],
)
def test_the_parts_record_the_lines_they_run_and_check_reads_them_before_any_marker(
    tmp_path, path, changed
):
    """No part runs a test a second time for the guard of test_new_lines_run.py: each part's
    `make test` records the lines of the changed feature code its tests run and uploads them, and
    `check` downloads every part's upload of the same attempt and runs the guard on them, only
    where the change touches a feature's src/ or scripts/. A marker of a pass comes after the
    guard, so a run whose guard failed leaves none."""
    parts, _ = steps(CHECK.read_text(), "check-shard")
    test = next(step for step in parts if step.get("name") == "make test")
    assert 'NEW_LINES_PART="$RUNNER_TEMP/new-lines"' in test["run"]
    upload = next(
        step for step in parts if step.get("with", {}).get("path") == "${{ runner.temp }}/new-lines"
    )
    assert upload["with"]["name"] == "new-lines-${{ github.run_attempt }}-${{ matrix.shard }}"
    found, _ = steps(CHECK.read_text(), "check")
    names = [step.get("id", step.get("name", step.get("uses", ""))) for step in found]
    code, guard = found[names.index("code")], found[names.index("new lines")]
    download = next(step for step in found if "download-artifact" in step.get("uses", ""))
    assert fnmatch(
        upload["with"]["name"].replace("${{ matrix.shard }}", "3"), download["with"]["pattern"]
    )
    assert "merge-multiple" not in download["with"], "every part names its record alike"
    assert guard["env"]["NEW_LINES_PARTS"] == download["with"]["path"]
    assert "features/repo-guards/tests/test_new_lines_run.py" in guard["run"]
    assert names.index("new lines") < names.index("checked") < names.index("marker")
    assert all("always()" not in str(step.get("if")) for step in found[names.index("new lines") :])
    repo = tmp_path / "repo"
    (repo / path).parent.mkdir(parents=True)
    git = ["git", "-c", "user.name=a", "-c", "user.email=a@example.com", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True)
    for text in ("base\n", "merge\n"):
        (repo / path).write_text(text)
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-q", "-m", text.strip()], check=True)
    output = tmp_path / "output"
    output.write_text("")
    subprocess.run(
        ["sh", "-c", code["run"]],
        cwd=repo,
        env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(output)},
        check=True,
    )
    assert output.read_text() == ("changed=true\n" if changed else "")
