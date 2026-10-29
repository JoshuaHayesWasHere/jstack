"""One route to a home: every delivery to a home is an open item with an owner, carried by the
one list (`jbus.wakes`), and nothing else writes a home's box or sends to a home's thread.

The scan reads each module of jbus for each call that sends to a thread (`outbox.send`, under any
name it is imported as, or the `t3_thread_send` tool itself), by the function it is in. It fails
on any call site not in `SENDERS`: a new module that sends, and a new send in a module named there,
whether in a new function or a second call in a named one. Each module says whom it sends to. The
ones that reach a home outside the list are named as such, so a new side door to a home fails here
and has to be argued for."""

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
    "wakes.py": (ITEMS, ["_send"]),
    "outbox.py": ("the outbox every send goes through", ["send"]),
    "reload.py": ("a thread that loaded a skill a merge changed", ["_told"]),
    "reviewed.py": ("the crew of a reviewed pull request", ["tell"]),
    "rebase.py": ("the crew of a pull request to rebase", ["post"]),
    "mainmoved.py": ("the crew whose pull request fixes main", ["tell"]),
    "slotwait.py": ("a thread that waits on a test slot", ["tell", "tell_capped", "tell_ended"]),
    "failover.py": ("a thread moved to another provider", ["apply"]),
    "questions.py": ("the thread that asked a question", ["carry", "propose"]),
    "remarks.py": ("the thread a remark is for", ["tell"]),
    "threads.py": (
        "a crew to resume or that merged; a home, of a crew that stopped",
        ["_stopped", "merged", "resume"],
    ),
    "children.py": ("a home, of a child home that stalled", ["_send"]),
    "clock.py": ("a crew, or a home, of a row the clock holds", ["_send"]),
    "merge.py": ("a home, of a row jmerge put on no step", ["unplaced"]),
    "stop.py": ("a home, of what a stopped thread asked or was answered", ["_send"]),
    "word.py": ("a home, with the user's own word", ["post"]),
}


def _names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """The names the module calls `outbox` by, and the names it calls `outbox.send` by."""
    modules, functions = {"outbox"}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for one in node.names:
                if node.module == "jbus" and one.name == "outbox":
                    modules.add(one.asname or one.name)
                if node.module == "jbus.outbox" and one.name == "send":
                    functions.add(one.asname or one.name)
        elif isinstance(node, ast.Import):
            named = (one for one in node.names if one.name == "jbus.outbox")
            modules |= {one.asname for one in named if one.asname}
    return modules, functions


def _sends(node: ast.AST, modules: set[str], functions: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "send":
        if isinstance(func.value, ast.Name) and func.value.id in modules:
            return True
    if isinstance(func, ast.Name) and func.id in functions:
        return True
    return any(isinstance(arg, ast.Constant) and arg.value == "t3_thread_send" for arg in node.args)


def senders(tree: ast.AST) -> list[str]:
    """Each call that sends to a thread, by the function or method it is in, once for each."""
    modules, functions = _names(tree)
    found: list[str] = []

    def walk(node: ast.AST, where: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = where
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{where}.{child.name}" if where else child.name
            if _sends(child, modules, functions):
                found.append(name or "<module>")
            walk(child, name)

    walk(tree, "")
    return sorted(found)


def test_only_the_named_call_sites_send_to_a_thread():
    found = {
        str(path.relative_to(SOURCE)): senders(ast.parse(path.read_text()))
        for path in sorted(SOURCE.rglob("*.py"))
    }
    assert {name: sites for name, sites in found.items() if sites} == {
        name: sorted(sites) for name, (_, sites) in SENDERS.items()
    }


def test_a_send_under_another_name_or_a_second_in_a_named_function_is_found():
    aliased = "from jbus import outbox as box\n\ndef tell(run):\n    box.send(run)\n"
    imported = "from jbus.outbox import send as post\n\ndef tell(run):\n    post(run)\n"
    once = "    outbox.send(run)\n"
    twice = f"from jbus import outbox\n\ndef _send(run):\n{once}{once}"
    assert senders(ast.parse(aliased)) == ["tell"]
    assert senders(ast.parse(imported)) == ["tell"]
    assert senders(ast.parse(twice)) == ["_send", "_send"]


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
