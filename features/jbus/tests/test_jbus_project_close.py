"""`jbus project close <name>` puts a project away: no pass, word or scheduled task reaches it, and
T3 Code lists none of its threads. `jbus project open <name>` brings it back as it was, and the next
pass works what it left queued.

Like `test_jbus_kitchen.py`, the tests run the real commands and the real pass against a faked T3
Code server, `gh` and `jmerge`. Nothing reaches the network.
"""

import tomllib
from datetime import datetime, timedelta

import pytest

import jbus
import jsettings
from jbus import project, t3
from jbus.view import state as view_state
from jmerge import judgement
from test_jbus_kitchen import NOW, PROJECT, complete, sends
from test_jbus_questions import held

HOME_1, HOME_2, CREW_2 = "home-1", "home-2", "mcp:other-crew"
REFUSED = "refused: project other is closed: jbus project open other first"


@pytest.fixture
def two(kitchen):
    """`demo` and `other`, each with a home thread, a queued row with the user's go, and room for
    both to launch. `other` also has an unanswered question, a finished crew's thread, a
    scheduled task that is on and one that is off."""
    side = kitchen.second()
    kitchen.config(max_running=4)
    for home, thread, at in ((kitchen.home, HOME_1, PROJECT), (side.home, HOME_2, side.project)):
        (home / "home-id").write_text(f"{thread}\n")
        kitchen.t3.thread("home", "completed", threadId=thread, title="home: x", project=at)
    kitchen.t3.thread("old", "completed", threadId=CREW_2, project=side.project)
    kitchen.t3.tasks += [
        {"scheduledTaskId": "task-on", "projectId": side.project, "enabled": True},
        {"scheduledTaskId": "task-off", "projectId": side.project, "enabled": False},
        {"scheduledTaskId": "task-demo", "projectId": PROJECT, "enabled": True},
    ]
    for name, slug in (("demo", "alpha"), ("other", "beta")):
        queued(kitchen, name, slug)
    (side.home / "tasks" / "gamma.md").write_text("# gamma: a task\nWhere: `src/gamma/`\n")
    assert kitchen.main("--project", "other", "gate", "gamma", stdin=held())[0] == 0
    return side


def queued(kitchen, name, slug):
    text = complete(slug)
    add = ["--project", name, "queue", "add", slug, "--priority", "1"]
    assert kitchen.main(*add, stdin=text)[0] == 0, kitchen.main(*add, stdin=text)
    sha = judgement.brief_sha(text)[:12]
    approve = ["--project", name, "queue", "approve", slug, "--word", kitchen.word(name)]
    assert kitchen.main(*approve, "--sha", sha)[0] == 0


def thread(kitchen, at):
    return next(one for one in kitchen.t3.threads if one["threadId"] == at)


def tasks(kitchen):
    return {one["scheduledTaskId"]: one["enabled"] for one in kitchen.t3.tasks}


def today():
    return jsettings.load().local(datetime.now().astimezone()).date().isoformat()


def table(kitchen, name):
    raw = tomllib.loads((kitchen.config_dir / "config.toml").read_text())
    return next(one for one in raw["project"] if one["name"] == name)


def test_a_pass_reaches_only_the_open_project_and_after_open_it_works_the_closed_ones_row(
    kitchen, two
):
    code, said = kitchen.main("project", "close", "other")
    assert code == 0 and said.startswith("closed: other, 2 threads archived and 1 scheduled tasks")
    assert table(kitchen, "other")["closed"] == today()
    assert "closed" not in table(kitchen, "demo")
    assert [thread(kitchen, one).get("archived") for one in (HOME_2, CREW_2)] == [True, True]
    assert not thread(kitchen, HOME_1).get("archived")
    assert tasks(kitchen) == {"task-on": False, "task-off": False, "task-demo": True}

    kitchen.t3.calls.clear()
    kitchen.poll()
    launched = [one["title"] for one in kitchen.t3.launches]
    assert launched == ["crew: alpha"]
    assert all(one["threadId"] not in (HOME_2, CREW_2) for one in sends(kitchen))
    assert two.wakes.listed == []
    assert all(given.get("projectId") != two.project for _, given in kitchen.t3.calls), (
        "a pass asked T3 Code about the closed project"
    )
    code, out = kitchen.main("needs")
    assert code == 0 and "other" not in out

    words = kitchen.message("go all crews")
    code, out = kitchen.main("word", "--all", *words)
    assert code == 0 and out.startswith("sent: demo, to home-1") and "other" not in out
    assert kitchen.main("word", "--to", "other", *words) == (1, REFUSED + "\n")
    add = ["--project", "other", "queue", "add", "delta", "--priority", "1"]
    assert kitchen.main(*add, stdin=complete("delta")) == (1, REFUSED + "\n")
    code, out = kitchen.main("--project", "other", "queue", "show")
    assert code == 0 and "beta" in out

    status = jbus.load()
    assert [one.name for one in status.closed] == ["other"]
    code, out = kitchen.main("status")
    assert code == 0 and '"closed": {\n    "other": "' + today() + '"' in out
    assert '"homes_off_bus": []' in out

    assert kitchen.main("project", "close", "other") == (
        0,
        f"already closed: other has been closed since {today()}, nothing changed\n",
    )

    code, said = kitchen.main("project", "open", "other")
    assert code == 0 and said.startswith("opened: other")
    assert "closed" not in table(kitchen, "other")
    assert not thread(kitchen, HOME_2).get("archived")
    assert thread(kitchen, CREW_2)["archived"]
    assert tasks(kitchen) == {"task-on": True, "task-off": False, "task-demo": True}
    assert not (two.state / project.RECORD).exists()
    assert kitchen.main("project", "open", "other") == (
        0,
        "already open: other is open, nothing changed\n",
    )

    kitchen.poll(NOW + timedelta(minutes=10))
    assert [one["title"] for one in kitchen.t3.launches] == ["crew: alpha", "crew: beta"]
    kitchen.poll(NOW + timedelta(minutes=30))
    assert two.wakes.said == [
        "question 1: drop the old branch, it holds (deletes data) for your answer"
    ]


