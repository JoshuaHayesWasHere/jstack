"""A go and an answer are acts: each is one line of `acts.jsonl`, by a party, on evidence, and an
act on a door goes through only for the user on words jbus read itself.

The bot acts only over its own route, `POST /act` on the real view server, known by its key
alone. The tests run the real command, the real server and the real pass against the faked T3
Code server of `test_jbus_kitchen`.
"""

import json

import pytest

import jbus
import jsettings
from jbus import acts, blockers, item, party, questions, queue, waiting, wake, word
from jbus import view as jview
from jbus.view import state as view_state
from test_jbus_kitchen import ASK, RAN, SAID, Kitchen, sends
from test_jbus_queue import add, adds, approves, batch, brief, rows, sha12
from view.scene import free_port

HOME, MESSAGE = "mcp:a-home", "a-message-of-his"
REF = f"{HOME}/{MESSAGE}"
CHAT = "bot-chat:+15550100/a-phone"
HOLDS = "Holds: rewrites history\n"
SAFE = "Fail-safe: a bundle of the old history at ~/old.bundle\n"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


class Route:
    """The view's server, and the bot's key that `jbus bot key` made."""

    def __init__(self, kitchen):
        with kitchen.monkeypatch.context() as shell:
            shell.delenv(queue.SESSION)
            code, said = kitchen.main("bot", "key")
        assert code == 0, said
        self.key = said.splitlines()[0]
        sources = view_state.Sources(
            kitchen.state_dir, kitchen.root / "home", user=jsettings.load()
        )
        self.port = free_port()
        self.app = jview.App(sources)
        self.doors = jview.Doors(self.app, self.port)
        self.doors.open()

    def act(self, body, key=None, headers=None, project="demo"):
        import http.client

        link = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        sent = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if key is not False:
            sent["Authorization"] = f"Bearer {key or self.key}"
        try:
            link.request(
                "POST", f"/act?project={project}", json.dumps(body), sent | (headers or {})
            )
            answer = link.getresponse()
            return answer.status, json.loads(answer.read())
        finally:
            link.close()

    def get(self, path):
        import http.client

        link = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            link.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}"})
            return json.loads(link.getresponse().read())
        finally:
            link.close()

    def close(self):
        self.doors.close()


@pytest.fixture
def route(kitchen):
    made = Route(kitchen)
    yield made
    made.close()


def logged(kitchen):
    """Every act but the kitchen's word, which `kitchen.word` keeps for the gos to rest on."""
    return [one for one in acts.read(kitchen.state) if one["id"] != SAID]


def stored(kitchen, slug):
    return (kitchen.state / "briefs" / f"{slug}.md").read_text()


def bot_go(route, kitchen, slug, **more):
    body = {"action": "go", "slug": slug, "sha12": sha12(stored(kitchen, slug)), "evidence": CHAT}
    return route.act(body | more)


def gate(kitchen, holds=False):
    lines = ASK
    if holds:
        lines = ASK.replace("which one?", "which history?").replace(
            "Option:", f"{HOLDS}{SAFE}Option:", 1
        )
    code, said = kitchen.main("gate", "alpha", stdin=lines)
    assert code == 0, said
    return questions.read(kitchen.state)[-1].number


def test_the_door_table_names_what_pauses_and_what_is_a_review():
    assert waiting.paused("then force-push main") == "rewrites history"
    assert waiting.paused("deploy the site tonight") == "touches prod or real users"
    assert waiting.paused("drop the old tables") == "deletes data"
    assert waiting.paused("rotate the api key") == "changes access or secrets"
    asked = questions.Question(1, "alpha", "", "rotate the api key?", "", "", "", "", "")
    assert item.risk("", [asked]) is item.Risk.REVIEW
    edit = questions.Question(2, "alpha", "", "edit the config?", "", "", "", "", "")
    assert (item.risk("", [edit]), waiting.paused("edit the config")) == (item.Risk.REVIEW, "")


def _gate(question, context, known=("token-one-findings-route",)):
    slug = "token-no-cleanup-rows"
    asked = questions.Question(128, slug, "", question, "yes", "", "", "", None, context)
    return blockers.needs(questions.item(asked), context, frozenset(known))


def test_a_slug_that_holds_a_door_word_does_not_make_its_gate_hold():
    assert (
        _gate(
            "When the cleanup row route goes, should `Review: after` go too?",
            "token-one-findings-route is queued that way; "
            "~/.local/state/home/jstack/tasks/token-no-cleanup-rows.md, its Result\n"
            "Asked by: token-no-cleanup-rows, thread mcp:a-thread",
        )
        == ""
    )
    assert waiting.paused("Asked by: scout-token-review, thread mcp:a-thread") == ""


