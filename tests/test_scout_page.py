"""The scout's page: the block that serves it is run with and without `lavish-axi` on `PATH`."""

import os
import re
import subprocess

import pytest

import test_scout as scout
from test_grill_page import a_path_of
from test_prose_lines import unwrapped
from test_sweep import REPORT, settles

DISCONNECTED = "`status: browser_disconnected`"
NEEDED = ("sh", "git", "basename", "dirname", "realpath")


def run(scene, path, about):
    """Run the block of "Write it down" that holds `about`, as a scout does."""
    (block,) = [block for block in scout.given("Write it down") if about in block]
    (paths,) = scout.given()
    return subprocess.run(
        ["sh", "-c", f"{paths}\nS={scout.SLUG}\n{block}"],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(scene.user), "PATH": path},
        cwd=scene.worktree,
        check=False,
    )


@pytest.fixture
def scene(tmp_path):
    return scout.Scene(tmp_path)


@pytest.fixture
def stub(tmp_path):
    """A `PATH` whose `lavish-axi` prints its arguments."""
    path = a_path_of(tmp_path, *NEEDED)
    command = tmp_path / "only" / "lavish-axi"
    command.write_text('#!/bin/sh\necho "served: $*"\n')
    command.chmod(0o755)
    return path


def test_with_no_lavish_axi_the_block_says_there_is_no_page_and_why(scene, tmp_path):
    ran = run(scene, a_path_of(tmp_path, *NEEDED), "command -v lavish-axi")
    assert (ran.returncode, ran.stdout, ran.stderr) == (
        0,
        "no page: lavish-axi is not installed\n",
        "",
    )


def test_with_lavish_axi_the_block_says_a_page_is_built_and_serves_nothing(scene, stub):
    ran = run(scene, stub, "command -v lavish-axi")
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "page: lavish-axi is installed\n", "")


def test_with_lavish_axi_the_built_page_is_served(scene, stub):
    page = scene.home_dir / "reports" / f"{scout.SLUG}.html"
    ran = run(scene, stub, 'lavish-axi "$H')
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, f"served: {page}\n", "")


def test_the_block_named_for_a_closed_tab_serves_the_page_again(scene, stub):
    """The sentence on `browser_disconnected` names a section and a command: that block is run."""
    (said,) = [line for line in unwrapped(scout.SKILL.read_text()) if DISCONNECTED in line]
    section, command = re.search(r'the block of "([^"]+)" that runs `([^`]+)`', said).groups()
    assert [block.strip() for block in scout.given(section)].count(command) == 1
    page = scene.home_dir / "reports" / f"{scout.SLUG}.html"
    ran = run(scene, stub, command)
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, f"served: {page}\n", "")


def test_a_report_whose_page_is_none_for_want_of_lavish_axi_settles_the_scout(tmp_path):
    report = REPORT.format("done", "none, lavish-axi is not installed")
    assert settles(tmp_path, report) == ["settle"]


def test_the_poll_is_a_block_that_returns_only_when_the_poll_has(scene, tmp_path):
    """A poll in the background of the call would let the turn end with nobody listening."""
    path = a_path_of(tmp_path, *NEEDED, "sleep")
    command, heard = tmp_path / "only" / "lavish-axi", tmp_path / "heard"
    command.write_text(f'#!/bin/sh\nsleep 0.3\necho "answered: $*" > "{heard}"\n')
    command.chmod(0o755)
    (block,) = [block for block in scout.given("End") if "lavish-axi poll" in block]
    (paths,) = scout.given()
    ran = subprocess.run(
        ["sh", "-c", f"{paths}\nS={scout.SLUG}\n{block}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "HOME": str(scene.user), "PATH": path},
        cwd=scene.worktree,
        check=False,
    )
    page = scene.home_dir / "reports" / f"{scout.SLUG}.html"
    assert (ran.returncode, heard.read_text()) == (0, f"answered: poll {page}\n")
