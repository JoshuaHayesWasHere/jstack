"""A pass keeps the scorecard's page: `scorecard.html` in jbus's state, each measure a row.

The tests seed a store with the real `telemetry.connect`, run the pass's chore as `jbus poll`
does, and read the page the child it starts writes, as its reader does: the band on top and the
rows by `data-measure`. The page names no row of the store.
"""

import re
import time
from datetime import UTC, datetime, timedelta

import jbus
from jbus import telemetry
from jbus.telemetry import measures, values
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
    store.execute(
        "insert into runs (project, key, at, workflow, event, created)"
        " values ('alpha', ?, ?, 'macos', 'pull_request', ?)",
        (SLUG, at, at),
    )
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
