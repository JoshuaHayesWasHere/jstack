"""The user's go for a work item, by its id: from the command, from Sous Chef's chat on a card,
and from the view. Each writes one `approved` line that says where it was said, and each refuses
what the go's rules refuse, with a sentence, writing nothing."""

import pytest

from jbus import chat, item
from view.test_view_answer import Counter
from view.scene import Served


@pytest.fixture
def counter(tmp_path, monkeypatch):
    made = Counter(tmp_path, monkeypatch)
    yield made
    made.kitchen.close()


def proposed(kitchen, title="a page"):
    said = kitchen.main("item", "propose", "--by", "Sous Chef", "--where", "chat", "--title", title)
    assert said[0] == 0, said
    return said[1].split()[1].rstrip(":")


def last(kitchen, name):
    return [one for one in item.read(kitchen.state) if one["item"] == name][-1]


def decided(kitchen, name, verb="approve", by="user", words=None, seen=None):
    body = {
        "project": "demo",
        "item": name,
        "verb": verb,
        "by": by,
        "seen_event": seen or item.items(kitchen.state)[name].last_event,
        "words": f"go on {name}" if words is None else words,
        "message": "chat/m1",
    }
    return chat.decide(body)


def test_the_command_records_the_go_said_on_the_command_line(counter):
    kitchen = counter.kitchen
    name = proposed(kitchen)
    assert kitchen.main("item", "approve", name, "--by", "user") == (0, f"approved {name}\n")
    line = last(kitchen, name)
    assert (line["verb"], line["where"], line["by"]) == ("approved", "cli", "user")
    assert item.items(kitchen.state)[name].state is item.State.APPROVED


def test_chat_records_the_users_go_for_a_routine_item_its_words_name(counter):
    kitchen = counter.kitchen
    name = proposed(kitchen)
    status, said = decided(kitchen, name)
    assert status == 200, said
    line = last(kitchen, name)
    assert (line["verb"], line["where"], line["id"]) == ("approved", "chat", said["id"])
    assert (line["basis"], line["ref"], line["said"]) == ("chat", "chat/m1", f"go on {name}")
    assert line["checked"] is False


@pytest.mark.parametrize(
    ("by", "words", "refused"),
    [
        ("user", "go on it", "an approval from chat names the item"),
        ("Sous Chef", "go on w1", "only user approves an item, not Sous Chef"),
    ],
)
def test_chat_refuses_a_go_whose_words_name_no_item_or_that_is_not_the_users(
    counter, by, words, refused
):
    kitchen = counter.kitchen
    name = proposed(kitchen)
    before = item.read(kitchen.state)
    status, said = decided(kitchen, name, by=by, words=words)
    assert status == 409
    assert refused in said["refused"]
    assert item.read(kitchen.state) == before


def approve(served, name, seen):
    body = {"item": name, "action": "approve", "words": "", "seen_event": seen, "confirm": False}
    return served.write(body, path="/steer?project=demo")


def test_the_view_records_the_users_go_and_refuses_one_the_item_moved_past(counter):
    kitchen = counter.kitchen
    name = proposed(kitchen)
    seen = item.items(kitchen.state)[name].last_event
    served = Served(counter)
    try:
        status, said = approve(served, name, seen)
        assert status == 200, said
        line = last(kitchen, name)
        assert (line["verb"], line["where"], line["by"]) == ("approved", "view", "user")
        assert (said["state"], said["last_event"]) == ("approved", line["id"])
        status, said = approve(served, name, seen)
        assert status == 409
        assert f"{name} moved since {seen}" in said["say"]
        assert approve(served, "w99", seen)[0] == 404
        assert served.write({"item": name}, path="/steer?project=demo")[0] == 400
    finally:
        served.close()
