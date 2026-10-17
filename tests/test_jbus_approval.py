"""An approval names the words of the user's it rests on, and jbus writes who ran it and when.

`queue approve` takes a word `jbus word` kept, the answer that closed a question, or a
message jbus reads from T3 Code itself, and no name and no time. Every test runs the real
command and the real pass against the faked T3 Code server of `test_jbus_kitchen`.
"""

import json
from dataclasses import replace

import pytest

import jbus
import jsettings
from jbus import questions, queue, word
from jbus.view import state as view_state
from test_jbus_kitchen import ASK, GO, NOW, RAN, SAID, SAID_AT, SESSION, bound
from test_jbus_queue import NO_BASIS, add, brief, rows, sha12

HOME, MESSAGE = "mcp:a-home", "a-message-of-his"
REF = f"{HOME}/{MESSAGE}"
HEARD_AT = "2026-10-12 10:30 ET"
HEARD = f"his word, {HEARD_AT}, in home: demo; run {RAN} by the demo home"


def go(kitchen, slug, *basis):
    sha = sha12((kitchen.state / "briefs" / f"{slug}.md").read_text())
    return kitchen.main("queue", "approve", slug, *basis, "--sha", sha)


def cell(kitchen, slug):
    """The `approved` cell `queue show` prints for the row."""
    lines = kitchen.main("queue", "show", "--all")[1].splitlines()
    (found,) = [line for line in lines if line.startswith(f"| {slug} |")]
    return found.split(" | ")[4]


def viewed(kitchen):
    """The view's state, read with the config's zone, as `jbus view` reads it."""
    sources = view_state.Sources(kitchen.state_dir, kitchen.root / "home", user=jsettings.load())
    return view_state.build(sources, "demo", NOW, lambda _: {})


def test_an_approval_by_a_word_is_a_record_of_the_word_and_of_who_ran_it(kitchen):
    add(kitchen, "alpha", approve=False)
    code, said = go(kitchen, "alpha", "--word", kitchen.word())
    assert (code, said.splitlines()[-1].split(" | ")[4]) == (0, GO)
    row = rows(kitchen)["alpha"]
    assert row["approval"] == {
        "basis": "word",
        "ref": SAID,
        "words": "go",
        "said_at": SAID_AT,
        "said_in": "",
        "checked": False,
        "ran_by": {"session": SESSION, "directory": str(kitchen.checkout)},
        "ran_at": RAN,
        **bound(kitchen, "alpha"),
    }
    assert (row["approved"], cell(kitchen, "alpha")) == (GO, GO)
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_a_word_the_project_does_not_keep_approves_nothing(kitchen):
    add(kitchen, "alpha", approve=False)
    kept = kitchen.state / "words.json"
    assert go(kitchen, "alpha", "--word", "nope") == (1, f"refused: {kept} has no word nope\n")
    assert rows(kitchen)["alpha"]["approved"] == ""


@pytest.mark.parametrize(
    "basis",
    [(), ("--by", "user", "--at", SAID_AT), ("--word", SAID, "--by", "user"), ("--at", SAID_AT)],
)
def test_an_approval_with_no_basis_or_with_a_name_or_a_time_is_refused(kitchen, basis):
    add(kitchen, "alpha", approve=False)
    kitchen.word()
    assert go(kitchen, "alpha", *basis) == (1, f"refused: {NO_BASIS}\n")
    assert "approval" not in rows(kitchen)["alpha"]


def test_an_approval_by_a_message_holds_what_jbus_read_from_t3_code(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "yes,\n  launch alpha")
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--message", REF)[0] == 0
    row = rows(kitchen)["alpha"]
    assert row["approval"] == {
        "basis": "message",
        "ref": REF,
        "words": "yes, launch alpha",
        "said_at": HEARD_AT,
        "said_in": "home: demo",
        "checked": True,
        "ran_by": {"session": SESSION, "directory": str(kitchen.checkout)},
        "ran_at": RAN,
        **bound(kitchen, "alpha"),
    }
    assert (row["approved"], cell(kitchen, "alpha")) == (HEARD, HEARD)
    (read,) = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_read"]
    assert read == {
        "threadId": HOME,
        "itemId": f"turn-item:message:{MESSAGE}",
        "maxCharsPerItem": 50000,
    }


