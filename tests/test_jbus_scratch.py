"""A scratch home is a project with no repo: `jbus project add --scratch` writes its table,
the pass runs no repo step for it, `jbus status` lists it with its home thread, and `jbus
word --to <name>` reaches that thread.

Every test runs the real commands and the real pass in the kitchen of `test_jbus_kitchen`,
against its faked T3 Code server. Nothing reaches the network.
"""

import subprocess
import tomllib

import pytest

import jbus
from test_jbus_kitchen import sends

NAME = "scratch"
SCRATCH_ID = "mcp:the-no-project-id"
AT = "2026-10-12 10:55 ET"
SAID = ("--by", "user", "--at", AT, "tidy", "this", "draft")


def add(kitchen, name=NAME, project=SCRATCH_ID):
    return kitchen.main("project", "add", name, "--scratch", "--project-id", project)


@pytest.fixture
def scratch(kitchen):
    """The kitchen with a scratch home added and started: its thread id in its `home-id`."""
    code, out = add(kitchen)
    assert code == 0, out
    home = kitchen.root / "home" / NAME
    home.mkdir(parents=True)
    (home / "home-id").write_text("mcp:scratch-home\n")
    return home


def ran_in(kitchen, monkeypatch):
    """Every directory a command of the pass ran in, the kitchen's fakes included."""
    seen = []
    inner = subprocess.run

    def run(command, **how):
        seen.append(str(how.get("cwd") or ""))
        return inner(command, **how)

    monkeypatch.setattr(subprocess, "run", run)
    return seen


def test_project_add_writes_a_scratch_table_with_no_checkout(kitchen):
    code, out = add(kitchen)
    assert code == 0 and out.startswith("added: one [[project]] table"), out
    table = tomllib.loads((kitchen.config_dir / "config.toml").read_text())["project"][-1]
    assert table == {"name": NAME, "kind": "scratch", "projectId": SCRATCH_ID}
    assert add(kitchen) == (1, "refused: the config already has this project\n")
    assert add(kitchen, "demo")[1] == "refused: the config already has a project of that name\n"


def test_a_scratch_home_is_no_repo_project_of_the_config(scratch):
    config = jbus.load()
    assert [one.name for one in config.projects] == ["demo"]
    assert [(one.name, one.project_id) for one in config.scratch] == [(NAME, SCRATCH_ID)]


def test_the_pass_runs_no_repo_step_for_a_scratch_home(kitchen, scratch, monkeypatch):
    seen = ran_in(kitchen, monkeypatch)
    kitchen.poll()
    assert seen and all(where in ("", str(kitchen.checkout)) for where in seen), seen
    state = kitchen.state_dir / NAME
    left = sorted(path.name for path in state.iterdir()) if state.exists() else []
    assert "queue.json" not in left and "wake.json" not in left, left
    asked = [given for _, given in kitchen.t3.calls if SCRATCH_ID in str(given)]
    assert asked == []


def test_status_lists_the_scratch_home_with_its_thread_and_no_repo_fields(kitchen, scratch):
    kitchen.poll()
    status = kitchen.status()
    assert NAME not in status["projects"]
    assert status["scratch"] == {
        NAME: {"project_id": SCRATCH_ID, "home_thread": "mcp:scratch-home"}
    }
    assert NAME not in status["homes_off_bus"]
    code, out = kitchen.main("status")
    assert code == 0 and '"home_thread": "mcp:scratch-home"' in out


def test_a_word_to_the_scratch_home_reaches_its_thread(kitchen, scratch):
    code, out = kitchen.main("word", "--to", NAME, *SAID)
    assert code == 0 and out.startswith(f"sent: {NAME}, to mcp:scratch-home, word "), out
    (sent,) = sends(kitchen)
    assert sent["threadId"] == "mcp:scratch-home"
    assert sent["message"].endswith("tidy this draft")


def test_a_word_recorded_from_the_scratch_homes_own_thread_is_kept_and_not_posted(kitchen, scratch):
    code, out = kitchen.main("word", "--to", NAME, "--from", "mcp:scratch-home", *SAID)
    assert code == 0 and out.startswith(f"kept: {NAME}, not posted,"), out
    assert sends(kitchen) == []


def test_a_word_that_waited_for_the_home_id_goes_on_the_next_pass(kitchen, scratch):
    (scratch / "home-id").unlink()
    code, out = kitchen.main("word", "--to", NAME, *SAID)
    assert code == 0 and out.startswith(f"waits: {NAME},"), out
    (scratch / "home-id").write_text("mcp:scratch-home\n")
    kitchen.poll()
    assert [one["threadId"] for one in sends(kitchen)] == ["mcp:scratch-home"]
