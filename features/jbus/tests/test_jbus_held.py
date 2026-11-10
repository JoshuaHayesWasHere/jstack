"""A hold nobody works on wakes its home (fl-hold-wakes). Rows whose pull requests `jmerge` holds
on one reason for longer than `clock.HOLD_MINUTES`, with no thread at work on the cause, wake the
home that owns the rows once, and the hold is on what waits on the user until it clears or a
thread takes it up. The tests replay small made-up rows through the real pass against the
kitchen's fakes. A hold's age is minutes since a pass first saw it, not passes, so a pass at each
minute a test reads stands for one a minute."""

from datetime import timedelta

import pytest

import jbus
from jbus import clock, stall, work
from jmerge import judgement, ready
from test_jbus_expedite import Short, host_unread, later
from test_jbus_expedite_result import PROVED_MISSING
from test_jbus_kitchen import NOW, sends
from test_jbus_leftover import home
from test_jbus_needs import needs

pytestmark = pytest.mark.usefixtures(host_unread.__name__)
"""What a pass reads of the machine is none of what these tests assert
(`test_jbus_expedite.host_unread`)."""

ROWS = ("one", "two", "three", "four")
SHA = "abcdef123456"
REASON = ready.NO_RUN.format(check="check", head=SHA)
RESULT = "\n## Result\nStatus: done\nBranch: {slug}   Pull request: {url}\nLeft: none\n"


def url(number):
    return f"https://example.test/pull/{number}"


class Held:
    """Four rows ended their turns with their pull requests open, #11 to #14, and a home owns
    them. A first pass has recorded what is so, and from minute 0 `jmerge` says each one waits on
    the same reason."""

    def __init__(self, kitchen, reason=REASON, ahead=False):
        self.kitchen = kitchen
        self.desk = home(kitchen)
        self.crews = {}
        self.ahead = ahead
        rows = ((AHEAD, 10),) if ahead else ()
        rows += tuple((slug, number) for number, slug in enumerate(ROWS, start=11))
        for slug, number in rows:
            kitchen.brief(slug, RESULT.format(slug=slug, url=url(number)))
            self.crews[slug] = kitchen.t3.thread(slug, "completed", idle=timedelta(hours=2))
        opened = [kitchen.opened(slug, number) for slug, number in rows]
        if ahead:
            opened[0] = kitchen.opened(AHEAD, 10, state=None)
        kitchen.set("open.json", opened)
        kitchen.quiet()
        self.say(reason)

    def say(self, reason):
        lines = [f"wait {n} {url(n)}: {reason}\n" for n, _ in enumerate(ROWS, start=11)]
        if self.ahead:
            lines.insert(0, f"wait 10 {url(10)}: {ready.NOT_PASSED.format(check='check')}\n")
        self.kitchen.set("jmerge.txt", "".join(lines) if reason else "")

    def at(self, *minutes):
        """Run a pass at each of `minutes`."""
        for minute in minutes:
            self.kitchen.poll(NOW + timedelta(minutes=minute))

    def told(self):
        return [one["message"] for one in sends(self.kitchen) if one["threadId"] == self.home_id]

    @property
    def home_id(self):
        return self.desk["threadId"]

    def needs(self):
        listed = jbus.read_json(self.kitchen.state / "waiting-on-user.json", [])
        return [one for one in listed if one["kind"] == "held"]


def test_four_rows_held_31_minutes_with_nobody_at_work_wake_their_home_once(kitchen):
    held = Held(kitchen)
    held.at(0, 30)
    assert held.told() == [] and held.needs() == []
    held.at(31)
    (told,) = held.told()
    assert REASON in told and "31 minutes" in told
    assert all(f"{slug} (#{n})" in told for n, slug in enumerate(ROWS, start=11))
    (need,) = held.needs()
    assert need["rows"] == list(ROWS) and REASON in need["line"]
    held.at(60)
    assert len(held.told()) == 1 and len(held.needs()) == 1
    assert [one["who"] for one in kept(kitchen)] == ["user"]


def kept(kitchen):
    return list(jbus.read_json(kitchen.state / clock.HELD_FILE, {}).values())


def _twice(kitchen, reason):
    """Alpha's pull request #7 waits on `reason`, a wait only its crew's own run clears: jbus
    tells the crew on the first pass, and once more when the crew worked and ended its turn
    again. Told once and idle past `clock.HOLD_MINUTES`, it is the crew's and wakes nobody. Return
    the `Short` and a reader of what woke its home, after the second tell."""
    short = Short(kitchen)
    desk = home(kitchen)

    def woke():
        held = [one for one in sends(kitchen) if one["clientRequestId"].startswith(clock.HELD)]
        assert all(one["threadId"] == desk["threadId"] for one in held)
        return held

    short.out(reason)
    short.passes(40)
    (hold,) = kept(kitchen)
    assert (hold["who"], hold["woke"], hold["rows"]) == ("crew", False, ["alpha"])
    assert woke() == []
    short.thread["status"] = "running"
    short.passes(1)
    short.thread["status"] = "completed"
    short.passes(1)
    kind = ready.code_of(reason)
    told = f"{kind}|alpha|{short.head[:12]}"
    crew = [one for one in sends(kitchen) if one["threadId"] == short.thread["threadId"]]
    assert [one["clientRequestId"] for one in crew] == [told, f"{told}|2"]
    return short, woke


