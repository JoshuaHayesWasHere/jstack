"""GitHub's API budget, which jbus and every thread share, is kept above a floor (`jbus.budget`).

This is the replay of the rule PassesNeverStarve of the flow-blockers spec (S12Budget.tla): a fake
`gh` whose rate_limit falls to 0. A pass at or under the floor makes no call that can wait, `jmerge`
still runs, and no row changes, and a pass that gets no answer about the budget changes no row
either. The tool's half of the rule is `test_jobs_are_refused_when_they_would_spend_half_the_budget`
in `test_jbus_flow.py`.
"""

import json
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest

from jbus import budget, queue, waiting
from jbus.flow import records
from test_jbus_kitchen import NOW, PROJECT, Kitchen, rate_limit
from test_jbus_queue import add, launches


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def passed(kitchen, minutes, left):
    """Run a pass `minutes` after NOW with `left` calls in GitHub's budget, and return what the
    pass said, the calls it made to `gh` and to `jmerge`, and the table before and after."""
    kitchen.set("rate-limit.json", left if isinstance(left, str) else rate_limit(left))
    table = (kitchen.state / "queue.json").read_text()
    calls, merges = len(kitchen.log("gh")), len(kitchen.log("jmerge"))
    said = kitchen.poll(NOW + timedelta(minutes=minutes))
    after = (kitchen.state / "queue.json").read_text()
    return said, kitchen.log("gh")[calls:], kitchen.log("jmerge")[merges:], table, after


