"""The needs-you list as an inbox: each need has one action, approve, answer or steer, and the
default it goes ahead on, and an action taken on the page reaches jbus as the user's word by the
path `jbus answer`, `jbus queue approve --word` and `jbus word` take. Once it is recorded, the
need leaves the list."""

import pytest

from jbus import queue, word
from jbus.view.panels.you import panel as panel_you
from test_jbus_kitchen import complete
from view.scene import EVIL, GATE, Scene, Served
from view.test_view_answer import Counter
from view.test_view_you import needing

HOME = "mcp:home-demo"


@pytest.fixture
def counter(tmp_path, monkeypatch):
    made = Counter(tmp_path, monkeypatch)
    (made.kitchen.home / "home-id").write_text(HOME + "\n")
    served = Served(made)
    yield made, served
    served.close()
    made.kitchen.close()


def act(served, write, body, origin=None):
    return served.write(body, origin=origin, path=f"/panel/you/{write}?project=demo")


def unapproved(counter, slug="oat-milk"):
    """A row queued with no go, as the user's need after a pass, and the sha of its brief."""
    code, said = counter.kitchen.main("queue", "add", slug, "--priority", "1", stdin=complete(slug))
    assert code == 0, said
    counter.passes(1)
    return queue.brief_sha(queue.brief(counter.state, slug))[:12]


def needs(served):
    return {one["key"]: one for one in served.json("/state.json?project=demo")["needs"]}


def words(counter):
    return {one.id: one for one in word.load(counter.state)}


def test_each_need_has_one_action_and_says_what_happens_if_the_user_does_nothing(
    tmp_path, monkeypatch
):
    scene = Scene(tmp_path, monkeypatch)
    needing(scene)
    served = Served(scene)
    try:
        found = served.json("/stack.json")["needs"]
    finally:
        served.close()
    acts = {one["kind"]: one["act"] for one in found}
    assert acts == {
        "config": "open",
        "gate": "answer",
        "approve": "approve",
        "row": "steer",
        "left": "steer",
        "hold": "steer",
    }
    assert all(one["default"] for one in found)
    by = {one["kind"]: one for one in found}
    assert by["gate"]["default"] == "the first one"
    assert by["approve"]["default"] == panel_you.IDLE["approve"]
    assert by["hold"]["default"] == panel_you.IDLE["hold"]
    assert by["approve"]["sha"] == queue.brief_sha(queue.brief(scene.state, "tea-kettle"))[:12]
    assert {one["sha"] for one in found if one["kind"] != "approve"} == {""}
    assert {one["steered"] for one in found} == {None}


def test_approve_keeps_the_users_word_gives_the_row_its_go_on_it_and_the_need_leaves(counter):
    counter, served = counter
    sha = unapproved(counter)
    assert needs(served)["approve:oat-milk"]["act"] == "approve"
    status, said = act(served, "approve", {"slug": "oat-milk", "sha": sha})
    assert status == 200, said
    row = queue.fresh(counter.state, "oat-milk")
    approval = row["approval"]
    assert (approval["basis"], approval["ref"]) == ("word", said["word"])
    kept = words(counter)[said["word"]]
    assert (kept.words, kept.by) == (f"Approve oat-milk, brief {sha}, in jbus view", "user")
    assert approval["words"] == kept.words
    assert kept.thread == HOME and kept.sent_at
    assert any(said["word"] in one["message"] for one in counter.sends())
    assert said["say"].startswith(f"oat-milk approved at 11:00 ET, on your word {said['word']}.")
    assert [key for key, one in needs(served).items() if one["slug"] == "oat-milk"] == []


def test_approve_of_a_brief_that_changed_since_the_page_showed_it_keeps_no_word(counter):
    counter, served = counter
    unapproved(counter)
    status, said = act(served, "approve", {"slug": "oat-milk", "sha": "0" * 12})
    assert status == 409
    assert "read it, then approve it" in said["say"]
    assert not queue.fresh(counter.state, "oat-milk").get("approved")
    assert words(counter) == {}
    assert "approve:oat-milk" in needs(served)


def test_undo_takes_back_the_go_that_one_word_gave_and_tells_the_home(counter):
    counter, served = counter
    sha = unapproved(counter)
    _, given = act(served, "approve", {"slug": "oat-milk", "sha": sha})
    status, said = act(served, "hold", {"slug": "oat-milk", "word": "f" * 12})
    assert status == 409
    assert queue.fresh(counter.state, "oat-milk").get("approved")
    status, said = act(served, "hold", {"slug": "oat-milk", "word": given["word"]})
    assert status == 200, said
    row = queue.fresh(counter.state, "oat-milk")
    assert (row.get("approved"), row.get("held")) == ("", True)
    told = [one for one in words(counter).values() if one.words.startswith("Hold oat-milk")]
    assert [one.words for one in told] == [
        f"Hold oat-milk: undo of word {given['word']}, in jbus view"
    ]
    assert told[0].sent_at


def test_undo_while_a_launch_is_out_is_refused_and_keeps_no_word(counter):
    """A pass that has begun the launch has written its intent and has no thread yet: the go
    is not taken back under it, and no Hold word is left for the home."""
    counter, served = counter
    sha = unapproved(counter)
    _, given = act(served, "approve", {"slug": "oat-milk", "sha": sha})
    record = counter.kitchen.state_dir / "launches" / "demo" / "oat-milk" / "0123456789ab.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"key": "0123456789ab", "state": "intent"}')
    kept = set(words(counter))
    status, said = act(served, "hold", {"slug": "oat-milk", "word": given["word"]})
    assert status == 409, said
    assert "launch" in said["say"]
    assert queue.fresh(counter.state, "oat-milk").get("approved")
    assert set(words(counter)) == kept


