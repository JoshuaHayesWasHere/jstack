"""The ledger of the tests main failed, run through the shared check's own jobs.

Each case runs the workflow's `plan`, `test` and `passed` jobs with `run_job`, from
test_check_workflow, on its fixture caller, whose `make select` prints what the case sets and whose
`make test` runs `FAKE_TEST`: it fails each id of `$FAILS` it runs, and each id of `$FLAKY` the
first time only, and writes the ids that failed to `$REPO_STANDARD_FAILED`, as an adapter does.
The jobs' uploads go to a store, and `gh` on the path is a stub that serves GitHub's answers from
it: the artifacts by name, each one's zip, and the runs of main that the case lists, so a later
job finds what an earlier one left, as it would on GitHub.

The jobs run the tool from the copy the workflow clones, so the cases after them run the verb
`misses` in this process, from the caller's checkout with the same stub, as a job runs it: those
are the runs of this checkout's own `repo_standard.misses`.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from repo_standard import VERSION, cli
from repo_standard.config import Refused
from repo_standard.misses import FILE, Row
from test_check_workflow import caller, commit, git, makefile, run_job

caller = caller
SUITE = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]
BROWSER = "web/e2e/pets.spec.ts > pets > shows a pet"
FAKE_TEST = """import os, sys
from pathlib import Path

if sys.argv[1:2] == ["--e2e"]:
    listed = sys.argv[2:]
    ran = Path(listed[0]).read_text().splitlines() if listed else [BROWSER]
    fails = os.environ.get("E2E_FAILS", "").split("|")
else:
    ran = sys.argv[1:] or SUITE
    fails = os.environ.get("FAILS", "").split()
seen = Path(os.environ["FLAKY_SEEN"])
seen.mkdir(exist_ok=True)
failed = [one for one in ran if one in fails]
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
""".replace("SUITE", repr(SUITE)).replace("BROWSER", repr(BROWSER))
GH = """import io, json, os, re, sys, zipfile
from pathlib import Path

if sys.argv[1] == "repo":
    print(os.environ.get("REPO_VIEW", ""))
    sys.exit(0 if os.environ.get("REPO_VIEW") else 1)
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
    expired = name in os.environ.get("EXPIRED", "").split()
    found = [{"id": names.index(name), "name": name, "expired": expired}] if name in names else []
    print(json.dumps({"artifacts": found}))
