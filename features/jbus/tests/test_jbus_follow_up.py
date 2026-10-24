"""A follow-up of an approved row is approved by the home's follow-up rule when it is queued.

The rule (`queue.FOLLOW_UP`) reads the row, its brief and the parent's row: the row names its
parent P (a `Follows: P` line, or the slug `cleanup-P`), the row is P's (its slug is `cleanup-P`,
or its entry is P's), and P's go is the user's own. The home's `follow-rule` file names the rule of
its `standing.md` that says so. A row of new work waits for the user's go, and only its decision
reaches the user. Every test runs the real `jbus queue add` and `approve`, and a pass, against the
kitchen's fakes.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import queue
from test_jbus_approve_by_rule import RULE, STANDING
from test_jbus_kitchen import RAN, SAID, Kitchen
from test_jbus_queue import brief, rows, sha12

BY_RULE = "rule 6, follow-up of {parent}; run {ran} by the demo home; you did not speak of this row"
NIGHT = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)
BUILDS_ON = "Builds on: alpha: the code of its pull request, which the findings are in\n"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "standing.md").write_text(STANDING)
    (made.home / "follow-rule").write_text("6\n")
    made.word()
    yield made
    made.close()


def add(kitchen, slug, *more, text=None):
    argv = ("queue", "add", slug, "--priority", "1", *more)
    code, said = kitchen.main(*argv, stdin=text or brief(slug))
    assert code == 0, said
    return said.partition("| slug |")[0].strip().splitlines()


def go(kitchen, slug):
    sha = sha12((kitchen.state / "briefs" / f"{slug}.md").read_text())
    return kitchen.main("queue", "approve", slug, "--word", SAID, "--sha", sha)


def follows(parent):
    return f"Follows: {parent}\n"


def decided(kitchen):
    return [line.split(":")[0] for line in kitchen.lines("decision")]


def test_three_follow_ups_queued_overnight_launch_and_only_the_new_rows_decision_is_sent(kitchen):
    """The replay: an approved entry, alpha, merged in the evening. Overnight, with the owner away,
    a review files cleanup-alpha and the home queues the entry's second and third units and one row
    of new work. The three follow-ups are approved by rule and launch that night, and the one
    decision sent asks for the new row."""
    kitchen.config(max_running=6)
    assert add(kitchen, "alpha") == []
    assert go(kitchen, "alpha")[0] == 0
    merged = [kitchen.merged("alpha", 7, "a" * 40, ago=timedelta(hours=-2))]
    (kitchen.stub / "merged.json").write_text(json.dumps(merged))
    kitchen.quiet()
    kitchen.poll(NIGHT - timedelta(hours=2))
    assert rows(kitchen)["alpha"]["status"] == "merged"
    kitchen.forget()
    queued = [
        ("cleanup-alpha", ("--depends", "alpha"), brief("cleanup-alpha", BUILDS_ON)),
        ("alpha-2", ("--entry", "alpha"), brief("alpha-2", follows("alpha"))),
        ("alpha-3", ("--entry", "alpha"), brief("alpha-3", follows("alpha"))),
        ("delta", (), brief("delta")),
    ]
    said = {slug: add(kitchen, slug, *more, text=text) for slug, more, text in queued}
    for slug in ("cleanup-alpha", "alpha-2", "alpha-3"):
        line = BY_RULE.format(parent="alpha", ran=RAN)
        assert said[slug] == [f"approved {slug}: brief {sha12(brief_of(kitchen, slug))}, {line}"]
        made = rows(kitchen)[slug]["approval"]
        assert (made["basis"], made["ref"], made["follows"], made["words"]) == (
            "rule",
            "6",
            "alpha",
            RULE,
        )
    assert said["delta"] == [] and rows(kitchen)["delta"]["approved"] == ""
    for hour in range(4):
        kitchen.poll(NIGHT + timedelta(hours=hour))
    launched = sorted(one["title"] for one in kitchen.t3.launches)
    assert launched == ["crew: alpha-2", "crew: alpha-3", "crew: cleanup-alpha"]
    assert decided(kitchen) == ["decision delta"]
    waits = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    assert [one["key"] for one in waits] == ["approve:delta"]
    posted = [one for post in kitchen.webhook.posts for one in post or []]
    assert {one["slug"] for one in posted if one["event"] == "decision"} == {"delta"}


def brief_of(kitchen, slug):
    return (kitchen.state / "briefs" / f"{slug}.md").read_text()


@pytest.mark.parametrize(
    ("slug", "more", "text", "why"),
    [
        (
            "cleanup-nope",
            (),
            None,
            "cleanup-nope cannot follow nope: the queue has no row nope",
        ),
        (
            "cleanup-unsaid",
            (),
            None,
            "cleanup-unsaid cannot follow unsaid: unsaid has no approval",
        ),
        (
            "beta",
            ("--entry", "unsaid"),
            brief("beta", follows("unsaid")),
            "beta cannot follow unsaid: unsaid has no approval",
        ),
        (
            "beta",
            (),
            brief("beta", follows("alpha")),
            "beta does not do work for alpha's plan entry alpha: its entry is beta",
        ),
        (
            "cleanup-gone",
            (),
            None,
            "cleanup-gone cannot follow gone: gone was removed 2026-10-12 10:00 ET by user, and "
            "its row did not go as merged",
        ),
    ],
    ids=[
        "no parent row",
        "a parent never approved",
        "a second unit of an unapproved row",
        "a Follows line with no entry of the parent's",
        "a parent removed unmerged",
    ],
)
def test_new_work_waits_for_the_users_go_and_its_decision_is_sent(kitchen, slug, more, text, why):
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    add(kitchen, "unsaid")
    add(kitchen, "gone")
    assert go(kitchen, "gone")[0] == 0
    at = "2026-10-12 10:00 ET"
    assert kitchen.main("queue", "remove", "gone", "--by", "user", "--at", at)[0] == 0
    kitchen.quiet()
    said = add(kitchen, slug, *more, text=text)
    assert said == [f"{slug} waits for the user's go, not a follow-up by rule 6: {why}"]
    assert rows(kitchen)[slug]["approved"] == ""
    kitchen.poll()
    assert sorted(decided(kitchen)) == sorted([f"decision {slug}", "decision unsaid"])


def test_a_row_that_names_no_parent_waits_and_add_says_nothing_of_the_rule(kitchen):
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    assert add(kitchen, "beta", "--entry", "alpha") == []
    assert rows(kitchen)["beta"]["approved"] == ""


def test_a_home_with_no_follow_rule_file_approves_no_row_by_rule(kitchen):
    (kitchen.home / "follow-rule").unlink()
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    kitchen.quiet()
    assert add(kitchen, "cleanup-alpha") == []
    assert rows(kitchen)["cleanup-alpha"]["approved"] == ""
    kitchen.poll()
    assert decided(kitchen) == ["decision cleanup-alpha"]


def test_a_follow_rule_the_standing_rules_lack_approves_nothing_and_says_so(kitchen):
    (kitchen.home / "follow-rule").write_text("9\n")
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    standing = kitchen.home / "standing.md"
    assert add(kitchen, "cleanup-alpha") == [
        f"cleanup-alpha waits for the user's go, not a follow-up by rule 9: {standing} has no "
        "rule 9"
    ]
    assert rows(kitchen)["cleanup-alpha"]["approved"] == ""


def test_a_follow_up_of_a_follow_up_waits_for_the_user(kitchen):
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    add(kitchen, "cleanup-alpha")
    assert add(kitchen, "cleanup-cleanup-alpha") == [
        "cleanup-cleanup-alpha waits for the user's go, not a follow-up by rule 6: "
        "cleanup-cleanup-alpha cannot follow cleanup-alpha: cleanup-alpha was approved by rule 6 "
        "as a follow-up of alpha, and a chain is one step: follow alpha, or take the user's word "
        "for cleanup-cleanup-alpha"
    ]


def test_a_batch_approves_a_follow_up_whose_parent_gets_its_go_later_in_the_batch(kitchen):
    text = (
        f"add alpha --priority 1\n--- brief alpha\n{brief('alpha')}--- end\n"
        f"add alpha-2 --priority 1 --entry alpha\n--- brief alpha-2\n"
        f"{brief('alpha-2', follows('alpha'))}--- end\n"
        f"approve alpha --word {SAID} --sha {sha12(brief('alpha'))}\n"
    )
    code, said = kitchen.main("queue", "apply", stdin=text)
    assert code == 0, said
    line = BY_RULE.format(parent="alpha", ran=RAN)
    assert f"approved alpha-2: brief {sha12(brief('alpha-2', follows('alpha')))}, {line}" in said
    assert rows(kitchen)["alpha-2"]["approval"]["follows"] == "alpha"


def test_the_users_go_for_a_parent_approves_its_waiting_follow_ups(kitchen):
    add(kitchen, "alpha")
    assert add(kitchen, "cleanup-alpha") == [
        "cleanup-alpha waits for the user's go, not a follow-up by rule 6: cleanup-alpha cannot "
        "follow alpha: alpha has no approval"
    ]
    code, said = go(kitchen, "alpha")
    line = BY_RULE.format(parent="alpha", ran=RAN)
    assert code == 0
    assert said.splitlines()[0] == (
        f"approved cleanup-alpha: brief {sha12(brief('cleanup-alpha'))}, {line}"
    )


def test_a_row_the_user_left_waiting_is_not_approved_by_adding_it_again(kitchen):
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    add(kitchen, "beta")
    assert add(kitchen, "beta", "--entry", "alpha", text=brief("beta", follows("alpha"))) == []
    assert rows(kitchen)["beta"]["approved"] == ""


def test_a_hold_of_the_parent_holds_its_follow_ups_and_adding_one_again_keeps_the_hold(kitchen):
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    add(kitchen, "cleanup-alpha")
    add(kitchen, "alpha-2", "--entry", "alpha", text=brief("alpha-2", follows("alpha")))
    code, said = kitchen.main("queue", "hold", "alpha")
    assert code == 0 and said.splitlines()[0] == (
        "held alpha, and alpha-2, cleanup-alpha with it: a follow-up approved by rule has no go "
        "without its parent's"
    )
    again = brief("cleanup-alpha", "One more note.\n")
    assert add(kitchen, "cleanup-alpha", text=again) == []
    assert (rows(kitchen)["cleanup-alpha"]["approved"], rows(kitchen)["alpha-2"]["approved"]) == (
        "",
        "",
    )


def test_a_follow_up_whose_brief_changed_meaning_is_approved_by_rule_again(kitchen):
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    add(kitchen, "cleanup-alpha")
    wider = brief("cleanup-alpha").replace("- it is done\n", "- it is done\n- and more\n")
    said = add(kitchen, "cleanup-alpha", text=wider)
    line = BY_RULE.format(parent="alpha", ran=RAN)
    assert said[-1] == f"approved cleanup-alpha: brief {sha12(wider)}, {line}"
    assert queue.approved_text(rows(kitchen)["cleanup-alpha"], wider)


def test_queue_add_help_gives_the_follow_up_rule_and_the_file_that_names_it(kitchen):
    code, said = kitchen.main("queue", "add", "--help")
    assert code == 0
    assert queue.FOLLOW_UP in " ".join(said.split())
    assert "follow-rule file names that rule of its standing.md" in " ".join(said.split())


def test_a_follow_up_whose_work_item_was_redirected_is_not_approved_by_rule(kitchen):
    """A redirect gives the item a new brief and holds its row, and a held row is never approved by
    rule: queued again as a follow-up, it waits for the user."""
    add(kitchen, "alpha")
    assert go(kitchen, "alpha")[0] == 0
    add(kitchen, "cleanup-alpha")
    name = rows(kitchen)["cleanup-alpha"]["item"]
    seen = kitchen.main("item", "show", name)[1].partition("last event: ")[2].split()[0]
    redirected = brief("cleanup-alpha", "Redirected.\n")
    argv = ("item", "steer", name, "redirect", "--seen", seen, "--by", "user", "--word", SAID)
    code, said = kitchen.main(*argv, stdin=redirected)
    assert code == 0, said
    assert rows(kitchen)["cleanup-alpha"]["approved"] == ""
    assert add(kitchen, "cleanup-alpha", text=redirected) == []
    assert rows(kitchen)["cleanup-alpha"]["approved"] == ""
    kitchen.quiet()
    kitchen.poll()
    assert "decision cleanup-alpha" in decided(kitchen)
