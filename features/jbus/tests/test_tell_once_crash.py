"""A pass that dies between an act and its mark tells nobody twice and drops no tell: the next pass
tells once. These are the seven acts on which TLC broke a rule of `features/jbus/spec/TellOnce.tla`
in the code before the fix, each replayed through the real pass against the kitchen's fakes.

A death is `Died`, raised at the point TLC's trace names, right after the act. It is a
`BaseException`, so no step's `except Exception` takes it: the pass stops there, its locks go as a
dead process's flocks do, and the disk keeps what it wrote. What the receiver took is counted the
receiver's way: T3 Code takes one message per `clientRequestId` (the fake's `messages`), the log
holds the event lines, `questions.json` the questions, and the relay, the second target, sends on
a body once per id under its own rule (`relayed`)."""

import json
from datetime import timedelta

import pytest

from jbus import mainmoved, outbox, questions, queue, relay, wake
from test_jbus_blocking import Second, hold, later, relayed
from test_jbus_clock import N, NO_REVIEW, to
from test_jbus_expedite import Short
from test_jbus_failover import POOL
from test_jbus_github import launched
from test_jbus_github import passes as run_at
from test_jbus_kitchen import NOW, RESULT, iso
from test_jbus_leftover import home
from test_jbus_owed import AFTER, ASK, limit, said, stopped
from test_jbus_queue import rows
from test_jbus_red_main import asked, landed, no_job
from test_jbus_main_moved import checks, tip
from test_jbus_twice import A, B, pages, red_at
from test_jbus_word import CHAT, REF, WORDS

__all__ = ["launched"]


class Died(BaseException):
    """The pass dies here: a timeout, a reboot or an OOM kill between two of its writes."""


def dies_after(monkeypatch, owner, name, when):
    """Kill the pass right after the first call of `owner.name` for which `when(result, *args,
    **kwargs)` holds. The call's own writes stand, and nothing after it runs."""
    real, armed = getattr(owner, name), [True]

    def dying(*args, **kwargs):
        made = real(*args, **kwargs)
        if armed and when(made, *args, **kwargs):
            armed.clear()
            raise Died(f"{owner.__name__}.{name}")
        return made

    monkeypatch.setattr(owner, name, dying)


def taken(kitchen, prefix):
    """The messages T3 Code took under a key that starts with `prefix`: one per key."""
    return [one for key, one in kitchen.t3.messages.items() if key.startswith(prefix)]


def test_twice_pages_the_chef_once_when_the_pass_dies_after_it_held_the_row(launched, monkeypatch):
    """TLC's first trace (NoTellLost): `queue.hold` holds the row at its second red head, the pass
    dies before `run.gate`, and the next pass skips the held row, so the page never goes."""
    red_at(launched, A, "11")
    run_at(launched, 0)
    red_at(launched, B, "12")
    dies_after(monkeypatch, queue, "hold", lambda _, state, slug, **how: slug == "alpha")
    with pytest.raises(Died):
        run_at(launched, 3)
    run_at(launched, 6, 9)
    assert rows(launched)["alpha"]["held"] is True
    (page,) = pages(launched)
    assert "aaaaaaaaaaaa" in page["text"] and "bbbbbbbbbbbb" in page["text"]


@pytest.fixture
def short(kitchen):
    return Short(kitchen)


def test_the_clock_s_stall_reaches_the_home_when_the_pass_dies_after_its_key(
    short, kitchen, monkeypatch
):
    """NoTellLost: `Box.send` writes the stall's key to `sent.json`, the pass dies before the event
    line, and the next pass finds the key, writes `home`, and the home is never told."""
    desk = home(kitchen)
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    short.out(NO_REVIEW, result=f"Reviewer: {reviewer['threadId']} #1\n", review=False)
    short.passes(2 * N - 1)
    assert to(kitchen, desk) == []
    stall = "stall|alpha|clock "
    dies_after(
        monkeypatch, wake, "_write_sent", lambda _, path, keys: keys and keys[-1].startswith(stall)
    )
    with pytest.raises(Died):
        short.passes(1)
    short.minute += 1
    short.passes(3)
    lines = [one for one in kitchen.lines("stall") if one.startswith("stall alpha: #7 waited")]
    assert len(lines) == 1
    (told,) = to(kitchen, desk)
    assert "alpha" in told and NO_REVIEW in told


@pytest.fixture
def pools(jstack_config, kitchen):
    """The crew and the home share one pool, claudeAgent first, as `test_jbus_owed` has it."""
    kitchen.machine(plan=None)
    (jstack_config.parent / "roles").write_text(
        f"crew: claudeAgent claude-sonnet-5-5 {POOL}\nhome: claudeAgent claude-opus-5-5 {POOL}\n"
    )


def test_an_ask_failover_carried_on_goes_once_when_the_pass_dies_after_the_carry_on(
    pools, kitchen, monkeypatch
):
    """NoTellTwice: failover sends the carry-on quoting the ask, the pass dies before
    `owed.taken`, the carry-on's turn ends, and the sweep sends the ask again under its own key."""
    desk = home(kitchen, idle=timedelta(minutes=1))
    stopped(desk, [said(ASK), *limit()], ran_on="claudeAgent")
    dies_after(monkeypatch, outbox, "send", lambda went, *_, **sent: sent["template"] == "failover")
    with pytest.raises(Died):
        kitchen.poll(NOW)
    (carry,) = taken(kitchen, "failover|")
    turn = said(carry["message"], run="run-2", by="agent", item="m2", position=5)
    older = [{"runId": "run-1", "status": "failed"}]
    stopped(desk, [said(ASK), *limit(), turn], run="run-2", status="completed", older=older)
    kitchen.poll(AFTER)
    kitchen.poll(AFTER + timedelta(minutes=1))
    quoting = [one for one in kitchen.t3.messages.values() if ASK in one["message"]]
    assert [one["threadId"] for one in quoting] == [desk["threadId"]]


