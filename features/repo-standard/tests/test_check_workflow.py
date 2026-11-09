"""The shared check workflow, `.github/workflows/repo-standard-check.yml`, run on a fixture caller.

The fixture is a small git repo that is not jstack, with a `.repo-standard.yml`, a Makefile whose
`select`, `lint` and `test` targets print what they were asked, and an upstream: a git repo tagged
`repo-standard-v1` that holds the repo-standard and jmerge code the workflow takes from jstack.
`run_job` runs a job of the workflow as GitHub would, step by step: it evaluates each step's `if:`,
with `success()` in front of one that names no status function, and the `${{ }}` of its job's and
its own `env:`, runs its `run:` under bash with `$GITHUB_OUTPUT` and `$GITHUB_STEP_SUMMARY`, and
records what an `upload-artifact` step would upload. Given a `store`, a dict, an upload copies its
path there under its name, the last upload of a name kept, and a `download-artifact` step copies
each stored artifact its pattern matches back, each to a folder of its name, as GitHub does with no
`merge-multiple`. A `gh` on the path that always fails stands in for GitHub,
so a lookup of a marker cannot ask and runs the tests, as the workflow does with no network.

The workflow and /new-home's template, the caller every repo starts from, are read with the
standard's own YAML reader, `repo_standard.config.parse`, which refuses what it cannot read.
"""

import fnmatch
import json
import os
import re
import shutil
import subprocess

import pytest

from repo_standard.cli import main
from repo_standard.config import parse
from repo_standard.conform import TAG, UPSTREAM, VERSION
from repo_standard.plan import ALL, NONE
from testing.paths import REPO

WORKFLOW = REPO / ".github" / "workflows" / "repo-standard-check.yml"
TEMPLATE = REPO / "features" / "home" / "templates" / "check.yml"
CALLED = f"JoshuaHayesWasHere/jstack/.github/workflows/repo-standard-check.yml@{TAG}{VERSION}"
TOOL = ("features/repo-standard/src", "features/jmerge/src", "scripts/green_tree.py")
SELECTED = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]
SHELLS = {
    "": ["bash", "-e", "-c"],
    "bash": ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"],
}
"""How GitHub runs a `run:` step on Linux: with no shell named, `bash -e`, which lets a pipe hide a
failure, and with `shell: bash`, the same with pipefail."""
EXPRESSION = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
STATUS = re.compile(r"\b(?:always|success|failure|cancelled)\(")
TOKEN = re.compile(
    r"\s*(?:'((?:[^']|'')*)'|(==|!=|&&|\|\||!|\(|\)|\[|\]|,)|(\d+)|([A-Za-z_][\w.-]*))"
)


def workflow():
    return parse(WORKFLOW.read_text())


def template(command="make check"):
    text = TEMPLATE.read_text()
    assert text.count("<the check command>") == 1
    return parse(text.replace("<the check command>", command.replace("'", "''")))


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def commit(root, files, message):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    git(root, "add", "-A")
    git(
        root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-qm", message
    )


def makefile(selection):
    printed = "".join(f"\t@echo '{one}'\n" for one in selection)
    return (
        f"select:\n{printed or chr(9) + '@true' + chr(10)}"
        'lint:\n\t@echo "make lint $(BASE)" >> "$(MAKE_LOG)"\n'
        'test:\n\t@echo "make test TESTS=$(TESTS) SHARD=$(SHARD)" >> "$(MAKE_LOG)"\n'
        'e2e:\n\t@echo "make e2e E2E_LIST=$(if $(E2E_LIST),given)" >> "$(MAKE_LOG)"\n'
        '\t@$(if $(E2E_LIST),cat "$(E2E_LIST)" >> "$(MAKE_LOG)")\n'
    )


