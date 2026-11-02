"""A brief holds for a door by its `Holds:` lines and by the commands its `Done when:` and
`Proves it:` lines run (`party.DOORS`, each case's `runs`). A word that a bot or a home carried
opens no such door, on any basis jbus has: only the user's own message or pick, read in T3 Code,
that names the row or its gate and was said after the brief was stored.

The commands are Winnifred's `qw-deploy-main-to-prod` brief, whose go on a word the bot carried
deployed prod on 2026-10-30 with no `Holds:` line, and the table the scout replayed over the week
audit. The tests run the real commands, the bot's route and the pass against the kitchen's fakes.
"""

from datetime import UTC, datetime, timedelta

import pytest

from jbus import party, questions, queue
from test_jbus_acts import CHAT, Route, bot_go, stored
from test_jbus_approve_by_pick import QUESTION, shown
from test_jbus_approve_by_pick import REF as PICKED
from test_jbus_approve_by_pick import stored as answered
from test_jbus_entry_go import GATE, PLAN, Frozen, silence
from test_jbus_kitchen import NOW, Kitchen, iso
from test_jbus_queue import approves, brief, rows, sha12
from testing.paths import REPO

PROD = "touches prod or real users"
DEPLOY = "DSQL_STAGE=prod db/apply.sh dsql migrations/0023.up.sql"
WINNIFRED = (REPO / "features/jbus/tests/fixtures/doors/qw-deploy-main-to-prod.md").read_text()
HOME = "mcp:a-home"
BOT = "bot-chat:t36u/a-phone"
CARRIED = "deploy the changes that have landed so far to prod"


def door(slug, more=""):
    """A brief whose `Done when:` runs a prod migration, with no `Holds:` line."""
    return brief(slug, more).replace("- it is done\n", f"- `{DEPLOY}` is run on prod\n")


def test_winnifreds_prod_deploy_brief_holds_for_prod_by_the_migration_it_runs():
    assert "Holds:" not in WINNIFRED
    assert party.doors(WINNIFRED) == (PROD,)
    assert party.walked(WINNIFRED) == (
        (PROD, "DSQL_STAGE=prod db/apply.sh dsql migrations/0023_delivery_dismissed.up.sql"),
    )


@pytest.mark.parametrize(
    "command, case",
    [
        ("DSQL_STAGE=prod db/apply.sh dsql x.up.sql", PROD),
        ("AWS_PROFILE=winnifred-prod sam logs", PROD),
        ("infra/deploy-backend.sh prod", PROD),
        ("scripts/deploy caveman", PROD),
        ("sam deploy --stack-name x", PROD),
        ("terraform apply", PROD),
        ("kubectl apply -f x.yaml", PROD),
        ("git push --force origin main", "rewrites history"),
        ("git push origin main -f", "rewrites history"),
        ("git filter-repo --path x", "rewrites history"),
        ("psql -c DROP TABLE dose", "deletes data"),
        ("aws s3 rm s3://bucket/x --recursive", "deletes data"),
        ("git branch -D old", "deletes data"),
        ("git worktree remove ../old", "deletes data"),
        ("git push origin --delete old", "deletes data"),
        ("gh repo delete x/y", "deletes data"),
        ("tailscale serve --bg 8491", "changes access or secrets"),
        ("tailscale funnel 443", "changes access or secrets"),
        ("edit policy/tailnet.hujson", "changes access or secrets"),
        ("grant tag:grokbox to the box", "changes access or secrets"),
        ("export CLOUDFLARE_API_TOKEN=x", "changes access or secrets"),
        ("gh release create v1.0", "publishes"),
        ("uv publish", "publishes"),
        ("twine upload dist/*", "publishes"),
        ("git push origin --tags", "publishes"),
    ],
)
def test_each_command_of_the_table_walks_through_its_door(command, case):
    assert [one for one, _ in party.walks(f"`{command}`")] == [case]
    assert party.doors(brief("alpha", f"Proves it: `{command}`\n")) == (case,)


