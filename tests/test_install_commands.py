"""The commands part of `install.sh`, uv's tool `jstack`: an old one, one that lacks a command,
one of another checkout, one shadowed, and one whose editable paths lack a package root that
pyproject.toml lists, which `--check` says is `stale`, as an install from before a package moved
is. Run as `tests/test_install.py` runs it, against its fake `uv`."""

import pytest

from test_install import NAMES, PACKAGE_ROOTS, REPO, User, line_for


@pytest.fixture
def user(tmp_path):
    return User(tmp_path)


def test_a_tool_whose_editable_paths_miss_a_package_root_is_stale_and_is_installed_again(user):
    user.run()
    user.tool("jstack", REPO, NAMES, roots=["src"])
    lacking = " ".join(str(REPO / root) for root in PACKAGE_ROOTS if root != "src")
    assert line_for(user.run("--check")[1], "commands") == [
        f"old hard commands jstack -> stale: its editable paths lack {lacking}"
    ]
    assert user.run() == (0, user.every("ok"))
    assert user.said(user.uv_log)[-1] == f"tool install --editable {REPO} --reinstall"
    assert line_for(user.run("--check")[1], "commands") == ["ok hard commands jstack"]


def test_a_jgauge_tool_from_this_checkout_is_old_and_is_removed(user):
    user.tool("jgauge", REPO, NAMES[:4])
    code, said = user.run("--check")
    assert line_for(said, "commands") == [
        "old hard commands jstack -> tool jgauge, from before the rename, "
        f"lacks {' '.join(NAMES[4:])}"
    ]
    assert user.run() == (0, user.every("ok"))
    assert user.said(user.uv_log) == [
        "tool uninstall jgauge",
        f"tool install --editable {REPO} --reinstall",
    ]
    assert not (user.tools / "jgauge").exists()


def test_a_tool_that_lacks_a_command_is_old_and_is_installed_again(user):
    user.run()
    (user.bin / NAMES[-1]).unlink()
    (user.tools / "jstack" / "names").write_text(" ".join(NAMES[:-1]))
    assert line_for(user.run("--check")[1], "commands") == [
        f"old hard commands jstack -> lacks {NAMES[-1]}"
    ]
    assert user.run() == (0, user.every("ok"))
    assert (user.bin / NAMES[-1]).exists()


def test_a_program_that_is_not_uvs_is_never_replaced(user):
    theirs = user.bin / NAMES[0]
    user.write(theirs, "theirs\n")
    code, said = user.run()
    assert (code, line_for(said, "commands")) == (1, ["missing hard commands jstack"])
    assert theirs.read_text() == "theirs\n"
    assert user.said(user.uv_log) == [f"tool install --editable {REPO} --reinstall"]


def test_a_tool_from_another_checkout_is_old_and_uninstall_keeps_it(user):
    user.tool("jstack", "/elsewhere/jstack", NAMES)
    assert line_for(user.run("--check")[1], "commands") == [
        "old hard commands jstack -> an install of /elsewhere/jstack"
    ]
    code, said = user.run("--uninstall")
    assert (code, said) == (0, ["kept commands jstack -> an install of /elsewhere/jstack"])
    assert (user.tools / "jstack").is_dir()


def test_a_command_that_another_program_shadows_is_old(user):
    user.run()
    shadow = user.script("jbus", "#!/bin/sh\n")
    code, said = user.run()
    assert code == 1
    assert line_for(said, "commands") == [
        f"old hard commands jstack -> jbus is shadowed by {shadow}"
    ]
    assert len(user.said(user.uv_log)) == 1
