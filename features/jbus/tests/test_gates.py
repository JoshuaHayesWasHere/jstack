"""A question only the user can answer is one numbered record in jbus, and a home keeps no copy
of it. The home reads the open questions from jbus, runs `jbus answer` with the user's words, and
treats a word that `jbus word` delivered as the user's own.

The tests take the home skill's blocks out of the skill file and run them as the skill says,
against the real `jbus` in the temporary state directory of `test_jbus`'s kitchen. The passes are
the real ones, against the kitchen's faked T3 Code server. Nothing reaches the network."""

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

import jbus
import jsettings
from jbus import questions
from jbus.view import state as view_state
from test_home_thread import (
    CONTEXT,
    FILLED,
    PROPOSED,
    a_gate_in,
    block,
    finds_this_home,
    git,
    paths,
)
from test_jbus_kitchen import NOW, Kitchen, complete, iso
from test_jbus_queue import brief as queued
from testing.layouts import assembled
from testing.paths import REPO

TEMPLATE = REPO / "features" / "home" / "templates" / "gates.md"
ROOT = "mcp:the-root-home"
SCOPED = "mcp:the-scoped-home"
CREW = "mcp:crew-alpha"
SCOPE = "speed"
AT = "2026-10-12 11:30 ET"
HEARD = NOW + timedelta(minutes=30)
READS = "OPEN="
ASKED = "tea or coffee?"
ACTED = " Its default is acted on already, and stands unless you stop it."
DOOR = "deletes data"
SAFE = "the dry-run lists the 3 branches that go, bundle at ~/b.bundle"
REST = (
    "default: tea\nbuilt on it: the cups in pull request 7\nundo: pour it out: one revert\n"
    "acted on already: the default stands unless the user stops it"
)


def a_gate(question=ASKED, slug="alpha", holds="", **changed):
    """Return the template as the asking thread sends it, with every `<...>` placeholder filled
    in except `<n>`. With `holds`, it is a one-way door: its `Holds:` and `Fail-safe:` lines
    follow `Undo:`."""
    said = {
        "Asked by": f"{slug}, thread {CREW}",
        "Default": "tea",
        "Built on it": "the cups in pull request 7",
        "Undo": "pour it out: one revert",
        **changed,
    }
    lines = []
    for line in TEMPLATE.read_text().split("\n\n")[0].splitlines():
        label = line.split(":")[0]
        if line.startswith("## "):
            line = f"{label}: {question}"
        elif label in said:
            line = f"{label}: {said[label]}"
        if said.get(label, "") is not None:
            lines.append(line)
    if holds:
        lines += [f"Holds: {holds}", f"Fail-safe: {SAFE}"]
    return "\n".join(lines)


def whole(question=ASKED, slug="alpha", holds="", **changed):
    """Return a gate as jbus takes it: the template filled in, with its context and its options."""
    return f"{a_gate(question, slug, holds, **changed)}\n{CONTEXT}\n{PROPOSED}"