@pytest.mark.parametrize(
    "more, wrote",
    [
        ({"createdBy": "agent", "creationSource": "mcp"}, "user_message by agent, from mcp"),
        (
            {"type": "assistant_message", "createdBy": "agent", "creationSource": "provider"},
            "assistant_message by agent, from provider",
        ),
    ],
)
def test_a_message_that_is_not_the_users_own_approves_nothing(kitchen, more, wrote):
    kitchen.t3.says(HOME, MESSAGE, "yes, launch alpha", **more)
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--message", REF) == (
        1,
        f"refused: message {REF} is not user's own: T3 Code has it as a {wrote}\n",
    )
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_a_message_t3_code_does_not_have_and_a_reference_that_is_not_one_are_refused(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "yes")
    add(kitchen, "alpha", approve=False)
    code, said = go(kitchen, "alpha", "--message", f"{HOME}/another")
    assert code == 1
    assert said.startswith(f"refused: T3 Code gave no message {HOME}/another (")
    code, said = go(kitchen, "alpha", "--message", "mcp:no-thread/another")
    assert (code, said.startswith("refused: T3 Code gave no message mcp:no-thread/another (")) == (
        1,
        True,
    )
    assert go(kitchen, "alpha", "--message", MESSAGE) == (
        1,
        f'refused: --message is "<thread id>/<message id>", not {MESSAGE}\n',
    )
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_a_long_message_is_read_whole_and_an_id_is_sent_as_t3_code_names_its_item(kitchen):
    long = "word " * 12000
    kitchen.t3.says(HOME, "message:mcp:a/b", long)
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--message", f"{HOME}/message:mcp:a/b")[0] == 0
    assert rows(kitchen)["alpha"]["approval"]["words"] == long.strip()
    reads = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_read"]
    assert [given.get("textOffset") for given in reads] == [None, 50000]
    assert reads[0]["itemId"] == "turn-item:message:message%3Amcp%3Aa%2Fb"