@pytest.fixture
def caller(tmp_path):
    """A caller repo with two commits, the upstream it clones, and the env every step gets.

    The env takes only PATH and HOME from the runner's, so nothing else there reaches a step: a
    SHARD or TESTS in the env of CI's full run, or exported by a make such as `make check
    SHARD=K/4`, would otherwise reach the caller's make and change what it is asked."""
    upstream = tmp_path / "upstream"
    for part in TOOL:
        source, target = REPO / part, upstream / part
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)
    git(upstream, "init", "-q")
    commit(upstream, {}, "the tool")
    git(upstream, "tag", f"{TAG}{VERSION}")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, {"README.md": "a repo\n"}, "first")
    commit(repo, {"Makefile": makefile(SELECTED), ".repo-standard.yml": "standard: 1\n"}, "second")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "gh").write_text("#!/bin/sh\necho 'gh: no network here' >&2\nexit 1\n")
    (bin_ / "gh").chmod(0o755)
    env = {
        "HOME": os.environ["HOME"],
        "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_REPOSITORY": "someone/repo",
        "GITHUB_RUN_ATTEMPT": "1",
        "MAKE_LOG": str(tmp_path / "make.log"),
        "REPO_STANDARD_UPSTREAM": str(upstream),
    }
    return repo, env


def lookup(name, context):
    value = context
    for key in name.split("."):
        value = value.get(key, "") if isinstance(value, dict) else ""
    return value


def evaluate(expression, context, root):
    """The value of a GitHub expression, for the operators and functions the workflow uses."""
    failed = context.get("failed", False)
    functions = {
        "always": lambda: True,
        "success": lambda: not failed,
        "failure": lambda: failed,
        "cancelled": lambda: False,
        "fromJSON": json.loads,
        "format": lambda text, *values: text.format(*values),
        "hashFiles": lambda path: "hashed" if (root / path).is_file() else "",
    }
    words, at = [], 0
    expression = expression.strip()
    while at < len(expression):
        found = TOKEN.match(expression, at)
        assert found and found.end() > at, f"cannot read {expression[at:]!r}"
        text, operator, number, name = found.groups()
        if text is not None:
            words.append(repr(text.replace("''", "'")))
        elif operator:
            words.append({"&&": " and ", "||": " or ", "!": " not "}.get(operator, operator))
        elif number:
            words.append(number)
        elif expression[found.end() :].lstrip().startswith("("):
            words.append(f"functions[{name!r}]")
        else:
            words.append(repr(lookup(name, context)))
        at = found.end()
    return eval("".join(words), {"functions": functions})


def substitute(text, context, root):
    def one(found):
        value = evaluate(found[1], context, root)
        return json.dumps(value) if isinstance(value, (list, dict)) else str(value)

    return EXPRESSION.sub(one, str(text))


