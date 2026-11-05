"""A word that names rows whose briefs only jbus keeps goes to the home that owns the rows.

On 11-05 the user's word ended "[for: vv-noise-architect, ..., vv-noise-writing]", 41 slugs of
rows the verify home had queued, and still went to the root home. jbus looked for a slug's brief
only in the home's tasks/ and scouts/, and the vv-noise briefs were only in jbus's own briefs dir,
the copy `queue add` keeps of a row's brief. A slug is now found there too, by its brief's `Home:`
line. The same day's review found that a bot-chat word "go [for: cicd home]" that keeps no bot's
message was refused as bare, since it names no row: a scope named in `[for: ...]` names a home,
so the word is kept for it.
"""

import pytest

from jbus import word
from test_jbus_acts import CHAT
from test_jbus_queue import add, brief
from test_jbus_word_for_scope import CICD, ROOT, kept, to

VERIFY = "home-verify"


@pytest.fixture(autouse=True)
def homes(kitchen):
    (kitchen.home / "home-id").write_text(f"{ROOT}\n")
    for scope, thread in (("cicd", CICD), ("verify", VERIFY)):
        (kitchen.home / scope).mkdir()
        (kitchen.home / scope / "home-id").write_text(f"{thread}\n")
    for slug in ("vv-noise-architect", "vv-noise-writing"):
        text = brief(slug).replace("Home: root\n", "Home: verify\n")
        add(kitchen, slug, approve=False, text=text)
        assert not (kitchen.home / "tasks" / f"{slug}.md").exists()


def test_a_word_for_rows_whose_briefs_only_jbus_keeps_goes_to_the_home_that_queued_them(kitchen):
    code, out = kitchen.main(
        "word",
        "--to",
        "demo",
        "--evidence",
        CHAT,
        "--words",
        "go on [for: vv-noise-architect, vv-noise-writing]",
    )
    assert code == 0, out
    assert out.startswith(f"sent: demo, to the verify home at {VERIFY}, word "), out
    assert kept(kitchen) == ["verify"] and to(kitchen) == [VERIFY]


def test_a_new_slug_with_the_prefix_of_those_rows_goes_to_their_home(kitchen):
    code, out = kitchen.main(
        "word",
        "--to",
        "demo",
        "--evidence",
        CHAT,
        "--words",
        "go [for: vv-noise-reader]",
        "--answers",
        "Start it?",
    )
    assert code == 0, out
    assert kept(kitchen) == ["verify"] and to(kitchen) == [VERIFY]


def test_a_bot_chat_word_for_a_scope_with_no_answers_is_kept_for_that_scope(kitchen):
    code, out = kitchen.main(
        "word", "--to", "demo", "--evidence", CHAT, "--words", "go [for: cicd home]"
    )
    assert code == 0, out
    assert out.startswith(f"sent: demo, to the cicd home at {CICD}, word "), out
    assert kept(kitchen) == ["cicd"] and to(kitchen) == [CICD]


def test_a_bot_chat_word_for_no_scope_and_no_row_is_still_refused_as_bare(kitchen):
    code, out = kitchen.main(
        "word", "--to", "demo", "--evidence", CHAT, "--words", "go [for: ops home]"
    )
    assert (code, out.strip()) == (1, word.BARE_WORD)
    assert kept(kitchen) == [] and to(kitchen) == []