@pytest.mark.parametrize(
    "command",
    [
        "DSQL_STAGE=prod db/apply.sh dsql x.up.sql --dry-run",
        "DRY_RUN=1 ./deploy-backend.sh prod",
        "deploy-backend.sh dev",
        "scripts/deploy --help",
        "git push --force-with-lease=main:abc origin x",
        "git fetch origin --tags",
        "git branch -d merged-old",
        "tailscale serve status",
        "tailscale funnel 443 off",
        "git commit -m fix the deploy script",
        "grep -rn deploy features/",
        "less api/DEPLOYMENT.md",
        "make check",
    ],
)
def test_a_dry_run_and_a_command_that_only_names_a_door_walk_through_none(command):
    assert party.walks(f"`{command}`") == ()


def test_a_segment_that_says_the_command_is_never_run_holds_nothing():
    said = brief("alpha").replace(
        "- it is done\n",
        "- the fix ships; never `git push --force` to main\n"
        "- it runs `make check` without `terraform apply`\n"
        "- `DSQL_STAGE=prod db/apply.sh` is not run here\n"
        "- do not `twine upload`\n",
    )
    assert party.doors(said) == ()


@pytest.mark.parametrize(
    "line",
    [
        "run `infra/deploy-backend.sh prod` from a checkout, never `sam deploy` by hand",
        "`terraform apply` without -target",
        "never `sam build` by hand, then `infra/deploy-backend.sh prod`",
    ],
)
def test_an_aside_hides_only_the_command_it_is_about_not_a_door_beside_it(line):
    assert party.doors(brief("alpha").replace("- it is done\n", f"- {line}\n")) == (PROD,)


def test_a_command_outside_done_when_and_proves_it_holds_nothing():
    said = brief("alpha", "Instruments: `terraform apply`\nRead: `scripts/deploy`\n")
    assert party.doors(said) == ()


def test_the_cases_holds_lines_declare_and_the_commands_imply_are_one_set():
    said = door("alpha", "Holds: publishes\n")
    assert party.doors(said) == (PROD, "publishes")
    assert queue.case(said) == f"{PROD}, publishes"


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    (made.home / "plan.md").write_text(PLAN)
    (made.home / "home-id").write_text("home-1\n")
    monkeypatch.setattr(questions, "datetime", Frozen)
    made.settings = jstack_config
    yield made
    made.close()


@pytest.fixture
def route(kitchen):
    made = Route(kitchen)
    yield made
    made.close()


def queued(kitchen, slug="deploy-prod", text=None, entry="epic"):
    code, said = kitchen.main(
        "queue", "add", slug, "--priority", "1", "--entry", entry, stdin=text or door(slug)
    )
    assert code == 0, said
    return said


def josh(kitchen, words, name="josh-go", at=None):
    """Josh's own message in T3 Code, said now (after the brief was stored) unless `at` says."""
    kitchen.t3.says(HOME, name, words, updatedAt=iso(at or datetime.now(UTC)))
    return f"{HOME}/{name}"


def approve(kitchen, slug, *basis, user=False):
    sha = sha12(stored(kitchen, slug))
    who = ("--as", "user") if user else ()
    return kitchen.main(*who, "queue", "approve", slug, *basis, "--sha", sha)


def test_queue_add_says_which_door_the_commands_imply_and_the_brief_does_not_declare(kitchen):
    said = queued(kitchen)
    assert f"holds: {PROD}, from {DEPLOY}\n" in said
    declared = queued(kitchen, "declared", door("declared", f"Holds: {PROD}\n"))
    assert "holds:" not in declared


def carried_word(kitchen, route, slug):
    code, said = kitchen.main("word", "--to", "demo", "--evidence", BOT, "--words", CARRIED)
    assert code == 0, said
    return approve(kitchen, slug, "--word", said.split()[-1])[1]


def typed_word(kitchen, route, slug):
    return approve(kitchen, slug, "--word", kitchen.word())[1]


def bot_route_go(kitchen, route, slug):
    status, said = bot_go(route, kitchen, slug)
    assert status == 200, said
    return said["act"]["line"]


def bot_route_answer(kitchen, route, slug):
    number = bot_go(route, kitchen, slug)[1]["act"]["gate"]
    body = {"action": "answer", "number": number, "words": "yes", "keeps": True, "evidence": CHAT}
    status, said = route.act(body)
    assert status == 409, said
    return said["error"]


def batch(kitchen, route, slug):
    return kitchen.main("queue", "apply", stdin=approves(slug, sha12(stored(kitchen, slug))))[1]


