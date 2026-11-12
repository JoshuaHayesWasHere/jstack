"""The tests of `features/jgauge/hooks/limits.sh`. Claude Code gives the status line script its
input on stdin. The script writes a file from that input, and `room` reads the file back. The
tests cover that file. They also cover every input on which the script leaves the file alone.
Every test runs the script."""

import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from test_room import IDLE, check, machine, ran
from testing.paths import REPO

HOOK = REPO / "features" / "jgauge" / "hooks" / "limits.sh"
NOW = int(time.time())
SOON, LATER, WEEK = NOW + 3600, NOW + 5 * 3600, NOW + 90 * 3600
"""Resets for the script, which never reads the clock. A test that asks `room`, which does, takes
its resets from `ahead` instead, since a whole suite can run for longer than SOON is ahead."""


def ahead():
    """Return a five-hour and a weekly reset an hour and 90 hours from now."""
    now = int(time.time())
    return now + 3600, now + 90 * 3600


def handed(**windows):
    """What Claude Code gives a status line on stdin. Each window in `windows` is a pair of the
    share used and the reset time, `used, resets_at`."""
    return json.dumps(
        {
            "session_id": "0b1f6c1e-aaaa-4bbb-8ccc-1234567890ab",
            "model": {"id": "claude-opus-5-5", "display_name": "Opus"},
            "context_window": {"used_percentage": 8, "remaining_percentage": 92},
            "rate_limits": {
                name: {"used_percentage": used, "resets_at": resets}
                for name, (used, resets) in windows.items()
            },
        }
    )


def write(stdin, env):
    """Run the script as a status line would. It never fails and never prints."""
    done = subprocess.run(
        ["sh", str(HOOK)], input=stdin, env=env, capture_output=True, text=True, check=False
    )
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")


@pytest.fixture
def env(tmp_path):
    """The machine, for a status line of the built-in account, `~/.claude`."""
    made = machine(tmp_path, **IDLE, plan=None)
    made.pop("CLAUDE_CONFIG_DIR", None)
    return made


def kept(env):
    return Path(env["LIMITS"]).read_text()


def test_what_the_script_writes_is_what_room_reads(env):
    soon, week = ahead()
    write(handed(five_hour=(23.5, soon), seven_day=(41.2, week)), env)
    assert kept(env) == f"five_hour 23.5 {soon}\nseven_day 41.2 {week}\n"
    said = ran(env, check())
    assert (said.stdout, said.stderr) == ("go\n", "")


def test_a_window_past_the_cushion_in_the_written_file_makes_room_wait(env):
    write(handed(five_hour=(100, int(time.time()) + 3600 + 59), seven_day=(41.2, WEEK)), env)
    said = ran(env, check())
    assert said.stdout == (
        "wait: the five-hour limit is 100% used, at or over 90%, and resets in 1 h 0 min\n"
    )


def test_the_file_and_its_directory_are_made_under_the_account_when_none_is_named(tmp_path, env):
    home = tmp_path / "home"
    home.mkdir()
    del env["LIMITS"]
    write(handed(five_hour=(10, SOON), seven_day=(20, WEEK)), {**env, "HOME": str(home)})
    assert (home / ".local" / "state" / "claude" / "limits").read_text() == (
        f"five_hour 10 {SOON}\nseven_day 20 {WEEK}\n"
    )


def test_the_use_is_kept_to_two_places_and_the_reset_to_whole_seconds(env):
    write(handed(five_hour=(12.3456, SOON + 0.75), seven_day=(0, WEEK)), env)
    assert kept(env) == f"five_hour 12.35 {SOON}\nseven_day 0 {WEEK}\n"


NOTHING_TO_KEEP = [
    "",
    "not json",
    "[]",
    "7",
    "null",
    "{}",
    '{"rate_limits": null}',
    '{"rate_limits": {}}',
    '{"rate_limits": "soon"}',
    '{"rate_limits": {"five_hour": null, "seven_day": {}}}',
    '{"rate_limits": {"five_hour": {"used_percentage": 50}}}',
    '{"rate_limits": {"five_hour": {"resets_at": 1999999999}}}',
    '{"rate_limits": {"five_hour": {"used_percentage": "lots", "resets_at": "soon"}}}',
    '{"rate_limits": {"five_hour": {"used_percentage": -1, "resets_at": 1999999999}}}',
    '{"rate_limits": {"spend_limit": {"used_percentage": 62.8, "resets_at": 1999999999}}}',
    '{"rate_limits": {"five_hour": {"used_percentage": 50, "resets_at": 1999999999}',
]


@pytest.mark.parametrize("stdin", NOTHING_TO_KEEP)
def test_input_with_no_limits_leaves_the_file_as_it_was(env, stdin):
    write(handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK)), env)
    before = (kept(env), os.stat(env["LIMITS"]).st_ino, os.stat(env["LIMITS"]).st_mtime_ns)
    write(stdin, env)
    assert (kept(env), os.stat(env["LIMITS"]).st_ino, os.stat(env["LIMITS"]).st_mtime_ns) == before
    beside = sorted(os.listdir(Path(env["LIMITS"]).parent))
    assert beside == ["limits", "limits.lock", "proc", "stub"]


