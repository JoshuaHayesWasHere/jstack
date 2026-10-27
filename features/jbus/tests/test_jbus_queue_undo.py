"""A home undoes its own row: `jbus queue add` refuses a second row for a brief already queued,
`jbus queue rename` moves an unlaunched row to a new slug with its go, and `jbus queue withdraw`,
or a `jbus queue remove` by anyone but the user, takes out a row that never launched. The tests
run the real command against the faked T3 Code server and `gh` of `test_jbus_kitchen.py`."""

import json

import pytest

import jbus
from jbus import queue
from test_jbus_kitchen import NOW, RAN, Kitchen
from test_jbus_queue import add, brief, go, rows
from test_jbus_row_history import transitions

AT = "2026-10-12 10:58 ET"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    monkeypatch.setattr(queue, "clock", lambda: NOW)
    yield made
    made.close()


def again(slug, under):
    """Return `slug`'s brief with its head line naming `under`: the same brief under another
    slug."""
    return brief(slug).replace(f"# {slug}:", f"# {under}:", 1)


def queue_(kitchen, *argv, stdin=""):
    return kitchen.main("--project", "demo", "queue", *argv, stdin=stdin)


def stored(kitchen, slug):
    path = queue.brief_path(kitchen.state, slug)
    return path.read_text() if path.exists() else None


def table(kitchen, slug, **columns):
    """Set columns of a row as a pass would, where no command writes them."""
    kept = rows(kitchen)
    kept[slug].update(columns)
    jbus.write_json(kitchen.state / "queue.json", list(kept.values()))


def gone(kitchen):
    return jbus.read_json(kitchen.state / "removed.json", {})


@pytest.mark.parametrize(
    "status, columns",
    [
        ("queued", {}),
        ("held", {}),
        ("gate", {"status": "gate"}),
        ("launched", {"status": "launched", "thread": "mcp:thread-1"}),
        ("running", {"status": "running", "thread": "mcp:thread-1"}),
        ("pr", {"status": "pr", "thread": "mcp:thread-1", "pr": "9"}),
    ],
)
def test_add_refuses_a_brief_whose_body_another_live_row_has(kitchen, status, columns):
    add(kitchen, "alpha")
    if status == "held":
        assert queue_(kitchen, "hold", "alpha")[0] == 0
    if columns:
        table(kitchen, "alpha", **columns)
    before = (kitchen.state / "queue.json").read_text()
    code, said = queue_(kitchen, "add", "beta", "--priority", "1", stdin=again("alpha", "beta"))
    assert (code, said) == (
        1,
        f"refused: beta's brief is alpha's ({status}): rename by "
        "`jbus queue rename alpha beta`, or withdraw one\n",
    )
    assert (kitchen.state / "queue.json").read_text() == before
    assert stored(kitchen, "beta") is None


def test_add_takes_the_same_slug_again_another_brief_and_a_brief_whose_twin_is_over(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "alpha", priority=4, approve=False)
    add(kitchen, "beta", approve=False)
    table(kitchen, "beta", status="merged")
    add(kitchen, "gamma", approve=False, text=again("beta", "gamma"))
    assert sorted(rows(kitchen)) == ["alpha", "beta", "gamma"]
    assert rows(kitchen)["alpha"]["priority"] == 4


def test_rename_moves_an_unlaunched_row_with_its_columns_and_its_go(kitchen):
    add(kitchen, "gamma", approve=False)
    text = brief("alpha", "Builds on: gamma\n")
    argv = ["--priority", "3", "--depends", "gamma", "--merge-after", "gamma", "--entry", "plan-a"]
    assert queue_(kitchen, "add", "alpha", *argv, stdin=text)[0] == 0
    assert go(kitchen, "alpha")[0] == 0
    was = rows(kitchen)["alpha"]
    code, said = queue_(kitchen, "rename", "alpha", "delta")
    assert code == 0, said
    renamed = text.replace("# alpha:", "# delta:", 1)
    assert said.splitlines()[0] == (
        f"renamed alpha to delta: brief {queue.brief_sha(renamed)[:12]}, its go holds"
    )
    assert "alpha" not in rows(kitchen)
    row = rows(kitchen)["delta"]
    for column in ("priority", "depends", "merge_after", "entry", "approved"):
        assert row[column] == was[column], column
    assert row["approval"]["words"] == was["approval"]["words"]
    assert stored(kitchen, "alpha") is None
    assert stored(kitchen, "delta") == renamed
    code, said = queue_(kitchen, "verify", "delta")
    assert (code, json.loads(said)["holds"]) == (0, True)
    assert gone(kitchen) == {"alpha": {"at": RAN, "by": "the demo home", "why": "renamed to delta"}}
    code, said = queue_(kitchen, "add", "alpha", "--priority", "1", stdin=brief("alpha"))
    assert code == 1 and "a removed slug is not added again" in said


