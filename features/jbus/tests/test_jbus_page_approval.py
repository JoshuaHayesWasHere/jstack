"""An approval recorded from a page's send, before `queue approve` stopped taking `--page`, keeps
its go: the row loads, shows and verifies, and its act stays readable. Nothing gives such an
approval now: `--page` and the `lavish-page` source are refused.
"""

import json

import pytest

from jbus import queue
from test_jbus_approval import cell, viewed
from test_jbus_kitchen import RAN, SESSION, bound
from test_jbus_queue import add, brief, rows, sha12

REF = "27362329dd06edc4/send-3"
PAGE = "/home/user/.local/state/home/demo/reports/grill-demo.html"
AT = "2026-10-12 10:30 ET"
WROTE = f"your pick on a Lavish page, {AT}, grill-demo.html; run {RAN} by the demo home"
DRAWN = f"your pick on a page, {AT}, grill-demo.html; run {RAN} by the demo home"


def recorded(kitchen, slug="alpha"):
    """Give the row the approval that `--page` wrote, and the line of `acts.jsonl` beside it."""
    add(kitchen, slug, approve=False)
    table = kitchen.state / "queue.json"
    kept = json.loads(table.read_text())
    listed = kept["rows"] if isinstance(kept, dict) else kept
    (row,) = [one for one in listed if one["slug"] == slug]
    row["approved"] = WROTE
    row["approval"] = {
        "basis": "page",
        "ref": REF,
        "words": "1. Ship it: as recommended",
        "said_at": AT,
        "said_in": PAGE,
        "checked": True,
        "ran_by": {"session": SESSION, "directory": str(kitchen.checkout)},
        "ran_at": RAN,
        **bound(kitchen, slug),
    }
    row["brief_sha"] = row["approval"]["brief_sha"]
    table.write_text(json.dumps(kept))
    return row


def test_an_old_approval_by_a_page_loads_verifies_and_launches(kitchen):
    recorded(kitchen)
    code, said = kitchen.main("queue", "verify", "alpha")
    assert code == 0
    assert json.loads(said)["approved"] == DRAWN
    assert cell(kitchen, "alpha") == DRAWN
    (task,) = viewed(kitchen)["tasks"]
    assert task["approved"] == DRAWN
    assert queue.record(rows(kitchen)["alpha"]).basis == queue.PAGE
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


@pytest.mark.parametrize(
    "words",
    [
        ("queue", "approve", "alpha", "--page", REF, "--sha", "0" * 12),
        ("queue", "remove", "alpha", "--page", REF),
    ],
)
def test_no_verb_takes_a_page(kitchen, words):
    add(kitchen, "alpha", approve=False)
    code, said = kitchen.main(*words)
    assert code == 2 and "unrecognized arguments: --page" in said
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_a_batch_takes_no_page(kitchen):
    add(kitchen, "alpha", approve=False)
    sha = sha12(brief("alpha"))
    code, said = kitchen.main("queue", "apply", stdin=f"approve alpha --page={REF} --sha {sha}\n")
    assert code == 1 and said.startswith("refused: ")
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_the_source_an_old_act_has_is_no_evidence_a_verb_takes(kitchen):
    add(kitchen, "alpha", approve=False)
    code, said = kitchen.main("--evidence", f"lavish-page:{REF}", "queue", "approve", "alpha")
    assert code == 1 and said.startswith("refused: --evidence is <t3-message | t3-pick | bot-chat")
    assert rows(kitchen)["alpha"]["approved"] == ""
