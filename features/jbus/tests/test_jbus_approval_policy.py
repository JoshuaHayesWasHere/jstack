"""A row is approved by the user's go on its plan entry, and only a door or no go reaches the user.

On the night of 2026-11-09, 23 of the user's 52 messages were approvals: a crew that found work
outside its task queued it from its own worktree, with no `--entry`, and the row waited on the
user's list though the crew's own row ran on the user's go for its plan entry. jbus now files such
a row under the entry of the crew whose worktree queued it, where both briefs name one home, so
the entry's go approves it in the same `jbus queue add`, and its own follow-ups after it. A row
whose brief holds a `Holds:` line, a row of a crew under an entry with no go, and a row of another
home still wait on the user, and `jbus needs` shows them. Every test runs the real commands
against the kitchen's fakes.
"""

import os
from datetime import timedelta

import pytest

from jbus import cleanup, queue, verbs
from test_jbus_entry_go import PLAN, basis, plan_go, queued
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import brief, rows

FAULT = "Decisions: noticed in {filer}, a test\n"


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "plan.md").write_text(PLAN)
    polish = made.home / "polish"
    polish.mkdir(parents=True, exist_ok=True)
    (polish / "plan.md").write_text("# a plan\n")
    (polish / "home-id").write_text("mcp:polish\n")
    yield made
    made.close()


def from_crew(kitchen, filer, slug, text=None):
    """Queue `slug` as the crew of the row `filer` does: from a folder inside its worktree, with
    no `--entry`. Return what `jbus queue add` printed."""
    worktree = cleanup.worktrees() / kitchen.checkout.name / filer / "features"
    worktree.mkdir(parents=True, exist_ok=True)
    was = os.getcwd()
    os.chdir(worktree)
    try:
        return queued(kitchen, slug, entry="", text=text or brief(slug, FAULT.format(filer=filer)))
    finally:
        os.chdir(was)


def waiting(kitchen):
    """Return what `jbus needs` prints, after a pass, five minutes on."""
    kitchen.poll()
    kitchen.monkeypatch.setattr(verbs, "clock", lambda: NOW + timedelta(minutes=5))
    code, out = kitchen.main("needs")
    assert code == 0, out
    return out


def test_a_row_a_crew_queues_is_approved_on_its_entry_go_and_so_is_its_own_follow_up(kitchen):
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    said = from_crew(kitchen, "alpha", "alpha-fix")
    assert "approved alpha-fix" in said
    assert basis(kitchen, "alpha-fix") == (queue.ENTRY, "epic")
    from_crew(kitchen, "alpha-fix", "alpha-fix-2")
    assert basis(kitchen, "alpha-fix-2") == (queue.ENTRY, "epic")
    out = waiting(kitchen)
    assert "alpha-fix" not in out


@pytest.mark.parametrize(
    ("filer_entry", "more", "why"),
    [
        ("epic", "Holds: publishes\n", "a row that opens a door"),
        ("other", "", "a row of a crew whose entry has no go"),
    ],
)
def test_a_row_that_opens_a_door_or_has_no_entry_go_waits_on_the_user(
    kitchen, filer_entry, more, why
):
    queued(kitchen, "alpha", entry=filer_entry)
    queued(kitchen, "beta")
    assert plan_go(kitchen)[0] == 0
    from_crew(kitchen, "alpha", "alpha-fix", brief("alpha-fix", FAULT.format(filer="alpha") + more))
    assert basis(kitchen, "alpha-fix") == (), why
    assert "alpha-fix" in waiting(kitchen), why


def test_a_row_a_crew_queues_for_another_home_is_not_filed_under_its_entry(kitchen):
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    other = brief("alpha-fix", FAULT.format(filer="alpha")).replace(
        "Home: uncategorized", "Home: polish"
    )
    from_crew(kitchen, "alpha", "alpha-fix", other)
    assert not rows(kitchen)["alpha-fix"].get("entry")
    assert basis(kitchen, "alpha-fix") == ()


def test_a_crew_that_queues_its_own_row_again_keeps_it_under_its_entry(kitchen):
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    from_crew(kitchen, "alpha", "alpha")
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")