def run_job(name, repo, env, context, top=None, store=None):
    """Run job `name` of the workflow in `repo`: each step's outputs, outcome and the artifacts
    it uploaded, keyed by its id or name, and the job's outputs. A failed step fails the job, and
    only the steps whose `if:` asks for a failure run after it."""
    top = top or workflow()
    job = top["jobs"][name]
    steps, uploaded = {}, []
    context = {**context, "steps": steps, "failed": False}
    temp = repo.parent / f"temp-{name}-{len(list(repo.parent.glob('temp-*')))}"
    temp.mkdir()
    summary = temp / "summary.md"
    workflow_env = top.get("env", {}).items()
    base = {**{key: substitute(value, context, repo) for key, value in workflow_env}, **env}
    base.update(
        {key: substitute(value, context, repo) for key, value in job.get("env", {}).items()}
    )
    base["RUNNER_TEMP"] = str(temp)
    context["runner"] = {"temp": str(temp)}
    for at, step in enumerate(job["steps"]):
        key = step.get("id") or step.get("name") or f"step{at}"
        condition = step.get("if", "success()")
        if not STATUS.search(EXPRESSION.sub(r"\1", condition)):
            condition = f"success() && ({condition})"
        if not evaluate(condition, context, repo):
            steps[key] = {"outputs": {}, "outcome": "skipped"}
            continue
        action = step.get("uses", "")
        if action.startswith("actions/checkout@"):
            steps[key] = {"outputs": {}, "outcome": "success"}
            continue
        if action.startswith("actions/upload-artifact@"):
            artifact = substitute(step["with"]["name"], context, repo)
            uploaded.append(artifact)
            path = substitute(step["with"]["path"], context, repo)
            if store is not None and os.path.exists(path):
                kept = repo.parent / "store" / artifact
                shutil.rmtree(kept, ignore_errors=True)
                if os.path.isdir(path):
                    shutil.copytree(path, kept)
                else:
                    kept.mkdir(parents=True)
                    shutil.copy(path, kept)
                store[artifact] = kept
            steps[key] = {"outputs": {}, "outcome": "success"}
            continue
        if action.startswith("actions/download-artifact@"):
            pattern = substitute(step["with"]["pattern"], context, repo)
            into = substitute(step["with"]["path"], context, repo)
            for artifact, kept in sorted((store or {}).items()):
                if fnmatch.fnmatchcase(artifact, pattern):
                    shutil.copytree(kept, os.path.join(into, artifact), dirs_exist_ok=True)
            steps[key] = {"outputs": {}, "outcome": "success"}
            continue
        assert "run" in step, f"{name}: the fixture runs no action {action}"
        output = repo.parent / f"output-{name}-{at}"
        output.write_text("")
        own = {k: substitute(v, context, repo) for k, v in step.get("env", {}).items()}
        done = subprocess.run(
            [*SHELLS[top.get("defaults", {}).get("run", {}).get("shell", "")], step["run"]],
            cwd=repo,
            env={**base, **own, "GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)},
            capture_output=True,
            text=True,
        )
        outputs = dict(line.split("=", 1) for line in output.read_text().splitlines() if line)
        outcome = "success" if done.returncode == 0 else "failure"
        steps[key] = {"outputs": outputs, "outcome": outcome, "said": done.stdout + done.stderr}
        if outcome == "failure" and not step.get("continue-on-error"):
            context["failed"] = True
    said = summary.read_text() if summary.exists() else ""
    if context["failed"]:
        return {
            "result": "failure",
            "steps": steps,
            "uploaded": uploaded,
            "outputs": {},
            "summary": said,
        }
    outputs = {k: substitute(v, context, repo) for k, v in job.get("outputs", {}).items()}
    return {
        "result": "success",
        "steps": steps,
        "uploaded": uploaded,
        "outputs": outputs,
        "summary": said,
    }


def github(event):
    return {"event_name": event, "token": "a-token"}


def planned(repo, env, event, inputs=None):
    env = {**env, "GITHUB_EVENT_NAME": event}
    inputs = {"runner": "ubuntu-24.04", "command": "", **(inputs or {})}
    done = run_job("plan", repo, env, {"github": github(event), "inputs": inputs})
    assert done["result"] == "success", done["steps"]
    return done["outputs"]


def configure(repo, text, selection=SELECTED):
    commit(repo, {".repo-standard.yml": text, "Makefile": makefile(selection)}, "config")


def test_a_pull_requests_plan_selects_its_tests_and_deals_them_to_the_parts_the_config_sets(
    caller,
):
    repo, env = caller
    configure(repo, "standard: 1\ncheck:\n  shards: 2\n")
    tree, base = (
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", f"{one}^{{tree}}"], capture_output=True, text=True
        ).stdout.strip()
        for one in ("HEAD", "HEAD^1")
    )
    said = planned(repo, env, "pull_request")
    assert said["mode"] == "standard"
    assert said["tag"] == f"{TAG}{VERSION}"
    assert said["run"] == "true"
    assert said["selection"] == "some"
    assert json.loads(said["shards"]) == [1, 2]
    assert json.loads(said["parts"]) == {
        "1": "tests/test_a.py tests/test_c.py",
        "2": "tests/test_b.py",
    }
    assert said["reused"] == "false"
    assert said["checked"] == f"checked-tree-{base}-{tree}"
    assert said["tree"] == f"green-tree-{tree}"
    assert said["marker"] == ""


def test_a_selection_of_all_runs_every_part_whole(caller):
    repo, env = caller
    configure(repo, "standard: 1\ncheck:\n  shards: 3\n", ["tests/test_a.py", "all"])
    said = planned(repo, env, "pull_request")
    assert said["selection"] == "all"
    assert json.loads(said["parts"]) == {"1": "all", "2": "all", "3": "all"}


