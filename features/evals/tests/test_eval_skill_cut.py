"""The skill-cut eval scores an answer from its text and its case's key alone. It reads the
files under test from git revisions, never from the working tree, and it applies the README's
rule."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jbriefs import skills
from testing.paths import REPO

EVAL = REPO / "features" / "evals" / "evals" / "skill-cut"


def load(path):
    sys.path.insert(0, str(EVAL))
    try:
        spec = importlib.util.spec_from_file_location(f"skill_cut_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(EVAL))


score = load(EVAL / "score.py")
run = load(EVAL / "eval.py")


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


def test_a_finding_outside_where_scores_when_it_ends_with_the_tag_the_skill_gives():
    """The key asks for the words pr-review's SKILL.md tells the reviewer to end such a finding
    with, so a reviewer that does what the skill says scores 1."""
    skill = (REPO / "features" / "pr-review" / "SKILL.md").read_text()
    tag = re.search(r"with these words at the end of its line: `([^`]+)`", skill)[1]
    case = next(one for one in run.steps_cases() if one["id"] == "pr-review-outside-where")
    answer = f"Keep the finding and send it like any other, its line ending `{tag}`."
    assert score.score_steps(answer, case).value == 1.0


def test_a_fault_outside_where_scores_when_the_answer_uses_the_crew_skills_words():
    """The crew skill says a fault outside the task makes "a queued row", so an answer in its
    words scores 1 without the judge."""
    rule = (REPO / "features" / "crew" / "do-the-task.md").read_text()
    words = re.search(r"which makes it (a queued row)", rule)[1]
    case = next(one for one in run.steps_cases() if one["id"] == "crew-outside-where")
    answer = f"Leave it out of the diff: the off-by-one becomes {words} of its own."
    assert score.score_steps(answer, case).value == 1.0


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
        named = Path(case["file"])
        there = any((REPO / each).is_file() for each in run.spellings(case["file"]))
        assert there or skills.resolve(named.stem).kind == "principle"
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
    """run-1 was answered against an older `steps.json`, kept in `fixture/steps-of-run-1.json`."""
    for name in ("cases", "run-1"):
        shutil.copytree(EVAL / name, tmp_path / name)
    shutil.copy(EVAL / "fixture" / "steps-of-run-1.json", tmp_path / "cases" / "steps.json")
    monkeypatch.setattr(run, "HERE", tmp_path)
    assert run.main(["--run", "run-1"]) == 0
    for name in ("scores.json", "results.md"):
        assert (tmp_path / "run-1" / name).read_bytes() == (EVAL / "run-1" / name).read_bytes()
    key = json.loads((EVAL / "run-1" / "key.json").read_text())
    assert {one["arm"] for one in key.values()} == set(run.ARMS)


def test_a_reports_prose_holds_one_sentence_to_a_line_so_a_branch_can_commit_its_run(
    tmp_path, monkeypatch
):
    """`prose_lint.py` judges each line a cut branch adds, a new run's `results.md` among them."""
    path = REPO / "features" / "writing" / "scripts" / "prose_lint.py"
    spec = importlib.util.spec_from_file_location("skill_cut_prose_lint", path)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    for name in ("cases", "run-1"):
        shutil.copytree(EVAL / name, tmp_path / name)
    shutil.copy(EVAL / "fixture" / "steps-of-run-1.json", tmp_path / "cases" / "steps.json")
    (tmp_path / "run-1" / "results.md").unlink()
    monkeypatch.setattr(run, "HERE", tmp_path)
    assert run.main(["--run", "run-1"]) == 0
    lines = (tmp_path / "run-1" / "results.md").read_text().splitlines()
    judged = [one for one, prose in zip(lines, lint.prose(lines), strict=True) if prose]
    assert judged
    assert [one for one in judged if len(lint.sentences(one)) > 1] == []


def test_a_whole_write_adds_one_run_of_a_few_files_whatever_the_number_of_answers(
    tmp_path, monkeypatch
):
    shutil.copytree(EVAL / "cases", tmp_path / "cases")
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(run, "_private", lambda: ())
    monkeypatch.setattr(run.shutil, "which", lambda name: "/bin/true")
    monkeypatch.setattr(run, "claude", lambda prompt, model=run.MODEL: "BUCKETS\n")
    run.write("HEAD", "HEAD")
    named = tmp_path / f"run-{run.resolve('HEAD')[:12]}"
    made = sorted(path.name for path in named.iterdir())
    assert made == ["answers.json", "key.json", "run.json", "variant.patch", "which.json"]
    answers = json.loads((named / "answers.json").read_text())
    assert len(answers) == len(run.case_ids()) * len(run.ARMS) * run.TRIALS
    assert json.loads((named / "run.json").read_text())["cases"] == run.cases_sha()


def test_two_branches_name_their_runs_apart_and_a_kept_name_is_refused(tmp_path, monkeypatch):
    (tmp_path / "run-1").mkdir()
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(run.shutil, "which", lambda name: "/bin/true")
    calls = []
    monkeypatch.setattr(run, "_private", lambda: calls.append(1) or ())
    with pytest.raises(SystemExit, match="run-1 is kept already"):
        run.write("HEAD", "HEAD", "run-1")
    with pytest.raises(SystemExit, match="is not run-"):
        run.write("HEAD", "HEAD", "../elsewhere")
    assert calls == []
    assert run.main(["--base", "HEAD", "--variant", "HEAD", "--nam", "run-x"]) == 2


def test_a_skill_is_read_before_and_after_its_move_into_a_features_skills_folder(
    tmp_path, monkeypatch
):
    commit = ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm")
    git(tmp_path, "init", "-q")
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "skills" / "demo" / "SKILL.md").write_text("before the move\n")
    git(tmp_path, "add", ".")
    git(tmp_path, *commit, "one")
    (tmp_path / "features" / "lib" / "skills").mkdir(parents=True)
    git(tmp_path, "mv", "skills/demo", "features/lib/skills/demo")
    (tmp_path / "features" / "lib" / "skills" / "demo" / "SKILL.md").write_text("after\n")
    git(tmp_path, "add", ".")
    git(tmp_path, *commit, "two")
    monkeypatch.setattr(run, "REPO", tmp_path)
    assert run.show("HEAD~1", "skills/demo/SKILL.md") == "before the move\n"
    assert run.show("HEAD", "skills/demo/SKILL.md") == "after\n"


def test_a_kept_run_is_not_rescored_against_cases_that_changed(tmp_path, monkeypatch):
    for name in ("cases", "run-1"):
        shutil.copytree(EVAL / name, tmp_path / name)
    steps = tmp_path / "cases" / "steps.json"
    shutil.copy(EVAL / "fixture" / "steps-of-run-1.json", steps)
    monkeypatch.setattr(run, "HERE", tmp_path)
    steps.write_text(steps.read_text().replace("Stale base: at", "Stale base:"))
    with pytest.raises(SystemExit, match="answered against cases"):
        run.main(["--run", "run-1"])


def test_a_principle_is_read_under_the_name_it_has_at_each_revision():
    """A case names `principles/type-system-discipline.md`, which was the file's name before the
    rename added pstack's prefix. At a revision after the rename, the eval reads the renamed file
    for the old name, just as it does for the new name."""
    path = "principles/type-system-discipline.md"
    renamed = "HEAD:features/principles/skills/principle-type-system-discipline/SKILL.md"
    now = subprocess.run(
        ["git", "-C", str(REPO), "show", renamed], capture_output=True, text=True, check=True
    ).stdout
    assert run.show("HEAD", path) == now
    assert run.show("HEAD", "principles/principle-type-system-discipline.md") == now
