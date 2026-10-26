"""The inbox on the page: Approve, "Undo the approval" and a Steer line, each tapped as a person
would, and the write each one sends after its 10-second countdown."""

import json

import pytest

from jbus import queue, word
from test_jbus_kitchen import complete
from view.page.browser import BROWSES, LAUNCH, PATIENCE, PROBE, look
from view.scene import GATE, Served
from view.test_view_answer import Counter

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 60)]

START, STEP = 2500, 500
COUNT = 22
"""Looks that outlast the 10-second countdown and the write after it."""


def test_approve_its_undo_and_a_steer_line_each_reach_jbus_from_the_page(tmp_path, monkeypatch):
    counter = Counter(tmp_path, monkeypatch)
    (counter.kitchen.home / "home-id").write_text("mcp:home-demo\n")
    code, said = counter.kitchen.main(
        "queue", "add", "oat-milk", "--priority", "1", stdin=complete("oat-milk")
    )
    assert code == 0, said
    counter.passes(1)
    sha = queue.brief_sha(queue.brief(counter.state, "oat-milk"))[:12]
    (counter.kitchen.home / "gates.md").write_text(
        GATE.format(n=40, asked="which jar?", status="open", default="")
    )
    served = Served(counter)
    try:
        found = served.json("/state.json?project=demo")["needs"]
        (jar,) = [one for one in found if one["what"] == "which jar?"]
        line = f'[data-type="demo/{jar["key"]}"]'
        walk = ["look", 'tap:[data-accept="demo/approve:oat-milk"]', *["look"] * COUNT]
        walk += ["tap:[data-unsay]", *["look"] * 4]
        typed = START + STEP * len(walk) - STEP // 2
        walk += [f"key:Enter:{line}", *["look"] * COUNT]
        fill = (
            f"setTimeout(function () {{ var box = document.querySelector({json.dumps(line)});"
            ' box.value = "the blue one";'
            ' box.dispatchEvent(new Event("input", { bubbles: true })); }, '
            f"{typed});"
        )
        seen = look(
            counter,
            tmp_path / "look",
            route="#/demo",
            port=served.port,
            walk=walk,
            script=PROBE + fill,
            at=4000 + STEP * len(walk),
            budget=60000,
        )
        row = queue.fresh(counter.state, "oat-milk")
        kept = [one.words for one in word.load(counter.state)]
    finally:
        served.close()
        counter.kitchen.close()
    assert seen["errors"] == []
    walked = seen["walked"]
    assert walked[1]["acc"].startswith("Approving it in") and walked[1]["acc"].endswith("Undo")
    approved = walked[1 + COUNT]
    assert "oat-milk approved at" in approved["nsaid"] and "Undo the approval" in approved["nsaid"]
    assert "its go is taken back" in walked[2 + COUNT + 4]["nsaid"]
    assert walked[-1]["nsaid"].startswith("Your line on")
    writes = [(one["path"].partition("?")[0], one["body"]) for one in seen["writes"]]
    approve, hold, steer = writes
    assert approve == ("/panel/you/approve", {"slug": "oat-milk", "sha": sha})
    assert hold[0] == "/panel/you/hold" and hold[1]["slug"] == "oat-milk"
    assert steer == ("/panel/you/steer", {"subj": jar["subj"], "words": "the blue one"})
    assert (row.get("approved"), row.get("held")) == ("", True)
    assert f"{jar['subj']}: the blue one" in kept
