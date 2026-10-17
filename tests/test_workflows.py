"""The check workflow runs on main as well as on every pull request, and a run on main is
never cancelled by the next one: each push's run is a concurrency group of its own. A pull
request gets the job `check`, the fast one, with the lint and the tests its change reaches,
and a push to main and a manual run get the job `full`, the whole suite.

The workflow file is read as YAML, by the little of it these two blocks use: mappings by
their indentation, a scalar, and a list in brackets.

Every job but the pull request's `check` takes its runner from one repo variable, and the
repo's local ephemeral runner, `jstack-ephemeral`, when the repo has none: never GitHub's,
since every CI job runs locally. The `check` runs on the local fast lane, the runner labelled
`jstack-fast`, which takes no full suite's job and so never queues behind one; the lane stops
a job at 10 minutes, so the `check` is cancelled by GitHub at 9, before the lane stops it.
The check names Google Chrome as its test browser on every runner. Every workflow is given
read access to the contents and no more, and none runs on `pull_request_target`. The check
may also read the repo's artifacts, which is where a green run's marker is.

A run of `full` whose tree a green run already tested skips the suite, by its steps and never
by its job or its triggers, so `full` is always reported. Only `full` asks for a marker and
leaves one: a marker says the full suite passed a tree. The script that asks is
run here in a temporary repo, against a `gh` that answers from files.

The drift step keeps jdrift's clone of pstack in the runner's temporary directory, which
does not outlive the job."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
CHECK = WORKFLOWS / "check.yml"
DRIFT = WORKFLOWS / "pstack-drift.yml"
GREEN_TREE = WORKFLOWS.parent.parent / "scripts" / "green_tree.py"
PICK = (
    "${{ startsWith(vars.RUNS_ON, '[') && fromJSON(vars.RUNS_ON)"
    " || vars.RUNS_ON || 'jstack-ephemeral' }}"
)
FAST = "[self-hosted, jstack-fast]"


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


def test_the_check_runs_on_every_pull_request_on_each_push_to_main_and_by_hand():
    assert block("on") == {
        "pull_request": None,
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }


def worked(expression, values):
    """What an expression gives with these values for the names in it, worked out here.

    It reads `&&`, `||`, `==`, `!=` and a string in single quotes, as `picked` does.
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


def test_every_job_but_the_fast_check_takes_its_runner_from_the_repos_variable():
    assert {path.name: jobs(path.read_text()) for path in sorted(WORKFLOWS.glob("*.yml"))} == {
        "check.yml": {"check": FAST, "full": PICK},
        "pstack-drift.yml": {"drift": PICK},
    }


def picked(expression, variable):
    """What a `runs-on` expression gives for one value of the repo's variable, worked out here.

    It reads the little of GitHub's expressions the pick uses: `&&` and `||`, which give one
    of their operands as Python's `and` and `or` do, `startsWith`, `fromJSON`, a string in
    single quotes, and a variable, which is the empty string when the repo has none.
    """
    assert expression.startswith("${{ ") and expression.endswith(" }}"), expression
    names = {
        "__builtins__": {},
        "startsWith": lambda text, start: text.startswith(start),
        "fromJSON": json.loads,
        "RUNS_ON": variable,
    }
    inner = expression[4:-3].replace("vars.RUNS_ON", "RUNS_ON")
    return eval(inner.replace("&&", " and ").replace("||", " or "), names)


def test_the_runner_is_the_local_one_with_no_variable_and_a_label_or_a_list_of_them_with_one():
    for runs_on in {
        runs_on
        for found in map(jobs, map(Path.read_text, WORKFLOWS.glob("*.yml")))
        for runs_on in found.values()
        if runs_on != FAST
    }:
        assert picked(runs_on, "") == "jstack-ephemeral"
        assert picked(runs_on, "jstack") == "jstack"
        assert picked(runs_on, '["one", "two"]') == ["one", "two"]


