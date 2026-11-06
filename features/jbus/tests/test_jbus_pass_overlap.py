"""A pass runs its projects side by side, since most of it is waiting on `gh` and `git`.

Every test runs the real pass against the faked T3 Code server, `gh` and `jmerge` of
`test_jbus_kitchen`, which answer at once, so a barrier in a project's call is what shows that two
projects are in a half at the same moment: run one after the other, the first waits out the barrier.
"""

import threading
import time

import jbus
from jbus import merge, poll
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
