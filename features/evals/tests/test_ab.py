"""The A/B harness, driven through its command line: a stand-in `claude` on PATH answers, and a
throwaway git repository holds the two revisions."""

import hashlib
import json
import os
import subprocess
import sys

import pytest

from testing.paths import REPO

AB = REPO / "features" / "evals" / "ab" / "ab.py"
SKILL_CUT = REPO / "features" / "evals" / "evals" / "skill-cut"

READ_SET = ("features/evals/evals/skill-cut/",)

STAND_IN = r"""#!/usr/bin/env python3
import json, os, sys
here = os.environ["AB_STAND_IN"]
prompt = sys.stdin.read()
with open(os.path.join(here, "calls.log"), "a") as log:
    log.write(json.dumps(prompt) + "\n")
if os.environ.get("AB_STAND_IN_REFUSE"):
    sys.exit("the stand-in claude was called, and no model may be")
if "flaky" in prompt and not os.path.exists(os.path.join(here, "flaked")):
    open(os.path.join(here, "flaked"), "w").close()
    sys.exit("Not logged in")
answer = "PASS good" if "version one" in prompt else "PASS"
usage = {"input_tokens": 10, "output_tokens": 2}
print(json.dumps({"type": "result", "is_error": False, "result": answer, "total_cost_usd": 0.01,
                  "num_turns": 1, "duration_ms": 5, "usage": usage}))
"""

TASKS = {
    "families": {
        "steps": {"kind": "pass/fail"},
        "grade": {
            "kind": "graded",
            "score": [
                sys.executable,
                "-c",
                "import sys; print(0.75 if 'good' in sys.stdin.read() else 0.25)",
            ],
        },
    },
    "tasks": [
        {
            "id": f"s{i}",
            "family": "steps",
            "files": ["skill.md"],
            "prompt": f"Step {i}.",
            "must": ["PASS"],
        }
        for i in range(3)
    ]
    + [
        {"id": f"g{i}", "family": "grade", "files": ["skill.md"], "prompt": f"Grade {i}."}
        for i in range(3)
    ],
}


