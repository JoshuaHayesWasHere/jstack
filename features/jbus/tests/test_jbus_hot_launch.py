"""A pass does not launch a row while another row that names the same hot file runs or has its
pull request open (`jbus.dispatch`), and the queue says which file and which row it waits on
(`jbus.watch`). A file is hot once the `rebase` events of the last 7 days put it in 3 or more
conflicts with main (`jbus.hotfiles`). Like `test_jbus_queue.py`, the tests run the real pass
against a faked T3 Code server, `gh` and `jmerge`, over a real git checkout in which each conflict
is made."""

import json
import os
import subprocess
from datetime import timedelta

import pytest

import jbus
from jbus import hotfiles, rebase, wake
from repo_template import IDENTITY
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, brief, rows
from test_jbus_queue_remove import remove

HOT = "src/hot.py"
WAITS = f"waits on alpha: both name {HOT}, a file in 3 or more conflicts with main in 7 days"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    made.config(max_running=40)
    yield made
    made.close()


def git(kitchen, *args, at=NOW - timedelta(hours=2)):
    """Run git in the kitchen's checkout, with author and committer dated `at`, and return its
    output."""
    stamp = at.isoformat()
    env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    done = subprocess.run(
        ["git", *IDENTITY, *args],
        cwd=kitchen.checkout,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def commit(kitchen, path, text, at):
    file = kitchen.checkout / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)
    git(kitchen, "add", path, at=at)
    git(kitchen, "commit", "-q", "-m", f"{path}: {text.strip()}", at=at)
    return git(kitchen, "rev-parse", "HEAD", at=at)


def conflicts(kitchen, path, times, at=NOW - timedelta(hours=1)):
    """Put `path` in `times` conflicts with main: `times` heads each change it one way while main
    changes it another, and jbus tells each head's crew to rebase, as `jbus.rebase` words it, at
    `at`."""
    before = at - timedelta(hours=1)
    base = commit(kitchen, path, "base\n", before)
    heads = []
    for one in range(times):
        git(kitchen, "checkout", "-q", "-b", f"side-{path.replace('/', '-')}-{one}", base)
        heads.append(commit(kitchen, path, f"side {one}\n", before))
        git(kitchen, "checkout", "-q", "main")
    commit(kitchen, path, "main\n", before)
    git(kitchen, "push", "-q", "origin", "main")
    git(kitchen, "fetch", "-q", "origin")
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(wake.Box, "clock", staticmethod(lambda: at))
        for number, head in enumerate(heads, start=900):
            told(box, number, head)


def told(box, number, head):
    """Log the rebase message jbus sends the crew of pull request `number` at `head`."""
    slug = f"old-{number}"
    text = rebase.MESSAGE.format(
        default="main",
        number=number,
        reason="it conflicts with its base",
        slug=slug,
        short=head[:12],
        head=head,
    )
    line = f"rebase {slug}: told the crew (#{number}, {head[:12]})"
    assert box.send(slug, "rebase", line, text, key=rebase.mark("rebase", slug, head))


def naming(slug, *paths):
    """A brief whose `Where:` line names `paths`."""
    named = ", ".join(f"`{path}`" for path in paths)
    return brief(slug).replace(f"Where: `src/{slug}/`, a new test", f"Where: {named}")


def queue_two(kitchen, alpha=(HOT,), beta=(HOT,)):
    add(kitchen, "alpha", priority=1, text=naming("alpha", *alpha))
    add(kitchen, "beta", priority=2, text=naming("beta", *beta))


def launched(kitchen):
    crews = (one["title"] for one in kitchen.t3.launches if one["title"].startswith("crew: "))
    return [title.removeprefix("crew: ") for title in crews]


def crew(kitchen, slug, status):
    """Set the status of the thread jbus launched for `slug`'s crew."""
    (thread,) = (one for one in kitchen.t3.threads if one["title"] == f"crew: {slug}")
    thread["status"] = status
    if status != "running":
        kitchen.t3.at_work.discard(thread["threadId"])


def test_two_rows_naming_one_hot_file_launch_one_at_a_time(kitchen):
    conflicts(kitchen, HOT, 3)
    queue_two(kitchen)

    kitchen.poll()

    assert launched(kitchen) == ["alpha"]
    assert rows(kitchen)["beta"]["status"] == "queued"
    assert rows(kitchen)["beta"]["why"] == WAITS


def test_the_held_row_waits_while_the_first_runs_and_while_its_pull_request_is_open(kitchen):
    conflicts(kitchen, HOT, 3)
    queue_two(kitchen)
    kitchen.poll()
    crew(kitchen, "alpha", "running")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert launched(kitchen) == ["alpha"] and rows(kitchen)["beta"]["why"] == WAITS

    crew(kitchen, "alpha", "completed")
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll(NOW + timedelta(minutes=6))
    assert launched(kitchen) == ["alpha"] and rows(kitchen)["beta"]["why"] == WAITS

    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll(NOW + timedelta(minutes=9))
    assert launched(kitchen) == ["alpha", "beta"]