def test_steer_gives_the_users_line_to_the_home_and_the_need_moves_to_steered(counter):
    """A gate of the home's own file is no question jbus holds, so the user steers it: the line
    is a word for the home, and the need leaves the list for the list of what was steered."""
    counter, served = counter
    (counter.kitchen.home / "gates.md").write_text(
        GATE.format(n=40, asked="which jar?", status="open", default="")
    )
    (one,) = [one for one in needs(served).values() if one["what"] == "which jar?"]
    assert (one["act"], one["default"]) == ("steer", panel_you.IDLE["gate"])
    status, said = act(served, "steer", {"subj": one["subj"], "words": "  the blue  one "})
    assert status == 200, said
    kept = words(counter)[said["word"]]
    assert (kept.words, kept.by) == (f"{one['subj']}: the blue one", "user")
    assert kept.thread == HOME and kept.sent_at
    assert any(kept.id in sent["message"] for sent in counter.sends())
    state = served.json("/state.json?project=demo")
    assert "which jar?" not in [each["what"] for each in state["needs"]]
    (moved,) = [each for each in state["steered"] if each["what"] == "which jar?"]
    assert moved["steered"] == kept.kept_at


@pytest.mark.parametrize(
    "body", ["not json", {}, {"subj": "fig-jam"}, {"subj": "fig-jam", "words": "   "}]
)
def test_a_steer_that_is_not_the_shape_is_400_and_keeps_nothing(counter, body):
    counter, served = counter
    status, _ = served.write(body, path="/panel/you/steer?project=demo")
    assert status == 400
    assert words(counter) == {}


def test_a_panel_write_is_held_to_the_origin_and_names_a_write_the_panel_has(counter):
    counter, served = counter
    sha = unapproved(counter)
    body = {"slug": "oat-milk", "sha": sha}
    assert act(served, "approve", body, origin=f"http://{EVIL}")[0] == 403
    assert act(served, "nothing", body)[0] == 404
    assert served.write(body, path="/panel/nopanel/approve?project=demo")[0] == 404
    assert served.write(body, path="/panel/you/approve?project=nowhere")[0] == 404
    assert served.ask("/panel/you/approve?project=demo")[0] == 404
    status, headers, _ = served.ask("/panel/you/approve?project=demo", method="PUT")
    assert (status, headers.get("Allow")) == (405, "POST")
    assert not queue.fresh(counter.state, "oat-milk").get("approved")


def counts(served):
    """The waiting count as each screen reads it: the project's list, its row on the overview,
    and every project's, which the Triage tab draws."""
    state, stack = served.json("/state.json?project=demo"), served.json("/stack.json")
    (row,) = [one for one in stack["projects"] if one["name"] == "demo"]
    return len(state["needs"]), row["waits"], len(stack["needs"])


def test_one_count_on_every_screen_and_a_steered_need_leaves_each_of_them(counter):
    """The page says "nothing falls due before" the first `due` of `proceeds`, so the soonest
    default leads that list, in the project and across projects."""
    counter, served = counter
    counter.asks("tea or coffee?")
    counter.asks("milk?")
    (counter.kitchen.home / "gates.md").write_text(
        GATE.format(n=40, asked="which jar?", status="open", default="")
    )
    before = counts(served)
    assert len(set(before)) == 1 and before[0] >= 1, before
    for read in (served.json("/state.json?project=demo"), served.json("/stack.json")):
        due = [one["due"] for one in read["proceeds"]]
        assert len(due) == 2 and None not in due and due[0] == min(due), due
    (one,) = [one for one in needs(served).values() if one["what"] == "which jar?"]
    status, said = act(served, "steer", {"subj": one["subj"], "words": "the blue one"})
    assert status == 200, said
    assert counts(served) == tuple(n - 1 for n in before)


def test_a_go_given_before_the_brief_changed_still_needs_the_user(counter):
    """A row keeps its `approved` when its brief changes after the go, and that go no longer
    holds. So the need stays, before the next pass and after it, which gates the row."""
    counter, served = counter
    sha = unapproved(counter)
    assert act(served, "approve", {"slug": "oat-milk", "sha": sha})[0] == 200
    brief = counter.state / "briefs" / "oat-milk.md"
    brief.write_text(brief.read_text().replace('"do oat-milk"', '"do oat-milk, then the jam"'))
    assert needs(served)["approve:oat-milk"]["act"] == "approve"
    counter.passes(1)
    row = queue.fresh(counter.state, "oat-milk")
    assert row.get("approved") and row["why"].startswith("brief changed after approval")
    assert [key for key, one in needs(served).items() if one["slug"] == "oat-milk"] == [
        "row:oat-milk"
    ]


def test_a_steered_need_that_keeps_no_time_stays_on_every_count_with_the_time_of_the_line(
    counter,
):
    """A gate of the home's file has no `since` until a pass sees it, so no change after the
    user's line could ever bring it back: it stays on the list and on each count, and says
    when it was steered."""
    counter, served = counter
    (counter.kitchen.home / "gates.md").write_text(
        GATE.format(n=40, asked="which jar?", status="open", default="")
    )
    (one,) = [one for one in needs(served).values() if one["what"] == "which jar?"]
    assert one["since"] is None
    before = counts(served)
    status, said = act(served, "steer", {"subj": one["subj"], "words": "the blue one"})
    assert status == 200, said
    assert counts(served) == before
    kept = words(counter)[said["word"]]
    (still,) = [each for each in needs(served).values() if each["what"] == "which jar?"]
    assert still["steered"] == kept.kept_at
    assert served.json("/state.json?project=demo")["steered"] == []