def test_a_renamed_row_that_was_its_own_plan_entry_stays_in_that_entry(kitchen):
    add(kitchen, "alpha")
    assert queue_(kitchen, "rename", "alpha", "delta")[0] == 0
    assert queue.entry(rows(kitchen)["delta"]) == "alpha"


def test_a_rename_that_dies_before_it_retires_the_old_slug_keeps_the_row_and_its_go(
    kitchen, monkeypatch
):
    add(kitchen, "alpha")
    written = queue.write_json

    def dies(where, value):
        if where == queue.removed_path(kitchen.state):
            raise OSError("the machine went down")
        written(where, value)

    monkeypatch.setattr(queue, "write_json", dies)
    with pytest.raises(OSError):
        queue.rename(kitchen.state, "alpha", "delta", RAN, "the demo home")
    assert list(rows(kitchen)) == ["delta"] and gone(kitchen) == {}
    code, said = queue_(kitchen, "verify", "delta")
    assert (code, json.loads(said)["holds"]) == (0, True)


@pytest.mark.parametrize(
    "scene, says",
    [
        ("launched", "refused: alpha launched, and its crew has it"),
        ("named", "refused: beta names alpha, so alpha keeps its slug"),
        ("taken", "refused: the queue has a row beta"),
        ("slug", "refused: Delta is not a slug"),
        ("none", "refused: the queue has no row nope"),
    ],
)
def test_rename_refuses_a_launched_row_a_named_one_and_a_slug_in_use(kitchen, scene, says):
    add(kitchen, "alpha")
    old, new = "alpha", "delta"
    if scene == "launched":
        table(kitchen, "alpha", status="running", thread="mcp:thread-1")
    elif scene == "named":
        add(kitchen, "beta", depends="alpha", approve=False)
    elif scene == "taken":
        add(kitchen, "beta", approve=False)
        new = "beta"
    elif scene == "slug":
        new = "Delta"
    elif scene == "none":
        old = "nope"
    before = (kitchen.state / "queue.json").read_text()
    code, said = queue_(kitchen, "rename", old, new)
    assert (code, said) == (1, f"{says}\n")
    assert (kitchen.state / "queue.json").read_text() == before
    assert stored(kitchen, "alpha") is not None and gone(kitchen) == {}


@pytest.mark.parametrize(
    "verb", [["withdraw", "alpha", "--why", "no"], ["rename", "alpha", "delta"]]
)
def test_withdraw_and_rename_refuse_a_row_whose_launch_t3_code_has_not_answered(kitchen, verb):
    add(kitchen, "alpha")
    record = kitchen.state_dir / "launches" / "demo" / "alpha" / "0123456789ab.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"state": "intent"}')
    assert queue_(kitchen, *verb) == (1, "refused: alpha launched, and its crew has it\n")
    assert list(rows(kitchen)) == ["alpha"] and gone(kitchen) == {}


@pytest.mark.parametrize("status", ["queued", "held", "gate"])
def test_withdraw_takes_out_an_unlaunched_row_by_the_home_that_ran_it(kitchen, status):
    add(kitchen, "alpha")
    if status == "held":
        assert queue_(kitchen, "hold", "alpha")[0] == 0
    elif status == "gate":
        table(kitchen, "alpha", status="gate")
    code, said = queue_(kitchen, "withdraw", "alpha", "--why", "a second row for one brief")
    assert code == 0, said
    was = "gate" if status == "gate" else "queued"
    kept = kitchen.state / "removed" / f"alpha.{queue.brief_sha(brief('alpha'))[:12]}.md"
    assert said.splitlines()[0] == (
        f"removed alpha: was {was}, {RAN} by the demo home, brief kept at {kept}: "
        "a second row for one brief"
    )
    assert "alpha" not in rows(kitchen)
    assert gone(kitchen) == {
        "alpha": {"at": RAN, "by": "the demo home", "why": "a second row for one brief"}
    }
    (move,) = transitions(kitchen)
    assert (move["by"], move["why"], move["to"]) == (
        "the demo home",
        "a second row for one brief",
        "removed",
    )