def test_an_approval_by_an_answer_rests_on_the_answer_that_closed_the_question(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.main("gate", "alpha", stdin=ASK)
    assert go(kitchen, "alpha", "--answer", "1") == (
        1,
        "refused: question 1 is open, and an open question approves nothing\n",
    )
    kept = kitchen.state / "questions.json"
    assert go(kitchen, "alpha", "--answer", "2") == (1, f"refused: {kept} has no question 2\n")
    said = ("--by", "user", "--at", SAID_AT, "--default", "the", "first")
    assert kitchen.main("answer", "1", *said)[0] == 0
    assert go(kitchen, "alpha", "--answer", "1")[0] == 0
    kept = rows(kitchen)["alpha"]["approval"]
    assert (kept["basis"], kept["ref"], kept["words"], kept["said_at"], kept["checked"]) == (
        "answer",
        "1",
        "the first",
        SAID_AT,
        False,
    )
    assert cell(kitchen, "alpha") == GO


def test_a_question_its_home_closed_in_a_file_approves_nothing(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.main("gate", "alpha", stdin=ASK)
    (one,) = questions.read(kitchen.state)
    given = questions.Answer("answered: yes", "", "", "gates.md", False, closed_by=questions.HOME)
    questions._write(kitchen.state, 2, [replace(one, answer=given)])
    assert go(kitchen, "alpha", "--answer", "1") == (
        1,
        'refused: question 1 was closed by its home in gates.md, "answered: yes": '
        "jbus has no word of it\n",
    )


def test_a_row_that_holds_only_the_old_string_loads_launches_and_says_it_was_typed(kitchen):
    add(kitchen, "alpha")
    table = json.loads((kitchen.state / "queue.json").read_text())
    del table[0]["approval"]
    table[0]["approved"] = "2026-10-13 13:50 ET by user"
    jbus.write_json(kitchen.state / "queue.json", table)
    assert cell(kitchen, "alpha") == "2026-10-13 13:50 ET by user (typed, not checked)"
    (task,) = viewed(kitchen)["tasks"]
    assert (task["approved"], task["approved_at"]) == (
        "2026-10-13 13:50 ET by user (typed, not checked)",
        None,
    )
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_the_views_row_says_the_line_queue_show_prints_and_takes_the_time_from_the_record(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "yes, launch alpha")
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--message", REF)[0] == 0
    (task,) = viewed(kitchen)["tasks"]
    assert (task["approved"], task["approved_at"]) == (HEARD, "2026-10-12T15:00:00+00:00")
    assert task["approved"] == cell(kitchen, "alpha")


def test_a_hold_takes_the_record_back_with_the_go(kitchen):
    add(kitchen, "alpha")
    assert kitchen.main("queue", "hold", "alpha")[0] == 0
    row = rows(kitchen)["alpha"]
    assert (row["approved"], row["brief_sha"], "approval" in row) == ("", "", False)
    assert cell(kitchen, "alpha") == ""


def test_the_line_names_a_home_or_a_shell_by_where_and_whether_a_session_ran_it(kitchen):
    add(kitchen, "alpha", approve=False)
    desk = kitchen.root / "elsewhere"
    desk.mkdir()
    kitchen.monkeypatch.chdir(desk)
    argv = ("--project", "demo", "queue", "approve", "alpha", "--word", kitchen.word())
    assert kitchen.main(*argv, "--sha", sha12(brief("alpha")))[0] == 0
    typed = f"his word, {SAID_AT} (time typed); run {RAN} by"
    assert rows(kitchen)["alpha"]["approved"] == f"{typed} the elsewhere home"
    kitchen.monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    assert kitchen.main(*argv, "--sha", sha12(brief("alpha")))[0] == 0
    row = rows(kitchen)["alpha"]
    assert row["approval"]["ran_by"] == {"session": "", "directory": str(desk)}
    assert row["approved"] == f"{typed} a shell in {desk}"


def test_a_batch_takes_the_three_bases_and_asks_t3_code_for_a_message_once(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "yes, both")
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    text = (
        f"approve alpha --message {REF} --sha {sha12(brief('alpha'))}\n"
        f"approve beta --message={REF} --sha {sha12(brief('beta'))}\n"
    )
    code, said = kitchen.main("queue", "apply", stdin=text)
    assert (code, said.splitlines()) == (
        0,
        [
            f"approved alpha: brief {sha12(brief('alpha'))}, {HEARD}",
            f"approved beta: brief {sha12(brief('beta'))}, {HEARD}",
        ],
    )
    assert [tool for tool, _ in kitchen.t3.calls].count("t3_thread_read") == 1
    assert queue.parse(
        f"approve alpha --word {SAID} --sha 0\napprove beta --answer 4 --sha 0\n"
    ) == [
        (1, queue.Approve("alpha", "word", SAID, "0")),
        (2, queue.Approve("beta", "answer", "4", "0")),
    ]
    with pytest.raises(jbus.Refused, match="line 1: approve takes one basis"):
        queue.parse(f'approve alpha --by user --at "{SAID_AT}" --sha 0\n')


def test_a_row_with_no_approval_is_listed_with_the_command_and_its_three_bases(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    (one,) = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    assert one["line"] == (
        f"approve alpha: jbus --project demo queue approve alpha --sha {sha12(brief('alpha'))} "
        "with --word <id>, --answer <number>, --message <thread id>/<message id> or --page "
        "<session key>/<entry id>"
    )


def test_a_word_given_as_a_message_is_kept_with_the_messages_own_words_and_time(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.t3.says("mcp:sous", MESSAGE, "launch\nalpha and beta", title="Sous Chef")
    code, said = kitchen.main("word", "--to", "demo", "--message", f"mcp:sous/{MESSAGE}")
    (kept,) = word.load(kitchen.state)
    assert (code, said) == (0, f"sent: demo, to home-1, word {kept.id}\n")
    assert (kept.words, kept.by, kept.at, kept.ref, kept.said_in, kept.checked) == (
        "launch alpha and beta",
        "user",
        HEARD_AT,
        f"mcp:sous/{MESSAGE}",
        "Sous Chef",
        True,
    )
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--word", kept.id)[0] == 0
    row = rows(kitchen)["alpha"]
    assert row["approved"] == f"his word, {HEARD_AT}, in Sous Chef; run {RAN} by the demo home"
    assert (row["approval"]["basis"], row["approval"]["checked"]) == ("word", True)


def test_a_typed_word_is_still_taken_and_is_not_checked(kitchen):
    typed = ("--by", "user", "--at", SAID_AT, "launch", "alpha")
    assert kitchen.main("word", "--to", "demo", *typed)[0] == 0
    (kept,) = word.load(kitchen.state)
    assert (kept.words, kept.at, kept.ref, kept.said_in, kept.checked) == (
        "launch alpha",
        SAID_AT,
        "",
        "",
        False,
    )


@pytest.mark.parametrize(
    "given",
    [
        ("--message", REF, "--by", "user", "--at", SAID_AT, "launch"),
        ("--message", REF, "launch"),
        ("--by", "user", "launch"),
        ("--by", "user", "--at", SAID_AT),
        (),
    ],
)
def test_a_word_and_an_answer_take_a_message_or_typed_words_and_not_both(kitchen, given):
    kitchen.t3.says(HOME, MESSAGE, "yes")
    kitchen.main("gate", "alpha", stdin=ASK)
    for verb, argv in (
        ("word", ("word", "--to", "demo")),
        ("answer", ("answer", "1", "--default")),
    ):
        assert kitchen.main(*argv, *given) == (
            1,
            f"refused: {verb} takes --message <thread id>/<message id>, or --by and --at with "
            "the words, and not both\n",
        )
    assert not (kitchen.state / "words.json").exists()
    assert questions.read(kitchen.state)[0].answer is None


def test_an_answer_given_as_a_message_is_closed_with_the_messages_own_words_and_time(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "the  first")
    kitchen.main("gate", "alpha", stdin=ASK)
    code, said = kitchen.main("answer", "1", "--default", "--message", REF)
    assert (code, said) == (
        0,
        f'answered: question 1: "the first", by user, {HEARD_AT}, in {kitchen.checkout} '
        "(the default stands): nothing is sent\n",
    )
    given = questions.read(kitchen.state)[0].answer
    assert (given.words, given.at, given.ref, given.said_in, given.checked) == (
        "the first",
        HEARD_AT,
        REF,
        "home: demo",
        True,
    )
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--answer", "1")[0] == 0
    assert rows(kitchen)["alpha"]["approved"] == HEARD
    kitchen.t3.says(HOME, "an-agents", "the first", createdBy="agent", creationSource="mcp")
    kitchen.main("gate", "alpha", stdin=ASK.replace("which one?", "and which?"))
    code, said = kitchen.main("answer", "2", "--default", "--message", f"{HOME}/an-agents")
    assert (code, said.startswith(f"refused: message {HOME}/an-agents is not user's own")) == (
        1,
        True,
    )


def test_the_views_merged_list_takes_the_approval_time_from_the_record_and_none_from_a_string(
    kitchen,
):
    kitchen.t3.says(HOME, MESSAGE, "yes, launch both")
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta")
    assert go(kitchen, "alpha", "--message", REF)[0] == 0
    table = json.loads((kitchen.state / "queue.json").read_text())
    for row in table:
        row["status"] = "merged"
        if row["slug"] == "beta":
            del row["approval"]
            row["approved"] = "2026-10-12 09:00 ET by user"
    jbus.write_json(kitchen.state / "queue.json", table)
    at = "2026-10-12T14:00:00+00:00"
    moves = [{"slug": slug, "from": "pr", "to": "merged", "at": at} for slug in ("alpha", "beta")]
    (kitchen.state / "transitions.jsonl").write_text("".join(json.dumps(m) + "\n" for m in moves))
    merged = {one["slug"]: one["approved"] for one in viewed(kitchen)["merged"]}
    assert merged == {"alpha": "2026-10-12T15:00:00+00:00", "beta": None}
