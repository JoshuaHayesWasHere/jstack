"""`jbus word` sends the user's word to a home. jbus keeps the word as an act, sends it once to the
thread in the home's `home-id`, and puts it in no wake. The word is the user's own message, read
from T3 Code: a word typed with `--by` and `--at` is not taken.

Every test runs the real command and the real pass against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import acts, party, passes, t3, wake, word
from test_jbus_kitchen import NOW, iso, sends

AT = "2026-10-12 10:55 ET"
WORDS = "hold every merge until I say"
ID = "9e0a0bcb94dd"


def thread(digit):
    """Return a made-up T3 Code thread id, `mcp:<uuid>` with every digit `digit`."""
    return "mcp:" + "-".join(digit * size for size in (8, 4, 4, 4, 12))


HOME, WAS, CREW, NOBODY = thread("a"), thread("b"), thread("c"), thread("0")
CHAT, REF = thread("e"), f"{thread('e')}/m-word"
SAID = ("--message", REF)


@pytest.fixture(autouse=True)
def said(kitchen):
    """The user said WORDS at AT, in a thread of theirs that is no home's."""
    kitchen.t3.says(CHAT, "m-word", WORDS, updatedAt=iso(NOW - timedelta(minutes=5)), title="chat")


OTHER = "caeb11cd4f1b"
MESSAGE = (
    "jbus: this is user's own word, said 2026-10-12 10:55 ET and carried to this home by "
    "jbus. Take it as said by user in this thread. It answers no open question, and nothing "
    "is sent back for it. It is word 9e0a0bcb94dd: a row it approves is approved with --word "
    "9e0a0bcb94dd.\n\nhold every merge until I say"
)


def logged(kitchen, project="demo"):
    code, out = kitchen.main("--project", project, "events")
    assert code == 0
    return [json.loads(line) for line in out.splitlines()]


def decide(kitchen):
    """Queue one decision, the kind of event that starts a POST for the user."""
    config = jbus.load()
    wake.Box(kitchen.state, config.project("demo")).send(
        "alpha", "decision", "decision alpha: which one?"
    )


