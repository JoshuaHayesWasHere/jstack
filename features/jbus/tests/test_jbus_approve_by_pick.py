"""The user's answer to a question box in a T3 Code thread is a basis for `queue approve`.

`--pick <thread id>/<item id>` names a thread's `user_input_request` item, the box that Claude
Code's AskUserQuestion shows. jbus reads the item from T3 Code's server, and who answered it,
when and with what from T3 Code's own store, and approves each row that a picked label names.
Every test runs the real command against the faked server of `test_jbus_kitchen` and a small
store laid out as T3 Code lays out its own, under `T3CODE_HOME`.
"""

import json
import sqlite3
import urllib.parse

import pytest

from test_jbus_approval import cell, go
from test_jbus_kitchen import RAN, SESSION, bound
from test_jbus_queue import add, brief, rows, sha12

HOME = "mcp:a-home"
REQUEST = "runtime-request:provider:claudeAgent:native-request:toolu_01:e9a1"
ITEM = f"turn-item:runtime-request:{urllib.parse.quote(REQUEST, safe='')}"
REF = f"{HOME}/{ITEM}"
QUESTION = "Which of the fixes should I queue now?"
LABELS = ["alpha (S)", "beta (S)", "gamma (M)"]
ANSWERED_AT = "2026-10-12 10:30 ET"
APP = "00000000-0000-4000-8000-000000000001"
AGENT = "mcp:an-agents-command"


def box(labels=LABELS):
    return json.dumps(
        [
            {
                "id": QUESTION,
                "header": "Queue fixes",
                "question": QUESTION,
                "options": [{"label": one, "description": "why"} for one in labels],
                "multiSelect": True,
            }
        ]
    )


def shown(kitchen, kind="user_input_request", labels=LABELS):
    """Put the box in the home's thread as T3 Code's server gives it by its item id."""
    kitchen.t3.says(
        HOME,
        ITEM,
        box(labels),
        itemId=ITEM,
        messageId=None,
        createdBy=None,
        creationSource=None,
        type=kind,
        status="completed",
    )


def stored(tmp_path, monkeypatch, answers, status="resolved", commands=(APP,)):
    """Write T3 Code's store with the request and the commands that resolved it, as T3 Code
    keeps them, and point `T3CODE_HOME` at it."""
    home = tmp_path / "t3"
    (home / "userdata").mkdir(parents=True)
    db = sqlite3.connect(home / "userdata" / "statev2.sqlite")
    db.executescript(
        """
        create table orchestration_v2_projection_runtime_requests (
            runtime_request_id text primary key, thread_id text, node_id text,
            provider_turn_id text, kind text, status text, created_at text, resolved_at text,
            payload_json text);
        create table orchestration_events (
            sequence integer primary key autoincrement, event_id text, aggregate_kind text,
            stream_id text, stream_version integer, event_type text, occurred_at text,
            command_id text, causation_event_id text, correlation_id text, actor_kind text,
            payload_json text, metadata_json text);
        create table orchestration_command_receipts (
            command_id text primary key, aggregate_kind text, aggregate_id text,
            accepted_at text, result_sequence integer, status text, error text,
            command_type text);
        """
    )
    resolved = "2026-10-12T14:30:00.000Z" if status == "resolved" else None
    payload = {"id": REQUEST, "kind": "user_input", "status": status}
    if status == "resolved":
        payload |= {"resolvedAt": resolved, "answers": answers}
    db.execute(
        "insert into orchestration_v2_projection_runtime_requests values (?,?,?,?,?,?,?,?,?)",
        (
            REQUEST,
            HOME,
            "node",
            "turn",
            "user_input",
            status,
            "2026-10-12T14:00:00Z",
            resolved,
            json.dumps(payload),
        ),
    )
    for number, command in enumerate(commands):
        db.execute(
            "insert into orchestration_events (event_id, aggregate_kind, stream_id,"
            " stream_version, event_type, occurred_at, command_id, actor_kind, payload_json,"
            " metadata_json) values (?,?,?,?,?,?,?,?,?,?)",
            (
                f"event-{number}",
                "thread",
                HOME,
                number,
                "runtime-request.updated",
                resolved,
                command,
                "server",
                json.dumps(payload),
                "{}",
            ),
        )
        db.execute(
            "insert into orchestration_command_receipts values (?,?,?,?,?,?,?,?)",
            (
                command,
                "thread",
                HOME,
                resolved,
                number,
                "accepted",
                None,
                "runtime-request.respond",
            ),
        )
    db.commit()
    db.close()
    monkeypatch.setenv("T3CODE_HOME", str(home))


def line(label):
    return (
        f'your pick in a question box, {ANSWERED_AT}, in home: demo: "{label}", for "{QUESTION}"; '
        f"run {RAN} by the demo home"
    )


def test_an_approval_by_a_pick_holds_the_label_that_names_the_row(kitchen, tmp_path, monkeypatch):
    shown(kitchen)
    stored(tmp_path, monkeypatch, {QUESTION: ["alpha (S)", "gamma (M)"]})
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--pick", REF)[0] == 0
    row = rows(kitchen)["alpha"]
    assert row["approval"] == {
        "basis": "pick",
        "ref": REF,
        "words": f'"alpha (S)", for "{QUESTION}"',
        "said_at": ANSWERED_AT,
        "said_in": "home: demo",
        "checked": True,
        "ran_by": {"session": SESSION, "directory": str(kitchen.checkout)},
        "ran_at": RAN,
        **bound(kitchen, "alpha"),
    }
    assert (row["approved"], cell(kitchen, "alpha")) == (line("alpha (S)"), line("alpha (S)"))
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_one_answer_of_three_picks_is_the_go_for_the_three_rows(kitchen, tmp_path, monkeypatch):
    shown(kitchen)
    stored(tmp_path, monkeypatch, {QUESTION: LABELS})
    for slug in ("alpha", "beta", "gamma"):
        add(kitchen, slug, approve=False)
    batch = "".join(
        f"approve {slug} --pick {REF} --sha {sha12(brief(slug))}\n"
        for slug in ("alpha", "beta", "gamma")
    )
    code, said = kitchen.main("queue", "apply", stdin=batch)
    assert code == 0, said
    assert {slug: row["approved"] for slug, row in rows(kitchen).items()} == {
        "alpha": line("alpha (S)"),
        "beta": line("beta (S)"),
        "gamma": line("gamma (M)"),
    }
    assert {row["approval"]["ref"] for row in rows(kitchen).values()} == {REF}