@pytest.mark.parametrize("stdin", NOTHING_TO_KEEP)
def test_input_with_no_limits_makes_no_file(env, stdin):
    write(stdin, env)
    assert not Path(env["LIMITS"]).exists()


@pytest.mark.parametrize(
    ("first", "then", "left"),
    [
        ((80, SOON), (2, LATER), f"five_hour 2 {LATER}"),
        ((2, LATER), (80, SOON), f"five_hour 2 {LATER}"),
        ((30, SOON), (31.5, SOON), f"five_hour 31.5 {SOON}"),
        ((31.5, SOON), (30, SOON), f"five_hour 31.5 {SOON}"),
        ((9, SOON), (10, SOON), f"five_hour 10 {SOON}"),
    ],
    ids=[
        "a later reset over higher use",
        "an earlier reset after a later one",
        "higher use at the same reset",
        "lower use at the same reset",
        "a little more use at the same reset",
    ],
)
def test_the_later_reset_wins_and_then_the_higher_use(env, first, then, left):
    write(handed(five_hour=first, seven_day=(41.2, WEEK)), env)
    write(handed(five_hour=then, seven_day=(41.2, WEEK)), env)
    assert kept(env) == f"{left}\nseven_day 41.2 {WEEK}\n"


def test_a_session_that_gives_one_window_keeps_the_other(env):
    write(handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK)), env)
    write(handed(five_hour=(24, SOON)), env)
    assert kept(env) == f"five_hour 24 {SOON}\nseven_day 41.2 {WEEK}\n"
    write(handed(seven_day=(42, WEEK)), env)
    assert kept(env) == f"five_hour 24 {SOON}\nseven_day 42 {WEEK}\n"


def test_a_file_that_is_no_limits_file_is_replaced_by_one(env):
    Path(env["LIMITS"]).write_text(f"not a limits file\nfive_hour lots soon\nseven_day 5 {WEEK}\n")
    write(handed(five_hour=(23.5, SOON)), env)
    assert kept(env) == f"five_hour 23.5 {SOON}\nseven_day 5 {WEEK}\n"


def test_figures_already_in_the_file_do_not_write_it_again(env):
    stdin = handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK))
    write(stdin, env)
    before = (os.stat(env["LIMITS"]).st_ino, os.stat(env["LIMITS"]).st_mtime_ns)
    write(stdin, env)
    assert (os.stat(env["LIMITS"]).st_ino, os.stat(env["LIMITS"]).st_mtime_ns) == before


def test_a_run_ended_before_its_rename_leaves_only_the_lock_beside_the_file(tmp_path, env):
    write(handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK)), env)
    old = kept(env)
    (tmp_path / "stub" / "mv").write_text('#!/bin/sh\nkill -TERM "$PPID"\nexit 1\n')
    (tmp_path / "stub" / "mv").chmod(0o755)
    write(handed(five_hour=(60, LATER), seven_day=(41.2, WEEK)), env)
    assert kept(env) == old
    assert sorted(os.listdir(tmp_path)) == ["limits", "limits.lock", "proc", "stub"]


def test_runs_that_overlap_leave_one_whole_file_and_only_the_lock_beside_it(tmp_path, env):
    runs = [handed(five_hour=(n, SOON + n), seven_day=(n, WEEK + n)) for n in range(1, 25)]
    wholes = {
        f"five_hour {n} {SOON + n}\nseven_day {m} {WEEK + m}\n"
        for n in range(1, 25)
        for m in range(1, 25)
    }
    with ThreadPoolExecutor(max_workers=8) as pool:
        writers = [pool.submit(write, stdin, env) for stdin in runs]
        while not all(writer.done() for writer in writers):
            if Path(env["LIMITS"]).exists():
                assert kept(env) in wholes
        for writer in writers:
            writer.result()
    assert kept(env) in wholes
    assert sorted(os.listdir(tmp_path)) == ["limits", "limits.lock", "proc", "stub"]


def test_a_path_it_cannot_write_to_breaks_nothing(tmp_path, env):
    stdin = handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK))
    Path(env["LIMITS"]).mkdir()
    write(stdin, env)
    assert os.listdir(env["LIMITS"]) == []
    (tmp_path / "file").write_text("in the way\n")
    write(stdin, {**env, "LIMITS": str(tmp_path / "file" / "limits")})
    assert sorted(os.listdir(tmp_path)) == ["file", "limits", "proc", "stub"]


def test_a_directory_where_the_lock_cannot_be_opened_breaks_nothing(tmp_path, env):
    """The state directory stands but is read-only, so `limits.lock` cannot be opened: the
    status line still ends 0 and writes nothing."""
    shut = tmp_path / "shut"
    shut.mkdir(mode=0o555)
    write(
        handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK)),
        {**env, "LIMITS": str(shut / "limits")},
    )
    assert os.listdir(shut) == []


