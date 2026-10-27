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
from test_jbus_kitchen import NOW, Kitchen, iso
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
    """What the home thread got of a retry cap, once a pass has run."""
    kitchen.poll()
    return [one for sent in kitchen.wakes.said for one in sent if "the retry cap" in one]


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


def pull(kitchen, slug, number, ran=None, conclusion="FAILURE"):
    """The slug's open pull request, whose check started `ran` before now and took 2 minutes."""
    made = kitchen.opened(slug, number, state=conclusion)
    if ran is not None:
        made["statusCheckRollup"][0].update(
            name="check",
            startedAt=iso(NOW - ran),
            completedAt=iso(NOW - ran + timedelta(minutes=2)),
        )
    return made


def merged_after_one_ran(kitchen, launched_first):
    """Through passes: beta's check fails on #7, beta-fix-1 is queued and removed, launched first
    or not, and beta-fix-2 merges as #8 40 minutes before now. Return what `jbus clear` says
    then."""
    add(kitchen, "beta")
    kitchen.t3.thread("beta", "idle", idle=timedelta(hours=2))
    kitchen.set("open.json", [pull(kitchen, "beta", 7, ran=timedelta(minutes=80))])
    kitchen.poll(NOW - timedelta(minutes=60))
    for slug in ("beta-fix-1", "beta-fix-2"):
        assert queued(kitchen, slug, "check:beta")[0] == 0
    if launched_first:
        kitchen.t3.thread("beta-fix-1", "completed", idle=timedelta(minutes=55))
        kitchen.poll(NOW - timedelta(minutes=50))
    assert remove(kitchen, "beta-fix-1")[0] == 0
    assert go(kitchen, "beta-fix-2")[0] == 0
    kitchen.t3.thread("beta-fix-2", "completed", settled=True)
    merged = kitchen.merged("beta-fix-2", 8, "e" * 40, ago=timedelta(minutes=42))
    kitchen.set("merged.json", [merged])
    kitchen.poll(NOW - timedelta(minutes=40))
    return cleared(kitchen)


def test_a_merged_fix_s_effect_is_waited_on_and_a_blocker_it_clears_never_pages(kitchen):
    pending = merged_after_one_ran(kitchen, launched_first=False)
    paged_while_pending = paged(kitchen)
    kitchen.set(
        "open.json", [pull(kitchen, "beta", 7, ran=timedelta(minutes=30), conclusion="SUCCESS")]
    )
    kitchen.poll(NOW - timedelta(minutes=20))
    after = cleared(kitchen)

    assert counted(kitchen, "check:beta") == ["beta-fix-2"]
    assert pending.startswith("wait check:beta: beta-fix-2 merged"), pending
    assert paged_while_pending == []
    assert "check:beta" not in after, after
    assert paged(kitchen) == []
    assert posted(kitchen) == []


def test_at_the_cap_a_merged_fix_s_effect_is_waited_on_and_a_rerun_that_fails_again_pages(kitchen):
    pending = merged_after_one_ran(kitchen, launched_first=True)
    refused = queued(kitchen, "beta-fix-3", "check:beta")
    paged_while_pending = paged(kitchen)
    still = pull(kitchen, "beta", 7, ran=timedelta(minutes=30))
    kitchen.set("open.json", [still])
    kitchen.poll(NOW - timedelta(minutes=20))
    row = next(
        one for one in jbus.read_json(kitchen.state / "queue.json", []) if one["slug"] == "beta"
    )
    stands = cleared(kitchen)

    assert counted(kitchen, "check:beta") == ["beta-fix-1", "beta-fix-2"]
    assert pending.startswith("wait check:beta: beta-fix-2 merged"), pending
    assert refused[0] == 1
    assert "beta-fix-2 merged" in refused[1]
    assert paged_while_pending == []
    assert row["updated"] == stamp(timedelta(minutes=60)), "the rerun changed no column"
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
    """mac-room-proc's check failed on #379. mac-sync-main-2 was queued as its fix and removed
    unrun at 17:25 for mac-sync-shards, which merged as #393. The cap paged Josh "I take it"."""
    add(kitchen, "mac-room-proc")
    kitchen.t3.thread("mac-room-proc", "idle", idle=timedelta(hours=1))
    kitchen.set("open.json", [kitchen.opened("mac-room-proc", 379, state="FAILURE")])
    kitchen.poll(NOW - timedelta(minutes=50))
    for slug in ("mac-sync-main-2", "mac-sync-shards"):
        assert queued(kitchen, slug, "check:mac-room-proc")[0] == 0
        assert go(kitchen, slug)[0] == 0
    assert remove(kitchen, "mac-sync-main-2")[0] == 0
    kitchen.t3.thread("mac-sync-shards", "completed", settled=True)
    merged = kitchen.merged("mac-sync-shards", 393, "d" * 40, ago=timedelta(minutes=20))
    kitchen.set("merged.json", [merged])
    kitchen.poll(NOW - timedelta(minutes=15))
    kitchen.forget()

    said = cleared(kitchen)
    kitchen.poll()

    assert "decision" not in said, said
    assert [one["line"] for one in kitchen.events("decision")] == []
    assert kitchen.wakes.posts == []
    assert counted(kitchen, "check:mac-room-proc") == ["mac-sync-shards"]


@pytest.mark.parametrize(("status", "key"), [("left", "left:beta"), ("gate", "row:beta")])
def test_a_blocker_no_pass_judges_again_pages_at_the_cap_once_its_last_fix_merged(
    kitchen, status, key
):
    """Only a failed check on an open pull request is judged again over a merged fix. A stuck or
    left row keeps its columns, so waiting for its next judgment would wait for ever."""
    add(kitchen, "beta")
    seen(kitchen, "beta", timedelta(hours=3), status=status, thread="mcp:beta")
    for slug, ago in (("beta-fix-1", timedelta(minutes=90)), ("beta-fix-2", timedelta(hours=1))):
        assert queued(kitchen, slug, key)[0] == 0
        seen(kitchen, slug, ago, status="merged", thread=f"mcp:{slug}", pr="#8")

    capped = cleared(kitchen)
    refused = queued(kitchen, "beta-fix-3", key)

    assert capped.startswith(f"decision {key}: {key} had 2 fixes (beta-fix-1, beta-fix-2)"), capped
    assert refused[0] == 1
    assert "raised to" in refused[1], refused[1]
    assert [one["line"] for one in paged(kitchen)] == [
        f"decision beta: {key} had 2 fixes (beta-fix-1, beta-fix-2), the retry cap, and it still "
        f'blocks. Reply: "demo {key}: I take it"'
    ]
