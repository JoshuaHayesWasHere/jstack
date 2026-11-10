"""A pass keeps the scorecard's page: `scorecard.html` in jbus's state, each measure a row.

The tests seed a store with the real `telemetry.connect`, run the pass's chore as `jbus poll`
does, and read the page the child it starts writes, as its reader does: the band on top and the
rows by `data-measure`. The page names no row of the store.
"""

import contextlib
import io
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta

import jbus
from jbus import cli, telemetry
from jbus.telemetry import measures, scorecard, values
from test_jbus_telemetry import Machine

SLUG = "w7-seeded-row-slug"
"""The slug of every row the seed writes, which the page must never show."""


def chore():
    return next(each for each in telemetry.CHORES if each.rank == 37)


def run(now, said):
    chore().run(jbus.load(), None, now, said.append)


def waited(file, until=lambda text: bool(text)):
    """The text of `file` once `until` holds of it, for up to a minute: the child is not waited
    for by the pass, so the test waits for it."""
    for _ in range(600):
        if file.is_file() and until(text := file.read_text()):
            return text
        time.sleep(0.1)
    raise AssertionError(f"{file} was not written")


def seed(path, now):
    store = telemetry.connect(path)
    at = (now - timedelta(seconds=30)).strftime(values.STAMP)
    store.executemany(
        "insert into runs (project, key, at, workflow, event, created)"
        " values ('alpha', ?, ?, 'macos', 'pull_request', ?)",
        [(f"{SLUG}.run{i}", at, at) for i in range(120)],
    )
    store.executemany("insert into builds (at, ms) values (?, 500)", [(at,) for _ in range(10)])
    store.execute("insert into builds (at, ms) values ('2026-11-04T12:00:00.000000Z', 330)")
    for key, (begins, ends) in enumerate([("queued", "launched"), ("launched", "failed")]):
        store.execute(
            "insert into transitions (project, key, at, slug, from_status, to_status)"
            " values ('alpha', ?, ?, ?, ?, ?)",
            (f"{SLUG}.{key}", at, SLUG, begins, ends),
        )
    store.close()


def test_a_pass_writes_the_page_once_in_fifteen_minutes(tmp_path, monkeypatch):
    machine = Machine(tmp_path, monkeypatch)
    now = datetime.now(UTC)
    seed(machine.state_dir / telemetry.FILE, now)
    page = machine.state_dir / telemetry.SCORECARD
    started = machine.state_dir / f".{telemetry.SCORECARD}.started"
    said = []

    run(now, said)
    text = waited(page, lambda text: text.endswith("</html>\n"))
    written = page.stat().st_mtime_ns
    run(now + timedelta(minutes=1), said)
    assert started.stat().st_mtime == now.timestamp()
    assert page.stat().st_mtime_ns == written
    assert said == []

    rows = re.findall(r"data-measure='([^']+)'", text)
    assert sorted(rows) == sorted(each.name for each in measures.MEASURES)
    band = re.search(r"<div class='band[^>]*>(.*?)</div>", text, re.S)
    assert band is not None
    assert "macos-on-prs" in band.group(1)
    assert SLUG not in text
    assert "<script" not in text and "http" not in text.replace("http-equiv", "")


def test_a_build_that_fails_is_one_line_on_the_next_pass(tmp_path, monkeypatch):
    """No store to read: the child refuses, and the next pass says so once, with no raise."""
    machine = Machine(tmp_path, monkeypatch)
    now = datetime.now(UTC)
    said = []
    run(now, said)
    log = waited(machine.state_dir / f".{telemetry.SCORECARD}.log")
    assert log.startswith("refused: no telemetry store to read")
    run(now + timedelta(minutes=1), said)
    run(now + timedelta(minutes=2), said)
    assert len(said) == 1 and said[0].startswith("scorecard: no page: refused:"), said
    assert not (machine.state_dir / telemetry.SCORECARD).exists()


def scorecard_out(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--project", "alpha", "scorecard", *argv])
    return code, out.getvalue()


def states(text):
    """Each row's state, by its measure's name, as the chip in the row shows it."""
    return dict(re.findall(r"data-measure='([^']+)'.*?<span class='chip s-(\w+)'>", text))


def test_jbus_scorecard_out_writes_the_page_and_says_how_many_of_each_state(tmp_path, monkeypatch):
    machine = Machine(tmp_path, monkeypatch)
    seed(machine.state_dir / telemetry.FILE, datetime.now(UTC))
    page = tmp_path / "out" / "scorecard.html"

    code, said = scorecard_out("--out", str(page))
    assert code == 0
    text = page.read_text()
    shown = states(text)
    assert set(shown) == {each.name for each in measures.MEASURES}
    counted = re.fullmatch(
        rf"scorecard: {re.escape(str(page))}: alpha: "
        r"(\d+) bad, (\d+) watch, (\d+) ok, (\d+) none\n",
        said,
    )
    assert counted is not None, said
    assert [int(n) for n in counted.groups()] == [
        list(shown.values()).count(state) for state in scorecard.STATES
    ]
    assert (shown["macos-on-prs"], shown["build-time"]) == ("bad", "bad")
    band = re.search(r"<div class='band[^>]*>(.*?)</div>", text, re.S)
    assert band is not None
    worst = band.group(1)
    assert worst.index("macos-on-prs") < worst.index("build-time"), "a wake measure comes first"
    assert "120 runs" in worst
    assert [file.name for file in page.parent.iterdir()] == ["scorecard.html"]


def test_a_query_that_fails_shows_its_kind_and_never_its_message(tmp_path, monkeypatch):
    """A store with no tables: every query fails, nothing is worse than its baseline, and no
    sparkline has a day."""
    Machine(tmp_path, monkeypatch)
    bare = tmp_path / "bare.sqlite"
    sqlite3.connect(bare).close()
    page = tmp_path / "scorecard.html"
    assert scorecard_out("--store", str(bare), "--out", str(page))[0] == 0
    text = page.read_text()
    assert "its query failed (OperationalError)" in text
    assert "no such table" not in text
    assert "are at or better than their baseline" in text
    assert "no value in 7 days" in text


def test_a_store_that_cannot_be_opened_is_refused(tmp_path, monkeypatch):
    Machine(tmp_path, monkeypatch)
    page = tmp_path / "scorecard.html"
    code, said = scorecard_out("--store", str(tmp_path / "none.sqlite"), "--out", str(page))
    assert (code, said.startswith("refused: no telemetry store to read")) == (2, True)
    assert not page.exists()


def test_a_config_with_no_project_has_no_page(tmp_path, monkeypatch):
    machine = Machine(tmp_path, monkeypatch)
    (tmp_path / "c" / "config.toml").write_text('server = "http://127.0.0.1:1"\n')
    said = []
    run(datetime.now(UTC), said)
    assert said == []
    assert sorted(machine.state_dir.glob(".scorecard*")) == []


def test_a_python_that_cannot_start_is_one_line(tmp_path, monkeypatch):
    Machine(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "no-python"))
    said = []
    run(datetime.now(UTC), said)
    assert len(said) == 1 and "could not be run" in said[0], said
