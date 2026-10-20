"""`hooks/limits.sh`: the file it writes from what Claude Code hands a status line, read back by
`room`, and every input it leaves the file alone on. Every test runs the script."""

import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from test_room import IDLE, check, machine, ran

REPO = Path(__file__).parent.parent
HOOK = REPO / "hooks" / "limits.sh"
MV = shutil.which("mv")
NOW = int(time.time())
SOON, LATER, WEEK = NOW + 3600, NOW + 5 * 3600, NOW + 90 * 3600


def handed(**windows):
    """What Claude Code gives a status line on stdin, with these windows as `used, resets_at`."""
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
    write(handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK)), env)
    assert kept(env) == f"five_hour 23.5 {SOON}\nseven_day 41.2 {WEEK}\n"
    said = ran(env, check())
    assert (said.stdout, said.stderr) == ("go\n", "")


def test_a_window_past_the_cushion_in_the_written_file_makes_room_wait(env):
    write(handed(five_hour=(100, int(time.time()) + 3600 + 59), seven_day=(41.2, WEEK)), env)
    said = ran(env, check())
    assert said.stdout == (
        "wait: the five-hour limit is 100% used, at or over 100%, and resets in 1 h 0 min\n"
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
    assert sorted(os.listdir(Path(env["LIMITS"]).parent)) == ["limits", "proc", "stub"]


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


def test_the_file_is_whole_until_a_rename_puts_the_next_whole_one_in_its_place(tmp_path, env):
    write(handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK)), env)
    old, inode = kept(env), os.stat(env["LIMITS"]).st_ino
    seen = tmp_path / "seen"
    (tmp_path / "stub" / "mv").write_text(
        "#!/bin/sh\n"
        'for last; do :; done\n{ echo "to $last"; cat "$last"; echo "from"; '
        f'for arg; do [ "$arg" = "$last" ] || [ ! -f "$arg" ] || cat "$arg"; done; }} > {seen}\n'
        f'exec {MV} "$@"\n'
    )
    (tmp_path / "stub" / "mv").chmod(0o755)
    write(handed(five_hour=(60, LATER), seven_day=(41.2, WEEK)), env)
    new = f"five_hour 60 {LATER}\nseven_day 41.2 {WEEK}\n"
    assert seen.read_text() == f"to {env['LIMITS']}\n{old}from\n{new}"
    assert kept(env) == new and os.stat(env["LIMITS"]).st_ino != inode
    assert sorted(os.listdir(tmp_path)) == ["limits", "proc", "seen", "stub"]


def test_a_run_ended_before_its_rename_leaves_nothing_beside_the_file(tmp_path, env):
    write(handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK)), env)
    old = kept(env)
    (tmp_path / "stub" / "mv").write_text('#!/bin/sh\nkill -TERM "$PPID"\nexit 1\n')
    (tmp_path / "stub" / "mv").chmod(0o755)
    write(handed(five_hour=(60, LATER), seven_day=(41.2, WEEK)), env)
    assert kept(env) == old
    assert sorted(os.listdir(tmp_path)) == ["limits", "proc", "stub"]


def test_runs_that_overlap_leave_one_whole_file_and_nothing_beside_it(tmp_path, env):
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
    assert sorted(os.listdir(tmp_path)) == ["limits", "proc", "stub"]


def test_a_path_it_cannot_write_to_breaks_nothing(tmp_path, env):
    stdin = handed(five_hour=(23.5, SOON), seven_day=(41.2, WEEK))
    Path(env["LIMITS"]).mkdir()
    write(stdin, env)
    assert os.listdir(env["LIMITS"]) == []
    (tmp_path / "file").write_text("in the way\n")
    write(stdin, {**env, "LIMITS": str(tmp_path / "file" / "limits")})
    assert sorted(os.listdir(tmp_path)) == ["file", "limits", "proc", "stub"]


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
    """The provider inventory under the environment's config directory, with prime's home."""
    config = tmp_path / "xdg"
    (config / "jstack").mkdir(parents=True, exist_ok=True)
    (config / "jstack" / "providers.json").write_text(
        json.dumps(
            {
                "claudeAgent": {"driver": "claudeAgent", "enabled": True},
                PRIME: {"driver": "claudeAgent", "config": {"homePath": prime_home}},
                "codex": {"driver": "codex"},
            }
        )
    )
    return {**env, "XDG_CONFIG_HOME": str(config)}


@pytest.mark.parametrize("prime_home", ["~/.claude_prime", "{home}/.claude_prime/"])
def test_a_second_account_writes_its_own_file_and_leaves_the_first_alone(tmp_path, env, prime_home):
    """Each account's status line writes the file of the instance its CLAUDE_CONFIG_DIR is the
    home of, so one account's limits never stand for another's."""
    home = tmp_path / "home"
    named = inventory(tmp_path, {**env, "HOME": str(home)}, prime_home.format(home=home))
    write(handed(five_hour=(12, SOON), seven_day=(30, WEEK)), named)
    full = handed(five_hour=(100, SOON), seven_day=(30, WEEK))
    write(full, {**named, "CLAUDE_CONFIG_DIR": str(home / ".claude_prime")})
    assert kept(env) == f"five_hour 12 {SOON}\nseven_day 30 {WEEK}\n"
    assert (
        Path(f"{env['LIMITS']}.{PRIME}").read_text()
        == f"five_hour 100 {SOON}\nseven_day 30 {WEEK}\n"
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
        "xdg",
    ]