def test_a_push_to_main_runs_the_whole_suite_in_one_part_by_default(caller):
    repo, env = caller
    said = planned(repo, env, "push")
    assert (said["run"], said["selection"], said["shards"]) == ("true", "all", "[1]")
    assert json.loads(said["parts"]) == {"1": "all"}
    assert said["marker"] == "unknown"
    assert said["reused"] == ""


@pytest.mark.parametrize(
    "config, run, shards",
    [
        ("standard: 1\n", "false", [1]),
        ("standard: 1\ncheck:\n  nightly: false\n", "false", [1]),
        ("standard: 1\ncheck:\n  nightly: true\n  shards: 4\n", "true", [1, 2, 3, 4]),
    ],
)
def test_the_nightly_run_tests_the_whole_suite_only_where_the_config_turns_it_on(
    caller, config, run, shards
):
    repo, env = caller
    configure(repo, config)
    said = planned(repo, env, "schedule")
    assert (said["run"], json.loads(said["shards"]), said["marker"]) == (run, shards, "")
    assert set(json.loads(said["parts"]).values()) == {"all"}


def test_a_repo_with_no_config_runs_its_check_command_alone(caller):
    repo, env = caller
    git(repo, "rm", "-q", ".repo-standard.yml")
    commit(repo, {}, "no config")
    said = planned(repo, env, "pull_request")
    assert said["mode"] == "command"
    assert said["run"] == ""
    needs = {"plan": {"result": "success", "outputs": said}}
    context = {"github": github("pull_request"), "needs": needs, "inputs": {"command": "x"}}
    assert evaluate(workflow()["jobs"]["command"]["if"], context, repo)
    for job in ("lint", "test"):
        assert not evaluate(workflow()["jobs"][job]["if"], context, repo)
    done = run_job("command", repo, env, {**context, "inputs": {"command": "make lint BASE=it"}})
    assert done["result"] == "success"
    assert (repo.parent / "make.log").read_text() == "make lint it\n"


@pytest.mark.parametrize(
    "config, step, said",
    [
        ("features: features\n", "standard", "pins no version"),
        ("standard: 2\n", "standard", "pins v2, and check.yml calls the shared check at"),
        ("standard: 1\ncheck:\n  shards: 0\n", "plan", "check.shards is not a number of parts"),
    ],
)
def test_a_config_the_plan_cannot_follow_fails_it(caller, config, step, said):
    repo, env = caller
    configure(repo, config)
    done = run_job("plan", repo, {**env, "GITHUB_EVENT_NAME": "push"}, {"github": github("push")})
    assert done["result"] == "failure"
    assert said in done["steps"][step]["said"]


def test_a_selection_of_fewer_ids_than_parts_starts_no_empty_part(caller):
    repo, env = caller
    configure(repo, "standard: 1\ncheck:\n  shards: 4\n", ["tests/test_a.py"])
    said = planned(repo, env, "pull_request")
    assert json.loads(said["shards"]) == [1]
    assert json.loads(said["parts"]) == {"1": "tests/test_a.py"}


def test_the_lint_runs_make_lint_and_conform_at_the_pinned_tag(caller):
    repo, env = caller
    needs = {"plan": {"result": "success", "outputs": planned(repo, env, "pull_request")}}
    context = {"github": github("pull_request"), "needs": needs}
    assert evaluate(workflow()["jobs"]["lint"]["if"], context, repo)
    done = run_job("lint", repo, env, context)
    assert (repo.parent / "make.log").read_text() == "make lint HEAD^1\n"
    conformed = done["steps"]["repo-standard conform"]
    assert f"conform {TAG}{VERSION}, " in conformed["said"]
    assert conformed["outcome"] == "failure"
    assert done["result"] == "failure"