def test_the_held_row_launches_on_the_pass_after_the_first_is_removed(kitchen):
    conflicts(kitchen, HOT, 3)
    queue_two(kitchen)
    kitchen.poll()
    assert launched(kitchen) == ["alpha"]

    crew(kitchen, "alpha", "interrupted")
    code, said = remove(kitchen, "alpha")
    assert code == 0, said
    kitchen.poll(NOW + timedelta(minutes=3))

    assert launched(kitchen) == ["alpha", "beta"]


def test_a_file_in_two_conflicts_is_not_hot_and_both_rows_launch(kitchen):
    conflicts(kitchen, HOT, 2)
    queue_two(kitchen)

    kitchen.poll()

    assert launched(kitchen) == ["alpha", "beta"]


def test_conflicts_older_than_7_days_do_not_make_a_file_hot(kitchen):
    conflicts(kitchen, HOT, 3, at=NOW - timedelta(days=8))
    queue_two(kitchen)

    kitchen.poll()

    assert launched(kitchen) == ["alpha", "beta"]


def test_rows_whose_where_names_no_hot_file_launch_as_before(kitchen):
    conflicts(kitchen, HOT, 3)
    queue_two(kitchen, alpha=("src/alpha.py",), beta=("src/beta.py",))

    kitchen.poll()

    assert launched(kitchen) == ["alpha", "beta"]


def test_a_folder_on_the_where_line_does_not_name_the_hot_file_under_it(kitchen):
    """Only a path or glob that is the hot file holds a row: a folder would hold most rows, since
    most `Where:` lines name a feature's `src/` (scouts/conflict-avoidance.md)."""
    conflicts(kitchen, HOT, 3)
    queue_two(kitchen, beta=("src/",))

    kitchen.poll()

    assert launched(kitchen) == ["alpha", "beta"]


def test_a_glob_that_matches_the_hot_file_names_it(kitchen):
    conflicts(kitchen, HOT, 3)
    queue_two(kitchen, beta=("src/*.py",))

    kitchen.poll()

    assert launched(kitchen) == ["alpha"]
    assert rows(kitchen)["beta"]["why"] == WAITS


def test_a_held_row_waits_on_the_user_where_the_row_it_waits_on_does(kitchen):
    """The row out holds a pull request only the user may merge: that root unblocks the held row
    too (`jbus.stall`)."""
    conflicts(kitchen, HOT, 3)
    queue_two(kitchen)
    kitchen.poll()
    crew(kitchen, "alpha", "completed")
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.set("jmerge.txt", "hold 7 https://example.test/pull/7: needs user\n")

    kitchen.poll(NOW + timedelta(minutes=3))

    (event,) = kitchen.events("waiting-on-user")
    assert event["slug"] == "#7"
    assert kitchen.lines("waiting-on-user")[0].endswith("unblocks beta · since 11:03 ET")


def test_a_head_that_merges_cleanly_or_that_git_cannot_read_counts_no_conflict(kitchen):
    conflicts(kitchen, HOT, 2)
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(wake.Box, "clock", staticmethod(lambda: NOW - timedelta(hours=1)))
        told(box, 990, git(kitchen, "rev-parse", "main"))
        told(box, 991, "f" * 40)
    queue_two(kitchen)

    kitchen.poll()

    assert launched(kitchen) == ["alpha", "beta"]


def test_a_ledger_and_log_lines_that_are_not_records_are_passed_over(kitchen):
    """The hot list is a help, never a gate: what it cannot read gives fewer hot files, not a
    failed pass."""
    (kitchen.state / hotfiles.LEDGER).write_text("[]")
    log = kitchen.state / wake.LOG
    stray = {"event": "rebase", "at": "never", "text": f"refs/jstack/pre-rebase/x/a {'a' * 40}"}
    with log.open("a") as file:
        file.write("not a record\n" + json.dumps(stray) + "\n")
    conflicts(kitchen, HOT, 3)
    queue_two(kitchen)

    kitchen.poll()

    assert launched(kitchen) == ["alpha"]
    assert rows(kitchen)["beta"]["why"] == WAITS


def test_a_pass_with_no_log_launches_as_before(kitchen):
    queue_two(kitchen)
    (kitchen.state / wake.LOG).unlink(missing_ok=True)

    kitchen.poll()

    assert launched(kitchen) == ["alpha", "beta"]


def test_a_pass_asks_git_about_so_many_heads_and_the_next_goes_on_from_there(kitchen, monkeypatch):
    monkeypatch.setattr(hotfiles, "MOST", 2)
    conflicts(kitchen, HOT, 3)
    add(kitchen, "gamma", priority=1, text=naming("gamma", HOT))
    kitchen.poll()
    assert launched(kitchen) == ["gamma"]

    queue_two(kitchen)
    kitchen.poll(NOW + timedelta(minutes=3))

    assert launched(kitchen) == ["gamma"]
    assert rows(kitchen)["alpha"]["why"] == WAITS.replace("alpha", "gamma")
