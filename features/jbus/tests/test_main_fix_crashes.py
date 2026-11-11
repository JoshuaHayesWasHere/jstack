"""A pass that stops between two writes of main's revert or fix, or of a nightly's row, leaves
nothing the next pass loses: `features/jbus/spec/MainFix.tla`'s RevertSaid, RevertKnown and
FiledWhole, each at the write its TLC trace named before st-main-fix-crash-gaps.

Each test runs the real pass against the kitchen's fakes, stops one pass at a write as a timeout
or a reboot would (`Died`, which no step catches), and runs the next pass."""

import json
from datetime import timedelta

import pytest

import jbus.queue
from jbus import reverts, watch
from jmerge import mainjson
from jmerge import reverts as kept
from test_jbus_kitchen import NOW
from test_jbus_main_moved import move
from test_jbus_reverts import DONE, asked, red_merges
from test_jbus_watch import browser_red, browser_run, browser_runs


class Died(BaseException):
    """The pass stopped here, between two writes."""


def dies(monkeypatch, module, name, after=False):
    """Stop the next pass at `module.name`: before it writes, or just `after`. Return what puts
    the write back for the passes after it."""
    real = getattr(module, name)

    def stop(*args, **kwargs):
        if after:
            real(*args, **kwargs)
        raise Died(name)

    monkeypatch.setattr(module, name, stop)
    return lambda: monkeypatch.setattr(module, name, real)


def died(kitchen, now=NOW):
    with pytest.raises(Died):
        kitchen.poll(now)


def said(kitchen, slug):
    return [
        line
        for line in kitchen.lines("revert")
        if line.startswith(f"revert {slug}: ") and "jbus opened" in line
    ]