def test_a_machine_with_no_jq_breaks_nothing(tmp_path, env):
    empty = tmp_path / "empty"
    empty.mkdir()
    done = subprocess.run(
        ["/bin/sh", str(HOOK)],
        input=handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK)),
        env={**env, "PATH": str(empty)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert not Path(env["LIMITS"]).exists()


PRIME = "claudeAgent_claude_prime"


def inventory(tmp_path, env, prime_home):
    """The provider instances, T3's settings under the environment's T3 home, with prime's
    home."""
    t3 = tmp_path / "t3"
    (t3 / "userdata").mkdir(parents=True, exist_ok=True)
    (t3 / "userdata" / "settings.json").write_text(
        json.dumps(
            {
                "providerInstances": {
                    "claudeAgent": {"driver": "claudeAgent", "enabled": True},
                    PRIME: {"driver": "claudeAgent", "config": {"homePath": prime_home}},
                    "codex": {"driver": "codex"},
                }
            }
        )
    )
    return {**env, "T3CODE_HOME": str(t3)}


@pytest.mark.parametrize("prime_home", ["~/.claude_prime", "{home}/.claude_prime/"])
def test_a_second_account_writes_its_own_file_and_leaves_the_first_alone(tmp_path, env, prime_home):
    """Each account's status line writes the file of one instance: the instance whose home is
    the account's CLAUDE_CONFIG_DIR. So one account's limits never count as another's."""
    home = tmp_path / "home"
    soon, week = ahead()
    named = inventory(tmp_path, {**env, "HOME": str(home)}, prime_home.format(home=home))
    write(handed(five_hour=(12, soon), seven_day=(30, week)), named)
    full = handed(five_hour=(100, soon), seven_day=(30, week))
    write(full, {**named, "CLAUDE_CONFIG_DIR": str(home / ".claude_prime")})
    assert kept(env) == f"five_hour 12 {soon}\nseven_day 30 {week}\n"
    assert (
        Path(f"{env['LIMITS']}.{PRIME}").read_text()
        == f"five_hour 100 {soon}\nseven_day 30 {week}\n"
    )
    assert ran(env, check()).stdout == "go\n"
    waits = ran({**env, "POOL": PRIME}, check()).stdout
    assert waits.startswith("wait: the five-hour limit is 100% used")


def test_an_account_the_inventory_does_not_declare_writes_nothing(tmp_path, env):
    named = inventory(tmp_path, env, "~/.claude_prime")
    write(handed(five_hour=(100, SOON)), {**named, "CLAUDE_CONFIG_DIR": str(tmp_path / "other")})
    assert sorted(path.name for path in Path(env["LIMITS"]).parent.iterdir()) == [
        "proc",
        "stub",
        "t3",
    ]


def test_a_reset_a_second_off_is_the_same_window_and_a_cap_on_it_stands(env):
    """The status line gives a window's reset. `jgauge limits` and jbus may each write a reset
    for that window up to one second before or after it, and the script counts both as the same
    window. The script merges them as `jroles.ledger.merge` does, and a lower share never
    replaces the cap."""
    Path(env["LIMITS"]).write_text(f"five_hour 100 {SOON + 1}\n")
    write(handed(five_hour=(63, SOON)), env)
    assert kept(env) == f"five_hour 100 {SOON + 1}\n"
    write(handed(five_hour=(12, LATER)), env)
    assert kept(env) == f"five_hour 12 {LATER}\n"


def test_a_second_writer_between_the_read_and_the_rename_keeps_its_record(tmp_path, env):
    """A second writer of the file, here another status line, starts while the script is between
    its read and its rename, as TestSlot.tla's LedgerNoLostUpdate trace has it. The script's
    older copy of the file must not drop the second writer's cap. The script's read stops for
    the second writer, or for a second at most."""
    soon, week = ahead()
    stub = tmp_path / "stub"
    (stub / "cat").write_text(
        "#!/bin/sh\n"
        f'{shutil.which("cat")} "$@"\n'
        f'mkdir "{stub}/read" 2>/dev/null || exit 0\n'
        f'i=0; while [ ! -e "{stub}/done" ] && [ $i -lt 10 ]; do sleep 0.1; i=$((i+1)); done\n'
    )
    (stub / "cat").chmod(0o755)

    def second():
        while not (stub / "read").exists():
            time.sleep(0.01)
        write(handed(seven_day=(100, week)), env)
        (stub / "done").touch()

    with ThreadPoolExecutor(max_workers=2) as pool:
        writers = [pool.submit(write, handed(five_hour=(40, soon)), env), pool.submit(second)]
        for writer in writers:
            writer.result(timeout=30)
    assert kept(env) == f"five_hour 40 {soon}\nseven_day 100 {week}\n"
