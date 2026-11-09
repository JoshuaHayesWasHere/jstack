"""The commands this machine's passes, wakes and homes run come from the green copy, a clone of the
checkout at main's last green tip (`jbus.green`). A pass moves it forward when main goes green,
and says so with the sha. A tip of main that is red, or that does not import, never reaches it,
so the jbus that reverts or fixes a red main still runs.

Like `test_jbus_main_moved.py`, the tests run the real pass against the fakes, with the
kitchen's own origin as the remote whose main moves."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import jbus
from jbus import green, launchd
from jbus.passes import Pass
from test_jbus_kitchen import NOW
from test_jbus_queue import gates

REPO = Path(__file__).resolve().parents[3]
BROKEN = 'raise ImportError("jbus.telemetry.migrations: v007_drift is migration 8")\n'
REINSTALL = green._reinstall
SYSTEMD = pytest.mark.skipif(
    sys.platform == "darwin",
    reason="systemd: the move puts the units to work through jinstall's own Machine.here(), "
    "whose platform no test can set, so on macOS it makes launchd agents of the test's units",
)
"""A test whose move reaches `jinstall.green.live` with units to put to work: it holds where
systemd runs the units, and `launchd.manager` pinned to systemd does not reach jinstall."""
DEMO = """[project]
name = "greendemo"
version = "0"
[project.scripts]
greendemo = "greendemo:main"
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[tool.hatch.build.targets.wheel]
packages = ["src/greendemo"]
"""


def tip(kitchen):
    asked = ["git", "rev-parse", "refs/heads/main"]
    done = subprocess.run(asked, cwd=kitchen.origin, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def checks(kitchen, sha, conclusion):
    kept = kitchen.stub / "check-runs.json"
    runs = json.loads(kept.read_text()) if kept.exists() else {}
    runs[sha] = [{"status": "completed", "conclusion": conclusion}]
    kitchen.set("check-runs.json", runs)


def land(kitchen, conclusion, files=None):
    """Land a merge on origin's main from another clone, which writes `files` (path to text, or
    None to remove the file), and whose check ends as `conclusion` says. Return the new tip."""
    other = kitchen.root / "other"
    if not other.exists():
        kitchen.git("clone", "-q", str(kitchen.origin), str(other), cwd=kitchen.root)
    kitchen.git("pull", "-q", "--ff-only", cwd=other)
    for name, text in (files or {}).items():
        if text is None:
            (other / name).unlink()
            continue
        (other / name).parent.mkdir(parents=True, exist_ok=True)
        (other / name).write_text(text)
    kitchen.git("add", "-A", cwd=other)
    kitchen.git("commit", "-q", "--allow-empty", "-m", "a merge", cwd=other)
    kitchen.git("push", "-q", "origin", "main", cwd=other)
    checks(kitchen, tip(kitchen), conclusion)
    return tip(kitchen)


def at(copy):
    return subprocess.run(
        ["git", "-C", str(copy), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture(autouse=True)
def installs(monkeypatch):
    """The trees a move installed the tool from, in place of uv's tool install, which the one
    test of the real install puts back."""
    done = []
    monkeypatch.setattr(green, "_reinstall", lambda copy: done.append(copy.resolve()) or "")
    return done


@pytest.fixture
def systemctl(kitchen, monkeypatch):
    """A systemctl on the kitchen's PATH that keeps each call's arguments, one line a call, so no
    move reaches this machine's systemd. While `systemctl.refuse` is in the stub, it refuses the
    next daemon-reload, as a user bus that is not up does, and takes the file away. The machine is
    one whose units systemd runs, on macOS too, where `launchd.manager()` would say launchd."""
    monkeypatch.setattr(launchd, "manager", lambda: "systemd")
    fake = kitchen.stub / "systemctl"
    refuse = kitchen.stub / "systemctl.refuse"
    fake.write_text(
        f'#!/bin/sh\necho "$*" >> {kitchen.stub / "systemctl.log"}\n'
        '[ "$2" = show-environment ] && echo "HOME=$HOME"\n'
        f'[ "$*" = "--user daemon-reload" ] && [ -f {refuse} ] || exit 0\nrm -f {refuse}\n'
        'echo "Failed to connect to bus: No medium found" >&2\nexit 1\n'
    )
    fake.chmod(0o755)
    return kitchen.stub / "systemctl.log"


@pytest.fixture
def copied(kitchen, tmp_path, monkeypatch, systemctl):
    """A kitchen whose checkout has a green copy at main's tip, which a first pass recorded as
    green, under a data home of the test's own, and a systemctl that only keeps its calls."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    first = tip(kitchen)
    checks(kitchen, first, "success")
    copy = green.path()
    assert green.make(kitchen.checkout, copy, first) == ""
    kitchen.poll()
    assert at(copy) == first
    kitchen.copy, kitchen.first = copy, first
    return kitchen