@pytest.mark.parametrize(
    "part, shards, made",
    [
        (
            "tests/test_a.py tests/test_c.py",
            2,
            "make test TESTS=tests/test_a.py tests/test_c.py SHARD=",
        ),
        ("all", 1, "make test TESTS= SHARD="),
        ("all", 3, "make test TESTS= SHARD=2/3"),
        ("none", 2, None),
    ],
)
def test_each_part_runs_what_the_plan_dealt_it(caller, part, shards, made):
    repo, env = caller
    outputs = {
        "mode": "standard",
        "run": "true",
        "shards": json.dumps(list(range(1, shards + 1))),
        "parts": json.dumps({str(at): part for at in range(1, shards + 1)}),
    }
    context = {
        "github": github("pull_request"),
        "needs": {"plan": {"result": "success", "outputs": outputs}},
        "matrix": {"shard": min(2, shards)},
        "strategy": {"job-total": shards},
    }
    job = workflow()["jobs"]["test"]
    assert evaluate(job["if"], context, repo)
    matrix = EXPRESSION.fullmatch(job["strategy"]["matrix"]["shard"])[1]
    assert evaluate(matrix, context, repo) == list(range(1, shards + 1))
    assert run_job("test", repo, env, context)["result"] == "success"
    log = repo.parent / "make.log"
    assert (log.read_text().strip() if log.exists() else None) == made


@pytest.mark.parametrize("skip", [{"reused": "true"}, {"marker": "green"}, {"run": "false"}])
def test_a_reuse_a_green_tree_or_a_nightly_left_off_runs_no_test(caller, skip):
    repo, _ = caller
    outputs = {"mode": "standard", "run": "true", "reused": "false", "marker": "", **skip}
    context = {"github": github("push"), "needs": {"plan": {"outputs": outputs}}}
    assert not evaluate(workflow()["jobs"]["test"]["if"], context, repo)


def gathered(repo, env, event, plan, **results):
    needs = {"plan": {"result": "success", "outputs": plan}}
    for job in ("lint", "test", "browser", "command"):
        needs[job] = {"result": results.get(job, "skipped")}
    return run_job("passed", repo, env, {"github": github(event), "needs": needs})


PULL = {
    "mode": "standard",
    "run": "true",
    "reused": "false",
    "checked": "green-checked-a-b",
    "tree": "green-tree-t",
    "selection": "some",
}


@pytest.mark.parametrize(
    "event, plan, results, result, uploaded",
    [
        (
            "pull_request",
            PULL,
            {"lint": "success", "test": "success"},
            "success",
            ["green-checked-a-b"],
        ),
        (
            "pull_request",
            {**PULL, "selection": "all"},
            {"lint": "success", "test": "success"},
            "success",
            ["green-checked-a-b", "green-tree-t"],
        ),
        ("pull_request", PULL, {"lint": "success", "test": "failure"}, "failure", []),
        ("pull_request", PULL, {"lint": "failure", "test": "success"}, "failure", []),
        ("pull_request", PULL, {"lint": "success", "test": "cancelled"}, "failure", []),
        ("pull_request", {**PULL, "reused": "true"}, {"lint": "success"}, "success", []),
        (
            "push",
            {**PULL, "checked": ""},
            {"lint": "success", "test": "success"},
            "success",
            ["green-tree-t"],
        ),
        ("push", {**PULL, "marker": "green"}, {"lint": "success"}, "success", ["green-tree-t"]),
        ("schedule", {**PULL, "run": "false"}, {}, "success", []),
        ("pull_request", {**PULL, "run": ""}, {}, "failure", []),
        ("push", {**PULL, "run": "false"}, {}, "failure", []),
        ("pull_request", {"mode": "command"}, {"command": "success"}, "success", []),
        ("pull_request", {"mode": "command"}, {"command": "failure"}, "failure", []),
        (
            "pull_request",
            PULL,
            {"lint": "success", "test": "success", "browser": "failure"},
            "failure",
            [],
        ),
        (
            "pull_request",
            PULL,
            {"lint": "success", "test": "success", "browser": "cancelled"},
            "failure",
            [],
        ),
        (
            "pull_request",
            PULL,
            {"lint": "success", "test": "success", "browser": "success"},
            "success",
            ["green-checked-a-b"],
        ),
    ],
)
def test_passed_gathers_every_job_and_leaves_the_markers(
    caller, event, plan, results, result, uploaded
):
    repo, env = caller
    done = gathered(repo, env, event, plan, **results)
    assert (done["result"], done["uploaded"]) == (result, uploaded)


