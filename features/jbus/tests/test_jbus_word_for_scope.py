"""A word whose trailing `[for: ...]` names scoped homes of the project goes to each of them.

On 11-05 the user said in the bot's chat that each flow gets a home of its own, ending the words
"[for: cicd home, docs home, lab home, verify home]". jbus routed a word only by the slugs it
names, so the word went to the root home. A word that names scoped homes, by name or as
"<scope> home", is now kept once for each of them and sent to each one's thread, as `--scope`
does for a T3 message. The tests drive the bot's own route `POST /act` and `jbus word`.
"""

import pytest

from jbus import acts, word
from test_jbus_acts import CHAT, Route
from test_jbus_kitchen import sends
from test_jbus_queue import add

ROOT, CICD, DOCS = "home-root", "home-cicd", "home-docs"
ASKED = "Make a home for each flow?"
SAID = "Each flow gets its own sub-home. [for: cicd home, docs home]"


@pytest.fixture
def route(kitchen):
    made = Route(kitchen)
    yield made
    made.close()


@pytest.fixture(autouse=True)
def homes(kitchen):
    add(kitchen, "alpha", approve=False)
    (kitchen.home / "home-id").write_text(f"{ROOT}\n")
    for scope, thread in (("cicd", CICD), ("docs", DOCS), ("lab", "home-lab")):
        (kitchen.home / scope).mkdir()
        (kitchen.home / scope / "home-id").write_text(f"{thread}\n")


def kept(kitchen):
    """The home each word act is for, by the order jbus kept them."""
    return [
        one["action"]["subject"]
        for one in acts.read(kitchen.state)
        if one["action"]["verb"] == "word"
    ]


def to(kitchen):
    return [one["threadId"] for one in sends(kitchen) if one["clientRequestId"].startswith("word|")]


def test_the_bots_word_for_two_scoped_homes_goes_to_each_and_not_to_the_root(kitchen, route):
    body = {"action": "word", "words": SAID, "evidence": CHAT, "answers": ASKED}
    status, said = route.act(body)
    assert status == 200, said
    assert kept(kitchen) == ["cicd", "docs"]
    assert sorted(to(kitchen)) == [CICD, DOCS]
    assert all(one["message"].endswith(ASKED) for one in sends(kitchen))
    assert said["say"].splitlines()[0].startswith(f"sent: demo, to the cicd home at {CICD}, word ")
    assert said["say"].splitlines()[1].startswith(f"sent: demo, to the docs home at {DOCS}, word ")
    assert route.act(body)[0] == 200
    kitchen.poll()
    assert kept(kitchen) == ["cicd", "docs"] and sorted(to(kitchen)) == [CICD, DOCS]


def test_jbus_word_for_two_scoped_homes_goes_to_each_and_not_to_the_root(kitchen):
    argv = ("word", "--to", "demo", "--evidence", CHAT, "--words", SAID, "--answers", ASKED)
    code, out = kitchen.main(*argv)
    assert code == 0, out
    cicd, docs = out.splitlines()
    assert cicd.startswith(f"sent: demo, to the cicd home at {CICD}, word ")
    assert docs.startswith(f"sent: demo, to the docs home at {DOCS}, word ")
    assert kept(kitchen) == ["cicd", "docs"]
    assert sorted(to(kitchen)) == [CICD, DOCS]
    code, again = kitchen.main(*argv)
    assert code == 0 and all(
        one.startswith("already sent: demo, to the ") for one in again.splitlines()
    )
    kitchen.poll()
    assert kept(kitchen) == ["cicd", "docs"] and sorted(to(kitchen)) == [CICD, DOCS]


def test_a_word_for_a_slug_beside_a_scope_keeps_its_slug_routing(kitchen):
    code, out = kitchen.main(
        "word", "--to", "demo", "--evidence", CHAT, "--words", "go [for: alpha, cicd home]"
    )
    assert code == 0, out
    assert kept(kitchen) == [""] and to(kitchen) == [ROOT]


def test_a_name_that_is_no_scope_and_no_slug_changes_nothing(kitchen):
    code, out = kitchen.main(
        "word",
        "--to",
        "demo",
        "--evidence",
        CHAT,
        "--words",
        "go [for: ops home]",
        "--answers",
        ASKED,
    )
    assert code == 0, out
    assert kept(kitchen) == [""] and to(kitchen) == [ROOT]
    assert word.load(kitchen.state)[0].home == ""


def test_a_word_that_names_a_scope_by_its_name_alone_goes_to_that_home(kitchen):
    code, out = kitchen.main(
        "word", "--to", "demo", "--evidence", CHAT, "--words", "go [for: Lab]", "--answers", ASKED
    )
    assert code == 0, out
    assert out.startswith("sent: demo, to the lab home at home-lab, word ")
    assert kept(kitchen) == ["lab"] and to(kitchen) == ["home-lab"]