class Home:
    """`Home` is the kitchen's repo with a root home and a scoped one, and the skills as a user
    has them."""

    def __init__(self, tmp_path, monkeypatch):
        self.kitchen = Kitchen(tmp_path / "kitchen", monkeypatch)
        self.kitchen.clock_reads(AT)
        self.dir, self.main = self.kitchen.home, self.kitchen.checkout
        self.user = tmp_path / "user"
        (self.user / ".claude").mkdir(parents=True)
        (self.user / ".claude" / "skills").symlink_to(assembled() / "skills")
        (self.user / ".local" / "state").mkdir(parents=True)
        (self.user / ".local" / "state" / "home").symlink_to(self.dir.parent)
        (self.dir / "home-id").write_text(f"{ROOT}\n")
        (self.dir / SCOPE).mkdir()
        (self.dir / SCOPE / "plan.md").write_text("# a plan\n")
        (self.dir / SCOPE / "home-id").write_text(f"{SCOPED}\n")
        self.worktree = tmp_path / "trees" / "alpha"
        git(self.main, "worktree", "add", "-q", str(self.worktree))
        self.kitchen.brief("alpha", f"Thread: {CREW}\n")
        self.kitchen.quiet()
        self.env = {**os.environ, "HOME": str(self.user)}
        self.shown_dir = self.user / ".local" / "state" / "home" / self.dir.name

    def sh(self, text, cwd):
        ran = subprocess.run(
            ["sh", "-c", text], capture_output=True, text=True, env=self.env, cwd=cwd
        )
        assert ran.stderr == ""
        return ran.stdout.strip()

    def home(self, holding, thread=ROOT, cwd=None, **filled):
        """Run a block of the home skill, in one call with the three blocks that run before it."""
        found = block("home", holding)
        if FILLED in filled:
            found = a_gate_in(found, filled.pop(FILLED))
        for mark, text in filled.items():
            assert mark in found
            found = found.replace(mark, text)
        top = f"{paths('home')}\n{finds_this_home(thread)}\n{block('home', READS)}"
        return self.sh(f"{top}\n{found}", cwd or self.main)

    def pipes(self, skill="crew", question=ASKED, slug="alpha", holds=DOOR):
        """Pipe a gate the way a crewmate or a scout does: run the block of that role's own
        skill, in that role's worktree. It is a one-way door unless `holds` is empty."""
        sends = block(skill, "jbus gate '<slug>'")
        sends = a_gate_in(sends, a_gate(question, slug, holds)).replace("<slug>", slug)
        return self.sh(f"{paths(skill)}\n{sends}", self.worktree)

    def raised(self, question=ASKED, slug="alpha", project="demo"):
        """Keep a question with no `Holds:` line of a crew's row, as a pass raises one or as jbus
        kept one before such a gate was a decision."""
        return self.kitchen.raises(slug, whole(question, slug), project)

    def hears(self, number, which="--default"):
        """Answer a question with the user's own message in T3 Code, the one answer that closes a
        gate that holds."""
        at = iso(datetime.now(UTC))
        self.kitchen.t3.says(ROOT, f"said-{number}", f"to question {number}", updatedAt=at)
        argv = ("--as", "user", "answer", str(number), "--message", f"{ROOT}/said-{number}")
        return self.kitchen.main(*argv, which)

    def asks(self, thread=ROOT, entry=None, slug="own"):
        filled = {FILLED: entry or a_gate("which way?", "home"), "slug='own'": f"slug='{slug}'"}
        return self.home('jbus gate "$slug"', thread, **filled)

    def moves(self, thread=ROOT):
        return self.home("nothing to move: ", thread)

    def shown(self, thread=ROOT, **more):
        return self.home("no open questions", thread, **more)

    def closes(self, number, words, which="differs", by="user", at=None, thread=ROOT):
        """Run the home's block that answers a question. It runs jbus in a shell, on the
        machine's own clock, so the time it types is that clock's unless `at` says another."""
        filled = {
            "<number>": str(number),
            "<the user's name>": by,
            "<YYYY-MM-DD HH:MM ZONE>": at or jsettings.load().stamp(datetime.now(UTC)),
            "<default or differs>": which,
            "<the user's answer, in their words>": words,
        }
        return self.home("jbus answer", thread, **filled)

    def word(self, thread=ROOT, **more):
        return self.home("no word: ", thread, **more)

    def sends(self):
        return [given for tool, given in self.kitchen.t3.calls if tool == "t3_thread_send"]

    def records(self):
        return json.loads((self.kitchen.state / "questions.json").read_text())["records"]

    def files(self):
        return sorted(
            str(path.relative_to(self.dir)) for path in self.dir.rglob("*") if path.is_file()
        )


@pytest.fixture
def home(tmp_path, monkeypatch):
    made = Home(tmp_path, monkeypatch)
    yield made
    made.kitchen.close()


def test_the_template_is_a_gate_the_real_jbus_takes_with_every_line_of_it(home):
    assert home.kitchen.main("gate", "alpha", stdin=whole(holds=DOOR)) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    (kept,) = home.records()
    assert (kept["question"], kept["default"], kept["thread"]) == (ASKED, "tea", CREW)
    assert (kept["built_on"], kept["undo"]) == (
        "the cups in pull request 7",
        "pour it out: one revert",
    )
    assert (kept["holds"], kept["fail_safe"]) == (DOOR, SAFE)