def entry_go(kitchen, route, slug):
    kitchen.t3.says(HOME, "on-the-epic", "go on the epic")
    code, said = kitchen.main("plan", "go", "epic", "--message", f"{HOME}/on-the-epic")
    assert code == 0, said
    kitchen.poll()
    return said


def follow_up(kitchen, route, slug):
    queued(kitchen, "parent", brief("parent"))
    assert approve(kitchen, "parent", "--word", kitchen.word())[0] == 0
    return approve(kitchen, slug, "--follows", "parent")[1]


def silence_close(kitchen, route, slug):
    silence(kitchen)
    code, said = kitchen.main("gate", slug, stdin=GATE.format(slug=slug))
    assert code == 0, said
    return "\n".join(kitchen.poll(NOW + timedelta(minutes=31)))


def view_answer(kitchen, route, slug):
    code, said = kitchen.main("gate", slug, stdin=GATE.format(slug=slug))
    assert code == 0, said
    status, said = route.answer({"numbers": [int(said.split()[-1])]})
    assert status == 409, said
    return said["refused"][0]["say"]


def user_message(kitchen, route, slug):
    code, said = approve(kitchen, slug, "--message", josh(kitchen, f"go {slug}"), user=True)
    assert code == 0, said
    return said


def user_pick(kitchen, route, slug):
    shown(kitchen, labels=[f"{slug} (S)", "other (S)"])
    answered(
        kitchen.root,
        kitchen.monkeypatch,
        {QUESTION: [f"{slug} (S)"]},
        resolved=iso(datetime.now(UTC)),
    )
    code, said = approve(kitchen, slug, "--pick", PICKED, user=True)
    assert code == 0, said
    return said


SHUT = [
    (carried_word, "gated deploy-prod: its brief holds for touches prod or real users"),
    (typed_word, "gated deploy-prod: its brief holds for touches prod or real users"),
    (bot_route_go, "gated deploy-prod: its brief holds for touches prod or real users"),
    (bot_route_answer, "holds (touches prod or real users): only user's own word"),
    (batch, "refused: approve deploy-prod in a batch: its brief holds for touches prod"),
    (entry_go, "went epic: your go for the plan entry epic"),
    (follow_up, "gated deploy-prod: its brief holds for touches prod or real users"),
    (silence_close, "deploy-prod waits for the user's go after question"),
    (view_answer, "keeps the go of deploy-prod, whose brief holds for touches prod"),
]


@pytest.mark.parametrize("basis, says", SHUT, ids=[one.__name__ for one, _ in SHUT])
def test_no_carried_or_typed_basis_opens_a_door_the_commands_imply(kitchen, route, basis, says):
    queued(kitchen)
    said = basis(kitchen, route, "deploy-prod")
    assert says in said
    assert rows(kitchen)["deploy-prod"]["approved"] == ""
    kitchen.poll()
    assert "crew: deploy-prod" not in [launch["title"] for launch in kitchen.t3.launches]


@pytest.mark.parametrize("basis", [user_message, user_pick], ids=["message", "pick"])
def test_the_users_own_message_or_pick_naming_the_row_opens_it(kitchen, route, basis):
    queued(kitchen)
    basis(kitchen, route, "deploy-prod")
    assert rows(kitchen)["deploy-prod"]["approval"]["checked"] is True
    kitchen.poll()
    assert "crew: deploy-prod" in [launch["title"] for launch in kitchen.t3.launches]


def test_the_carried_word_parks_a_gate_whose_holds_names_the_case(kitchen):
    queued(kitchen)
    said = carried_word(kitchen, None, "deploy-prod")
    (asked,) = questions.read(kitchen.state)
    assert f"so it waits for user's own word: question {asked.number}\n" in said
    assert (asked.slug, asked.holds) == ("deploy-prod", PROD)


def test_a_message_of_joshs_that_names_another_row_is_refused_and_says_what_to_send(kitchen):
    queued(kitchen)
    ref = josh(kitchen, "go on the skills")
    code, said = approve(kitchen, "deploy-prod", "--message", ref, user=True)
    sha = sha12(stored(kitchen, "deploy-prod"))
    assert (code, said) == (
        1,
        f"refused: deploy-prod's brief holds for {PROD}, and message {ref} (\"go on the "
        'skills") names neither deploy-prod nor its gate: user sends "go deploy-prod" in T3 '
        f"Code, and jbus --as user queue approve deploy-prod --sha {sha} --message "
        "<thread>/<message> records it\n",
    )
    assert rows(kitchen)["deploy-prod"]["approved"] == ""


