"""A feature declares the step it adds to a pass, and `first_half` runs each slot's steps by
rank. Run as `tests/test_jbus_guarded_ask.py` runs: the real pass, against the fakes.

`ORDER` is the order `first_half` called its tellers in before any was a step, written out
once, here, with each step added since in its slot by rank. `BEFORE` is what one pass's
first half called, and the events the pass queued, over the fixtures the other tests build,
recorded on the code before the move. Two calls moved with it, and `moved` moves them:
`questions.closed_in_files` runs in the first slot, before `merge.merge` and `queue.load`,
which touch no question; `watch.gone`, which only reads, runs after the tellers slot, beside
`expedite.tell`.
"""

import importlib
import re
import sys
from datetime import timedelta

import pytest

import jbus
from jbus import (
    cli,
    dispatch,
    expedite,
    mainmoved,
    merge,
    mirror,
    questions,
    queue,
    rebase,
    remarks,
    stall,
    threads,
    verbs,
    watch,
    word,
)
from test_jbus_expedite import NO_FIXED, URL, Short
from test_jbus_fresh_head import Due
from test_jbus_kitchen import NOW, PROJECT
from test_jbus_questions import AT, answer, ask
from test_jbus_remarks import OWNER, one
from test_jbus_unlock import CHANGED
from test_jbus_verbs import fresh

ORDER = [
    "before-watch 10 word.deliver",
    "before-watch 20 questions.closed_in_files",
    "before-watch 30 questions.silent",
    "tellers 10 mirror.scan (sight)",
    "tellers 15 noticed.scan (sight)",
    "tellers 20 questions.tell (sight, client)",
    "tellers 30 questions.propose (sight, client)",
    "tellers 40 watch.watch (client, world)",
    "tellers 50 threads.tie (client, world)",
    "tellers 55 failover.failover (client, world)",
    "tellers 60 threads.resume (client, world)",
    "tellers 70 threads.merged (client, world)",
    "tellers 80 threads.out and stall.hung (client, world)",
    "tellers 100 rebase.tell (client, world)",
    "tellers 110 stall.guarded (client, world)",
    "after-expedite 10 mainmoved.tell (client, world)",
    "after-expedite 20 remarks.tell (client, world)",
    "after-expedite 30 rebase.github (client, world)",
]
JMERGE = f"wait 7 {URL}: {NO_FIXED}"

BEFORE = {
    "short": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read watch.watch threads.tie threads.resume threads.merged "
        "threads.out stall.hung watch.gone rebase.tell stall.guarded expedite.tell "
        "mainmoved.tell remarks.tell dispatch.turns",
        [("jmerge", JMERGE)],
    ),
    "question": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read watch.watch threads.tie threads.resume threads.merged "
        "threads.out stall.hung rebase.tell stall.guarded expedite.tell mainmoved.tell "
        "remarks.tell dispatch.turns",
        [
            ("note", "note alpha: told its thread the answer to question 1"),
            ("waiting", "waiting demo: 0 wait on user, 0 new, 1 gone"),
        ],
    ),
    "word": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read watch.watch threads.tie threads.resume threads.merged "
        "threads.out stall.hung rebase.tell stall.guarded expedite.tell mainmoved.tell "
        "remarks.tell dispatch.turns",
        [("word", "word demo: sent to mcp:a-home")],
    ),
    "main moved": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read watch.watch threads.tie threads.resume threads.merged "
        "threads.out stall.hung watch.gone rebase.tell stall.guarded expedite.tell "
        "mainmoved.tell remarks.tell dispatch.turns",
        [
            ("result", "result alpha: done"),
            ("review", "review alpha: findings"),
            ("mainmoved", "mainmoved alpha: told the crew (#7, main <head>)"),
            ("queue", "queue demo: the table changed"),
        ],
    ),
    "stale": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read watch.watch threads.tie threads.resume threads.merged "
        "threads.out stall.hung watch.gone rebase.tell stall.guarded expedite.tell "
        "mainmoved.tell remarks.tell dispatch.turns",
        [
            ("jmerge", f"wait 7 {URL}: {CHANGED}: it needs a rebase"),
            ("result", "result alpha: done"),
            ("review", "review alpha: findings"),
            ("rebase", "rebase alpha: told the crew (#7, <head>)"),
            ("queue", "queue demo: the table changed"),
        ],
    ),
    "t3 down": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read expedite.told",
        [("jmerge", JMERGE), ("condition", "condition demo: T3 Code could not be asked")],
    ),
    "signed out": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan expedite.told",
        [
            ("jmerge", JMERGE),
            ("condition", "condition demo: T3 Code could not be asked"),
            (
                "waiting-on-user",
                "waiting-on-user demo: run jbus t3 login · unblocks none · since 12:00 ET",
            ),
            ("waiting", "waiting demo: 1 wait on user, 1 new (config demo), 0 gone"),
        ],
    ),
    "blind": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look expedite.told",
        [("jmerge", JMERGE), ("condition", "condition demo: removed.json does not parse")],
    ),
    "words.json": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read watch.watch threads.tie threads.resume threads.merged "
        "threads.out stall.hung watch.gone rebase.tell stall.guarded expedite.tell "
        "mainmoved.tell remarks.tell dispatch.turns",
        [("condition", "condition demo: words.json does not parse"), ("jmerge", JMERGE)],
    ),
    "questions.json": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read watch.watch threads.tie threads.resume threads.merged "
        "threads.out stall.hung watch.gone rebase.tell stall.guarded expedite.tell "
        "mainmoved.tell remarks.tell dispatch.turns",
        [("jmerge", JMERGE), ("condition", "condition demo: questions.json does not parse")],
    ),
    "queue.json": (
        "word.deliver merge.merge queue.load questions.closed_in_files questions.read "
        "watch.look mirror.scan questions.tell questions.read questions.propose "
        "questions.read watch.watch threads.tie threads.resume threads.merged "
        "threads.out stall.hung rebase.tell stall.guarded expedite.tell mainmoved.tell "
        "remarks.tell",
        [("jmerge", JMERGE), ("condition", "condition demo: queue.json does not parse")],
    ),
}