def test_a_pass_moves_the_copy_to_main_s_new_green_tip_and_says_so_with_the_sha(copied):
    new = land(copied, "success")
    said = copied.poll()
    assert at(copied.copy) == new
    line = f"green demo: the commands now run from {new[:12]}, in place of {copied.first[:12]}"
    assert line in said
    assert copied.poll().count(line) == 0


TIMER = "[Timer]\nOnUnitActiveSec={}\n\n[Install]\nWantedBy=timers.target\n"
SERVICE = "[Service]\nType=oneshot\nExecStart=jbus tick\n"


READS = {"show", "show-environment", "list-units", "list-timers", "is-active", "is-enabled"}
READS |= {"status", "cat"}
"""The calls a pass makes to read systemd, which change nothing in it."""


def calls(log):
    """The calls that changed systemd, as the fake kept them."""
    kept = log.read_text().splitlines() if log.exists() else []
    return [one for one in kept if one.split()[1] not in READS]


def test_a_move_that_changes_a_timer_restarts_it_and_one_that_changes_no_unit_calls_nothing(
    copied, systemctl
):
    """The day of #1240: main set jbus-merge.timer to 2 s and the copy moved, but systemd kept
    the 5 s timer it had loaded until the home ran daemon-reload by hand. The units link through
    the copy, so a move that changes one reloads systemd and restarts each timer it changed."""
    units = "features/jbus/units/"
    land(copied, "success", {units + "jbus-merge.timer": TIMER.format("5s")})
    land(copied, "success", {units + "jbus-merge.service": SERVICE})
    copied.poll()
    systemctl.unlink(missing_ok=True)

    faster = land(copied, "success", {units + "jbus-merge.timer": TIMER.format("2s")})
    said = copied.poll()
    assert at(copied.copy) == faster
    assert calls(systemctl) == ["--user daemon-reload", "--user try-restart jbus-merge.timer"]
    assert "green demo: systemd reloaded jbus-merge.timer, and restarted jbus-merge.timer" in said

    systemctl.unlink()
    land(copied, "success", {units + "jbus-merge.service": SERVICE + "TimeoutStartSec=60\n"})
    said = copied.poll()
    assert calls(systemctl) == ["--user daemon-reload"]
    assert "green demo: systemd reloaded jbus-merge.service" in said

    systemctl.unlink()
    unchanged = land(copied, "success", {"features/new.txt": "new\n"})
    said = copied.poll()
    assert at(copied.copy) == unchanged
    assert calls(systemctl) == []
    assert not [line for line in said if "systemd" in line]


@pytest.fixture
def systemd(copied, systemctl, tmp_path, monkeypatch):
    """A systemctl that loads units as systemd does: a daemon-reload keeps the mtime of each unit
    file the copy links, through the link, and a unit owes a reload while the file behind its link
    is newer than the one systemd loaded, as `NeedDaemonReload` says. The unit folder is the
    test's own, and `link` links a unit into it through the copy, as the install does."""
    folder = tmp_path / "config" / "systemd" / "user"
    folder.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    loaded = copied.stub / "systemd.loaded"
    copied.stub.joinpath("systemctl").write_text(
        f"#!{sys.executable}\nimport json, pathlib, sys\n"
        f"open({str(systemctl)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[2:] == ['show-environment']:\n"
        "    print('HOME=' + __import__('os').environ['HOME'])\n"
        "if sys.argv[1:] == ['--user', 'daemon-reload']:\n"
        f"    units = pathlib.Path({str(copied.copy)!r}).glob({green.UNITS!r})\n"
        "    mtimes = {one.name: one.stat().st_mtime_ns for one in units}\n"
        f"    pathlib.Path({str(loaded)!r}).write_text(json.dumps(mtimes))\n"
    )
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)

    def owing():
        kept = json.loads(loaded.read_text())
        return sorted(
            one.name
            for one in copied.copy.glob(green.UNITS)
            if one.stat().st_mtime_ns > kept.get(one.name, 0)
        )

    def link(*names):
        for name in names:
            (folder / name).symlink_to(copied.copy / "features/jbus/units" / name)

    owing.link = link
    return owing


