"""The ledger of the tests main failed, run through the shared check's own jobs.

Each case runs the workflow's `plan`, `test` and `passed` jobs with `run_job`, from
test_check_workflow, on its fixture caller, whose `make select` prints what the case sets and whose
`make test` runs `FAKE_TEST`: it fails each id of `$FAILS` it runs, and each id of `$FLAKY` the
first time only, and writes the ids that failed to `$REPO_STANDARD_FAILED`, as an adapter does.
The jobs' uploads go to a store, and `gh` on the path is a stub that serves GitHub's answers from
it: the artifacts by name, each one's zip, and the runs of main that the case lists, so a later
job finds what an earlier one left, as it would on GitHub.
"""

import json
import subprocess
import sys

import pytest

from repo_standard.config import Refused
from repo_standard.misses import FILE, Row
from test_check_workflow import caller, commit, git, makefile, run_job

caller = caller
SUITE = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]
FAKE_TEST = """import os, sys
from pathlib import Path

ran = sys.argv[1:] or SUITE
seen = Path(os.environ["FLAKY_SEEN"])
seen.mkdir(exist_ok=True)
failed = [one for one in ran if one in os.environ.get("FAILS", "").split()]
for one in ran:
    if one in os.environ.get("FLAKY", "").split():
        mark = seen / one.replace("/", "_")
        if not mark.exists():
            failed.append(one)
            mark.touch()
with open(os.environ["REPO_STANDARD_FAILED"], "a") as out:
    out.write("".join(one + "\\n" for one in failed))
print("ran", *ran, "failed", *failed)
sys.exit(1 if failed else 0)
""".replace("SUITE", repr(SUITE))
GH = """import io, json, os, re, sys, zipfile
from pathlib import Path

store, path = Path(os.environ["STORE"]), sys.argv[2]
names = sorted(one.name for one in store.iterdir()) if store.is_dir() else []
route = path.split("?")[0]
query = dict(re.findall(r"([a-z_]+)=([^&]*)", path))
if route == "repos/someone/repo":
    print(json.dumps({"default_branch": "main"}))
elif route.endswith("/runs") and "/workflows/" in route:
    runs = Path(os.environ["RUNS"])
    listed = json.loads(runs.read_text()) if runs.exists() and query.get("page") == "1" else []
    print(json.dumps({"workflow_runs": listed}))
elif route.endswith("/artifacts") and "name" in query:
    name = query["name"]
    found = [{"id": names.index(name), "name": name, "expired": False}] if name in names else []
    print(json.dumps({"artifacts": found}))
elif m := re.fullmatch(r"repos/someone/repo/actions/artifacts/(\\d+)/zip", route):
    folder, out = store / names[int(m[1])], io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for one in folder.iterdir():
            archive.write(one, one.name)
    sys.stdout.buffer.write(out.getvalue())
else:
    print("gh: no answer here for " + path, file=sys.stderr)
    sys.exit(1)
"""


@pytest.fixture
def loop(caller, tmp_path):
    """The caller, with the suite's files and the fake test, its env, and the store."""
    repo, env = caller
    (tmp_path / "fake_test.py").write_text(FAKE_TEST)
    gh = tmp_path / "bin" / "gh"
    gh.write_text(f"#!{sys.executable}\n{GH}")
    store = {}
    env = {
        **env,
        "FAKE_TEST": str(tmp_path / "fake_test.py"),
        "FLAKY_SEEN": str(tmp_path / "flaky-seen"),
        "STORE": str(tmp_path / "store"),
        "RUNS": str(tmp_path / "runs.json"),
    }
    merge(repo, "the suite", ["tests/test_a.py"], dict.fromkeys(SUITE, ""))
    return repo, env, store


def merge(repo, subject, selection, files=None):
    """A commit on main whose `make select` prints the selection."""
    text = makefile(selection).replace(
        "test:\n\t@echo", 'test:\n\t@python3 "$(FAKE_TEST)" $(TESTS)\n\t@echo'
    )
    commit(repo, {"Makefile": text, **(files or {})}, subject)


def head(repo, ref="HEAD"):
    done = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref], capture_output=True, text=True
    )
    return done.stdout.strip()


def github(event, run=1):
    repository = {"default_branch": "main"}
    ref = "main" if event == "push" else "7/merge"
    return {
        "event_name": event,
        "token": "a-token",
        "ref_name": ref,
        "run_id": str(run),
        "event": {"repository": repository},
    }