@pytest.mark.parametrize("skill", ["crew", "scout"])
def test_a_piped_gate_leaves_its_number_as_the_one_line_to_keep(home, skill):
    assert home.pipes(skill).splitlines() == [
        "asked: queued: question 1",
        "Gate: question 1",
    ]
    assert home.pipes(skill).splitlines() == [
        "asked: already sent: question 1",
        "Gate: question 1",
    ]
    assert home.hears(1)[0] == 0
    said, kept = home.pipes(skill).splitlines()
    assert said.startswith("asked: already answered: question 1: ")
    assert kept == "Gate: question 1"


@pytest.mark.parametrize("skill", ["crew", "scout", "home"])
def test_the_context_and_the_options_a_skills_block_writes_are_kept_with_their_marks(home, skill):
    """The test uses the block's own `Context:` and `Option:` lines, filled in as the block
    writes them."""
    said = (home.asks() if skill == "home" else home.pipes(skill)).splitlines()[0]
    assert said.endswith("queued: question 1")
    (kept,) = home.records()
    assert kept["context"] == CONTEXT.removeprefix("Context: ")
    assert kept["options"] == [
        {"name": "tea", "follows": "the cups stay", "default": True, "recommended": True},
        {"name": "coffee", "follows": "the cups go back", "default": False, "recommended": False},
    ]


def test_a_gate_with_the_blocks_option_line_left_as_it_is_is_not_taken(home):
    sends = block("crew", "jbus gate '<slug>'").replace("<slug>", "alpha")
    said = home.sh(f"{paths('crew')}\n{sends.replace(FILLED, a_gate())}", home.worktree)
    assert said.startswith('not asked: not sent: the line "Option: <an option')
    assert not (home.kitchen.state / "questions.json").exists()


def test_a_home_reads_the_open_questions_from_jbus_and_writes_no_file(home):
    before = home.files()
    assert home.shown() == "no open questions"
    home.raised()
    home.kitchen.poll()
    assert home.shown() == f"question 1, from alpha: {ASKED}\n" + REST
    assert home.files() == before
    assert not list(home.dir.rglob("gates.md"))


def test_an_answer_that_differs_is_closed_by_jbus_and_carried_by_jbus_alone(home):
    home.raised()
    home.kitchen.poll()
    words = "no & don't: \"coffee\", it's $HOME \\n"
    at = jsettings.load().stamp(datetime.now(UTC))
    said = home.closes(1, words, at=at)
    assert said == (
        f'answered: question 1: "{words}", by user, {at}, in {home.main} (not the default): '
        "the next pass tells alpha's thread"
    )
    assert home.sends() == []
    (kept,) = home.records()
    assert (kept["answer"]["words"], kept["answer"]["by"], kept["answer"]["at"]) == (
        words,
        "user",
        at,
    )
    home.kitchen.poll()
    (sent,) = home.sends()
    assert sent["threadId"] == CREW
    assert words in sent["message"] and "pour it out: one revert" in sent["message"]
    assert home.shown() == "no open questions"
    home.kitchen.poll()
    assert len(home.sends()) == 1


def test_an_answer_that_is_the_default_closes_it_and_nobody_is_sent_anything(home):
    home.raised()
    said = home.closes(1, "yes\ntea", "default")
    assert said.startswith('answered: question 1: "yes tea", by user, ')
    assert said.endswith("(the default stands): nothing is sent")
    home.kitchen.poll()
    assert home.sends() == []
    assert home.shown() == "no open questions"


def test_a_second_answer_is_refused_with_the_first_and_changes_nothing(home):
    home.raised()
    home.closes(1, "coffee")
    before = home.records()
    said = home.closes(1, "tea after all", "default")
    assert said.startswith("not answered: jbus said: refused: question 1 was answered already: ")
    assert '"coffee", by user' in said
    assert home.closes(4, "tea").startswith("not answered: jbus said: refused: no question 4")
    assert home.records() == before


