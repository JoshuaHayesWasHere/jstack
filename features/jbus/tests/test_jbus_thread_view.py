"""`jbus thread <slug or thread id>` prints what a thread last said, from T3 Code's store alone.

It reads no config and calls no T3 Code tool: each test runs the real command with no server at
all, against a small store laid out as T3 Code lays out its own, under `T3CODE_HOME`.
"""

import sqlite3

import pytest

from jbus import cli, threadview
from test_jbus_message_last import stored

CREW = "mcp:the-crew"


def pull(number, state="open", checks="passing"):
    return {
        "number": number,
        "url": f"https://github.com/o/r/pull/{number}",
        "linkedAt": f"2026-11-10T10:{number % 60:02d}:00Z",
        "snapshot": {"state": state, "checksState": checks},
    }


def said(text, at, thread=CREW, streaming=False):
    return (f"{thread}:{at}", thread, "assistant", "agent", streaming, at, at, text)


def thread(capsys, *named):
    code = cli.main(["thread", *named])
    return code, capsys.readouterr().out


def test_a_crews_thread_shows_its_status_last_run_pull_requests_and_last_word(
    tmp_path, monkeypatch, capsys
):
    stored(
        tmp_path,
        monkeypatch,
        [
            said("I started.", "2026-11-10T10:00:00Z"),
            said("Opened #12; checks pass.", "2026-11-10T11:00:00Z"),
            said("half a sentence", "2026-11-10T11:30:00Z", streaming=True),
        ],
        threads=[(CREW, "crew: alpha", None, {"settledAt": "x", "pullRequests": [pull(12)]})],
        runs=[
            (CREW, 1, "completed", "2026-11-10T09:00:00Z", "2026-11-10T10:00:00Z"),
            (CREW, 2, "running", "2026-11-10T11:20:00Z", None),
        ],
    )
    assert thread(capsys, "alpha") == (
        0,
        f"crew: alpha ({CREW})\n"
        "status: settled\n"
        "last run: running, 2026-11-10T11:20:00Z\n"
        "pull request #12: open, checks passing, https://github.com/o/r/pull/12\n"
        "last said:\n"
        "Opened #12; checks pass.\n",
    )
    assert thread(capsys, CREW)[1].startswith(f"crew: alpha ({CREW})\nstatus: settled\n")


def test_a_long_last_word_is_cut_at_2000_and_says_so_in_2600_at_most(tmp_path, monkeypatch, capsys):
    stored(
        tmp_path,
        monkeypatch,
        [said("x" * 5000, "2026-11-10T11:00:00Z")],
        threads=[
            ("mcp:the-scout", "scout: alpha", None, {}),
            (
                CREW,
                "crew: alpha",
                "2026-11-10T12:00:00Z",
                {"pullRequests": list(map(pull, range(30)))},
            ),
        ],
    )
    code, out = thread(capsys, "alpha")
    assert code == 0
    assert threadview.SAID == 2000 and threadview.CAP == 2600
    assert "x" * 2000 + "\n(cut: the first 2000 of 5000 characters)\n" in out
    assert "x" * 2001 not in out
    assert len(out) <= 2600
    assert out.splitlines()[:3] == [f"crew: alpha ({CREW})", "status: archived", "last run: none"]
    assert "also: scout: alpha mcp:the-scout" in out


@pytest.mark.parametrize("named", ["beta", "mcp:no-such-thread"])
def test_a_thread_the_store_does_not_have_is_refused(tmp_path, monkeypatch, capsys, named):
    stored(tmp_path, monkeypatch, [], threads=[(CREW, "crew: alpha", None, {})])
    assert thread(capsys, named) == (
        1,
        f"refused: T3 Code's store has no thread {named}, by id or by slug\n",
    )


def test_a_thread_that_said_nothing_yet_says_so(tmp_path, monkeypatch, capsys):
    stored(tmp_path, monkeypatch, [], threads=[(CREW, "crew: alpha", None, {})])
    db = sqlite3.connect(tmp_path / "t3" / threadview.STORE)
    db.execute("update orchestration_v2_projection_threads set payload_json = 'not json'")
    db.commit()
    db.close()
    assert thread(capsys, "alpha") == (
        0,
        f"crew: alpha ({CREW})\nstatus: open\nlast run: none\nlast said: nothing yet\n",
    )


@pytest.mark.parametrize(
    ("store", "why"),
    [
        (None, "T3 Code keeps no store at {where}"),
        (b"not sqlite", "T3 Code's store at {where} cannot be read"),
    ],
)
def test_a_store_that_is_not_there_or_does_not_read_is_refused(
    tmp_path, monkeypatch, capsys, store, why
):
    where = tmp_path / threadview.STORE
    if store is not None:
        where.parent.mkdir(parents=True)
        where.write_bytes(store)
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path))
    code, out = thread(capsys, "alpha")
    assert (code, out.startswith("refused: " + why.format(where=where))) == (1, True)


def test_said_lists_the_users_own_messages_that_hold_the_words(tmp_path, monkeypatch, capsys):
    words = "just drop it in the future"
    stored(
        tmp_path,
        monkeypatch,
        [
            (f"m{n}", thread, "user", by, False, f"2026-11-0{n}T10:00:00Z", "", text)
            for n, thread, by, text in [
                (1, "mcp:a-home", "user", f"Some of this is noise. {words}"),
                (2, "mcp:a-home", "agent", f"jbus: carried, {words}"),
                (3, "mcp:another", "user", f"again: {words}\nplease"),
                (4, "mcp:another", "user", "nothing of it"),
            ]
        ],
    )
    assert thread(capsys, "--said", words) == (
        0,
        f"mcp:another/m3 2026-11-03T10:00:00Z: again: {words} please\n"
        f"mcp:a-home/m1 2026-11-01T10:00:00Z: Some of this is noise. {words}\n",
    )
    assert thread(capsys, "mcp:a-home", "--said", words)[1].startswith("mcp:a-home/m1 ")
    assert thread(capsys, "--said", "not said") == (
        0,
        "none: no message of the user's holds 'not said'\n",
    )
    assert thread(capsys) == (
        1,
        "refused: jbus thread takes a thread, by its id or a slug, or --said\n",
    )
