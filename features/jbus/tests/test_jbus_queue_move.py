"""`jbus queue move <slug> --home <scope>` gives a row to another child home, with its go.

A row's home is its brief's `Home:` line, which every send about the row reads again. The move
rewrites that line in the brief jbus stores and in the home's copy, keeps the go (a go covers what
the brief asks, not whom it is sent to), says so on the go's line, and logs the move. The tests
run the real command, `jbus.asks`'s `queue move` over `jbus.queue.move` and
`jbus.blockers.rehome`, and the real pass, against the kitchen's fakes."""

import json

import pytest

from jbriefs import home as homes
from jbus import blockers, queue
from jmerge import judgement
from test_jbus_clock import N, to
from test_jbus_expedite import DONE, NO_REVIEW, URL, Short
from test_jbus_kitchen import RAN
from test_jbus_leftover import home
from test_jbus_queue import add, brief, rows
from test_jbus_row_ends import result, sends


def move(kitchen, slug, scope):
    return kitchen.main("--project", "demo", "queue", "move", slug, "--home", scope)


def stored(kitchen, slug):
    return queue.brief_path(kitchen.state, slug).read_text()


def verified(kitchen, slug):
    """The row's go as `jbus queue verify` prints it, which exits 1 where the go does not hold."""
    return json.loads(kitchen.main("--project", "demo", "queue", "verify", slug)[1])


@pytest.fixture
def homes_of(kitchen):
    """The root home and two child homes, flow and pantry, each with a running thread."""
    return {
        name: home(kitchen, scope)["threadId"]
        for name, scope in (("root", ""), ("flow", "flow"), ("pantry", "pantry"))
    }


def test_a_move_rewrites_the_home_line_keeps_the_go_by_rule_and_logs_the_move(kitchen, homes_of):
    add(kitchen, "alpha", text=brief("alpha").replace("Home: uncategorized", "Home: flow"))
    copy = kitchen.home / "tasks/alpha.md"
    copy.write_text(stored(kitchen, "alpha") + "Thread: mcp:crew\n" + result())
    was = verified(kitchen, "alpha")
    assert was["holds"]

    code, said = move(kitchen, "alpha", "pantry")

    line = f"moved alpha from the flow home to the pantry home, {RAN} by the demo home"
    assert (code, said.splitlines()[0]) == (0, f"{line}, its go carried: {queue.MOVE_RULE}")
    assert homes.named(stored(kitchen, "alpha")) == "pantry"
    assert homes.named(copy.read_text()) == "pantry"
    assert copy.read_text().endswith("Thread: mcp:crew\n" + result())
    now = verified(kitchen, "alpha")
    assert now["holds"] and now["approval"] == was["approval"]
    assert now["approved"] == (
        f"{was['approved']}; carried from the flow home to the pantry home by a move, {RAN} by "
        f"the demo home: {queue.MOVE_RULE}"
    )
    (event,) = kitchen.events("move")
    assert (event["slug"], event["line"], event["loud"]) == (
        "alpha",
        f"queue demo: {said.splitlines()[0]}",
        "quiet",
    )


def test_a_second_move_to_the_same_home_moves_nothing_and_logs_nothing(kitchen, homes_of):
    add(kitchen, "alpha")
    copy = kitchen.home / "tasks/alpha.md"
    copy.write_text(stored(kitchen, "alpha"))
    assert move(kitchen, "alpha", "flow")[0] == 0
    code, said = move(kitchen, "alpha", "flow")
    assert (code, said.splitlines()[0]) == (0, "alpha is the flow home's already: nothing is moved")
    assert homes.named(copy.read_text()) == "flow"
    assert len(kitchen.events("move")) == 1


def test_a_new_go_after_a_move_is_not_said_to_be_carried(kitchen, homes_of):
    add(kitchen, "alpha")
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert kitchen.main("--project", "demo", "queue", "hold", "alpha")[0] == 0
    argv = ["queue", "approve", "alpha", "--word", kitchen.word()]
    assert kitchen.main("--project", "demo", *argv)[0] == 0
    assert "carried" not in verified(kitchen, "alpha")["approved"]


def test_a_row_with_no_go_moves_and_has_none_to_carry(kitchen, homes_of):
    add(kitchen, "alpha", approve=False)
    code, said = move(kitchen, "alpha", "pantry")
    assert (code, said.splitlines()[0].endswith(", it has no go to carry")) == (0, True)
    assert verified(kitchen, "alpha")["approved"] == ""


