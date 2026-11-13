"""`jbus needs` prints what waits on the user, for one project or for all: each item with what it
holds and a plain hint for the reply (`jbus.blockers.reply`), and nothing a home can clear by
itself.

Like `test_jbus_kitchen.py`, the tests run the real commands and the real pass against a faked T3
Code server, `gh` and `jmerge`. Nothing reaches the network.
"""

import json
import os
import re
from datetime import timedelta

import pytest

import jbus
from jbus import acts, homestatus, questions, snapshot, verbs, work
from test_jbus_build_behind import machine, patched
from test_jbus_kitchen import GATE, NOW, RESULT
from test_jbus_leftover import home
from test_jbus_questions import held
from test_jbus_queue import add, brief, go
from test_jbus_scout import request
from test_jbus_snapshot import killed, take, tree_fixture, with_origin  # noqa: F401

HOLDS = "hold 9 https://example.test/pull/9: needs user, touches skills/crew/SKILL.md"


AFTER = NOW + timedelta(minutes=5)
"""A few minutes after the pass, past a row's grace."""


def needs(kitchen, *argv, at=AFTER, home=None):
    """What `jbus needs` prints at `at`, for the home `home` where it is given."""
    kitchen.monkeypatch.setattr(verbs, "clock", lambda: at)
    code, out = kitchen.main(*argv, "needs", *(["--home", str(home)] if home else []))
    assert code == 0, out
    return out.splitlines()


def test_an_open_gate_that_holds_is_listed_with_what_it_holds_and_the_reply_that_answers_it(
    kitchen,
):
    kitchen.brief("alpha")
    assert kitchen.main("gate", "alpha", stdin=held())[0] == 0
    kitchen.poll()
    assert needs(kitchen) == [
        "waiting on user: 1, in demo",
        "demo question 1: drop the old branch, it holds (deletes data) for your answer",
        "  fail-safe: the dry-run in /tmp/gone.txt",
        "  answer: reply in your own words to keep the default (the first one) or say what "
        "to do instead",
    ]


def test_a_row_awaiting_the_users_word_and_a_held_pull_request_are_listed(kitchen):
    add(kitchen, "unsaid", approve=False)
    kitchen.brief("held", RESULT)
    kitchen.set("open.json", [kitchen.opened("held", 9)])
    kitchen.set("jmerge.txt", HOLDS + "\n")
    kitchen.poll()
    command = "jbus --project demo queue approve unsaid with"
    said = needs(kitchen)
    assert said[0] == "waiting on user: 2, in demo"
    assert said[1].startswith(f"demo approve unsaid: {command}")
    assert said[1].endswith(", a row with no approval of its brief")
    assert said[2] == (
        "  answer: reply in your own words to give unsaid its go or say what to do instead"
    )
    assert said[3:] == [
        f"demo {HOLDS}, a pull request jmerge holds for your word",
        "  answer: reply in your own words to merge #9 or say what to do instead",
    ]


def test_nothing_needs_prints_or_a_decision_says_gives_the_user_words_to_send(kitchen):
    """Each item ends in a plain hint: the user replies in their own words, and the home turns
    them into a verb. A `say "..."` line is what a home copied to the user as words to send."""
    kitchen.config(max_running=6)
    kitchen.quiet()
    kitchen.brief("alpha")
    assert kitchen.main("gate", "alpha", stdin=held())[0] == 0
    sc = scoped(kitchen, "sc")
    asked = GATE.format(n=1, asked="drop the old rows?", status="open", slug="home")
    (sc / "gates.md").write_text(asked.replace("Option:", "Holds: deletes data\nOption:", 1))
    add(kitchen, "unsaid", approve=False)
    kitchen.brief("held", RESULT)
    kitchen.set("open.json", [kitchen.opened("held", 9)])
    kitchen.set("jmerge.txt", HOLDS + "\n")
    kitchen.poll()
    kitchen.poll(AFTER)
    said = needs(kitchen)
    decided = kitchen.lines("decision")
    assert len([one for one in said if one.startswith("  answer: ")]) == 4, said
    assert len(decided) == 4, decided
    for line in [*said, *decided]:
        assert 'say "' not in line, line
        assert not re.search(r"(?:question \d+: default|gate [\w#]*\d+: hold it)", line), line
        assert not re.search(r"(?:#\d+: merge it|approve [\w-]+: go)", line), line