@pytest.mark.parametrize(
    "scene, says",
    [
        ("launched", "refused: alpha launched, and its crew has it"),
        ("waited", "refused: beta wait on alpha: remove them first"),
        ("why", "the following arguments are required: --why"),
    ],
)
def test_withdraw_refuses_a_launched_row_and_one_another_row_waits_on(kitchen, scene, says):
    add(kitchen, "alpha")
    argv = ["withdraw", "alpha", "--why", "not needed"]
    if scene == "launched":
        table(kitchen, "alpha", status="launched", thread="mcp:thread-1")
    elif scene == "waited":
        add(kitchen, "beta", depends="alpha", approve=False)
    elif scene == "why":
        argv = argv[:2]
    before = (kitchen.state / "queue.json").read_text()
    code, said = queue_(kitchen, *argv)
    assert code and says in said
    assert (kitchen.state / "queue.json").read_text() == before
    assert gone(kitchen) == {} and transitions(kitchen) == []


def test_remove_by_anyone_but_the_user_withdraws_a_row_that_never_launched(kitchen):
    add(kitchen, "alpha")
    code, said = queue_(kitchen, "remove", "alpha", "--by", "flow home", "--at", AT)
    assert code == 0, said
    assert said.splitlines()[0].startswith(
        f"removed alpha: was queued, {AT} by the demo home, brief kept at "
    )
    assert said.splitlines()[0].endswith(
        ": withdrawn, not removed: only user removes a row, and alpha never launched"
    )
    assert "alpha" not in rows(kitchen)
    assert gone(kitchen)["alpha"]["by"] == "the demo home"


def test_remove_by_anyone_but_the_user_of_a_launched_row_is_refused_naming_the_user(kitchen):
    add(kitchen, "alpha")
    table(kitchen, "alpha", status="running", thread="mcp:thread-1")
    before = (kitchen.state / "queue.json").read_text()
    code, said = queue_(kitchen, "remove", "alpha", "--by", "flow home", "--at", AT)
    assert (code, said) == (
        1,
        "refused: alpha launched, and only user removes a row that launched, not flow home\n",
    )
    assert (kitchen.state / "queue.json").read_text() == before


def test_the_flow_homes_morning_the_home_undoes_its_own_second_row(kitchen, tmp_path):
    """2026-10-27: the flow home queued and approved n1-slot-strays, then queued the same brief
    as fl-n1-slot-strays to rename it, and asked the user to remove the first. Now the second add
    is refused, and the home renames and withdraws by itself."""
    flow = tmp_path / "flow"
    flow.mkdir()
    kitchen.monkeypatch.chdir(flow)
    add(kitchen, "n1-slot-strays")
    code, said = queue_(
        kitchen,
        "add",
        "fl-n1-slot-strays",
        "--priority",
        "1",
        stdin=again("n1-slot-strays", "fl-n1-slot-strays"),
    )
    assert code == 1
    assert "rename by `jbus queue rename n1-slot-strays fl-n1-slot-strays`" in said
    code, said = queue_(kitchen, "rename", "n1-slot-strays", "fl-n1-slot-strays")
    assert code == 0 and said.splitlines()[0].endswith(", its go holds"), said
    assert json.loads(queue_(kitchen, "verify", "fl-n1-slot-strays")[1])["holds"]
    code, said = queue_(kitchen, "withdraw", "fl-n1-slot-strays", "--why", "the plan dropped it")
    assert code == 0, said
    assert rows(kitchen) == {}
    assert {slug: one["by"] for slug, one in gone(kitchen).items()} == {
        "n1-slot-strays": "the flow home",
        "fl-n1-slot-strays": "the flow home",
    }
