"""A home's standing word approves its follow-ups that open no door, as they are queued.

On 2026-11-09 the user told the polish home "when new briefs need my approval, approve them", and
a dozen follow-ups a crew queued still waited on the user's list until the user typed "approve
<slug>" for each. A home now records such a word with `jbus standing`: a follow-up of that home
(its brief names a parent on a `Follows:` line) whose brief holds no case of gates.md, queued
after it, is approved on that word in the same `jbus queue add`, and its approved column names the
word. A row with a `Holds:` line, and a row with no `Follows:` line, still waits on the user. The
same verb withdraws the word, and `jbus needs` names each home's standing word while it holds.
Every test runs the real commands against the kitchen's fakes.
"""

from datetime import timedelta

import pytest

from jbus import verbs
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import brief, rows

POLISH = "mcp:" + "-".join("7" * size for size in (8, 4, 4, 4, 12))
SAID = "when new briefs need my approval, approve them. keep the train running"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    for scope, thread in (("polish", POLISH), ("uncategorized", "mcp:uncategorized")):
        (made.home / scope).mkdir(parents=True, exist_ok=True)
        (made.home / scope / "plan.md").write_text("# a plan\n")
        (made.home / scope / "home-id").write_text(f"{thread}\n")
    yield made
    made.close()


def said_in_polish(kitchen, words=SAID):
    """Keep the user's own message `words`, said in the polish home's thread, as a word, and
    return its id."""
    name = f"m{len(kitchen.t3.said)}"
    kitchen.t3.says(POLISH, name, words, title="home: polish")
    code, out = kitchen.main("word", "--to", "demo", "--message", f"{POLISH}/{name}")
    assert code == 0, out
    return out.split("word ")[-1].strip()


def polish(slug, more=""):
    return brief(slug, more).replace("Home: uncategorized", "Home: polish")


def add(kitchen, slug, text):
    code, said = kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)
    assert code == 0, said
    return said.partition("| slug |")[0].strip().splitlines()


def stand(kitchen, *argv):
    code, out = kitchen.main("standing", "--to", "demo", *argv)
    return code, out.strip()


def test_a_follow_up_with_no_door_is_approved_on_the_homes_standing_word_as_it_is_queued(kitchen):
    word = said_in_polish(kitchen)
    code, out = stand(kitchen, "--word", word)
    assert code == 0, out
    assert out == (
        f"standing: demo, the polish home approves its follow-ups that open no door on word {word}"
    )
    assert add(kitchen, "alpha", polish("alpha")) == []
    said = add(kitchen, "alpha-2", polish("alpha-2", "Follows: alpha\n"))
    approved = rows(kitchen)["alpha-2"]["approved"]
    assert said == [f"approved alpha-2: brief {said[0].split()[3]} {approved}"]
    assert approved.startswith(f"your standing word {word} for follow-ups, ")
    assert "follow-up of alpha" in approved
    made = rows(kitchen)["alpha-2"]["approval"]
    assert (made["basis"], made["ref"], made["follows"]) == ("standing", word, "alpha")
    assert made["words"] == SAID


@pytest.mark.parametrize(
    ("more", "why"),
    [
        ("Follows: alpha\nHolds: publishes\n", "a follow-up with a Holds: line"),
        ("", "a row with no Follows: line"),
    ],
)
def test_a_row_that_opens_a_door_or_follows_nothing_still_waits_for_the_user_word(
    kitchen, more, why
):
    stand(kitchen, "--word", said_in_polish(kitchen))
    add(kitchen, "alpha", polish("alpha"))
    add(kitchen, "beta", polish("beta", more))
    assert rows(kitchen)["beta"]["approved"] == "", why


def test_a_follow_up_of_another_home_waits_for_the_user_word(kitchen):
    stand(kitchen, "--word", said_in_polish(kitchen))
    add(kitchen, "alpha", brief("alpha"))
    add(kitchen, "alpha-2", brief("alpha-2", "Follows: alpha\n"))
    assert rows(kitchen)["alpha-2"]["approved"] == ""


def test_a_withdrawn_standing_word_approves_no_later_follow_up(kitchen):
    word = said_in_polish(kitchen)
    stand(kitchen, "--word", word)
    code, out = stand(kitchen, "--word", word, "--withdraw")
    assert code == 0, out
    assert out == f"withdrawn: demo, the polish home's standing word {word} approves nothing more"
    add(kitchen, "alpha", polish("alpha"))
    add(kitchen, "alpha-2", polish("alpha-2", "Follows: alpha\n"))
    assert rows(kitchen)["alpha-2"]["approved"] == ""


def test_a_word_jbus_did_not_read_from_the_users_own_message_does_not_stand(kitchen):
    kitchen.word()
    code, out = stand(kitchen, "--word", "said-by-user")
    assert code == 1
    assert out.startswith("refused: word said-by-user is not the user's own message")


def test_jbus_needs_names_each_homes_standing_word_while_it_holds(kitchen):
    word = said_in_polish(kitchen)
    stand(kitchen, "--word", word)
    kitchen.poll()
    at = NOW + timedelta(minutes=5)
    kitchen.monkeypatch.setattr(verbs, "clock", lambda: at)
    code, out = kitchen.main("needs")
    assert code == 0, out
    line = f'demo polish home standing word {word} for follow-ups that open no door: "{SAID}"'
    assert line in out.splitlines()
    stand(kitchen, "--word", word, "--withdraw")
    assert line not in kitchen.main("needs")[1].splitlines()
