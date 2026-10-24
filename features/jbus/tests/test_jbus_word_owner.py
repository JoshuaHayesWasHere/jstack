"""A word goes to the one home that owns its subject, and a home queues no row of another home's.

The subject of a word is the page it was given on, or the briefs, requests and rows it names by
slug. A scoped home owns a subject whose brief or request has its `Home:` line, or a page in its own
directory or named for such a slug. Any other word is the root home's. Two homes that both acted on
one word wrote two briefs for one fix, so jbus carries each word to one home, and `jbus queue add`
refuses a home's row whose brief names another home, unless `--for` hands it over.

The tests run the real command against the kitchen's faked T3 Code server.
"""

import pytest

from jbus import word
from test_jbus_kitchen import Kitchen, complete, sends
from test_jbus_word import AT, thread

ROOT, FLOW, CREW = thread("a"), thread("f"), thread("c")
SCOPE = "flow"
SAID = ("--by", "user", "--at", AT)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "home-id").write_text(f"{ROOT}\n")
    (made.home / SCOPE).mkdir()
    (made.home / SCOPE / "plan.md").write_text("# the flow plan\n")
    (made.home / SCOPE / "home-id").write_text(f"{FLOW}\n")
    made.brief("fl-statechart", f"Home: {SCOPE}\n", kind="scouts")
    made.brief("fl-s1-stack", f"Home: {SCOPE}\n")
    made.brief("fix-login")
    yield made
    made.close()


def says(kitchen, *words, more=()):
    return kitchen.main("word", "--to", "demo", *SAID, *more, *words)


def to(kitchen):
    return [one["threadId"] for one in sends(kitchen)]


def test_a_word_that_names_a_scoped_homes_report_goes_to_that_home_alone(kitchen):
    code, out = says(kitchen, "Let's", "fix", "the", "bugs", "of", "the", "fl-statechart", "report")
    assert to(kitchen) == [FLOW]
    assert (code, out.startswith(f"sent: demo, to the {SCOPE} home at {FLOW}, word ")) == (0, True)
    kitchen.poll()
    assert to(kitchen) == [FLOW]


def test_a_word_that_names_a_row_with_a_scoped_homes_home_line_goes_to_that_home(kitchen):
    assert says(kitchen, "land", "fl-s1-stack", "first")[0] == 0
    assert to(kitchen) == [FLOW]


def test_a_word_given_on_a_page_goes_to_the_home_whose_page_it_is(kitchen):
    page = kitchen.home / "reports" / "fl-statechart" / "index.html"
    assert says(kitchen, "fix", "them", more=("--page", str(page)))[0] == 0
    own = kitchen.home / SCOPE / "grill-gates.html"
    assert says(kitchen, "yes", "to", "all", more=("--page", str(own)))[0] == 0
    assert to(kitchen) == [FLOW, FLOW]


def test_the_page_decides_over_the_slugs_its_words_name(kitchen):
    page = kitchen.home / "reports" / "fl-statechart.html"
    assert says(kitchen, "and", "fix-login", "too", more=("--page", str(page)))[0] == 0
    assert to(kitchen) == [FLOW]


def test_a_word_about_the_roots_work_or_about_no_brief_goes_to_the_root(kitchen):
    assert says(kitchen, "fix-login", "can", "wait")[0] == 0
    assert says(kitchen, "hold", "every", "merge")[0] == 0
    assert to(kitchen) == [ROOT, ROOT]


def test_a_word_that_names_two_homes_work_goes_to_the_root(kitchen):
    assert says(kitchen, "fix-login", "before", "fl-s1-stack")[0] == 0
    assert to(kitchen) == [ROOT]


def test_the_root_that_records_a_scoped_homes_word_forwards_it_and_the_scope_keeps_its_own(
    kitchen,
):
    code, out = says(kitchen, "fix", "fl-statechart", more=("--from", ROOT))
    assert (code, out.startswith(f"sent: demo, to the {SCOPE} home at {FLOW}, word ")) == (0, True)
    assert to(kitchen) == [FLOW]
    code, out = says(kitchen, "drop", "fl-s1-stack", more=("--from", FLOW))
    assert (code, out.startswith("kept: demo, not posted, ")) == (0, True)
    assert to(kitchen) == [FLOW]
    (_, kept) = word.load(kitchen.state)
    assert kept.thread == FLOW


def test_a_scoped_homes_word_waits_for_its_home_and_not_for_the_root(kitchen):
    (kitchen.home / SCOPE / "home-id").write_text("")
    code, out = says(kitchen, "fix", "fl-statechart")
    assert (code, out.startswith(f"waits: demo, for the {SCOPE} home, ")) == (0, True)
    kitchen.poll()
    assert to(kitchen) == []
    (kitchen.home / SCOPE / "home-id").write_text(f"{FLOW}\n")
    kitchen.poll()
    assert to(kitchen) == [FLOW]


def queues(kitchen, slug, home="", *more):
    lines = f"Home: {home}\n" if home else ""
    argv = ("queue", "add", slug, "--priority", "1", *more)
    return kitchen.main(*argv, stdin=complete(slug, lines))


def test_a_home_queues_no_row_whose_brief_names_another_home(kitchen):
    code, out = queues(kitchen, "fl-new", SCOPE, "--from", ROOT)
    assert code != 0
    assert out.startswith(
        f"refused: fl-new's brief is the {SCOPE} home's, and the root home adds it: "
    )
    code, out = queues(kitchen, "root-job", "", "--from", FLOW)
    assert (
        code,
        out.startswith(
            f"refused: root-job's brief is the root home's, and the {SCOPE} home adds it: "
        ),
    ) == (1, True)
    assert "fl-new" not in kitchen.main("queue", "show")[1]


def test_a_home_queues_its_own_rows_and_hands_another_homes_over_with_for(kitchen):
    assert queues(kitchen, "fl-mine", SCOPE, "--from", FLOW)[0] == 0
    assert queues(kitchen, "root-mine", "", "--from", ROOT)[0] == 0
    assert queues(kitchen, "fl-given", SCOPE, "--from", ROOT, "--for", SCOPE)[0] == 0
    code, out = queues(kitchen, "fl-wrong", SCOPE, "--from", ROOT, "--for", "root")
    assert (
        code,
        out.startswith(f"refused: --for root, and fl-wrong's brief is the {SCOPE} home's"),
    ) == (1, True)
    table = kitchen.main("queue", "show")[1]
    assert all(slug in table for slug in ("fl-mine", "root-mine", "fl-given"))
    assert "fl-wrong" not in table


def test_a_from_that_is_no_homes_thread_is_refused(kitchen):
    code, out = queues(kitchen, "fl-crew", SCOPE, "--from", CREW)
    assert (code, out.startswith(f"refused: --from {CREW} is no home of demo now")) == (1, True)
