"""The user's go for a work item, by its id: from the command and from the view. Each writes
one `approved` line that says where it was said, and each refuses what the go's rules refuse,
with a sentence, writing nothing."""

import pytest

from jbus import item
from view.scene import Served
from view.test_view_answer import Counter


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


def test_the_command_records_the_go_said_on_the_command_line(counter):
    kitchen = counter.kitchen
    name = proposed(kitchen)
    assert kitchen.main("item", "approve", name, "--by", "user") == (0, f"approved {name}\n")
    line = last(kitchen, name)
    assert (line["verb"], line["where"], line["by"]) == ("approved", "cli", "user")
    assert item.items(kitchen.state)[name].state is item.State.APPROVED


def approve(served, name, seen):
    return served.write({"item": name, "seen_event": seen}, path="/approve?project=demo")


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
        assert served.write({"item": name}, path="/approve?project=demo")[0] == 400
        assert (
            served.write({"item": name, "seen_event": seen}, path="/steer?project=demo")[0] == 405
        )
    finally:
        served.close()
