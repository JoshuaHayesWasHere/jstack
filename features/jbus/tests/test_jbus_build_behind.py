"""A T3 Code build behind the patches jbus runs from waits on the user (po-build-behind-waits).

A merged change to jstack's T3 Code patches reaches the screen only after the user runs
`jinstall --setup` and opens T3 Code again. Each pass reads the series of the running build from
a stand-in `t3 --version`, the way the doctor does, and lists one `install` item while it is not
the series of the checkout's patches. The tests run the real pass and the real `jbus needs`
against the kitchen's fakes.
"""

import json

import pytest

from jbus import verbs
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
        "jinstall --setup, then quit T3 Code and open it again"
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
