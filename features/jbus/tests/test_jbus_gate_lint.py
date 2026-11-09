"""`jbus gate` asks nothing a rule already settles, and takes no default that waits for the
user's word, since a pass closes a gate with no `Holds:` line at once and nobody is left to give
that word. A gate that holds is asked as before, whatever its shape.

The tests run the real `jbus gate` against the kitchen of `test_jbus_kitchen`, and read what it
printed and the questions it kept. Each shape of `SHAPES` is a gate the audit of 2026-10-26 to
11-01 found asked, in its words, with the rule that settles it and what the thread does instead,
as the refusal must name them."""

import json

import pytest

from test_jbus_kitchen import Kitchen

THREAD = "mcp:crew-alpha"
OPTIONS = "Option: the first (default, recommended): nothing changes\nOption: the other: it does\n"
SAFE = "Holds: deletes data\nFail-safe: the dry-run in /tmp/gone.txt\n"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.brief("alpha", f"Thread: {THREAD}\n")
    made.quiet()
    yield made
    made.close()


def lines(asked, default="the first", holds=""):
    return (
        f"## Gate <n>: {asked}\nStatus: open\nAsked by: alpha, thread {THREAD}\n"
        f"Default: {default}\nBuilt on it: the branch alpha\nUndo: one revert\n{holds}{OPTIONS}"
    )


def kept(kitchen):
    found = kitchen.state / "questions.json"
    return json.loads(found.read_text())["records"] if found.exists() else []


SHAPES = {
    "swarm": (
        "Run /swarm over the fourteen walk findings, as the request's Skills line names it?",
        "no swarm; this scout researched all fourteen in one thread with three Explore subagents",
        "features/arena-swarm/skills/swarm/SKILL.md",
        "do the work in this thread",
    ),
    "Review: none": (
        "alpha: https://example.com/o/r/pull/9 is green and has no review (the brief says "
        "Review: none): may it merge?",
        "the pull request waits, as a draft",
        "REVIEW_NONE",
        "write the Result's Reviewer: none line",
    ),
    "exit 124": (
        "make check-fast at 1e4837d3 stopped at the short lane's 120 s limit (exit 124, lint "
        "passed, no test failed): write Fixed: on CI's check instead?",
        "no Fixed: line yet; the pull request waits",
        "features/crew/do-the-task.md",
        "treat the 124 as a failure",
    ),
    "merge base": (
        "#415 was moved onto main, but #404 under it merged into train/macos: should #415's base "
        "be train/macos?",
        "#415 waits on its base main, not rebased onto it",
        "features/jmerge/src/jmerge/rows.py",
        "open or keep the pull request on the base",
    ),
    "cross-cutting": (
        "may #585 carry the cross-cutting label, which its borders check asks for?",
        "the label is not added, and #585 waits with its borders check red",
        "features/crew/do-the-task.md",
        "gh pr edit --add-label cross-cutting",
    ),
    "a red that is its base's": (
        "#580's browser run is red only on main's overview test, which #576 fixes: does #580 wait "
        "for #576?",
        "#580 waits for #576 to merge, then rebases",
        "features/jmerge/docs/jmerge.md",
        "carry no fix of it here",
    ),
}


@pytest.mark.parametrize("shape", SHAPES)
def test_a_gate_a_rule_settles_is_not_asked_and_says_the_rule_and_what_to_do(kitchen, shape):
    asked, default, rule, do = SHAPES[shape]
    code, said = kitchen.main("gate", "alpha", stdin=lines(asked, default))
    assert code == 1
    assert said.startswith(f"not asked: settled: {shape}: ")
    assert rule in said
    assert do in said
    assert kept(kitchen) == []


def test_exit_124_never_passes(kitchen):
    """The desk check is the guards alone, in a full slot, and jmerge holds a pull request whose
    last `Checked:` line ends 124: the answer must not tell the thread to go on past a 124 as on
    exit 0."""
    asked, default, _, _ = SHAPES["exit 124"]
    _, said = kitchen.main("gate", "alpha", stdin=lines(asked, default))
    assert "an exit 124 never passes" in said
    assert "short_on_checked" in said
    assert "PART=guards exit 0" in said
    assert "as on exit 0" not in said


@pytest.mark.parametrize(
    "asked",
    (
        "Should the swarm skill's default fan-out be 4 or 8?",
        "Which base model should the benchmark use?",
        "Should the Cross-cutting tests stay in the quick list?",
    ),
)
def test_a_choice_that_only_names_a_shapes_word_is_not_refused(kitchen, asked):
    """No rule settles it, so jbus takes it: from a crew's row with no `Holds:` line, as a
    decision on the brief."""
    code, said = kitchen.main("gate", "alpha", stdin=lines(asked))
    assert (code, said.startswith("decided: written to ")) == (0, True), said


@pytest.mark.parametrize("shape", SHAPES)
def test_a_gate_that_holds_is_asked_whatever_its_shape(kitchen, shape):
    asked, default, _, _ = SHAPES[shape]
    code, said = kitchen.main("gate", "alpha", stdin=lines(asked, default, SAFE))
    assert (code, said.splitlines()[0]) == (0, "asked: queued: question 1")
    assert [one["holds"] for one in kept(kitchen)] == ["deletes data"]


WAITS = (
    "the pull request waits, unmerged, for the user's word",
    "no Fixed: line is written, so #525 stays a draft and waits for your word",
    "merge PR #1 as it stands once your word is recorded",
    "the pull request waits for the user to merge it",
    "the pull request waits, unmerged, for Josh's go-ahead",
)


@pytest.mark.parametrize("default", WAITS)
def test_a_default_that_waits_for_the_users_word_is_not_sent(kitchen, default):
    code, said = kitchen.main("gate", "alpha", stdin=lines("tea or coffee?", default))
    assert code == 1
    assert said.startswith("not asked: not sent: the Default: line waits for the user's word")
    assert "Holds:" in said
    assert kept(kitchen) == []


@pytest.mark.parametrize("default", WAITS)
def test_a_default_that_waits_for_the_users_word_and_holds_is_asked(kitchen, default):
    code, said = kitchen.main("gate", "alpha", stdin=lines("tea or coffee?", default, SAFE))
    assert (code, said.splitlines()[0]) == (0, "asked: queued: question 1")
    assert [one["default"] for one in kept(kitchen)] == [default]


@pytest.mark.parametrize(
    "default",
    (
        "#580 waits for #576 to merge, then rebases",
        "keep the draft; the owner's last word on gate 62 said so",
        "made tea, and the cups wait in the kitchen",
        "the pull request waits for CI's answer",
        "wait once GitHub's merge lands",
    ),
)
def test_a_default_that_waits_on_anything_but_the_users_word_is_not_refused(kitchen, default):
    code, said = kitchen.main("gate", "alpha", stdin=lines("tea or coffee?", default))
    assert (code, said.startswith("decided: written to ")) == (0, True), said
