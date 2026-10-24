"""A blocker's retry cap counts the fixes that ran, and its page waits for the last fix's effect.

`jbus queue add` counts a fix into `blockers.json`, and `jbus queue remove` of a fix row that
never launched gives that try back: the fix did no work. A fix that launched stays counted when
its row is removed. Once the key had its cap, `jbus clear` raises it to the user, but not while
the key's last fix has merged and the blocker has not been judged since: the merged fix may be
what clears it. Like `test_jbus_queue.py`, the tests run the real commands and the real pass
against a faked T3 Code server, `gh` and `jmerge`, on rows a pass would have written.
"""

from datetime import timedelta

import pytest

import jbus
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, brief, go

AT = "2026-10-12 10:58 ET"
WORD = ("--by", "user", "--at", AT)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    made.quiet()
    yield made
    made.close()


def fix(slug, key):
    return brief(slug, f"Fix of: {key}\nWhen green: `check` passes on the fix's pull request\n")


def queued(kitchen, slug, key):
    code, said = kitchen.main(
        "--project", "demo", "queue", "add", slug, "--priority", "1", stdin=fix(slug, key)
    )
    return code, said


def remove(kitchen, slug):
    return kitchen.main("--project", "demo", "queue", "remove", slug, *WORD)


def stamp(ago):
    return jbus.load().user.stamp(NOW - ago)


def seen(kitchen, slug, ago, **columns):
    """Write a row's derived columns as a pass would have, `ago` before now."""
    table = jbus.read_json(kitchen.state / "queue.json", [])
    for row in table:
        if row["slug"] == slug:
            row.update(columns, updated=stamp(ago))
    jbus.write_json(kitchen.state / "queue.json", table)


def red(kitchen, slug, ago=timedelta(hours=2)):
    """A row whose pull request's check failed, `ago` before now."""
    add(kitchen, slug)
    seen(kitchen, slug, ago, status="pr", thread=f"mcp:{slug}", pr="#7", checks="failed")


def counted(kitchen, key):
    kept = jbus.read_json(kitchen.home / "blockers.json", {})
    return [one["slug"] for one in kept.get(key, [])]


def cleared(kitchen):
    code, said = kitchen.main("--project", "demo", "clear")
    assert code == 0, said
    return said


def paged(kitchen):
    """Every decision of a retry cap raised so far, each one an event the next pass posts."""
    return [one for one in kitchen.events("decision") if "the retry cap" in one["line"]]


def posted(kitchen):
    """What the webhook got of a retry cap, once a pass has run."""
    kitchen.poll()
    return [one for sent in kitchen.webhook.said for one in sent if "the retry cap" in one]


def test_a_fix_removed_before_it_launched_gives_its_try_back(kitchen):
    for slug in ("beta-fix-1", "beta-fix-2"):
        assert queued(kitchen, slug, "check:beta")[0] == 0
    assert remove(kitchen, "beta-fix-1")[0] == 0

    third = queued(kitchen, "beta-fix-3", "check:beta")
    fourth = queued(kitchen, "beta-fix-4", "check:beta")

    assert counted(kitchen, "check:beta") == ["beta-fix-2", "beta-fix-3"]
    assert third[0] == 0, third[1]
    assert fourth[0] == 1
    assert "check:beta had 2 fixes (beta-fix-2, beta-fix-3)" in fourth[1]


def test_a_fix_removed_after_it_launched_still_counts(kitchen):
    assert queued(kitchen, "beta-fix-1", "check:beta")[0] == 0
    seen(kitchen, "beta-fix-1", timedelta(hours=1), status="queued", thread="mcp:beta-fix-1")
    kitchen.t3.thread("beta-fix-1", "completed", settled=True)
    assert remove(kitchen, "beta-fix-1")[0] == 0

    second = queued(kitchen, "beta-fix-2", "check:beta")
    third = queued(kitchen, "beta-fix-3", "check:beta")

    assert second[0] == 0, second[1]
    assert third[0] == 1
    assert "check:beta had 2 fixes (beta-fix-1, beta-fix-2)" in third[1]


def merged_fix(kitchen, slug, ago):
    seen(kitchen, slug, ago, status="merged", thread=f"mcp:{slug}", pr="#8", checks="")


