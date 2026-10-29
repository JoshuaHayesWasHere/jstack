"""A row's order is one of two kinds. `--depends` holds a row's launch until the row it names has
opened its pull request, and the row then launches stacked on that pull request's branch. It is
only for a row whose brief builds on that row's work: its `Builds on:` line names it. Every other
order is only about merging, and is `--merge-after`: the row launches at once, and jmerge holds
its pull request until the row it names has merged.

The tests run the real `jbus queue add` and the real pass in a kitchen, against its fakes of T3
Code and GitHub. The merges follow the real rule of `jmerge.rows`, which jmerge asks first."""

import os
import sys
from datetime import timedelta

import pytest

from jmerge import rows as jrows
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import brief, go, rows
from testing.paths import REPO

BRIEFS = REPO / "features/arena-swarm/skills/arena/briefs.sh"

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


@pytest.mark.parametrize(
    "line",
    [
        "Builds on: alpha: the docs alpha writes\n",
        "Builds on: alpha: its parser; gamma: the docs it reads\n",
        "Builds on: <slug>: <what of its work this row starts from>\n",
    ],
)
def test_a_word_after_the_colon_names_no_row(kitchen, line):
    """Only the slugs before each item's colon are rows the brief builds on: a word of the
    description that happens to be a slug, or the template's own text, names none."""
    for slug in ("alpha", "gamma", "docs"):
        assert queue_add(kitchen, slug)[0] == 0
    code, said = queue_add(kitchen, "beta", "--depends", "docs", text=brief("beta", line))
    assert code != 0 and ORDER_ONLY.format(slug="beta", other="docs") in said


@pytest.mark.parametrize(
    "line",
    [
        "Builds on: alpha: its parser; then docs\n",
        "Builds on: alpha is the parser docs\n",
    ],
)
def test_prose_with_no_colon_names_no_row(kitchen, line):
    """An item with no colon is prose, a `;` inside a description or a line that names no row
    before a colon: a word of it that happens to be a slug names none."""
    for slug in ("alpha", "docs"):
        assert queue_add(kitchen, slug)[0] == 0
    code, said = queue_add(kitchen, "beta", "--depends", "docs", text=brief("beta", line))
    assert code != 0 and ORDER_ONLY.format(slug="beta", other="docs") in said


def test_a_list_of_slugs_with_no_colon_names_each_row(kitchen):
    for slug in ("alpha", "docs"):
        assert queue_add(kitchen, slug)[0] == 0
    built = brief("beta", "Builds on: alpha, `docs`\n")
    code, said = queue_add(kitchen, "beta", "--depends", "alpha,docs", text=built)
    assert code == 0, said


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
    return [
        slug
        for slug in slugs
        if jrows.short(table, slug, brief=jrows.stored(kitchen.checkout, slug)) == ""
    ]


def test_a_chain_only_about_merging_launches_at_once_and_merges_link_by_link(kitchen):
    """Four rows, each merging after the one before it, and one more row that builds on the
    first. The four launch on the first pass. Each pass after that merges what jmerge's rule
    lets through, which is one link, the one whose row ahead has merged. The row that builds
    on the first launches once the first has opened its pull request, stacked on its branch,
    and not before."""
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
        five = [given for given in kitchen.t3.launches if given["title"] == "crew: five"]
        assert [given["workspaceStrategy"]["baseRef"] for given in five] == ["one"]
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


@pytest.mark.parametrize("have", ["a b", "a"])
def test_the_arena_queues_its_four_seats_whose_briefs_build_on_what_they_depend_on(
    kitchen, tmp_path, have
):
    """The arena's script writes the four briefs and queues them with `jbus queue apply`: the
    judge depends on the runners and the graft on them and the judge, and each brief's
    `Builds on:` line names what its row depends on, so the batch is queued whole."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "jbus"
    fake.write_text(
        f'#!/bin/sh\ncase $1 in plan) exit 0 ;; esac\nexec {sys.executable} -m jbus "$@"\n'
    )
    fake.chmod(0o755)
    frame = {
        "H": str(kitchen.home),
        "slug": "ar",
        "entry": "ar",
        "size": "S",
        "where": "`src/ar/`",
        "priority": "2",
        "scope": "",
        "have": have,
        "prompt": "make a thing",
        "rubric": "- it is a thing",
        "done_when": "- it is done",
        "proves": "`make check`",
    }
    env = {**os.environ, **frame, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    ran = kitchen.started(["sh", str(BRIEFS)], env=env, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    runners = [f"ar-{one}" for one in have.split()]
    table = rows(kitchen)
    assert (table["ar-judge"]["depends"], table["ar"]["depends"]) == (
        runners,
        [*runners, "ar-judge"],
    )


def launch_of(kitchen, slug):
    (given,) = [given for given in kitchen.t3.launches if given["title"] == f"crew: {slug}"]
    return given


def head_of(kitchen, slug):
    text = (kitchen.home / "tasks" / f"{slug}.md").read_text()
    return text.partition("\n## ")[0].splitlines()


def test_a_row_that_builds_on_an_open_pull_request_launches_stacked_on_its_branch(kitchen):
    """The fl-statechart replay of bug 3, the other way round: the entry, and a follow-up whose
    brief builds on it, each with your go. Once the entry's crew opens its pull request, the
    next pass launches the follow-up on the entry's branch, and its brief says what it is
    stacked on. It gets no `Green main:` line: its base is the entry's branch, not main."""
    kitchen.config(max_running=8)
    assert queue_add(kitchen, "one")[0] == 0
    assert go(kitchen, "one")[0] == 0
    built = brief("two", "Builds on: one: the table one adds\n")
    assert queue_add(kitchen, "two", "--depends", "one", text=built)[0] == 0
    assert go(kitchen, "two")[0] == 0
    kitchen.poll()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: one"]
    assert rows(kitchen)["two"]["status"] == "queued"

    pull = {**kitchen.opened("one", 10), "headRefName": "one-branch"}
    with (kitchen.home / "tasks" / "one.md").open("a") as one:
        one.write(f"\n## Result\nBranch: one-branch   Pull request: {pull['url']}\n")
    kitchen.set("open.json", [pull])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: one", "crew: two"]
    assert launch_of(kitchen, "two")["workspaceStrategy"]["baseRef"] == "one-branch"
    head = head_of(kitchen, "two")
    assert "Stacked on: one one-branch" in head
    assert not [line for line in head if line.startswith("Green main:")]
    assert "Stacked on: one one-branch" in launch_of(kitchen, "two")["message"]
    assert rows(kitchen)["two"]["status"] != "queued"