def test_every_job_runs_on_the_callers_runner_and_takes_the_pinned_actions():
    top = workflow()
    assert set(top["on"]) == {"workflow_call"}
    assert set(top["on"]["workflow_call"]["inputs"]) == {
        "runner",
        "command",
        "timeout-minutes",
        "browser-channel",
    }
    assert top["permissions"] == {"contents": "read", "actions": "read"}
    assert top["env"]["REPO_STANDARD_UPSTREAM"] == UPSTREAM
    assert top["env"]["REPO_STANDARD_VERSION"] == VERSION
    assert top["defaults"] == {"run": {"shell": "bash"}}
    assert set(top["jobs"]) == {"plan", "lint", "test", "browser", "command", "passed"}
    for job in top["jobs"].values():
        assert job["runs-on"] == "${{ inputs.runner }}"
        cap = job["timeout-minutes"]
        assert isinstance(cap, int) or cap == "${{ inputs.timeout-minutes }}"
    assert top["jobs"]["passed"]["needs"] == ["plan", "lint", "test", "browser", "command"]
    pinned = re.compile(r"^\s*- uses: (actions/[\w-]+@\S+)", re.M)
    ours = set(pinned.findall((REPO / ".github/workflows/check.yml").read_text()))
    assert set(pinned.findall(WORKFLOW.read_text())) <= ours


def test_the_template_is_a_caller_of_the_shared_workflow_at_the_pinned_tag(caller):
    repo, env = caller
    top = template("npm test")
    assert set(top["on"]) == {"pull_request", "push", "schedule", "workflow_dispatch"}
    assert top["on"]["push"] == {"branches": ["main"]}
    assert top["permissions"] == {"contents": "read", "actions": "read"}
    standard = top["jobs"]["standard"]
    assert standard["uses"] == CALLED
    assert standard["with"] == {"runner": "ubuntu-24.04", "command": "npm test"}
    check = top["jobs"]["check"]
    assert (check["needs"], check["if"]) == ("standard", "always()")
    assert "name" not in check and "strategy" not in check
    for result, ends in (("success", "success"), ("failure", "failure"), ("skipped", "failure")):
        context = {"needs": {"standard": {"result": result}}}
        assert run_job("check", repo, env, context, top)["result"] == ends


def plan_of(root, capsys, *args):
    """What `repo-standard plan` prints for the repo at `root`, and its exit code."""
    code = main(["plan", "--root", str(root), *args])
    printed = capsys.readouterr()
    return code, dict(line.split("=", 1) for line in printed.out.splitlines()), printed.err


def test_the_plan_verb_reads_the_event_and_the_selection_it_is_given(caller, capsys, monkeypatch):
    repo, _ = caller
    configure(repo, "standard: 1\ncheck:\n  shards: 2\n  nightly: true\n")
    selection = repo.parent / "selection.txt"
    selection.write_text("tests/test_a.py\n\ntests/test_b.py\ntests/test_a.py\n")
    code, said, _ = plan_of(repo, capsys, "--event", "pull_request", "--selection", str(selection))
    assert code == 0
    assert said["parts"] == json.dumps({"1": "tests/test_a.py", "2": "tests/test_b.py"})
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    code, said, _ = plan_of(repo, capsys)
    assert (code, said["run"], said["selection"]) == (0, "true", ALL)
    selection.write_text("")
    code, said, _ = plan_of(repo, capsys, "--selection", str(selection))
    assert (said["selection"], said["parts"]) == (NONE, json.dumps({"1": NONE, "2": NONE}))


@pytest.mark.parametrize(
    "check, said",
    [
        ("  shards: 0\n", "check.shards is not a number of parts from 1 to 64"),
        ("  shards: true\n", "check.shards is not a number of parts from 1 to 64"),
        ("  shards: 65\n", "check.shards is not a number of parts from 1 to 64"),
        ("  nightly: yes\n", "check.nightly is not true or false"),
        ("  parts: 2\n", "check has parts, which the standard does not know"),
    ],
)
def test_a_check_part_the_plan_cannot_follow_exits_2_and_says_why(caller, capsys, check, said):
    repo, _ = caller
    configure(repo, f"standard: 1\ncheck:\n{check}")
    code, _, err = plan_of(repo, capsys, "--event", "push")
    assert code == 2
    assert said in err


