"""The skill-cut eval scores an answer from its text and its case's key alone, reads the files
under test from git revisions and never the working tree, and applies the README's rule."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
EVAL = REPO / "evals" / "skill-cut"


def load(name):
    sys.path.insert(0, str(EVAL))
    try:
        spec = importlib.util.spec_from_file_location(f"skill_cut_{name}", EVAL / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(EVAL))


score = load("score")
run = load("eval")


def test_the_committed_lead_fixture_scores_seven_of_nine():
    text = (EVAL / "fixture" / "lead-pstack-autopilot-ketchup.md").read_text()
    said = score.score_lead(text, run.lead_key("pstack-autopilot-ketchup"))
    assert said.unsettled == []
    assert said.value == pytest.approx(7 / 9)
    assert said.detail["three_way"] == pytest.approx(6 / 9)
    assert (said.detail["fixed"], said.detail["fixed_sent"], said.detail["sent"]) == (4, 3, 4)


def test_the_committed_steps_fixture_takes_the_prescribed_step():
    text = (EVAL / "fixture" / "steps-crew-stale-base.md").read_text()
    case = next(one for one in run.steps_cases() if one["id"] == "crew-stale-base")
    assert score.score_steps(text, case).value == 1.0


def test_a_finding_with_no_bucket_is_unsettled_until_the_judge_reads_it():
    key = {
        "A1": {"fate": "sent", "fixed": True},
        "A2": {"fate": "dismissed", "fixed": None},
        "B1": {"fate": "dropped", "fixed": None},
    }
    text = "BUCKETS\nA1: Consider\n"
    assert score.score_lead(text, key).unsettled == ["A2"]
    assert score.score_lead(text, key, {"A2": "noted"}).value == 1.0
    assert score.score_lead(text, key, {"A2": "none"}).value == 1.0
    assert score.score_lead("BUCKETS\nA1: Noted\nA2: Act on\n", key).value == 0.0


def test_the_last_buckets_block_wins():
    text = "BUCKETS\nA1: Act on\n\nOn reflection:\n\nBUCKETS\nA1: Dismissed\n"
    assert score.buckets(text) == {"A1": "dismissed"}


def test_a_steps_answer_near_the_key_is_unsettled_and_the_judge_settles_it():
    case = {"id": "x", "must": [r"Stale base: at"], "near": r"(?i)stale base"}
    assert score.score_steps("I note the stale base.", case).unsettled == ["x"]
    assert score.score_steps("I note the stale base.", case, True).value == 1.0
    assert score.score_steps("I rebase.", case).value == 0.0


def test_every_case_is_whole_and_every_key_names_a_finding_of_its_case():
    for case in run.steps_cases():
        assert set(case) >= {"id", "file", "state", "expect", "must", "near"}
        assert (REPO / case["file"]).is_file()
        for shape in [*case["must"], case["near"]]:
            re.compile(shape)
    files = {case["file"] for case in run.steps_cases()}
    for name in ("home", "crew", "scout", "pr-review", "handoff", "expert"):
        assert sum(one["file"] == f"skills/{name}/SKILL.md" for one in run.steps_cases()) >= 3
    assert {"principles/type-system-discipline.md"} <= files
    assert len(run.lead_cases()) >= 15
    for slug in run.lead_cases():
        body = (EVAL / "cases" / "lead" / f"{slug}.md").read_text()
        ids = re.findall(r"^### ([AB]\d+)$", body, re.M)
        assert set(run.lead_key(slug)) == set(ids), slug


def git(where, *args):
    subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True)


def test_a_file_is_read_from_the_revision_and_never_from_the_working_tree(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    (tmp_path / "skill.md").write_text("as committed\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one")
    (tmp_path / "skill.md").write_text("edited, not committed\n")
    monkeypatch.setattr(run, "REPO", tmp_path)
    assert run.show(run.resolve("HEAD"), "skill.md") == "as committed\n"
    with pytest.raises(SystemExit, match="no-such-rev"):
        run.resolve("no-such-rev")


def test_an_anchored_private_pattern_takes_out_the_name_and_keeps_the_line():
    pattern = run.jleak.Pattern("user-name", re.compile(r"(?i)^(?!Copyright).*\b(?:ada)\b"))
    text = "first line\nTask: Ada, 2026-10-15, relayed: ask Ada\n"
    assert (
        run._redact(text, (pattern,))
        == "first line\nTask: the user, 2026-10-15, relayed: ask the user\n"
    )


def test_the_rule_holds_within_the_noise_floor_and_fails_on_a_sign_test_loss():
    held = run.verdict([1.0, 0.5, 0.5], [0.9, 0.5, 0.5], [0.95, 0.5, 0.5])
    assert held["floor"] == pytest.approx(0.1 / 3) and held["holds"]
    below = run.verdict([1.0, 1.0], [1.0, 1.0], [0.9, 1.0])
    assert not below["within"] and not below["holds"]
    lost = run.verdict([1.0] * 8, [0.0] * 8, [0.9] * 8)
    assert lost["within"] and lost["lost"] and lost["p"] == pytest.approx(0.0078, abs=0.0001)


@pytest.mark.parametrize(("wins", "losses", "p"), [(10, 0, 0.002), (5, 5, 1.0), (0, 0, 1.0)])
def test_the_sign_test_is_two_sided(wins, losses, p):
    assert run.sign_test(wins, losses) == pytest.approx(p, abs=0.001)


def test_run_rescores_a_kept_run_and_refuses_anything_else(capsys):
    assert run.main(["--run", "run-1", "write"]) == 2
    assert run.main(["--run", "run-9"]) == 2
    assert run.main(["--base", "main"]) == 2
    assert "--run" in capsys.readouterr().err


def test_write_with_no_claude_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "no-bin"))
    with pytest.raises(SystemExit, match="no claude on PATH"):
        run.write("HEAD", "HEAD")
    assert list(tmp_path.iterdir()) == []


def test_the_committed_run_1_rescores_to_its_results_byte_for_byte(tmp_path, monkeypatch):
    for name in ("cases", "run-1"):
        shutil.copytree(EVAL / name, tmp_path / name)
    monkeypatch.setattr(run, "HERE", tmp_path)
    assert run.main(["--run", "run-1"]) == 0
    for name in ("scores.json", "results.md"):
        assert (tmp_path / "run-1" / name).read_bytes() == (EVAL / "run-1" / name).read_bytes()
    key = json.loads((EVAL / "run-1" / "key.json").read_text())
    assert {one["arm"] for one in key.values()} == set(run.ARMS)