def test_a_refusal_names_what_the_block_is_to_be_given(home):
    home.raised()
    said = home.closes(1, "coffee", by="somebody")
    assert said == "not answered: jbus said: refused: only user answers a question, not somebody"
    said = home.closes(1, "coffee", at="yesterday")
    assert said == 'not answered: jbus said: refused: --at is "<YYYY-MM-DD HH:MM ET>"'
    assert home.closes(1, "coffee", which="<default or differs>").startswith(
        "not answered: say whether"
    )
    assert home.closes(1, "coffee", which="yes").startswith("not answered: say whether")
    assert home.records()[0]["answer"] is None


def test_a_homes_own_question_is_asked_under_its_own_slug_and_shown_to_it_alone(home):
    assert home.asks() == "asked: queued: question 1\nGate: question 1"
    assert home.asks() == "asked: already sent: question 1\nGate: question 1"
    assert (
        home.asks(SCOPED, a_gate("how fast?", "home"))
        == "asked: queued: question 2\nGate: question 2"
    )
    assert [one["slug"] for one in home.records()] == ["home", f"home-{SCOPE}"]
    home.kitchen.poll()
    assert home.shown() == "question 1, from home: which way?\n" + REST
    assert home.shown(SCOPED) == f"question 2, from home-{SCOPE}: how fast?\n" + REST
    said = home.closes(2, "faster", thread=SCOPED)
    assert said.endswith(
        f"home-{SCOPE} has no Thread: line in a brief or request, so no thread is told"
    )
    home.kitchen.poll()
    assert home.sends() == []


@pytest.mark.parametrize(
    ("entry", "said"),
    [
        (
            FILLED,
            "not asked: not sent: the first line is not '## Gate <n>: ' and the question.",
        ),
        (
            a_gate("which way?", "home", Default=None),
            "not asked: not sent: the gate has no Default: line that is filled in.",
        ),
    ],
)
def test_a_question_that_is_not_filled_in_is_not_asked(home, entry, said):
    assert home.asks(entry=entry) == said
    assert not (home.kitchen.state / "questions.json").exists()


def test_a_question_is_shown_to_the_home_of_the_brief_that_asked(home):
    home.kitchen.brief("beta", f"Home: {SCOPED}\nThread: mcp:crew-beta\n")
    home.kitchen.brief("gamma", f"Home: {ROOT}\n", kind="scouts")
    for slug in ("alpha", "beta", "gamma", "expert-style-no-rollback"):
        assert home.raised(f"from {slug}?", slug)[1]
    home.kitchen.poll()
    lines = home.shown().splitlines()[::5]
    assert lines == [
        "question 1, from alpha: from alpha?",
        "question 3, from gamma: from gamma?",
        "question 4, from expert-style-no-rollback: from expert-style-no-rollback?",
    ]
    assert home.shown(SCOPED) == "question 2, from beta: from beta?\n" + REST


def test_a_home_reads_the_questions_of_its_own_repos_project_and_no_other(home):
    side = home.kitchen.second()
    (side.home / "tasks" / "alpha.md").write_text("# alpha: a task\n")
    assert home.raised("theirs?", project="other")[1]
    home.raised()
    home.kitchen.poll()
    assert home.shown() == f"question 1, from alpha: {ASKED}\n" + REST
    (side.home / "home-id").write_text(f"{ROOT}\n")
    assert home.shown(cwd=side.checkout) == "question 1, from alpha: theirs?\n" + REST


def test_a_home_that_cannot_read_jbus_says_why_and_shows_no_question(home, tmp_path):
    home.raised()
    home.kitchen.poll()
    elsewhere = tmp_path / "code" / "elsewhere"
    elsewhere.mkdir(parents=True)
    git(elsewhere, "init", "-q")
    (home.dir.parent / "elsewhere").mkdir()
    (home.dir.parent / "elsewhere" / "home-id").write_text(f"{ROOT}\n")
    assert home.shown(cwd=elsewhere) == (
        "no project: jbus's config names no project for elsewhere, "
        "so it holds no question of this repo"
    )
    kept = home.kitchen.state / "questions.json"
    whole = kept.read_text()
    kept.write_text("not what jbus writes")
    assert home.shown() == f"jbus could not be read: {kept} is not the record jbus writes"
    kept.write_text(whole)
    assert home.shown() == f"question 1, from alpha: {ASKED}\n" + REST
    home.env["PATH"] = "/usr/bin:/bin"
    assert home.shown() == "no jbus: jbus is not installed here, so it holds no question"
    assert home.asks() == "not asked: jbus is not installed here"
    assert home.closes(1, "coffee") == "not answered: jbus is not installed here"