elif route.endswith("/pulls") and os.environ.get("PULLS"):
    print(os.environ["PULLS"])
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
    text = text.replace(
        "e2e:\n\t@echo", 'e2e:\n\t@python3 "$(FAKE_TEST)" --e2e $(E2E_LIST)\n\t@echo'
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
    inputs = {"runner": "ubuntu-24.04", "command": "", "browser-channel": ""}
    context = {"github": github(event, run), "inputs": inputs}
    plan = run_job("plan", repo, env, context, store=store)
    assert plan["result"] == "success", plan["steps"]
    needs = {"plan": {"result": "success", "outputs": plan["outputs"]}}
    part = {**context, "needs": needs, "matrix": {"shard": 1}, "strategy": {"job-total": 1}}
    tests = run_job("test", repo, env, part, store=store)
    browser = {"result": "skipped"}
    if plan["outputs"]["browser"] != "none":
        browser = run_job("browser", repo, env, {**context, "needs": needs}, store=store)
    needs |= {
        "lint": {"result": "success"},
        "test": {"result": tests["result"]},
        "browser": {"result": browser["result"]},
        "command": {"result": "skipped"},
    }
    passed = run_job("passed", repo, env, {**context, "needs": needs}, store=store)
    return plan, tests, passed, browser


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
    plan, tests, passed, _ = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py"]
    assert passed["result"] == "success"

    plan, tests, passed, _ = check(repo, env, store, "push", run=101, FAILS="tests/test_b.py")
    assert tests["result"] == "failure"
    assert "- tests/test_b.py" in tests["summary"]
    assert "failed: tests/test_b.py" in passed["steps"]["every job passed"]["said"]
    assert ledger(store, 101) == [Row("tests/test_b.py", "#7", False, "miss", head(repo))]
    assert "| `tests/test_b.py` | #7 | no | miss |" in passed["summary"]

    ran_on_main(env, (101, "failure"))
    merge(repo, "another change to a (#8)", ["tests/test_a.py"])
    plan, _, _, _ = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py", "tests/test_b.py"]

    ran_on_main(env, (101, "failure"), (102, "success"))
    plan, _, _, _ = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py"]


E2E = {
    ".repo-standard.yml": f"standard: {VERSION}\n"
    "stacks:\n  web:\n    adapter: node-vite\n    roots: [web]\n"
    "    e2e:\n      root: web\n      script: test:e2e\n",
    "web/package-lock.json": json.dumps(
        {"packages": {"node_modules/@playwright/test": {"version": "1.64.1"}}}
    ),
    "web/e2e/pets.spec.ts": "",
}


def test_a_browser_test_the_selection_skipped_fails_on_main_and_joins_the_next_browser_run(loop):
    repo, env, store = loop
    merge(repo, "a change to the pets page (#9)", ["tests/test_a.py"], E2E)
    plan, _, passed, browser = check(repo, env, store, "pull_request")
    assert (plan["outputs"]["browser"], browser["result"]) == ("none", "skipped")
    assert passed["result"] == "success"

    _, tests, passed, browser = check(repo, env, store, "push", run=101, E2E_FAILS=BROWSER)
    assert (tests["result"], browser["result"]) == ("success", "failure")
    assert browser["steps"]["again"]["outcome"] == "success"
    assert f"- {BROWSER}" in browser["summary"]
    said = passed["steps"]["every job passed"]["said"]
    assert f"the browser tests ended failure, and failed: {BROWSER}" in said
    assert ledger(store, 101) == [Row(BROWSER, "#9", False, "miss", head(repo))]

    ran_on_main(env, (101, "failure"))
    merge(repo, "another change to a (#10)", ["tests/test_a.py"])
    plan, _, _, browser = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py"]
    assert json.loads(plan["outputs"]["browser-ids"]) == [BROWSER]
    assert browser["result"] == "success"


def test_a_test_that_passes_when_run_again_is_flaky_and_joins_no_selection(loop):
    repo, env, store = loop
    merge(repo, "a change to a (#7)", ["tests/test_a.py"])
    outcomes = {"FAILS": "tests/test_b.py", "FLAKY": "tests/test_c.py"}
    _, tests, passed, _ = check(repo, env, store, "push", run=101, **outcomes)
    assert tests["steps"]["again"]["outcome"] == "success"
    assert {row.id: row.kind for row in ledger(store, 101)} == {
        "tests/test_b.py": "miss",
        "tests/test_c.py": "flaky",
    }
    said = passed["steps"]["every job passed"]["said"]
    assert "failed: tests/test_b.py tests/test_c.py" in said

    ran_on_main(env, (101, "failure"))
    merge(repo, "another change to a (#8)", ["tests/test_a.py"])
    plan, _, _, _ = check(repo, env, store, "pull_request")
    assert selected(plan) == ["tests/test_a.py", "tests/test_b.py"]


@pytest.mark.parametrize("moved, kind", [(False, "env"), (True, "race")])
def test_a_selected_test_main_fails_is_a_race_where_the_base_moved_after_the_check(
    loop, moved, kind
):
    repo, env, store = loop
    merge(repo, "a change to b (#7)", ["tests/test_b.py"])
    plan, _, passed, _ = check(repo, env, store, "pull_request")
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
    plan, _, _, _ = check(repo, env, store, "pull_request")
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


@pytest.fixture
def here(loop, monkeypatch):
    """The caller as the verb `misses` sees it when a job runs it: its checkout as the working
    directory, and the stub `gh` on the path. The verb runs here in this process."""
    repo, env, store = loop
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_WORKFLOW_REF", raising=False)
    monkeypatch.chdir(repo)
    return repo, env


def misses(capsys, *argv):
    code = cli.main(["misses", *argv])
    out, err = capsys.readouterr()
    return code, out, err


def kept(env, run, *rows):
    """A ledger main's run `run` left, where the stub serves it."""
    folder = Path(env["STORE"]) / f"miss-ledger-{run}"
    folder.mkdir(parents=True)
    (folder / FILE).write_text("".join(f"{row.line()}\n" for row in rows))


def test_record_writes_a_row_for_each_failed_id_with_its_class_and_pull_request(
    here, capsys, monkeypatch, tmp_path
):
    repo, env = here
    merge(repo, "a change to a (#7)", ["tests/test_a.py"])
    failed = tmp_path / "failed" / "failed-1-1"
    failed.mkdir(parents=True)
    (failed / "failed.txt").write_text("tests/test_a.py\ntests/test_b.py\ntests/test_c.py\n")
    (failed / "again.txt").write_text("tests/test_a.py\ntests/test_b.py\n")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("PULLS", json.dumps([{"number": 12, "merged_at": "2026-11-09T00:00:00Z"}]))

    out_dir = tmp_path / "ledger"
    code, out, _ = misses(
        capsys, "record", "--failed", str(tmp_path / "failed"), "--out", str(out_dir)
    )

    commit_ = head(repo)
    assert code == 0
    assert [Row.read(line) for line in (out_dir / FILE).read_text().splitlines()] == [
        Row("tests/test_a.py", "#12", True, "race", commit_),
        Row("tests/test_b.py", "#12", False, "miss", commit_),
        Row("tests/test_c.py", "#12", False, "flaky", commit_),
    ]
    assert "| `tests/test_b.py` | #12 | no | miss |" in out
    assert summary.read_text() == f"### The tests main failed\n\n{out}\n"


def test_record_with_no_selection_and_no_marker_to_read_calls_no_row_a_miss_or_a_race(
    here, capsys, monkeypatch, tmp_path
):
    repo, env = here
    commit(repo, {"Makefile": "select:\n\t@exit 3\n"}, "a change to b (#7)")
    monkeypatch.setenv("PATH", f"{tmp_path / 'nogh'}:{env['PATH']}")
    (tmp_path / "nogh").mkdir()
    (tmp_path / "nogh" / "gh").write_text("#!/bin/sh\nexit 1\n")
    (tmp_path / "nogh" / "gh").chmod(0o755)
    failed = tmp_path / "failed"
    failed.mkdir()
    (failed / "failed.txt").write_text("tests/test_b.py\n")

    code, out, err = misses(capsys, "record", "--failed", str(failed), "--out", str(tmp_path / "o"))

    assert code == 0
    assert "| `tests/test_b.py` | #7 | yes | env |" in out
    assert "::warning::misses: make select BASE=HEAD^1 failed" in err
    assert "::warning::misses: could not ask for the checked-tree marker" in err


def test_record_needs_both_folders(here, capsys):
    with pytest.raises(SystemExit) as stopped:
        misses(capsys, "record", "--failed", "somewhere")
    assert stopped.value.code == 2
    assert "record needs --failed and --out" in capsys.readouterr().err


def test_failing_prints_each_red_id_no_later_green_run_passed_that_is_still_here_in_a_kept_ledger(
    here, capsys, monkeypatch
):
    _, env = here
    monkeypatch.setenv(
        "GITHUB_WORKFLOW_REF", "someone/repo/.github/workflows/check.yml@refs/heads/main"
    )
    kept(env, 101, Row("tests/test_a.py", "#6", False, "miss", "a" * 40))
    kept(
        env,
        103,
        Row("tests/test_b.py", "#7", False, "miss", "c" * 40),
        Row("tests/gone.py", "#7", False, "miss", "c" * 40),
        Row("tests/test_c.py", "#7", False, "flaky", "c" * 40),
    )
    kept(env, 104, Row("tests/test_c.py", "#8", False, "miss", "d" * 40))
    monkeypatch.setenv("EXPIRED", "miss-ledger-104")
    ran_on_main(env, (101, "failure"), (102, "success"), (103, "failure"), (104, "failure"))

    code, out, err = misses(capsys, "failing")

    assert (code, out) == (0, "tests/test_b.py\n")
    assert "misses: 1 tests main failed join the selection" in err


def test_failing_that_cannot_read_the_ledgers_warns_and_prints_nothing(here, capsys):
    _, env = here
    Path(env["RUNS"]).write_text("not json")
    code, out, err = misses(capsys, "failing")
    assert (code, out) == (0, "")
    assert "::warning::misses: could not read main's ledgers" in err


def test_the_rate_counts_the_misses_per_merged_pull_request(here, capsys, monkeypatch):
    _, env = here
    monkeypatch.delenv("GITHUB_REPOSITORY")
    monkeypatch.setenv("REPO_VIEW", "someone/repo")
    kept(
        env,
        101,
        Row("tests/test_b.py", "#7", False, "miss", "b" * 40),
        Row("tests/test_c.py", "#7", False, "flaky", "b" * 40),
    )
    ran_on_main(env, (100, "success"), (101, "failure"))

    code, out, _ = misses(capsys, "--days", "7")

    assert code == 0
    assert out.splitlines() == [
        "miss rate: 1 misses in 2 merged pull requests (50.0%),"
        " from the runs of check.yml on main in the last 7 days",
        f"101\t{'b' * 12}\t#7\tmiss\tnot selected\ttests/test_b.py",
        f"101\t{'b' * 12}\t#7\tflaky\tnot selected\ttests/test_c.py",
    ]


def test_the_rate_with_no_repo_to_ask_fails(here, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY")
    code, _, err = misses(capsys, "--days", "7")
    assert code == 2
    assert "no GITHUB_REPOSITORY, and gh repo view names no repo" in err