def test_a_message_of_joshs_said_before_the_brief_was_stored_is_refused(kitchen):
    queued(kitchen)
    ref = josh(kitchen, "go deploy-prod", at=datetime.now(UTC) - timedelta(days=1))
    code, said = approve(kitchen, "deploy-prod", "--message", ref, user=True)
    assert code == 1
    assert said.startswith(
        f"refused: deploy-prod's brief holds for {PROD}, and message {ref} was said at "
    )
    assert "before deploy-prod's brief was stored at " in said
    assert rows(kitchen)["deploy-prod"]["approved"] == ""


def test_a_message_naming_the_parked_gates_number_opens_it_and_closes_the_gate(kitchen):
    queued(kitchen)
    carried_word(kitchen, None, "deploy-prod")
    (asked,) = questions.read(kitchen.state)
    ref = josh(kitchen, f"yes to {asked.number}")
    code, said = approve(kitchen, "deploy-prod", "--message", ref, user=True)
    assert code == 0, said
    assert questions.read(kitchen.state)[0].answer.closed_by == questions.CLEARED


def test_an_answer_to_a_held_gate_names_its_number_or_its_row(kitchen):
    queued(kitchen)
    carried_word(kitchen, None, "deploy-prod")
    (asked,) = questions.read(kitchen.state)
    number = str(asked.number)
    unrelated = josh(kitchen, "yes", name="plain-yes")
    code, said = kitchen.main("--as", "user", "answer", number, "--differs", "--message", unrelated)
    assert code == 1 and "names neither deploy-prod nor question" in said, said
    assert questions.question(kitchen.state, asked.number).answer is None
    named = josh(kitchen, f"go on {number}, deploy it", name="named")
    code, said = kitchen.main("--as", "user", "answer", number, "--differs", "--message", named)
    assert code == 0, said


def test_an_edit_that_adds_a_door_takes_the_rows_go_back(kitchen):
    """`Proves it:` and `Holds:` are not what a go's fingerprint reads, so a go would hold for a
    brief edited to run a door after it: the edit takes the go back instead."""
    queued(kitchen, "plain", brief("plain"))
    assert approve(kitchen, "plain", "--word", kitchen.word())[0] == 0
    edited = brief("plain", f"Holds: {PROD}\n").replace(
        "Proves it: `make check`", f"Proves it: `make check`, then `{DEPLOY}`"
    )
    said = queued(kitchen, "plain", edited)
    assert f"plain's go is taken back: its brief now holds for {PROD}" in said
    assert rows(kitchen)["plain"]["approved"] == ""
    kitchen.poll()
    assert "crew: plain" not in [launch["title"] for launch in kitchen.t3.launches]


def test_a_carried_go_on_winnifreds_prod_deploy_brief_is_gated_and_launches_nothing(kitchen):
    text = WINNIFRED.replace("Home: 123s\n", "Home: root\n")
    queued(kitchen, "qw-deploy-main-to-prod", text)
    said = carried_word(kitchen, None, "qw-deploy-main-to-prod")
    (asked,) = questions.read(kitchen.state)
    assert said.startswith(
        f"gated qw-deploy-main-to-prod: its brief holds for {PROD}, so it waits for user's own "
        f"word: question {asked.number}\n"
    )
    assert asked.holds == PROD
    assert rows(kitchen)["qw-deploy-main-to-prod"]["approved"] == ""
    kitchen.poll()
    assert kitchen.t3.launches == []


DELETES = "deletes data"
STALE = "stale-worktrees"


def deletes(kitchen):
    """A row whose brief holds for deletes data, as stale-worktrees-1102's did on 2026-11-02."""
    queued(kitchen, STALE, brief(STALE, f"Holds: {DELETES}\n"))
    return sha12(stored(kitchen, STALE))


WORDINGS = [
    "go {slug}",
    "approve {slug} (brief sha {sha})",
    "answer question 7 ({slug}): yes, go",
]