def test_a_decision_raised_by_hand_carries_the_homes_hint_as_it_is(kitchen):
    kitchen.quiet()
    hint = "reply in your own words to add the sign-in or say what to do instead"
    asked = ("decide", "alpha", "--question", "add a second sign-in to the plan?", "--reply", hint)
    assert kitchen.main(*asked) == (0, "raised: alpha: add a second sign-in to the plan?\n")
    assert kitchen.lines("decision") == [
        f"decision alpha: add a second sign-in to the plan?. Reply: {hint}"
    ]


def test_with_nothing_open_it_says_nothing_waits(kitchen):
    kitchen.poll()
    assert needs(kitchen) == ["nothing waits on user in any project"]
    assert needs(kitchen, "--project", "demo") == ["nothing waits on user in demo"]


def test_a_go_typed_with_a_stale_sha_is_done_and_nothing_is_listed(kitchen):
    add(kitchen, "retried", approve=False)
    assert go(kitchen, "retried", sha="0" * 12)[0] == 0
    assert [one["outcome"] for one in acts.read(kitchen.state)][-1:] == ["done"]
    kitchen.poll()
    assert needs(kitchen) == ["nothing waits on user in any project"]


def test_a_row_its_home_can_clear_and_a_gate_whose_default_stands_are_not_listed(kitchen):
    add(kitchen, "stuck")
    kitchen.t3.thread("stuck", "failed", settled=True)
    (kitchen.home / "gates.md").write_text(
        GATE.format(n=4, asked="which way?", status="open", slug="home")
    )
    kitchen.poll()
    kinds = [one["kind"] for one in jbus.read_json(kitchen.state / "waiting-on-user.json", [])]
    assert kinds == ["gate", "row"]
    assert needs(kitchen) == ["nothing waits on user in any project"]


def test_a_go_gate_whose_silence_starts_nothing_waits_on_the_user(kitchen):
    add(kitchen, "picked", approve=False)
    asked = GATE.format(n="<n>", asked="start picked?", status="open", slug="picked")
    lines = asked.replace("Default: the first one", "Default: approve").replace(
        "Option: the first one (default, recommended)", "Option: approve (default, recommended)"
    )
    assert kitchen.main("gate", "picked", stdin=lines)[0] == 0
    kitchen.poll()
    said = needs(kitchen)
    assert (
        "demo question 1: start picked, its silence starts nothing, since the setting go is "
        "entry, not silence" in said
    )


def test_all_projects_or_one(kitchen):
    other = kitchen.second()
    kitchen.brief("alpha")
    assert kitchen.main("gate", "alpha", stdin=held())[0] == 0
    kitchen.poll()
    assert needs(kitchen)[0] == "waiting on user: 1, in demo"
    assert needs(kitchen, "--project", other.name) == ["nothing waits on user in other"]


def test_a_project_no_pass_has_listed_is_not_said_to_have_nothing_waiting(kitchen):
    other = kitchen.second()
    assert needs(kitchen, "--project", other.name) == [
        "not known: other: no pass has listed what waits there yet",
        "nothing else known waits on user in other",
    ]


AWAITS_REVIEW = (
    "\n## Result\nStatus: done\nBranch: a-branch   Pull request: after the review\n"
    "Left: the docs page\n"
)