@pytest.mark.parametrize(
    ("name", "after"),
    [("_own", False), ("write_text", False), ("_keep", False), ("_keep", True)],
)
def test_a_revert_on_record_has_its_line_whichever_write_its_pass_stopped_at(
    kitchen, monkeypatch, name, after
):
    """RevertSaid. The trace: a pass recorded the revert in reverts.json and stopped before
    `run.find`, and every later pass read it as its own (`Keep.OPENED`), so events.jsonl never
    had its line. The record is now the last write: a pass stopped at any write before it leaves
    the revert to `known`, and one stopped just after it has said it."""
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    module = type(kitchen.home) if name == "write_text" else reverts
    if name == "write_text":
        real = module.write_text

        def stop(path, *args, **kwargs):
            if path.name == "revert-7-alpha.md":
                raise Died(name)
            return real(path, *args, **kwargs)

        monkeypatch.setattr(module, "write_text", stop)

        def back():
            monkeypatch.setattr(module, "write_text", real)

    else:
        back = dies(monkeypatch, module, name, after)
    died(kitchen)
    back()
    for minutes in (3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert list(kept.read(kitchen.state)) == [red]
    assert len(said(kitchen, "alpha")) == 1
    assert len(asked(kitchen, "pr revert")) == 1
    assert (kitchen.home / "tasks" / "revert-7-alpha.md").exists()
    assert (
        not (kitchen.state / reverts.OPENING).exists()
        or json.loads((kitchen.state / reverts.OPENING).read_text()) == {}
    )


def green_fix(kitchen):
    """Land a merge on the red main whose check passes, as a hand's merge or a fix row's does,
    before the next pass. Return it."""
    fixed = move(kitchen, "success")
    commits = json.loads((kitchen.stub / "commits.json").read_text())
    kitchen.set(
        "commits.json", [kitchen.commit(fixed, "fix: main (#878)", ago=timedelta(0))] + commits
    )
    pushed = json.loads((kitchen.stub / "push-runs.json").read_text())
    kitchen.set("push-runs.json", {**pushed, fixed: [{**DONE, "id": 601, "conclusion": "success"}]})
    return fixed


def test_a_revert_opened_by_a_pass_that_stopped_is_kept_once_main_is_green(kitchen, monkeypatch):
    """RevertKnown, World "hand". The trace: main went red, a pass opened the revert and stopped
    before its record, and a merge turned main green; no pass judged main red again, so nothing
    asked GitHub for the revert, and it stayed open with no record, which jmerge never merges and
    `reverts.close` never closes. Now `known` keeps it on the next pass, red or green, and
    `close` then closes it as it does any revert of a red main passed above."""
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    back = dies(monkeypatch, reverts, "_own")
    died(kitchen)
    back()
    assert kept.read(kitchen.state) == {}
    (opened,) = json.loads((kitchen.stub / "open.json").read_text())
    fixed = green_fix(kitchen)
    kitchen.poll(NOW + timedelta(minutes=30))
    assert mainjson.read(kitchen.state).green == fixed
    made = kept.read(kitchen.state)
    assert made == {red: kept.Revert(red, "alpha", "revert-7-alpha", "e" * 40, opened["url"])}
    assert len(said(kitchen, "alpha")) == 1
    (closed,) = asked(kitchen, "pr close")
    assert closed.startswith(f"pr close {opened['url']} --comment ") and fixed[:12] in closed
    assert len(asked(kitchen, "pr revert")) == 1


def test_a_revert_opened_by_a_pass_that_stopped_is_kept_though_github_s_compare_is_silent(
    kitchen, monkeypatch
):
    """RevertKnown, World "refuses". The trace: a pass opened the revert and stopped, and the next
    one got no answer from GitHub's compare (`Keep.UNANSWERED`) and filed a fix row, with the
    revert open and not on record. `known` keeps the revert before main is judged, so main's red
    reads as `Keep.OPENED`, and no fix row is filed beside it."""
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    back = dies(monkeypatch, reverts, "_own")
    died(kitchen)
    back()
    monkeypatch.setattr(reverts, "compared", lambda *_: None)
    late = NOW + reverts.READ_WAIT + timedelta(minutes=5)
    kitchen.poll(late)
    assert list(kept.read(kitchen.state)) == [red]
    assert [
        row for row in jbus.queue.load(kitchen.state) if row["slug"].startswith(mainjson.FIX)
    ] == []
    assert len(asked(kitchen, "pr revert")) == 1


def unfiled(kitchen, prefix):
    """The briefs `tasks/` holds under `prefix` that no queue row has."""
    rows = {row["slug"] for row in jbus.queue.load(kitchen.state)}
    return [
        path.stem
        for path in (kitchen.home / "tasks").glob(f"{prefix}*.md")
        if path.stem not in rows
    ]


@pytest.mark.parametrize(("module", "name"), [(jbus.queue, "add"), (watch, "copy_brief")])
def test_main_s_fix_brief_has_its_row_when_its_pass_stopped_and_the_next_reverts(
    kitchen, monkeypatch, module, name
):
    """FiledWhole, World "refuses". The trace: GitHub did not answer, so a pass wrote main's fix
    brief and stopped before queue.add; the next pass, answered, opened the revert, so the brief
    stayed in tasks/ with no row. The queue's row is now the first write and the brief's copy the
    second: a pass stopped before the row leaves nothing, and one stopped after it leaves the row,
    whose copy `brief_of` reads from the queue and its launch writes."""
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    answers = reverts.compared
    monkeypatch.setattr(reverts, "compared", lambda *_: None)
    late = NOW + reverts.READ_WAIT + timedelta(minutes=5)
    back = dies(monkeypatch, module, name)
    died(kitchen, late)
    back()
    monkeypatch.setattr(reverts, "compared", answers)
    kitchen.poll(late + timedelta(minutes=3))
    assert len(asked(kitchen, "pr revert")) == 1
    assert list(kept.read(kitchen.state)) == [red]
    assert unfiled(kitchen, mainjson.FIX) == []
    filed = [row["slug"] for row in jbus.queue.load(kitchen.state)]
    assert filed == ([f"{mainjson.FIX}{red[:12]}"] if name == "copy_brief" else [])
    assert all(jbus.queue.brief(kitchen.state, slug) for slug in filed)


@pytest.mark.parametrize(("module", "name"), [(jbus.queue, "add"), (watch, "copy_brief")])
def test_a_nightly_s_brief_has_its_row_when_its_pass_stopped_and_the_run_is_stale_by_the_next(
    kitchen, monkeypatch, module, name
):
    """FiledWhole, World "late". The trace: a pass wrote a nightly's brief and stopped before
    queue.add, and no pass ran for three days; the next one skipped the run as stale
    (`NIGHTLY_WINDOW`) and never wrote `seen`, so the brief had no row and the red run filed
    nothing. Now the row is the first write: the brief never stands alone, whatever the next
    pass makes of the run's age."""
    browser_runs(kitchen, browser_run())
    back = dies(monkeypatch, module, name)
    died(kitchen)
    back()
    kitchen.poll(NOW + watch.NIGHTLY_WINDOW + timedelta(hours=1))
    assert unfiled(kitchen, "browser-red-") == []
    rows = [row["slug"] for row in browser_red(kitchen)]
    assert rows == (["browser-red-2026-10-12"] if name == "copy_brief" else [])


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        json.dumps(["a"]),
        json.dumps({"f" * 40: "x", "e" * 40: {"branch": "b", "at": 3}}),
    ],
)
def test_a_pass_reverts_main_over_a_names_file_no_pass_could_have_written(kitchen, text):
    """An `OPENING` that does not parse, or names a revert with no branch or with a time no pass
    writes, as from a hand's edit, stops no pass: the next one reverts main's culprit and says it,
    and drops each name GitHub has no revert for."""
    (red,) = red_merges(kitchen, ("alpha", 7, None))
    (kitchen.state / reverts.OPENING).write_text(text)
    kitchen.poll(NOW)
    assert list(kept.read(kitchen.state)) == [red]
    assert len(said(kitchen, "alpha")) == 1
    assert json.loads((kitchen.state / reverts.OPENING).read_text()) == {}
