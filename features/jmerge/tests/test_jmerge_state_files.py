"""`jmerge` keeps its state in the homes' state, as jbus finds it, and writes each JSON file whole:
a run killed while it writes leaves the file as it was, never half of it."""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from jmerge import cli, rejudge


def test_the_repo_state_is_under_jbus_home_dir_with_home_elsewhere(tmp_path, monkeypatch):
    main = tmp_path / "checkouts" / "demo"
    main.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(main)], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("JBUS_HOME_DIR", str(tmp_path / "homes"))
    assert cli.state_of(main) == tmp_path / "homes" / "demo"
    monkeypatch.delenv("JBUS_HOME_DIR")
    assert cli.state_of(main) == tmp_path / "elsewhere" / ".local" / "state" / "home" / "demo"


def pull(number, head):
    return SimpleNamespace(number=number, head=head)


def test_a_base_merge_record_killed_mid_write_leaves_the_whole_file(tmp_path, monkeypatch):
    kept = rejudge.BaseMerge(tmp_path, tmp_path, [], run=True)
    kept.keep(pull(7, "a" * 40), "b" * 40, said="asked")
    before = (tmp_path / rejudge.NAME).read_text()

    def killed(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", killed)
    with pytest.raises(KeyboardInterrupt):
        kept.keep(pull(8, "c" * 40), "d" * 40, said="asked")
    assert (tmp_path / rejudge.NAME).read_text() == before
    monkeypatch.undo()
    assert set(json.loads(before)) == {"7"}
    assert kept.was(pull(7, "a" * 40), "b" * 40)["said"] == "asked"
    kept.keep(pull(8, "c" * 40), "d" * 40, said="asked")
    assert set(kept.known()) == {"7", "8"}
    assert sorted(path.name for path in Path(tmp_path).iterdir()) == [rejudge.NAME]