def test_a_gate_whose_prose_names_a_token_still_holds():
    asked = "Should the crew rotate the API token?"
    assert _gate(asked, "token-no-cleanup-rows asked it") == "it names changes access or secrets"
    assert waiting.paused("then force-push main, and e-mail the api-key") == "rewrites history"
    assert waiting.paused("e-mail the api-key") == "changes access or secrets"


@pytest.mark.parametrize(
    "words, case",
    [
        ("rotate the API-token", "changes access or secrets"),
        ("renew the refresh-token", "changes access or secrets"),
        ("set the db-password", "changes access or secrets"),
        ("send a one-time-password", "changes access or secrets"),
        ("re-deploy the site", "touches prod or real users"),
        ("hard-delete the data rows", "deletes data"),
    ],
)
def test_a_door_word_that_ends_a_hyphenated_compound_still_holds(words, case):
    assert waiting.paused(words) == case


@pytest.mark.parametrize(
    "words, case",
    [
        ("drop-and-recreate the tables", "deletes data"),
        ("wipe-and-reload the database", "deletes data"),
        ("we force-push-with-lease to main", "rewrites history"),
    ],
)
def test_a_door_word_that_leads_a_hyphenated_compound_still_holds(words, case):
    assert waiting.paused(words) == case


def test_only_a_slug_the_queue_knows_is_left_out_of_the_door_match(kitchen):
    add(kitchen, "token-one-findings-route")
    add(kitchen, "drop-old-tables")
    code, said = kitchen.main("queue", "remove", "drop-old-tables", "--by", "user", "--at", RAN)
    assert code == 0, said
    known = queue.known(kitchen.state)
    assert {"token-one-findings-route", "drop-old-tables"} <= known
    asked = questions.Question(
        3, "alpha", "", "token-one-findings-route waits, go on?", "", "", "", ""
    )
    assert item.risk("", [asked], known) is item.Risk.ROUTINE
    assert waiting.paused("drop-old-tables is gone, so go on", known) == ""
    assert waiting.paused("drop-old-tables is gone, so go on") == "deletes data"
    assert waiting.paused("deploy the site", known | {"deploy"}) == "touches prod or real users"
    unknown = "the cleanup-token-rows-fix row"
    assert _gate(unknown, "", known) == "it names changes access or secrets"


def test_a_hyphenated_config_word_still_makes_a_review():
    edit = questions.Question(2, "alpha", "", "edit the config-file?", "", "", "", "")
    assert item.risk("", [edit]) is item.Risk.REVIEW


def test_each_go_and_each_answer_is_one_act_and_each_basis_is_its_source(kitchen):
    kitchen.t3.says(HOME, MESSAGE, "yes")
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False)
    assert (
        kitchen.main(
            "queue", "approve", "beta", "--message", REF, "--sha", sha12(stored(kitchen, "beta"))
        )[0]
        == 0
    )
    number = gate(kitchen)
    assert kitchen.main("answer", str(number), "--message", REF, "--default")[0] == 0
    add(kitchen, "gamma", approve=False)
    assert (
        kitchen.main(
            "queue",
            "approve",
            "gamma",
            "--answer",
            str(number),
            "--sha",
            sha12(stored(kitchen, "gamma")),
        )[0]
        == 0
    )
    add(kitchen, "cleanup-alpha", approve=False)
    lines = logged(kitchen)
    assert [(one["v"], one["action"]["verb"], one["action"]["subject"]) for one in lines] == [
        (1, "go", "alpha"),
        (1, "go", "beta"),
        (1, "answer", str(number)),
        (1, "go", "gamma"),
    ]
    assert [(one["party"]["kind"], one["evidence"]["source"], one["outcome"]) for one in lines] == [
        ("home", "typed", "done"),
        ("home", "t3-message", "done"),
        ("home", "t3-message", "done"),
        ("home", "answer", "done"),
    ]
    assert lines[1]["evidence"]["checked"] is True
    assert {
        basis: jbus.party.Evidence(source, "").basis for basis, source in jbus.party.SOURCE.items()
    } == {basis: basis for basis in (*queue.BASES, queue.RULE, queue.ENTRY)}
    approval = rows(kitchen)["beta"]["approval"]
    assert (approval["basis"], approval["checked"]) == ("message", True)


