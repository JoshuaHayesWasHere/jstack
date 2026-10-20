"""A question only the user can answer is one numbered record in jbus, and a home keeps no
copy of it: it reads the open ones from jbus, runs `jbus answer` with the user's words, and
takes a word `jbus word` carried as theirs.

The home skill's blocks are lifted from the skill and run as it says to run them, against the
real `jbus` in the temporary state directory of `test_jbus`'s kitchen. The passes are the
real ones, against its faked T3 Code server. Nothing reaches the network."""

import json
import os
import re
import subprocess

import pytest

from test_grill_page import page
from test_home_thread import (
    CONTEXT,
    FILLED,
    PROPOSED,
    REPO,
    a_gate_in,
    block,
    finds_this_home,
    git,
    paths,
)
from test_jbus_kitchen import Kitchen, complete

TEMPLATE = REPO / "templates" / "gates.md"
ROOT = "mcp:the-root-home"
SCOPED = "mcp:the-scoped-home"
CREW = "mcp:crew-alpha"
SCOPE = "speed"
AT = "2026-10-12 11:30 ET"
POLLED = "<what the poll printed>"
READS = "OPEN="
ASKED = "tea or coffee?"
ACTED = " Its default is acted on already, and stands unless you stop it."
REST = (
    "default: tea\nbuilt on it: the cups in pull request 7\nundo: pour it out: one revert\n"
    "acted on already: the default stands unless the user stops it"
)


def a_gate(question=ASKED, slug="alpha", **changed):
    """The template filled in as the asking thread sends it: every `<...>` but `<n>`."""
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
    return "\n".join(lines)


def whole(question=ASKED, slug="alpha", **changed):
    """A gate as jbus takes it: the template filled in, with its context and its options."""
    return f"{a_gate(question, slug, **changed)}\n{CONTEXT}\n{PROPOSED}"


class Home:
    """The kitchen's repo with a root home and a scoped one, and the skills as a user has them."""

    def __init__(self, tmp_path, monkeypatch):
        self.kitchen = Kitchen(tmp_path / "kitchen", monkeypatch)
        self.dir, self.main = self.kitchen.home, self.kitchen.checkout
        self.user = tmp_path / "user"
        (self.user / ".claude").mkdir(parents=True)
        (self.user / ".claude" / "skills").symlink_to(REPO / "skills")
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
        """A block of the home skill, in one call with the three blocks it is run after."""
        found = block("home", holding)
        if FILLED in filled:
            found = a_gate_in(found, filled.pop(FILLED))
        for mark, text in filled.items():
            assert mark in found
            found = found.replace(mark, text)
        top = f"{paths('home')}\n{finds_this_home(thread)}\n{block('home', READS)}"
        return self.sh(f"{top}\n{found}", cwd or self.main)

    def pipes(self, skill="crew", question=ASKED, slug="alpha"):
        """A crewmate or a scout pipes a gate by its own skill's block, from its worktree."""
        sends = block(skill, "jbus gate '<slug>'")
        sends = a_gate_in(sends, a_gate(question, slug)).replace("<slug>", slug)
        return self.sh(f"{paths(skill)}\n{sends}", self.worktree)

    def asks(self, thread=ROOT, entry=None, slug="own"):
        filled = {FILLED: entry or a_gate("which way?", "home"), "slug='own'": f"slug='{slug}'"}
        return self.home('echo "asked: ', thread, **filled)

    def moves(self, thread=ROOT):
        return self.home("nothing to move: ", thread)

    def shown(self, thread=ROOT, **more):
        return self.home("no open questions", thread, **more)

    def closes(self, number, words, which="differs", by="user", at=AT, thread=ROOT):
        filled = {
            "<number>": str(number),
            "<the user's name>": by,
            "<YYYY-MM-DD HH:MM ZONE>": at,
            "<default or differs>": which,
            "<the user's answer, in their words>": words,
        }
        return self.home("jbus answer", thread, **filled)

    def round(self, thread=ROOT):
        return self.home("round written: ", thread)

    def answers(self, polled):
        return self.home(POLLED, **{POLLED: polled})

    def word(self, thread=ROOT, **more):
        return self.home("no word: ", thread, **more)

    def make_page(self, slug):
        """Step 1 of the grilling skill's "On a page", with the slug the home skill gives."""
        (top,) = [text for text in [paths("grilling")] if text]
        make = block("grilling", 'cp "$T/grill-page.html"')
        stub = self.user / "bin" / "lavish-axi"
        stub.parent.mkdir(exist_ok=True)
        stub.write_text("#!/bin/sh\n")
        stub.chmod(0o755)
        env = {**self.env, "PATH": f"{stub.parent}{os.pathsep}{self.env['PATH']}"}
        text = f"{top}\n{make}".replace("<slug>", slug)
        subprocess.run(["sh", "-c", text], env=env, cwd=self.main, check=True)
        return self.shown_dir / "reports" / f"grill-{slug}.html"

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