def test_a_move_that_changes_no_unit_leaves_no_unit_owing_systemd_a_reload(copied, systemd):
    """sa-checks-bound-measure-3: each move left jbus.service and jbus-merge.{service,timer} owing a
    reload, with "changed on disk" in `systemctl cat`, though no unit's content changed. systemd
    reads the file behind the link, and each tip's tree is a checkout of its own whose files are
    newer than the ones systemd loaded, so a reload truly owed looked like every other."""
    units = "features/jbus/units/"
    land(copied, "success", {units + "jbus-merge.timer": TIMER.format("2s")})
    land(copied, "success", {units + "jbus-merge.service": SERVICE})
    copied.poll()
    systemd.link("jbus-merge.timer", "jbus-merge.service")
    assert systemd() == []
    (copied.stub / "systemctl.log").unlink()

    unchanged = land(copied, "success", {"features/new.txt": "new\n"})
    said = copied.poll()
    assert at(copied.copy) == unchanged
    assert systemd() == []
    assert calls(copied.stub / "systemctl.log") == ["--user daemon-reload"]
    assert f"green demo: systemd reloaded the units of {unchanged[:12]}" in said


FOLLOWER = (
    "[Service]\nExecStart=jbus follow\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n"
)


@SYSTEMD
def test_a_move_to_a_main_that_adds_a_unit_links_enables_and_starts_it_once(
    copied, systemd, systemctl, tmp_path, monkeypatch
):
    """sa-follow-runs-live: #1255 added jbus-follow.service to main, and the move relinked the
    units already linked but linked no new one, so the follower ran only once someone ran
    jinstall. The move adds each unit the install would enable that has no link yet, services
    first, and a second move finds it there and adds nothing."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    units = "features/jbus/units/"
    land(copied, "success", {units + "jbus-merge.timer": TIMER.format("2s")})
    land(copied, "success", {units + "jbus-merge.service": SERVICE})
    copied.poll()
    systemd.link("jbus-merge.timer", "jbus-merge.service")
    systemctl.unlink()

    added = land(
        copied,
        "success",
        {units + "jbus-follow.service": FOLLOWER, units + "jbus-day.timer": TIMER.format("1d")},
    )
    said = copied.poll()
    assert at(copied.copy) == added
    folder = tmp_path / "config" / "systemd" / "user"
    for name in ("jbus-follow.service", "jbus-day.timer"):
        assert (folder / name).readlink() == copied.copy / units / name
    assert calls(systemctl)[:3] == [
        "--user daemon-reload",
        "--user enable --now jbus-follow.service",
        "--user enable --now jbus-day.timer",
    ]
    assert "green demo: linked, enabled and started jbus-follow.service, jbus-day.timer" in said
    assert gates(copied) == []

    systemctl.unlink()
    land(copied, "success", {"features/new.txt": "new\n"})
    said = copied.poll()
    assert not [line for line in calls(systemctl) if " enable " in line]
    assert not [line for line in said if "linked, enabled" in line]


@SYSTEMD
def test_a_pass_at_a_tip_whose_move_did_not_put_the_units_to_work_does_it_once(
    copied, systemd, systemctl, tmp_path, monkeypatch
):
    """sa-follow-live-each-pass: the move to 269cb479d, which added `live`, ran the jbus of before
    the move, which has no `live` step, so the follower was never linked, and each later pass found
    the copy at green and returned before `live`. A pass at a tip whose `live` stamp in
    `green.json` is not that tip's puts the units to work, and the next pass does nothing."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    units = "features/jbus/units/"
    land(copied, "success", {units + "jbus-merge.timer": TIMER.format("2s")})
    copied.poll()
    systemd.link("jbus-merge.timer")
    added = land(copied, "success", {units + "jbus-follow.service": FOLLOWER})
    copied.poll()
    assert at(copied.copy) == added
    folder = tmp_path / "config" / "systemd" / "user"
    (folder / "jbus-follow.service").unlink(missing_ok=True)
    kept = _pass(copied).state / green.FILE
    record = json.loads(kept.read_text()) if kept.exists() else {}
    kept.write_text(json.dumps({key: value for key, value in record.items() if key != "live"}))
    systemctl.unlink()

    said = copied.poll()
    assert at(copied.copy) == added
    follower = units + "jbus-follow.service"
    assert (folder / "jbus-follow.service").readlink() == copied.copy / follower
    assert "--user enable --now jbus-follow.service" in calls(systemctl)
    assert "green demo: linked, enabled and started jbus-follow.service" in said
    assert gates(copied) == []

    systemctl.unlink()
    said = copied.poll()
    assert not [line for line in calls(systemctl) if " enable " in line]
    assert not [line for line in said if "linked, enabled" in line]


