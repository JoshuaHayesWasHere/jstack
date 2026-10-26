"""`jbus flow asks` counts the owner's status asks per job and per day, from T3 Code's store.

The tests write a small store the way `test_jbus_flow_nudges` does and run the real command over
it in the kitchen of `test_jbus_kitchen`. Each job of the jview-asks Report is asked once on the
first day, in a home, a crew or a scratch thread, and one message asks two jobs. Beside them are
messages that ask nothing: a nudge, an approval, new work that names a plan, a slash command,
a crew's report, and the home's own reply. On the second day the same `$ketchup` is typed to two
homes, which counts twice, and a word jbus carried counts once with the message he typed, and
once alone.
"""

import json
from datetime import UTC, datetime

import pytest

from jbus import word
from jbus.flow import asks
from test_jbus_flow_nudges import write
from test_jbus_kitchen import Kitchen

T = datetime(2026, 10, 22, 16, 0, tzinfo=UTC)
DAY = 24 * 60
ROOT, FLOW, CREW, SCRATCH = "mcp:root", "mcp:flow", "mcp:crew", "mcp:scratch"
THREADS = {ROOT: "home: demo", FLOW: "home: demo flow", CREW: "crew: demo", SCRATCH: "This week"}


def carried(words):
    return word.MESSAGE.format(
        by="owner", at="2026-10-23 12:05 EDT", id="0123456789ab", words=words
    )


MESSAGES = [
    (0, ROOT, "user", "user", "we seem stalled. why?"),
    (1, ROOT, "assistant", "agent", "Main is red: are we stalled? No, a check runs."),
    (2, ROOT, "user", "user", "provide me with a visual that shows where we are in the queue"),
    (3, ROOT, "user", "user", "does anything need me?"),
    (4, ROOT, "user", "user", "why is machine load at 100??? what is running??"),
    (5, CREW, "user", "user", "have the wide view changes landed?"),
    (6, ROOT, "user", "user", "why is this being asked? I have never seen it"),
    (7, FLOW, "user", "user", "and how close are we to it?"),
    (8, ROOT, "user", "user", "$ketchup provide a visual overview of the work in the child homes"),
    (9, SCRATCH, "user", "user", "How much work has been done today?"),
    (10, ROOT, "user", "user", "the stack is flowing - how can we monitor it in jview?"),
    (11, ROOT, "user", "user", "Keep moving."),
    (12, ROOT, "user", "user", "Approved, go"),
    (13, ROOT, "user", "user", "we need a plan for the docs. write it up."),
    (14, ROOT, "user", "user", "/crew demo-status"),
    (15, CREW, "user", "agent", "Background task completed: status? the crew is stuck."),
    (DAY, ROOT, "user", "user", "$ketchup"),
    (DAY + 1, FLOW, "user", "user", "$ketchup"),
    (DAY + 5, FLOW, "user", "user", "Status? Why do we seem stalled??"),
    (DAY + 6, ROOT, "user", "agent", carried("Status? Why do we seem stalled??")),
    (DAY + 30, ROOT, "user", "agent", carried("and what is the status of the mac work?")),
]
WINDOW = ("2026-10-22T12:00Z", "2026-10-24T12:00Z")


@pytest.fixture
def store(tmp_path):
    return write(tmp_path / "statev2.sqlite", THREADS, MESSAGES, T)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    return Kitchen(tmp_path, monkeypatch)