def test_the_bots_route_takes_its_key_alone_and_nothing_else(kitchen, route):
    add(kitchen, "alpha", approve=False)
    forged = {"X-Forwarded-For": "192.0.2.9", "Tailscale-User-Login": "bot@example.test"}
    for key, headers in ((False, {}), ("not-the-key", {}), (False, forged), ("nope", forged)):
        body = {"action": "go", "slug": "alpha", "sha12": sha12(stored(kitchen, "alpha"))}
        status, said = route.act(body | {"evidence": CHAT}, key=key, headers=headers)
        assert (status, said) == (
            401,
            {"error": "this route is the bot's, and takes the bot's key"},
        )
    assert rows(kitchen)["alpha"]["approved"] == ""
    code, said = kitchen.main(
        "--as",
        "bot",
        "queue",
        "approve",
        "alpha",
        "--word",
        kitchen.word(),
        "--sha",
        sha12(stored(kitchen, "alpha")),
    )
    assert code == 2
    assert said.splitlines()[-1] == (
        "jbus: error: argument --as: refused: --as bot: the bot acts only over its own route, "
        "POST /act on jbus view, with its key, and on the command line a party is user or home"
    )
    assert (rows(kitchen)["alpha"]["approved"], logged(kitchen)) == ("", [])
    assert "sha256" in json.loads((kitchen.state_dir / acts.KEY).read_text())
    assert route.key not in (kitchen.state_dir / acts.KEY).read_text()


def test_a_bot_go_approves_a_row_that_names_no_door_and_the_pass_launches_it(kitchen, route):
    add(kitchen, "alpha", approve=False)
    status, said = bot_go(route, kitchen, "alpha")
    assert status == 200, said
    assert (said["act"]["outcome"], said["act"]["party"]) == (
        "done",
        {"kind": "bot", "route": "bot", "name": ""},
    )
    row = rows(kitchen)["alpha"]
    assert (row["approval"]["basis"], row["approval"]["checked"]) == ("bot-chat", False)
    assert row["approved"].startswith("the bot's go for you, ")
    ran = row["approval"]["ran_at"]
    assert row["approved"].endswith(
        f"from bot-chat {CHAT.removeprefix('bot-chat:')}; run {ran} by the bot"
    )
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_a_bot_go_on_a_brief_that_holds_parks_a_gate_for_the_user_and_approves_nothing(
    kitchen, route
):
    add(kitchen, "alpha", approve=False, text=brief("alpha", HOLDS))
    status, said = bot_go(route, kitchen, "alpha")
    assert status == 200, said
    assert (said["act"]["outcome"], said["act"]["action"]["doors"]) == (
        "gated",
        ["rewrites history"],
    )
    (asked,) = questions.read(kitchen.state)
    assert (asked.number, asked.holds, asked.answer) == (
        said["act"]["gate"],
        "rewrites history",
        None,
    )
    assert rows(kitchen)["alpha"]["approved"] == ""
    kitchen.poll()
    assert kitchen.t3.launches == []
    assert questions.read(kitchen.state)[0].answer is None
    sha = sha12(stored(kitchen, "alpha"))
    code, said = kitchen.main("queue", "approve", "alpha", "--word", kitchen.word(), "--sha", sha)
    assert (code, said.splitlines()[0]) == (
        0,
        "gated alpha: its brief holds for rewrites history, so it waits for user's own word: "
        f"question {asked.number}",
    )
    kitchen.t3.says(HOME, MESSAGE, "yes, rewrite it")
    code, said = kitchen.main(
        "--as", "user", "queue", "approve", "alpha", "--message", REF, "--sha", sha
    )
    assert code == 0, said
    assert rows(kitchen)["alpha"]["approval"]["checked"] is True
    assert questions.read(kitchen.state)[0].answer.closed_by == questions.CLEARED
    assert [one["outcome"] for one in logged(kitchen)] == ["gated", "gated", "done"]


def test_a_follow_up_on_a_door_parks_a_gate_whose_command_names_the_stored_briefs_sha(kitchen):
    """A go by --follows takes no sha, so the gate it parks names the sha the user is shown: the
    command its Undo line gives the user is one `approve` takes."""
    add(kitchen, "alpha")
    add(kitchen, "beta", approve=False, text=brief("beta", HOLDS))
    code, said = kitchen.main("queue", "approve", "beta", "--follows", "alpha")
    assert code == 0 and said.startswith("gated beta: its brief holds for rewrites history")
    (asked,) = questions.read(kitchen.state)
    sha = sha12(stored(kitchen, "beta"))
    assert f"queue approve beta --sha {sha} --message <thread>/<message>" in asked.undo
    kitchen.t3.says(HOME, MESSAGE, "yes, rewrite it")
    code, said = kitchen.main(
        "--as", "user", "queue", "approve", "beta", "--message", REF, "--sha", sha
    )
    assert code == 0, said
    assert rows(kitchen)["beta"]["approval"]["checked"] is True