def relayed_on(posts):
    """What the relay sends on of the bodies posted to it, each with when it was posted: a body
    under its own `id` once ever, and one with no id of its own once per `RELAY_DEDUP_SECONDS`
    (900, `jbus.relayenv`) of its hashed id, since a hash names only the content
    (`relay.event_id`)."""
    sent, last = [], {}
    for at, body in posts:
        named = relay.event_id(body)
        own = body.get("id") == named
        if named in last and (own or (at - last[named]).total_seconds() < 900):
            continue
        last[named] = at
        sent.append(body)
    return sent


def test_the_second_target_takes_a_body_once_when_the_pass_dies_after_its_post(
    kitchen, monkeypatch
):
    """NoTellTwice: the POST went, the pass dies (or hears no answer in time) before `outbox.json`
    drops the body, and a pass past the relay's window posts it again."""
    second = Second()
    try:
        relayed(kitchen, second)
        hold(kitchen, 9)
        dies_after(monkeypatch, wake, "_post_blocking", lambda why, *_: why == "")
        with pytest.raises(Died):
            kitchen.poll(later(1))
        first = len(second.bodies)
        kitchen.poll(later(20))
        posts = [(later(1), one) for one in second.bodies[:first]]
        posts += [(later(20), one) for one in second.bodies[first:]]
    finally:
        second.close()
    assert [one["kind"] for _, one in posts].count("events") == 2
    assert [one["kind"] for one in relayed_on(posts)].count("events") == 1


def test_a_word_goes_to_one_home_thread_when_the_pass_dies_after_it_went_and_the_home_moves(
    kitchen, monkeypatch
):
    """NoTellTwice: the word went, the run dies before `sent_at`, the home hands its thread on,
    and the next pass sends the word to the new thread too."""
    kitchen.t3.says(CHAT, "m-word", WORDS, updatedAt=iso(NOW - timedelta(minutes=5)), title="chat")
    (kitchen.home / "home-id").write_text("home-1\n")
    dies_after(monkeypatch, outbox, "send", lambda went, *_, **sent: sent["template"] == "word")
    with pytest.raises(Died):
        kitchen.main("word", "--to", "demo", "--message", REF)
    (kitchen.home / "home-id").write_text("home-2\n")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=1))
    (word,) = taken(kitchen, "word|")
    assert word["message"].endswith(WORDS)


def test_the_account_question_is_parked_once_when_the_pass_dies_before_account_json(
    kitchen, monkeypatch
):
    """NoTellTwice: `questions.park` keeps the question, the pass dies before `account.json`, main's
    unrun tip moves, and a second question is parked."""
    kitchen.brief("alpha", RESULT)
    green = tip(kitchen)
    checks(kitchen, green, "success")
    kitchen.set("commits.json", [kitchen.commit(green, ago=timedelta(hours=1))])
    kitchen.quiet()
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, green, ago=timedelta(minutes=30))])
    no_job(kitchen, landed(kitchen, 1), 1)
    dies_after(
        monkeypatch, questions, "park", lambda _, run, slug, lines: slug == mainmoved.ACCOUNT
    )
    with pytest.raises(Died):
        kitchen.poll(NOW + timedelta(minutes=3))
    no_job(kitchen, landed(kitchen, 2), 2)
    kitchen.poll(NOW + timedelta(minutes=6))
    kitchen.poll(NOW + timedelta(minutes=7))
    (question,) = [one for one in asked(kitchen) if one.slug == mainmoved.ACCOUNT]
    assert json.loads((kitchen.state / mainmoved.ACCOUNT_FILE).read_text()) == {
        "question": question.number
    }
    assert len(kitchen.lines("gate")) == 1


CHANGED = 'merged 7 alpha abc1234def5 "a skill", skills changed: crew, revert: x\n'
AGAIN = 'merged 8 alpha 0de1234abc9 "a skill", skills changed: crew, revert: y\n'


def test_a_skill_s_notice_names_a_merge_once_when_the_pass_dies_after_it_went(kitchen, monkeypatch):
    """NoTellTwice: the notice of merge 7 went, the pass dies before its commit is marked, merge 8
    is kept, and the next notice's key names both: merge 7 is told again."""
    kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=30))
    kitchen.set("jmerge.txt", CHANGED)
    dies_after(monkeypatch, outbox, "send", lambda went, *_, **sent: sent["template"] == "reload")
    with pytest.raises(Died):
        kitchen.poll()
    kitchen.set("jmerge.txt", AGAIN)
    kitchen.poll(NOW + timedelta(minutes=1))
    kitchen.set("jmerge.txt", "")
    kitchen.poll(NOW + timedelta(minutes=2))
    told = [one["message"] for one in taken(kitchen, "reload|")]
    assert sum("#7 at abc1234def5" in one for one in told) == 1
    assert sum("#8 at 0de1234abc9" in one for one in told) == 1
