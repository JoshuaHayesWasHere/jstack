"""One word, one home: a word about a scoped home's work reaches that home's start alone.

The root home and a scoped one run the home skill's own blocks, as `test_gates` runs them, against
the real `jbus` in the kitchen. The block of a start that prints what jbus carried to this thread
shows a word about the scope's brief to the scoped home alone. The root home that records such a
word forwards it with the skill's block, and the block that queues a row refuses the root a brief
the scoped home owns.
"""

import pytest

from test_gates import AT, SCOPE, Home
from test_jbus_kitchen import complete
from test_jbus_word import thread

ROOT, SCOPED = thread("a"), thread("f")

NONE = "no word: jbus carried none to this thread"
RECORDS = 'jbus word --to "$P" --from "$ME"'
QUEUES = "no row: jbus has no plan"


@pytest.fixture
def home(tmp_path, monkeypatch):
    made = Home(tmp_path, monkeypatch)
    (made.dir / "home-id").write_text(f"{ROOT}\n")
    (made.dir / SCOPE / "home-id").write_text(f"{SCOPED}\n")
    (made.dir / "plan.md").write_text("# the root plan\n")
    made.kitchen.brief("sp-chart", f"Home: {SCOPE}\n", kind="scouts")
    yield made
    made.kitchen.close()


def test_a_word_about_a_scoped_homes_report_is_shown_at_that_homes_start_alone(home):
    said = ("--by", "user", "--at", AT, "fix", "the", "bugs", "of", "the", "sp-chart", "report")
    assert home.kitchen.main("word", "--to", "demo", *said)[0] == 0
    assert home.word(SCOPED) == f"user, {AT}: fix the bugs of the sp-chart report"
    assert home.word() == NONE


def test_the_root_home_that_records_a_scoped_homes_word_forwards_it_there(home):
    home.kitchen.t3.says("mcp:sous", "m1", "drop sp-chart", title="Sous Chef")
    ran = home.home(RECORDS, ROOT, **{"<thread id>/<message id>": "mcp:sous/m1"})
    assert ran.startswith(f"sent: demo, to the {SCOPE} home at {SCOPED}, word ")
    assert home.word(SCOPED).endswith(": drop sp-chart")
    assert home.word() == NONE


@pytest.mark.parametrize(("thread", "queued"), [(ROOT, False), (SCOPED, True)])
def test_the_block_that_queues_a_row_adds_a_scoped_homes_brief_for_that_home_alone(
    home, thread, queued
):
    (home.dir / "tasks" / "sp-fix.md").write_text(complete("sp-fix", f"Home: {SCOPE}\n"))
    filled = {"<slug>": "sp-fix", "<n>": "1", "<entry>": "sp-fix"}
    ran = home.home(QUEUES, thread, **filled)
    if queued:
        assert ran == "added: the row sp-fix, of the entry sp-fix"
    else:
        assert ran.startswith(f"refused: sp-fix's brief is the {SCOPE} home's, and the root ")
    assert ("sp-fix" in home.kitchen.main("queue", "show")[1]) is queued
