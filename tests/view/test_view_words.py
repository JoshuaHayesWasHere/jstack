"""The Words panel: his answers, his words and each approval, newest first."""

import json
import types

import jsettings
from jbus import questions, view, word
from test_jbus_kitchen import GATE as PIPED
from view.scene import ago, asks, iso, said_by_him, table


def test_the_words_panel_lists_his_answers_his_words_and_each_approval_newest_first(scene, served):
    number = said_by_him(scene)
    state = served.json("/state.json?project=demo")
    said = state["words"]
    typed = sorted(one["slug"] for one in table() if one["approved"] and one["slug"] != "tea-cups")
    assert [one["key"] for one in said] == [
        "word:f6e5d4c3b2a1",
        "approval:tea-cups",
        "word:a1b2c3d4e5f6",
        f"question:{number}",
        *(f"approval:{slug}" for slug in typed),
    ]
    entry = {one["key"]: one for one in said}
    answered = entry[f"question:{number}"]
    assert {key: answered[key] for key in ("question", "default", "words", "by", "at")} == {
        "question": "which pot?",
        "default": "the first one",
        "words": "coffee, please",
        "by": jsettings.load().user,
        "at": iso(ago(minutes=30)),
    }
    assert (answered["keeps"], answered["where"], answered["slug"]) == (False, "Sous Chef", "alpha")
    went, waits = entry["word:a1b2c3d4e5f6"], entry["word:f6e5d4c3b2a1"]
    assert (went["kept_at"], went["sent_at"]) == (iso(ago(minutes=19)), iso(ago(minutes=18)))
    assert (waits["sent_at"], waits["waits"]) == (None, "the home has no home-id")
    approved = entry["approval:tea-cups"]
    assert {key: approved[key] for key in ("basis", "rests", "words", "who", "ran_at")} == {
        "basis": "word",
        "rests": "word:a1b2c3d4e5f6",
        "words": "go ahead with the kettle",
        "who": "the elsewhere home",
        "ran_at": iso(ago(minutes=10)),
    }
    assert approved["said_at"] == iso(ago(minutes=20))
    before = entry["approval:tea-tray"]
    assert (before["line"], before["words"], before["at"]) == (
        "no record: approved before the record was kept",
        "2026-10-12 09:00 ET by user",
        None,
    )
    assert "approval:tea-kettle" not in entry
    assert [one for one in said if one.get("question") == "milk?"] == []
    assert served.json("/panel/words.json?project=demo")["data"] == {"words": said}
    names = {one["name"]: one["state"] for one in state["sources"]}
    assert (names["questions.json"], names["words.json"]) == ("ok", "ok")


def test_a_question_its_home_closed_in_gates_md_is_said_to_be_closed_by_its_home(scene, served):
    said_by_him(scene)
    number = asks(scene, "which lid?", slug="jam-lid")
    with open(scene.home / "gates.md", "a") as gates:
        gates.write(
            "\n"
            + PIPED.format(n=number, asked="which lid?", status="answered: red", slug="jam-lid")
        )
    questions.closed_in_files(types.SimpleNamespace(home=scene.home, state=scene.state))
    entry = {one["key"]: one for one in served.json("/state.json?project=demo")["words"]}
    closed = entry[f"question:{number}"]
    assert (closed["home"], closed["words"], closed["where"]) == (True, "answered: red", "")
    assert (closed["by"], closed["at"]) == ("", None)
    assert [one["home"] for one in entry.values() if one["kind"] == "answer"] == [False, True]


def test_an_answered_question_is_on_no_waiting_list_and_the_open_one_still_is(scene, served):
    number = said_by_him(scene)
    waiting = served.json("/state.json?project=demo")["waiting"]
    asked = [one["question"] for one in waiting if one["kind"] == "gate"]
    assert "milk?" in asked
    assert "which pot?" not in [one["question"] for one in waiting]
    assert str(number) not in [one["number"] for one in waiting]


def test_a_words_file_that_does_not_parse_is_said_and_the_rest_is_listed(scene, served):
    number = said_by_him(scene)
    (scene.state / word.NAME).write_text("{not json")
    state = served.json("/state.json?project=demo")
    assert {one["name"]: one["state"] for one in state["sources"]}["words.json"] == "unreadable"
    assert f"question:{number}" in [one["key"] for one in state["words"]]
    assert [one for one in state["words"] if one["kind"] == "word"] == []


def test_a_token_planted_in_his_answer_his_word_and_an_approval_is_in_no_answer(scene, served):
    planted = "ghp_" + "Wq4" * 12
    said_by_him(scene, answer=f"yes, and {planted}", sent=f"go with {planted}")
    paths = [
        "/",
        "/state.json?project=demo",
        "/digest.json",
        "/task/tea-cups/github?project=demo",
        *view.routes(),
    ]
    held = {}
    for path in paths:
        _, headers, body = served.ask(path)
        held[path] = planted in body + json.dumps(headers)
    assert held == dict.fromkeys(paths, False)
    said = json.dumps(served.json("/panel/words.json?project=demo"))
    assert said.count("[redacted]") == 3