@pytest.mark.parametrize("homed", [True, False], ids=["a home", "no home"])
def test_a_row_work_json_says_is_the_users_is_one_jbus_needs_lists(kitchen, homed):
    """The sidebar draws `work.json`'s `who`, which `jbus.states.keep_work` writes: a row it says
    waits on the user is one `jbus needs` lists, and no other. A row that ended with something
    left is its home's to close, even while no home thread is there to tell; a row whose Result
    opens its pull request after a review not written yet waits on that review, whatever its
    `Left:` line says; a gate of the user's that holds its row is the user's."""
    if homed:
        at = kitchen.t3.thread("demo", "completed", title="home: demo")
        (kitchen.home / "home-id").write_text(at["threadId"] + "\n")
    add(kitchen, "left")
    kitchen.brief(
        "left",
        "\n## Result\nStatus: done\nBranch: a-branch   Pull request: none\nLeft: the docs page\n",
    )
    kitchen.t3.thread("left", "completed")
    add(kitchen, "reviewed")
    kitchen.brief("reviewed", "Review: review\n" + AWAITS_REVIEW)
    kitchen.t3.thread("reviewed", "completed")
    add(kitchen, "gated")
    assert kitchen.main("gate", "gated", stdin=held())[0] == 0
    for minutes in (0, 1):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    lines = {one["key"]: one for one in json.loads((kitchen.state / work.NAME).read_text())["work"]}
    asked = {str(one.number): one.slug for one in questions.load(kitchen.state)}
    listed = {
        asked[said.split()[2].rstrip(":")]
        for said in needs(kitchen)
        if said.startswith("demo question ")
    }
    assert {key for key, one in lines.items() if one["who"] == "user"} == listed == {"gated"}
    assert (lines["left"]["who"], lines["left"]["value"]) == ("home", "leftover")
    assert lines["left"]["waits"].startswith("its home" if homed else "a home")
    assert (lines["reviewed"]["who"], lines["reviewed"]["waits"]) == ("rev", "its review")


def scoped(kitchen, scope):
    """Start the scoped home `scope` of demo, with its plan, and return its directory."""
    home(kitchen, scope)
    (kitchen.home / scope / "plan.md").write_text(f"# {scope}: plan\n")
    return kitchen.home / scope


def unsaid(kitchen, slug, where="uncategorized", project="demo"):
    """Queue a row of the home `where` with no go, so it waits on the user's word."""
    text = brief(slug).replace("Home: uncategorized", f"Home: {where}")
    add(kitchen, slug, approve=False, text=text, project=project)


def rows(said):
    """The slugs of the rows awaiting a go that `jbus needs` printed, each with its project."""
    return [line.split(":")[0] for line in said if " approve " in line.split(":")[0]]


def test_a_root_home_lists_its_own_and_its_scopes_items_and_a_scope_only_its_own(kitchen):
    sc = scoped(kitchen, "sc")
    scoped(kitchen, "sd")
    other = kitchen.second()
    unsaid(kitchen, "rooted")
    unsaid(kitchen, "scoped", "sc")
    unsaid(kitchen, "sibling", "sd")
    unsaid(kitchen, "elsewhere", project=other.name)
    kitchen.poll()
    assert rows(needs(kitchen)) == [
        "demo approve rooted",
        "demo approve scoped",
        "demo approve sibling",
        "other approve elsewhere",
    ]
    root = needs(kitchen, "--project", "demo", home=kitchen.home)
    assert root[0] == "waiting on user: 3, in demo"
    assert rows(root) == ["demo approve rooted", "demo approve scoped", "demo approve sibling"]
    assert rows(needs(kitchen, "--project", "demo", home=sc)) == ["demo approve scoped"]


def test_a_root_home_with_no_scope_lists_its_own_items(kitchen):
    unsaid(kitchen, "rooted")
    kitchen.poll()
    said = needs(kitchen, "--project", "demo", home=kitchen.home)
    assert rows(said) == ["demo approve rooted"]


def test_a_scope_with_nothing_waiting_says_so_by_its_name(kitchen):
    sc = scoped(kitchen, "sc")
    unsaid(kitchen, "rooted")
    kitchen.poll()
    assert needs(kitchen, "--project", "demo", home=sc) == [
        "nothing waits on user in demo's sc home"
    ]


def test_a_directory_that_is_no_home_of_the_project_is_refused(kitchen, tmp_path):
    kitchen.poll()
    code, said = kitchen.main("--project", "demo", "needs", "--home", str(tmp_path))
    assert code != 0 and f"refused: {tmp_path} is no home of demo" in said