def test_a_fail_safe_line_under_holds_is_its_own_field_so_the_go_names_only_its_door(
    kitchen, route
):
    add(kitchen, "alpha", approve=False, text=brief("alpha", HOLDS + SAFE))
    assert party.doors(stored(kitchen, "alpha")) == ("rewrites history",)
    status, said = bot_go(route, kitchen, "alpha")
    assert status == 200, said
    assert said["act"]["action"]["doors"] == ["rewrites history"]
    needs = [one for one in route.get("/stack.json")["needs"] if one["kind"] == "gate"]
    assert [one["what"] for one in needs] == ["may alpha go? Its brief holds for rewrites history"]
    (asked,) = questions.read(kitchen.state)
    assert (asked.holds, "too" in asked.context) == ("rewrites history", False)


def test_a_bot_answer_closes_a_two_way_gate_and_is_refused_on_a_gate_that_holds(kitchen, route):
    add(kitchen, "beta", approve=False)
    kitchen.brief("alpha", "Thread: mcp:crew-alpha\n")
    plain = gate(kitchen)
    body = {
        "action": "answer",
        "number": plain,
        "words": "the other",
        "keeps": False,
        "evidence": CHAT,
    }
    status, said = route.act(body)
    assert status == 200, said
    assert said["act"]["outcome"] == "done"
    closed = questions.read(kitchen.state)[0].answer
    assert (closed.words, closed.by, closed.keeps, closed.checked) == (
        "the other",
        "the bot",
        False,
        False,
    )
    held = gate(kitchen, holds=True)
    status, said = route.act(body | {"number": held})
    assert status == 409
    assert said["error"] == (
        f"refused: question {held} holds (rewrites history): only user's own word, read in T3 "
        "Code or on a Lavish page, answers it, so it stays open. It closes with jbus --as user "
        f"answer {held} --default --message <thread id>/<message id>, or --differs for an "
        "answer that is not the default, where the message is user's own in T3 Code: --by and "
        "--at cannot close it"
    )
    assert (said["act"]["outcome"], said["act"]["action"]["doors"]) == (
        "refused",
        ["rewrites history"],
    )
    assert questions.question(kitchen.state, held).answer is None


