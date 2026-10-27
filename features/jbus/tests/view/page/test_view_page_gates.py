"""A gate on the page: opened, answered each of the three ways, and the write that follows."""

import html
import json
import re
import types

import pytest

import jsettings
from jbus import party, questions
from test_jbus_kitchen import GATE as PIPED
from view.page.browser import (
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    WORDS,
    browse,
    clean,
    gated,
    look,
)
from view.scene import NOW, Served, asks, et, kept, said_by_him

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


def test_a_question_its_home_closed_is_drawn_as_closed_by_its_home_and_not_as_his_answer(
    scene, tmp_path
):
    said_by_him(scene)
    number = asks(scene, "which lid?", slug="jam-lid")
    with open(scene.home / "gates.md", "a") as gates:
        gates.write(
            "\n"
            + PIPED.format(n=number, asked="which lid?", status="answered: red", slug="jam-lid")
        )
    questions.closed_in_files(types.SimpleNamespace(home=scene.home, state=scene.state))
    served = Served(scene)
    try:
        ran = browse(
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=3000",
            f"http://127.0.0.1:{served.port}/#/demo/words/question/{number}",
        )
    finally:
        served.close()
    drawer = ran.stdout.partition('id="drawer"')[2].partition("</dialog>")[0]
    hit = drawer.partition('<li class="hit">')[2].partition("</li>")[0]
    said = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", hit)))
    assert "which lid?" in said
    assert 'Closed by its home "answered: red"' in said
    assert "Your answer" not in said
    assert "not the default" not in said


ACCEPT = "[data-accept][aria-description^='Accepts the default']"
"""The gate's own Accept default in its row of Needs you, beside the rows to approve, which
accept inline too."""


def test_the_inline_accept_waits_ten_seconds_undo_stops_it_and_one_write_follows(scene, tmp_path):
    """A gate has a default and no hold, and the user accepts it from the queue. Undo within the
    10-second window sends nothing, a second accept sends one write after the window, and the
    page shows the server's sentence. At the start, nothing on the page or in the drawer has the
    focus. Each row of the list has its one action filled, and no more."""
    tea, _, _ = gated(scene)
    walk = ["look", f"tap:{ACCEPT}", "look", "tap:[data-undo]", *["look"] * 23]
    walk += [f"tap:{ACCEPT}", *["look"] * 23]
    seen = look(scene, tmp_path, walk=walk, at=4000 + 500 * len(walk), budget=40000)
    assert seen["errors"] == []
    before, started, counting, undone, *_ = seen["walked"]
    assert before["focus"] == ""
    assert started["acc"].startswith("Accepting the default in") and started["acc"].endswith("Undo")
    assert counting["acc"] and undone["acc"] == ""
    assert seen["walked"][2 + 1 + 23]["acc"] == ""
    assert seen["walked"][-1]["acc"] == ""
    assert [one["body"] for one in seen["writes"]] == [{"numbers": [tea]}]
    assert seen["walked"][-1]["nsaid"], "the server's sentence is on the page"
    rows = [one for one in seen["needs"]["now"] if one["seen"]]
    assert rows and all(sum(act["fill"] for act in one["acts"]) <= 1 for one in rows), "one each"


def test_an_accept_still_counting_is_dropped_when_the_route_leaves_its_project(scene, tmp_path):
    """Going to another project hides the queue and its Undo. So the countdown ends there,
    and no write follows."""
    gated(scene)
    walk = ["look", f"tap:{ACCEPT}", "hash:#/nowhere", *["look"] * 25]
    seen = look(scene, tmp_path, walk=walk, at=4000 + 500 * len(walk), budget=40000)
    assert seen["errors"] == []
    assert seen["writes"] == []


