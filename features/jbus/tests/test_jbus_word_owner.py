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

ROOT, FLOW, NEXT, CREW, VIEW = thread("a"), thread("f"), thread("e"), thread("c"), thread("d")
SCOPE, OTHER = "flow", "view"
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
    (made.home / OTHER).mkdir()
    (made.home / OTHER / "home-id").write_text(f"{VIEW}\n")
    made.brief("vw-board", f"Home: {OTHER}\n")
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


def test_a_slug_that_ends_a_sentence_is_still_that_slug(kitchen):
    kitchen.brief("fl-other")
    assert says(kitchen, "fix", "fl-statechart.", "Then", "stop.")[0] == 0
    assert to(kitchen) == [FLOW]


def test_a_word_that_names_a_row_with_a_scoped_homes_home_line_goes_to_that_home(kitchen):
    assert says(kitchen, "land", "fl-s1-stack", "first")[0] == 0
    assert to(kitchen) == [FLOW]


def test_a_word_that_names_a_new_slug_of_a_scoped_homes_prefix_goes_to_that_home(kitchen):
    assert says(kitchen, "brief", "fl-brand-new", "for", "it")[0] == 0
    assert says(kitchen, "a", "follow-up", "on", "fl-brand-new")[0] == 0
    assert to(kitchen) == [FLOW, FLOW]


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


def test_a_word_that_names_no_slug_stays_in_the_home_that_recorded_it(kitchen):
    code, out = says(kitchen, "show", "me", "the", "board", more=("--from", FLOW))
    assert (code, out.startswith("kept: demo, not posted, it was recorded by ")) == (0, True)
    assert to(kitchen) == []
    (kept,) = word.load(kitchen.state)
    assert (kept.home, kept.thread) == (SCOPE, FLOW)
    kitchen.poll()
    assert to(kitchen) == []


def test_a_word_said_in_a_scoped_homes_thread_stays_in_that_scope(kitchen):
    kitchen.t3.says(FLOW, "m1", "show me the board", title="home: demo flow")
    code, out = kitchen.main("word", "--to", "demo", "--message", f"{FLOW}/m1", "--from", ROOT)
    assert (code, out.startswith("kept: demo, not posted, it was said in ")) == (0, True)
    assert to(kitchen) == []
    (kept,) = word.load(kitchen.state)
    assert (kept.home, kept.thread) == (SCOPE, FLOW)


def test_the_same_word_recorded_by_the_root_is_the_roots(kitchen):
    code, out = says(kitchen, "show", "me", "the", "board", more=("--from", ROOT))
    assert (code, out.startswith("kept: demo, not posted, it was recorded by ")) == (0, True)
    assert "went to the root home" not in out
    (kept,) = word.load(kitchen.state)
    assert (kept.home, kept.thread) == ("", ROOT)


def test_a_scoped_homes_word_that_names_another_scopes_slug_goes_to_that_scope(kitchen):
    code, out = says(kitchen, "show", "vw-board", "first", more=("--from", FLOW))
    assert (code, out.startswith(f"sent: demo, to the {OTHER} home at {VIEW}, word ")) == (0, True)
    assert to(kitchen) == [VIEW]


def test_a_scoped_homes_word_that_names_the_roots_slug_goes_to_the_root(kitchen):
    assert says(kitchen, "fix-login", "can", "wait", more=("--from", FLOW))[0] == 0
    assert to(kitchen) == [ROOT]


def test_a_word_from_no_home_that_falls_to_the_root_says_so(kitchen):
    code, out = says(kitchen, "show", "me", "the", "board")
    assert code == 0
    assert to(kitchen) == [ROOT]
    assert "went to the root home" in out
    assert "went to the root home" not in says(kitchen, "fix", "fl-statechart")[1]


def test_a_scoped_homes_word_waits_for_its_home_and_not_for_the_root(kitchen):
    (kitchen.home / SCOPE / "handoff.md").write_text(f"# flow: handoff\nWas home: {FLOW}\n")
    code, out = says(kitchen, "fix", "fl-statechart")
    assert (code, out.startswith(f"waits: demo, for the {SCOPE} home, ")) == (0, True)
    kitchen.poll()
    assert to(kitchen) == []
    (kitchen.home / SCOPE / "home-id").write_text(f"{NEXT}\n")
    kitchen.poll()
    assert to(kitchen) == [NEXT]


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