@SYSTEMD
def test_a_new_unit_the_manager_will_not_enable_raises_a_condition_and_the_copy_still_moves(
    copied, systemd, systemctl, tmp_path, monkeypatch
):
    """An enable systemd refuses leaves the follower stopped, so the move says so as a condition
    of the tip, and the copy has moved all the same."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    units = "features/jbus/units/"
    land(copied, "success", {units + "jbus-merge.timer": TIMER.format("2s")})
    copied.poll()
    systemd.link("jbus-merge.timer")
    copied.stub.joinpath("systemctl").write_text(
        f'#!/bin/sh\necho "$*" >> {systemctl}\n'
        '[ "$2" = show-environment ] && { echo "HOME=$HOME"; exit 0; }\n'
        '[ "$2" = enable ] && { echo "Failed to enable unit: Access denied"; exit 1; }\nexit 0\n'
    )
    added = land(copied, "success", {units + "jbus-follow.service": FOLLOWER})
    said = copied.poll()
    assert at(copied.copy) == added
    assert gates(copied) == [f"condition green: {green.UNSTARTED}"]
    assert not [line for line in said if "linked, enabled" in line]


@SYSTEMD
def test_a_manager_that_reads_another_home_is_asked_for_no_reload(copied, systemd, systemctl):
    """A test or a sandbox runs a move under a HOME of its own, whose units link through its
    copy, while `systemctl --user` reaches the account's manager, which reads another HOME: the
    move asks that manager for nothing, as the install does."""
    copied.stub.joinpath("systemctl").write_text(
        f'#!/bin/sh\necho "$*" >> {systemctl}\n'
        '[ "$2" = show-environment ] && echo "HOME=/home/someone-else"\nexit 0\n'
    )
    systemd.link("jbus.timer")
    systemctl.unlink()
    land(copied, "success", {"features/jbus/units/jbus.timer": TIMER.format("1min")})
    said = copied.poll()
    assert calls(systemctl) == []
    assert gates(copied) == []
    assert not [line for line in said if "systemd" in line]


@SYSTEMD
def test_a_reload_systemd_refuses_raises_a_condition_and_restarts_no_timer(copied, systemctl):
    copied.stub.joinpath("systemctl").write_text(
        f'#!/bin/sh\necho "$*" >> {systemctl}\n'
        '[ "$2" = show-environment ] && { echo "HOME=$HOME"; exit 0; }\n'
        '[ "$2" = daemon-reload ] && { echo "Failed to connect to bus" >&2; exit 1; }\nexit 0\n'
    )
    moved = land(copied, "success", {"features/jbus/units/jbus.timer": TIMER.format("1min")})
    said = copied.poll()
    assert at(copied.copy) == moved
    assert calls(systemctl) == ["--user daemon-reload"]
    assert gates(copied) == [f"condition green: {green.UNRELOADED}"]
    assert not [line for line in said if "systemd reloaded" in line]


@SYSTEMD
def test_a_reload_systemd_refused_is_tried_again_by_each_pass_until_it_holds(copied, systemctl):
    """A move reloads once, so a reload systemd refused left the stale timer running, and every
    later pass found the copy at green and never asked again: the day of #1240 until a hand
    reload. The reload a move owes is kept until systemd takes every call of it."""
    units = "features/jbus/units/"
    land(copied, "success", {units + "jbus-merge.timer": TIMER.format("5s")})
    copied.poll()
    systemctl.unlink(missing_ok=True)

    (systemctl.parent / "systemctl.refuse").touch()
    faster = land(copied, "success", {units + "jbus-merge.timer": TIMER.format("2s")})
    said = copied.poll()
    assert at(copied.copy) == faster
    assert calls(systemctl) == ["--user daemon-reload"]
    assert gates(copied) == [f"condition green: {green.UNRELOADED}"]
    assert not [line for line in said if "systemd reloaded" in line]

    systemctl.unlink()
    said = copied.poll()
    assert at(copied.copy) == faster
    assert calls(systemctl) == ["--user daemon-reload", "--user try-restart jbus-merge.timer"]
    assert "green demo: systemd reloaded jbus-merge.timer, and restarted jbus-merge.timer" in said

    systemctl.unlink()
    said = copied.poll()
    assert calls(systemctl) == []
    assert not [line for line in said if "systemd" in line]


def test_a_tip_whose_check_failed_and_that_does_not_import_leaves_the_copy_where_it_was(copied):
    """The day of #923 and #935: main's tip fails to import jbus. Its check fails, so the copy,
    and so every command a pass runs, stays at the last green tip, and the pass runs on."""
    broken = land(copied, "failure", {"features/jbus/src/jbus/__init__.py": BROKEN})
    said = copied.poll()
    assert at(copied.copy) == copied.first
    assert not [line for line in said if line.startswith("green ")]
    assert green.imports(copied.copy) == ""
    fresh = copied.root / "fresh"
    copied.git("clone", "-q", str(copied.origin), str(fresh), cwd=copied.root)
    assert at(fresh) == broken
    assert "v007_drift is migration 8" in green.imports(fresh)


def test_a_tip_whose_check_passed_but_that_does_not_import_here_is_put_back(copied):
    broken = land(copied, "success", {"features/jbus/src/jbus/__init__.py": BROKEN})
    said = copied.poll()
    assert at(copied.copy) == copied.first
    assert f"green demo: {broken[:12]} does not import, kept {copied.first[:12]}" in said
    assert gates(copied) == [f"condition green: {green.NO_IMPORT}"]
    assert green.imports(copied.copy) == ""
    assert not [line for line in copied.poll() if line.startswith("green ")]


def test_the_copy_moves_on_once_a_later_tip_fixes_main(copied):
    land(copied, "failure", {"features/jbus/src/jbus/__init__.py": BROKEN})
    copied.poll()
    fixed = land(copied, "success", {"features/jbus/src/jbus/__init__.py": None})
    copied.poll()
    assert at(copied.copy) == fixed


def test_a_tip_that_changes_the_dependencies_is_imported_with_them_and_not_with_this_python(copied):
    """`uv tool install` reads `pyproject.toml`, so a tip that changes it is imported in an
    environment uv makes from it: one whose dependency cannot be had is refused here, and does not
    reach the tool, though this Python imports its code."""
    needs = 'dependencies = ["nowhere @ file:///nonexistent/nowhere"]'
    pyproject = f'[project]\nname = "demo"\nversion = "0"\n{needs}\n'
    unmet = land(copied, "success", {"pyproject.toml": pyproject})
    said = copied.poll()
    assert at(copied.copy) == copied.first
    assert f"green demo: {unmet[:12]} does not import, kept {copied.first[:12]}" in said
    assert gates(copied) == [f"condition green: {green.NO_IMPORT}"]
    assert sorted(path.name for path in green.trees(copied.copy).iterdir()) == [copied.first]


def test_a_move_points_the_copy_at_a_new_tree_and_leaves_the_last_one_whole(copied):
    """A move never rewrites a tree a command runs from: it makes the new tip's tree beside it and
    swaps the link in one rename, and the tree it named before stays whole until the next move."""
    before = copied.copy.resolve()
    new = land(copied, "success", {"features/new.txt": "new\n"})
    copied.poll()
    assert copied.copy.is_symlink()
    assert copied.copy.resolve() == green.trees(copied.copy) / new
    assert at(before) == copied.first
    assert not (before / "features/new.txt").exists()
    later = land(copied, "success")
    copied.poll()
    assert sorted(path.name for path in green.trees(copied.copy).iterdir()) == sorted([new, later])


def test_the_tool_runs_each_new_tip_once_it_moves_and_keeps_the_trees_it_may_run(
    copied, tmp_path, monkeypatch
):
    """uv's editable install names the tree the link points at, not the link, so each move
    installs the tool again from the new tree, and the command runs the new tip at once."""
    monkeypatch.setattr(green, "_reinstall", REINSTALL)
    monkeypatch.setattr(green, "IMPORTS", "import greendemo")
    monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("UV_TOOL_BIN_DIR", str(tmp_path / "bin"))
    tips = []
    for word in ("one", "two", "three"):
        files = {"src/greendemo/__init__.py": f"def main():\n    print({word!r})\n"}
        if word == "one":
            files["pyproject.toml"] = DEMO
        tips.append(land(copied, "success", files))
        copied.poll()
        ran = subprocess.run([tmp_path / "bin" / "greendemo"], capture_output=True, text=True)
        assert ran.stdout.strip() == word, ran.stderr
    kept = sorted(path.name for path in green.trees(copied.copy).iterdir())
    assert kept == sorted(tips[1:])


def test_a_tool_install_that_fails_puts_the_link_back_and_the_next_pass_tries_again(
    copied, monkeypatch, installs
):
    monkeypatch.setattr(green, "_reinstall", lambda copy: "error: no wheel")
    new = land(copied, "success")
    said = copied.poll()
    assert at(copied.copy) == copied.first
    assert sorted(path.name for path in green.trees(copied.copy).iterdir()) == [copied.first]
    assert gates(copied) == [f"condition green: {green.MOVE_FAILED}"]
    assert not [line for line in said if line.startswith("green ")]
    monkeypatch.setattr(green, "_reinstall", lambda copy: installs.append(copy.resolve()) or "")
    copied.poll()
    assert at(copied.copy) == new
    assert installs == [green.trees(copied.copy) / new]


def test_a_copy_of_another_checkout_is_left_alone(kitchen, tmp_path):
    other = tmp_path / "other-checkout"
    subprocess.run(["git", "clone", "-q", str(kitchen.origin), str(other)], check=True)
    copy = tmp_path / "copy"
    first = tip(kitchen)
    assert green.make(other, copy, first) == ""
    checks(kitchen, first, "success")
    kitchen.poll()
    land(kitchen, "success")
    kitchen.poll()
    green.move(_pass(kitchen), copy)
    assert at(copy) == first


def test_the_copy_records_its_checkout_and_fetches_from_the_checkout_s_origin(kitchen, tmp_path):
    copy = tmp_path / "copy"
    assert green.make(kitchen.checkout, copy, tip(kitchen)) == ""
    assert at(copy) == tip(kitchen)
    assert green.of(copy) == kitchen.checkout
    url = subprocess.run(
        ["git", "-C", str(copy), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert Path(url) == kitchen.origin
    assert green.make(kitchen.checkout, copy, tip(kitchen)) == f"{copy} is there already"
    assert green.of(tmp_path) is None
    nowhere = tmp_path / "nowhere"
    assert green.make(kitchen.checkout, nowhere, "f" * 40).startswith("git fetch: ffffffffffff")
    assert not nowhere.exists()


def test_a_crew_s_tests_import_their_own_tree_and_not_the_green_copy():
    """A crew runs `uv run pytest` in its worktree: the jbus under test is that tree's, wherever
    the green copy is."""
    assert Path(jbus.__file__).resolve().is_relative_to(REPO)
    assert not Path(jbus.__file__).resolve().is_relative_to(green.path())


def _pass(kitchen):
    config = jbus.load()
    return Pass(config, config.project("demo"), NOW)
