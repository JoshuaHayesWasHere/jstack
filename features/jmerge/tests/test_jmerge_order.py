"""A queue row can hold its pull request back from a merge. `jbus queue hold` withdraws the
row's go, and `jbus queue add --merge-after a,b` names the rows whose pull requests merge
first. `jmerge` reads both from the project's `queue.json` (`jmerge.rows`).

The tests run the command as `test_home_merge` runs it, against its fake `gh` and a real
origin. Two pull requests are open, `alpha` (#7) and `beta` (#8), on the one reviewed head,
and the user's home has a jbus config whose project is this checkout.

The project's state can also hold a pull request back because main is red. jbus's
`main.json` names a red tip when its `broken` field holds a tip that is not green. While it
does, only the fix of that main, the brief `main-red-<sha12>`, merges, and every other pull
request waits until main is green."""

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


def queue_of(home, rows, more=""):
    """The jbus config that names this checkout as a project, and that project's queue. `more`
    holds lines of the project's table, such as its migration directory."""
    config = home.user / ".config" / "jbus"
    config.mkdir(parents=True, exist_ok=True)
    (config / "config.toml").write_text(
        'server = "http://127.0.0.1:1"\n\n[[project]]\n'
        f'name = "demo"\ncheckout = "{home.main}"\nprojectId = "p1"\n{more}'
    )
    (config / "config.toml").chmod(0o600)
    state = home.user / ".local" / "state" / "jbus" / "demo"
    state.mkdir(parents=True, exist_ok=True)
    (state / "queue.json").write_text(json.dumps(rows))
    return state / "queue.json"


@pytest.fixture
def two(merged):
    """Open `alpha` and `beta`, which both have a clean review at the pushed head and a green
    check."""
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


DIRECTORY = 'migrations = "db/migrations"\n'
STAMPED = DIRECTORY + 'migration_names = "timestamped"\n'
GAMMA_URL = "https://example.test/pull/9"


def migration(name):
    return f"db/migrations/{name}.up.sql"