@pytest.mark.parametrize(
    "scope, refused",
    [
        (
            "root",
            "refused: root is the root home, and a row moves only to a child home: name one "
            "of its scopes",
        ),
        (
            "docs",
            "refused: Home: line names docs, which is no home of demo: name uncategorized or "
            "the row's scope (flow, pantry): nothing is moved",
        ),
    ],
)
def test_a_move_to_the_root_or_to_no_scope_is_refused_and_changes_nothing(
    kitchen, homes_of, scope, refused
):
    add(kitchen, "alpha", text=brief("alpha").replace("Home: uncategorized", "Home: flow"))
    before = (stored(kitchen, "alpha"), (kitchen.state / "queue.json").read_text())
    assert move(kitchen, "alpha", scope) == (1, refused + "\n")
    assert (stored(kitchen, "alpha"), (kitchen.state / "queue.json").read_text()) == before
    assert kitchen.events("move") == []


def test_a_move_to_the_root_by_its_thread_id_is_refused_too(kitchen, homes_of):
    add(kitchen, "alpha", text=brief("alpha").replace("Home: uncategorized", "Home: flow"))
    code, said = move(kitchen, "alpha", homes_of["root"])
    assert code == 1 and said.startswith(f"refused: {homes_of['root']} is the root home")


def test_a_row_that_merged_stays_where_it_is(kitchen, homes_of):
    add(kitchen, "alpha")
    kept = rows(kitchen)
    kept["alpha"]["status"] = "merged"
    (kitchen.state / "queue.json").write_text(json.dumps(list(kept.values())))
    assert move(kitchen, "alpha", "flow") == (
        1,
        "refused: alpha is merged, and a row that is over stays\n",
    )


def test_a_fix_row_takes_its_try_to_its_new_homes_ledger(kitchen, homes_of):
    fix = "Fix of: check:beta\nWhen green: `check` passes on the fix's head\n"
    add(kitchen, "alpha", text=brief("alpha", fix))
    catchall = homes.catchall(kitchen.home)
    assert blockers.tries(catchall, "check:beta")
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert blockers.tries(catchall, "check:beta") == []
    assert [one["slug"] for one in blockers.tries(kitchen.home / "flow", "check:beta")] == ["alpha"]


FIX = "Fix of: check:beta\nWhen green: `check` passes on the fix's head\n"


def slugs(directory):
    return [one["slug"] for one in blockers.tries(directory, "check:beta")]


def test_a_fix_rows_move_cut_short_before_its_try_is_carried_carries_it_when_run_again(
    kitchen, homes_of
):
    add(kitchen, "alpha", text=brief("alpha", FIX))
    catchall = homes.catchall(kitchen.home)
    with pytest.MonkeyPatch.context() as cut_short:
        cut_short.setattr(blockers, "rehome", lambda *_: None)
        assert move(kitchen, "alpha", "flow")[0] == 0
    assert (slugs(catchall), slugs(kitchen.home / "flow")) == (["alpha"], [])
    code, said = move(kitchen, "alpha", "flow")
    assert (code, said.splitlines()[0]) == (0, "alpha is the flow home's already: nothing is moved")
    assert (slugs(catchall), slugs(kitchen.home / "flow")) == ([], ["alpha"])


def test_a_fix_rows_try_cut_short_between_its_two_ledgers_is_carried_once(kitchen, homes_of):
    add(kitchen, "alpha", text=brief("alpha", FIX))
    catchall = homes.catchall(kitchen.home)
    kept = (catchall / blockers.LEDGER).read_text()
    assert move(kitchen, "alpha", "flow")[0] == 0
    (catchall / blockers.LEDGER).write_text(kept)
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert (slugs(catchall), slugs(kitchen.home / "flow")) == ([], ["alpha"])


def test_a_fix_row_moved_twice_carries_its_try_once(kitchen, homes_of):
    add(kitchen, "alpha", text=brief("alpha", FIX))
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert move(kitchen, "alpha", "pantry")[0] == 0
    assert move(kitchen, "alpha", "pantry")[0] == 0
    assert (slugs(kitchen.home / "flow"), slugs(kitchen.home / "pantry")) == ([], ["alpha"])
    assert slugs(homes.catchall(kitchen.home)) == []


def test_a_fix_row_with_no_try_counted_moves_with_none(kitchen, homes_of):
    fix = "Fix of: check:beta\nWhen green: `check` passes on the fix's head\n"
    add(kitchen, "alpha", text=brief("alpha", fix))
    (homes.catchall(kitchen.home) / blockers.LEDGER).write_text("{}")
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert blockers.tries(kitchen.home / "flow", "check:beta") == []


