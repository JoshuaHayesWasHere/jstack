"""A standing rule lives in code, a brief or the queue, and never in a file a thread reads at its
start (`jbus.rules`).

A home's `standing.md` with text in it, and a file with text in it in a Claude Code auto-memory
directory, are each an item of the one list, the root home's, keyed `rulefile:<path>`, and
`jbus rules` lists them and fails. The tests run the real pass against the kitchen's fakes, with
the Claude homes under a home directory of the test's own.
"""

import json
import os
from datetime import timedelta

import pytest

import jbus
from jbus import rules, wakes
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_leftover import home

ASK = "holds a standing rule, and no file a thread reads at its start may hold one"
RULE = "---\nname: a-rule\n---\n\nAlways do the thing.\n"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


@pytest.fixture
def root(kitchen):
    return home(kitchen)["threadId"]


def memory(kitchen, claude=".claude", checkout=None):
    """The auto-memory directory of a checkout, the kitchen's by default, in a Claude home."""
    name = rules.memory_name(checkout or kitchen.checkout)
    made = kitchen.root / "user" / claude / "projects" / name / "memory"
    made.mkdir(parents=True, exist_ok=True)
    return made


def found_in(kitchen):
    config = jbus.load()
    return rules.found(config, config.project("demo"))


def rule_wakes(kitchen, thread):
    return [
        given["message"]
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send"
        and given["threadId"] == thread
        and given["clientRequestId"].startswith("wakes|")
        and "rulefile " in given["message"]
    ]


def listed(kitchen):
    told = json.loads((kitchen.state / wakes.FILE).read_text())["threads"]
    return [key for seen in told.values() for key in seen if key.startswith("rulefile:")]


def test_a_standing_md_with_a_rule_wakes_the_root_once_and_leaves_when_deleted(kitchen, root):
    standing = kitchen.home / "standing.md"
    standing.write_text("# demo: standing rules\n\n1. Never do the thing.\n")
    kitchen.poll(NOW)
    (said,) = rule_wakes(kitchen, root)
    assert f"rulefile {standing}" in said and ASK in said
    kitchen.poll(NOW + timedelta(minutes=1))
    assert len(rule_wakes(kitchen, root)) == 1
    standing.unlink()
    kitchen.poll(NOW + wakes.KEEP + timedelta(minutes=2))
    assert listed(kitchen) == []


def test_an_empty_standing_md_and_an_empty_memory_index_hold_no_rule(kitchen, root):
    (kitchen.home / "standing.md").write_text("\n")
    (memory(kitchen) / "MEMORY.md").write_text("")
    kitchen.poll(NOW)
    assert rule_wakes(kitchen, root) == []
    assert kitchen.main("rules") == (0, "rules: 0 rule files\n")


def test_a_scoped_homes_standing_md_is_a_rule_file_too(kitchen, root):
    scoped = kitchen.home / "flow" / "standing.md"
    scoped.parent.mkdir()
    scoped.write_text("1. A rule of the scope.\n")
    assert found_in(kitchen) == [scoped]


def test_an_auto_memory_file_wakes_the_root_and_its_index_is_listed_too(kitchen, root):
    made = memory(kitchen)
    (made / "a-rule.md").write_text(RULE)
    (made / "MEMORY.md").write_text("- [A rule](a-rule.md): always do the thing\n")
    kitchen.poll(NOW)
    (said,) = rule_wakes(kitchen, root)
    assert f"rulefile {made / 'MEMORY.md'}" in said and f"rulefile {made / 'a-rule.md'}" in said


def test_each_claude_home_t3_runs_is_read_and_a_file_two_homes_share_is_listed_once(
    kitchen, t3_settings
):
    prime = kitchen.root / "user" / ".claude_prime"
    instance = {"driver": "claudeAgent", "config": {"homePath": str(prime)}}
    t3_settings.write_text(json.dumps({"providerInstances": {"prime": instance}}))
    first, second = memory(kitchen) / "a-rule.md", memory(kitchen, ".claude_prime") / "b-rule.md"
    first.write_text(RULE)
    second.write_text(RULE)
    shared = memory(kitchen, ".claude_prime") / "a-rule.md"
    os.link(first, shared)
    found = found_in(kitchen)
    assert sorted(found) == sorted([first, second])


def test_another_projects_memory_is_its_own_and_one_no_project_names_is_the_machines(kitchen):
    infra = kitchen.second("infra")
    (memory(kitchen, checkout=infra.checkout) / "its-rule.md").write_text(RULE)
    (memory(kitchen, checkout=kitchen.root / "scratch") / "loose.md").write_text(RULE)
    orphan = kitchen.root / "home" / "gone" / "standing.md"
    orphan.parent.mkdir()
    orphan.write_text("1. A rule of a home no project has.\n")
    code, said = kitchen.main("rules")
    lines = said.splitlines()
    assert code == 1 and lines[-1] == "rules: 3 rule files"
    assert lines[0] == f"infra: {orphan}"
    assert sorted(line.split(": ", 1)[0] for line in lines[:-1]) == ["infra"] * 3
    code, said = kitchen.main("rules", "--project", "demo")
    assert (code, said) == (0, "rules: 0 rule files\n")
