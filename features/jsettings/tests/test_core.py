"""The core's helpers, one definition each: paths, the store, the runner and the brief's head."""

import json
import os
import subprocess

import pytest

from jsettings import brief, paths, proc, store


def test_the_homes_state_is_jbus_home_dir_or_under_the_home(tmp_path):
    assert paths.homes_dir({}, tmp_path) == tmp_path / ".local" / "state" / "home"
    named = {"JBUS_HOME_DIR": str(tmp_path / "homes")}
    assert paths.homes_dir(named, tmp_path) == tmp_path / "homes"


def test_a_worktree_is_of_its_main_checkouts_repo(tmp_path):
    main = tmp_path / "demo"
    main.mkdir()
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "one"]):
        proc.git(main, "-c", "user.name=t", "-c", "user.email=t@example.com", *args)
    proc.git(main, "worktree", "add", "-q", "--detach", str(tmp_path / "other"))
    assert paths.main_checkout(tmp_path / "other") == main
    assert paths.repo_name(tmp_path / "other") == "demo"
    assert paths.repo_name(tmp_path) == ""


def test_a_json_file_is_written_whole_in_the_form_it_is_asked_for(tmp_path):
    path = tmp_path / "deep" / "one.json"
    store.write_json(path, {"b": 1, "a": 2})
    assert path.read_text() == '{\n  "a": 2,\n  "b": 1\n}\n'
    store.write_json(path, {"b": 1, "a": 2}, indent=None, sort_keys=False, mode=0o600)
    assert path.read_text() == '{"b": 1, "a": 2}\n'
    assert path.stat().st_mode & 0o777 == 0o600
    assert [one.name for one in path.parent.iterdir()] == ["one.json"]
    assert store.read_dict(path) == {"b": 1, "a": 2}
    assert store.read_json(tmp_path / "none.json", []) == []


def test_records_are_added_to_a_log_one_line_each(tmp_path):
    path = tmp_path / "deep" / "log.jsonl"
    store.append_jsonl(path, [{"b": 1, "a": 2}], mode=0o600)
    store.append_jsonl(path, [{"b": 3, "a": 4}, {"c": 5}], sort_keys=True)
    store.append_jsonl(path, [])
    assert path.read_text() == '{"b": 1, "a": 2}\n{"a": 4, "b": 3}\n{"c": 5}\n'
    assert path.stat().st_mode & 0o777 == 0o600


def test_a_lock_another_holds_is_refused_at_once_when_asked_not_to_wait(tmp_path):
    with store.locked(tmp_path / "state", "one.lock"):
        with pytest.raises(BlockingIOError), store.locked(tmp_path / "state", "one.lock", False):
            pass
    with store.locked(tmp_path / "state", "one.lock", wait=False):
        pass


def test_a_command_that_cannot_run_or_runs_too_long_fails_like_any_other(tmp_path):
    missing = proc.run("no-such-program-anywhere", cwd=tmp_path)
    assert isinstance(missing, proc.Unrun) and missing.returncode == 127
    slow = proc.run("sleep", "5", timeout=0.1)
    assert isinstance(slow, proc.TimedOut) and slow.returncode == 127
    assert "timed out" in slow.stderr
    done = proc.run("sh", "-c", "cat; echo $ONE", stdin="in ", env={**os.environ, "ONE": "1"})
    assert (type(done), done.returncode, done.stdout) == (subprocess.CompletedProcess, 0, "in 1\n")
    assert proc.ask(["sh", "-c", "exit 1"]) is None
    assert proc.ask(["echo", "hi"]) == "hi\n"


def test_a_line_is_read_from_the_head_of_a_brief_and_not_below_it():
    text = "# one\nStack: a 1 on b\nStack: c\n## Result\nHome: x\n"
    assert brief.head_lines(text) == ["# one", "Stack: a 1 on b", "Stack: c"]
    assert brief.head(text, "Stack:") == "a 1 on b"
    assert brief.head(text, "Home:") is None


@pytest.mark.parametrize(
    ("report", "page"),
    [("Page: reports/a.html\n", "reports/a.html"), ("Page: none, why\n", ""), ("", "")],
)
def test_a_report_names_its_last_page(report, page):
    assert brief.page(report) == page


def test_a_locked_list_is_written_as_it_always_was(tmp_path):
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class One:
        since: str
        id: str

    kept = store.LockedList("list.json", "list.lock", lambda raw: [One(**one) for one in raw])
    kept.change(tmp_path, lambda was: [*was, One("2026", "b")])
    assert (tmp_path / "list.json").read_text() == json.dumps(
        [{"since": "2026", "id": "b"}], indent=2
    ) + "\n"
    assert kept.read(tmp_path) == [One("2026", "b")]
