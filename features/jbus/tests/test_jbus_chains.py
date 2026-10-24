"""A row's order is one of two kinds. `--depends` holds a row's launch until the row it names has
merged, and is only for a row whose brief builds on that row's work: its `Builds on:` line names
it. Every other order is only about merging, and is `--merge-after`: the row launches at once,
and jmerge holds its pull request until the row it names has merged.

The tests run the real `jbus queue add` and the real pass in a kitchen, against its fakes of T3
Code and GitHub. The merges follow the real rule of `jmerge.rows`, which jmerge asks first."""

from datetime import timedelta

import pytest

from jmerge import rows as jrows
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import brief, go, rows

ORDER_ONLY = "{slug} cannot depend on {other}: its brief's Builds on: line does not name"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def queue_add(kitchen, slug, *flags, text=None):
    argv = ["--project", "demo", "queue", "add", slug, "--priority", "1", *flags]
    return kitchen.main(*argv, stdin=text if text is not None else brief(slug))


def test_a_depends_the_brief_does_not_build_on_is_refused_and_nothing_is_queued(kitchen):
    assert queue_add(kitchen, "alpha")[0] == 0
    code, said = queue_add(kitchen, "beta", "--depends", "alpha")
    assert code != 0
    assert ORDER_ONLY.format(slug="beta", other="alpha") in said
    assert "--merge-after alpha" in said
    assert "beta" not in rows(kitchen)


def test_queue_apply_refuses_the_same_depends_and_queues_none_of_its_batch(kitchen):
    assert queue_add(kitchen, "alpha")[0] == 0
    batch = (
        f"add gamma --priority 1\n--- brief gamma\n{brief('gamma')}--- end\n"
        f"add beta --priority 1 --depends alpha\n--- brief beta\n{brief('beta')}--- end\n"
    )
    code, said = kitchen.main("--project", "demo", "queue", "apply", stdin=batch)
    assert code != 0 and ORDER_ONLY.format(slug="beta", other="alpha") in said
    assert sorted(rows(kitchen)) == ["alpha"]


def test_a_depends_its_brief_builds_on_is_queued(kitchen):
    assert queue_add(kitchen, "alpha")[0] == 0
    built = brief("beta", "Builds on: `alpha`: it calls the parser alpha adds\n")
    code, said = queue_add(kitchen, "beta", "--depends", "alpha", text=built)
    assert code == 0, said
    assert rows(kitchen)["beta"]["depends"] == ["alpha"]


def test_a_builds_on_line_names_a_slug_whole_and_not_a_slug_it_starts_with(kitchen):
    for slug in ("alpha", "alpha-two"):
        assert queue_add(kitchen, slug)[0] == 0
    built = brief("beta", "Builds on: alpha-two: its tables\n")
    assert queue_add(kitchen, "beta", "--depends", "alpha", text=built)[0] != 0
    assert queue_add(kitchen, "beta", "--depends", "alpha-two", text=built)[0] == 0


def test_an_order_only_about_merging_is_queued_as_merge_after_with_no_line(kitchen):
    assert queue_add(kitchen, "alpha")[0] == 0
    code, said = queue_add(kitchen, "beta", "--merge-after", "alpha")
    assert code == 0, said
    assert (rows(kitchen)["beta"]["depends"], rows(kitchen)["beta"]["merge_after"]) == (
        [],
        ["alpha"],
    )


def test_a_row_added_again_keeps_a_depends_it_already_had(kitchen):
    """A row's depends from before the rule stay: an add that only changes its priority or its
    brief is not refused for them. A depends new to the row still is."""
    for slug in ("alpha", "gamma"):
        assert queue_add(kitchen, slug)[0] == 0
    built = brief("beta", "Builds on: alpha: its parser\n")
    assert queue_add(kitchen, "beta", "--depends", "alpha", text=built)[0] == 0
    assert queue_add(kitchen, "beta", "--depends", "alpha")[0] == 0
    code, said = queue_add(kitchen, "beta", "--depends", "alpha,gamma")
    assert code != 0 and ORDER_ONLY.format(slug="beta", other="gamma") in said
    assert rows(kitchen)["beta"]["depends"] == ["alpha"]


CHAIN = ("one", "two", "three", "four")


def opened(kitchen, slugs):
    kitchen.set("open.json", [kitchen.opened(slug, 10 + CHAIN.index(slug)) for slug in slugs])


def mergeable(kitchen, slugs):
    """The open pull requests that jmerge's queue rule lets merge now, read from the table the
    last pass wrote, as jmerge reads it."""
    table = jrows.read(kitchen.checkout)
    assert table is not None
    return [slug for slug in slugs if jrows.short(table, slug) == ""]


def test_a_chain_only_about_merging_launches_at_once_and_merges_link_by_link(kitchen):
    """Four rows, each merging after the one before it, and one more row that builds on the
    first. The four launch on the first pass. Each pass after that merges what jmerge's rule
    lets through, which is one link, the one whose row ahead has merged. The row that builds
    on the first launches once the first has merged, and not before."""
    kitchen.config(max_running=8)
    after = None
    for slug in CHAIN:
        flags = ("--merge-after", after) if after else ()
        assert queue_add(kitchen, slug, *flags)[0] == 0
        assert go(kitchen, slug)[0] == 0
        after = slug
    built = brief("five", "Builds on: one: the table one adds\n")
    assert queue_add(kitchen, "five", "--depends", "one", text=built)[0] == 0
    assert go(kitchen, "five")[0] == 0

    kitchen.poll()
    launched = [given["title"] for given in kitchen.t3.launches]
    assert sorted(launched) == sorted(f"crew: {slug}" for slug in CHAIN)

    opened(kitchen, CHAIN)
    now, merged, order = NOW, [], []
    while len(order) < len(CHAIN):
        now += timedelta(minutes=3)
        kitchen.poll(now)
        if "one" not in order:
            assert "crew: five" not in [given["title"] for given in kitchen.t3.launches]
        left = [slug for slug in CHAIN if slug not in order]
        assert [rows(kitchen)[slug]["status"] for slug in left] == ["pr"] * len(left)
        ready = mergeable(kitchen, left)
        assert ready == left[:1], f"after {order}, jmerge would merge {ready}"
        order += ready
        merged += [kitchen.merged(slug, 10 + CHAIN.index(slug), "a" * 40) for slug in ready]
        kitchen.set("merged.json", merged)
        opened(kitchen, [slug for slug in CHAIN if slug not in order])
    kitchen.poll(now + timedelta(minutes=3))
    assert order == list(CHAIN)
    assert [rows(kitchen)[slug]["status"] for slug in CHAIN] == ["merged"] * len(CHAIN)
    assert [given["title"] for given in kitchen.t3.launches][len(CHAIN) :] == ["crew: five"]
