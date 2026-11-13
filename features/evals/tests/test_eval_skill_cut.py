"""The skill-cut eval scores an answer from its text and its case's key alone. It reads the
files under test from git revisions, never from the working tree, and it applies the README's
rule."""

import importlib.util
import json
import re
import subprocess
import sys

import pytest

from testing.paths import REPO

EVAL = REPO / "features" / "evals" / "evals" / "skill-cut"

READ_SET = ("features/evals/evals/skill-cut/",)


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
    rule = (REPO / "features" / "crew" / "SKILL.md").read_text()
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


def test_a_call_that_fails_is_tried_again_after_a_wait(monkeypatch):
    """A login that lapses for a moment fails every try made at once, and one failed call ends the
    run with all its answers lost."""
    ran = iter(
        subprocess.CompletedProcess([], code, out, err)
        for code, out, err in [(1, "", "Not logged in"), (1, "", "Not logged in"), (0, "ok\n", "")]
    )
    waits = []
    monkeypatch.setattr(run.subprocess, "run", lambda *a, **k: next(ran))
    monkeypatch.setattr(run.time, "sleep", waits.append)
    assert run.claude("the prompt") == "ok"
    assert waits == [run.TRY_AGAIN_AFTER, run.TRY_AGAIN_AFTER]


def test_write_with_no_claude_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "DATA", tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "no-bin"))
    with pytest.raises(SystemExit, match="no claude on PATH"):
        run.write("HEAD", "HEAD")
    assert list(tmp_path.iterdir()) == []


def test_the_kept_run_1_rescores_to_its_results_byte_for_byte(kept_runs, monkeypatch):
    """run-1 was answered against an older `steps.json`, kept in `fixture/steps-of-run-1.json`."""
    monkeypatch.setattr(run, "DATA", kept_runs)
    monkeypatch.setattr(run, "STEPS_FILE", kept_runs / "fixture" / "steps-of-run-1.json")
    written = [kept_runs / "run-1" / name for name in ("scores.json", "results.md")]
    kept = {path: path.read_bytes() for path in written}
    for path in written:
        path.unlink()
    assert run.main(["--run", "run-1"]) == 0
    for path, was in kept.items():
        assert path.read_bytes() == was
    key = json.loads((kept_runs / "run-1" / "key.json").read_text())
    assert {one["arm"] for one in key.values()} == set(run.ARMS)


def test_two_branches_name_their_runs_apart_and_a_kept_name_is_refused(tmp_path, monkeypatch):
    (tmp_path / "run-1").mkdir()
    monkeypatch.setattr(run, "DATA", tmp_path)
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


def test_the_variant_patch_holds_the_diff_of_a_file_named_as_it_was_before_its_move(
    tmp_path, monkeypatch
):
    commit = ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm")
    git(tmp_path, "init", "-q")
    (tmp_path / "features" / "lib" / "skills" / "demo").mkdir(parents=True)
    skill = tmp_path / "features" / "lib" / "skills" / "demo" / "SKILL.md"
    skill.write_text("the base\n")
    git(tmp_path, "add", ".")
    git(tmp_path, *commit, "one")
    skill.write_text("the variant\n")
    git(tmp_path, "add", ".")
    git(tmp_path, *commit, "two")
    monkeypatch.setattr(run, "REPO", tmp_path)
    said = run.patch("HEAD~1", "HEAD", ["skills/demo/SKILL.md"])
    assert "-the base\n+the variant\n" in said
    assert run.patch("HEAD", "HEAD", ["skills/demo/SKILL.md"]) == ""


def test_a_kept_run_is_not_rescored_against_cases_that_changed(kept_runs, monkeypatch):
    steps = kept_runs / "fixture" / "steps-of-run-1.json"
    monkeypatch.setattr(run, "DATA", kept_runs)
    monkeypatch.setattr(run, "STEPS_FILE", steps)
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


def test_a_steps_file_is_fed_as_read_with_each_side_file_after_its_trigger_line(
    tmp_path, monkeypatch
):
    git(tmp_path, "init", "-q")
    folder = tmp_path / "skills" / "crew"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("one\nThen: read `$T/../skills/crew/side.md` now.\ntwo\n")
    (folder / "side.md").write_text("the side\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one")
    monkeypatch.setattr(run, "REPO", tmp_path)
    text = run.as_read(run.resolve("HEAD"), "skills/crew/SKILL.md")
    assert text.splitlines() == [
        "one",
        "Then: read `$T/../skills/crew/side.md` now.",
        "",
        "the side",
        "two",
    ]