def test_a_pick_approves_each_row_it_names_one_command_at_a_time(kitchen, tmp_path, monkeypatch):
    shown(kitchen)
    stored(tmp_path, monkeypatch, {QUESTION: LABELS})
    for slug in ("alpha", "beta"):
        add(kitchen, slug, approve=False)
        assert go(kitchen, slug, "--pick", REF)[0] == 0
    assert [row["approval"]["words"] for row in rows(kitchen).values()] == [
        f'"alpha (S)", for "{QUESTION}"',
        f'"beta (S)", for "{QUESTION}"',
    ]


@pytest.mark.parametrize(
    "answers, status, commands, why",
    [
        (
            {QUESTION: ["beta (S)"]},
            "resolved",
            (APP,),
            f'the pick {REF} does not name alpha: it picked "beta (S)"',
        ),
        (
            {QUESTION: "go on alpha"},
            "resolved",
            (APP,),
            f"the pick {REF} does not name alpha: it picked no label",
        ),
        ({}, "pending", (), f"question box {REF} is not answered: T3 Code has it pending"),
        (
            {QUESTION: "alpha (S)"},
            "resolved",
            (AGENT,),
            f"question box {REF} is not user's own answer: an agent answered it through T3 "
            f"Code's MCP server (command {AGENT})",
        ),
        (
            {QUESTION: ["alpha (S)"]},
            "resolved",
            (APP, AGENT),
            f"question box {REF} is not user's own answer: an agent answered it through T3 "
            f"Code's MCP server (command {AGENT})",
        ),
        (
            {QUESTION: ["alpha (S)"]},
            "resolved",
            ("cli:a-command",),
            f"question box {REF} is not user's own answer: command cli:a-command answered it, "
            "and it is not T3 Code's app",
        ),
        (
            {QUESTION: ["alpha (S)"]},
            "resolved",
            (),
            f"question box {REF} is not user's own answer: T3 Code's store holds no command "
            "that answered it",
        ),
    ],
)
def test_a_pick_that_is_not_the_users_go_for_the_row_approves_nothing(
    kitchen, tmp_path, monkeypatch, answers, status, commands, why
):
    shown(kitchen)
    stored(tmp_path, monkeypatch, answers, status, commands)
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--pick", REF) == (1, f"refused: {why}\n")
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_a_label_names_a_slug_only_as_a_word_of_its_own(kitchen, tmp_path, monkeypatch):
    shown(kitchen, labels=["alpha-two (S)"])
    stored(tmp_path, monkeypatch, {QUESTION: ["alpha-two (S)"]})
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--pick", REF) == (
        1,
        f'refused: the pick {REF} does not name alpha: it picked "alpha-two (S)"\n',
    )


def test_an_item_that_is_not_a_question_box_approves_nothing(kitchen, tmp_path, monkeypatch):
    shown(kitchen, kind="user_message")
    stored(tmp_path, monkeypatch, {QUESTION: ["alpha (S)"]})
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--pick", REF) == (
        1,
        f"refused: item {REF} is a user_message, not a question box\n",
    )


@pytest.mark.parametrize(
    "ref, why",
    [
        (HOME, f'--pick is "<thread id>/turn-item:runtime-request:<request>", not {HOME}'),
        (
            f"{HOME}/turn-item:message:a-message",
            '--pick is "<thread id>/turn-item:runtime-request:<request>", not '
            f"{HOME}/turn-item:message:a-message",
        ),
    ],
)
def test_a_pick_that_names_no_question_box_approves_nothing(kitchen, ref, why):
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--pick", ref) == (1, f"refused: {why}\n")


def test_a_store_that_is_not_there_approves_nothing(kitchen, tmp_path, monkeypatch):
    shown(kitchen)
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path / "none"))
    add(kitchen, "alpha", approve=False)
    where = tmp_path / "none" / "userdata" / "statev2.sqlite"
    assert go(kitchen, "alpha", "--pick", REF) == (
        1,
        f"refused: T3 Code keeps no store at {where}\n",
    )


def test_a_pick_is_the_users_own_word_for_a_door(kitchen, tmp_path, monkeypatch):
    shown(kitchen)
    stored(tmp_path, monkeypatch, {QUESTION: ["alpha (S)"]})
    held = brief("alpha", "Holds: publishes\n")
    add(kitchen, "alpha", approve=False, text=held)
    code, said = kitchen.main("queue", "approve", "alpha", "--pick", REF, "--sha", sha12(held))
    assert (code, rows(kitchen)["alpha"]["approved"]) == (0, ""), said
    assert said.startswith("gated alpha: its brief holds for publishes")
    code, said = kitchen.main(
        "--as",
        "user",
        "queue",
        "approve",
        "alpha",
        "--pick",
        REF,
        "--sha",
        sha12(held),
    )
    assert code == 0, said
    assert rows(kitchen)["alpha"]["approved"] == line("alpha (S)")