def test_close_refuses_while_the_project_has_work_out_and_names_each(kitchen, two):
    kitchen.t3.thread("beta", "running", project=two.project, title="crew: beta")
    kitchen.t3.thread("pr-9", "running", project=two.project, title="review: beta")
    kitchen.t3.thread("talk", "running", project=two.project, title="a chat")
    code, said = kitchen.main("project", "close", "other")
    assert code == 1
    assert said.startswith("refused: other still has work out: crew thread mcp:thread-")
    assert said.count("thread mcp:") == 2 and "a chat" not in said
    assert "closed" not in table(kitchen, "other")
    assert not (two.state / project.RECORD).exists()
    assert not any(one.get("archived") for one in kitchen.t3.threads)
    assert tasks(kitchen)["task-on"]


class Killed(BaseException):
    """The run stopped here, as a kill would stop it."""


def cut_after(monkeypatch, steps):
    """Stop the run of `close` or `open` right after its `steps`-th change: to T3 Code (a thread
    put away or back, a task switched) or to a file."""
    done = [0]

    def after(real):
        def step(*args, **kwargs):
            made = real(*args, **kwargs)
            done[0] += 1
            if done[0] == steps:
                raise Killed
            return made

        return step

    real_call = t3.Client.call

    def call(self, tool, arguments):
        if tool in ("t3_thread_organize", "schedule_task"):
            return after(real_call)(self, tool, arguments)
        return real_call(self, tool, arguments)

    monkeypatch.setattr(t3.Client, "call", call)
    monkeypatch.setattr(project, "_private", after(project._private))
    monkeypatch.setattr(jbus, "write_json", after(jbus.write_json))


def run(kitchen, verb, steps):
    """Run `verb` cut off after `steps` changes, then run it again whole."""
    with kitchen.monkeypatch.context() as patched:
        cut_after(patched, steps)
        with pytest.raises(Killed):
            project.close(kitchen.config_dir / "config.toml", "other") if verb == "close" else (
                project.reopen(kitchen.config_dir / "config.toml", "other")
            )
    return kitchen.main("project", verb, "other")


CLOSE_STEPS, OPEN_STEPS = 7, 4
"""`close` of `other` makes seven changes: its record, one task off, two threads archived, the
record with its day, the copy of the config and the config. `open` makes four before the record's
delete: one task on, one home back, the copy and the config."""


@pytest.mark.parametrize("steps", range(1, CLOSE_STEPS + 1))
def test_a_close_cut_off_after_any_step_is_finished_by_the_next_run(kitchen, two, steps):
    code, _ = run(kitchen, "close", steps)
    assert code == 0
    assert table(kitchen, "other")["closed"] == today()
    assert [thread(kitchen, one)["archived"] for one in (HOME_2, CREW_2)] == [True, True]
    assert tasks(kitchen) == {"task-on": False, "task-off": False, "task-demo": True}
    record = jbus.read_json(two.state / project.RECORD, {})
    assert record == {
        "closed": today(),
        "homes": [HOME_2],
        "tasks": ["task-on"],
        "threads": sorted([HOME_2, CREW_2]),
    }


@pytest.mark.parametrize("steps", range(1, OPEN_STEPS + 1))
def test_an_open_cut_off_after_any_step_is_finished_by_the_next_run(kitchen, two, steps):
    assert kitchen.main("project", "close", "other")[0] == 0
    code, _ = run(kitchen, "open", steps)
    assert code == 0
    assert "closed" not in table(kitchen, "other")
    assert [thread(kitchen, one)["archived"] for one in (HOME_2, CREW_2)] == [False, True]
    assert tasks(kitchen) == {"task-on": True, "task-off": False, "task-demo": True}
    assert not (two.state / project.RECORD).exists()


def test_the_view_shows_a_closed_project_as_closed_and_keeps_its_questions_out(kitchen, two):
    kitchen.config(max_running=4, dispatch=False)
    kitchen.poll()
    sources = view_state.Sources(kitchen.state_dir, kitchen.root / "home")

    def stack():
        return view_state.stack(sources, NOW, lambda _: {}, names=["demo", "other"])

    assert any(one["project"] == "other" for one in stack()["needs"])
    assert kitchen.main("project", "close", "other")[0] == 0
    shown = stack()
    assert {one["name"]: one["closed"] for one in shown["projects"]} == {
        "demo": None,
        "other": today(),
    }
    assert all(one["project"] != "other" for one in shown["needs"])
