"""Every wait has a clock (S3 of reports/flow-blockers). A pull request that waits on a reviewer
that never writes, or on a crew that stopped, is re-asked by its age in passes: jbus acts once by
itself, and after a second miss sends one line to the home, never to the user. Like
`test_jbus_expedite.py`, the tests replay small made-up rows through the real pass against the
fakes: the replay the report names for NoWaitWithoutClock is
`test_a_review_that_never_comes_is_relaunched_and_then_goes_to_the_home_in_one_line`."""

import pytest

from jmerge import ready
from jroles import ledger
from test_jbus_expedite import NO_REVIEW, Short, later
from test_jbus_kitchen import sends
from test_jbus_leftover import home
from test_jbus_queue import gates

NO_RESULT = "no brief has a Result that names it"
NO_FIX_REVIEW = "its fix is not reviewed: the scoped review of it is not written"
N = 10
"""The passes a wait may sit with nobody at work on it before jbus acts."""


@pytest.fixture
def short(kitchen):
    return Short(kitchen)


def to(kitchen, thread):
    return [one["message"] for one in sends(kitchen) if one["threadId"] == thread["threadId"]]


def loud(kitchen):
    """Return each event that a pass posted for the user."""
    return [one["line"] for post in kitchen.webhook.posts for one in post if one["loud"] == "user"]


def test_the_reasons_these_tests_give_jmerge_are_the_ones_it_prints():
    assert (NO_RESULT, NO_REVIEW, NO_FIX_REVIEW) == (
        ready.NO_BRIEF,
        ready.NO_REVIEW,
        ready.FIX_UNREVIEWED,
    )


def test_a_review_that_never_comes_is_relaunched_and_then_goes_to_the_home_in_one_line(
    short, kitchen
):
    """The replay of infra's retire-jstack-runners, from made-up rows: the crew launched its
    reviewer, the reviewer's thread ended with no `## Review`, and nobody wakes it. jbus sends the
    reviewer back to work within `N` passes, once, and after a second miss tells the home."""
    desk = home(kitchen)
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    short.passes(N - 1)
    assert to(kitchen, reviewer) == []
    said = short.passes(1)
    (again,) = to(kitchen, reviewer)
    assert again.startswith("/pr-review run alpha again")
    line = f"clock alpha: #7 waited {N} passes on {NO_REVIEW}; relaunched its reviewer"
    assert any(one.startswith(line) for one in said)
    short.passes(N - 1)
    assert to(kitchen, desk) == [] and len(to(kitchen, reviewer)) == 1
    short.passes(1)
    (told,) = to(kitchen, desk)
    assert "alpha" in told and "#7" in told and NO_REVIEW in told
    assert reviewer["threadId"] in told
    short.passes(3 * N)
    assert len(to(kitchen, reviewer)) == 1 and len(to(kitchen, desk)) == 1
    assert loud(kitchen) == [] and gates(kitchen) == []