def test_a_gate_a_scope_asked_as_its_home_is_that_scopes(kitchen):
    """A gate in a scope's `gates.md` whose `Asked by:` is `home` is the scope's (`jbus.needs`),
    not the root's, though the root home lists it with its scopes'."""
    sc = scoped(kitchen, "sc")
    asked = GATE.format(n=1, asked="drop the old rows?", status="open", slug="home")
    (sc / "gates.md").write_text(asked.replace("Option:", "Holds: deletes data\nOption:", 1))
    kitchen.poll()
    gated = "demo gate 1: drop the old rows"
    assert needs(kitchen, "--project", "demo", home=sc)[1].startswith(gated)
    assert needs(kitchen, "--project", "demo", home=kitchen.home)[1].startswith(gated)
    alone = scoped(kitchen, "sd")
    assert needs(kitchen, "--project", "demo", home=alone) == [
        "nothing waits on user in demo's sd home"
    ]


def test_a_held_pull_request_is_the_home_of_its_row_and_the_roots_where_the_queue_is_unread(
    kitchen,
):
    sc = scoped(kitchen, "sc")
    add(kitchen, "held", text=brief("held").replace("Home: uncategorized", "Home: sc"))
    kitchen.brief("held", "Home: sc\n" + RESULT)
    kitchen.set("open.json", [kitchen.opened("held", 9)])
    kitchen.set("jmerge.txt", HOLDS + "\n")
    kitchen.poll()
    held = f"demo {HOLDS}, a pull request jmerge holds for your word"
    assert needs(kitchen, "--project", "demo", home=sc)[1] == held
    (kitchen.state / "queue.json").write_text("not a table\n")
    assert needs(kitchen, "--project", "demo", home=sc) == [
        "nothing waits on user in demo's sc home"
    ]
    assert needs(kitchen, "--project", "demo", home=kitchen.home)[1] == held


def test_a_question_whose_brief_only_the_queue_stored_is_its_scopes_in_needs_and_home_status(
    kitchen, monkeypatch
):
    """`jbus needs --home` and `jbus home status --home` say which home a question is by one
    rule, so a slug whose brief is in no home's files goes to the home its stored brief names
    in both."""
    sc = scoped(kitchen, "sc")
    unsaid(kitchen, "stored", "sc")
    assert not (kitchen.home / "tasks" / "stored.md").exists()
    assert kitchen.main("gate", "stored", stdin=held())[0] == 0
    kitchen.poll()
    question = "demo question 1: drop the old branch"
    assert any(line.startswith(question) for line in needs(kitchen, "--project", "demo", home=sc))
    monkeypatch.setattr(homestatus.paths, "repo_name", lambda: kitchen.home.name)

    def asked(directory):
        here = homestatus.Home.of(str(directory))
        found = homestatus.bus(here, installed=True)
        return [line.split(homestatus.SEP)[1] for line in homestatus.gates(here, found)[2:]]

    assert asked(sc) == ["stored"]
    assert asked(kitchen.home) == []


def test_the_sidebar_file_names_rows_from_before_that_say_root_under_uncategorized(kitchen):
    """T3 Code's sidebar draws `work.json`, and `jbus.states.keep_work` names each row's home
    there as jbus resolves it (`jbriefs.home.home_of`): a brief or a scout's request queued
    before `add` refused `Home: root` is the catch-all's, `uncategorized`, never the root's, and a
    scout's request with no copy under `scouts/` is read from jbus's own."""
    scoped(kitchen, "sc")
    add(kitchen, "old-row", approve=False)
    add(kitchen, "old-ask", approve=False, text=request("old-ask"))
    add(
        kitchen,
        "sc-ask",
        approve=False,
        text=request("sc-ask", "Home: sc\n", asked="find out what Y does"),
    )
    add(
        kitchen,
        "sc-row",
        approve=False,
        text=brief("sc-row").replace("Home: uncategorized", "Home: sc"),
    )
    for kind in ("tasks", "scouts"):
        (kitchen.home / kind).mkdir(exist_ok=True)
    rooted = (
        (kitchen.state / "briefs" / "old-row.md")
        .read_text()
        .replace("Home: uncategorized\n", "Home: root\n")
    )
    (kitchen.state / "briefs" / "old-row.md").write_text(rooted)
    (kitchen.home / "tasks" / "old-row.md").write_text(rooted)
    asked = request("old-ask").replace("Home: uncategorized\n", "Home: root\n")
    (kitchen.home / "scouts" / "old-ask.md").write_text(asked)
    kitchen.poll()
    lines = json.loads((kitchen.state / work.NAME).read_text())["work"]
    homes = {one["key"]: one["home"] for one in lines if one.get("kind") == "row"}
    assert homes == {
        "old-row": "uncategorized",
        "old-ask": "uncategorized",
        "sc-ask": "sc",
        "sc-row": "sc",
    }