def polled(sent):
    """What `lavish-axi poll` prints for a prompt the page sent: one row, the prompt quoted."""
    (_, text, options), _ = sent
    whole = text + "\n\nContext data:\n" + json.dumps(options["data"], indent=2)
    return (
        "session:\n  file: /tmp/grill-gates.html\n  status: feedback\n"
        "prompts[1]{uid,prompt,selector,tag,text}:\n"
        f'  "1",{json.dumps(whole, ensure_ascii=False)},button#send,round,"Round 1: 2 answers"\n'
        'next_step: "Apply the requested changes to /tmp/grill-gates.html."'
    )


def test_the_template_is_a_gate_the_real_jbus_takes_with_every_line_of_it(home):
    assert home.kitchen.main("gate", "alpha", stdin=whole()) == (0, "queued: question 1\n")
    (kept,) = home.records()
    assert (kept["question"], kept["default"], kept["thread"]) == (ASKED, "tea", CREW)
    assert (kept["built_on"], kept["undo"]) == (
        "the cups in pull request 7",
        "pour it out: one revert",
    )


@pytest.mark.parametrize("skill", ["crew", "scout"])
def test_a_piped_gate_leaves_its_number_as_the_one_line_to_keep(home, skill):
    assert home.pipes(skill).splitlines() == [
        "sent to jbus: queued: question 1",
        "Gate: question 1",
    ]
    assert home.pipes(skill).splitlines() == [
        "sent to jbus: already sent: question 1",
        "Gate: question 1",
    ]
    home.closes(1, "tea is fine", "default")
    said, kept = home.pipes(skill).splitlines()
    assert said.startswith("sent to jbus: already answered: question 1: ")
    assert kept == "Gate: question 1"


@pytest.mark.parametrize("skill", ["crew", "scout", "home"])
def test_the_context_and_the_options_a_skills_block_writes_are_kept_with_their_marks(home, skill):
    """The block's own `Context:` and `Option:` lines, filled in as it writes them."""
    said = home.asks() if skill == "home" else home.pipes(skill).splitlines()[0]
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
    assert said.startswith('not sent: the line "Option: <an option')
    assert not (home.kitchen.state / "questions.json").exists()


def test_a_home_reads_the_open_questions_from_jbus_and_writes_no_file(home):
    before = home.files()
    assert home.shown() == "no open questions"
    home.pipes()
    home.kitchen.poll()
    assert home.shown() == f"question 1, from alpha: {ASKED}\n" + REST
    assert home.files() == before
    assert not list(home.dir.rglob("gates.md"))


def test_an_answer_that_differs_is_closed_by_jbus_and_carried_by_jbus_alone(home):
    home.pipes()
    home.kitchen.poll()
    words = "no & don't: \"coffee\", it's $HOME \\n"
    said = home.closes(1, words)
    assert said == (
        f'answered: question 1: "{words}", by user, {AT}, in {home.main} (not the default): '
        "the next pass tells alpha's thread"
    )
    assert home.sends() == []
    (kept,) = home.records()
    assert (kept["answer"]["words"], kept["answer"]["by"], kept["answer"]["at"]) == (
        words,
        "user",
        AT,
    )
    home.kitchen.poll()
    (sent,) = home.sends()
    assert sent["threadId"] == CREW
    assert words in sent["message"] and "pour it out: one revert" in sent["message"]
    assert home.shown() == "no open questions"
    home.kitchen.poll()
    assert len(home.sends()) == 1


