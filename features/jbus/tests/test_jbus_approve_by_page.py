"""A pick that the user sends from a Lavish page is a basis for `queue approve`, and jbus reads it.

`--page <session key>/<entry id>` names a chat entry of a session in Lavish's own state file. jbus
reads the file itself, and takes only an entry whose role is the user's. Every test runs the real
command against a small state file, which the test writes where the kitchen points
`LAVISH_AXI_STATE_DIR`.
"""

import json

import pytest

from test_jbus_approval import cell, go, viewed
from test_jbus_kitchen import RAN, SESSION, bound
from test_jbus_queue import add, brief, rows, sha12

KEY, ENTRY = "27362329dd06edc4", "send-3"
REF = f"{KEY}/{ENTRY}"
PAGE = "/home/user/.local/state/home/demo/reports/grill-demo.html"
PICKED_AT = "2026-10-12 10:30 ET"
PICKED = f"his pick on a Lavish page, {PICKED_AT}, grill-demo.html; run {RAN} by the demo home"
PICKS = "1. Ship it: as recommended\n2. Order: as recommended"


def chat(*more):
    return [
        {"role": "agent", "id": "send-1", "at": "2026-10-12T14:00:00.000Z", "text": "asked"},
        {
            "role": "user",
            "id": ENTRY,
            "at": "2026-10-12T14:30:00.000Z",
            "tag": "picks",
            "text": PICKS,
        },
        *more,
    ]


def lavish(kitchen, sessions):
    """Write Lavish's state file as Lavish writes it, with the sessions by their key, and return
    its path."""
    where = kitchen.root / "lavish"
    where.mkdir(exist_ok=True)
    (where / "state.json").write_text(json.dumps({"sessions": sessions}))
    return where / "state.json"


def session(entries):
    return {KEY: {"key": KEY, "file": PAGE, "status": "ended", "chat": entries}}


def test_an_approval_by_a_pick_holds_what_jbus_read_from_lavish(kitchen):
    state = lavish(kitchen, session(chat()))
    before = state.read_text()
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--page", REF)[0] == 0
    row = rows(kitchen)["alpha"]
    assert row["approval"] == {
        "basis": "page",
        "ref": REF,
        "words": "1. Ship it: as recommended 2. Order: as recommended",
        "said_at": PICKED_AT,
        "said_in": PAGE,
        "checked": True,
        "ran_by": {"session": SESSION, "directory": str(kitchen.checkout)},
        "ran_at": RAN,
        **bound(kitchen, "alpha"),
    }
    assert (row["approved"], cell(kitchen, "alpha")) == (PICKED, PICKED)
    (task,) = viewed(kitchen)["tasks"]
    assert task["approved"] == PICKED
    assert state.read_text() == before
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_a_batch_takes_a_pick(kitchen):
    lavish(kitchen, session(chat()))
    add(kitchen, "alpha", approve=False)
    sha = sha12(brief("alpha"))
    code, said = kitchen.main("queue", "apply", stdin=f"approve alpha --page={REF} --sha {sha}\n")
    assert (code, said) == (0, f"approved alpha: brief {sha}, {PICKED}\n")


@pytest.mark.parametrize(
    "sessions, ref, why",
    [
        (None, REF, "Lavish keeps no state file at {state}"),
        ({}, REF, "Lavish's state at {state} has no session " + KEY),
        (session(chat()), f"{KEY}/send-9", f"session {KEY} has no chat entry send-9"),
        (
            session(chat()),
            f"{KEY}/send-1",
            f"chat entry {KEY}/send-1 is not user's own: Lavish has it as role agent",
        ),
        (
            session(
                chat({"role": "user", "id": "send-4", "at": "2026-10-12T15:00:00Z", "text": " "})
            ),
            f"{KEY}/send-4",
            f"chat entry {KEY}/send-4 has no words",
        ),
        (
            session(chat({"role": "user", "id": "send-4", "text": "go"})),
            f"{KEY}/send-4",
            f"chat entry {KEY}/send-4 has no time Lavish kept",
        ),
        (session(chat()), KEY, f'--page is "<session key>/<entry id>", not {KEY}'),
    ],
)
def test_a_pick_jbus_cannot_read_as_the_users_approves_nothing(kitchen, sessions, ref, why):
    state = kitchen.root / "lavish" / "state.json"
    if sessions is not None:
        lavish(kitchen, sessions)
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--page", ref) == (1, f"refused: {why.format(state=state)}\n")
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_a_state_file_that_does_not_parse_approves_nothing(kitchen):
    where = kitchen.root / "lavish"
    where.mkdir()
    (where / "state.json").write_text("{")
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--page", REF) == (
        1,
        f"refused: Lavish's state at {where / 'state.json'} does not parse\n",
    )


def test_a_state_file_that_cannot_be_read_approves_nothing(kitchen):
    where = kitchen.root / "lavish" / "state.json"
    where.mkdir(parents=True)
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--page", REF) == (
        1,
        f"refused: Lavish's state at {where} cannot be read\n",
    )
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_a_session_with_no_page_file_approves_nothing(kitchen):
    lavish(kitchen, {KEY: {"key": KEY, "status": "ended", "chat": chat()}})
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--page", REF) == (
        1,
        f"refused: session {KEY} keeps no page file\n",
    )
    assert rows(kitchen)["alpha"]["approved"] == ""