def test_a_word_goes_once_to_the_thread_in_the_homes_home_id(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    assert kitchen.main("word", "--to", "demo", *SAID) == (0, f"sent: demo, to home-1, word {ID}\n")
    (sent,) = sends(kitchen)
    assert sent == {
        "threadId": "home-1",
        "message": MESSAGE,
        "mode": "queue",
        "clientRequestId": f"word|demo|{ID}|home-1",
    }
    assert kitchen.main("word", "--to", "demo", *SAID) == (
        0,
        f"already sent: demo, to home-1, word {ID}\n",
    )
    kitchen.poll()
    assert len(sends(kitchen)) == 1


def test_jbus_events_prints_the_word_with_its_words_by_at_and_where_it_went(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.main("word", "--to", "demo", *SAID)
    (one,) = logged(kitchen)
    assert (one["event"], one["line"], one["posted"]) == ("word", "word demo: sent to home-1", None)
    assert one["word"] == {"words": WORDS, "by": "user", "at": AT, "to": "home-1"}


def test_no_wake_carries_the_word_and_the_wake_another_event_starts_has_none_of_it(kitchen):
    """The test sends the word from a checkout that is no project's."""
    (kitchen.home / "home-id").write_text("home-1\n")
    desk = kitchen.root / "elsewhere"
    kitchen.git("init", "-q", str(desk), cwd=kitchen.root)
    kitchen.monkeypatch.chdir(desk)
    assert kitchen.main("word", "--to", "demo", *SAID) == (0, f"sent: demo, to home-1, word {ID}\n")
    assert kitchen.waiting() == []
    decide(kitchen)
    assert "woke demo: 1 events" in kitchen.poll()
    assert [[one["event"] for one in post] for post in kitchen.wakes.posts] == [["decision"]]
    carried = json.dumps([kitchen.wakes.posts, kitchen.wakes.said, kitchen.waiting()])
    assert "merge" not in carried and "word" not in carried


def test_all_sends_it_once_to_each_projects_home(kitchen):
    side = kitchen.second()
    (kitchen.home / "home-id").write_text("home-1\n")
    (side.home / "home-id").write_text("home-2\n")
    said = f"sent: demo, to home-1, word {ID}\nsent: other, to home-2, word {OTHER}\n"
    assert kitchen.main("word", "--all", *SAID) == (0, said)
    assert [(one["threadId"], one["message"]) for one in sends(kitchen)] == [
        ("home-1", MESSAGE),
        ("home-2", MESSAGE.replace(ID, OTHER)),
    ]
    again = (
        f"already sent: demo, to home-1, word {ID}\nalready sent: other, to home-2, word {OTHER}\n"
    )
    assert kitchen.main("word", "--all", *SAID) == (0, again)
    assert kitchen.main("word", "--to", "other", *SAID) == (
        0,
        f"already sent: other, to home-2, word {OTHER}\n",
    )
    assert len(sends(kitchen)) == 2
    assert [one["line"] for one in logged(kitchen, "other")] == ["word other: sent to home-2"]


def kept_not_posted(kitchen, why, project="demo", thread="home-1", name=ID):
    """Return what the command says of a word it kept and posted to nobody. Its act alone says
    it went to its home's thread: `word-sends.json` need not hold it."""
    (one,) = [each for each in word.load(kitchen.state) if each.id == name]
    assert one.thread == thread and one.sent_at and one.waits == ""
    return f"kept: {project}, not posted, {why}, word {name}\n"


def test_a_word_said_in_the_homes_own_thread_is_kept_and_posted_to_nobody(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.t3.says("home-1", "m1", WORDS, title="home: demo")
    ref = "home-1/m1"
    (code, out) = kitchen.main("word", "--to", "demo", "--message", ref)
    (kept,) = word.load(kitchen.state)
    why = "it was said in this project's own home thread home-1"
    assert (code, out) == (0, kept_not_posted(kitchen, why, name=kept.id))
    assert (kept.words, kept.ref, kept.checked) == (WORDS, ref, True)
    assert kitchen.main("word", "--to", "demo", "--message", ref) == (code, out)
    kitchen.poll(NOW + timedelta(minutes=5))
    assert sends(kitchen) == []
    (event,) = logged(kitchen)
    assert (event["event"], event["line"], event["posted"]) == (
        "word",
        f"word demo: kept, {why}",
        None,
    )
    assert event["word"] == {"words": WORDS, "by": "user", "at": event["word"]["at"], "to": ""}
    assert word.basis(kitchen.state, kept.id).words == WORDS
    assert not word.path(kitchen.state).exists()


def test_a_word_recorded_by_the_home_is_kept_and_posted_to_nobody(kitchen):
    (kitchen.home / "home-id").write_text(f"{HOME}\n")
    assert kitchen.main("word", "--to", "demo", "--from", HOME, *SAID) == (
        0,
        kept_not_posted(
            kitchen, f"it was recorded by this project's home thread {HOME}", thread=HOME
        ),
    )
    again = kitchen.main("word", "--to", "demo", "--from", HOME, *SAID)
    assert again == (
        0,
        kept_not_posted(
            kitchen, f"it was recorded by this project's home thread {HOME}", thread=HOME
        ),
    )
    assert not word.path(kitchen.state).exists()
    kitchen.poll(NOW + timedelta(minutes=5))
    assert sends(kitchen) == [] and kitchen.wakes.posts == []


def test_a_word_recorded_anywhere_else_is_posted_to_the_home_once(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.t3.says("mcp:sous", "m1", WORDS, title="Sous Chef")
    code, out = kitchen.main("word", "--to", "demo", "--message", "mcp:sous/m1")
    assert (code, out.startswith("sent: demo, to home-1, word ")) == (0, True)
    assert kitchen.main("word", "--to", "demo", "--message", "mcp:sous/m1")[1].startswith(
        "already sent:"
    )
    (sent,) = sends(kitchen)
    assert sent["threadId"] == "home-1"


def test_a_word_recorded_by_a_thread_that_is_not_the_home_is_posted_to_the_home(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.t3.thread("crew", threadId=CREW)
    assert kitchen.main("word", "--to", "demo", "--from", CREW, *SAID) == (
        0,
        f"sent: demo, to home-1, word {ID}\n",
    )
    assert len(sends(kitchen)) == 1


def test_a_word_from_a_home_that_handed_off_waits_for_the_next_home(kitchen):
    (kitchen.home / "home-id").write_text(f"{WAS}\n")
    (kitchen.home / "handoff.md").write_text(f"# Handoff\nWas home: {WAS}\n")
    kitchen.t3.thread("home", threadId=WAS)
    code, out = kitchen.main("word", "--to", "demo", "--from", WAS, *SAID)
    assert (code, out.startswith("waits: demo,")) == (0, True)
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.poll(NOW + timedelta(minutes=5))
    assert [one["threadId"] for one in sends(kitchen)] == ["home-1"]


def test_all_skips_only_the_recording_homes_own_copy(kitchen):
    side = kitchen.second()
    (kitchen.home / "home-id").write_text(f"{HOME}\n")
    (side.home / "home-id").write_text("home-2\n")
    code, out = kitchen.main("word", "--all", "--from", HOME, *SAID)
    assert code == 0
    why = f"it was recorded by this project's home thread {HOME}"
    assert out.splitlines() == [
        kept_not_posted(kitchen, why, thread=HOME).strip(),
        f"sent: other, to home-2, word {OTHER}",
    ]
    assert [(one["threadId"], one["message"]) for one in sends(kitchen)] == [
        ("home-2", MESSAGE.replace(ID, OTHER))
    ]
    kitchen.poll(NOW + timedelta(minutes=5))
    assert len(sends(kitchen)) == 1


@pytest.mark.parametrize("given", ["home-jstack", "home-1", "mcp:home", HOME[len("mcp:") :], ""])
def test_a_from_that_is_not_a_thread_id_is_refused_and_nothing_is_kept_or_sent(kitchen, given):
    """2026-10-23: the jstack home recorded the user's word with `--from home-jstack`, and jbus
    posted the word into that home, which had already acted on it."""
    (kitchen.home / "home-id").write_text(f"{HOME}\n")
    assert kitchen.main("word", "--to", "demo", "--from", given, *SAID) == (
        1,
        f'refused: --from is a T3 Code thread id, mcp:<uuid>, not "{given}"\n',
    )
    assert word.load(kitchen.state) == []
    assert [tool for tool, _ in kitchen.t3.calls if tool == "t3_thread_send"] == []


def test_a_from_that_names_a_thread_t3_code_does_not_have_is_refused(kitchen):
    (kitchen.home / "home-id").write_text(f"{HOME}\n")
    assert kitchen.main("word", "--to", "demo", "--from", NOBODY, *SAID) == (
        1,
        f"refused: --from {NOBODY} is no thread of T3 Code, and not this home's\n",
    )
    assert word.load(kitchen.state) == []
    assert [tool for tool, _ in kitchen.t3.calls if tool == "t3_thread_send"] == []


def test_a_from_t3_code_gives_no_answer_about_goes_on_the_shape_alone_and_says_so(kitchen):
    """T3 Code gives the user's message, and no answer on the thread of `--from`."""
    (kitchen.home / "home-id").write_text(f"{HOME}\n")
    read = t3.Client.call

    def lossy(client, tool, given):
        if tool == "t3_thread_read" and not given.get("itemId"):
            raise t3.T3Error("no answer")
        return read(client, tool, given)

    kitchen.monkeypatch.setattr(t3.Client, "call", lossy)
    assert kitchen.main("word", "--to", "demo", "--from", NOBODY, *SAID) == (
        0,
        f"unchecked: --from {NOBODY} has the shape of a thread id, and T3 Code gave no answer "
        f"on whether it has that thread\nsent: demo, to {HOME}, word {ID}\n",
    )


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"home-id": "\n"},
        {"home-id": "home-0\n", "handoff.md": "# Handoff\nWas home: home-0\n"},
        {"home-id": "home-0\n", "handoff.md": "# Handoff\nWas home:home-0\n"},
    ],
    ids=["no-file", "empty", "handed-off", "handed-off-no-space"],
)
def test_a_word_for_a_home_with_no_home_id_waits_and_goes_on_the_pass_after_its_start(
    kitchen, files
):
    for name, text in files.items():
        (kitchen.home / name).write_text(text)
    why = "its home has no home-id, so it goes on the pass after that home's next start"
    assert kitchen.main("word", "--to", "demo", *SAID) == (0, f"waits: demo, {why}, word {ID}\n")
    assert kitchen.main("word", "--to", "demo", *SAID) == (0, f"waits: demo, {why}, word {ID}\n")
    kitchen.poll()
    assert sends(kitchen) == []
    (kept,) = word.load(kitchen.state)
    assert (kept.words, kept.by, kept.at, kept.sent_at) == (WORDS, "home/cli", AT, "")
    assert [one["line"] for one in logged(kitchen)] == [f"word demo: waits, {why}"]
    (kitchen.home / "home-id").write_text("home-1\n")
    assert "word demo: sent to home-1" in kitchen.poll(NOW + timedelta(minutes=5))
    kitchen.poll(NOW + timedelta(minutes=10))
    assert [(one["threadId"], one["message"]) for one in sends(kitchen)] == [("home-1", MESSAGE)]
    assert [one["word"]["to"] for one in logged(kitchen)] == ["", "home-1"]
    assert kitchen.waiting() == [] and kitchen.wakes.posts == []


def test_the_home_id_is_read_when_the_word_is_sent_not_when_it_was_kept(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.t3.lose_send = True
    assert kitchen.main("word", "--to", "demo", *SAID) == (
        0,
        f"waits: demo, T3 Code gave no answer, word {ID}\n",
    )
    kitchen.t3.lose_send = False
    (kitchen.home / "home-id").write_text("home-2\n")
    assert "word demo: sent to home-2" in kitchen.poll()
    assert list(kitchen.t3.messages.values())[0]["threadId"] == "home-2"
    assert kitchen.main("word", "--to", "demo", *SAID) == (
        0,
        f"already sent: demo, to home-2, word {ID}\n",
    )


def test_a_word_t3_code_refuses_waits_and_no_wake_carries_anything_of_it(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.t3.refuse_send = True
    assert kitchen.main("word", "--to", "demo", *SAID) == (
        0,
        f"waits: demo, T3 Code refused it, word {ID}\n",
    )
    decide(kitchen)
    assert "woke demo: 1 events" not in kitchen.poll()
    assert [one["line"] for one in logged(kitchen) if one["event"] == "word"] == [
        "word demo: waits, T3 Code refused it"
    ]
    kitchen.t3.refuse_send = False
    said = kitchen.poll(NOW + timedelta(minutes=5))
    assert "word demo: sent to home-1" in said and "woke demo: 1 events" in said
    assert [[one["event"] for one in post] for post in kitchen.wakes.posts] == [["decision"]]
    assert len(kitchen.t3.messages) == 1


def test_a_word_a_pass_sent_meanwhile_is_not_written_back_as_waiting(kitchen):
    """The command read the word unsent, and a pass sent it before the command's own send failed."""
    (kitchen.home / "home-id").write_text("home-1\n")
    config = jbus.load()
    run = passes.Pass(config, config.project("demo"), NOW, lambda _: None)
    heard = party.Evidence("t3-message", REF, WORDS, AT, "chat", True)
    held = word.keep(run, party.HOME, heard)
    assert "word demo: sent to home-1" in kitchen.poll()
    assert word._change(run, held, waits=word.NO_ANSWER) is False
    assert word._change(run, held, thread="home-2", sent_at="later", waits="") is False
    (kept,) = word.load(kitchen.state)
    assert (kept.thread, kept.waits, bool(kept.sent_at)) == ("home-1", "", True)
    assert [one["line"] for one in logged(kitchen)] == ["word demo: sent to home-1"]
    assert kitchen.main("word", "--to", "demo", *SAID) == (
        0,
        f"already sent: demo, to home-1, word {ID}\n",
    )


@pytest.mark.parametrize("text", ["not json", '[{"id": "a", "nope": 1}]'], ids=["text", "list"])
def test_a_words_file_that_does_not_parse_is_a_gate_and_the_rest_of_the_pass_runs(kitchen, text):
    kitchen.state.mkdir(parents=True, exist_ok=True)
    word.path(kitchen.state).write_text(text)
    said = kitchen.poll()
    assert kitchen.lines("condition") == ["condition demo: word-sends.json does not parse"]
    assert not [line for line in said if line.startswith(("pass failed", "wait: crews out"))]
    assert (
        jbus.read_json(kitchen.state / "wake.json", {})["began"] is True
        and kitchen.status()["projects"]["demo"]["last_error"] == ""
    )
    assert word.path(kitchen.state).read_text() == text
    code, out = kitchen.main("word", "--to", "demo", *SAID)
    assert code == 1 and "word-sends.json " in out and "nothing writes it" in out


def test_a_word_with_no_sign_in_waits_for_a_pass_that_has_one(kitchen):
    """A word the view keeps needs no read of T3 Code, and waits while jbus is not signed in."""
    (kitchen.home / "home-id").write_text("home-1\n")
    config = jbus.load()
    run = passes.Pass(config, config.project("demo"), NOW, lambda _: None)
    held = word.keep(run, party.Party("user", "view"), party.Evidence("view", "", WORDS, AT))
    word.deliver(run, None)
    said = f"waits: demo, jbus is not signed in to T3 Code, word {held.id}"
    assert word.line(run, held) == said
    assert "word demo: sent to home-1" in kitchen.poll()


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (["--to", "demo"], word.TYPED.removeprefix("refused: ")),
        (["--to", "demo", "--message", f"{CHAT}/m-blank"], f"message {CHAT}/m-blank has no words"),
        (["--to", "nope", *SAID], "no project nope, have demo"),
    ],
    ids=["no-message", "no-words", "no-such-project"],
)
def test_what_is_not_the_users_word_for_a_project_is_refused_and_nothing_is_kept(
    kitchen, argv, says
):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.t3.says(CHAT, "m-blank", " ")
    assert kitchen.main("word", *argv) == (1, f"refused: {says}\n")
    assert word.load(kitchen.state) == [] and sends(kitchen) == []


def test_a_word_typed_with_by_and_at_is_no_longer_taken(kitchen):
    """Only the user's own message is a word: `--by` and `--at` are gone."""
    code, out = kitchen.main("word", "--to", "demo", "--by", "user", "--at", AT, "go")
    assert code == 2 and "unrecognized arguments: --by user --at" in out
    assert word.load(kitchen.state) == [] and sends(kitchen) == []


def test_a_word_is_an_act_kept_once_with_the_users_message_as_its_evidence(kitchen):
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.main("word", "--to", "demo", *SAID)
    kitchen.main("word", "--to", "demo", *SAID)
    (one,) = [each for each in acts.read(kitchen.state) if each["action"]["verb"] == "word"]
    assert (one["id"], one["party"]["kind"], one["outcome"], one["line"]) == (
        ID,
        "home",
        "done",
        "kept",
    )
    assert (one["evidence"]["source"], one["evidence"]["ref"]) == ("t3-message", REF)
    assert one["evidence"]["checked"] is True


def test_a_word_names_one_project_or_all_and_not_both(kitchen):
    code, out = kitchen.main("word", *SAID)
    assert code == 2 and "one of the arguments --to --all is required" in out


def test_all_passes_over_a_project_whose_words_file_does_not_parse(kitchen):
    side = kitchen.second()
    (kitchen.home / "home-id").write_text("home-1\n")
    (side.home / "home-id").write_text("home-2\n")
    kitchen.state.mkdir(parents=True, exist_ok=True)
    word.path(kitchen.state).write_text("not json")
    code, out = kitchen.main("word", "--all", *SAID)
    refused = f"refused: {word.path(kitchen.state)} does not parse, and nothing writes it"
    assert (code, out) == (1, f"{refused}\nsent: other, to home-2, word {OTHER}\n")
    assert [one["threadId"] for one in sends(kitchen)] == ["home-2"]


def test_a_word_sent_whose_record_was_not_written_goes_again_under_the_same_key(kitchen):
    """The run stopped after T3 Code said yes and before the command wrote `sent_at`."""
    (kitchen.home / "home-id").write_text("home-1\n")
    kitchen.main("word", "--to", "demo", *SAID)
    word._write(kitchen.state, {ID: {"thread": "", "sent_at": "", "waits": ""}})
    assert "word demo: sent to home-1" in kitchen.poll()
    assert [one["clientRequestId"] for one in sends(kitchen)] == [f"word|demo|{ID}|home-1"] * 2
    assert list(kitchen.t3.messages) == [f"word|demo|{ID}|home-1"]
