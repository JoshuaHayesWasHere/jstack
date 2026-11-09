"""`budget.logged` reads what is left of GitHub's API budget from the line each `gh` call logs
(`proc.CALLS`), and asks `gh api rate_limit` only where a window has no line in the last minute:
once, for every reader that finds it so at the same moment."""

import json
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from jsettings import budget, proc


def answer(left, reset):
    """What `gh api rate_limit` prints when both windows have `left` calls until `reset`."""
    window = {
        "limit": 5000,
        "used": 5000 - left,
        "remaining": left,
        "reset": int(reset.timestamp()),
    }
    return json.dumps({"resources": {"core": window, "graphql": window}})


class GitHub:
    """A `gh api rate_limit` that answers `left` calls after `slow` seconds, and counts its asks.
    Its windows start again half an hour after the test made it: a time fixed when the module is
    imported has passed by the time a long run reaches it (macos-nightly run 42593535428)."""

    def __init__(self, left=4000, slow=0.0):
        self.left, self.slow, self.asks = left, slow, 0
        self.reset = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=30)

    def __call__(self, command):
        assert command == budget.ASK
        self.asks += 1
        time.sleep(self.slow)
        return answer(self.left, self.reset)


def logs(state, resource, remaining, ago=0, **more):
    """Log a `gh` call as `proc.run` does, `ago` seconds back."""
    at = datetime.now(UTC) - timedelta(seconds=ago)
    line = {
        "at": at.isoformat(timespec="seconds"),
        "caller": "test",
        "endpoint": "/x",
        "status": 0,
        "remaining": remaining,
        "resource": resource,
        **more,
    }
    with open(state / proc.CALLS, "a") as log:
        log.write(json.dumps(line) + "\n")


@pytest.fixture
def state(tmp_path):
    return tmp_path


def aged(state, seconds=61):
    """Make the kept answer of `gh api rate_limit` `seconds` old."""
    kept = state / budget.KEPT
    given = json.loads(kept.read_text())
    given["at"] = (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()
    kept.write_text(json.dumps(given))


def remaining(read):
    return {one.name: one.remaining for one in read.windows}


def test_with_no_line_logged_it_asks_once_and_then_answers_from_that_answer(state):
    github = GitHub(4000)
    assert remaining(budget.logged(state, asked=github)) == {"core": 4000, "graphql": 4000}
    assert github.asks == 1
    github.left = 10
    assert remaining(budget.logged(state, asked=github)) == {"core": 4000, "graphql": 4000}
    assert github.asks == 1


def test_a_fresh_line_for_each_window_answers_with_no_call(state):
    github = GitHub(4000)
    budget.logged(state, asked=github)
    aged(state)
    logs(state, "core", 3990)
    logs(state, "graphql", 4800)
    logs(state, "core", 3980, http="HTTP/2.0 304 Not Modified")
    logs(state, "search", 3)
    logs(state, "core", None, status=127)
    read = budget.logged(state, asked=github)
    assert remaining(read) == {"core": 3980, "graphql": 4800}
    assert read.low.reset == github.reset and read.low.limit == 5000
    assert github.asks == 1


def test_of_github_s_two_counts_of_a_window_the_lowest_of_the_last_minute_answers(state):
    """GitHub keeps two counts of each window, which start again at different times, and a
    response gives either: the read takes the lower, the answer it asked for included, and none
    older than a minute."""
    github = GitHub(4000)
    budget.logged(state, asked=github)
    logs(state, "core", 2600, ago=61)
    logs(state, "core", 3100)
    logs(state, "core", 4300)
    logs(state, "graphql", 4500)
    assert remaining(budget.logged(state, asked=github)) == {"core": 3100, "graphql": 4000}
    assert github.asks == 1


def test_a_window_with_no_line_in_the_last_minute_is_asked_for_once(state):
    github = GitHub(4000)
    budget.logged(state, asked=github)
    aged(state)
    logs(state, "graphql", 4800, ago=61)
    logs(state, "core", 3990)
    github.left = 3000
    assert remaining(budget.logged(state, asked=github)) == {"core": 3000, "graphql": 3000}
    assert github.asks == 2
    budget.logged(state, asked=github)
    assert github.asks == 2


def test_a_window_that_started_again_is_asked_for_again(state):
    github = GitHub(4000)
    budget.logged(state, asked=github)
    kept = state / budget.KEPT
    given = json.loads(kept.read_text())
    given["resources"]["core"]["reset"] = int(datetime.now(UTC).timestamp()) - 1
    kept.write_text(json.dumps(given))
    budget.logged(state, asked=github)
    assert github.asks == 2


def test_no_answer_is_none_and_is_asked_for_again(state):
    asks = []
    assert budget.logged(state, asked=lambda command: asks.append(command)) is None
    assert budget.logged(state, asked=lambda command: asks.append(command)) is None
    assert len(asks) == 2


def test_readers_that_find_no_line_at_one_moment_ask_once_between_them(state):
    github = GitHub(4000, slow=0.3)
    found = []
    readers = [
        threading.Thread(target=lambda: found.append(budget.logged(state, asked=github)))
        for _ in range(5)
    ]
    for reader in readers:
        reader.start()
    for reader in readers:
        reader.join()
    assert github.asks == 1
    assert [remaining(one) for one in found] == [{"core": 4000, "graphql": 4000}] * 5


def test_a_long_log_is_read_from_its_end(state, monkeypatch):
    monkeypatch.setattr(budget, "CHUNK", 100)
    github = GitHub(4000)
    budget.logged(state, asked=github)
    aged(state)
    logs(state, "graphql", 4700)
    for left in range(3999, 3900, -1):
        logs(state, "core", left)
    assert remaining(budget.logged(state, asked=github)) == {"core": 3901, "graphql": 4700}
    assert github.asks == 1


def test_a_state_that_cannot_be_written_still_answers_and_asks_again(tmp_path):
    """No lock and no kept answer can be made where the state is a file: each read asks, and
    answers."""
    state = tmp_path / "state"
    state.write_text("")
    github = GitHub(4000)
    for asks in (1, 2):
        assert remaining(budget.logged(state, asked=github)) == {"core": 4000, "graphql": 4000}
        assert github.asks == asks