CALLED = (
    (word, "deliver"),
    (merge, "merge"),
    (queue, "load"),
    (questions, "closed_in_files"),
    (questions, "read"),
    (watch, "look"),
    (mirror, "scan"),
    (questions, "tell"),
    (questions, "propose"),
    (watch, "watch"),
    (threads, "tie"),
    (threads, "resume"),
    (threads, "merged"),
    (threads, "out"),
    (stall, "hung"),
    (watch, "gone"),
    (rebase, "tell"),
    (stall, "guarded"),
    (expedite, "tell"),
    (expedite, "told"),
    (mainmoved, "tell"),
    (remarks, "tell"),
    (dispatch, "turns"),
)


def moved(before):
    """The calls recorded before the move, with the two that moved where they are now."""
    calls = before.split()
    calls.remove("questions.closed_in_files")
    calls.insert(calls.index("word.deliver") + 1, "questions.closed_in_files")
    if "watch.gone" in calls:
        calls.remove("watch.gone")
        calls.insert(calls.index("stall.guarded") + 1, "watch.gone")
    return calls


def traced(kitchen, monkeypatch, *more):
    """One pass, and what its first half called, in order, with the events it queued."""
    calls, inside = [], []
    for module, name in (*CALLED, *more):
        real = getattr(module, name)

        def spy(*args, real=real, called=f"{module.__name__[5:]}.{name}", **kwargs):
            if inside:
                calls.append(called)
            return real(*args, **kwargs)

        monkeypatch.setattr(module, name, spy)
    first = cli.first_half

    def half(*args):
        inside.append(True)
        try:
            return first(*args)
        finally:
            inside.clear()

    monkeypatch.setattr(cli, "first_half", half)
    kitchen.forget()
    kitchen.poll(NOW + timedelta(hours=1))
    events = [(e["event"], re.sub("[0-9a-f]{12}", "<head>", e["line"])) for e in kitchen.events()]
    return calls, events


def short(kitchen):
    made = Short(kitchen)
    made.out(NO_FIXED)
    kitchen.set("repo.json", {"owner": {"login": OWNER}})
    kitchen.set("remarks.json", {"issues/7/comments": [one(1, OWNER, "please rename it")]})


