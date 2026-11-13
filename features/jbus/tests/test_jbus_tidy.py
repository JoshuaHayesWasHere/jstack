"""`jbus tidy` finds and clears what is left over, in one of three modes: `stale` lists the state
nothing will act on again, `blockers` clears a home's blockers, and `files` deletes the files a
skill's step names. Each refusal and exit code the modes had as three verbs of their own, stale,
clear and forget, is run here through the command, against the kitchen's fakes; `files` has its
own tests in `test_jbus_tidy_files.py`.
"""

import pytest

from test_jbus_kitchen import Kitchen

STALE = ("tidy", "stale")
BLOCKERS = ("tidy", "blockers")


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def test_stale_lists_nothing_of_a_project_with_nothing_left_and_ends_0(kitchen):
    code, said = kitchen.main(*STALE, "--project", "demo")
    assert code == 0
    assert said.splitlines()[-1].startswith("stale: 0 in demo (")


def test_stale_refuses_a_project_the_config_does_not_name_and_ends_1(kitchen):
    code, said = kitchen.main(*STALE, "--project", "nope")
    assert code == 1
    assert said.startswith("refused: ") and "nope" in said


def test_stale_refuses_a_queue_that_does_not_parse_and_ends_1(kitchen):
    kitchen.state.mkdir(parents=True, exist_ok=True)
    (kitchen.state / "queue.json").write_text("{not json")
    code, said = kitchen.main(*STALE, "--project", "demo")
    assert (code, said) == (1, f"refused: {kitchen.state / 'queue.json'} does not parse\n")


def test_blockers_says_nothing_blocks_a_home_with_nothing_and_ends_0(kitchen):
    assert kitchen.main("--project", "demo", *BLOCKERS) == (0, "nothing blocks this home\n")


def test_blockers_refuses_a_scope_with_no_plan_and_ends_1(kitchen):
    code, said = kitchen.main("--project", "demo", *BLOCKERS, "--scope", "nowhere")
    assert (code, said) == (
        1,
        f"refused: {kitchen.home / 'nowhere'} has no plan.md, so nowhere is no scoped home\n",
    )


def test_blockers_refuses_a_repo_the_config_does_not_name_and_ends_1(kitchen, tmp_path):
    kitchen.monkeypatch.chdir(tmp_path)
    code, said = kitchen.main(*BLOCKERS)
    assert code == 1
    assert said.startswith("refused: no project for this repo (")


@pytest.mark.parametrize("mode", [STALE, BLOCKERS])
def test_a_mode_that_reads_the_config_refuses_where_there_is_none_and_ends_1(kitchen, mode):
    (kitchen.config_dir / "config.toml").unlink()
    code, said = kitchen.main("--project", "demo", *mode)
    assert (code, said) == (1, f"refused: no config at {kitchen.config_dir / 'config.toml'}\n")