def check(repo, env, store, event, run=1, **outcomes):
    """The run of the check: plan, the one part of the tests, and passed. Lint passes."""
    env = {**env, "GITHUB_EVENT_NAME": event, **outcomes}
    context = {"github": github(event, run), "inputs": {"runner": "ubuntu-24.04", "command": ""}}
    plan = run_job("plan", repo, env, context, store=store)
    assert plan["result"] == "success", plan["steps"]
    needs = {"plan": {"result": "success", "outputs": plan["outputs"]}}
    part = {**context, "needs": needs, "matrix": {"shard": 1}, "strategy": {"job-total": 1}}
    tests = run_job("test", repo, env, part, store=store)
    needs |= {
        "lint": {"result": "success"},
        "test": {"result": tests["result"]},
        "browser": {"result": "skipped"},
        "command": {"result": "skipped"},
    }
    passed = run_job("passed", repo, env, {**context, "needs": needs}, store=store)
    return plan, tests, passed


def selected(plan):
    return " ".join(json.loads(plan["outputs"]["parts"]).values()).split()


def ledger(store, run):
    text = (store[f"miss-ledger-{run}"] / FILE).read_text()
    return [Row.read(line) for line in text.splitlines()]


def ran_on_main(env, *runs):
    """Main's runs, as GitHub lists them to the lookup."""
    listed = [
        {"id": run, "event": "push", "conclusion": conclusion, "head_sha": f"{run:040d}"}
        for run, conclusion in runs
    ]
    with open(env["RUNS"], "w") as out:
        json.dump(listed, out)


def test_a_test_the_selection_skipped_fails_on_main_and_joins_the_next_selection(loop):
    repo, env, store = loop
    merge(repo, "a change to a (#7)", ["tests/test_a.py"])
    plan, tests, passed = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py"]
    assert passed["result"] == "success"

    plan, tests, passed = check(repo, env, store, "push", run=101, FAILS="tests/test_b.py")
    assert tests["result"] == "failure"
    assert "- tests/test_b.py" in tests["summary"]
    assert "failed: tests/test_b.py" in passed["steps"]["every job passed"]["said"]
    assert ledger(store, 101) == [Row("tests/test_b.py", "#7", False, "miss", head(repo))]
    assert "| `tests/test_b.py` | #7 | no | miss |" in passed["summary"]

    ran_on_main(env, (101, "failure"))
    merge(repo, "another change to a (#8)", ["tests/test_a.py"])
    plan, _, _ = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py", "tests/test_b.py"]

    ran_on_main(env, (101, "failure"), (102, "success"))
    plan, _, _ = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py"]


def test_a_test_that_passes_when_run_again_is_flaky_and_joins_no_selection(loop):
    repo, env, store = loop
    merge(repo, "a change to a (#7)", ["tests/test_a.py"])
    outcomes = {"FAILS": "tests/test_b.py", "FLAKY": "tests/test_c.py"}
    _, tests, passed = check(repo, env, store, "push", run=101, **outcomes)
    assert tests["steps"]["again"]["outcome"] == "success"
    assert {row.id: row.kind for row in ledger(store, 101)} == {
        "tests/test_b.py": "miss",
        "tests/test_c.py": "flaky",
    }
    said = passed["steps"]["every job passed"]["said"]
    assert "failed: tests/test_b.py tests/test_c.py" in said

    ran_on_main(env, (101, "failure"))
    merge(repo, "another change to a (#8)", ["tests/test_a.py"])
    plan, _, _ = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py", "tests/test_b.py"]


@pytest.mark.parametrize("moved, kind", [(False, "env"), (True, "race")])
def test_a_selected_test_main_fails_is_a_race_where_the_base_moved_after_the_check(
    loop, moved, kind
):
    repo, env, store = loop
    merge(repo, "a change to b (#7)", ["tests/test_b.py"])
    plan, _, passed = check(repo, env, store, "pull_request")
    assert passed["uploaded"] == [plan["outputs"]["checked"]]
    if moved:
        git(repo, "reset", "-q", "--hard", "HEAD^1")
        commit(repo, {"other.txt": "landed first\n"}, "another pull request (#6)")
        merge(repo, "a change to b (#7)", ["tests/test_b.py"])

    check(repo, env, store, "push", run=101, FAILS="tests/test_b.py")
    assert ledger(store, 101) == [Row("tests/test_b.py", "#7", True, kind, head(repo))]


def test_a_lookup_that_fails_warns_and_adds_nothing(loop):
    repo, env, store = loop
    with open(env["RUNS"], "w") as out:
        out.write("not json")
    plan, _, _ = check(repo, env, store, "pull_request")
    assert plan["steps"]["failed on main"]["outcome"] == "success"
    assert (
        "::warning::misses: could not read main's ledgers"
        in plan["steps"]["failed on main"]["said"]
    )
    assert selected(plan) == ["tests/test_a.py"]


def test_a_ledger_row_of_an_unknown_class_is_refused():
    line = json.dumps({"id": "a", "pr": "", "selected": True, "kind": "lost", "commit": "c"})
    with pytest.raises(Refused):
        Row.read(line)
