"""`/engine schedule` leaves one scheduled task that runs `/engine` in the root's thread every
15 minutes, and `/engine stop` leaves none. Each test runs the engine skill's own block against a
reply of a fake T3 Code, and makes the calls the block's lines ask for with the skill's own JSON,
which a call checks against its tool's schema before it changes anything."""

import json

import pytest

from test_handoff_pin import call
from test_home_thread import block
from test_scope_root import homes
from test_scoped_home import ROOT
from test_tool_calls import FILLED, errors

__all__ = ["homes"]

DO = "<schedule or stop>"
FILE = "<the reply file>"
EVERY = {"type": "interval", "everyMs": 900000}
OLD = "Run `jbus queue show` and `jbus needs`, and check open PRs with gh."


class T3:
    """The scheduled tasks T3 Code keeps. A task made by a call is bound to the thread that
    calls."""

    def __init__(self):
        self.tasks = {}
        self.made = 0

    def task(self, bound, prompt, title="demo root: run the engine", schedule=EVERY):
        self.made += 1
        id = f"scheduled-task:{self.made}"
        self.tasks[id] = {
            "scheduledTaskId": id,
            "title": title,
            "prompt": prompt,
            "schedule": schedule,
            "enabled": True,
            "boundThreadId": bound,
        }
        return id

    def call(self, caller, made, **filled):
        given = {
            key: filled.get(value, value) if isinstance(value, str) else value
            for key, value in made.given.items()
        }
        assert errors(made, given) == [], made.where
        if made.tool == "schedule_task":
            assert given["bindToCurrentThread"] is True
            self.task(caller, given["prompt"], given["title"], given["schedule"])
        elif made.tool == "delete_scheduled_task":
            del self.tasks[given["scheduledTaskId"]]
        else:
            raise AssertionError(f"{made.where}: no rule here for {made.tool}")

    def engine(self, thread):
        return [task for task in self.tasks.values() if task["boundThreadId"] == thread]


@pytest.fixture
def t3():
    return T3()


def lines(homes, t3, do, thread=ROOT):
    """What the schedule's block prints for `do`, run by the home whose thread is `thread`."""
    reply = homes.home_dir.parent / "reply.json"
    reply.write_text(json.dumps({"tasks": list(t3.tasks.values())}))
    found = block("engine", DO).replace(DO, do).replace(FILE, str(reply))
    return homes.run("home", found, homes.main, thread).stdout.splitlines()


def run(homes, t3, do):
    """`/engine <do>` as the skill says: run the block, make each call its lines ask for, then
    run the block again and return what it printed then."""
    for line in lines(homes, t3, do):
        if line.startswith("make:"):
            t3.call(ROOT, call("engine", "schedule_task"))
        elif line.startswith("delete "):
            id = line.removeprefix("delete ").split(": ", 1)[0]
            delete = call("engine", "delete_scheduled_task")
            t3.call(ROOT, delete, **{FILLED["<scheduledTaskId>"]: id})
        else:
            assert line.startswith(("keep ", "none: ")), line
    return lines(homes, t3, do)


def test_schedule_makes_one_task_and_a_second_run_leaves_it(homes, t3):
    assert run(homes, t3, "schedule") == ["keep scheduled-task:1: demo root: run the engine"]
    (task,) = t3.engine(ROOT)
    assert (task["prompt"], task["schedule"], task["enabled"]) == ("/engine", EVERY, True)
    assert run(homes, t3, "schedule") == ["keep scheduled-task:1: demo root: run the engine"]
    assert len(t3.tasks) == 1


def test_schedule_replaces_the_old_paragraph_and_any_second_engine_task(homes, t3):
    t3.task(ROOT, OLD, title="demo root: run the engine")
    t3.task(ROOT, "/engine", schedule={"type": "interval", "everyMs": 600000})
    theirs = t3.task("mcp:another-thread", "/engine")
    other = t3.task(ROOT, "{{body.say}}", title="jbus events: demo home")
    assert lines(homes, t3, "schedule")[0].startswith("make: ")
    assert run(homes, t3, "schedule") == ["keep scheduled-task:5: demo root: run the engine"]
    assert [task["prompt"] for task in t3.engine(ROOT)] == ["{{body.say}}", "/engine"]
    assert theirs in t3.tasks and other in t3.tasks


def test_stop_deletes_the_engine_task_and_leaves_the_others(homes, t3):
    run(homes, t3, "schedule")
    other = t3.task(ROOT, "{{body.say}}", title="jbus events: demo home")
    assert run(homes, t3, "stop") == ["none: no engine task runs in this thread"]
    assert list(t3.tasks) == [other]
    assert run(homes, t3, "stop") == ["none: no engine task runs in this thread"]


def test_a_reply_the_block_cannot_read_is_named(homes, t3):
    found = block("engine", DO).replace(DO, "schedule").replace(FILE, "/nowhere/reply.json")
    said = homes.run("home", found, homes.main, ROOT).stdout.splitlines()
    assert said[-1].startswith("not read: put the path of a file")