def test_a_held_wait_its_crew_was_told_twice_and_left_is_the_users_with_the_word_that_lifts_it(
    kitchen,
):
    """A `Proved:` wait the crew could not clear after both its tells, as #1535's base run that
    passed was, is filed as the user's once the crew sat `stall.PASSES` passes idle after the
    second: `held.json` says `who` `user` and the word that lifts it, `jbus needs` lists it with
    its reason and that word in the pass that files it, and `work.json` says alpha waits on the
    user's accept. No home is woken to pick it up, since nothing but that word moves it."""
    short, woke = _twice(kitchen, PROVED_MISSING)
    short.passes(stall.PASSES - 1)
    (hold,) = kept(kitchen)
    assert (hold["who"], hold["woke"]) == ("crew", False)
    short.passes(2)
    (hold,) = kept(kitchen)
    assert (hold["who"], hold["lift"], hold["woke"]) == ("user", judgement.ACCEPT, True)
    assert woke() == []
    assert needs(kitchen, at=later(short.minute)) == [
        "waiting on user: 1, in demo",
        f"demo held alpha: {hold['minutes']} minutes by {PROVED_MISSING}, and no thread is at "
        "work on it, no crew clears it, and your word lifts it: jmerge --accept 7",
        "  answer: reply in your own words to merge #7 or say what to do instead",
    ]
    lines = {one["key"]: one for one in jbus.read_json(kitchen.state / work.NAME, {})["work"]}
    alpha = lines["alpha"]
    assert (alpha["who"], alpha["lift"]) == ("user", work.Lift.ACCEPT)
    assert alpha["waits"] == "your accept of #7 (jmerge --accept 7)"


def test_a_held_wait_no_word_of_the_users_lifts_stays_its_crews_and_wakes_its_home(kitchen):
    """A failed check is no wait an accept lifts, so a crew told twice keeps it: it wakes the
    home once it is older than `clock.HOLD_MINUTES` with nobody at work, and is not the user's."""
    reason = ready.CHECKED_FAILED.format(exit=1, at="c" * 12, head="c" * 12)
    short, woke = _twice(kitchen, reason)
    short.passes(29)
    assert woke() == []
    short.passes(2)
    (sent,) = woke()
    assert reason in sent["message"] and "alpha (#7)" in sent["message"]
    (hold,) = kept(kitchen)
    assert (hold["who"], hold["woke"], hold["lift"]) == ("crew", True, "")
    assert needs(kitchen, at=later(short.minute)) == ["nothing waits on user in any project"]


def test_a_wait_on_the_merge_runner_wakes_nobody(kitchen):
    held = Held(kitchen, ready.UNDECIDED)
    held.at(0, 45)
    assert held.told() == [] and held.needs() == []


def test_the_hold_leaves_what_waits_on_the_user_once_it_clears_or_a_thread_takes_it_up(kitchen):
    """The hold that starts again at minute 33 is due at 64, and a crew of one of its rows is at
    work from then on: a running crew keeps it from waking anyone."""
    held = Held(kitchen)
    held.at(0, 31)
    assert len(held.needs()) == 1
    held.say("")
    held.at(32)
    assert held.needs() == []
    held.say(REASON)
    held.at(33)
    crew = held.crews["two"]
    crew["status"] = "running"
    kitchen.t3.at_work.add(crew["threadId"])
    held.at(70)
    assert held.needs() == [] and len(held.told()) == 1


AHEAD = "first"
FOLLOWS = (
    ready.MERGES_AFTER.format(slug=AHEAD, open=url(10)),
    ready.STACKED_ON.format(branch=AHEAD, slug=AHEAD, default="main"),
    ready.CARRIES_AFTER.format(carried="two", number=12, slug=AHEAD, open=url(10)),
    ready.MIGRATION_REBASING.format(number=10),
    ready.IN_LINE.format(number=10, base="main"),
)


@pytest.mark.parametrize("reason", FOLLOWS)
def test_rows_that_wait_on_an_open_row_ahead_in_ci_wake_nobody(kitchen, reason):
    """The row ahead is open and in CI, so its own wait is what holds them, and the merge runner
    is on it: the rows behind it are no hold of their own."""
    held = Held(kitchen, reason, ahead=True)
    held.at(0, 45)
    assert held.told() == [] and held.needs() == []


@pytest.mark.parametrize("reason", (FOLLOWS[0], FOLLOWS[-1]))
def test_rows_that_wait_on_a_row_ahead_with_no_open_pull_request_wake_their_home(kitchen, reason):
    """The row ahead has no open pull request, closed with no merge or not opened yet, so no wait
    of its own is watched: the rows behind it are a hold, and wake their home. A reason names the
    row ahead by its slug or by its number (`clock.AHEAD`): one case of each."""
    held = Held(kitchen, reason)
    held.at(0, 31)
    (told,) = held.told()
    assert reason in told and "31 minutes" in told
    (need,) = held.needs()
    assert need["rows"] == list(ROWS)