def test_each_job_is_counted_per_day_and_what_asks_nothing_is_not(kitchen, store):
    before = store.read_bytes()
    code, out = kitchen.main("flow", "asks", *WINDOW, "--store", str(store))
    assert code == 0, out
    lines = out.splitlines()
    assert lines[:12] == [
        "2026-10-22T16:00Z\tJ1\thome: demo\twe seem stalled. why?",
        "2026-10-22T16:02Z\tJ2\thome: demo\tprovide me with a visual that shows where we are in "
        "the queue",
        "2026-10-22T16:03Z\tJ3\thome: demo\tdoes anything need me?",
        "2026-10-22T16:04Z\tJ4\thome: demo\twhy is machine load at 100??? what is running??",
        "2026-10-22T16:05Z\tJ5\tcrew: demo\thave the wide view changes landed?",
        "2026-10-22T16:06Z\tJ6\thome: demo\twhy is this being asked? I have never seen it",
        "2026-10-22T16:07Z\tJ7\thome: demo flow\tand how close are we to it?",
        "2026-10-22T16:08Z\tJ2,J8\thome: demo\t$ketchup provide a visual overview of the work in "
        "the child homes",
        "2026-10-22T16:09Z\tJ9\tThis week\tHow much work has been done today?",
        "2026-10-22T16:10Z\tJ1,VW\thome: demo\tthe stack is flowing - how can we monitor it in "
        "jview?",
        "2026-10-23T16:00Z\tJ2\thome: demo\t$ketchup",
        "2026-10-23T16:01Z\tJ2\thome: demo flow\t$ketchup",
    ]
    assert lines[12:] == [
        "2026-10-23T16:05Z\tJ1,J2\thome: demo flow\tStatus? Why do we seem stalled??",
        "2026-10-23T16:30Z\tJ5\thome: demo\tand what is the status of the mac work?",
        "",
        "day\tJ1\tJ2\tJ3\tJ4\tJ5\tJ6\tJ7\tJ8\tJ9\tVW\tasks",
        "2026-10-22\t2\t2\t1\t1\t1\t1\t1\t1\t1\t1\t10",
        "2026-10-23\t1\t3\t0\t0\t1\t0\t0\t0\t0\t0\t4",
        "all\t3\t5\t1\t1\t2\t1\t1\t1\t1\t1\t14",
        "messages 17, asks 14",
    ]
    assert store.read_bytes() == before


def test_json_gives_the_same_counts_and_one_title_narrows_them(kitchen, store):
    code, out = kitchen.main(
        "flow", "asks", *WINDOW, "--store", str(store), "--title", "home: demo flow", "--json"
    )
    assert code == 0, out
    said = json.loads(out)
    assert (said["messages"], said["asks"]) == (3, 3)
    assert said["days"] == {
        "2026-10-22": {"asks": 1, "jobs": dict.fromkeys(said["jobs"], 0) | {"J7": 1}},
        "2026-10-23": {"asks": 2, "jobs": dict.fromkeys(said["jobs"], 0) | {"J1": 1, "J2": 2}},
    }
    assert said["list"][0] == {
        "at": "2026-10-22T16:07:00+00:00",
        "jobs": ["J7"],
        "home": "home: demo flow",
        "thread": FLOW,
        "first": "and how close are we to it?",
    }
    code, out = kitchen.main("flow", "--json", "asks", *WINDOW, "--store", str(store))
    assert code == 0, out
    assert json.loads(out)["asks"] == 14


def test_the_help_gives_the_definition_and_flow_s_window_flags_are_refused(kitchen, store):
    code, out = kitchen.main("flow", "asks", "--help")
    assert code == 0
    assert asks.DEFINITION in " ".join(out.split())
    code, out = kitchen.main("flow", "--rows", "asks", *WINDOW, "--store", str(store))
    assert code == 1 and out.startswith("refused: --rows is jbus flow's, not jbus flow asks'"), out


def test_a_missing_store_and_a_window_that_ends_first_are_refused(kitchen, store, tmp_path):
    code, out = kitchen.main("flow", "asks", *WINDOW, "--store", str(tmp_path / "gone"))
    assert code == 1 and out.startswith("refused:")
    code, out = kitchen.main("flow", "asks", *reversed(WINDOW), "--store", str(store))
    assert code == 1 and out.startswith("refused:")


@pytest.mark.parametrize(
    "text", ["Status?", "Looks good. Status?", "Ok.\nStatus?", "Thanks. And now?"]
)
def test_a_short_status_question_asks_where_we_are_after_another_sentence_too(text):
    assert asks.jobs(text) == ("J2",)


def test_what_needs_to_be_done_asks_what_is_left_and_not_what_needs_the_owner():
    assert asks.jobs("what has been done? what needs to be done?") == ("J2",)