def test_a_word_jbus_carried_to_this_home_is_printed_with_its_words_and_time(home):
    assert home.word() == "no word: jbus carried none to this thread"
    said = home.kitchen.message("hold every merge", at=HEARD)
    code, went = home.kitchen.main("word", "--to", "demo", *said)
    assert (code, went.startswith(f"sent: demo, to {ROOT}, word ")) == (0, True)
    (sent,) = home.sends()
    assert sent["threadId"] == ROOT
    assert sent["message"].startswith(
        f"jbus: this is user's own word, said {AT} and carried to this home by jbus."
    )
    assert home.word() == f"user, {AT}: hold every merge"
    assert home.word(SCOPED) == "no word: jbus carried none to this thread"


def test_a_word_that_waits_or_went_to_another_project_is_not_this_homes(home):
    side = home.kitchen.second()
    (side.home / "home-id").write_text("mcp:their-home\n")
    ship, wait = (home.kitchen.message(words, at=HEARD) for words in ("ship it", "wait for me"))
    assert home.kitchen.main("word", "--to", "other", *ship)[0] == 0
    (home.dir / "home-id").write_text("")
    assert home.kitchen.main("word", "--to", "demo", *wait)[0] == 0
    (home.dir / "home-id").write_text(f"{ROOT}\n")
    assert home.word() == "no word: jbus carried none to this thread"
    home.kitchen.poll()
    assert home.word() == f"user, {AT}: wait for me"
    home.env["PATH"] = "/usr/bin:/bin"
    assert home.word() == "no jbus: jbus is not installed here, so it holds no question"


def old_file(home, where=None, gate=None):
    """Write a `gates.md` that an older home left. Its gates have no options, since no gate had
    options then. When `gate` is `whole`, the file's gates have the options that gates got later."""
    gate = gate or a_gate
    file = (where or home.dir) / "gates.md"
    done = gate("a closed one?").replace("<n>", "1").replace("Status: open", "Status: answered: no")
    left = gate("an old one?").replace("<n>", "2")
    mine = gate("the home's own?", "home").replace("<n>", "3")
    file.write_text(f"{done}\n\n{left}\n\n{mine}\n")
    return file, left, mine


def gates_listed(home):
    listed = json.loads((home.kitchen.state / "waiting-on-user.json").read_text())
    return sorted(one["line"] for one in listed if one["kind"] == "gate")


@pytest.mark.parametrize("thread", [ROOT, SCOPED])
def test_a_gate_an_older_home_left_in_a_file_is_moved_to_jbus_and_listed_once(home, thread):
    assert home.moves(thread) == "nothing to move: this home has no gates.md"
    own, where = ("home", home.dir) if thread == ROOT else (f"home-{SCOPE}", home.dir / SCOPE)
    file, _, _ = old_file(home, where, whole)
    before = file.read_text()
    shown = home.shown_dir / file.relative_to(home.dir)
    retired = shown.with_name("gates-moved.md")
    home.kitchen.poll()
    assert gates_listed(home) == ["gate 2: an old one?", "gate 3: the home's own?"]
    brief = home.kitchen.home / "tasks" / "alpha.md"
    assert home.moves(thread).splitlines() == [
        f"moved: gate 2 of {shown}, decided: written to {brief}: {questions.DECIDED_WHY}",
        f"moved: gate 3 of {shown}, queued: question 4",
        f"retired: {shown} is now {retired}, and jbus reads it no more",
    ]
    assert not file.exists() and retired.read_text() == before
    assert "## Decision: an old one?" in brief.read_text().splitlines()
    assert [(one["slug"], one["question"]) for one in home.records()] == [
        (own, "the home's own?"),
    ]
    assert home.shown(thread).splitlines()[::5][-1] == f"question 4, from {own}: the home's own?"
    home.kitchen.poll()
    assert gates_listed(home) == [f"question 4: the home's own?{ACTED}"]
    assert home.closes(4, "keep it", "default", thread=thread).startswith("answered: question 4: ")
    home.kitchen.poll()
    assert gates_listed(home) == []
    assert home.moves(thread) == "nothing to move: this home has no gates.md"