@pytest.mark.parametrize("screen", [DESK, PHONE])
def test_a_gate_is_opened_and_answered_each_of_the_three_ways(scene, tmp_path, screen):
    tea, milk, sugar = gated(scene)
    ways = [
        {"number": tea},
        {"number": milk, "option": 1},
        {"number": sugar, "words": "half a spoon"},
    ]
    seen = look(scene, tmp_path, budget=14000, screen=screen, gates={"ways": ways})
    clean(seen, screen)
    assert seen["words"] <= WORDS, seen["words"]
    assert [(one["path"], one["kind"]) for one in seen["writes"]] == [
        ("/answer?project=demo", "application/json")
    ] * 3
    assert {one["origin"] for one in seen["writes"]} == {f"http://127.0.0.1:{seen['at']}"}
    assert [one["body"] for one in seen["writes"]] == [
        {"numbers": [tea], "option": "the first one"},
        {"numbers": [milk], "option": "the other"},
        {"numbers": [sugar], "option": "the first one", "words": "half a spoon"},
    ]
    if screen == PHONE:
        assert [one for one in seen["opened"] if one["small"] or one["cut"]] == []
    assert {f"gate:{number}" for number in (tea, milk, sugar)} <= {
        one["target"] for one in seen["opened"]
    }
    accept, option, words = seen["answered"]
    opened = accept["opened"]
    assert opened["title"] == f"Question {tea}"
    assert opened["kv"] == ["Asked by", "Context", "Default taken", "Built on", "To undo"]
    for said in (
        "tea or coffee?",
        "Asked by crew alpha 25 min",
        "Context the pot holds two cups",
        "Default taken the first one",
        "Built on nothing",
        "To undo pick the other",
    ):
        assert said.lower() in opened["said"].lower(), said
    assert opened["cards"] == [
        {
            "name": "the first one",
            "picked": True,
            "marks": ["taken as default", "the thread recommends"],
            "follows": "nothing changes",
        },
        {"name": "the other", "picked": False, "marks": [], "follows": "one more cup"},
        {"name": "both", "picked": False, "marks": [], "follows": "a second pot"},
    ]
    assert opened["box"] is True
    assert opened["will"] == f"Nothing is sent. The default stands and question {tea} closes."
    assert opened["buttons"] == ["Accept the default"]
    assert option["opened"]["buttons"] == ["Accept the default"]
    assert option["opened"]["kv"] == ["Asked by", "Default taken", "Built on", "To undo"]
    assert [card["picked"] for card in option["before"]["cards"]] == [False, True]
    assert option["before"]["buttons"] == ["Send this option"]
    assert option["before"]["will"] == (
        'Goes at once to the crew thread of alpha: "the other", with how to undo the default: '
        "pick the other"
    )
    assert [card["picked"] for card in words["before"]["cards"]] == [True, False]
    assert words["before"]["buttons"] == ["Send my words"]
    assert words["before"]["will"].startswith(
        'Goes at once to the crew thread of alpha: "half a spoon"'
    )
    for one in seen["answered"]:
        for at in ("opened", "before", "after"):
            assert "deny" not in one[at]["said"].lower()
            assert one[at]["cut"] == [], (at, one[at]["cut"])
            if screen == PHONE:
                assert one[at]["small"] == [], (at, one[at]["small"])
                assert one[at]["drawer"] == [0, 0, *PHONE]
    assert accept["after"]["title"] == f"Question {tea}"
    assert (
        f"Question {tea} closed at 16:00 ET with its default, and nothing was sent."
        in (accept["after"]["said"])
    )
    assert accept["after"]["links"] == ["you:gate"]
    for one, number in ((option, milk), (words, sugar)):
        assert (
            f"Question {number} closed at 16:00 ET with its answer recorded and not yet sent, "
            "since no config at"
        ) in one["after"]["said"]
    assert seen["left"] == ["4"]
    records = kept(scene.state)
    assert [(records[n].answer.keeps, records[n].answer.words) for n in (tea, milk, sugar)] == [
        (True, "the first one"),
        (False, "the other"),
        (False, "half a spoon"),
    ]