def test_a_scopes_list_has_the_projects_own_items_and_the_asks_still_open_in_its_told(
    kitchen, request
):
    """`jbus needs --home` keeps one home's items, and with them each item about no row and no
    home, such as a T3 Code build to install, and each `decision local` or `stop local` line
    still in the home's `told`: an ask of the home's own, open until a `cleared` line ends it
    (`jbus.turnend`)."""
    answer = request.getfixturevalue(machine.__name__)
    sc = scoped(kitchen, "sc")
    old = patched(kitchen, "0001-tree.patch", "one\n")
    patched(kitchen, "0002-rows.patch", "two\n")
    answer(f"t3 v0.1.7+jstack.{old}")
    turn = (
        "decision local alpha: run the install at a quiet time and tell me\n"
        "stop local beta: lift the hold on beta\n"
        "decision question 3: drop the old branch\n"
        "stop local gamma: say which way\n"
    )
    assert kitchen.main("told", str(sc), stdin=turn)[0] == 0
    assert kitchen.main("told", str(sc), stdin="cleared local gamma: answered\n")[0] == 0
    kitchen.poll()
    said = needs(kitchen, "--project", "demo", home=sc)
    assert said[0] == "waiting on user: 3, in demo"
    assert said[1].startswith("demo install t3code-jstack: T3 Code runs the jstack build")
    assert said[3:] == [
        "demo sc home decision local alpha: run the install at a quiet time and tell me",
        "  answer: reply to the sc home in your own words",
        "demo sc home stop local beta: lift the hold on beta",
        "  answer: reply to the sc home in your own words",
    ]
    assert needs(kitchen, "--project", "demo", home=kitchen.home)[3:] == said[3:]


def test_the_project_wide_list_has_every_homes_open_asks_and_home_status_counts_them(kitchen):
    """`jbus needs` with no `--home` is what a thread outside a home and the root home read, so
    it lists each ask still open in the `told` of every home of the project, each named with its
    home, and `jbus home status` counts them in its line of what waits in other projects: a
    scope's ask never hides behind "nothing waits". A project whose root home has no directory
    has no asks, and the list still reads every project."""
    sc, ops = scoped(kitchen, "sc"), scoped(kitchen, "ops")
    other = kitchen.second()
    turn = "decision local alpha: which way?\ndecision question 3: drop the old branch\n"
    assert kitchen.main("told", str(sc), stdin=turn)[0] == 0
    assert kitchen.main("told", str(ops), stdin="stop local beta: lift the hold on beta\n")[0] == 0
    kitchen.poll()
    config = jbus.load()
    there = next(one for one in config.projects if one.name == other.name)

    def elsewhere():
        bus = homestatus.Bus(there, config, "", ())
        return [line for line in homestatus._needs(bus) if line.startswith("elsewhere:")]

    assert needs(kitchen) == [
        "waiting on user: 2, in demo",
        "demo ops home stop local beta: lift the hold on beta",
        "  answer: reply to the ops home in your own words",
        "demo sc home decision local alpha: which way?",
        "  answer: reply to the sc home in your own words",
    ]
    assert needs(kitchen, "--project", "demo")[1:] == needs(kitchen)[1:]
    assert elsewhere() == ["elsewhere: demo 2: jbus needs"]
    assert kitchen.main("told", str(sc), stdin="cleared local alpha: answered\n")[0] == 0
    assert kitchen.main("told", str(ops), stdin="cleared local beta: lifted\n")[0] == 0
    assert needs(kitchen) == ["nothing waits on user in any project"]
    assert elsewhere() == []
    other.home.rename(other.home.with_name("moved"))
    assert needs(kitchen) == ["nothing waits on user in any project"]