def test_a_brief_that_names_no_home_gets_the_line_above_its_first_section(kitchen, homes_of):
    add(kitchen, "alpha")
    named = stored(kitchen, "alpha").replace("Home: uncategorized\n", "")
    queue.brief_path(kitchen.state, "alpha").write_text(named + "\n## Result\nStatus: done")
    assert move(kitchen, "alpha", "flow")[0] == 0
    head, section = stored(kitchen, "alpha").split("## Result")
    assert (head.endswith("Home: flow\n"), section) == (True, "\nStatus: done")
    add(kitchen, "beta")
    queue.brief_path(kitchen.state, "beta").write_text(
        stored(kitchen, "beta").replace("Home: uncategorized\n", "").rstrip("\n")
    )
    assert move(kitchen, "beta", "flow")[0] == 0
    assert stored(kitchen, "beta").endswith("\nHome: flow\n")


def test_a_row_from_before_that_names_the_root_has_both_copies_named_for_its_home(
    kitchen, homes_of
):
    """A row queued before `add` refused `Home: root` still says it. jbus reads it as the
    catch-all's, and a move there names that home in jbus's copy under `briefs/` and in the
    home's copy under `tasks/` alike, its go untouched; run again, it moves nothing."""
    add(kitchen, "alpha")
    path = queue.brief_path(kitchen.state, "alpha")
    path.write_text(stored(kitchen, "alpha").replace("Home: uncategorized\n", "Home: root\n"))
    copy = kitchen.home / "tasks/alpha.md"
    copy.write_text(stored(kitchen, "alpha"))
    was = verified(kitchen, "alpha")
    assert move(kitchen, "alpha", "uncategorized")[0] == 0
    assert [homes.named(one.read_text()) for one in (path, copy)] == ["uncategorized"] * 2
    assert verified(kitchen, "alpha")["approved"] == was["approved"]
    code, said = move(kitchen, "alpha", "uncategorized")
    assert (code, said.splitlines()[0]) == (
        0,
        "alpha is the uncategorized home's already: nothing is moved",
    )


def test_a_row_with_no_brief_is_refused(kitchen, homes_of):
    add(kitchen, "alpha")
    queue.brief_path(kitchen.state, "alpha").unlink()
    assert move(kitchen, "alpha", "flow") == (1, "refused: alpha has no brief, add it again\n")


def test_a_move_cut_short_before_the_homes_copy_finishes_when_run_again(kitchen, homes_of):
    add(kitchen, "alpha")
    copy = kitchen.home / "tasks/alpha.md"
    copy.write_text(stored(kitchen, "alpha"))
    assert move(kitchen, "alpha", "flow")[0] == 0
    copy.write_text(copy.read_text().replace("Home: flow", "Home: uncategorized"))
    code, said = move(kitchen, "alpha", "flow")
    assert (code, said.splitlines()[0]) == (0, f"moved alpha's copy at {copy} to the flow home")
    assert homes.named(copy.read_text()) == "flow"
    assert len(kitchen.events("move")) == 1


def test_a_go_bound_to_the_whole_text_still_holds_after_a_move(kitchen, homes_of):
    """A go jbus recorded before its sha left out the `Home:` line binds the whole text, which
    the move changes, so the move binds that go to the moved brief."""
    add(kitchen, "alpha")
    table = json.loads((kitchen.state / "queue.json").read_text())
    for column in ("brief_sha", "scope", "meaning"):
        table[0]["approval"].pop(column)
    table[0]["brief_sha"] = judgement.sha(stored(kitchen, "alpha"))
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    assert verified(kitchen, "alpha")["holds"]
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert verified(kitchen, "alpha")["holds"]


def test_a_moved_running_rows_result_wake_and_stall_reach_its_new_home(short, kitchen):
    """Alpha runs in the root home's care; the root moves it to pantry. The crew's next Result
    is sent where `jbus home` says, and the stall its wait comes to wakes pantry, not the root."""
    root, pantry = home(kitchen), home(kitchen, "pantry")
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    task = kitchen.home / "tasks/alpha.md"

    assert move(kitchen, "alpha", "pantry")[0] == 0
    code, said = kitchen.main("home", str(task))
    assert (code, said) == (0, f"{pantry['threadId']}\n")

    short.launched = task.read_text().split(DONE.format(url=URL))[0]
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    short.passes(2 * N)
    (told,) = to(kitchen, pantry)
    assert told.startswith("jbus: 1 new for this home in demo") and "- stall alpha: " in told
    assert to(kitchen, root) == []


def test_a_moved_rows_leftover_wakes_its_new_home(kitchen, homes_of):
    add(kitchen, "alpha")
    kitchen.brief("alpha", "Home: uncategorized\n" + result("the docs"))
    kitchen.t3.thread("alpha", "completed")
    assert move(kitchen, "alpha", "flow")[0] == 0
    kitchen.poll()
    went = [one["threadId"] for one in sends(kitchen) if "- left alpha:" in one["message"]]
    assert went == [homes_of["flow"]]


@pytest.fixture
def short(kitchen):
    return Short(kitchen)