def test_every_gate_that_can_be_answered_is_ticked_and_closed_in_one_write(scene, tmp_path):
    tea, milk, sugar = gated(scene)
    seen = look(scene, tmp_path, budget=12000, gates={"batch": True})
    clean(seen)
    found = seen["batch"]
    assert [(row["number"], row["tick"]) for row in found["rows"]] == [
        ("4", False),
        (str(tea), True),
        (str(milk), True),
        (str(sugar), True),
    ]
    gate, first, second, _ = found["rows"]
    assert "cannot be answered here" in gate["said"] and gate["opens"] == []
    assert first["options"] == ["the first one (taken)", "the other", "both"]
    assert (first["taken"], first["opens"]) == (["the first one (taken)"], [f"gate:{tea}"])
    assert second["options"] == ["the first one (taken)", "the other"]
    assert found["control"] == "Tick all 3 that can be answered here"
    assert (found["none"]["button"], found["none"]["off"]) == ("Accept the default for 0", True)
    assert found["ticked"] == [str(tea), str(milk), str(sugar)]
    assert found["all"] == {
        "line": f"Closes questions {tea}, {milk} and {sugar} with their defaults. "
        "Nothing is sent to any thread.",
        "button": "Accept the default for 3",
        "off": False,
    }
    assert [one["body"] for one in seen["writes"]] == [{"numbers": [tea, milk, sugar]}]
    assert found["after"]["title"] == "3 of 3 closed"
    for number in (tea, milk, sugar):
        assert f"Question {number} closed at 16:00 ET with its default" in found["after"]["said"]
    assert seen["left"] == ["4"]
    assert [one.answer.keeps for one in kept(scene.state).values()] == [True, True, True]


def test_a_question_with_no_options_on_record_opens_with_no_cards_and_says_so(scene, tmp_path):
    tea, milk, _ = gated(scene)
    file = questions.path(scene.state)
    old = json.loads(file.read_text())
    for one in old["records"]:
        del one["options"]
    file.write_text(json.dumps(old))
    ways = [{"number": tea}, {"number": milk, "words": "oat milk"}]
    seen = look(scene, tmp_path, budget=12000, gates={"ways": ways})
    clean(seen)
    accept, words = seen["answered"]
    assert accept["opened"]["cards"] == [] and accept["opened"]["box"] is True
    assert "None are on record for this gate." in accept["opened"]["said"]
    assert accept["opened"]["buttons"] == ["Accept the default"]
    assert words["before"]["buttons"] == ["Send my words"]
    assert [one["body"] for one in seen["writes"]] == [
        {"numbers": [tea]},
        {"numbers": [milk], "words": "oat milk"},
    ]
    records = kept(scene.state)
    assert [(records[n].answer.keeps, records[n].answer.words) for n in (tea, milk)] == [
        (True, "the first one"),
        (False, "oat milk"),
    ]


def test_a_write_that_is_refused_or_meets_no_server_is_said_in_the_drawer(scene, tmp_path):
    tea, milk, sugar = gated(scene)
    user = jsettings.load()

    def meanwhile(nth):
        if nth > 1:
            return "dark"
        said = party.Evidence("typed", "", "coffee", et(NOW))
        where = "a shell"
        questions.answer(
            scene.state, tea, party=party.USER, evidence=said, where=where, keeps=False, user=user
        )

    ways = [{"number": tea}, {"number": milk, "option": 1}]
    gates = {"ways": ways, "batch": True}
    seen = look(scene, tmp_path, budget=16000, gates=gates, on_write=meanwhile)
    clean(seen)
    unknown = "The view server did not answer, so it is not known whether anything closed."
    refused, lost = seen["answered"]
    assert refused["after"]["title"] == f"Question {tea}"
    assert (
        f'Question {tea} was answered already, and nothing changed: "coffee", by user, '
        f"{et(NOW)}, in a shell (not the default)."
    ) in refused["after"]["said"]
    assert "Nothing changed." in refused["after"]["said"]
    assert lost["after"]["title"] == f"Question {milk}"
    assert unknown in lost["after"]["said"]
    assert lost["after"]["buttons"] == ["Send this option"]
    assert [card["picked"] for card in lost["after"]["cards"]] == [False, True]
    assert seen["batch"]["ticked"] == [str(milk), str(sugar)]
    assert unknown in seen["batch"]["after"]["said"]
    assert seen["batch"]["after"]["buttons"] == ["Accept the default for 2"]
    assert [one["body"] for one in seen["writes"]] == [
        {"numbers": [tea], "option": "the first one"},
        {"numbers": [milk], "option": "the other"},
        {"numbers": [milk, sugar]},
    ]
    assert seen["left"] == ["4", str(milk), str(sugar)]
    records = kept(scene.state)
    assert (records[tea].answer.words, records[milk].answer, records[sugar].answer) == (
        "coffee",
        None,
        None,
    )
