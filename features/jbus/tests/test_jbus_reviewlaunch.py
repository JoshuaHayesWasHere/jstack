"""`jbus.reviewlaunch` is the one place that says whether a head has a review asked for, and
both of jbus's launchers ask it: `prereview.launch`, the first review, and `rebase.scope`, the
scoped review of a rebase. A head is asked for where `review-launches.jsonl` holds a launch at
it, or a claim a pass wrote before a launch it did not live to record, or where `sent.json`
holds the key a pass marked before this ledger had claims. Like `test_jbus_rereview.py`, the
tests run the real pass against the kitchen's fakes."""

import json
import re
from datetime import timedelta

import pytest

import jbus
from jbus import reviewlaunch
from test_jbus_kitchen import NOW
from test_jbus_prereview import proved_crew, reviewers
from test_jbus_rereview import keys, launched, out, recorded, scoped
from testing.paths import REPO

__all__ = ["launched"]

HEAD = "c" * 40


def asked(kitchen, how, head):
    """Leave what an earlier pass left of a review asked for at `head`."""
    if how in ("reviewers", "rereview"):
        sent = jbus.read_json(kitchen.state / "sent.json", [])
        jbus.write_json(kitchen.state / "sent.json", [*sent, f"{how}|alpha|{head[:12]}"])
        return
    thread = "mcp:earlier" if how == "launched" else ""
    line = {"slug": "alpha", "thread": thread, "head": head, "kind": "first", "n": 1}
    with open(kitchen.state / reviewlaunch.LAUNCHES, "a") as file:
        file.write(json.dumps(line | {"at": NOW.isoformat()}) + "\n")


HOW = ["launched", "claimed", "reviewers", "rereview"]


@pytest.mark.parametrize("how", HOW)
def test_a_head_with_a_review_asked_for_gets_no_first_reviewer(kitchen, how):
    _, _, head = proved_crew(kitchen)
    asked(kitchen, how, head)
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert reviewers(kitchen) == []


@pytest.mark.parametrize("how", HOW)
def test_a_head_with_a_review_asked_for_gets_no_scoped_reviewer(launched, how):
    asked(launched, how, HEAD)
    out(launched)
    for minutes in (0, 3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert scoped(launched) == []


def test_a_launch_is_claimed_before_it_is_asked_for_so_one_with_no_reply_is_not_made_again(
    launched,
):
    out(launched)
    launched.t3.lose = "after"
    for minutes in (0, 3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    assert len(scoped(launched)) == 1
    assert keys(launched) == [HEAD[:12]] and recorded(launched) == []


def test_a_launch_t3_code_refuses_takes_its_claim_back_and_the_next_pass_launches(
    launched,
):
    """A line of the ledger that is no JSON is kept as it is, and the claim is still taken back."""
    (launched.state / reviewlaunch.LAUNCHES).write_text("not a line jbus wrote\n")
    out(launched)
    launched.t3.refuse = "no more threads"
    launched.poll(NOW)
    assert len(scoped(launched)) == 1 and keys(launched) == []
    launched.t3.refuse = ""
    for minutes in (3, 6):
        launched.poll(NOW + timedelta(minutes=minutes))
    made = launched.t3.threads[-1]["threadId"]
    assert len(scoped(launched)) == 2
    assert keys(launched) == [HEAD[:12]]
    assert recorded(launched) == [("alpha", made, HEAD, "scoped", 1)]
    ledger = (launched.state / reviewlaunch.LAUNCHES).read_text()
    assert ledger.startswith("not a line jbus wrote\n")


def test_no_other_module_names_a_launch_key():
    """A launcher that read or wrote `reviewers|` or `rereview|` itself would decide by a rule of
    its own again, as the five places before this one did."""
    source = REPO / "features/jbus/src/jbus"
    named = re.compile(r"\b(reviewers|rereview)\|")
    found = [
        str(path.relative_to(source))
        for path in sorted(source.rglob("*.py"))
        if path.name != "reviewlaunch.py" and named.search(path.read_text())
    ]
    assert found == []
