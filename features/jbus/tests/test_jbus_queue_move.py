"""`jbus queue move <slug> --home <scope>` gives a row to another child home, with its go.

A row's home is its brief's `Home:` line, which every send about the row reads again. The move
rewrites that line in the brief jbus stores and in the home's copy, keeps the go (a go covers what
the brief asks, not whom it is sent to), says so on the go's line, and logs the move. The tests
run the real command, and the real pass, against the kitchen's fakes."""

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
    add(kitchen, "alpha", text=brief("alpha").replace("Home: root", "Home: flow"))
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
    assert move(kitchen, "alpha", "flow")[0] == 0
    code, said = move(kitchen, "alpha", "flow")
    assert (code, said.splitlines()[0]) == (0, "alpha is the flow home's already: nothing is moved")
    assert len(kitchen.events("move")) == 1


def test_a_new_go_after_a_move_is_not_said_to_be_carried(kitchen, homes_of):
    add(kitchen, "alpha")
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert kitchen.main("--project", "demo", "queue", "hold", "alpha")[0] == 0
    sha = judgement.brief_sha(stored(kitchen, "alpha"))[:12]
    argv = ["queue", "approve", "alpha", "--word", kitchen.word(), "--sha", sha]
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
            "refused: Home: line names docs, which is no home of demo: name root or the "
            "row's scope (flow, pantry): nothing is moved",
        ),
    ],
)
def test_a_move_to_the_root_or_to_no_scope_is_refused_and_changes_nothing(
    kitchen, homes_of, scope, refused
):
    add(kitchen, "alpha", text=brief("alpha").replace("Home: root", "Home: flow"))
    before = (stored(kitchen, "alpha"), (kitchen.state / "queue.json").read_text())
    assert move(kitchen, "alpha", scope) == (1, refused + "\n")
    assert (stored(kitchen, "alpha"), (kitchen.state / "queue.json").read_text()) == before
    assert kitchen.events("move") == []


def test_a_move_to_the_root_by_its_thread_id_is_refused_too(kitchen, homes_of):
    add(kitchen, "alpha", text=brief("alpha").replace("Home: root", "Home: flow"))
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
    assert blockers.tries(kitchen.home, "check:beta")
    assert move(kitchen, "alpha", "flow")[0] == 0
    assert blockers.tries(kitchen.home, "check:beta") == []
    assert [one["slug"] for one in blockers.tries(kitchen.home / "flow", "check:beta")] == ["alpha"]


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
    kitchen.brief("alpha", "Home: root\n" + result("the docs"))
    kitchen.t3.thread("alpha", "completed")
    assert move(kitchen, "alpha", "flow")[0] == 0
    kitchen.poll()
    went = [one["threadId"] for one in sends(kitchen) if "- left alpha:" in one["message"]]
    assert went == [homes_of["flow"]]


@pytest.fixture
def short(kitchen):
    return Short(kitchen)
