"""Every verb on the queue is an act: `jbus queue hold`, the go that releases a hold, `remove`,
`withdraw`, a batch's lines and a scout's go each append one line to `acts.jsonl` with the
party that acted and the evidence it acted on, whatever came of it.

The tests run the real command against the faked T3 Code server of `test_jbus_kitchen`.
"""

import pytest

from jbus import acts, queue
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, adds, batch, go, rows
from test_jbus_scout import request

HOME, MESSAGE = "mcp:a-home", "a-message-of-his"
REF = f"{HOME}/{MESSAGE}"
AT = "2026-10-12 10:58 ET"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    monkeypatch.setattr(queue, "clock", lambda: NOW)
    made.word()
    yield made
    made.close()


def queue_(kitchen, *argv, stdin=""):
    return kitchen.main("--project", "demo", "queue", *argv, stdin=stdin)


def last(kitchen):
    """The newest act, as who did what on what, and what came of it."""
    one = acts.read(kitchen.state)[-1]
    return (
        one["action"]["verb"],
        one["action"]["subject"],
        one["party"]["kind"],
        one["evidence"]["source"],
        one["outcome"],
    )


def test_a_hold_is_an_act_by_the_home(kitchen):
    add(kitchen, "alpha")
    code, said = queue_(kitchen, "hold", "alpha")
    assert code == 0, said
    assert rows(kitchen)["alpha"]["held"] is True
    assert last(kitchen) == ("hold", "alpha", "home", "typed", "done")


def test_the_go_that_releases_a_hold_is_an_act(kitchen):
    add(kitchen, "alpha")
    assert queue_(kitchen, "hold", "alpha")[0] == 0
    assert go(kitchen, "alpha")[0] == 0
    assert "held" not in rows(kitchen)["alpha"]
    assert last(kitchen) == ("go", "alpha", "home", "typed", "done")


def test_a_remove_by_the_user_is_an_act_on_typed_or_checked_words(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta")
    code, said = queue_(kitchen, "remove", "alpha", "--by", "user", "--at", AT)
    assert code == 0, said
    assert "alpha" not in rows(kitchen)
    assert last(kitchen) == ("remove", "alpha", "home", "typed", "done")
    kitchen.t3.says(HOME, MESSAGE, "take beta out")
    code, said = kitchen.main("--as", "user", "queue", "remove", "beta", "--message", REF)
    assert code == 0, said
    assert "beta" not in rows(kitchen)
    assert last(kitchen) == ("remove", "beta", "user", "t3-message", "done")
    assert acts.read(kitchen.state)[-1]["evidence"]["checked"] is True


def test_a_remove_by_someone_else_with_no_checked_words_is_refused_and_logged(kitchen):
    add(kitchen, "alpha")
    code, said = queue_(kitchen, "remove", "alpha", "--by", "flow home", "--at", AT)
    assert (code, said) == (
        1,
        "refused: only user removes a row, on their own words: --by user, or --message "
        "<thread>/<message> or --page <session>/<entry>, not flow home; a home takes out a row "
        "of its own that never launched with jbus queue withdraw\n",
    )
    assert "alpha" in rows(kitchen)
    assert last(kitchen) == ("remove", "alpha", "home", "typed", "refused")


def test_a_withdraw_is_an_act_by_the_home(kitchen):
    add(kitchen, "alpha", approve=False)
    code, said = queue_(kitchen, "withdraw", "alpha", "--why", "done by beta")
    assert code == 0, said
    assert "alpha" not in rows(kitchen)
    assert last(kitchen) == ("withdraw", "alpha", "home", "typed", "done")
    assert acts.read(kitchen.state)[-1]["evidence"]["words"] == "done by beta"


def test_a_batchs_hold_and_remove_lines_are_acts(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta")
    text = batch("hold alpha\n", f'remove beta --by user --at "{AT}"\n', adds("gamma", "--priority 1"))
    code, said = queue_(kitchen, "apply", stdin=text)
    assert code == 0, said
    assert [one[:2] for one in map(tuple, _verbs(kitchen))][-2:] == [
        ("hold", "alpha"),
        ("remove", "beta"),
    ]


def _verbs(kitchen):
    return [(one["action"]["verb"], one["action"]["subject"]) for one in acts.read(kitchen.state)]


def test_a_scouts_go_is_an_act(kitchen):
    code, said = queue_(kitchen, "add", "what-x", "--priority", "1", stdin=request("what-x"))
    assert code == 0, said
    assert rows(kitchen)["what-x"]["role"] == queue.SCOUT
    assert go(kitchen, "what-x")[0] == 0
    assert last(kitchen) == ("go", "what-x", "home", "typed", "done")
