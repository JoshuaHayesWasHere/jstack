"""A T3 Code build behind the patches jbus runs from waits on the user (po-build-behind-waits).

A merged change to jstack's T3 Code patches reaches the screen only after the user runs
`jinstall --setup` and opens T3 Code again. Each pass reads the series of the running build from
a stand-in `t3 --version`, the way the doctor does, and lists one `install` item while it is not
the series of the checkout's patches. The tests run the real pass and the real `jbus needs`
against the kitchen's fakes.
"""

import json
import subprocess
import time

import pytest

from jbus import green, t3build, verbs
from jinstall.kinds import patch_series
from test_jbus_kitchen import NOW

PACKAGING = "features/t3code-jstack/packaging"


@pytest.fixture
def machine(kitchen, tmp_path, monkeypatch):
    """A home whose T3 Code answers `t3 --version` with what `answer` writes."""
    home = tmp_path / "account"
    t3 = home / ".t3" / "bin" / "t3"
    t3.parent.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    def answer(said):
        t3.write_text(f"#!/bin/sh\necho '{said}'\n")
        t3.chmod(0o755)

    return answer


def patched(kitchen, name, text):
    """Commit one more patch to the checkout, with the PKGBUILD naming the new series, as a
    merged change to the patches does, and return the series."""
    folder = kitchen.checkout / PACKAGING
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)
    series = patch_series(folder)
    (folder / "PKGBUILD").write_text(f'pkgver="0.1.7.jstack.{series}"\n')
    kitchen.git("add", PACKAGING)
    kitchen.git("commit", "-q", "-m", f"patch {name}")
    return series


def installs(kitchen):
    listed = json.loads((kitchen.state / "waiting-on-user.json").read_text())
    return [one for one in listed if one["kind"] == "install"]


def needs(kitchen):
    kitchen.monkeypatch.setattr(verbs, "clock", lambda: NOW)
    code, out = kitchen.main("needs")
    assert code == 0, out
    return [line for line in out.splitlines() if "install" in line]


def test_build_behind_main_waits_on_the_user_until_the_installed_series_matches(kitchen, machine):
    old = patched(kitchen, "0001-tree.patch", "one\n")
    patched(kitchen, "0002-rows.patch", "two\n")
    new = patched(kitchen, "0003-menus.patch", "three\n")
    machine(f"t3 v0.1.7+jstack.{old}")
    kitchen.poll()
    [item] = installs(kitchen)
    assert item["key"] == "install:t3code-jstack"
    assert item["line"] == (
        f"install t3code-jstack: T3 Code runs the jstack build of series {old}, and the patches "
        f"jbus runs from are series {new}: the build lacks 2 merged changes to them; run "
        "jinstall --setup and then quit T3 Code and open it again"
    )
    assert needs(kitchen) == [
        f"demo {item['line']}, a T3 Code build only you can install",
        "  answer: nothing to reply: the next pass after the install takes it off",
    ]

    machine(f"t3 v0.1.7+jstack.{new}")
    kitchen.poll()
    assert installs(kitchen) == []
    assert needs(kitchen) == []


@pytest.mark.parametrize("said", ["t3 v0.1.7", None])
def test_build_behind_is_never_listed_with_no_jstack_build(kitchen, machine, said):
    patched(kitchen, "0001-tree.patch", "one\n")
    if said is not None:
        machine(said)
    kitchen.poll()
    assert installs(kitchen) == []


def test_build_behind_reads_the_green_copy_where_jbus_runs_from_one(kitchen, machine, tmp_path):
    """On the user's machine jbus runs from the green copy, and the checkout may be ahead of it:
    a build of the copy's patches is not behind, and one older than them lacks what the copy
    holds and it does not."""
    old = patched(kitchen, "0001-tree.patch", "one\n")
    held = patched(kitchen, "0002-rows.patch", "two\n")
    patched(kitchen, "0003-menus.patch", "three\n")
    copy = green.path()
    subprocess.run(["git", "clone", "-q", str(kitchen.checkout), str(copy)], check=True)
    subprocess.run(["git", "-C", str(copy), "checkout", "-q", "HEAD~1"], check=True)
    (copy / ".git" / green.MARK).write_text(f"{kitchen.checkout}\n")
    machine(f"t3 v0.1.7+jstack.{held}")
    kitchen.poll()
    assert installs(kitchen) == []
    machine(f"t3 v0.1.7+jstack.{old}")
    kitchen.poll()
    [item] = installs(kitchen)
    assert f"are series {held}: the build lacks 1 merged change to them;" in item["line"]


def test_build_behind_of_a_series_main_never_had_still_waits(kitchen, machine):
    new = patched(kitchen, "0001-tree.patch", "one\n")
    machine("t3 v0.1.7+jstack.0123456789")
    kitchen.poll()
    [item] = installs(kitchen)
    assert f"are series {new}: main's history does not hold the build's series" in item["line"]


def test_build_behind_a_t3_that_hangs_holds_no_pass(kitchen, machine, monkeypatch, tmp_path):
    patched(kitchen, "0001-tree.patch", "one\n")
    machine("t3 v0.1.7+jstack.0123456789")
    t3 = tmp_path / "account" / ".t3" / "bin" / "t3"
    t3.write_text("#!/bin/sh\nexec sleep 30\n")
    monkeypatch.setattr(t3build, "TIMEOUT", 0.5)
    started = time.monotonic()
    kitchen.poll()
    assert time.monotonic() - started < 10
    assert installs(kitchen) == []