def test_no_file_under_github_names_a_runner_of_its_own_but_the_checks_fast_lane():
    named = [
        (path.name, line.strip())
        for path in sorted(WORKFLOWS.parent.rglob("*"))
        if path.is_file()
        for line in path.read_text().splitlines()
        if "self-hosted" in line
    ]
    assert named == [("check.yml", f"runs-on: {FAST}")]


def test_every_workflow_may_read_the_contents_and_no_more_and_none_runs_for_a_fork_with_secrets():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        more = {"actions": "read"} if path == CHECK else {}
        assert block("permissions", path) == {"contents": "read"} | more, path.name
        assert "pull_request_target" not in path.read_text(), path.name


CHROME = {"JSTACK_TEST_BROWSER": "/usr/bin/google-chrome"}
FAST_LANE_CPUS = 4
WORKER_CPUS = 0.8


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


WORKERS = {"TEST_WORKERS": str(round(FAST_LANE_CPUS / WORKER_CPUS))}


def test_the_fast_check_runs_enough_workers_to_use_the_cpus_the_lane_gives_it():
    """The container is capped at the pool's FAST_CPUS, but `nproc` in it counts the host's
    processors, so the Makefile's count would give a runner two workers and leave the rest idle.
    A worker uses about 0.8 of a processor (the Makefile's figure), so 4 CPUs take 5 workers."""
    assert job_env(CHECK.read_text(), "check")["TEST_WORKERS"] == WORKERS["TEST_WORKERS"] == "5"
    assert "TEST_WORKERS" not in job_env(CHECK.read_text(), "full")


def test_each_job_names_google_chrome_once_for_all_its_steps():
    text = CHECK.read_text()
    assert (job_env(text, "check"), job_env(text, "full")) == (CHROME | WORKERS, CHROME)
    named = [step for job in ("check", "full") for step in steps(text, job)[0] if "env" in step]
    assert [step["name"] for step in named] == ["green tree", "green tree marker"]
    assert text.count("JSTACK_TEST_BROWSER: ") == 2


def test_a_job_env_is_read_from_its_own_job_and_not_from_a_step():
    text = (
        "jobs:\n  one:\n    env:\n      A: b\n    steps:\n      - run: true\n"
        "  two:\n    steps:\n      - name: x\n        env:\n          C: d\n"
    )
    assert (job_env(text, "one"), job_env(text, "two")) == ({"A": "b"}, None)


@pytest.mark.parametrize(
    ("job", "suite", "when"),
    [
        ("check", "make check-fast", None),
        ("full", "make check", "steps.tree.outputs.marker != 'green'"),
    ],
)
def test_the_browser_is_looked_for_right_before_the_tests_and_its_absence_fails_naming_it(
    tmp_path, job, suite, when
):
    found, _ = steps(CHECK.read_text(), job)
    names = [step.get("name") for step in found]
    look = found[names.index("test browser")]
    assert names.index(suite) == names.index("test browser") + 1
    assert look.get("if") == when
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


def test_the_fast_check_is_cancelled_before_the_lane_stops_it_and_full_after_fifteen_minutes():
    text = "jobs:\n  other:\n    steps:\n      - timeout-minutes: 1\n  check:\n"
    text += "    timeout-minutes: 9\n"
    assert (cap(text, "check"), cap(text, "other")) == ("9", None)
    assert (cap(CHECK.read_text(), "check"), cap(CHECK.read_text(), "full")) == ("9", "15")


UNLESS_GREEN = "steps.tree.outputs.marker != 'green'"
OR_THE_DESKS = f"{UNLESS_GREEN} || steps.tree.outputs.from == 'desk'"


EVENTS = ("pull_request", "push", "workflow_dispatch")


def ran_on(job):
    """The events a job of the check runs on, worked out from its `if`."""
    inside, when = False, None
    for line in CHECK.read_text().splitlines():
        indent = len(line) - len(line.lstrip())
        if indent <= 2 and line.strip() and not line.lstrip().startswith("#"):
            inside = indent == 2 and line.strip() == f"{job}:"
        elif inside and indent == 4 and line.startswith("    if: "):
            when = line.partition(": ")[2]
    return [e for e in EVENTS if worked(when, {"github.event_name": e})]