@pytest.mark.parametrize(
    "selection, said",
    [
        (None, "cannot read"),
        ("tests/test_a.py::test_one[a b]\n", "make select printed an id with a space"),
    ],
)
def test_a_selection_the_plan_cannot_read_exits_2_and_says_why(caller, capsys, selection, said):
    repo, _ = caller
    path = repo.parent / "selection.txt"
    if selection is not None:
        path.write_text(selection)
    code, _, err = plan_of(repo, capsys, "--event", "pull_request", "--selection", str(path))
    assert code == 2
    assert said in err


E2E_CONFIG = (
    "standard: 1\ncheck:\n  shards: 2\nstacks:\n  web:\n    adapter: node-vite\n"
    "    roots: [web]\n    e2e:\n      root: web\n      script: test:e2e\n"
)
E2E_LOCK = json.dumps(
    {"packages": {"node_modules/@playwright/test": {"version": "1.64.1"}}}, indent=2
)
BROWSER_IDS = ["web/e2e/pets.spec.ts", "web/e2e/screens.spec.ts > screen: help"]


def browser_caller(repo, selection):
    commit(
        repo,
        {
            ".repo-standard.yml": E2E_CONFIG,
            "Makefile": makefile(selection),
            "web/package-lock.json": E2E_LOCK,
        },
        "a node stack with browser tests",
    )


def test_a_pull_requests_plan_routes_its_browser_ids_to_the_browser_job(caller):
    repo, env = caller
    browser_caller(repo, ["web/src/a.test.ts", *BROWSER_IDS, "web/src/b.test.ts"])
    said = planned(repo, env, "pull_request")
    assert json.loads(said["parts"]) == {"1": "web/src/a.test.ts", "2": "web/src/b.test.ts"}
    assert (said["browser"], json.loads(said["browser-ids"])) == ("some", BROWSER_IDS)
    assert said["playwright"] == "1.64.1"


@pytest.mark.parametrize(
    "selection, parts, browser, ids",
    [
        (["web/e2e/pets.spec.ts"], {"1": NONE, "2": NONE}, "some", ["web/e2e/pets.spec.ts"]),
        (["web/src/a.test.ts"], {"1": "web/src/a.test.ts"}, NONE, []),
        (["stack:web"], {"1": "stack:web"}, "some", ["stack:web"]),
        (["all"], {"1": ALL, "2": ALL}, ALL, []),
    ],
)
def test_the_plan_runs_the_browser_job_only_where_it_routed_it_an_id(
    caller, capsys, selection, parts, browser, ids
):
    repo, _ = caller
    browser_caller(repo, selection)
    path = repo.parent / "selection.txt"
    path.write_text("".join(f"{one}\n" for one in selection))
    code, said, _ = plan_of(repo, capsys, "--event", "pull_request", "--selection", str(path))
    assert code == 0
    assert json.loads(said["parts"]) == parts
    assert (said["browser"], json.loads(said["browser-ids"])) == (browser, ids)
    outputs = {"mode": "standard", "reused": "false", "marker": "", **said}
    needs = {"plan": {"result": "success", "outputs": outputs}}
    context = {"github": github("pull_request"), "needs": needs}
    assert evaluate(workflow()["jobs"]["browser"]["if"], context, repo) == (browser != NONE)


def test_main_and_nightly_run_every_browser_test_and_a_repo_with_none_skips_the_job(caller):
    repo, env = caller
    browser_caller(repo, [])
    configure(repo, E2E_CONFIG.replace("  shards: 2\n", "  shards: 2\n  nightly: true\n"))
    for event in ("push", "schedule"):
        said = planned(repo, env, event)
        assert said["browser"] == ALL
    configure(repo, "standard: 1\n")
    assert planned(repo, env, "push")["browser"] == NONE


