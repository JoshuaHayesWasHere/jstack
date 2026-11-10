"""One run of `jmerge` that may merge runs at a time, whoever started it: jbus's pass, jbus's
merge tick, or a hand run. A run waits for another to end, and with `--if-free` it does nothing
and exits 75, so the tick tries again on its next round. The tests run the command against a
real origin and a fake `gh` (`test_jmerge_fresh.py`), while the test holds the run lock as
another run would."""

import fcntl
import json
import os
import sys
import threading
import time

from jmerge import cli, lock
from test_jmerge_fresh import LINES
from test_jmerge_fresh import kitchen as kitchen


def held(kitchen):
    """Hold the run lock as another run of `jmerge` would, from another open of its file."""
    other = os.open(kitchen.home.state / lock.RUN, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return other


def asked(kitchen):
    """Whether the run asked GitHub anything: the fake `gh` keeps each call in `calls`."""
    return (kitchen.home.stub / "calls").exists()


def test_a_run_with_if_free_does_nothing_while_another_run_holds_the_lock(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    other = held(kitchen)
    said = kitchen.home.sh(f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge --if-free')
    assert kitchen.home.code == lock.BUSY
    assert said == [lock.BUSY_LINE.format(path=kitchen.home.state / lock.RUN)]
    assert not asked(kitchen)
    os.close(other)
    (merged,) = kitchen.run("--if-free")
    assert merged.startswith("merged 6 one ")


def test_a_run_waits_for_the_other_run_to_end_and_then_merges(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    other = held(kitchen)
    said = []
    waiting = threading.Thread(target=lambda: said.extend(kitchen.run()))
    waiting.start()
    time.sleep(1)
    assert waiting.is_alive() and not asked(kitchen)
    os.close(other)
    waiting.join(timeout=60)
    (merged,) = said
    assert merged.startswith("merged 6 one ")


def test_a_check_takes_no_lock(kitchen):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    other = held(kitchen)
    (ready,) = kitchen.run("--check")
    assert ready.startswith("ready 6 ")
    os.close(other)


STAMP = "2026-11-10T15:00:00+00:00"


def handed(kitchen, stamp, pulls=None):
    """The flags of a run jbus's pass hands the open list it kept (`jbus.pulls`), read at the pass
    `STAMP`, where the file holds `stamp`."""
    path = kitchen.tmp / "pulls.json"
    listed = list(kitchen.pulls.values()) if pulls is None else pulls
    path.write_text(json.dumps({"at": stamp, "default": "main", "pulls": listed}))
    return ["--if-free", "--pulls", str(path), "--pulls-at", STAMP]


def here(kitchen, monkeypatch, capsys, *flags):
    """Run `jmerge` with `flags` in this process, as `kitchen.run` does in a shell, and return its
    exit code and its lines."""
    home = kitchen.home
    state = home.user / ".local" / "state"
    for name, value in {
        "HOME": home.user,
        "JBUS_CONFIG_DIR": home.user / ".config" / "jbus",
        "JBUS_STATE_DIR": state / "jbus",
        "JBUS_HOME_DIR": state / "home",
        "PATH": f"{home.stub}:{os.environ['PATH']}",
        "STUB": home.stub,
        "ORIGIN": home.origin,
        "LOG": home.state / "merge.log",
    }.items():
        monkeypatch.setenv(name, str(value))
    monkeypatch.chdir(home.main)
    home.desk_checked()
    code = cli.main(list(flags))
    return code, capsys.readouterr().out.splitlines()


def test_a_run_jbus_hands_its_passs_list_asks_github_for_no_list_and_merges(
    kitchen, monkeypatch, capsys
):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    code, (merged,) = here(kitchen, monkeypatch, capsys, *handed(kitchen, STAMP))
    assert code == 0 and merged.startswith("merged 6 one ")
    assert kitchen.calls("pr list --state open") == [] and kitchen.calls("repo view") == []


def test_a_run_handed_a_list_another_pass_read_asks_github_for_its_own(
    kitchen, monkeypatch, capsys
):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    other = handed(kitchen, "2026-11-10T14:59:00+00:00")
    code, (merged,) = here(kitchen, monkeypatch, capsys, *other)
    assert code == 0 and merged.startswith("merged 6 one ")
    assert len(kitchen.calls("pr list --state open")) == 1


def test_a_run_by_hand_asks_github_for_its_list(kitchen, monkeypatch, capsys):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    code, (merged,) = here(kitchen, monkeypatch, capsys)
    assert code == 0 and merged.startswith("merged 6 one ")
    assert len(kitchen.calls("pr list --state open")) == 1


def test_a_run_handed_no_open_pull_request_asks_github_nothing_and_says_nothing(
    kitchen, monkeypatch, capsys
):
    assert here(kitchen, monkeypatch, capsys, *handed(kitchen, STAMP, [])) == (0, [])
    assert not asked(kitchen)


def test_a_handed_list_that_does_not_read_is_no_answer(kitchen, monkeypatch, capsys):
    flags = handed(kitchen, STAMP, [{"number": 6}])
    assert here(kitchen, monkeypatch, capsys, *flags) == (
        1,
        [f"wait: could not ask GitHub: {cli.UNREAD}"],
    )


def test_a_list_github_gave_that_is_not_json_is_no_answer(kitchen, monkeypatch, capsys):
    kitchen.crew("one", 6, {"a.txt": "ours\n" + LINES})
    (kitchen.home.stub / "list.json").write_text("<html>unicorn</html>")
    code, (said,) = here(kitchen, monkeypatch, capsys)
    assert code == 1 and said.startswith("wait: could not ask GitHub: ")
