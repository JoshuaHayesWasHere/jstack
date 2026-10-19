"""A home may approve a follow-up by a standing rule, with the parent row named.

`queue approve --rule <n> --follows <parent slug>` is the fourth basis. It rests on a rule of
the home's `standing.md`, which jbus reads itself, and on a parent row the user gave his own
word for. The row says he did not speak of it. Every test runs the real command against the
faked T3 Code server of `test_jbus_kitchen`.
"""

import json
import shlex
from pathlib import Path

import pytest

import jbus
from jbus import digest, queue
from jbus.view import state as view_state
from test_jbus_kitchen import NOW, RAN, SAID, SESSION, Kitchen, bound
from test_jbus_queue import NO_BASIS, add, brief, rows, sha12, widened

RULE = "Follow-ups to approved work need no new approval. New work needs his go."
STANDING = f"""# demo: standing rules

## Who does what
5. Only his own words count.
6. {RULE}
7. Batch the asks,
   and recommend.
- a note under rule 7

## How he wants the work
8. Real fixes.
"""
BY_RULE = f"rule 6, follow-up of alpha; run {RAN} by the demo home; he did not speak of this row"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "standing.md").write_text(STANDING)
    yield made
    made.close()


def go(kitchen, slug, *basis):
    sha = sha12((kitchen.state / "briefs" / f"{slug}.md").read_text())
    return kitchen.main("queue", "approve", slug, *basis, "--sha", sha)


def follow(kitchen, slug, parent, rule="6"):
    return go(kitchen, slug, "--rule", rule, "--follows", parent)


def refusal(kitchen, slug, *basis):
    code, said = go(kitchen, slug, *basis)
    assert code == 1 and "approval" not in rows(kitchen)[slug]
    return said.strip()


def cell(kitchen, slug):
    lines = kitchen.main("queue", "show", "--all")[1].splitlines()
    (found,) = [line for line in lines if line.startswith(f"| {slug} |")]
    return found.split(" | ")[4]


def old_string(kitchen, slug):
    """The row as one approved before the record: it holds only a typed string."""
    table = json.loads((kitchen.state / "queue.json").read_text())
    for row in table:
        if row["slug"] == slug:
            del row["approval"]
            row["approved"] = "2026-10-11 09:00 ET by user"
    jbus.write_json(kitchen.state / "queue.json", table)


def test_an_approval_by_rule_is_a_record_of_the_rule_and_the_parent_and_the_row_launches(kitchen):
    kitchen.config(max_running=6)
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    code, said = follow(kitchen, "beta", "alpha")
    assert (code, cell(kitchen, "beta")) == (0, BY_RULE)
    assert said.splitlines()[-1].split(" | ")[4] == BY_RULE
    row = rows(kitchen)["beta"]
    assert row["approval"] == {
        "basis": "rule",
        "ref": "6",
        "words": RULE,
        "said_at": "",
        "said_in": "",
        "checked": True,
        "follows": "alpha",
        "ran_by": {"session": SESSION, "directory": str(kitchen.checkout)},
        "ran_at": RAN,
        **bound(kitchen, "beta"),
    }
    assert row["approved"] == BY_RULE
    assert "follows" not in rows(kitchen)["alpha"]["approval"]
    kitchen.poll()
    assert sorted(launch["title"] for launch in kitchen.t3.launches) == [
        "crew: alpha",
        "crew: beta",
    ]


@pytest.mark.parametrize(
    "basis",
    [
        ("--rule", "6", "--follows", "alpha", "--word", SAID),
        ("--rule", "6", "--follows", "alpha", "--answer", "1"),
        ("--rule", "6", "--follows", "alpha", "--message", "mcp:a-home/a-message"),
        ("--rule", "6"),
        ("--follows", "alpha"),
        ("--word", SAID, "--follows", "alpha"),
        ("--rule", "6", "--follows", "alpha", "--by", "user"),
    ],
)
def test_a_rule_beside_another_basis_or_with_no_parent_is_refused(kitchen, basis):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    assert refusal(kitchen, "beta", *basis) == f"refused: {NO_BASIS}"


