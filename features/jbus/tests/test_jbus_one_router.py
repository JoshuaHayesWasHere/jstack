"""One route to a home: every delivery to a home is an open item with an owner, carried by the
one list (`jbus.wakes`), and nothing else writes a home's box or sends to a home's thread.

The scan reads each module of jbus for a call that sends to a thread (`outbox.send`, or the
`t3_thread_send` tool itself), and fails on any module not in `SENDERS`. Each module there says
whom it sends to. The ones that reach a home outside the list are named as such, so a new side
door to a home fails here and has to be argued for."""

import ast
import json
from datetime import timedelta
from pathlib import Path

import jbus
from jbus import alert, digest, record, wake
from test_jbus_kitchen import NOW

SOURCE = Path(jbus.__file__).parent
ITEMS = "the one list of open items"
SENDERS = {
    "wakes.py": ITEMS,
    "outbox.py": "the outbox every send goes through",
    "reload.py": "a thread that loaded a skill a merge changed",
    "reviewed.py": "the crew of a reviewed pull request",
    "rebase.py": "the crew of a pull request to rebase",
    "mainmoved.py": "the crew whose pull request fixes main",
    "slotwait.py": "a thread that waits on a test slot",
    "failover.py": "a thread moved to another provider",
    "questions.py": "the thread that asked a question",
    "remarks.py": "the thread a remark is for",
    "threads.py": "a crew to resume or that merged; a home, of a crew that stopped",
    "children.py": "a home, of a child home that stalled",
    "clock.py": "a crew, or a home, of a row the clock holds",
    "merge.py": "a home, of a row jmerge put on no step",
    "stop.py": "a home, of what a stopped thread asked or was answered",
    "word.py": "a home, with the user's own word",
}


def _sends(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "send":
            if isinstance(func.value, ast.Name) and func.value.id == "outbox":
                return True
        named = (arg.value for arg in node.args if isinstance(arg, ast.Constant))
        if "t3_thread_send" in named:
            return True
    return False


def test_only_the_named_modules_send_to_a_thread():
    found = {
        str(path.relative_to(SOURCE))
        for path in sorted(SOURCE.rglob("*.py"))
        if _sends(ast.parse(path.read_text()))
    }
    assert found == set(SENDERS)


def test_a_box_send_writes_the_log_and_nothing_a_home_reads(kitchen):
    project = jbus.load().projects[0]
    state = kitchen.root / "box"
    state.mkdir()
    box = wake.Box(state, project)
    assert box.send("", "alert", "alert: one", key="one")
    assert not box.send("", "alert", "alert: one", key="one")
    files = {path.name for path in state.rglob("*") if path.is_file()}
    assert files - {name for name in files if name.endswith(".lock")} == {
        "events.jsonl",
        "sent.json",
    }
    assert kitchen.t3.calls == []


def test_an_owner_resolves_to_its_project_or_to_infra_and_never_to_every_home(kitchen):
    kitchen.second("infra")
    config = jbus.load()
    own, infra = config.projects
    assert config.owner(own.name) == own
    assert config.owner(alert.MACHINE) == infra
    assert config.owner("no-such-project") == infra


def test_a_machine_item_with_no_infra_project_goes_to_the_desk_alone(kitchen, monkeypatch):
    desk = []
    monkeypatch.setattr(wake, "notify", desk.append)
    config = jbus.load()
    assert config.owner(alert.MACHINE) is None
    assert config.owner("no-such-project") is None
    alert.raise_(config, "pass", "alert: pass failed", now=NOW)
    alert.raise_(config, "pass", "alert: pass failed", now=NOW + timedelta(minutes=1))
    assert desk == ["alert: pass failed"]
    assert [one.key for one in alert.open_items(config.state_dir, NOW)] == ["pass"]


def test_an_alert_of_a_project_is_not_raised_on_the_desk(kitchen, monkeypatch):
    desk = []
    monkeypatch.setattr(wake, "notify", desk.append)
    config = jbus.load()
    name = config.projects[0].name
    alert.raise_(config, f"jmerge {name}", "alert: jmerge failed", owner=name, now=NOW)
    assert desk == []
    assert alert.open_items(config.state_dir, NOW)[0].owner == name


def test_status_names_no_webhook_and_no_wake_setting(kitchen):
    kitchen.poll(NOW)
    status = kitchen.status()
    assert "webhook" not in json.dumps(status)
    assert "wake" not in status["projects"]["demo"]
    assert "outbox" not in status["projects"]["demo"]


def test_status_and_the_digest_show_the_last_sweep(kitchen):
    config = jbus.load()
    wake.Box(kitchen.state, config.project("demo")).swept("2026-10-23 ran", True)
    assert record.status(config, NOW)["projects"]["demo"]["sweep"] == "2026-10-23 ran"
    assert digest.build(config, now=NOW)["projects"]["demo"]["sweep"] == "2026-10-23 ran"