@pytest.fixture
def lab(tmp_path):
    """A repo whose `skill.md` reads "version one" at tag `one` and "version two" at tag `two`, a
    task file, and a stand-in `claude` first on PATH. The stand-in logs each call and answers from
    the file under test, so an answer tells which revision asked it; a prompt naming `flaky` fails
    the first time it is asked, and only then."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*a):
        subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    for version in ("one", "two"):
        (repo / "skill.md").write_text(f"The skill, version {version}.\n")
        git("add", "skill.md")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", version)
        git("tag", version)
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps(TASKS))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text(STAND_IN)
    (bin_dir / "claude").chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "AB_STAND_IN": str(tmp_path),
    }

    def ab(*args, refuse=False):
        return subprocess.run(
            [sys.executable, str(AB), *args],
            cwd=repo,
            env={**env, **({"AB_STAND_IN_REFUSE": "1"} if refuse else {})},
            capture_output=True,
            text=True,
        )

    def calls():
        log = tmp_path / "calls.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.is_file() else []

    return type(
        "Lab",
        (),
        {
            "ab": staticmethod(ab),
            "calls": staticmethod(calls),
            "tasks": tasks,
            "dir": tmp_path,
            "repo": repo,
        },
    )


def run(lab, out, *more):
    return lab.ab(
        "run", "--a", "one", "--b", "two", "--tasks", str(lab.tasks), "--out", str(out), *more
    )


def test_rescore_of_the_kept_skill_cut_runs_agrees_on_priming_and_catches_986(lab):
    """The two priming runs are the same revisions, and skill-cut's own rule split them; #986's
    cut is a known regression. No model is called: the stand-in fails if it is."""
    said = {}
    for name in ("run-crew-scout-priming", "run-crew-scout-priming-2", "run-interrogate-986"):
        ran = lab.ab("rescore", str(SKILL_CUT / name), refuse=True)
        assert ran.returncode == 0, ran.stderr
        said[name] = {line.split(":")[0]: line for line in ran.stdout.splitlines()}
    assert lab.calls() == []
    for name in ("run-crew-scout-priming", "run-crew-scout-priming-2"):
        assert said[name]["lead"].startswith("lead: no measurable difference; B - A -0.00")
    assert said["run-interrogate-986"]["lead"].startswith("lead: B worse; B - A -0.32")
    assert "17 tasks, 51 runs an arm" in said["run-interrogate-986"]["lead"]
    assert "errors not recorded; cost not recorded" in said["run-interrogate-986"]["lead"]


def test_a_rescore_writes_the_same_results_byte_for_byte_and_nothing_into_the_kept_run(lab):
    kept = SKILL_CUT / "run-crew-scout-priming"
    before = {p.name: p.read_bytes() for p in kept.iterdir()}
    for out in ("one.md", "two.md"):
        assert (
            lab.ab("rescore", str(kept), "--seed", "7", "--out", str(lab.dir / out)).returncode == 0
        )
    assert (lab.dir / "one.md").read_bytes() == (lab.dir / "two.md").read_bytes()
    assert {p.name: p.read_bytes() for p in kept.iterdir()} == before


def test_an_aa_that_differs_by_itself_is_inconclusive_not_a_winner(lab):
    """B is 0.1 above A on every task, which alone would be `B better`; but A-again is 0.2 below
    A, the same prompts at the same revision, so the run says nothing about B."""
    made = lab.dir / "run-aa"
    made.mkdir()
    key, scores = {}, {}
    for task in range(10):
        for arm, value in (("base", 0.8), ("base-again", 0.6), ("variant", 0.9)):
            for trial in (1, 2, 3):
                name = f"{task}-{arm}-{trial}"
                key[name] = {"case": f"lead/t{task}", "arm": arm, "trial": trial}
                scores[name] = {"value": value, "unsettled": []}
    (made / "key.json").write_text(json.dumps(key))
    (made / "scores.json").write_text(json.dumps(scores))
    ran = {"base": "a" * 40, "variant": "b" * 40, "model": "m", "effort": "medium", "trials": 3}
    (made / "run.json").write_text(json.dumps(ran))
    said = lab.ab("rescore", str(made), refuse=True)
    assert said.returncode == 0, said.stderr
    assert said.stdout.startswith("lead: inconclusive: A/A not clean; B - A +0.100")
    assert "A/A -0.200 [-0.200, -0.200]" in said.stdout


def test_a_prompt_run_names_arms_only_in_its_key_and_interleaves_them(lab):
    out = lab.dir / "out"
    ran = run(lab, out, "--workers", "1")
    assert ran.returncode == 0, ran.stderr
    asked = lab.calls()
    assert len(asked) == 6 * 3 * 3
    revision = ["one" if "version one" in p else "two" for p in asked]
    switches = sum(x != y for x, y in zip(revision, revision[1:], strict=False))
    assert switches > 10, revision
    key = json.loads((out / "key.json").read_text())
    assert sorted({k["arm"] for k in key.values()}) == ["A", "A-again", "B"]
    for path in out.iterdir():
        if path.name not in ("key.json", "results.md"):
            text = path.read_text()
            assert '"arm"' not in text and "A-again" not in text, path.name
    assert "steps: no measurable difference" in ran.stdout
    assert "grade: B worse; B - A -0.500 [-0.500, -0.500]" in ran.stdout
    assert "cost A $0.09 108 tokens, A-again $0.09 108 tokens, B $0.09 108 tokens" in ran.stdout


def test_the_same_seed_gives_the_same_order_and_results_and_run_json_says_what_ran(lab):
    for out in ("x", "y"):
        assert run(lab, lab.dir / out, "--seed", "11").returncode == 0
    for name in ("jobs.json", "key.json", "results.md"):
        assert (lab.dir / "x" / name).read_bytes() == (lab.dir / "y" / name).read_bytes(), name
    assert run(lab, lab.dir / "z", "--seed", "12").returncode == 0
    assert (lab.dir / "z" / "jobs.json").read_bytes() != (lab.dir / "x" / "jobs.json").read_bytes()
    said = json.loads((lab.dir / "x" / "run.json").read_text())

    def resolve(rev):
        ran = subprocess.run(
            ["git", "rev-parse", rev + "^{commit}"], cwd=lab.repo, capture_output=True, text=True
        )
        return ran.stdout.strip()

    assert said["seed"] == 11
    assert (said["a"]["sha"], said["b"]["sha"]) == (resolve("one"), resolve("two"))
    assert said["tasks"]["sha256"] == hashlib.sha256(lab.tasks.read_bytes()).hexdigest()
    assert (said["model"], said["effort"], said["trials"]) == ("claude-opus-5-5", "medium", 3)


def test_a_failed_call_is_asked_again_on_the_next_run_and_costs_only_itself(lab):
    flaky = json.loads(lab.tasks.read_text())
    flaky["tasks"][0]["prompt"] = "Step 0, flaky."
    lab.tasks.write_text(json.dumps(flaky))
    out = lab.dir / "out"
    first = run(lab, out)
    assert first.returncode == 1
    assert "1 calls failed" in first.stderr
    assert len(lab.calls()) == 54
    second = run(lab, out)
    assert second.returncode == 0, second.stderr
    assert len(lab.calls()) == 55
    steps = next(line for line in second.stdout.splitlines() if line.startswith("steps:"))
    errors = steps.split("; errors ")[1].split(";")[0]
    assert sorted(int(part.split()[-1]) for part in errors.split(", ")) == [0, 0, 1]


def test_a_run_dir_of_another_run_is_refused(lab):
    out = lab.dir / "out"
    assert run(lab, out, "--seed", "1").returncode == 0
    again = run(lab, out, "--seed", "2")
    assert again.returncode != 0
    assert "holds another run" in again.stderr