def test_a_gate_with_no_options_in_an_older_homes_file_is_not_moved_and_the_file_stays(home):
    file, left, mine = old_file(home)
    before = file.read_text()
    shown = home.shown_dir / "gates.md"
    said = home.moves()
    why = "jbus said: not sent: the gate has no Option: lines and needs two or more."
    assert f"not moved: gate 2 of {shown}, {why}" in said
    assert f"not moved: gate 3 of {shown}, {why}" in said
    assert left in said and mine in said
    assert said.splitlines()[-1] == f"kept: {shown}, with 2 open that jbus does not hold"
    assert file.read_text() == before
    assert not (home.kitchen.state / "questions.json").exists()


def test_a_gate_jbus_cannot_take_stays_in_the_file_and_is_printed_whole(home):
    file, left, mine = old_file(home, gate=whole)
    before = file.read_text()
    shown = home.shown_dir / "gates.md"
    home.kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=complete("alpha"))
    code, _ = home.kitchen.main("queue", "remove", "alpha", "--by", "user", "--at", AT)
    assert code == 0
    said = home.moves()
    assert said.startswith(f"not moved: gate 2 of {shown}, jbus said: refused: ")
    assert left in said and mine not in said
    assert f"moved: gate 3 of {shown}, queued: question " in said
    assert said.splitlines()[-1] == f"kept: {shown}, with 1 open that jbus does not hold"
    assert file.read_text() == before
    home.env["PATH"] = "/usr/bin:/bin"
    why = "no jbus: jbus is not installed here, so it holds no question"
    said = home.moves()
    assert f"not moved: gate 2 of {shown}, {why}:\n{left}" in said
    assert f"not moved: gate 3 of {shown}, {why}:\n{mine}" in said
    assert said.splitlines()[-1] == f"kept: {shown}, with 2 open that jbus does not hold"
    assert file.read_text() == before


def test_a_gate_another_thread_wrote_out_is_handed_to_jbus_under_that_threads_slug(home):
    assert home.pipes().splitlines()[0] == "asked: queued: question 1"
    written = a_gate(holds=DOOR).replace("<n>", "1")
    assert (
        home.asks(entry=written, slug="alpha")
        == "asked: already sent: question 1\nGate: question 1"
    )
    assert (
        home.asks(entry=a_gate("milk?", holds=DOOR), slug="alpha")
        == "asked: queued: question 2\nGate: question 2"
    )
    said = home.asks(entry=a_gate("sugar?"), slug="alpha")
    assert said.startswith("decided: written to ")
    assert [(one["slug"], one["thread"]) for one in home.records()] == [("alpha", CREW)] * 2
    assert home.hears(1)[0] == 0
    assert home.asks(entry=written, slug="alpha").startswith(
        "asked: already answered: question 1: "
    )


def test_a_question_closed_since_the_last_pass_is_not_shown_as_open(home):
    for question in ("one?", "two?", "three?"):
        assert home.raised(question)[1]
    home.kitchen.poll()
    home.closes(2, "yes", "default")
    assert home.shown().splitlines()[::5] == [
        "question 1, from alpha: one?",
        "question 3, from alpha: three?",
    ]
    home.closes(3, "no")
    assert home.shown() == "question 1, from alpha: one?\n" + REST


def test_a_scoped_homes_own_slug_is_its_own_whatever_brief_has_that_name(home):
    home.kitchen.brief(f"home-{SCOPE}", f"Home: {ROOT}\n")
    assert (
        home.asks(SCOPED, a_gate("how fast?", "home"))
        == "asked: queued: question 1\nGate: question 1"
    )
    home.kitchen.poll()
    assert home.shown() == "no open questions"
    assert home.shown(SCOPED) == f"question 1, from home-{SCOPE}: how fast?\n" + REST
    home.closes(1, "faster", thread=SCOPED)
    said = home.asks(SCOPED, a_gate("how fast?", "home"))
    assert said.startswith('asked: already answered: question 1: "faster", by user, ')