def test_a_pull_request_runs_check_and_a_push_to_main_and_a_manual_run_run_full():
    assert jobs(CHECK.read_text()) == {"check": FAST, "full": PICK}
    assert (ran_on("check"), ran_on("full")) == (["pull_request"], ["push", "workflow_dispatch"])


def test_the_fast_check_reads_two_commits_and_runs_the_tests_its_change_reaches_over_main():
    found, keys = steps(CHECK.read_text(), "check")
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in found] == [
        "actions/checkout",
        "astral-sh/setup-uv",
        "uv sync --locked",
        'test -x "$JSTACK_TEST_BROWSER" || { echo "::error::no test browser at'
        ' $JSTACK_TEST_BROWSER, which the check declares"; exit 1; }',
        "make check-fast BASE=HEAD^1",
    ]
    assert found[0]["with"] == {"persist-credentials": False, "fetch-depth": "2"}
    assert all("if" not in step for step in found)


def test_only_the_full_suite_asks_for_a_marker_and_leaves_one():
    marking = ("green_tree.py", "green-tree", "upload-artifact", "steps.tree", "steps.suite")
    for job, marks in (("check", False), ("full", True)):
        said = " ".join(map(str, steps(CHECK.read_text(), job)[0]))
        assert [word for word in marking if word in said] == (list(marking) if marks else []), job


