"""A home's turn ends with no message to the user unless it asks a decision or reports a stop
(S15, OnlyDecisionsReachOwner in the flow-blockers spec).

The home skill's "How a turn ends" gives the one block a home runs at the end of a turn that a
thread, jbus or an audit tick started. The home writes into it what the turn did, one line each,
and says to the user only what the block prints after `say:`. Each test takes that block from the
skill and runs it, in one call with the block at the top and the block that finds this home, as
the skill says. The day below is made up: it is the kinds of wake a home gets, not any day's text.

`DAY` has the flow-blockers ledger's shape: what woke the home (`josh` is an instruction from the
user, never a question), the tag the ledger gives such a turn (`D` is a decision of the user's,
every other tag is noise or an echo), and the lines the turn wrote into the block. Only the `D`
rows may reach the user.
"""

import pytest

from test_home_thread import THREAD, Scene, block

PLACEHOLDER = "<what this turn did, one line each>"
SILENT = "silent: end the turn with no message"

DAY = [
    ("sched", "N-sched", []),
    ("result", "N-result", ["merged: #41 tidy-docs", "launched: next-step, thread mcp:t2"]),
    ("result", "N-result", ["handled: tidy-notes ended with no pull request, its entry closed"]),
    ("jbus", "D", ["decision question 7: may the old flag stay? default: it stays"]),
    (
        "josh",
        "N-launch",
        ["launched: add-cache, thread mcp:t3", "launched: add-index, thread mcp:t4"],
    ),
    ("sched", "N-other", ["handled: slow-one was stuck two ticks, told to carry on"]),
    (
        "sched",
        "E-gate",
        [
            "decision question 7: may the old flag stay? default: it stays",
            "waits: #42 add-cache waits on its review",
        ],
    ),
    ("other", "N-result", ["parked: cache-ideas reported, its two briefs wait on the plan"]),
    ("josh", "N-ack", ["handled: the row of add-index is approved on the user's word"]),
    ("result", "D", ["decision local fix-two: keep the v1 route? default: it stays"]),
    ("jbus", "E-wake", ["handled: the user's word carried by jbus was already acted on"]),
    ("jbus", "D", ["stop jbus: demo: alert: webhook demo failed 3 times in a row since 10:00 ET"]),
    ("josh", "D", ["stop local next-step: no tool in this session starts a thread"]),
    ("result", "E-status", ["waits: #42 add-cache waits on its review"]),
    ("sched", "N-sched", []),
    ("result", "N-result", ["merged: #42 add-cache", "handled: the planned work is done"]),
]


class Turns(Scene):
    """A home's state directory, and the home whose thread is `THREAD`."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.file.write_text(f"{THREAD}\n")

    def end(self, lines):
        """Run the end of a turn that did `lines`, and return what the block printed."""
        ends = block("home", PLACEHOLDER)
        ran = self.run("home", ends.replace(PLACEHOLDER, "\n".join(lines)), self.main, THREAD)
        return ran.returncode, ran.stdout.splitlines()


@pytest.fixture
def turns(tmp_path):
    return Turns(tmp_path)


def test_a_day_of_wakes_reaches_the_user_only_on_its_decision_rows(turns):
    reached = []
    for at, (trigger, tag, lines) in enumerate(DAY):
        code, said = turns.end(lines)
        assert code == 0, (trigger, tag, said)
        if said == [SILENT]:
            continue
        reached.append(at)
        assert said == [f"say: {line}" for line in lines if line.split()[0] in ("decision", "stop")]
    assert reached == [at for at, (_, tag, _) in enumerate(DAY) if tag == "D"]


def test_a_decision_is_told_once_and_a_later_turn_that_has_it_again_is_silent(turns):
    asked = "decision question 9: may the flag go? default: it goes"
    assert turns.end([asked]) == (0, [f"say: {asked}"])
    reworded = "decision question 9: the flag, may it go? default: it goes"
    assert turns.end([reworded, "merged: #50 fix-login"]) == (0, [SILENT])
    other = "decision question 10: and the old route? default: it stays"
    assert turns.end([asked, other]) == (0, [f"say: {other}"])


def test_an_event_jbus_carried_is_told_once_by_its_whole_line(turns):
    alert = "stop jbus: demo: alert: webhook demo failed 3 times in a row since 10:00 ET"
    assert turns.end([alert]) == (0, [f"say: {alert}"])
    assert turns.end([alert]) == (0, [SILENT])
    again = alert.replace("10:00", "16:40")
    assert turns.end([again]) == (0, [f"say: {again}"])


def test_a_stop_and_a_decision_in_one_turn_are_both_told_in_their_order(turns):
    lines = [
        "merged: #51 tidy-docs",
        "stop local tidy-docs: jbus is not installed here, so no question can be asked",
        "decision local tidy-docs: keep the old page? default: it goes",
    ]
    assert turns.end(lines) == (0, [f"say: {line}" for line in lines[1:]])


KINDS = "its kind is none of decision, stop, merged, launched, handled, parked, waits"
KEYS = "a decision or a stop names its key first: question <n>, jbus or local <slug>"


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("Merged #41, launched next-step.", KINDS),
        ("merged #41 tidy-docs", KINDS),
        ("question 7: may the flag go?", KINDS),
        (PLACEHOLDER, KINDS),
        ("decision: may the flag go? default: it goes", KEYS),
        ("decision fix-login: may the flag go? default: it goes", KEYS),
        ("stop: the merge is stuck", KEYS),
    ],
)
def test_a_line_the_block_cannot_read_is_refused_and_nothing_is_marked_told(turns, line, why):
    asked = "decision question 11: may it go? default: it goes"
    assert turns.end([asked, line]) == (2, [f"refused: {line}: {why}"])
    assert turns.end([asked]) == (0, [f"say: {asked}"])


def test_each_home_keeps_what_it_told_apart(turns):
    asked = "decision question 12: may it go? default: it goes"
    assert turns.end([asked]) == (0, [f"say: {asked}"])
    scope = turns.home_dir / "speed"
    scope.mkdir()
    (scope / "plan.md").write_text("# a plan\n")
    (scope / "home-id").write_text("mcp:the-scoped-home\n")
    ends = block("home", PLACEHOLDER).replace(PLACEHOLDER, asked)
    ran = turns.run("home", ends, turns.main, "mcp:the-scoped-home")
    assert ran.stdout.splitlines() == [f"say: {asked}"]