def test_a_home_typing_the_users_name_on_a_door_is_refused_and_the_gate_stays_open(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew-alpha\n")
    held = gate(kitchen, holds=True)
    code, said = kitchen.main(
        "answer", str(held), "--by", "user", "--at", "2026-10-12 11:00 ET", "--default", "yes"
    )
    assert (code, said) == (
        1,
        f"refused: question {held} holds (rewrites history): only user's own word, read in T3 "
        "Code or on a Lavish page, answers it, so it stays open. It closes with jbus --as user "
        f"answer {held} --default --message <thread id>/<message id>, or --differs for an "
        "answer that is not the default, where the message is user's own in T3 Code: --by and "
        "--at cannot close it\n",
    )
    assert questions.question(kitchen.state, held).answer is None
    assert [
        (one["party"]["kind"], one["evidence"]["source"], one["outcome"]) for one in logged(kitchen)
    ] == [("home", "typed", "refused")]
    kitchen.t3.says(HOME, MESSAGE, "yes")
    code, said = kitchen.main("--as", "user", "answer", str(held), "--default", "--message", REF)
    assert code == 0, said
    assert questions.question(kitchen.state, held).answer.keeps
    code, said = kitchen.main(
        "--as",
        "user",
        "answer",
        str(held),
        "--by",
        "user",
        "--at",
        "2026-10-12 11:00 ET",
        "--default",
        "yes",
    )
    assert (code, said) == (
        1,
        "refused: --as user acts on the user's own words that jbus reads itself, --message "
        "<thread>/<message> or --page <session>/<entry>, and this act has typed words\n",
    )


def last_seen(kitchen):
    """The id of the newest event, as `jbus events` prints it for the bot."""
    code, said = kitchen.main("events")
    assert code == 0
    return json.loads(said.splitlines()[-1])["id"]


def test_a_second_go_is_a_noop_and_a_go_on_an_older_event_is_stale(kitchen, route):
    add(kitchen, "alpha", approve=False)
    assert bot_go(route, kitchen, "alpha")[0] == 200
    approved = rows(kitchen)["alpha"]["approval"]
    status, said = bot_go(route, kitchen, "alpha")
    assert (status, said["act"]["outcome"]) == (200, "noop")
    assert rows(kitchen)["alpha"]["approval"] == approved
    add(kitchen, "beta", approve=False)
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    box.send("beta", "queue", "queue demo: beta is queued")
    seen = last_seen(kitchen)
    box.send("beta", "queue", "queue demo: beta's brief changed")
    status, said = bot_go(route, kitchen, "beta", seen=seen)
    assert status == 409
    assert said["error"].startswith(f"refused: stale: beta changed after event {seen}, in event ")
    assert (said["act"]["outcome"], rows(kitchen)["beta"]["approved"]) == ("refused", "")
    status, said = bot_go(route, kitchen, "beta", seen="not-an-event")
    assert (status, said["error"]) == (409, "refused: stale: no event not-an-event in demo's log")
    status, said = bot_go(route, kitchen, "beta", seen=last_seen(kitchen))
    assert (status, said["act"]["outcome"]) == (200, "done")


GO_GATE = (
    "## Gate <n>: start {slug}?\nStatus: open\nAsked by: home, thread mcp:a-home\n"
    "Default: approve\nBuilt on it: nothing yet\nUndo: hold the row\n"
    "Option: start it (default, recommended): the row launches\nOption: wait: it waits\n"
)


def test_the_bots_answer_that_keeps_a_go_gates_default_is_a_go_and_a_door_still_waits(
    kitchen, route
):
    add(kitchen, "plain", approve=False)
    add(kitchen, "door", approve=False, text=brief("door", HOLDS))
    numbers = {}
    for slug in ("plain", "door"):
        code, said = kitchen.main("gate", slug, stdin=GO_GATE.format(slug=slug))
        assert code == 0, said
        numbers[slug] = int(said.split()[-1])
    body = {"action": "answer", "words": "yes, start it", "keeps": True, "evidence": CHAT}
    status, said = route.act(body | {"number": numbers["plain"]})
    assert (status, said["act"]["outcome"]) == (200, "done")
    assert "approved plain" in said["act"]["line"]
    assert rows(kitchen)["plain"]["approval"]["basis"] == "answer"
    status, said = route.act(body | {"number": numbers["door"]})
    assert status == 409
    assert said["error"] == (
        f"refused: question {numbers['door']} keeps the go of door, whose brief holds for "
        "rewrites history: only user's own word, read in T3 Code or on a Lavish page, answers it, "
        f"so it stays open. It closes with jbus --as user answer {numbers['door']} --default "
        "--message <thread id>/<message id>, or --differs for an answer that is not the default, "
        "where the message is user's own in T3 Code: --by and --at cannot close it"
    )
    assert rows(kitchen)["door"]["approved"] == ""
    assert questions.question(kitchen.state, numbers["door"]).answer is None


def test_an_agents_session_cannot_make_the_bots_key(kitchen, route):
    kept = (kitchen.state_dir / acts.KEY).read_text()
    assert kitchen.main("bot", "key") == (1, f"{acts.BOT_KEY_SESSION}\n")
    assert (kitchen.state_dir / acts.KEY).read_text() == kept
    assert acts.is_bot(kitchen.state_dir, f"Bearer {route.key}")


def test_a_batch_that_adds_a_brief_that_holds_and_approves_it_is_refused(kitchen):
    add(kitchen, "alpha", approve=False)
    held = brief("gamma", HOLDS)
    text = batch(adds("gamma", "--priority 1", held), approves("gamma", sha12(held)))
    code, said = kitchen.main("queue", "apply", stdin=text)
    assert (code, said) == (
        1,
        "refused: approve gamma in a batch: its brief holds for rewrites history, so its go goes "
        "by jbus queue approve alone, and nothing in the batch was applied\n",
    )
    assert "gamma" not in rows(kitchen)
    assert logged(kitchen) == []


READ = "read vision.md"
SHAPE = (
    "an act is {action: go, slug, sha12}, {action: answer, number, words, keeps} or "
    "{action: word, words}, with evidence bot-chat:<address>/<device> and an optional seen"
)


def test_a_bot_word_on_bot_chat_evidence_goes_to_the_projects_home(kitchen, route):
    (kitchen.home / "home-id").write_text("home-1\n")
    add(kitchen, "alpha", approve=False)
    status, said = route.act({"action": "word", "words": f"  {READ} ", "evidence": CHAT})
    assert status == 200, said
    made = said["act"]
    assert (made["outcome"], made["line"], made["party"]["kind"]) == ("done", word.KEPT, "bot")
    assert made["action"]["verb"] == "word"
    assert made["evidence"] | {"said_at": ""} == {
        "source": "bot-chat",
        "ref": CHAT.removeprefix("bot-chat:"),
        "words": READ,
        "said_at": "",
        "said_in": f"bot-chat {CHAT.removeprefix('bot-chat:')}",
        "checked": False,
        "picks": [],
    }
    (sent,) = sends(kitchen)
    assert sent["threadId"] == "home-1" and sent["message"].endswith(f"\n\n{READ}")
    assert sent["clientRequestId"] == f"word|demo|{made['id']}|home-1"
    (kept,) = [one for one in word.load(kitchen.state) if one.id == made["id"]]
    assert (kept.thread, kept.by, kept.checked) == ("home-1", "bot/bot", False)


@pytest.mark.parametrize(
    "evidence",
    [None, "voice:+15550100/a-phone", "bot-chat:+15550100", "bot-chat:/a-phone", "t3-message:a/b"],
    ids=["missing", "voice", "no-device", "no-address", "not-the-bots"],
)
@pytest.mark.parametrize("verb", ["go", "word"])
def test_a_bot_go_or_word_on_evidence_that_is_not_the_bots_chat_is_refused(
    kitchen, route, verb, evidence
):
    (kitchen.home / "home-id").write_text("home-1\n")
    add(kitchen, "alpha", approve=False)
    body = {"action": "word", "words": READ}
    if verb == "go":
        body = {"action": "go", "slug": "alpha", "sha12": sha12(stored(kitchen, "alpha"))}
    if evidence is not None:
        body["evidence"] = evidence
    assert route.act(body) == (400, {"error": SHAPE})
    assert (logged(kitchen), sends(kitchen), rows(kitchen)["alpha"]["approved"]) == ([], [], "")


@pytest.mark.parametrize("verb", ["go", "word"])
def test_a_bot_word_is_checked_as_a_go_is_for_its_key_and_its_project(kitchen, route, verb):
    (kitchen.home / "home-id").write_text("home-1\n")
    add(kitchen, "alpha", approve=False)
    body = {"action": "word", "words": READ, "evidence": CHAT}
    if verb == "go":
        body = {"action": "go", "slug": "alpha", "sha12": sha12(stored(kitchen, "alpha"))}
        body["evidence"] = CHAT
    refused = {"error": "this route is the bot's, and takes the bot's key"}
    assert route.act(body, key=False) == (401, refused)
    assert route.act(body, key="not-the-key") == (401, refused)
    assert route.act(body, project="nope")[0] == 404
    assert (logged(kitchen), sends(kitchen), rows(kitchen)["alpha"]["approved"]) == ([], [], "")


def test_a_bot_word_with_no_words_is_refused(kitchen, route):
    add(kitchen, "alpha", approve=False)
    for words in (None, "", "   ", 3):
        body = {"action": "word", "evidence": CHAT}
        if words is not None:
            body["words"] = words
        assert route.act(body) == (400, {"error": SHAPE})
    assert (logged(kitchen), sends(kitchen)) == ([], [])


def test_the_bot_sending_one_chat_message_again_later_is_the_same_word(kitchen, route):
    """The bot's address names its message, so a resend minutes later, after a lost answer,
    is the same word and goes to the home once."""
    from datetime import UTC, datetime, timedelta

    (kitchen.home / "home-id").write_text("home-1\n")
    add(kitchen, "alpha", approve=False)
    first = datetime(2026, 10, 29, 20, 0, tzinfo=UTC)
    body = {"action": "word", "words": READ, "evidence": CHAT}
    route.app.clock = lambda: first
    status, said = route.act(body)
    assert status == 200, said
    route.app.clock = lambda: first + timedelta(minutes=3)
    again, said_again = route.act(body)
    assert again == 200, said_again
    assert said_again["act"]["id"] == said["act"]["id"]
    assert said_again["say"] == f"already sent: demo, to home-1, word {said['act']['id']}"
    assert len(sends(kitchen)) == 1
    other = route.act(body | {"evidence": "bot-chat:+15550100/another-phone"})[1]
    assert other["act"]["id"] != said["act"]["id"] and len(sends(kitchen)) == 2