def test_a_green_tree_skips_the_suite_by_its_steps_and_the_job_always_runs():
    found, keys = steps(CHECK.read_text(), "full")
    assert "if" in keys and ran_on("full") == ["push", "workflow_dispatch"]
    assert [step.get("uses", step.get("run")).partition("@")[0] for step in found] == [
        "actions/checkout",
        "python3 scripts/green_tree.py",
        "astral-sh/setup-uv",
        "uv sync --locked",
        'test -x "$JSTACK_TEST_BROWSER" || { echo "::error::no test browser at'
        ' $JSTACK_TEST_BROWSER, which the check declares"; exit 1; }',
        "make check",
        'mkdir -p "$RUNNER_TEMP/green-tree" && touch "$RUNNER_TEMP/green-tree/$NAME"',
        "actions/upload-artifact",
        'echo "::warning::green-tree, the lookup ended ${{ steps.tree.outcome }} and the upload'
        ' ${{ steps.upload.outcome }}, so a later run of this tree may not skip the suite"',
    ]
    checkout, ask, setup, sync, _, suite, *_ = found
    assert "if" not in checkout
    assert (ask.get("if"), ask["id"], ask["continue-on-error"]) == (None, "tree", True)
    assert [step["if"] for step in (setup, sync, suite)] == [
        OR_THE_DESKS,
        OR_THE_DESKS,
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
    found, _ = steps(CHECK.read_text(), "full")
    _, _, setup, sync, _, suite, *_ = found
    assert (sync["run"], suite["run"]) == ("uv sync --locked", "make check")
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
    everything = ["astral-sh/setup-uv", "uv sync --locked", "make check"]
    assert ran == {
        ("green", "desk"): everything[:2],
        ("green", "run"): [],
        ("none", ""): everything,
        ("unknown", ""): everything,
    }


OUTCOMES = ("success", "failure", "cancelled", "skipped", "")


def test_the_marker_is_left_only_after_the_suite_ran_and_passed():
    *_, mark, upload, warn = steps(CHECK.read_text(), "full")[0]
    assert [
        (outcome, name)
        for outcome in OUTCOMES
        for name in ("green-tree-1", "")
        if worked(mark["if"], {"steps.suite.outcome": outcome, "steps.tree.outputs.name": name})
    ] == [("success", "green-tree-1")]
    assert mark["id"] == "marker"
    assert [o for o in OUTCOMES if worked(upload["if"], {"steps.marker.outcome": o})] == ["success"]
    text = CHECK.read_text()
    assert "\n          NAME: ${{ steps.tree.outputs.name }}\n" in text
    assert "\n          name: ${{ steps.tree.outputs.name }}\n" in text
    assert (
        "\n          path: ${{ runner.temp }}/green-tree/${{ steps.tree.outputs.name }}\n" in text
    )


def test_a_lookup_or_an_upload_that_failed_never_fails_the_run_and_is_a_warning_on_it():
    *_, upload, warn = steps(CHECK.read_text(), "full")[0]
    assert (upload["id"], upload["continue-on-error"]) == ("upload", True)
    assert [
        (tree, sent)
        for tree in ("success", "failure")
        for sent in ("success", "failure", "skipped")
        if worked(warn["if"], {"steps.tree.outcome": tree, "steps.upload.outcome": sent})
    ] == [
        ("success", "failure"),
        ("failure", "success"),
        ("failure", "failure"),
        ("failure", "skipped"),
    ]


def green_tree(tmp_path, answers, **env):
    """Run the script in a new repo against a `gh` that answers from these files.

    The answers are by path, or a function that gives them for the repo's tree. With none for
    it, the tree has no ref: the desk left no marker.

    Gives the step's outputs, what it printed, the tree, and the paths `gh` was asked for.
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
    for path, body in ({f"{REFS}/{tree}": []} | (answers or {})).items():
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
        [sys.executable, str(GREEN_TREE)],
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
        f"api {REFS}/{tree}",
        f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100",
        f"api {RUN}",
    ]


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
    assert asked == [f"api {REFS}/{tree}", f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100"]


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


def ref(tree, **changed):
    """What GitHub lists for the ref the desk pushed for a tree, at the commit c0ffee."""
    name = f"refs/jstack/green-tree/{tree}"
    return [{"ref": name, "object": {"sha": "c0ffee", "type": "commit"}} | changed]


def test_a_tree_the_desk_marked_is_green_and_the_log_names_the_desk(tmp_path):
    outputs, printed, tree, asked = green_tree(
        tmp_path, lambda tree: {f"{REFS}/{tree}": ref(tree), COMMIT: {"tree": {"sha": tree}}}
    )
    assert outputs == {"name": f"green-tree-{tree}", "marker": "green", "from": "desk"}
    assert printed == (
        f"green-tree: tree {tree}: passed a fresh check on the desk, which marked it with the"
        " commit c0ffee, so the suite is skipped"
    )
    assert asked == [f"api {REFS}/{tree}", f"api {COMMIT}"]


@pytest.mark.parametrize(
    "listed",
    [
        lambda tree: {f"{REFS}/{tree}": ref(tree), COMMIT: {"tree": {"sha": "0ther"}}},
        lambda tree: {f"{REFS}/{tree}": ref(tree), COMMIT: {}},
        lambda tree: {f"{REFS}/{tree}": ref(tree, ref=f"refs/jstack/green-tree/{tree}0")},
        lambda tree: {f"{REFS}/{tree}": ref(tree, object={"sha": "c0ffee", "type": "tag"})},
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
    assert asked[-1] == f"api {ARTIFACTS}?name=green-tree-{tree}&per_page=100"


def test_a_ref_whose_commit_cannot_be_read_runs_the_suite(tmp_path):
    outputs, printed, tree, asked = green_tree(tmp_path, lambda tree: {f"{REFS}/{tree}": ref(tree)})
    assert outputs == {"name": f"green-tree-{tree}", "marker": "unknown", "from": ""}
    assert printed.startswith("::warning::green-tree: ") and ": could not ask (" in printed
    assert asked == [f"api {REFS}/{tree}", f"api {COMMIT}"]


def test_a_manual_run_and_a_run_again_run_the_suite_on_a_tree_the_desk_marked(tmp_path):
    def marked(tree):
        return {f"{REFS}/{tree}": ref(tree), COMMIT: {"tree": {"sha": tree}}}

    for at, env in enumerate(
        ({"GITHUB_EVENT_NAME": "workflow_dispatch"}, {"GITHUB_RUN_ATTEMPT": "2"})
    ):
        (tmp_path / str(at)).mkdir()
        outputs, _, tree, asked = green_tree(tmp_path / str(at), marked, **env)
        assert outputs == {"name": f"green-tree-{tree}", "marker": "unasked", "from": ""}
        assert asked == []