def test_a_pass_whose_budget_falls_to_zero_makes_no_call_that_can_wait_and_changes_no_row(
    kitchen,
):
    add(kitchen, "alpha")
    kitchen.set("open.json", [kitchen.opened("beta", 7)])
    for minutes, left in enumerate((budget.FLOOR, budget.FLOOR // 2, 1, 0)):
        said, calls, merges, table, after = passed(kitchen, 3 * minutes, left)
        assert calls == ["api rate_limit"]
        assert merges, "the merge is urgent, and jmerge runs under the floor"
        assert "--sweep --check" not in merges
        assert after == table and launches(kitchen) == []
        assert (
            f"wait demo: GitHub not asked: GitHub's core budget has {left} of 5000 calls left, "
            f"at or under the floor of {budget.FLOOR} kept for merges, until 2026-10-12 16:00 UTC"
        ) in said
    said, calls, merges, table, after = passed(kitchen, 15, budget.FLOOR + 1)
    assert calls[0] == "api rate_limit" and any(call.startswith("pr list") for call in calls)
    assert launches(kitchen) == ["alpha"] and after != table


@pytest.mark.parametrize("answer", ["", "not json", json.dumps({"resources": {}})])
def test_a_pass_with_no_answer_about_the_budget_makes_no_other_call_and_changes_no_row(
    kitchen, answer
):
    add(kitchen, "alpha")
    said, calls, merges, table, after = passed(kitchen, 0, answer)
    assert calls == ["api rate_limit"] and merges
    assert after == table and launches(kitchen) == []
    assert any(line.startswith("wait demo: could not ask GitHub: ") for line in said)


@pytest.mark.parametrize("blind", ["t3 down", "removed.json does not parse"])
def test_a_pass_that_sees_no_world_still_spends_no_budget_under_the_floor(kitchen, blind):
    add(kitchen, "alpha")
    if blind == "t3 down":
        kitchen.t3.down.add(PROJECT)
    else:
        queue.removed_path(kitchen.state).write_text("not json")
    said, calls, merges, table, after = passed(kitchen, 0, 0)
    assert calls == ["api rate_limit"] and merges and "--sweep --check" not in merges
    assert after == table


def test_a_pass_under_the_floor_records_it_once_a_window_as_a_quiet_condition(kitchen):
    add(kitchen, "alpha")
    for minutes in (0, 3):
        passed(kitchen, minutes, 0)
    assert kitchen.lines("condition") == ["condition demo: GitHub's API budget is under the floor"]


@pytest.mark.parametrize("window", ["core", "graphql"])
def test_either_window_under_the_floor_holds_the_budget(window):
    given = rate_limit(5000)
    given["resources"] = {name: dict(one) for name, one in given["resources"].items()}
    given["resources"][window]["remaining"] = budget.FLOOR
    why = budget.held(budget.parse(json.dumps(given)))
    assert why.startswith(f"GitHub's {window} budget has {budget.FLOOR} of 5000 calls left")


def test_calls_to_come_count_against_the_floor():
    left = budget.parse(json.dumps(rate_limit(budget.FLOOR + 30)))
    assert budget.held(left, 29) == ""
    assert "30 calls would take it to 1000" in budget.held(left, 30)


@pytest.mark.parametrize(
    ("left", "code", "first"),
    [(5000, 0, "ok: GitHub's core budget has 5000 calls left, floor 1000"), (0, 75, "held")],
)
def test_the_threads_ask_the_same_floor_with_jbus_budget(kitchen, left, code, first):
    kitchen.set("rate-limit.json", rate_limit(left))
    said = kitchen.main("budget")
    assert said[0] == code and said[1].startswith(first)


def test_jbus_budget_holds_on_no_answer_and_counts_the_calls_to_come(kitchen):
    kitchen.set("rate-limit.json", "not json")
    assert kitchen.main("budget") == (
        75,
        "held: GitHub did not say what is left of its API budget: make no call to GitHub that "
        "can wait\n",
    )
    kitchen.set("rate-limit.json", rate_limit(budget.FLOOR + 10))
    assert kitchen.main("budget")[0] == 0
    assert kitchen.main("budget", "--calls", "10")[0] == 75


def test_jbus_budget_waits_until_the_budget_is_back_above_the_floor(kitchen, monkeypatch):
    kitchen.set("rate-limit.json", rate_limit(0))
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        kitchen.set("rate-limit.json", rate_limit(5000))

    monkeypatch.setattr(budget, "time", SimpleNamespace(monotonic=time.monotonic, sleep=sleep))
    assert kitchen.main("budget", "--wait", "540")[0] == 0 and slept == [budget.AGAIN]


def test_jobs_are_refused_where_they_would_take_the_budget_to_the_floor(monkeypatch):
    given = json.dumps(rate_limit(budget.FLOOR + 500))
    monkeypatch.setattr(records, "ask", lambda command, cwd=None: given)
    assert records.affordable(499) and not records.affordable(500)


def test_jobs_are_refused_where_the_floor_allows_them_and_they_would_spend_half(monkeypatch):
    given = json.dumps(rate_limit(2500))
    monkeypatch.setattr(records, "ask", lambda command, cwd=None: given)
    assert budget.held(budget.parse(given), 1251) == ""
    assert records.affordable(1250) and not records.affordable(1251)


def spent_items(kitchen):
    return [one["line"] for one in waiting.read(kitchen.state) or [] if one["kind"] == "github"]


def test_a_spent_window_waits_on_the_user_once_until_it_starts_again(kitchen):
    """A window with no call left is one item of what waits on the user, through every pass that
    reads it so, and through a pass that could not read the budget. Above nothing, it goes, as
    the floor still holds the pass's calls."""
    add(kitchen, "alpha")
    spent = (
        "GitHub's API allowance is spent: its core window has 0 of 5000 calls left "
        "until 2026-10-12 16:00 UTC"
    )
    for minutes in (0, 3):
        passed(kitchen, minutes, 0)
        assert spent_items(kitchen) == [spent]
    passed(kitchen, 6, "")
    assert spent_items(kitchen) == [spent]
    said, calls, _, _, _ = passed(kitchen, 9, budget.FLOOR // 2)
    assert spent_items(kitchen) == []
    assert calls == ["api rate_limit"]
    assert kitchen.lines("decision") == []