def test_a_row_whose_depends_have_two_open_pull_requests_waits_until_one_is_left(kitchen):
    """A stack sits on one branch: a row that builds on two rows whose pull requests are both
    open waits, and launches stacked on the one left open once the other has merged."""
    kitchen.config(max_running=8)
    for slug in ("one", "two"):
        assert queue_add(kitchen, slug)[0] == 0
        assert go(kitchen, slug)[0] == 0
    built = brief("three", "Builds on: one: its table; two: its parser\n")
    assert queue_add(kitchen, "three", "--depends", "one,two", text=built)[0] == 0
    assert go(kitchen, "three")[0] == 0
    kitchen.poll()
    kitchen.set("open.json", [kitchen.opened("one", 10), kitchen.opened("two", 11)])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert "crew: three" not in [given["title"] for given in kitchen.t3.launches]

    kitchen.set("open.json", [kitchen.opened("two", 11)])
    kitchen.set("merged.json", [kitchen.merged("one", 10, "a" * 40)])
    kitchen.poll(NOW + timedelta(minutes=6))
    assert launch_of(kitchen, "three")["workspaceStrategy"]["baseRef"] == "two"
    assert "Stacked on: two two" in head_of(kitchen, "three")


def opened_on(kitchen, slug, **more):
    """Open `slug`'s pull request on the branch `<slug>-branch`, and write it in its Result."""
    pull = {**kitchen.opened(slug, 10), "headRefName": f"{slug}-branch", **more}
    with (kitchen.home / "tasks" / f"{slug}.md").open("a") as one:
        one.write(f"\n## Result\nBranch: {slug}-branch   Pull request: {pull['url']}\n")
    kitchen.set("open.json", [pull])


def on_branch(text):
    return text.replace(
        "Pull request: open one when done", "Pull request: open one against release/x"
    )


def test_a_row_that_builds_on_a_main_row_launches_on_its_branch_once_that_row_merged(kitchen):
    """The macos home's #456: a row on `release/x` that builds on a row on main is no link of its
    stack, since a stack sits on one branch and the two go on different ones. While that row's
    pull request is open the row waits, and once it merged the row launches on its integration
    branch with no `Stacked on:` line."""
    kitchen.config(max_running=8)
    assert queue_add(kitchen, "one")[0] == 0
    assert go(kitchen, "one")[0] == 0
    built = on_branch(brief("two", "Builds on: one: the table one adds\n"))
    assert queue_add(kitchen, "two", "--depends", "one", text=built)[0] == 0
    assert go(kitchen, "two")[0] == 0
    kitchen.poll()
    opened_on(kitchen, "one")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert "crew: two" not in [given["title"] for given in kitchen.t3.launches]

    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("one", 10, "a" * 40)])
    kitchen.poll(NOW + timedelta(minutes=6))
    assert launch_of(kitchen, "two")["workspaceStrategy"]["baseRef"] == "release/x"
    head = head_of(kitchen, "two")
    assert not [line for line in head if line.startswith("Stacked on:")]


def test_a_branch_row_that_builds_on_a_row_on_its_branch_launches_stacked_on_its_branch(kitchen):
    kitchen.config(max_running=8)
    assert queue_add(kitchen, "one", text=on_branch(brief("one")))[0] == 0
    assert go(kitchen, "one")[0] == 0
    built = on_branch(brief("two", "Builds on: one: the table one adds\n"))
    assert queue_add(kitchen, "two", "--depends", "one", text=built)[0] == 0
    assert go(kitchen, "two")[0] == 0
    kitchen.poll()
    opened_on(kitchen, "one", baseRefName="release/x")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert launch_of(kitchen, "two")["workspaceStrategy"]["baseRef"] == "one-branch"
    assert "Stacked on: one one-branch" in head_of(kitchen, "two")
