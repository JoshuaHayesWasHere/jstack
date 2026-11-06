"""`jbus line-wait` reads a home's `merge.log` and prints how long pull requests waited in jmerge's
line on a day: the in-line PR-minutes, the merges, the PR-minutes per merge, and each time the head
of the line had its check started again because another pull request merged past it.

The tests write a `merge.log` into a home, run the verb as a user types it, and read what it
prints. `merge-1032.log` is #1032's own lines of 2026-11-04 as jmerge logged them, with the
repo's URL put as example.com. The merge-queue-scout's parse gave it 82 in-line minutes up to
13:05, which `merge-waits.json`'s 4834 seconds agrees with.
"""

import contextlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jbus import cli

FIXTURE = Path(__file__).parent / "fixtures" / "line-wait" / "merge-1032.log"
URL = "https://example.com/o/r/pull"
TAIL = (
    "main moved after its check started, and GitHub merges main into the branch of one pull "
    "request at a time, the one to merge next [in-line]"
)


def in_line(at, number, head):
    return f"2026-11-04 {at} wait {number} {URL}/{number}: it is in line behind #{head}: {TAIL}"


def asked(at, number, tip="0123456789ab"):
    return (
        f"2026-11-04 {at} wait {number} {URL}/{number}: GitHub was asked to merge main at {tip} "
        "into it: main moved after its check started [base-moved-asked]"
    )


def merged(at, number):
    return (
        f'2026-11-04 {at} merged {number} slug-{number} {"a" * 40} "title", '
        f"revert: gh pr revert {URL}/{number}"
    )


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A jbus config of one project, `alpha`, and its home, where `merge.log` goes."""
    config, state, homes = (tmp_path / name for name in ("c", "s", "h"))
    (state / "alpha").mkdir(parents=True)
    (homes / "alpha").mkdir(parents=True)
    config.mkdir()
    (config / "config.toml").write_text(
        'server = "http://127.0.0.1:1"\n[[project]]\nname = "alpha"\n'
        f'checkout = "{tmp_path / "alpha"}"\nprojectId = "alpha-id"\n'
    )
    (config / "config.toml").chmod(0o600)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("JBUS_CONFIG_DIR", str(config))
    monkeypatch.setenv("JBUS_STATE_DIR", str(state))
    monkeypatch.setenv("JBUS_HOME_DIR", str(homes))
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path / "t3"))
    return homes / "alpha"


def line_wait(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--project", "alpha", "line-wait", "--day", "2026-11-04", *args])
    assert code == 0
    return out.getvalue().splitlines()


def test_line_wait_gives_1032_its_82_in_line_minutes_up_to_1305(home):
    (home / "merge.log").write_text(FIXTURE.read_text())

    said = line_wait("--until", "13:05")

    assert "in-line PR-minutes: 82, over 1 pull request" in said
    assert "by pull request: #1032 82" in said


def test_line_wait_counts_a_restart_of_the_head_when_another_pull_request_merges_past_it(home):
    (home / "merge.log").write_text(
        "\n".join(
            [
                asked("10:00", 1),
                in_line("10:01", 2, 1),
                in_line("10:01", 3, 1),
                merged("10:10", 4),
                asked("10:12", 1),
                merged("10:30", 1),
                asked("10:31", 2),
                in_line("10:31", 3, 2),
                merged("10:45", 2),
                asked("10:46", 3),
                merged("11:00", 3),
            ]
        )
        + "\n"
    )

    said = line_wait()

    assert said[1:] == [
        "in-line PR-minutes: 75, over 2 pull requests",
        "merges: 4",
        "PR-minutes per merge: 18.8",
        "head restarts by a pull request jumping the line: 1",
        "- #1 at 10:12, after #4 merged past it",
        "by pull request: #3 45, #2 30",
    ]


def test_line_wait_clips_an_episode_to_the_window_and_ends_an_open_one_at_its_end(home):
    (home / "merge.log").write_text(
        "2026-11-03 23:50 wait 7 "
        f"{URL}/7: it is in line behind #6: {TAIL}\n" + in_line("00:20", 8, 6) + "\n"
    )

    said = line_wait("--since", "00:00", "--until", "01:00")

    assert said[1:3] == ["in-line PR-minutes: 100, over 2 pull requests", "merges: 0"]
    assert "PR-minutes per merge: none, no merge" in said


def test_line_wait_ends_an_episode_where_github_says_the_pull_request_merged_by_hand(home):
    """#9 merged by hand at 11:00, so jmerge logged no `merged` line for it; #10 was closed at
    10:30. Their episodes end there and not at the end of the day."""
    (home / "merge.log").write_text(in_line("10:00", 9, 1) + "\n" + in_line("10:00", 10, 1) + "\n")
    state = home.parent.parent / "s" / "alpha"

    def utc(clock):
        return datetime.fromisoformat(f"2026-11-04 {clock}").astimezone(UTC)

    (state / "ci-prs.jsonl").write_text(
        json.dumps({"number": 9, "merged": f"{utc('11:00'):%Y-%m-%dT%H:%M:%SZ}", "closed": None})
        + "\n"
        + json.dumps({"number": 10, "merged": None, "closed": f"{utc('10:30'):%Y-%m-%dT%H:%M:%SZ}"})
        + "\n"
    )

    said = line_wait()

    assert "in-line PR-minutes: 90, over 2 pull requests" in said
    assert "by pull request: #9 60, #10 30" in said