def test_an_answer_that_is_the_default_closes_it_and_nobody_is_sent_anything(home):
    home.pipes()
    said = home.closes(1, "yes\ntea", "default")
    assert said.startswith('answered: question 1: "yes tea", by user, ')
    assert said.endswith("(the default stands): nothing is sent")
    home.kitchen.poll()
    assert home.sends() == []
    assert home.shown() == "no open questions"


def test_a_second_answer_is_refused_with_the_first_and_changes_nothing(home):
    home.pipes()
    home.closes(1, "coffee")
    before = home.records()
    said = home.closes(1, "tea after all", "default")
    assert said.startswith("not answered: jbus said: refused: question 1 was answered already: ")
    assert '"coffee", by user' in said
    assert home.closes(4, "tea").startswith("not answered: jbus said: refused: no question 4")
    assert home.records() == before


def test_a_refusal_names_what_the_block_is_to_be_given(home):
    home.pipes()
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
    assert home.asks() == "asked: queued: question 1"
    assert home.asks() == "asked: already sent: question 1"
    assert home.asks(SCOPED, a_gate("how fast?", "home")) == "asked: queued: question 2"
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
            "not asked: jbus said: not sent: the first line is not '## Gate <n>: ' and the "
            "question.",
        ),
        (
            a_gate("which way?", "home", Default=None),
            "not asked: jbus said: not sent: the gate has no Default: line that is filled in.",
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
        code, _ = home.kitchen.main("gate", slug, stdin=whole(f"from {slug}?", slug))
        assert code == 0
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
    code, _ = home.kitchen.main("--project", "other", "gate", "alpha", stdin=whole("theirs?"))
    assert code == 0
    home.pipes()
    home.kitchen.poll()
    assert home.shown() == f"question 1, from alpha: {ASKED}\n" + REST
    (side.home / "home-id").write_text(f"{ROOT}\n")
    assert home.shown(cwd=side.checkout) == "question 1, from alpha: theirs?\n" + REST


def test_a_home_that_cannot_read_jbus_says_why_and_shows_no_question(home, tmp_path):
    home.pipes()
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
    assert home.round() == "no page: no jbus: jbus is not installed here, so it holds no question"
    assert home.asks() == "not asked: jbus is not installed here"
    assert home.closes(1, "coffee") == "not answered: jbus is not installed here"


def three_asked_one_answered(home):
    for question, took in (
        ("Keep the old column?", 'kept "both" columns, in `users`: né'),
        ("Ship behind a flag?", "yes"),
        ("Rename the table?", "left it\\as is"),
    ):
        entry = whole(question, Default=took)
        assert home.kitchen.main("gate", "alpha", stdin=entry)[0] == 0
    home.closes(2, "yes", "default")
    home.kitchen.poll()


def test_two_open_questions_are_one_round_of_the_grill_page_and_its_answers_close_them(home):
    three_asked_one_answered(home)
    assert home.round().endswith("make it first with gates-3 as the slug")
    made = home.make_page("gates-3")
    template = made.read_text()
    assert home.round() == f"round written: 2 questions, in {made}"
    data = '<script type="application/json" id="round-data">'
    assert made.read_text().split(data)[0] == template.split(data)[0]
    assert made.read_text().split("</script>", 1)[1] == template.split("</script>", 1)[1]

    picks = [{"id": "gate-3", "option": "other", "note": "drop it"}]
    drawn = page(round_=None, picks=picks, template=made)
    assert drawn["problems"] == []
    assert drawn["checked"] == {"1:gate-1": ["default"], "1:gate-3": ["default"]}
    first, third = drawn["cards"]
    assert "Keep the old column?" in first and 'Yes: kept "both" columns, in users: né' in first
    assert "Asked by alpha" in first
    assert "Built onthe cups in pull request 7" in first
    assert "Undopour it out: one revert" in first
    assert "Rename the table?" in third and "Yes: left it\\as is" in third

    said = home.answers(polled(drawn["calls"]))
    assert said == (
        "question 1: default: the default, picked on the page\nquestion 3: differs: drop it"
    )
    for line in said.splitlines():
        number, which, words = re.fullmatch(r"question (\d+): (\w+): (.*)", line).groups()
        assert home.closes(number, words, which).startswith(f"answered: question {number}: ")
    home.kitchen.poll()
    assert home.shown() == "no open questions"
    (sent,) = home.sends()
    assert sent["threadId"] == CREW and "drop it" in sent["message"]


def test_a_scoped_homes_round_has_a_page_of_its_own(home):
    for question in ("how fast?", "how far?"):
        assert home.asks(SCOPED, a_gate(question, "home")).startswith("asked: queued: ")
    home.kitchen.poll()
    slug = f"gates-{SCOPE}-2"
    assert home.round(SCOPED).endswith(f"make it first with {slug} as the slug")
    made = home.make_page(slug)
    assert home.round(SCOPED) == f"round written: 2 questions, in {made}"
    assert f'"slug": "{slug}"' in made.read_text()
    assert home.round() == "no page: 0 open, and fewer than two are text"


def test_one_open_question_stays_text_and_a_page_with_no_round_block_is_left_alone(home):
    three_asked_one_answered(home)
    made = home.make_page("gates-3")
    made.write_text("<html>reflowed by hand</html>\n")
    assert home.round() == f"no page: {made} has no round-data block to write the round into"
    assert made.read_text() == "<html>reflowed by hand</html>\n"
    assert sorted(path.name for path in made.parent.iterdir()) == [made.name]
    home.closes(3, "no")
    home.kitchen.poll()
    assert home.round() == "no page: 1 open, and fewer than two are text"


def test_a_note_on_the_default_is_its_own_kind_and_no_note_on_another_closes_nothing(home):
    three_asked_one_answered(home)
    made = home.make_page("gates-3")
    home.round()
    picks = [{"id": "gate-1", "note": 'no, drop "both"'}, {"id": "gate-3", "option": "other"}]
    sent = page(round_=None, picks=picks, template=made)["calls"]
    said = home.answers(polled(sent))
    assert home.answers(sent[0][1]) == said
    assert said.splitlines()[0] == 'question 1: noted: no, drop "both"'
    assert said.splitlines()[1].startswith("question 3: open: ")
    assert home.answers("status: feedback").startswith("no answers: ")


def test_a_word_jbus_carried_to_this_home_is_printed_with_its_words_and_time(home):
    assert home.word() == "no word: jbus carried none to this thread"
    said = ("--by", "user", "--at", AT, "hold", "every", "merge")
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
    said = ("--by", "user", "--at", AT)
    assert home.kitchen.main("word", "--to", "other", *said, "ship", "it")[0] == 0
    (home.dir / "home-id").write_text("")
    assert home.kitchen.main("word", "--to", "demo", *said, "wait", "for", "me")[0] == 0
    (home.dir / "home-id").write_text(f"{ROOT}\n")
    assert home.word() == "no word: jbus carried none to this thread"
    home.kitchen.poll()
    assert home.word() == f"user, {AT}: wait for me"
    home.env["PATH"] = "/usr/bin:/bin"
    assert home.word() == "no jbus: jbus is not installed here, so it holds no question"


def old_file(home, where=None, gate=None):
    """A `gates.md` an older home left: its gates have no options, as none had. With
    `whole` for `gate`, one whose gates were given their options since."""
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
    assert home.moves(thread).splitlines() == [
        f"moved: gate 2 of {shown}, queued: question 4",
        f"moved: gate 3 of {shown}, queued: question 5",
        f"retired: {shown} is now {retired}, and jbus reads it no more",
    ]
    assert not file.exists() and retired.read_text() == before
    assert [(one["slug"], one["question"]) for one in home.records()] == [
        ("alpha", "an old one?"),
        (own, "the home's own?"),
    ]
    assert home.shown(thread).splitlines()[::5][-1] == f"question 5, from {own}: the home's own?"
    home.kitchen.poll()
    assert gates_listed(home) == [
        f"question 4: an old one?{ACTED}",
        f"question 5: the home's own?{ACTED}",
    ]
    assert home.closes(5, "keep it", "default", thread=thread).startswith("answered: question 5: ")
    home.kitchen.poll()
    assert gates_listed(home) == [f"question 4: an old one?{ACTED}"]
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
    assert home.pipes().splitlines()[0] == "sent to jbus: queued: question 1"
    written = a_gate().replace("<n>", "1")
    assert home.asks(entry=written, slug="alpha") == "asked: already sent: question 1"
    assert home.asks(entry=a_gate("milk?"), slug="alpha") == "asked: queued: question 2"
    assert [(one["slug"], one["thread"]) for one in home.records()] == [("alpha", CREW)] * 2
    home.closes(1, "tea", "default")
    assert home.asks(entry=written, slug="alpha").startswith(
        "asked: already answered: question 1: "
    )


def test_a_question_closed_since_the_last_pass_is_not_shown_as_open(home):
    for question in ("one?", "two?", "three?"):
        assert home.kitchen.main("gate", "alpha", stdin=whole(question))[0] == 0
    home.kitchen.poll()
    home.closes(2, "yes", "default")
    assert home.shown().splitlines()[::5] == [
        "question 1, from alpha: one?",
        "question 3, from alpha: three?",
    ]
    home.closes(3, "no")
    assert home.shown() == "question 1, from alpha: one?\n" + REST
    assert home.round() == "no page: 1 open, and fewer than two are text"


def test_a_links_conflict_asks_the_home_and_is_on_no_round(home, tmp_path):
    url = "https://example.test/pull/7"
    link = f"alpha: {url} has a conflict, and it is a link of a stack"
    for question in ("one?", link):
        assert home.kitchen.main("gate", "alpha", stdin=whole(question))[0] == 0
    says = tmp_path / "gh-says"
    stub = tmp_path / "gh-bin" / "gh"
    stub.parent.mkdir()
    stub.write_text(
        f'#!/bin/sh\n[ "$3" = "{url}" ] || exit 1\njq -r \'"\\(.state) \\(.mergeable)"\' "{says}"\n'
    )
    stub.chmod(0o755)
    home.env["PATH"] = f"{stub.parent}{os.pathsep}{home.env['PATH']}"
    ours = "for this home, question 2, from alpha: "
    assert home.shown().splitlines() == [
        "question 1, from alpha: one?",
        *REST.splitlines(),
        f"{ours}could not ask GitHub about {url}",
    ]
    says.write_text('{"state": "OPEN", "mergeable": "CONFLICTING"}')
    assert home.shown().splitlines()[-1] == f"{ours}send its line, {url} has a conflict"
    assert home.round() == "no page: 1 open, and fewer than two are text"
    home.closes(1, "yes", "default")
    says.write_text('{"state": "OPEN", "mergeable": "MERGEABLE"}')
    assert home.shown() == (
        f"{ours}handled, {url} is OPEN MERGEABLE, "
        "and the question is the user's to close as default"
    )
    home.closes(2, "handled", "default")
    assert home.shown() == "no open questions"


def test_a_scoped_homes_own_slug_is_its_own_whatever_brief_has_that_name(home):
    home.kitchen.brief(f"home-{SCOPE}", f"Home: {ROOT}\n")
    assert home.asks(SCOPED, a_gate("how fast?", "home")) == "asked: queued: question 1"
    home.kitchen.poll()
    assert home.shown() == "no open questions"
    assert home.shown(SCOPED) == f"question 1, from home-{SCOPE}: how fast?\n" + REST
    home.closes(1, "faster", thread=SCOPED)
    said = home.asks(SCOPED, a_gate("how fast?", "home"))
    assert said.startswith('asked: already answered: question 1: "faster", by user, ')
