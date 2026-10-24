"""A feature declares the step it adds to a pass, and `first_half` and `second_half` run each slot's
steps by rank. Like `test_jbus_guarded_ask.py`, the tests run the real pass against the fakes.

`ORDER` is the order in which `first_half` called its tellers before any of them was a step. It is
written out once, here, with each step added since then placed in its slot by rank. `BEFORE` is what
the first half of one pass called, and the events the pass queued, over the fixtures the other tests
build. It was recorded on the code before the move. Two calls changed place in that move, and
`moved` puts them in their new places. `questions.closed_in_files` runs in the first slot, before
`merge.merge` and `queue.load`, which touch no question. `watch.gone`, which only reads, runs after
the tellers slot, beside `expedite.tell`.

`AFTER` is what the second half called, recorded the same way on the code before its calls were
steps. `EVENING` is the same for a pass late enough in the day to send the snapshot and to run the
sweep that is still owed. None of the second half's calls moved.
"""

import importlib
import re
import sys
from datetime import timedelta

import pytest

import jbus
from jbus import (
    alert,
    cli,
    dispatch,
    expedite,
    item,
    leftover,
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
    waiting,
    wake,
    watch,
    word,
    work,
)
from test_jbus_expedite import NO_FIXED, URL, Short
from test_jbus_fresh_head import Due
from test_jbus_kitchen import NOW, PROJECT
from test_jbus_questions import AT, answer, ask
from test_jbus_remarks import OWNER, one
from test_jbus_unlock import CHANGED
from test_jbus_verbs import fresh