def on_the_users_list(kitchen):
    """Return every place a question of the project would wait on the user, after a pass: the
    records jbus keeps, the gates of the list and of `jbus needs`, the view's Needs you, and the
    `gate` and `waiting` events."""
    kitchen.poll()
    listed = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    _, needs = kitchen.main("needs")
    sources = view_state.Sources(kitchen.state_dir, kitchen.root / "home")
    stack = view_state.build(sources, "demo", NOW, lambda _: {})
    return {
        "records": questions.load(kitchen.state),
        "listed": [one["line"] for one in listed if one["kind"] == "gate"],
        "needs": [line for line in needs.splitlines() if "question" in line],
        "view": [one["key"] for one in stack["waiting"] if one["kind"] == "gate"],
        "events": [one["line"] for one in kitchen.events() if one["event"] in ("gate", "waiting")],
    }


NOTHING = {"records": [], "listed": [], "needs": [], "view": [], "events": []}


def decided(file, before):
    """Return the lines jbus added to `file`, with the time on the `Decided:` line cut off."""
    added = file.read_text().removeprefix(before).splitlines()
    *said, last = added
    stamp, by = last.split(", ", 1)
    assert stamp.startswith("Decided: ") and by == questions.DECIDED_BY
    return said


@pytest.mark.parametrize(("skill", "kind"), [("crew", "tasks"), ("scout", "scouts")])
def test_a_crews_or_a_scouts_gate_with_no_holds_line_is_a_decision_on_its_brief(home, skill, kind):
    """A gate with no `Holds:` line is no one-way door: jbus writes it to the brief or the request
    of the row as a decision, once, and nothing of it waits on the user."""
    slug = "alpha" if kind == "tasks" else "gamma"
    file = home.kitchen.brief(slug, f"Thread: {CREW}\n", kind=kind)
    before = file.read_text()
    said = f"written to {file}: {questions.DECIDED_WHY}"
    assert home.pipes(skill, slug=slug, holds="") == f"decided: {said}"
    assert home.pipes(skill, slug=slug, holds="") == f"decided: already {said}"
    assert decided(file, before) == [
        "",
        f"## Decision: {ASKED}",
        "Default: tea",
        "Built on it: the cups in pull request 7",
        "Undo: pour it out: one revert",
    ]
    assert on_the_users_list(home.kitchen) == NOTHING
    assert home.shown() == "no open questions"


def test_a_crews_gate_that_holds_is_asked_of_the_user_and_its_brief_is_not_written(home):
    file = home.kitchen.home / "tasks" / "alpha.md"
    before = file.read_text()
    assert home.pipes().splitlines() == ["asked: queued: question 1", "Gate: question 1"]
    assert file.read_text() == before
    shown = on_the_users_list(home.kitchen)
    assert [one.holds for one in shown["records"]] == [DOOR]
    assert shown["listed"] == [
        f"question 1: {ASKED} It holds ({DOOR}) for your answer, with its fail-safe: {SAFE}."
    ]
    assert shown["view"] == ["gate:q1"]
    assert shown["events"][0] == f"gate alpha: question 1: {ASKED}"


class Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


GO = (
    "## Gate <n>: start alpha?\nStatus: open\nAsked by: home, thread mcp:the-root-home\n"
    "Default: approve\nBuilt on it: nothing yet\nUndo: hold the row\n"
    "Option: start it (default, recommended): the row launches\nOption: wait: it waits\n"
)