def test_an_e2e_root_that_pins_no_playwright_fails_the_plan(caller):
    repo, env = caller
    browser_caller(repo, BROWSER_IDS)
    commit(repo, {"web/package-lock.json": "{}"}, "no Playwright")
    done = run_job("plan", repo, {**env, "GITHUB_EVENT_NAME": "push"}, {"github": github("push")})
    assert done["result"] == "failure"
    assert "web/package-lock.json pins no @playwright/test" in done["steps"]["plan"]["said"]


@pytest.mark.parametrize("lock", [None, "{}", "not json"])
def test_the_plan_refuses_an_e2e_root_whose_lockfile_pins_no_playwright(caller, capsys, lock):
    repo, _ = caller
    browser_caller(repo, BROWSER_IDS)
    if lock is None:
        git(repo, "rm", "-q", "web/package-lock.json")
        commit(repo, {}, "no lockfile")
    else:
        commit(repo, {"web/package-lock.json": lock}, "a lockfile with no Playwright")
    code, _, err = plan_of(repo, capsys, "--event", "push")
    assert code == 2
    assert "stack web: web/package-lock.json pins no @playwright/test" in err


def test_two_e2e_roots_that_pin_two_playwrights_fail_the_plan(caller, capsys):
    repo, _ = caller
    second = E2E_CONFIG.replace("web", "app").split("stacks:\n")[1]
    commit(
        repo,
        {
            ".repo-standard.yml": E2E_CONFIG + second,
            "web/package-lock.json": E2E_LOCK,
            "app/package-lock.json": E2E_LOCK.replace("1.64.1", "1.63.0"),
        },
        "two e2e roots",
    )
    code, _, err = plan_of(repo, capsys, "--event", "push")
    assert code == 2
    assert "pin Playwright at more than one version: web 1.64.1, app 1.63.0" in err


def browser_job(repo, env, said, channel=""):
    needs = {"plan": {"result": "success", "outputs": said}}
    inputs = {"runner": "ubuntu-24.04", "browser-channel": channel}
    context = {"github": github("pull_request"), "needs": needs, "inputs": inputs}
    image = substitute(workflow()["jobs"]["browser"]["container"], context, repo)
    return image, run_job("browser", repo, env, context)


def test_the_browser_job_runs_the_routed_ids_in_the_pinned_playwright_image(caller):
    repo, env = caller
    browser_caller(repo, ["web/src/a.test.ts", *BROWSER_IDS])
    image, done = browser_job(repo, env, planned(repo, env, "pull_request"))
    assert image == "mcr.microsoft.com/playwright:v1.64.1-noble"
    assert done["result"] == "success"
    assert done["steps"]["browser version"]["outcome"] == "skipped"
    logged = (repo.parent / "make.log").read_text().splitlines()
    assert logged == ["make e2e E2E_LIST=given", *BROWSER_IDS]
    assert done["uploaded"] == ["playwright-report", "test-results"]


def test_on_main_the_browser_job_runs_every_test_with_no_list(caller):
    repo, env = caller
    browser_caller(repo, [])
    _, done = browser_job(repo, env, planned(repo, env, "push"))
    assert done["result"] == "success"
    assert (repo.parent / "make.log").read_text() == "make e2e E2E_LIST=\n"


def test_channel_mode_runs_on_the_runner_and_prints_the_browsers_version(caller, tmp_path):
    repo, env = caller
    browser_caller(repo, BROWSER_IDS)
    chrome = tmp_path / "bin" / "google-chrome"
    chrome.write_text("#!/bin/sh\necho 'Google Chrome 142.0.7444.59'\n")
    chrome.chmod(0o755)
    image, done = browser_job(repo, env, planned(repo, env, "pull_request"), channel="chrome")
    assert image == ""
    assert done["result"] == "success"
    assert done["steps"]["tools"]["outcome"] == "skipped"
    assert "Google Chrome 142.0.7444.59" in done["steps"]["browser version"]["said"]
    said = planned(repo, env, "pull_request")
    _, done = browser_job(repo, env, said, channel="chrome-nowhere")
    assert done["result"] == "failure"
    assert "the runner has no google-chrome-nowhere" in done["steps"]["browser version"]["said"]
