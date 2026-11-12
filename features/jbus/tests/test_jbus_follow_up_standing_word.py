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

import jbus
from jbus import needs, queue, standing, verbs
from test_jbus_acts import CHAT
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import brief, go, rows, widened

POLISH = "mcp:" + "-".join("7" * size for size in (8, 4, 4, 4, 12))
ROOT = "mcp:" + "-".join("6" * size for size in (8, 4, 4, 4, 12))
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


def said_in_polish(kitchen, words=SAID, thread=POLISH):
    """Keep the user's own message `words`, said in the polish home's thread (or `thread`), as a
    word, and return its id."""
    name = f"m{len(kitchen.t3.said)}"
    kitchen.t3.says(thread, name, words, title="home")
    code, out = kitchen.main("word", "--to", "demo", "--message", f"{thread}/{name}")
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
    assert (made["basis"], made["ref"], made["follows"]) == (queue.STANDING, word, "alpha")
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


def test_the_root_homes_standing_word_approves_a_follow_up_of_every_home(kitchen):
    (kitchen.home / "home-id").write_text(f"{ROOT}\n")
    word = said_in_polish(kitchen, thread=ROOT)
    code, out = stand(kitchen, "--word", word)
    assert code == 0, out
    assert out == (
        f"standing: demo, the root home approves its follow-ups that open no door on word {word}"
    )
    add(kitchen, "alpha", polish("alpha"))
    add(kitchen, "alpha-2", polish("alpha-2", "Follows: alpha\n"))
    made = rows(kitchen)["alpha-2"]["approval"]
    assert (made["basis"], made["ref"], made["follows"]) == (queue.STANDING, word, "alpha")


def parents(kitchen):
    """Queue the parents a follow-up may name: `ruled`, whose go the user gave and whose brief
    then changed, and `gone`, which the user removed before it merged."""
    add(kitchen, "ruled", polish("ruled"))
    assert go(kitchen, "ruled")[0] == 0
    add(kitchen, "ruled", widened("ruled").replace("Home: uncategorized", "Home: polish"))
    add(kitchen, "gone", polish("gone"))
    at = "2026-10-12 10:00 ET"
    kitchen.clock_reads(at)
    assert kitchen.main("queue", "remove", "gone", "--by", "user", "--at", at)[0] == 0


@pytest.mark.parametrize(
    ("follows", "why"),
    [
        ("beta", "beta cannot follow itself"),
        ("nope", "beta cannot follow nope: the queue has no row nope"),
        (
            "gone",
            "beta cannot follow gone: gone was removed 2026-10-12 10:00 ET by user, and its row "
            "did not go as merged",
        ),
        ("ruled", "beta cannot follow ruled: ruled's brief changed after its approval"),
    ],
    ids=["itself", "a slug the queue lacks", "a parent removed unmerged", "a changed parent"],
)
def test_a_follow_up_whose_parent_is_no_row_with_no_go_waits_for_the_user_word(
    kitchen, follows, why
):
    """The standing word stands only where the rule refused a parent for having no go: any other
    refusal of the parent is one the user's own go answers."""
    stand(kitchen, "--word", said_in_polish(kitchen))
    parents(kitchen)
    said = add(kitchen, "beta", polish("beta", f"Follows: {follows}\n"))
    assert said == [f"beta waits for the user's go, not a follow-up: {why}"]
    assert rows(kitchen)["beta"]["approved"] == ""


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
    assert (code, out) == (1, standing.NOT_OWN.format(id="said-by-user"))


def test_a_word_from_the_bots_chat_does_not_stand(kitchen):
    words = ("--evidence", CHAT, "--words", "approve the follow-ups [for: polish home]")
    code, out = kitchen.main("word", "--to", "demo", *words)
    assert code == 0, out
    said = out.split("word ")[-1].strip()
    assert stand(kitchen, "--word", said) == (1, standing.NOT_OWN.format(id=said))


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
    config = jbus.load()
    (demo,) = config.projects
    other = needs.lines(config, [demo], "demo", at, kitchen.home / "uncategorized")
    assert line in needs.lines(config, [demo], "demo", at, kitchen.home / "polish")
    assert line not in other
    stand(kitchen, "--word", word, "--withdraw")
    assert line not in kitchen.main("needs")[1].splitlines()


def test_a_second_run_changes_nothing_and_an_unknown_or_unheld_word_is_refused(kitchen):
    word = said_in_polish(kitchen)
    code, out = stand(kitchen, "--word", word, "--withdraw")
    assert (code, out) == (1, f"refused: the polish home of demo holds no standing word {word}")
    first = stand(kitchen, "--word", word)
    acted = (kitchen.state / "acts.jsonl").read_text()
    assert stand(kitchen, "--word", word) == first
    assert (kitchen.state / "acts.jsonl").read_text() == acted
    code, out = stand(kitchen, "--word", "nope")
    assert (code, out) == (1, f"refused: {kitchen.state / 'acts.jsonl'} has no word nope")


GOES = "give the plan entries their go yourself, don't wait on me"


def test_a_goes_word_stands_for_the_root_and_approves_no_follow_up(kitchen):
    """`--covers goes` makes the user's word the root's standing word for an entry's go, which
    `jbus plan go --standing` rests on. It is not a word for follow-ups, and a second run changes
    nothing."""
    (kitchen.home / "home-id").write_text(f"{ROOT}\n")
    word = said_in_polish(kitchen, GOES, thread=ROOT)
    code, out = stand(kitchen, "--word", word, "--covers", "goes")
    assert code == 0, out
    assert out == f"standing: demo, the root gives a plan entry its go on word {word}"
    acted = (kitchen.state / "acts.jsonl").read_text()
    assert stand(kitchen, "--word", word, "--covers", "goes") == (0, out)
    assert (kitchen.state / "acts.jsonl").read_text() == acted
    assert queue.standing_words(kitchen.state, queue.GOES)[""][0] == word
    assert queue.standing_words(kitchen.state) == {}
    add(kitchen, "alpha", polish("alpha"))
    add(kitchen, "alpha-2", polish("alpha-2", "Follows: alpha\n"))
    assert rows(kitchen)["alpha-2"]["approved"] == ""
    code, out = stand(kitchen, "--word", word, "--covers", "goes", "--withdraw")
    assert (code, out) == (
        0,
        f"withdrawn: demo, the root's standing word {word} for goes gives no more go",
    )
    assert queue.standing_words(kitchen.state, queue.GOES) == {}


def test_an_unchecked_a_bot_chat_or_another_threads_word_gives_the_root_no_goes(kitchen):
    kitchen.word()
    assert stand(kitchen, "--word", "said-by-user", "--covers", "goes") == (
        1,
        standing.NOT_OWN.format(id="said-by-user"),
    )
    words = ("--evidence", CHAT, "--words", "approve the goes [for: polish home]")
    code, out = kitchen.main("word", "--to", "demo", *words)
    assert code == 0, out
    chat = out.split("word ")[-1].strip()
    assert stand(kitchen, "--word", chat, "--covers", "goes") == (
        1,
        standing.NOT_OWN.format(id=chat),
    )
    (kitchen.home / "home-id").write_text(f"{ROOT}\n")
    for thread in (POLISH, "mcp:crew-alpha"):
        said = said_in_polish(kitchen, GOES, thread=thread)
        assert stand(kitchen, "--word", said, "--covers", "goes") == (
            1,
            f"refused: word {said} was not said in the root's thread, and only a word said there "
            "stands for goes",
        )
    assert queue.standing_words(kitchen.state, queue.GOES) == {}
