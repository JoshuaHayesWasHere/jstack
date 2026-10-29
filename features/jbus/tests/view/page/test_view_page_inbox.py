"""The inbox on the page: Approve and "Undo the approval", each tapped as a person would, the
write each one sends after its 10-second countdown, and the link to its home's thread that a need
the user writes about has in their place."""

import pytest

from jbus import queue
from jmerge import judgement
from test_jbus_kitchen import complete
from view.page.browser import BROWSES, LAUNCH, PATIENCE, PROBE, look
from view.scene import GATE, Served
from view.test_view_answer import Counter

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 60)]

STEP = 500
COUNT = 22
"""Looks that outlast the 10-second countdown and the write after it."""


def test_approve_and_its_undo_reach_jbus_and_a_gate_links_to_its_home(tmp_path, monkeypatch):
    counter = Counter(tmp_path, monkeypatch)
    (counter.kitchen.home / "home-id").write_text("mcp:home-demo\n")
    code, said = counter.kitchen.main(
        "queue", "add", "oat-milk", "--priority", "1", stdin=complete("oat-milk")
    )
    assert code == 0, said
    counter.passes(1)
    sha = judgement.brief_sha(queue.brief(counter.state, "oat-milk"))[:12]
    (counter.kitchen.home / "gates.md").write_text(
        GATE.format(n=40, asked="which jar?", status="open", default="")
    )
    served = Served(counter)
    try:
        found = served.json("/state.json?project=demo")["needs"]
        (jar,) = [one for one in found if one["what"] == "which jar?"]
        walk = ["look", 'tap:[data-accept="demo/approve:oat-milk"]', *["look"] * COUNT]
        walk += ["tap:[data-unsay]", *["look"] * 4]
        seen = look(
            counter,
            tmp_path / "look",
            route="#/demo",
            port=served.port,
            walk=walk,
            script=PROBE,
            at=4000 + STEP * len(walk),
            budget=60000,
        )
        row = queue.fresh(counter.state, "oat-milk")
    finally:
        served.close()
        counter.kitchen.close()
    assert seen["errors"] == []
    walked = seen["walked"]
    assert walked[1]["acc"].startswith("Approving it in") and walked[1]["acc"].endswith("Undo")
    approved = walked[1 + COUNT]
    assert "oat-milk approved at" in approved["nsaid"] and "Undo the approval" in approved["nsaid"]
    assert "its go is taken back" in walked[2 + COUNT + 4]["nsaid"]
    writes = [(one["path"].partition("?")[0], one["body"]) for one in seen["writes"]]
    approve, hold = writes
    assert approve == ("/panel/you/approve", {"slug": "oat-milk", "sha": sha})
    assert hold[0] == "/panel/you/hold" and hold[1]["slug"] == "oat-milk"
    assert (row.get("approved"), row.get("held")) == ("", True)
    actions = [one["body"]["name"] for one in seen["counted"] if one["body"]["kind"] == "action"]
    assert actions == ["approve", "hold"]
    (shown,) = [one for one in seen["needs"]["now"] if one["key"] == f"demo/{jar['key']}"]
    links = [(one["tag"], one["text"], one["href"]) for one in shown["acts"]]
    assert links == [("A", "Write to its home", "t3-thread://v1/mcp:home-demo")]


def test_the_drawer_of_what_waits_approves_a_row_in_place_and_hands_over_no_cli_line(
    tmp_path, monkeypatch
):
    """Its row says which brief waits and has the Approve of Needs you, which counts its 10 s
    with an Undo right there, not a `jbus queue approve` line with placeholders to fill in."""
    counter = Counter(tmp_path, monkeypatch)
    code, said = counter.kitchen.main(
        "queue", "add", "oat-milk", "--priority", "1", stdin=complete("oat-milk")
    )
    assert code == 0, said
    counter.passes(1)
    sha = judgement.brief_sha(queue.brief(counter.state, "oat-milk"))[:12]
    served = Served(counter)
    try:
        seen = look(
            counter,
            tmp_path / "look",
            route="#/demo/you/approve",
            port=served.port,
            walk=["look", 'tap:#dw [data-accept="demo/approve:oat-milk"]', "look"],
            at=6000,
            budget=10000,
        )
    finally:
        served.close()
        counter.kitchen.close()
    assert seen["errors"] == []
    drawer, tapped, _ = [one["said"] for one in seen["walked"]]
    assert "queue approve" not in drawer and "<id>" not in drawer
    assert f"brief {sha}, written " in drawer and "Approving it in" not in drawer
    assert "Approving it in" in tapped and "Undo" in tapped