def test_a_closed_homes_open_asks_stay_listed_until_cleared(kitchen):
    """A scope whose plan is archived is a closed home, with no thread to ask. Each ask it left
    open in its `told` still waits on the user, so the project-wide list and the root home's list
    keep it, named with the closed home, until a `cleared local` line in its `told` ends it."""
    sc = scoped(kitchen, "sc")
    turn = "decision local alpha: which way?\nstop local gamma: say which way\n"
    assert kitchen.main("told", str(sc), stdin=turn)[0] == 0
    assert kitchen.main("told", str(sc), stdin="cleared local gamma: answered\n")[0] == 0
    (sc / "plan.md").rename(sc / "plan-archived.md")
    kitchen.poll()
    listed = [
        "waiting on user: 1, in demo",
        "demo sc home (closed) decision local alpha: which way?",
        "  answer: reply to the root home in your own words: the sc home is closed",
    ]
    assert needs(kitchen) == listed
    assert needs(kitchen, "--project", "demo", home=kitchen.home) == listed
    assert kitchen.main("told", str(sc), stdin="cleared local alpha: moot\n")[0] == 0
    assert needs(kitchen) == ["nothing waits on user in any project"]


FINDS = """#!/bin/sh
while [ $# -gt 0 ]; do [ "$1" = --report-path ] && report=$2; shift; done
printf '[{"File": "demo/notes.md"}]' > "$report"
exit 1
"""
"""A gitleaks that finds a secret in `demo/notes.md`, as the real one finds a planted key."""


def test_a_failed_snapshot_is_one_item_on_jbus_needs_until_a_run_succeeds(
    kitchen, tree, tmp_path, monkeypatch
):
    """A run of the unit that fails, on a secret gitleaks found or stopped at its timeout, puts
    one item on the user's list, with when the backup first failed and the run's last line. A
    second failed run gives that item its own last line and adds none, and the next run that
    succeeds ends it."""
    kitchen.config(infra="demo")
    with_origin(tree, tmp_path)
    kitchen.poll()
    assert needs(kitchen) == ["nothing waits on user in any project"]
    finds = kitchen.root / "finds-gitleaks"
    finds.mkdir()
    (finds / "gitleaks").write_text(FINDS)
    (finds / "gitleaks").chmod(0o755)
    path = os.environ["PATH"]
    monkeypatch.setenv("PATH", f"{finds}{os.pathsep}{path}")
    (tree / "demo" / "notes.md").write_text("# notes\nAKIA...\n")
    assert take(NOW - timedelta(hours=1))[0] == 1
    answer = (
        "  answer: nothing to reply: fix what its last line names (journalctl --user -u "
        "jbus-snapshot.service has the rest), and the next snapshot that succeeds clears this"
    )
    head = "demo jbus-snapshot.service, the state backup, has failed since 2026-10-12 10:00 ET"
    refused = "gitleaks found a secret in the changes (demo/notes.md), nothing committed"
    assert needs(kitchen) == [
        "waiting on user: 1, in demo",
        f"{head}; its last line: snapshot: {refused}",
        answer,
    ]
    monkeypatch.setenv("PATH", path)
    killed(kitchen, tree)
    kitchen.poll()
    assert needs(kitchen) == [
        "waiting on user: 1, in demo",
        f"{head}; its last line: snapshot: {snapshot.KILLED}",
        answer,
    ]
    assert take()[0] == 0
    assert needs(kitchen) == ["nothing waits on user in any project"]
