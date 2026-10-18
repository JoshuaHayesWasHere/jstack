"""A queue row can hold its pull request back from a merge: `jbus queue hold` takes the go
back, and `jbus queue add --merge-after a,b` names the rows whose pull requests merge
first. `jmerge` reads both from the project's `queue.json` (`jmerge.rows`).

The command is run as `test_home_merge` runs it, against its fake `gh` and a real origin.
Two pull requests are open, `alpha` (#7) and `beta` (#8), on the one reviewed head, and the
user's home has a jbus config whose project is this checkout."""

import json

import pytest

import test_home_merge as merge
from jbus import merge as jbus_merge
from jmerge import ready

BETA_URL = "https://example.test/pull/8"


def row(slug, status="pr", pr="", **more):
    return {
        "slug": slug,
        "priority": 1,
        "depends": [],
        "approved": "his word",
        "status": status,
        "pr": pr,
        **more,
    }


def queue_of(home, rows):
    """The jbus config naming this checkout as a project, and that project's queue."""
    config = home.user / ".config" / "jbus"
    config.mkdir(parents=True, exist_ok=True)
    (config / "config.toml").write_text(
        'server = "http://127.0.0.1:1"\n\n[[project]]\n'
        f'name = "demo"\ncheckout = "{home.main}"\nprojectId = "p1"\n'
    )
    (config / "config.toml").chmod(0o600)
    state = home.user / ".local" / "state" / "jbus" / "demo"
    state.mkdir(parents=True, exist_ok=True)
    (state / "queue.json").write_text(json.dumps(rows))
    return state / "queue.json"


@pytest.fixture
def two(merged):
    """`alpha` and `beta`, both reviewed clean at the pushed head and green."""
    home = merged.home
    (home.tasks / "beta.md").write_text(
        merge.brief(merge.review("clean", merged.head))
        .replace(merge.URL, BETA_URL)
        .replace("# alpha", "# beta")
        .replace("Branch: alpha", "Branch: beta")
    )
    listed = json.loads((home.stub / "list.json").read_text())
    other = {**listed[0], "number": 8, "url": BETA_URL, "headRefName": "beta"}
    (home.stub / "list.json").write_text(json.dumps([listed[0], other]))
    return merged


def merged_numbers(said):
    return [int(line.split()[1]) for line in said if line.startswith("merged ")]


def test_a_pull_request_merges_after_the_one_its_row_names_and_not_before(two):
    path = queue_of(two.home, [row("alpha", pr="#7"), row("beta", pr="#8", merge_after=["alpha"])])
    first = two.run()
    assert merged_numbers(first) == [7]
    assert first[0].startswith("merged 7 alpha ")
    assert first[1] == (f"wait 8 {BETA_URL}: merges after alpha (#7), not merged yet")
    table = json.loads(path.read_text())
    table[0]["status"] = "merged"
    path.write_text(json.dumps(table))
    listed = json.loads((two.home.stub / "list.json").read_text())
    (two.home.stub / "list.json").write_text(json.dumps(listed[1:]))
    second = two.run()
    assert merged_numbers(second) == [8]


def test_a_pull_request_whose_predecessor_has_no_pull_request_yet_says_so(two):
    queue_of(
        two.home,
        [row("alpha", status="running"), row("beta", pr="#8", merge_after=["alpha"])],
    )
    said = two.run("--check")
    assert said[1] == (
        f"wait 8 {BETA_URL}: merges after alpha (no pull request yet), not merged yet"
    )


@pytest.mark.parametrize("over", ["merged", "done"])
def test_a_row_that_is_over_holds_nothing_back(two, over):
    queue_of(
        two.home,
        [row("alpha", status=over, pr="#7"), row("beta", pr="#8", merge_after=["alpha"])],
    )
    assert merged_numbers(two.run("--check")) == []
    assert [line.split()[0] for line in two.run("--check")] == ["ready", "ready"]


def test_a_pull_request_whose_row_is_held_is_not_merged(two):
    queue_of(
        two.home,
        [row("alpha", pr="#7", approved="", held=True), row("beta", pr="#8")],
    )
    said = two.run()
    assert said[0] == f"wait 7 {merge.URL}: {ready.ROW_HELD}"
    assert merged_numbers(said) == [8]
    assert (two.tree.exists(), two.branches()[1]) == (True, ["alpha", "main"])


def test_a_row_that_was_never_approved_is_no_held_row(two):
    queue_of(two.home, [row("alpha", pr="#7", approved=""), row("beta", pr="#8")])
    assert merged_numbers(two.run("--check")) == []
    assert [line.split()[0] for line in two.run("--check")] == ["ready", "ready"]


def test_a_repo_with_no_queue_merges_as_it_did(two):
    assert [line.split()[0] for line in two.run("--check")] == ["ready", "ready"]


def test_a_queue_that_cannot_be_read_merges_nothing(two):
    path = queue_of(two.home, [])
    path.write_text("not json")
    said = two.run()
    assert said == [
        f"wait 7 {merge.URL}: {ready.QUEUE_UNREADABLE}",
        f"wait 8 {BETA_URL}: {ready.QUEUE_UNREADABLE}",
    ]
    assert two.untouched()


def test_a_queue_file_the_filesystem_will_not_give_merges_nothing(two):
    path = queue_of(two.home, [])
    path.unlink()
    path.mkdir()
    said = two.run()
    assert said == [
        f"wait 7 {merge.URL}: {ready.QUEUE_UNREADABLE}",
        f"wait 8 {BETA_URL}: {ready.QUEUE_UNREADABLE}",
    ]
    assert two.untouched()


@pytest.mark.parametrize(
    ("reason", "step"),
    [
        (ready.ROW_HELD, "hold"),
        (ready.MERGES_AFTER.format(slug="alpha", open="#144"), "check"),
        (ready.MERGES_AFTER.format(slug="alpha", open="no pull request yet"), "check"),
        (ready.QUEUE_UNREADABLE, "hold"),
    ],
)
def test_each_wait_the_queue_gives_lands_on_its_step_and_not_in_unknown(reason, step):
    assert jbus_merge.step(f"wait: {reason}") == step
