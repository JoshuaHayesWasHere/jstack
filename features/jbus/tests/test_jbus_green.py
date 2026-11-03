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
from jbus import green
from jbus.passes import Pass
from test_jbus_kitchen import NOW
from test_jbus_queue import gates

REPO = Path(__file__).resolve().parents[3]
BROKEN = 'raise ImportError("jbus.telemetry.migrations: v007_drift is migration 8")\n'


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


@pytest.fixture
def copied(kitchen, tmp_path, monkeypatch):
    """A kitchen whose checkout has a green copy at main's tip, which a first pass recorded as
    green, under a data home of the test's own."""
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
    assert Path(sys.prefix).resolve().is_relative_to(REPO)


def _pass(kitchen):
    config = jbus.load()
    return Pass(config, config.project("demo"), NOW)
