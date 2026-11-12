"""`jbus retire <scope dir>` archives a scoped home's plan, as the handoff skill's archive runs it,
and carries the fixes counted in its `blockers.json` to the catch-all's ledger: once the plan is
archived, each brief that named the scope is the catch-all's, and admit reads the catch-all's
ledger for it. The tests run the real command and then `jbus queue add`, which is where a try
left behind would show: a fix past the cap queued as though none was tried."""

import pytest

from jbriefs import home as homes
from jbus import blockers
from scoped import scope
from test_jbus_kitchen import Kitchen
from test_jbus_queue import add, brief

FIX = "Fix of: check:beta\nWhen green: `check` passes on the fix's head\n"


def fix(slug, home="flow"):
    return brief(slug, FIX).replace("Home: uncategorized", f"Home: {home}")


def retire(kitchen, scope="flow"):
    return kitchen.main("retire", str(kitchen.home / scope))


def queue_fix(kitchen, slug):
    return kitchen.main(
        "--project",
        "demo",
        "queue",
        "add",
        slug,
        "--priority",
        "1",
        stdin=fix(slug, "uncategorized"),
    )


def slugs(directory):
    return [one["slug"] for one in blockers.tries(directory, "check:beta")]


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    """The demo project, the user's word given, and the flow scope's home."""
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    scope(made.home, "flow", "mcp:flow-home")
    yield made
    made.close()


@pytest.fixture
def capped(kitchen):
    """The flow scope with check:beta at its cap of two fixes, both counted in flow's ledger."""
    add(kitchen, "alpha", text=fix("alpha"))
    add(kitchen, "bravo", text=fix("bravo"))
    assert slugs(kitchen.home / "flow") == ["alpha", "bravo"]
    return kitchen


def test_a_retired_scope_s_fixes_count_against_the_cap_in_the_catch_all(capped):
    plan = (capped.home / "flow" / "plan.md").read_text()
    code, said = retire(capped)
    assert code == 0, said
    assert slugs(homes.catchall(capped.home)) == ["alpha", "bravo"]
    assert slugs(capped.home / "flow") == []
    assert not (capped.home / "flow" / "plan.md").exists()
    assert (capped.home / "flow" / "plan-archived.md").read_text() == plan
    code, said = queue_fix(capped, "charlie")
    assert code != 0
    assert "check:beta had 2 fixes (alpha, bravo), the retry cap" in said


def test_a_retire_run_again_counts_each_fix_once(capped):
    assert retire(capped)[0] == 0
    assert retire(capped)[0] == 0
    assert slugs(homes.catchall(capped.home)) == ["alpha", "bravo"]


def test_a_retire_cut_short_between_its_writes_carries_each_fix_once_when_run_again(capped):
    """Cut after the catch-all's ledger and the plan, before the scope's ledger is written: the
    scope still holds what it carried, and a run again takes it out and counts nothing twice."""
    kept = (capped.home / "flow" / blockers.LEDGER).read_text()
    assert retire(capped)[0] == 0
    (capped.home / "flow" / blockers.LEDGER).write_text(kept)
    assert retire(capped)[0] == 0
    assert slugs(homes.catchall(capped.home)) == ["alpha", "bravo"]
    assert slugs(capped.home / "flow") == []


def test_a_scope_with_no_ledger_retires_its_plan_and_carries_nothing(kitchen):
    assert retire(kitchen)[0] == 0
    assert (kitchen.home / "flow" / "plan-archived.md").exists()
    assert not (homes.catchall(kitchen.home) / blockers.LEDGER).exists()


@pytest.mark.parametrize("scope", ["uncategorized", "tasks", "nowhere"])
def test_the_catch_all_a_shared_folder_and_no_folder_are_refused(kitchen, scope):
    if scope != "nowhere":
        (kitchen.home / scope).mkdir(exist_ok=True)
    code, said = retire(kitchen, scope)
    assert code != 0
    assert said.startswith("refused: ")


def test_a_folder_outside_the_homes_state_is_refused(kitchen, tmp_path):
    outside = tmp_path / "elsewhere" / "flow"
    outside.mkdir(parents=True)
    (outside / "plan.md").write_text("# a plan\n")
    code, said = kitchen.main("retire", str(outside))
    assert code != 0
    assert (outside / "plan.md").exists()
