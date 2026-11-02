"""A pass runs its projects side by side, since most of it is waiting on `gh` and `git`.

Every test runs the real pass against the faked T3 Code server, `gh` and `jmerge` of
`test_jbus_kitchen`, which answer at once, so a barrier in a project's call is what shows that two
projects are in a half at the same moment: run one after the other, the first waits out the barrier.
"""

import threading
import time

import jbus
from jbus import alert, failover, merge, poll, rotation, slotwait
from test_jbus_kitchen import NOW

WAIT = 20


def meeting(parties=2):
    """Return a call that returns True once `parties` calls are in it at the same moment, and False
    once it has waited `WAIT` seconds with fewer."""
    barrier = threading.Barrier(parties)

    def meet():
        try:
            barrier.wait(WAIT)
        except threading.BrokenBarrierError:
            return False
        return True

    return meet


def test_the_first_halves_of_two_projects_overlap(kitchen, monkeypatch):
    kitchen.second()
    meet, met, real = meeting(), [], merge.merge

    def merging(run):
        met.append(meet())
        return real(run)

    monkeypatch.setattr(poll.merge, "merge", merging)
    kitchen.poll()
    assert met == [True, True]


def test_the_second_halves_of_two_projects_overlap(kitchen, monkeypatch):
    kitchen.second()
    meet, met, real = meeting(), [], alert.flush

    def flushing(run):
        met.append(meet())
        return real(run)

    monkeypatch.setattr(poll.alert, "flush", flushing)
    kitchen.poll()
    assert met == [True, True]


def test_the_launches_read_the_projects_in_the_configs_order_whichever_ended_first(
    kitchen, monkeypatch
):
    kitchen.second()
    names, real, share = [], merge.merge, rotation.share

    def merging(run):
        if run.project.name != "other":
            time.sleep(0.2)
        return real(run)

    def sharing(config, halves, say):
        names.append([half.run.project.name for half in halves])
        return share(config, halves, say)

    monkeypatch.setattr(poll.merge, "merge", merging)
    monkeypatch.setattr(poll.rotation, "share", sharing)
    kitchen.poll()
    assert names == [["demo", "other"]]


def test_no_launch_starts_until_every_first_half_has_ended(kitchen, monkeypatch):
    kitchen.second()
    ended, at_share, real, share = [], [], merge.merge, rotation.share

    def merging(run):
        time.sleep(0.1 if run.project.name == "demo" else 0)
        said = real(run)
        ended.append(run.project.name)
        return said

    def sharing(config, halves, say):
        at_share.append(sorted(ended))
        return share(config, halves, say)

    monkeypatch.setattr(poll.merge, "merge", merging)
    monkeypatch.setattr(poll.rotation, "share", sharing)
    kitchen.poll()
    assert at_share == [["demo", "other"]]


def test_a_project_that_raises_leaves_the_other_its_pass_and_nothing_launches(kitchen, monkeypatch):
    kitchen.second()
    real, ran = merge.merge, []

    def merging(run):
        if run.project.name == "demo":
            raise OSError("no disk")
        ran.append(run.project.name)
        return real(run)

    monkeypatch.setattr(poll.merge, "merge", merging)
    monkeypatch.setattr(poll.rotation, "share", lambda *_: ran.append("launched"))
    said = []
    kitchen.t3.write(NOW)
    assert poll.poll(jbus.load(), NOW, said.append) == 1
    assert ran == ["other"]
    assert any(line.startswith("pass failed demo: OSError: no disk") for line in said)
    assert "wait: crews out not known (demo: the pass raised)" in said


def test_a_step_marked_shared_runs_in_one_project_at_a_time(kitchen, monkeypatch):
    kitchen.second()
    meet, inside, most, guard = meeting(), [], [], threading.Lock()
    real = slotwait.wake, failover.failover

    def alone(work):
        def run(*given):
            with guard:
                inside.append(1)
                most.append(len(inside))
            time.sleep(0.1)
            with guard:
                inside.pop()
            return work(*given)

        return run

    monkeypatch.setattr(slotwait, "wake", alone(real[0]))
    monkeypatch.setattr(failover, "failover", alone(real[1]))
    merged, merging = [], merge.merge

    def met(run):
        merged.append(meet())
        return merging(run)

    monkeypatch.setattr(poll.merge, "merge", met)
    kitchen.poll()
    assert merged == [True, True]
    assert len(most) >= 2
    assert max(most) == 1


def test_a_line_is_said_whole_while_the_projects_run_side_by_side(kitchen, monkeypatch):
    kitchen.second()
    guard, inside, most = threading.Lock(), [], []

    def say(line):
        with guard:
            inside.append(line)
            most.append(len(inside))
        time.sleep(0.001)
        with guard:
            inside.remove(line)

    meet, real = meeting(), merge.merge

    def merging(run):
        meet()
        for line in range(5):
            run.say(f"{run.project.name} {line}")
        return real(run)

    monkeypatch.setattr(poll.merge, "merge", merging)
    kitchen.t3.write(NOW)
    assert poll.poll(jbus.load(), NOW, say) == 0
    assert len(most) >= 10
    assert max(most) == 1


def test_every_t3_code_session_a_pass_opens_ends_with_the_pass(kitchen):
    kitchen.second()
    kitchen.poll()
    assert len(kitchen.t3.sessions) == 3
    assert sorted(kitchen.t3.ended) == sorted(kitchen.t3.sessions)


def test_a_project_that_raises_still_ends_its_session(kitchen, monkeypatch):
    kitchen.second()

    def merging(run):
        raise OSError("no disk")

    monkeypatch.setattr(poll.merge, "merge", merging)
    kitchen.t3.write(NOW)
    assert poll.poll(jbus.load(), NOW, lambda _: None) == 1
    assert kitchen.t3.sessions
    assert sorted(kitchen.t3.ended) == sorted(kitchen.t3.sessions)
