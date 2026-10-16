"""Work items: one closed set of states, one table of moves, an append-only log folded by it,
and a pass that moves an item only when its row's state changes. The verbs are run as
`jbus` runs them, and the pass as `test_jbus_kitchen.py` runs it."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import item, questions, queue, wake, work
from jbus.item import MOVES, Item, Risk, State, Verb, Where
from test_jbus_kitchen import NOW, complete

PASS = timedelta(minutes=3)


@pytest.fixture
def box(tmp_path):
    project = jbus.Project("demo", tmp_path / "checkout", "demo", "project-1", "", "")
    return wake.Box(tmp_path / "state", project)


def put(box, verb, name="", **more):
    more.setdefault("line", f"a line that says {verb}")
    return item.write(box.state, box, verb, item=name, by="user", where=Where.CLI, **more)


REACH = {
    State.PROPOSED: [],
    State.APPROVED: [Verb.APPROVE],
    State.QUEUED: [Verb.APPROVE, Verb.QUEUE],
    State.RUNNING: [Verb.APPROVE, Verb.QUEUE, Verb.LAUNCH],
    State.WAITING_ON_YOU: [Verb.APPROVE, Verb.QUEUE, Verb.LAUNCH, Verb.WAIT],
    State.HELD: [Verb.APPROVE, Verb.QUEUE, Verb.HOLD],
    State.DONE: [Verb.APPROVE, Verb.QUEUE, Verb.LAUNCH, Verb.DONE],
    State.DROPPED: [Verb.DROP],
}


def reach(box, state):
    """A new item, brought to `state` by the verbs written out above."""
    name = put(box, Verb.PROPOSE, title="a task")["item"]
    for verb in REACH[state]:
        put(box, verb, name)
    assert item.items(box.state)[name].state is state
    return name


def test_the_states_are_the_eight_of_the_brief_and_no_other():
    assert [str(one) for one in State] == [
        "proposed",
        "approved",
        "queued",
        "running",
        "waiting_on_you",
        "held",
        "done",
        "dropped",
    ]


@pytest.mark.parametrize("state", list(State))
@pytest.mark.parametrize("verb", list(Verb))
def test_each_state_and_verb_not_in_the_table_is_refused_in_a_sentence_and_writes_nothing(
    box, state, verb
):
    name = reach(box, state)
    before = item.path(box.state).read_bytes()
    logged = len(box.log())
    more = {"slug": "alpha"} if verb is Verb.LINK else {}
    if (state, verb) in MOVES:
        put(box, verb, name, **more)
        assert item.path(box.state).read_bytes() != before
        assert len(box.log()) == logged + 1
        return
    with pytest.raises(jbus.Refused) as refused:
        put(box, verb, name, **more)
    assert str(refused.value).startswith(f"refused: {name} ")
    assert item.path(box.state).read_bytes() == before
    assert len(box.log()) == logged


def test_a_verb_for_an_item_there_is_not_is_refused_and_writes_nothing(box):
    for verb in Verb:
        if verb is Verb.PROPOSE:
            continue
        with pytest.raises(jbus.Refused, match="there is no item w7"):
            put(box, verb, "w7")
    assert not item.path(box.state).exists()


def test_waiting_on_you_is_entered_from_running_or_queued_and_left_for_where_it_came_from(box):
    assert {start for (start, verb) in MOVES if verb is Verb.WAIT} == {
        State.QUEUED,
        State.RUNNING,
    }
    for start in (State.QUEUED, State.RUNNING):
        name = reach(box, start)
        put(box, Verb.WAIT, name)
        assert item.items(box.state)[name].state is State.WAITING_ON_YOU
        put(box, Verb.RESUME, name)
        assert item.items(box.state)[name].state is start


def test_the_fold_of_a_log_is_the_state_written_out_by_hand(box):
    lines = [
        {"id": "w1.1", "item": "w1", "verb": "proposed", "where": "chat", "by": "Sous Chef"}
        | {"project": "demo", "title": "a page", "owner": "home", "at": "", "line": ""},
        {"id": "w2.1", "item": "w2", "verb": "proposed", "where": "cli", "by": "the demo home"}
        | {"project": "demo", "title": "a fix", "owner": "home", "slug": "fix", "at": ""}
        | {"line": ""},
        {"id": "w1.2", "item": "w1", "verb": "approved", "where": "chat", "by": "user"},
        {"id": "w1.3", "item": "w1", "verb": "linked", "where": "cli", "slug": "page", "by": "h"},
        {"id": "w2.2", "item": "w2", "verb": "dropped", "where": "cli", "by": "user"},
        {"id": "w1.4", "item": "w1", "verb": "queued", "where": "pass", "by": "jbus"},
        {"id": "w1.5", "item": "w1", "verb": "launched", "where": "pass", "by": "jbus"},
        {"id": "w1.6", "item": "w1", "verb": "waiting", "where": "pass", "by": "jbus"},
        {"id": "w2.3", "item": "w2", "verb": "approved", "where": "cli", "by": "user"},
    ]
    box.state.mkdir(parents=True)
    with open(item.path(box.state), "w") as log:
        log.writelines(json.dumps(line) + "\n" for line in lines)
        log.write("{a line a write that died left\n")
    assert item.items(box.state) == {
        "w1": Item(
            id="w1",
            project="demo",
            slug="page",
            title="a page",
            source="chat",
            owner="home",
            state=State.WAITING_ON_YOU,
            risk=Risk.ROUTINE,
            last_event="w1.6",
            back=State.RUNNING,
        ),
        "w2": Item(
            id="w2",
            project="demo",
            slug="fix",
            title="a fix",
            source="cli",
            owner="home",
            state=State.DROPPED,
            risk=Risk.ROUTINE,
            last_event="w2.2",
        ),
    }


def test_an_id_is_minted_from_the_counter_and_never_given_again(box):
    assert put(box, Verb.PROPOSE, title="one")["item"] == "w1"
    assert item.reserve(box.state) == "w2"
    assert put(box, Verb.PROPOSE, title="three")["item"] == "w3"
    item.path(box.state).unlink()
    assert put(box, Verb.PROPOSE, title="four")["item"] == "w4"
    assert put(box, Verb.PROPOSE, "w2", title="two")["item"] == "w2"
    with pytest.raises(jbus.Refused, match="w2 is proposed already"):
        put(box, Verb.PROPOSE, "w2", title="two again")


def test_a_line_that_names_a_last_line_the_item_moved_past_is_refused(box):
    name = reach(box, State.PROPOSED)
    put(box, Verb.APPROVE, name, seen="w1.1")
    before = item.path(box.state).read_bytes()
    with pytest.raises(jbus.Refused, match="w1 moved since w1.1: its last line is w1.2"):
        put(box, Verb.DROP, name, seen="w1.1")
    assert item.path(box.state).read_bytes() == before


def test_an_item_is_linked_to_one_row_and_a_row_to_one_item(box):
    first, second = reach(box, State.PROPOSED), reach(box, State.PROPOSED)
    put(box, Verb.LINK, first, slug="alpha")
    with pytest.raises(jbus.Refused, match="w1 is linked to alpha already"):
        put(box, Verb.LINK, first, slug="beta")
    with pytest.raises(jbus.Refused, match="alpha is linked to w1 already"):
        put(box, Verb.LINK, second, slug="alpha")
    assert item.items(box.state)[first].slug == "alpha"
    assert item.items(box.state)[second].slug == ""


def test_each_line_is_a_quiet_event_of_its_kind_in_the_log(box):
    name = reach(box, State.QUEUED)
    events = box.log()
    assert [one["event"] for one in events] == ["item.proposed", "item.approved", "item.queued"]
    assert {one["loud"] for one in events} == {"quiet"}
    assert [one["item"] for one in events] == [name] * 3
    assert [one["item_line"] for one in events] == ["w1.1", "w1.2", "w1.3"]
    assert {kind for kind in wake.LOUDNESS if kind.startswith("item.")} == set(item.EVENTS)
    assert set(item.EVENTS.values()) == {"quiet"}


def gate(slug, question="which one?", holds="", context=""):
    return questions.Question(
        number=1,
        slug=slug,
        thread="mcp:a-thread",
        question=question,
        default="the first",
        built_on="nothing",
        undo="pick the other",
        asked_at="2026-10-16T14:00:00+00:00",
        context=context,
        holds=holds,
    )


@pytest.mark.parametrize(
    ("value", "gates", "risk"),
    [
        ("working", [], Risk.ROUTINE),
        ("asking", [gate("a")], Risk.ROUTINE),
        ("hold", [], Risk.REVIEW),
        ("asking", [gate("a", holds="changes access")], Risk.REVIEW),
        ("asking", [gate("a", "which token does the relay use?")], Risk.REVIEW),
        ("asking", [gate("a", "where does the API key go?")], Risk.REVIEW),
        ("asking", [gate("a", context="it changes the config")], Risk.REVIEW),
        ("asking", [gate("a", "which configurable tab?")], Risk.ROUTINE),
    ],
)
def test_risk_is_review_for_a_held_merge_a_config_wait_a_secret_and_a_holding_gate(
    value, gates, risk
):
    assert item.risk(value, gates) is risk


@pytest.mark.parametrize(
    ("state", "go", "value", "verbs"),
    [
        (State.PROPOSED, False, "unapproved", []),
        (State.PROPOSED, True, "ready", [Verb.APPROVE, Verb.QUEUE]),
        (State.APPROVED, True, "behind", [Verb.QUEUE]),
        (State.APPROVED, True, "launching", [Verb.LAUNCH]),
        (State.QUEUED, True, "ready", []),
        (State.QUEUED, True, "working", [Verb.LAUNCH]),
        (State.QUEUED, False, "unapproved", [Verb.HOLD]),
        (State.HELD, True, "ready", [Verb.APPROVE, Verb.QUEUE]),
        (State.RUNNING, True, "review", []),
        (State.RUNNING, True, "asking", [Verb.WAIT]),
        (State.RUNNING, True, "hold", [Verb.WAIT]),
        (State.RUNNING, True, "merged", [Verb.DONE]),
        (State.QUEUED, True, "merged", [Verb.DONE]),
        (State.RUNNING, True, "unknown", []),
        (State.RUNNING, True, None, []),
        (State.DONE, True, "working", []),
    ],
)
def test_a_pass_writes_only_the_move_its_row_shows(box, state, go, value, verbs):
    name = reach(box, state)
    assert item.planned(item.items(box.state)[name], go, value) == verbs


def test_an_item_waiting_on_you_is_resumed_to_where_it_came_from_and_moves_on_from_there(box):
    for start, value, verbs in (
        (State.RUNNING, "working", [Verb.RESUME]),
        (State.QUEUED, "ready", [Verb.RESUME]),
        (State.QUEUED, "working", [Verb.RESUME, Verb.LAUNCH]),
        (State.RUNNING, "merged", [Verb.DONE]),
        (State.RUNNING, "asking", []),
    ):
        name = reach(box, start)
        put(box, Verb.WAIT, name)
        assert item.planned(item.items(box.state)[name], True, value) == verbs


def test_every_value_work_judges_says_a_state_or_none():
    assert set(item.AIM) == set(work.VALUES)


def add(kitchen, slug, *more):
    return kitchen.main("queue", "add", slug, "--priority", "1", *more, stdin=complete(slug))


def test_queue_add_mints_an_item_for_the_row_or_links_the_one_it_names(kitchen):
    assert add(kitchen, "alpha")[0] == 0
    said = kitchen.main(
        "item", "propose", "--title", "a page", "--by", "Sous Chef", "--where", "chat"
    )
    assert said == (0, "proposed w2: a page\n")
    assert add(kitchen, "beta", "--item", "w2")[0] == 0
    rows = {row["slug"]: row for row in queue.load(kitchen.state)}
    assert (rows["alpha"]["item"], rows["beta"]["item"]) == ("w1", "w2")
    found = item.items(kitchen.state)
    assert (found["w1"].slug, found["w1"].source, found["w1"].title) == ("alpha", "cli", "a task")
    assert (found["w2"].slug, found["w2"].source, found["w2"].title) == ("beta", "chat", "a page")
    assert [one["event"] for one in kitchen.events() if one["event"].startswith("item.")] == [
        "item.proposed",
        "item.proposed",
        "item.linked",
    ]
    assert add(kitchen, "alpha")[0] == 0
    assert item.items(kitchen.state)["w1"].last_event == "w1.1"


@pytest.mark.parametrize(
    ("named", "said"),
    [
        ("w9", "refused: there is no item w9, and nothing is queued\n"),
        ("w1", "refused: w1 is linked to alpha, and nothing is queued\n"),
    ],
)
def test_queue_add_refuses_an_item_it_cannot_link_and_queues_nothing(kitchen, named, said):
    assert add(kitchen, "alpha")[0] == 0
    before = item.path(kitchen.state).read_bytes()
    assert add(kitchen, "beta", "--item", named) == (1, said)
    assert [row["slug"] for row in queue.load(kitchen.state)] == ["alpha"]
    assert item.path(kitchen.state).read_bytes() == before


def test_a_row_added_with_a_go_maps_to_approved(kitchen):
    assert add(kitchen, "alpha")[0] == 0
    sha = queue.brief_sha(complete("alpha"))[:12]
    word = kitchen.word()
    assert kitchen.main("queue", "approve", "alpha", "--word", word, "--sha", sha)[0] == 0
    assert add(kitchen, "alpha")[0] == 0
    assert item.items(kitchen.state)["w1"].state is State.APPROVED


def written(kitchen):
    return item.read(kitchen.state)


def test_a_pass_writes_a_line_only_when_the_state_it_maps_changes(kitchen):
    kitchen.config(dispatch=False)
    test_a_row_added_with_a_go_maps_to_approved(kitchen)
    before = len(written(kitchen))
    kitchen.poll(NOW)
    first = written(kitchen)[before:]
    assert [(one["verb"], one["where"], one["by"]) for one in first] == [("queued", "pass", "jbus")]
    kitchen.poll(NOW + PASS)
    assert len(written(kitchen)) == before + 1
    assert item.items(kitchen.state)["w1"].state is State.QUEUED


def test_a_row_from_before_items_gets_its_item_on_the_next_pass_with_its_go(kitchen):
    kitchen.config(dispatch=False)
    test_a_row_added_with_a_go_maps_to_approved(kitchen)
    item.path(kitchen.state).unlink()
    table = json.loads(queue.path(kitchen.state).read_text())
    for row in table:
        row.pop("item")
    queue.path(kitchen.state).write_text(json.dumps(table))
    kitchen.poll(NOW)
    assert [one["verb"] for one in written(kitchen)] == ["proposed", "approved", "queued"]
    found = item.items(kitchen.state)
    assert [(one.id, one.slug, one.source, one.state) for one in found.values()] == [
        ("w2", "alpha", "pass", State.QUEUED)
    ]
    kitchen.poll(NOW + PASS)
    assert len(written(kitchen)) == 3


def test_a_pass_proposes_the_item_queue_add_reserved_and_has_not_written_yet(kitchen):
    kitchen.config(dispatch=False)
    assert add(kitchen, "alpha")[0] == 0
    item.path(kitchen.state).unlink()
    kitchen.poll(NOW)
    assert [(one.id, one.slug) for one in item.items(kitchen.state).values()] == [("w1", "alpha")]


def test_the_item_of_a_removed_row_is_dropped_by_the_next_pass(kitchen):
    kitchen.config(dispatch=False)
    assert add(kitchen, "alpha")[0] == 0
    removed = kitchen.main(
        "queue", "remove", "alpha", "--by", "user", "--at", "2026-10-12 10:58 ET"
    )
    assert removed[0] == 0, removed
    kitchen.poll(NOW)
    assert item.items(kitchen.state)["w1"].state is State.DROPPED
    kitchen.poll(NOW + PASS)
    assert [one["verb"] for one in written(kitchen)] == ["proposed", "dropped"]


def test_forget_trims_the_events_and_leaves_items_jsonl_as_it_was(kitchen):
    assert add(kitchen, "alpha")[0] == 0
    before = item.path(kitchen.state).read_bytes()
    assert kitchen.events("item.proposed")
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    box.forget(NOW + timedelta(days=365))
    assert not kitchen.events("item.proposed")
    assert item.path(kitchen.state).read_bytes() == before


def test_the_item_verbs_propose_approve_drop_show_and_list(kitchen):
    propose = ("item", "propose", "--by", "Sous Chef", "--where", "chat", "--title")
    assert kitchen.main(*propose, "a page") == (0, "proposed w1: a page\n")
    assert kitchen.main(*propose, "a fix") == (0, "proposed w2: a fix\n")
    said = kitchen.main("item", "approve", "w1", "--by", "Sous Chef")
    assert said == (1, "refused: only user approves an item, not Sous Chef\n")
    approve = ("item", "approve", "w1", "--by", "user", "--where", "chat", "--words")
    assert kitchen.main(*approve, "go on w1") == (0, "approved w1\n")
    assert kitchen.main("item", "drop", "w2", "--by", "the demo home") == (0, "dropped w2\n")
    said = kitchen.main("item", "approve", "w2", "--by", "user")
    assert said == (1, "refused: w2 is dropped, and an item that is dropped cannot be approved\n")
    code, shown = kitchen.main("item", "show", "w1")
    assert code == 0
    assert shown.splitlines()[:9] == [
        "w1: a page",
        "state: approved",
        "slug: (none)",
        "source: chat",
        "owner: home",
        "project: demo",
        "risk: routine",
        "last event: w1.2",
        "lines:",
    ]
    assert shown.splitlines()[10].endswith("approved by user in chat: approve by user: go on w1")
    assert kitchen.main("item", "list") == (
        0,
        "w1 approved routine - a page\nw2 dropped routine - a fix\n",
    )
    assert kitchen.main("item", "show", "w9") == (1, "refused: there is no item w9\n")


def test_show_gives_the_risk_of_a_merge_jmerge_holds(kitchen):
    assert add(kitchen, "alpha")[0] == 0
    facts = work.every().__next__()
    held = work.State("hold", "user", "your word", True, facts)
    work.write(kitchen.state, "", work.Answered.BOTH, [work.entry(held, key="alpha", kind="row")])
    assert "risk: review" in kitchen.main("item", "show", "w1")[1].splitlines()