def test_a_merged_fix_s_effect_is_waited_on_and_a_blocker_it_clears_never_pages(kitchen):
    red(kitchen, "beta")
    for slug in ("beta-fix-1", "beta-fix-2"):
        assert queued(kitchen, slug, "check:beta")[0] == 0
    assert remove(kitchen, "beta-fix-1")[0] == 0
    merged_fix(kitchen, "beta-fix-2", timedelta(minutes=30))

    pending = cleared(kitchen)
    paged_while_pending = paged(kitchen)
    seen(kitchen, "beta", timedelta(minutes=5), status="merged", checks="")
    after = cleared(kitchen)

    assert pending.startswith("wait check:beta: beta-fix-2 merged"), pending
    assert paged_while_pending == []
    assert "check:beta" not in after
    assert paged(kitchen) == []
    assert posted(kitchen) == []


def test_at_the_cap_a_merged_fix_s_effect_is_waited_on_and_then_a_blocker_that_stands_pages(
    kitchen,
):
    red(kitchen, "beta")
    for slug in ("beta-fix-1", "beta-fix-2"):
        assert queued(kitchen, slug, "check:beta")[0] == 0
    seen(kitchen, "beta-fix-1", timedelta(hours=1), status="queued", thread="mcp:beta-fix-1")
    kitchen.t3.thread("beta-fix-1", "completed", settled=True)
    assert remove(kitchen, "beta-fix-1")[0] == 0
    merged_fix(kitchen, "beta-fix-2", timedelta(minutes=30))

    pending = cleared(kitchen)
    refused = queued(kitchen, "beta-fix-3", "check:beta")
    paged_while_pending = paged(kitchen)
    seen(kitchen, "beta", timedelta(minutes=5), checks="failed")
    stands = cleared(kitchen)

    assert pending.startswith("wait check:beta: beta-fix-2 merged"), pending
    assert refused[0] == 1
    assert "beta-fix-2 merged" in refused[1]
    assert paged_while_pending == []
    assert stands.startswith("decision check:beta: check:beta had 2 fixes"), stands
    (said,) = posted(kitchen)
    assert 'Reply: "demo check:beta: I take it"' in said


def test_a_blocker_whose_two_launched_fixes_both_failed_pages_at_the_cap(kitchen):
    red(kitchen, "beta")
    for slug in ("beta-fix-1", "beta-fix-2"):
        assert queued(kitchen, slug, "check:beta")[0] == 0
        seen(kitchen, slug, timedelta(hours=1), status="pr", thread=f"mcp:{slug}", checks="failed")

    capped = cleared(kitchen)

    assert capped.startswith(
        "decision check:beta: check:beta had 2 fixes (beta-fix-1, beta-fix-2)"
    ), capped
    (said,) = posted(kitchen)
    assert "check:beta had 2 fixes (beta-fix-1, beta-fix-2), the retry cap" in said


def test_2026_10_24_check_mac_room_proc_replayed_through_a_pass_sends_no_page(kitchen):
    """mac-room-proc's check failed on #379. mac-train-sync-2 was queued as its fix and removed
    unrun at 17:25 for mac-sync-shards, which merged as #393. The cap paged Josh "I take it"."""
    add(kitchen, "mac-room-proc")
    kitchen.t3.thread("mac-room-proc", "idle", idle=timedelta(hours=1))
    kitchen.set("open.json", [kitchen.opened("mac-room-proc", 379, state="FAILURE")])
    kitchen.poll(NOW - timedelta(minutes=50))
    for slug in ("mac-train-sync-2", "mac-sync-shards"):
        assert queued(kitchen, slug, "check:mac-room-proc")[0] == 0
        assert go(kitchen, slug)[0] == 0
    assert remove(kitchen, "mac-train-sync-2")[0] == 0
    kitchen.t3.thread("mac-sync-shards", "completed", settled=True)
    merged = kitchen.merged("mac-sync-shards", 393, "d" * 40, ago=timedelta(minutes=20))
    kitchen.set("merged.json", [merged])
    kitchen.poll(NOW - timedelta(minutes=15))
    kitchen.forget()

    said = cleared(kitchen)
    kitchen.poll()

    assert "decision" not in said, said
    assert [one["line"] for one in kitchen.events("decision")] == []
    assert kitchen.webhook.posts == []
    assert counted(kitchen, "check:mac-room-proc") == ["mac-sync-shards"]