def commit_migration(repo, name):
    path = repo / migration(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("select 1;\n")
    merge.git(repo, "add", ".")
    merge.git(repo, "commit", "-q", "-m", name)


def listing(home, *pulls):
    """What GitHub lists: each pull request `(number, url, branch, files, mergeable)` at the one
    head that the fake `gh` merges, with each file `(path, kind)` as GitHub gives it."""
    head = (home.stub / "head").read_text().strip()
    template = json.loads((home.stub / "list.json").read_text())[0]
    listed = []
    for number, url, branch, files, mergeable in pulls:
        listed.append(
            {
                **template,
                "number": number,
                "url": url,
                "headRefName": branch,
                "headRefOid": head,
                "mergeable": mergeable,
                "files": [
                    {"path": path, "additions": 1, "deletions": 0, "changeType": kind}
                    for path, kind in files
                ],
                "changedFiles": len(files),
            }
        )
    (home.stub / "list.json").write_text(json.dumps(listed))


def adds(*names):
    return [(migration(name), "ADDED") for name in names]


@pytest.fixture
def lined(merged):
    """The repo has `0004_start` on main. `alpha` (#7), `beta` (#8) and `gamma` (#9) are
    reviewed clean and green at one head, whose tree holds the migration that `alpha` adds."""
    home, tree = merged.home, merged.tree
    commit_migration(home.main, "0004_start")
    merge.git(home.main, "push", "-q", "origin", "main")
    merge.git(tree, "rebase", "-q", "main")
    commit_migration(tree, "0005_alpha")
    merge.git(tree, "push", "-q", "-f", "origin", "alpha")
    merged.head = merge.git(tree, "rev-parse", "HEAD")
    (home.stub / "head").write_text(f"{merged.head}\n")
    (home.tasks / "alpha.md").write_text(merge.brief(merge.review("clean", merged.head)))
    for slug, url in (("beta", BETA_URL), ("gamma", GAMMA_URL)):
        (home.tasks / f"{slug}.md").write_text(
            merge.brief(merge.review("clean", merged.head))
            .replace(merge.URL, url)
            .replace("# alpha", f"# {slug}")
            .replace("Branch: alpha", f"Branch: {slug}")
        )
    return merged


def pulls(home, alpha=("0005_alpha",), beta=("0005_beta",), mergeable="MERGEABLE"):
    listing(
        home,
        (7, merge.URL, "alpha", adds(*alpha), mergeable),
        (8, BETA_URL, "beta", adds(*beta), "MERGEABLE"),
        (9, GAMMA_URL, "gamma", [("a.txt", "MODIFIED")], "MERGEABLE"),
    )


def starts(said):
    return [" ".join(line.split()[:2]) for line in said]


def test_two_ready_migrations_one_merges_and_the_other_is_renumbered_and_merges_later(lined):
    home = lined.home
    queue_of(home, [], DIRECTORY)
    pulls(home)
    first = lined.run()
    assert starts(first) == ["merged 7", "wait 8", "merged 9"]
    taken = ready.MIGRATION_TAKEN.format(
        name="0005_beta", number="0005", default="main", free="0006"
    )
    assert first[1] == f"wait 8 {BETA_URL}: {taken}"
    pulls(home, beta=("0006_beta",))
    listed = json.loads((home.stub / "list.json").read_text())
    (home.stub / "list.json").write_text(json.dumps(listed[1:2]))
    assert merged_numbers(lined.run()) == [8]


def test_a_look_shows_the_migration_pull_requests_in_order_with_one_let_through(lined):
    queue_of(lined.home, [], DIRECTORY)
    pulls(lined.home)
    said = lined.run("--check")
    assert said[0].startswith(f"ready 7 {lined.head} alpha alpha")
    assert said[1] == f"wait 8 {BETA_URL}: {ready.MIGRATION_MERGING.format(number=7)}"
    assert said[2].startswith(f"ready 9 {lined.head} gamma gamma")
    assert lined.home.stderr == ""


def test_a_pull_request_that_adds_no_migration_is_not_held(lined):
    queue_of(lined.home, [], DIRECTORY)
    pulls(lined.home)
    gamma = lined.run("--check")[2]
    assert gamma.startswith("ready 9 ")


def test_the_declared_order_is_the_order_migration_pull_requests_merge_in(lined):
    rows = [row("alpha", pr="#7", merge_after=["beta"]), row("beta", pr="#8")]
    queue_of(lined.home, rows, DIRECTORY)
    pulls(lined.home, alpha=("0006_alpha",), beta=("0005_beta",))
    said = lined.run("--check")
    assert starts(said)[:2] == ["ready 8", "wait 7"]
    assert said[1] == f"wait 7 {merge.URL}: merges after beta (#8), not merged yet"


def test_a_migration_whose_number_main_has_waits_and_holds_the_ones_behind_it(lined):
    queue_of(lined.home, [], DIRECTORY)
    pulls(lined.home, alpha=("0004_alpha",), beta=("0006_beta",))
    said = lined.run("--check")
    renumber = ready.MIGRATION_TAKEN.format(
        name="0004_alpha", number="0004", default="main", free="0005"
    )
    assert said[0] == f"wait 7 {merge.URL}: {renumber}"
    assert said[1] == f"wait 8 {BETA_URL}: {ready.MIGRATION_REBASING.format(number=7)}"
    assert said[2].startswith("ready 9 ")


def test_a_pull_request_with_several_migrations_is_renumbered_from_the_taken_one_up(lined):
    queue_of(lined.home, [], DIRECTORY)
    pulls(lined.home, alpha=("0004_a", "0005_b"))
    taken = ready.MIGRATION_TAKEN.format(name="0004_a", number="0004", default="main", free="0005")
    assert lined.run("--check")[0] == f"wait 7 {merge.URL}: {taken}"
    pulls(lined.home, alpha=("0005_a", "0006_b"))
    assert lined.run("--check")[0].startswith("ready 7 ")


def test_a_migration_pull_request_in_conflict_holds_the_ones_behind_it(lined):
    queue_of(lined.home, [], DIRECTORY)
    pulls(lined.home, mergeable="CONFLICTING")
    said = lined.run("--check")
    assert said[0] == f"wait 7 {merge.URL}: {ready.CONFLICTS}"
    assert said[1] == f"wait 8 {BETA_URL}: {ready.MIGRATION_REBASING.format(number=7)}"


def test_a_repo_with_timestamped_names_skips_the_number_and_still_merges_one_at_a_time(lined):
    queue_of(lined.home, [], STAMPED)
    pulls(lined.home, alpha=("0004_alpha",), beta=("0004_beta",))
    said = lined.run("--check")
    assert said[0].startswith(f"ready 7 {lined.head} alpha alpha")
    assert said[1] == f"wait 8 {BETA_URL}: {ready.MIGRATION_MERGING.format(number=7)}"


def test_a_repo_that_names_no_migration_directory_holds_nothing(lined):
    queue_of(lined.home, [])
    pulls(lined.home)
    assert [line.split()[0] for line in lined.run("--check")] == ["ready"] * 3


def test_a_file_outside_the_directory_or_not_added_is_no_migration(lined):
    queue_of(lined.home, [], DIRECTORY)
    listing(
        lined.home,
        (7, merge.URL, "alpha", [(migration("0005_alpha"), "MODIFIED")], "MERGEABLE"),
        (8, BETA_URL, "beta", [("docs/0005_beta.up.sql", "ADDED")], "MERGEABLE"),
    )
    assert [line.split()[0] for line in lined.run("--check")] == ["ready"] * 2


def test_pull_requests_with_no_declared_order_go_by_number_and_an_order_runs_through_a_row():
    from jmerge import rows as jrows

    table = [row("a"), row("b", merge_after=["via"]), row("via", merge_after=["c"]), row("c")]
    slugs = {3: "a", 5: "b", 9: "c"}
    assert jrows.merge_order(table, slugs) == [3, 9, 5]
    assert jrows.merge_order(None, slugs) == [3, 5, 9]
    cycle = [row("a", merge_after=["b"]), row("b", merge_after=["a"])]
    assert jrows.merge_order(cycle, {1: "a", 2: "b"}) == [1, 2]


TAKEN = ready.MIGRATION_TAKEN.format(name="0005_x", number="0005", default="main", free="0006")


@pytest.mark.parametrize(
    ("reason", "step"),
    [
        (TAKEN, "rebase"),
        (ready.MIGRATION_MERGING.format(number=7), "check"),
        (ready.MIGRATION_REBASING.format(number=7), "check"),
    ],
)
def test_each_wait_a_migration_gives_lands_on_its_step_and_not_in_unknown(reason, step):
    assert jbus_merge.step(f"wait: {reason}") == step


def mark(home, number, **fields):
    """Change the fields of one listed pull request as GitHub gives them."""
    listed = json.loads((home.stub / "list.json").read_text())
    for one in listed:
        if one["number"] == number:
            one.update(fields)
    (home.stub / "list.json").write_text(json.dumps(listed))


@pytest.mark.parametrize("mergeable", ["CONFLICTING", "MERGEABLE"])
def test_a_draft_migration_pull_request_ahead_holds_none_behind_it(lined, mergeable):
    queue_of(lined.home, [], DIRECTORY)
    pulls(lined.home, alpha=("0004_alpha",), mergeable=mergeable)
    mark(lined.home, 7, isDraft=True)
    said = lined.run("--check")
    assert said[0] == f"wait 7 {merge.URL}: {ready.DRAFT}"
    assert said[1].startswith(f"ready 8 {lined.head} beta beta")


def test_an_unreviewed_migration_pull_request_in_conflict_holds_none_behind_it(lined):
    queue_of(lined.home, [], DIRECTORY)
    pulls(lined.home, mergeable="CONFLICTING")
    (lined.home.tasks / "alpha.md").write_text(merge.brief())
    said = lined.run("--check")
    assert said[0].startswith(f"wait 7 {merge.URL}: ")
    assert not ready.being_rebased(said[0].split(": ", 1)[1])
    assert said[1].startswith(f"ready 8 {lined.head} beta beta")


def test_a_hand_merge_that_takes_the_number_after_the_judgment_has_it_renumbered(
    lined, monkeypatch
):
    from test_jmerge_fresh import repo

    home = lined.home
    queue_of(home, [], DIRECTORY)
    listing(home, (8, BETA_URL, "beta", adds("0005_beta"), "MERGEABLE"))
    listed = json.loads((home.stub / "list.json").read_text())
    for check in listed[0]["statusCheckRollup"]:
        check["startedAt"] = "2000-01-01T00:00:00Z"
    (home.stub / "list.json").write_text(json.dumps(listed))
    one = ready.pull_request(listed[0])
    monkeypatch.setenv("JBUS_CONFIG_DIR", str(home.user / ".config" / "jbus"))
    here = repo(lined, monkeypatch)
    here.line_up([one], "main")
    slug, verb, why, note, judged = here.waits(one, "main")
    assert here.migrations and here.numbers("main") == {4}
    assert (verb, why) == ("", "") and judged is not None and judged.tip
    by_hand = merge.git(home.main, "rev-parse", "HEAD")
    commit_migration(home.main, "0005_by_hand")
    merge.git(home.main, "push", "-q", "origin", "main")
    assert merge.git(home.main, "rev-parse", "HEAD") != by_hand
    taken = ready.MIGRATION_TAKEN.format(
        name="0005_beta", number="0005", default="main", free="0006"
    )
    assert here.merge(one, slug, note, judged) == f"wait 8 {BETA_URL}: {taken}"


RED = "c" * 40
FIX = "main-red-cccccccccccc"
RED_LINE = f"wait 7 {merge.URL}: main is red at cccccccccccc, its fix merges first"


def record(red="", green=""):
    """The record that `mainmoved` keeps of main: the tip, the tip's check, the red tip that the
    record keeps, and the last green tip."""
    if red:
        return {"main": red, "check": "failed", "broken": red, "green": green}
    return {"main": green, "check": "green", "green": green}


def main_says(home, **word):
    """What jbus recorded about the check of the default branch, in `main.json` beside the
    project's queue."""
    state = home.user / ".local" / "state" / "jbus" / "demo"
    state.mkdir(parents=True, exist_ok=True)
    (state / "main.json").write_text(json.dumps(record(**word)) if word else "{}")
    return state / "main.json"


@pytest.fixture
def fix_and_other(two):
    """`alpha` (#7) is an ordinary pull request, and `beta` (#8) is the fix that jbus filed for
    the red main at `cccccccccccc`, with the brief `main-red-cccccccccccc`."""
    (two.home.tasks / "beta.md").rename(two.home.tasks / f"{FIX}.md")
    queue_of(two.home, [row("alpha", pr="#7"), row(FIX, pr="#8")])
    return two


def test_a_red_main_merges_its_fix_and_holds_every_other_pull_request(fix_and_other):
    main_says(fix_and_other.home, red=RED, green="a" * 40)
    said = fix_and_other.run()
    assert said[0] == RED_LINE
    assert merged_numbers(said) == [8]
    assert (fix_and_other.tree.exists(), fix_and_other.branches()[1]) == (True, ["alpha", "main"])


def test_a_hold_for_a_red_main_shows_in_check_and_merges_nothing_but_the_fix(fix_and_other):
    main_says(fix_and_other.home, red=RED, green="a" * 40)
    said = fix_and_other.run("--check")
    assert said[0] == RED_LINE
    assert said[1].startswith("ready ")
    assert merged_numbers(said) == []


def test_a_green_main_lets_both_through(fix_and_other):
    main_says(fix_and_other.home, red="", green="a" * 40)
    assert [line.split()[0] for line in fix_and_other.run("--check")] == ["ready", "ready"]
    assert merged_numbers(fix_and_other.run()) == [7, 8]


def test_a_repo_whose_main_jbus_never_judged_merges_as_it_did(fix_and_other):
    assert [line.split()[0] for line in fix_and_other.run("--check")] == ["ready", "ready"]


def test_the_held_pull_request_merges_once_main_is_green_again(fix_and_other):
    path = main_says(fix_and_other.home, red=RED, green="a" * 40)
    assert merged_numbers(fix_and_other.run()) == [8]
    path.write_text(json.dumps(record(green="d" * 40)))
    listed = json.loads((fix_and_other.home.stub / "list.json").read_text())
    (fix_and_other.home.stub / "list.json").write_text(json.dumps(listed[:1]))
    assert merged_numbers(fix_and_other.run()) == [7]


def test_a_main_the_state_cannot_name_is_no_red_main(fix_and_other):
    main_says(fix_and_other.home).write_text("not json")
    assert [line.split()[0] for line in fix_and_other.run("--check")] == ["ready", "ready"]


def test_the_red_main_wait_lands_on_the_check_step_and_not_in_unknown():
    assert jbus_merge.step(f"wait: {ready.MAIN_RED.format(sha='cccccccccccc')}") == "check"