def test_a_reviewer_at_work_is_not_relaunched_however_long_the_review_takes(short, kitchen):
    reviewer = kitchen.t3.thread("alpha", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    short.passes(3 * N)
    assert to(kitchen, reviewer) == []


def test_a_scoped_review_that_never_comes_sends_its_reviewer_the_scoped_line_again(short, kitchen):
    desk = home(kitchen)
    reviewer = kitchen.t3.thread("alpha", "failed", title="review: alpha, scoped")
    owed = f"Scoped review: needed since {short.saw}, the fix changed a.py\n"
    result = owed + f"Scoped reviewer: {reviewer['threadId']}, of {short.head}\n"
    short.out(NO_FIX_REVIEW, result=result)
    short.passes(N)
    (again,) = to(kitchen, reviewer)
    assert again.startswith("/pr-review run alpha scoped ")
    assert f"..{short.saw} " in again and f"..{short.head}" in again
    short.passes(N)
    assert len(to(kitchen, desk)) == 1 and len(to(kitchen, reviewer)) == 1


def test_a_crew_that_stopped_before_its_result_named_the_pull_request_is_carried_on_once(
    short, kitchen
):
    """The crew opened the pull request and its turn ended before it wrote the Result."""
    desk = home(kitchen)
    short.out(NO_RESULT, result="", review=False)
    brief = kitchen.home / "tasks/alpha.md"
    brief.write_text(short.launched)
    short.passes(N - 1)
    assert to(kitchen, short.thread) == []
    short.passes(1)
    (carry,) = to(kitchen, short.thread)
    assert "Carry on" in carry and "tasks/alpha.md" in carry and NO_RESULT in carry
    short.passes(N)
    (told,) = to(kitchen, desk)
    assert "alpha" in told and short.thread["threadId"] in told
    short.passes(3 * N)
    assert len(to(kitchen, short.thread)) == 1 and len(to(kitchen, desk)) == 1
    assert loud(kitchen) == [] and gates(kitchen) == []


def test_a_crew_at_work_is_not_carried_on(short, kitchen):
    short.out(NO_RESULT, result="", review=False)
    (kitchen.home / "tasks/alpha.md").write_text(short.launched)
    short.thread["status"] = "running"
    kitchen.t3.at_work.add(short.thread["threadId"])
    short.passes(3 * N)
    assert to(kitchen, short.thread) == []


def test_a_pull_request_that_stops_waiting_starts_no_clock_again_until_it_waits(short, kitchen):
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    short.passes(N - 1)
    short.out("")
    short.passes(1)
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    short.passes(N - 1)
    assert to(kitchen, reviewer) == []
    short.passes(1)
    assert len(to(kitchen, reviewer)) == 1


def test_with_no_home_the_second_miss_is_one_quiet_stall_and_not_the_user_s(short, kitchen):
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    short.passes(3 * N)
    (stall,) = [one for one in kitchen.lines("stall") if one.startswith("stall alpha: #7 waited")]
    assert "no home" in stall
    assert loud(kitchen) == [] and gates(kitchen) == []


def test_a_reviewer_whose_thread_is_gone_is_not_asked_again_and_the_home_gets_the_line(
    short, kitchen
):
    desk = home(kitchen)
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    kitchen.t3.forgot.add(reviewer["threadId"])
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    said = short.passes(N)
    assert any("and T3 Code refused it" in one for one in said)
    short.passes(N)
    assert len(to(kitchen, desk)) == 1
    tried = [one for one in sends(kitchen) if one["threadId"] == reviewer["threadId"]]
    short.passes(N)
    assert len([one for one in sends(kitchen) if one["threadId"] == reviewer["threadId"]]) == len(
        tried
    )


def test_a_second_reviewer_at_the_same_head_gets_its_own_line_after_the_first_was_relaunched(
    short, kitchen
):
    first = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    result = f"Reviewer: {first['threadId']} #1\n"
    short.out(NO_REVIEW, result=result, review=False)
    short.passes(N)
    assert len(to(kitchen, first)) == 1
    second = kitchen.t3.thread("alpha", "completed", title="review: alpha, second pass")
    twice = ready.TWICE_UNWRITTEN.format(head=short.head[:12])
    short.out(twice, result=result + f"Second reviewer: {second['threadId']} #1\n")
    said = short.passes(N)
    (again,) = to(kitchen, second)
    assert again == "/pr-review run alpha again"
    assert any(one.endswith(second["threadId"]) and "relaunched" in one for one in said)


def test_a_decline_the_scoped_review_did_not_uphold_waits_on_the_crew_not_the_reviewer(
    short, kitchen
):
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha, scoped")
    owed = f"Scoped review: needed since {short.saw}, the fix changed a.py\n"
    result = owed + short.rebased() + f"Scoped reviewer: {reviewer['threadId']}, of {short.head}\n"
    short.out(ready.DECLINES_OVERRULED.format(ruled="F1"), result=result)
    short.passes(3 * N)
    assert to(kitchen, reviewer) == []


@pytest.mark.parametrize(
    "reason",
    [
        ready.NO_VERDICT,
        ready.SECOND_UNWRITTEN,
        ready.DECLINES_UNRULED.format(ids="F1, F2"),
        ready.SCOPED_UNRULED.format(files="a.py", command="nothing"),
    ],
)
def test_each_wait_on_a_reviewer_jmerge_gives_has_a_clock(reason, short, kitchen):
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(reason, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    short.passes(N)
    assert len(sends(kitchen)) >= 1
    assert any(one["clientRequestId"].startswith("clock|alpha|") for one in sends(kitchen))


def test_a_home_t3_code_refuses_the_line_is_one_quiet_stall_and_the_wait_is_not_dropped(
    short, kitchen
):
    desk = home(kitchen)
    kitchen.t3.forgot.add(desk["threadId"])
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    said = short.passes(3 * N)
    assert not any("told its home" in one for one in said)
    (stall,) = [one for one in kitchen.lines("stall") if one.startswith("stall alpha: #7 waited")]
    assert "refused its home" in stall and desk["threadId"] in stall
    assert loud(kitchen) == [] and gates(kitchen) == []


def test_a_reviewer_on_a_capped_instance_is_relaunched_only_after_the_reset(short, kitchen):
    """The cap holds the clock. At the reset jbus sends the crew its nudge again, so the clock gives
    the crew a whole bound before it relaunches the reviewer."""
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    resets = later(N + 5)
    ledger.file_of("claudeAgent").write_text(f"five_hour 100 {int(resets.timestamp())}\n")
    short.passes(N + 5)
    assert later(short.minute - 1) < resets and to(kitchen, reviewer) == []
    short.passes(N)
    assert to(kitchen, reviewer) == []
    short.passes(1)
    assert to(kitchen, reviewer) == ["/pr-review run alpha again"]
