"""A scratch home starts by the block of the home skill's `a-scratch-home.md`: in a thread of
no repo, it writes the thread's id to the `home-id` of the scratch home jbus lists. The block
is lifted from the skill as an agent reads it, and run against a `jbus` that prints a status."""

import json
import os
import subprocess

import pytest

from test_home_thread import block

THREAD = "mcp:scratch-thread"


def run(tmp_path, name="", scratch=("scratch",), repo=False):
    bin_dir, home, here = tmp_path / "bin", tmp_path / "me", tmp_path / "here"
    for made in (bin_dir, home, here):
        made.mkdir(exist_ok=True)
    status = {"scratch": {one: {"project_id": "p", "home_thread": ""} for one in scratch}}
    fake = bin_dir / "jbus"
    fake.write_text(f"#!/bin/sh\ncat <<'EOF'\n{json.dumps(status)}\nEOF\n")
    fake.chmod(0o755)
    if repo:
        subprocess.run(["git", "init", "-q", str(here)], check=True)
    text = block("home", "is the scratch home")
    text = text.replace("<threadId>", THREAD).replace("'<name>'", f"'{name}'")
    env = {
        "HOME": str(home),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
    }
    said = subprocess.run(["sh", "-c", text], cwd=here, env=env, capture_output=True, text=True)
    return said.stdout.strip(), home / ".local/state/home"


def test_the_one_scratch_home_jbus_lists_gets_this_threads_id(tmp_path):
    said, state = run(tmp_path)
    assert said.startswith(f"started: {THREAD} is the scratch home scratch")
    assert (state / "scratch" / "home-id").read_text() == f"{THREAD}\n"


def test_a_named_home_jbus_does_not_list_is_added_first_and_nothing_is_written(tmp_path):
    said, state = run(tmp_path, name="drafts")
    assert said.startswith("not added: jbus has no scratch home drafts")
    assert not (state / "drafts").exists()


@pytest.mark.parametrize("name", ["..", "../ab", "a/b"])
def test_a_name_with_a_path_in_it_writes_nothing_however_jbus_lists_the_homes(tmp_path, name):
    said, state = run(tmp_path, name=name, scratch=("ab",))
    assert said.startswith("not a name:")
    assert not (tmp_path / "me" / ".local").exists()


def test_a_name_is_matched_as_it_is_written_and_not_as_a_pattern(tmp_path):
    said, state = run(tmp_path, name="s.ratch")
    assert said.startswith("not added: jbus has no scratch home s.ratch")
    assert not state.exists()


@pytest.mark.parametrize("scratch", [(), ("one", "two")])
def test_with_none_or_many_listed_and_no_name_it_asks_which(tmp_path, scratch):
    said, state = run(tmp_path, scratch=scratch)
    assert said.startswith("which:")
    assert not state.exists()


def test_in_a_repo_it_starts_no_scratch_home(tmp_path):
    said, state = run(tmp_path, repo=True)
    assert said.startswith("not scratch:")
    assert not state.exists()
