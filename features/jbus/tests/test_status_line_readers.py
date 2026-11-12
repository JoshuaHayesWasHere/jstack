"""A `Status:` line that says `done` and a note in parentheses is done to every reader in jbus,
as `jbriefs.status` reads it: a scout's row ends done, not left, and a crew's Result leaves
nothing."""

import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from jbriefs.status import Status
from jbus import homestatus, mirror, stale, watch, work
from test_jbus_entry_go import PLAN
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import go, rows
from test_jbus_scout import add, judged, reported, scout_thread
from test_status_line import CASES

REPO = Path(__file__).resolve().parents[3]

NOTED = "done (both ran the same cases)"


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    (made.home / "plan.md").write_text(PLAN)
    yield made
    made.close()


def test_a_scout_whose_report_says_done_with_a_note_ends_done_not_left(kitchen):
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    scout_thread(kitchen, "look")["status"] = "running"
    reported(kitchen, "look", status=NOTED)
    scout_thread(kitchen, "look")["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=3))

    assert rows(kitchen)["look"]["status"] == "done"
    assert judged(kitchen, "look")["scout"] == "report in"


def test_a_scout_whose_report_says_done_with_a_clause_stays_left(kitchen):
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    scout_thread(kitchen, "look")["status"] = "running"
    reported(kitchen, "look", status="done, mostly")
    scout_thread(kitchen, "look")["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=3))

    assert rows(kitchen)["look"]["status"] == "left"


RESULT = f"## Result\nStatus: {NOTED}\nBranch: look   Pull request: none\nLeft: none\n"


def test_a_crews_result_that_says_done_with_a_note_leaves_nothing():
    assert watch.left(RESULT) == ""
    assert watch.written(RESULT) == work.Written.CLEAN


def test_a_paused_result_with_a_note_waits_on_its_rows():
    result = "## Result\nStatus: paused (until a-b merges)\nWaits on: a-b\n"
    assert mirror.paused_on(result, {"a-b"}) == ("a-b",)


def test_a_home_marks_a_merged_result_done_with_a_note_read_without_showing_it(
    tmp_path, monkeypatch
):
    state = tmp_path / "demo"
    (state / "tasks").mkdir(parents=True)
    (state / "beta").mkdir()
    (state / "beta" / "plan.md").write_text("# beta: plan\n")
    (state / "beta" / "read-seen").write_text("")
    for slug, status in (("noted", NOTED), ("mostly", "done, mostly")):
        (state / "tasks" / f"{slug}.md").write_text(
            f"# {slug}\nHome: beta\n\n## Result\nStatus: {status}\nLeft: none\n"
        )
    (state / "merge.log").write_text(
        '2026-10-13 17:00 merged 1 noted abc "a title", revert: gh pr revert x\n'
        '2026-10-13 17:01 merged 2 mostly abd "a title", revert: gh pr revert y\n'
    )
    monkeypatch.setattr(homestatus.paths, "repo_name", lambda: state.name)

    said = homestatus.run(str(state / "beta"), installed=False, only_gates=False)

    assert "tasks/noted.md: ## Result" not in said
    assert "tasks/mostly.md: ## Result" in said


def test_a_result_that_says_done_with_a_full_stop_is_clean_to_stale():
    assert stale._clean("## Result\nStatus: done.\nLeft: none.\n")
    assert not stale._clean("## Result\nStatus: done, mostly\nLeft: none\n")


NO_PR_END = REPO / "features" / "crew" / "no-pr-end.md"


UV = """\
#!{python}
import sys
from jbriefs import cli

sys.exit(cli.main(sys.argv[sys.argv.index("jbriefs") + 1 :]))
"""
"""A `uv` that runs the `jbriefs` the block names, as this environment has it."""


def no_pr_end_says(line: str, tmp_path: Path) -> str:
    """Run the crew's no-pr-end block, as the doc writes it, on a brief whose Result has `line` as
    its Status line and leaves nothing, and return the one line it prints."""
    (block,) = re.findall(r"```sh\n(.*?)```", NO_PR_END.read_text(), re.S)
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "<slug>.md").write_text(
        f"## Result\n{line}\nBranch: look   Pull request: none\nLeft: none\n"
    )
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "uv").write_text(UV.format(python=sys.executable))
    (stub / "uv").chmod(0o755)
    env = {**os.environ, "H": str(tmp_path), "T": str(tmp_path), "GIT_DIR": str(tmp_path / "no")}
    env["PATH"] = f"{stub}{os.pathsep}{env['PATH']}"
    ran = subprocess.run(
        ["bash", "-c", block], cwd=tmp_path, env=env, capture_output=True, text=True, check=True
    )
    return ran.stdout.strip()


def test_the_crews_no_pr_end_block_and_the_parser_agree_on_each_case(tmp_path):
    """The block keeps a paused Result and one that is not done, each for its own reason, and
    lets a done one past its Status line, where the parser reads each the same way."""
    said = {line: no_pr_end_says(line, tmp_path) for line, _ in CASES}
    read = {
        line: "done" if value is Status.DONE else "paused" if value is Status.PAUSED else "not done"
        for line, value in CASES
    }
    assert {
        line: "paused"
        if out == "stay: the task is paused, the last Result says Status: paused"
        else "not done"
        if out == "stay: the last Result does not say Status: done"
        else "done"
        for line, out in said.items()
    } == read
    assert {out for line, out in said.items() if read[line] == "done"} == {
        "stay: git status could not be run here"
    }