def question(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew-alpha\n")
    kitchen.quiet()
    ask(kitchen)
    kitchen.poll()
    answer(kitchen, 1, "coffee")


def worded(kitchen):
    assert kitchen.main("word", "--to", "demo", "--by", "user", "--at", AT, "go", "on")[0] == 0
    (kitchen.home / "home-id").write_text("mcp:a-home\n")


def main_moved(kitchen):
    due = Due(kitchen, "mainmoved")
    due.at(due.head)


def stale(kitchen):
    due = Due(kitchen, "rebase")
    due.at(due.head)


def t3_down(kitchen):
    short(kitchen)
    kitchen.t3.down.add(PROJECT)


def signed_out(kitchen):
    short(kitchen)
    (kitchen.config_dir / "t3.json").unlink()


def unparsed(name):
    def broken(kitchen):
        short(kitchen)
        (kitchen.state / name).write_text("{")

    return broken


FIXTURES = {
    "short": short,
    "question": question,
    "word": worded,
    "main moved": main_moved,
    "stale": stale,
    "t3 down": t3_down,
    "signed out": signed_out,
    "blind": unparsed("removed.json"),
    "words.json": unparsed("words.json"),
    "questions.json": unparsed("questions.json"),
    "queue.json": unparsed("queue.json"),
}


def test_jbus_steps_prints_the_order_the_tellers_ran_in_before_they_were_steps(kitchen):
    code, out = kitchen.main("steps")
    assert (code, out.splitlines()) == (0, ORDER)


@pytest.mark.parametrize("fixture", FIXTURES)
def test_a_pass_calls_what_it_called_and_says_what_it_said_before_the_steps(
    kitchen, monkeypatch, fixture
):
    FIXTURES[fixture](kitchen)
    calls, events = BEFORE[fixture]
    assert traced(kitchen, monkeypatch) == (moved(calls), events)


MADE_UP = """
from jbus import verbs


def step(half):
    half.run.say(f"made up: {len(half.out)} out")


STEPS = (verbs.Step("tellers", 85, "madeup.step", lambda half: step(half), ("client", "world")),)
"""


@pytest.fixture
def made_up(tmp_path, monkeypatch):
    """A module of jbus that no file of jbus names, with one step, between two of the
    tellers."""
    (tmp_path / "madeup.py").write_text(MADE_UP)
    monkeypatch.setattr(jbus, "__path__", [*jbus.__path__, str(tmp_path)])
    yield importlib.import_module("jbus.madeup")
    sys.modules.pop("jbus.madeup", None)


def test_a_new_module_s_step_runs_in_its_place_with_no_line_in_cli(kitchen, monkeypatch, made_up):
    monkeypatch.setattr(cli, "RANKED", verbs.ranked(jbus.__path__))
    short(kitchen)
    calls, events = traced(kitchen, monkeypatch, (made_up, "step"))
    expected = moved(BEFORE["short"][0])
    expected.insert(expected.index("stall.hung") + 1, "madeup.step")
    assert (calls, events) == (expected, BEFORE["short"][1])


def test_a_new_module_s_step_is_printed_in_its_place(tmp_path):
    (tmp_path / "jbus").mkdir()
    ran = fresh(tmp_path / "jbus", "from jbus import cli\ncli.main(['steps'])", madeup=MADE_UP)
    assert ran.returncode == 0, ran.stderr
    at = ORDER.index("tellers 100 rebase.tell (client, world)")
    assert ran.stdout.splitlines() == [
        *ORDER[:at],
        "tellers 85 madeup.step (client, world)",
        *ORDER[at:],
    ]


def test_a_rank_two_modules_declare_in_one_slot_fails_at_import_and_names_both(tmp_path):
    again = 'from jbus import verbs\nSTEPS = (verbs.Step("tellers", 100, "again", print),)\n'
    ran = fresh(tmp_path, "import jbus.cli", again=again)
    assert ran.returncode != 0
    last = ran.stderr.splitlines()[-1]
    assert last == "ValueError: tellers 100 is declared in jbus.rebase and in jbus.again", (
        ran.stderr
    )


@pytest.mark.parametrize(
    ("slot", "needs", "says"),
    [
        ("later", (), "there is no slot later"),
        ("tellers", ("sight", "rows"), "tellers cannot supply rows"),
        ("before-watch", ("sight",), "before-watch cannot supply sight"),
        ("before-watch", ("client", "world"), "before-watch cannot supply world"),
    ],
    ids=["slot", "need", "sight the slot runs before", "world the slot runs before"],
)
def test_a_slot_there_is_not_or_a_need_its_slot_cannot_supply_fails_at_import(
    tmp_path, slot, needs, says
):
    odd = f'from jbus import verbs\nSTEPS = (verbs.Step({slot!r}, 5, "odd", print, {needs!r}),)\n'
    ran = fresh(tmp_path, "import jbus.cli", odd=odd)
    assert ran.returncode != 0
    assert ran.stderr.splitlines()[-1] == f"ValueError: odd in jbus.odd: {says}", ran.stderr


def test_a_step_of_the_first_slot_may_need_a_client(tmp_path):
    first = (
        "from jbus import verbs\n"
        'STEPS = (verbs.Step("before-watch", 5, "first", print, ("client",)),)\n'
    )
    (tmp_path / "jbus").mkdir()
    ran = fresh(tmp_path / "jbus", "from jbus import cli\ncli.main(['steps'])", first=first)
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.splitlines()[0] == "before-watch 5 first (client)"
