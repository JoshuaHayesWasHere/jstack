"""`jmerge` keeps its state in the homes' state, as jbus finds it, and writes each JSON file whole:
a run killed while it writes leaves the file as it was, never half of it."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from jmerge import cli, rejudge


def test_the_repo_state_is_under_jbus_home_dir_with_home_elsewhere(tmp_path, monkeypatch):
    main = tmp_path / "checkouts" / "demo"
    monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("JBUS_HOME_DIR", str(tmp_path / "homes"))
    assert cli.homes_state(main) == tmp_path / "homes" / "demo"
    monkeypatch.delenv("JBUS_HOME_DIR")
    assert cli.homes_state(main) == tmp_path / "elsewhere" / ".local" / "state" / "home" / "demo"


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


WRITER = """
import sys
from pathlib import Path
import jbus
path, mark = Path(sys.argv[1]), sys.argv[2]
for n in range(150):
    jbus.write_json(path, {"by": mark, "n": n})
"""


def test_two_runs_writing_holds_at_once_both_finish_and_leave_one_whole_file(tmp_path):
    """A hand run of jmerge overlaps jbus's run, and both write holds.json: neither write fails."""
    holds = tmp_path / "holds.json"
    runs = [
        subprocess.Popen(
            [sys.executable, "-c", WRITER, str(holds), str(mark)], stderr=subprocess.PIPE
        )
        for mark in range(4)
    ]
    assert [(run.wait(), run.stderr.read()) for run in runs] == [(0, b"")] * 4
    assert json.loads(holds.read_text())["n"] == 149
    assert [path.name for path in tmp_path.iterdir()] == ["holds.json"]