ORDER = [
    "before-watch 6 health.first",
    "before-watch 7 item.settle",
    "before-watch 10 word.deliver",
    "before-watch 15 item.deliver (client)",
    "before-watch 20 questions.closed_in_files",
    "before-watch 30 questions.silent",
    "before-watch 40 slotwait.wake (client)",
    "before-watch 41 slotwait.wake_capped (client)",
    "tellers 10 mirror.scan (sight)",
    "tellers 15 noticed.scan (sight)",
    "tellers 20 questions.tell (sight, client)",
    "tellers 30 questions.propose (sight, client)",
    "tellers 40 watch.watch (client, world)",
    "tellers 45 sidered.owe (budget)",
    "tellers 50 threads.tie (client, world)",
    "tellers 55 failover.failover (client, world)",
    "tellers 60 threads.resume (client, world)",
    "tellers 70 threads.merged (client, world)",
    "tellers 80 threads.out and stall.hung (client, world)",
    "tellers 100 rebase.tell (client, world)",
    "tellers 110 stall.guarded (client, world)",
    "after-expedite 5 strays.stop (client, world)",
    "after-expedite 10 mainmoved.tell (client, world)",
    "after-expedite 20 remarks.tell (client, world)",
    "after-expedite 30 rebase.github (client, world)",
    "after-expedite 40 scouts.launch (client, world)",
    "derive 5 merge.shown",
    "derive 10 states.judged (sight)",
    "derive 20 states.derive (client, world, rows)",
    "after-derive 10 leftover.tell (client, world, rows)",
    "after-derive 20 stall.unclosed (client, world, rows)",
    "after-derive 30 states.unplaced (client, world, rows)",
    "after-derive 40 states.keep_work (rows)",
    "after-derive 50 item.follow (rows)",
    "after-derive 60 dispatch.overlaps (sight, budget)",
    "close 10 stall.tell",
    "close 20 waiting.keep (sight)",
    "close 25 blockers.raise_listed",
    "close 30 waiting.cadence",
    "close 40 chores.began (world)",
    "close 50 chores.daily",
    "close 60 chores.sweep (budget)",
    "close 70 packs.check",
    "close 80 cards.post",
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
            (
                "decision",
                "decision config: run jbus t3 login, jbus lacks a setup only you can give. "
                'Reply: "demo config: I set it up"',
            ),
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

DERIVED = "queue.derive queue.load leftover.tell stall.unclosed"
JUDGED = "work.write item.follow stall.tell waiting.keep questions.read waiting.cadence"
CLOSE = "Box.snapshot_due Box.sweep_owed alert.flush"
AFTER = {
    "short": f"{DERIVED} merge.unplaced {JUDGED} Box.began {CLOSE}",
    "question": f"{DERIVED} {JUDGED} Box.began {CLOSE}",
    "word": f"{DERIVED} {JUDGED} Box.began {CLOSE}",
    "main moved": f"{DERIVED} merge.unplaced {JUDGED} Box.began {CLOSE}",
    "stale": f"{DERIVED} merge.unplaced {JUDGED} Box.began {CLOSE}",
    "t3 down": f"{JUDGED} {CLOSE}",
    "signed out": f"{JUDGED.replace('questions.read', 'questions.read questions.read')} {CLOSE}",
    "blind": f"stall.tell waiting.cadence {CLOSE}",
    "words.json": f"{DERIVED} merge.unplaced {JUDGED} Box.began {CLOSE}",
    "questions.json": f"{DERIVED} merge.unplaced {JUDGED} Box.began {CLOSE}",
    "queue.json": f"stall.tell waiting.keep questions.read waiting.cadence Box.began {CLOSE}",
}
EVENING = (
    f"{DERIVED} merge.unplaced {JUDGED} Box.began Box.snapshot_due Box.snapshot_sent "
    "Box.prune Box.forget Box.sweep_owed merge.sweep Box.swept alert.flush"
)

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
SECOND = (
    (queue, "derive"),
    (leftover, "tell"),
    (stall, "unclosed"),
    (merge, "unplaced"),
    (work, "write"),
    (item, "follow"),
    (stall, "tell"),
    (waiting, "keep"),
    (waiting, "cadence"),
    (wake.Box, "began"),
    (wake.Box, "snapshot_due"),
    (wake.Box, "snapshot_sent"),
    (wake.Box, "prune"),
    (wake.Box, "forget"),
    (wake.Box, "sweep_owed"),
    (merge, "sweep"),
    (wake.Box, "swept"),
    (alert, "flush"),
)


def moved(before):
    """Return the calls recorded before the move, with the two that moved put where they are now."""
    calls = before.split()
    calls.remove("questions.closed_in_files")
    calls.insert(calls.index("word.deliver") + 1, "questions.closed_in_files")
    if "watch.gone" in calls:
        calls.remove("watch.gone")
        calls.insert(calls.index("stall.guarded") + 1, "watch.gone")
    return calls


def traced(kitchen, monkeypatch, *more, at=NOW + timedelta(hours=1)):
    """Run one pass, and return what each of its halves called, in order, and the events it
    queued."""
    calls = {"first_half": [], "second_half": []}
    inside = []
    for module, name in (*CALLED, *SECOND, *more):
        real = getattr(module, name)
        where = module.__qualname__ if isinstance(module, type) else module.__name__[5:]

        def spy(*args, real=real, called=f"{where}.{name}", **kwargs):
            if inside:
                calls[inside[-1]].append(called)
            return real(*args, **kwargs)

        monkeypatch.setattr(module, name, spy)
    for which in calls:
        real = getattr(cli, which)

        def half(*args, real=real, which=which):
            inside.append(which)
            try:
                return real(*args)
            finally:
                inside.clear()

        monkeypatch.setattr(cli, which, half)
    kitchen.forget()
    kitchen.poll(at)
    events = [(e["event"], re.sub("[0-9a-f]{12}", "<head>", e["line"])) for e in kitchen.events()]
    return calls["first_half"], calls["second_half"], events


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
    first, second, said = traced(kitchen, monkeypatch)
    assert (first, said) == (moved(calls), events)
    assert second == AFTER[fixture].split()


def test_the_evening_pass_snapshots_and_sweeps_in_the_order_it_did(kitchen, monkeypatch):
    short(kitchen)
    _, second, events = traced(kitchen, monkeypatch, at=NOW + timedelta(hours=7))
    assert (second, events) == (
        EVENING.split(),
        [("jmerge", JMERGE), ("snapshot", "snapshot demo: 2026-10-12")],
    )


MADE_UP = """
from jbus import verbs


def step(half):
    half.run.say(f"made up: {len(half.out)} out")


STEPS = (verbs.Step("tellers", 85, "madeup.step", lambda half: step(half), ("client", "world")),)
"""


@pytest.fixture
def made_up(tmp_path, monkeypatch):
    """Add a module of jbus that no file of jbus names, with one step between two of the tellers."""
    (tmp_path / "madeup.py").write_text(MADE_UP)
    monkeypatch.setattr(jbus, "__path__", [*jbus.__path__, str(tmp_path)])
    yield importlib.import_module("jbus.madeup")
    sys.modules.pop("jbus.madeup", None)


def test_a_new_module_s_step_runs_in_its_place_with_no_line_in_cli(kitchen, monkeypatch, made_up):
    monkeypatch.setattr(cli, "RANKED", verbs.ranked(jbus.__path__))
    short(kitchen)
    calls, _, events = traced(kitchen, monkeypatch, (made_up, "step"))
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


LATE = """
from jbus import verbs


def step(half):
    half.run.say(f"late: {len(half.table)} rows, {len(half.roots)} roots")


STEPS = (verbs.Step("close", 35, "late.step", lambda half: step(half), ("rows",)),)
"""


@pytest.fixture
def late(tmp_path, monkeypatch):
    """Add a module of jbus that no file of jbus names, with one step of the second half between
    `waiting.cadence` and `chores.began`."""
    (tmp_path / "late.py").write_text(LATE)
    monkeypatch.setattr(jbus, "__path__", [*jbus.__path__, str(tmp_path)])
    yield importlib.import_module("jbus.late")
    sys.modules.pop("jbus.late", None)


def test_a_new_module_s_second_half_step_runs_in_its_place_with_no_line_in_cli(
    kitchen, monkeypatch, late
):
    monkeypatch.setattr(cli, "RANKED", verbs.ranked(jbus.__path__))
    short(kitchen)
    first, second, events = traced(kitchen, monkeypatch, (late, "step"))
    expected = AFTER["short"].split()
    expected.insert(expected.index("waiting.cadence") + 1, "late.step")
    assert (first, second, events) == (moved(BEFORE["short"][0]), expected, BEFORE["short"][1])


def test_a_new_module_s_second_half_step_is_printed_in_its_place(tmp_path):
    (tmp_path / "jbus").mkdir()
    ran = fresh(tmp_path / "jbus", "from jbus import cli\ncli.main(['steps'])", late=LATE)
    assert ran.returncode == 0, ran.stderr
    at = ORDER.index("close 40 chores.began (world)")
    assert ran.stdout.splitlines() == [*ORDER[:at], "close 35 late.step (rows)", *ORDER[at:]]


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