def test_a_parent_that_is_no_row_or_has_no_go_or_is_the_row_itself_is_refused(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    assert refusal(kitchen, "beta", "--rule", "6", "--follows", "nope") == (
        "refused: beta cannot follow nope: the queue has no row nope"
    )
    assert refusal(kitchen, "beta", "--rule", "6", "--follows", "alpha") == (
        "refused: beta cannot follow alpha: alpha has no approval"
    )
    assert refusal(kitchen, "beta", "--rule", "6", "--follows", "beta") == (
        "refused: beta cannot follow itself"
    )


def test_a_parent_approved_by_rule_is_refused_and_the_refusal_names_its_own_parent(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    add(kitchen, "gamma", approve=False)
    assert follow(kitchen, "beta", "alpha")[0] == 0
    assert refusal(kitchen, "gamma", "--rule", "6", "--follows", "beta") == (
        "refused: gamma cannot follow beta: beta was approved by rule 6 as a follow-up of alpha, "
        "and a chain is one step: follow alpha, or take his word for gamma"
    )
    assert follow(kitchen, "gamma", "alpha")[0] == 0


def test_a_parent_that_holds_only_the_old_string_is_followed(kitchen):
    add(kitchen, "alpha")
    old_string(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    assert follow(kitchen, "beta", "alpha")[0] == 0
    assert rows(kitchen)["beta"]["approval"]["follows"] == "alpha"


@pytest.mark.parametrize(("status", "taken"), [("merged", True), ("queued", False)])
def test_a_removed_parent_is_followed_only_where_its_row_went_as_merged(kitchen, status, taken):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    was = {**rows(kitchen)["alpha"], "status": status}
    table = [row for row in json.loads((kitchen.state / "queue.json").read_text())]
    jbus.write_json(kitchen.state / "queue.json", [r for r in table if r["slug"] != "alpha"])
    at = "2026-10-12 10:00 ET"
    jbus.write_json(kitchen.state / "removed.json", {"alpha": {"at": at, "by": "user"}})
    move = {"slug": "alpha", "from": status, "to": "removed", "at": at, "row": was}
    (kitchen.state / "transitions.jsonl").write_text(json.dumps(move) + "\n")
    code, said = follow(kitchen, "beta", "alpha")
    assert (code == 0) == taken
    if not taken:
        assert said.strip() == (
            f"refused: beta cannot follow alpha: alpha was removed {at} by user, "
            "and its row did not go as merged"
        )


def test_a_rule_is_read_from_the_homes_standing_rules_up_to_the_next_rule_or_heading(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    standing = kitchen.home / "standing.md"
    assert refusal(kitchen, "beta", "--rule", "9", "--follows", "alpha") == (
        f"refused: {standing} has no rule 9"
    )
    assert refusal(kitchen, "beta", "--rule", "six", "--follows", "alpha") == (
        "refused: --rule is a rule's number, not six"
    )
    assert follow(kitchen, "beta", "alpha", rule="7")[0] == 0
    assert rows(kitchen)["beta"]["approval"]["words"] == (
        "Batch the asks,\n   and recommend.\n- a note under rule 7"
    )
    assert standing.read_text() == STANDING
    standing.unlink()
    add(kitchen, "gamma", approve=False)
    assert refusal(kitchen, "gamma", "--rule", "6", "--follows", "alpha") == (
        f"refused: {standing} has no rule 6"
    )


def test_the_home_of_the_folder_it_ran_in_is_named_as_who_ran_it(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    desk = kitchen.root / "elsewhere"
    desk.mkdir()
    kitchen.monkeypatch.chdir(desk)
    argv = ("--project", "demo", "queue", "approve", "beta", "--rule", "6", "--follows", "alpha")
    assert kitchen.main(*argv, "--sha", sha12(brief("beta")))[0] == 0
    named = BY_RULE.replace("the demo home", "the elsewhere home")
    assert rows(kitchen)["beta"]["approved"] == named


def test_the_views_row_says_the_same_line_and_is_marked_as_a_rule_approval(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    assert follow(kitchen, "beta", "alpha")[0] == 0
    sources = view_state.Sources(kitchen.state_dir, kitchen.root / "home")
    tasks = {
        one["slug"]: one for one in view_state.build(sources, "demo", NOW, lambda _: {})["tasks"]
    }
    assert tasks["beta"]["approved"] == BY_RULE == cell(kitchen, "beta")
    assert tasks["beta"]["by_rule"] == {"rule": "6", "follows": "alpha"}
    assert tasks["alpha"]["by_rule"] is None


def test_the_digest_counts_the_rows_approved_by_rule_since_the_time_asked_for(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    add(kitchen, "gamma", approve=False)
    assert follow(kitchen, "beta", "alpha")[0] == 0
    kitchen.monkeypatch.setattr(queue, "clock", lambda: NOW.replace(hour=18))
    assert follow(kitchen, "gamma", "alpha")[0] == 0
    one = {"slug": "beta", "rule": "6", "follows": "alpha", "at": RAN}
    two = {"slug": "gamma", "rule": "6", "follows": "alpha", "at": "2026-10-12 14:00 ET"}
    code, said = kitchen.main("digest", "--json", "--since", "2026-10-12T10:00")
    assert (code, json.loads(said)["projects"]["demo"]["by_rule"]) == (0, [one, two])
    late = digest.build(jbus.load(), since=NOW.replace(hour=17))
    assert late["projects"]["demo"]["by_rule"] == [two]
    assert (
        digest.build(jbus.load(), since=NOW.replace(hour=19))["projects"]["demo"]["by_rule"] == []
    )


def test_a_batch_takes_the_rule_and_the_parent_and_a_parent_approved_in_the_same_batch(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    kitchen.word()
    text = (
        f"approve alpha --word {SAID} --sha {sha12(brief('alpha'))}\n"
        f"approve beta --rule 6 --follows=alpha --sha {sha12(brief('beta'))}\n"
    )
    code, said = kitchen.main("queue", "apply", stdin=text)
    assert (code, said.splitlines()[1]) == (
        0,
        f"approved beta: brief {sha12(brief('beta'))}, {BY_RULE}",
    )
    assert queue.parse("approve beta --rule 6 --follows alpha --sha 0\n") == [
        (1, queue.Approve("beta", "rule", "6", "0", "alpha"))
    ]
    with pytest.raises(jbus.Refused, match="line 1: approve takes one basis"):
        queue.parse(f"approve beta --rule 6 --follows alpha --word {SAID} --sha 0\n")
    with pytest.raises(jbus.Refused, match="line 1: approve takes one basis"):
        queue.parse("approve beta --rule 6 --sha 0\n")


def test_the_command_the_home_skill_gives_for_a_follow_up_approves_one(kitchen):
    skill = (Path(__file__).parent.parent / "skills" / "home" / "SKILL.md").read_text()
    section = skill.partition("### A follow-up approved by a standing rule\n")[2].partition("\n#")[
        0
    ]
    (command,) = [line for line in section.splitlines() if line.startswith("jbus ")]
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    given = {"<project>": "demo", "<slug>": "beta", "<sha12>": sha12(brief("beta"))}
    argv = [(given | {"<parent>": "alpha"}).get(word, word) for word in shlex.split(command)[1:]]
    assert kitchen.main(*argv)[0] == 0
    assert cell(kitchen, "beta") == BY_RULE


def test_a_hold_of_the_parent_takes_the_go_of_its_queued_follow_ups_back(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    add(kitchen, "gamma", approve=False)
    assert follow(kitchen, "beta", "alpha")[0] == 0
    assert follow(kitchen, "gamma", "alpha")[0] == 0
    table = json.loads((kitchen.state / "queue.json").read_text())
    for row in table:
        row["status"] = "running" if row["slug"] == "gamma" else row["status"]
    jbus.write_json(kitchen.state / "queue.json", table)
    code, said = kitchen.main("queue", "apply", stdin="hold alpha\n")
    assert (code, said.strip()) == (
        0,
        "held alpha, and beta with it: a follow-up approved by rule has no go without its parent's",
    )
    held = rows(kitchen)
    assert (held["alpha"]["approved"], held["beta"]["approved"]) == ("", "")
    assert "approval" not in held["beta"] and held["gamma"]["approval"]["follows"] == "alpha"
    kitchen.poll()
    assert not {"crew: alpha", "crew: beta"} & {one["title"] for one in kitchen.t3.launches}


def test_a_removal_of_a_parent_that_did_not_merge_holds_its_follow_ups(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    assert follow(kitchen, "beta", "alpha")[0] == 0
    at = "2026-10-12 10:00 ET"
    code, said = kitchen.main("queue", "remove", "alpha", "--by", "user", "--at", at)
    assert code == 0 and said.splitlines()[0].endswith(
        ", and held beta: a follow-up approved by rule has no go without its parent's"
    )
    assert rows(kitchen)["beta"]["approved"] == ""


def test_a_parent_whose_brief_changed_after_its_go_is_not_followed(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "alpha", approve=False, text=widened("alpha", "More."))
    add(kitchen, "beta", approve=False)
    assert refusal(kitchen, "beta", "--rule", "6", "--follows", "alpha") == (
        "refused: beta cannot follow alpha: alpha's brief changed after its approval"
    )


def test_a_parent_removed_earlier_in_the_batch_is_followed_only_where_it_went_as_merged(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    at = "2026-10-12 10:00 ET"
    text = (
        f'remove alpha --by user --at "{at}"\n'
        f"approve beta --rule 6 --follows alpha --sha {sha12(brief('beta'))}\n"
    )
    code, said = kitchen.main("queue", "apply", stdin=text)
    assert (code, said.strip()) == (
        1,
        f"refused: line 2: beta cannot follow alpha: alpha was removed {at} by user, and its "
        "row did not go as merged, and nothing in the batch was applied",
    )
    table = json.loads((kitchen.state / "queue.json").read_text())
    for row in table:
        row["status"] = "merged" if row["slug"] == "alpha" else row["status"]
    jbus.write_json(kitchen.state / "queue.json", table)
    asks = queue.Asks(
        lambda _: "",
        lambda _: "",
        lambda _: None,
        lambda *_: queue.rule(kitchen.home / "standing.md", "6"),
    )
    said = queue.apply(kitchen.state, text, jbus.load().user, asks)
    assert said[1] == f"approved beta: brief {sha12(brief('beta'))}, {BY_RULE}"
    assert "alpha" not in rows(kitchen)


def test_an_approval_run_in_the_minute_a_digest_is_asked_from_is_listed(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    ran = NOW.replace(hour=18, minute=7, second=40)
    kitchen.monkeypatch.setattr(queue, "clock", lambda: ran)
    assert follow(kitchen, "beta", "alpha")[0] == 0
    one = {"slug": "beta", "rule": "6", "follows": "alpha", "at": "2026-10-12 14:07 ET"}
    for since, listed in ((ran.replace(second=30), [one]), (ran.replace(second=55), [one])):
        assert digest.build(jbus.load(), since=since)["projects"]["demo"]["by_rule"] == listed
    late = digest.build(jbus.load(), since=ran.replace(minute=8, second=0))
    assert late["projects"]["demo"]["by_rule"] == []


def test_queue_hold_of_a_parent_prints_the_follow_ups_it_held(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    assert follow(kitchen, "beta", "alpha")[0] == 0
    code, said = kitchen.main("queue", "hold", "alpha")
    assert (code, said.splitlines()[0]) == (
        0,
        "held alpha, and beta with it: a follow-up approved by rule has no go without its parent's",
    )
    assert rows(kitchen)["beta"]["approved"] == ""
    assert kitchen.main("queue", "hold", "alpha")[1].startswith("| slug |")


def test_a_row_that_another_row_follows_is_not_approved_by_rule_itself(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta")
    add(kitchen, "gamma", approve=False)
    assert follow(kitchen, "gamma", "beta")[0] == 0
    word = rows(kitchen)["beta"]["approval"]
    code, said = follow(kitchen, "beta", "alpha")
    assert (code, said.strip()) == (
        1,
        "refused: beta cannot follow alpha: gamma follow beta, and a chain is one step: take "
        "his word for beta",
    )
    assert rows(kitchen)["beta"]["approval"] == word