def test_a_homes_go_gate_on_a_crews_row_waits_its_quiet_window_on_the_list(
    home, jstack_config, monkeypatch
):
    """A go gate carries the user's go, not a crew's choice: under `go = "silence"` it is a
    question, on the list for `go_quiet_minutes`, though the row's brief is in the home."""
    jstack_config.write_text(jstack_config.read_text() + 'go = "silence"\ngo_quiet_minutes = 30\n')
    monkeypatch.setattr(questions, "datetime", Frozen)
    code, said = home.kitchen.main(
        "queue", "add", "alpha", "--priority", "1", stdin=queued("alpha")
    )
    assert code == 0, said
    assert home.kitchen.main("gate", "alpha", stdin=GO) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    home.kitchen.poll(NOW + timedelta(minutes=29))
    listed = jbus.read_json(home.kitchen.state / "waiting-on-user.json", [])
    assert [one["key"] for one in listed if one["kind"] == "gate"] == ["gate:q1"]
    assert questions.question(home.kitchen.state, 1).answer is None
    home.kitchen.poll(NOW + timedelta(minutes=31))
    assert questions.question(home.kitchen.state, 1).answer.closed_by == questions.SILENCE


QUESTION_259 = """\
## Gate <n>: Should #1297 wait for #1292 to merge, rather than drop --message from the root's queue step to go green now?
Status: open
Asked by: rh-root-skill, thread mcp:crew-rh-root-skill
Default: #1297 waits; no rerun and no commit, and its check goes green once #1292 puts jbus queue add --message on main
Built on it: pull request 1297 at 138899afe90a, whose scoped-homes.md queue block passes --message
Undo: drop --message from the queue block in scoped-homes.md and its test, in one commit on #1297
Context: check 5 of 8 fails only test_docs_true[scoped-homes.md] because --message lands with #1292 (rh-approve-at-queue, open); a rerun fails the same way; https://github.com/JoshuaHayesWasHere/jstack/pull/1297
Option: wait for #1292 (default, recommended): the brief asks for the user's message at queue time, and the row already merges after rh-approve-at-queue
Option: drop --message now: #1297 goes green at once, and the root's queue step approves no row until a follow-up adds it back
"""  # noqa: E501


def test_question_259_a_crews_wait_on_another_pull_request_puts_nothing_on_the_users_list(home):
    """Question 259 of 2026-11-09, replayed: rh-root-skill's crew asked whether #1297 waits for
    #1292, with no `Holds:` line. jbus listed it and wrote a `waiting` event naming it before
    the next pass closed it with its default. It is a decision on the brief, and nothing more."""
    file = home.kitchen.brief("rh-root-skill", "Thread: mcp:crew-rh-root-skill\n")
    before = file.read_text()
    code, said = home.kitchen.main("gate", "rh-root-skill", stdin=QUESTION_259)
    assert (code, said) == (0, f"decided: written to {file}: {questions.DECIDED_WHY}\n")
    assert decided(file, before)[1:3] == [
        "## Decision: Should #1297 wait for #1292 to merge, rather than drop --message from the "
        "root's queue step to go green now?",
        "Default: #1297 waits; no rerun and no commit, and its check goes green once #1292 puts "
        "jbus queue add --message on main",
    ]
    assert on_the_users_list(home.kitchen) == NOTHING


RISKY = (
    "\n## Review\nBy: a reviewer #1\nVerdict: findings\nHead: {head}\nFindings:\n"
    "- warning src/alpha/a.py:3 the token is logged (bucket: Consider) (risk: auth)\n"
    "- warning src/alpha/b.py:9 a name says less than it could (bucket: Consider)\n"
)


def test_a_crews_decline_of_a_risk_tagged_finding_is_asked_and_any_other_is_a_decision(home):
    """A finding tagged `(risk: <area>)` is declined only on the user's answer, so a gate that
    names it by its id is asked, though it has no `Holds:` line; one that names another finding
    of the review is a decision."""
    file = home.kitchen.home / "tasks" / "alpha.md"
    file.write_text(file.read_text() + RISKY.format(head="a" * 40))
    asked = home.pipes(question="May F1 stay as it is?", holds="")
    assert asked.splitlines() == ["asked: queued: question 1", "Gate: question 1"]
    decided = home.pipes(question="May F2 stay as it is?", holds="")
    assert decided == f"decided: written to {file}: {questions.DECIDED_WHY}"
    assert [one.question for one in questions.load(home.kitchen.state)] == ["May F1 stay as it is?"]