@pytest.mark.parametrize("wording", WORDINGS, ids=["go", "tree-approve", "tree-answer"])
def test_the_homes_approve_on_the_users_own_message_opens_the_door_at_once(kitchen, wording):
    """Josh sent "approve stale-worktrees-1102 (brief sha fd285a40568d)" from T3 Code, and the
    home's plain `jbus queue approve --message` on it parked a question and approved nothing."""
    sha = deletes(kitchen)
    ref = josh(kitchen, wording.format(slug=STALE, sha=sha))
    code, said = approve(kitchen, STALE, "--message", ref)
    assert code == 0, said
    assert said.startswith(f"approved {STALE}: brief {sha}"), said
    assert questions.read(kitchen.state) == []
    assert rows(kitchen)[STALE]["approval"]["checked"] is True
    kitchen.poll()
    assert f"crew: {STALE}" in [launch["title"] for launch in kitchen.t3.launches]


def test_a_message_that_is_not_the_users_own_opens_no_door(kitchen):
    deletes(kitchen)
    ref = f"{HOME}/agent-go"
    kitchen.t3.says(HOME, "agent-go", f"go {STALE}", type="assistant_message", createdBy="agent")
    code, said = approve(kitchen, STALE, "--message", ref)
    assert code == 1
    assert said.startswith(f"refused: message {ref} is not user's own"), said
    assert rows(kitchen)[STALE]["approved"] == ""


def test_a_bot_carried_word_naming_the_row_opens_no_door(kitchen):
    deletes(kitchen)
    code, said = kitchen.main("word", "--to", "demo", "--evidence", BOT, "--words", f"go {STALE}")
    assert code == 0, said
    said = approve(kitchen, STALE, "--word", said.split()[-1])[1]
    assert said.startswith(f"gated {STALE}: its brief holds for {DELETES}"), said
    assert rows(kitchen)[STALE]["approved"] == ""


def test_the_homes_approve_on_a_message_said_before_the_brief_was_stored_opens_no_door(kitchen):
    sha = deletes(kitchen)
    ref = josh(kitchen, f"go {STALE}", at=datetime.now(UTC) - timedelta(days=1))
    code, said = approve(kitchen, STALE, "--message", ref)
    assert code == 1
    assert f"before {STALE}'s brief was stored at " in said, said
    assert f"jbus queue approve {STALE} --sha {sha} --message <thread>/<message>" in said
    assert "--as user" not in said and f'sends "go {STALE}"' not in said
    assert rows(kitchen)[STALE]["approved"] == ""


def test_a_gated_go_names_the_command_that_opens_it_and_the_users_approve_closes_its_gate(
    kitchen,
):
    sha = deletes(kitchen)
    said = typed_word(kitchen, None, STALE)
    (asked,) = questions.read(kitchen.state)
    assert said.startswith(f"gated {STALE}: its brief holds for {DELETES}"), said
    assert f"jbus queue approve {STALE} --sha {sha} --message <thread>/<message>" in said
    shown = f"{asked.undo}\n{asked.context}\n" + "\n".join(one.follows for one in asked.options)
    assert "--as user" not in shown and '"go ' not in shown
    code, said = approve(kitchen, STALE, "--message", josh(kitchen, f"approve {STALE}"))
    assert code == 0, said
    assert questions.question(kitchen.state, asked.number).answer.closed_by == questions.CLEARED


def test_the_users_answer_to_a_may_go_gate_approves_the_row(kitchen):
    """Question 158: the user's answer, `jbus --as user answer`, recorded their message and the
    row still waited, so the home's approve refused again."""
    deletes(kitchen)
    typed_word(kitchen, None, STALE)
    (asked,) = questions.read(kitchen.state)
    ref = josh(kitchen, f"approve {STALE} (brief sha {sha12(stored(kitchen, STALE))})")
    number = str(asked.number)
    code, said = kitchen.main("--as", "user", "answer", number, "--differs", "--message", ref)
    assert code == 0, said
    assert f"approved {STALE}: brief " in said, said
    assert rows(kitchen)[STALE]["approval"]["checked"] is True
    code, said = approve(kitchen, STALE, "--message", ref)
    assert code == 0 and said.startswith("already"), said
