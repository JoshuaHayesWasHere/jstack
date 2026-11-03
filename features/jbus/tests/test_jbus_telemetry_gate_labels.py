"""`jbus telemetry` keeps each week's gate labels, and its view gives S8, the wrong closes of gates.

A scout writes `reports/gate-labels/<the week's first day>.tsv` in a project's home, by
`features/jbus/docs/jbus/gate-labels.md`; the gates are records of `questions.json`, as `jbus gate`
and `jbus answer` write them. The tests write both, run the real command, and read the store with
`sqlite3` as any reader would. S8 counts `corrected` and `other_done` over `stood`, `corrected`
and `other_done`, of the gates silence closed and, apart, of those the user's word closed, and
agrees with the weekly report's count over the same file (`jbus.ci.wrongcloses`).
"""

import contextlib
import sqlite3
from dataclasses import asdict
from datetime import date

import pytest

import jbus
from jbus import questions
from jbus.ci import wrongcloses
from jbus.questions import Answer, Question
from jbus.telemetry import labels
from test_jbus_telemetry import NOW, SECRET, Machine, dump, iso

WEEK = "2026-10-25"
COLUMNS = ("key", "week", "outcome", "outcome_evidence", "klass", "note", "shape")
"""The page's columns, then one more the store reads none of."""


@pytest.fixture
def machine(tmp_path, monkeypatch):
    return Machine(tmp_path, monkeypatch)


def gates(machine, project, closers):
    """Write the project's `questions.json` as `jbus gate` and `jbus answer` do, gate `n` closed by
    `closers[n - 1]`, None for open."""
    records = []
    for number, closer in enumerate(closers, 1):
        answer = None
        if closer is not None:
            answer = Answer(SECRET, "jbus", iso(NOW), "", True, closed_by=closer)
        one = Question(number, "row", "thread", SECRET, SECRET, "", "", iso(NOW), answer=answer)
        records.append(asdict(one))
    machine.write(project, "questions.json", {"next": len(records) + 1, "records": records})


def label(machine, project, week, rows, word="audit"):
    """Write the week's labels file in the project's home, each row `(key, outcome)`: its `week`
    column holds `word`, as the scout's first files did, since the file's name gives the week."""
    folder = machine.home_dir / project / "reports" / "gate-labels"
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(COLUMNS)]
    lines += [f"{key}\t{word}\t{outcome}\t{SECRET}\tdoor\t{SECRET}\tx" for key, outcome in rows]
    path = folder / f"{week}.tsv"
    path.write_text("\n".join(lines) + "\n")
    return path


S, W, H, C = questions.SILENCE, questions.COMMAND, questions.HOME, questions.CLEARED
ALPHA = [S, S, S, S, S, S, S, W, W, H, None, C]
"""alpha's gates: seven closed by silence, two by the user's word, one by `gates.md`, one open,
one cleared."""
LABELS = [
    ("alpha#1", "stood"),
    ("alpha#2", "stood"),
    ("alpha#3", "corrected"),
    ("alpha#4", "other_done"),
    ("alpha#5", "unknown"),
    ("alpha#6", "moot"),
    ("alpha#7", "open"),
    ("alpha#8", "stood"),
    ("alpha#9", "corrected"),
    ("alpha#10", "corrected"),
    ("alpha#11", "open"),
    ("alpha#12", "other_done"),
    ("beta#1", "other_done"),
]
"""One label of each outcome over silence's gates, the user's word's two, and the gates closed
any other way or still open, which S8 counts in neither share; `beta#1`, a gate of another
project labelled in alpha's home."""


def weekly(machine, week=WEEK):
    with contextlib.closing(machine.store()) as store:
        store.row_factory = sqlite3.Row
        found = store.execute("SELECT * FROM weekly_wrong_closes WHERE week = ?", (week,))
        row = found.fetchone()
    return dict(row) if row else None


def test_the_store_keeps_each_label_by_the_pages_columns_and_the_week_its_file_names(machine):
    gates(machine, "alpha", ALPHA)
    gates(machine, "beta", [S])
    label(machine, "alpha", WEEK, LABELS)

    assert "gate_labels 13" in machine.build()

    with contextlib.closing(machine.store()) as store:
        kept = dict(store.execute("SELECT key, outcome FROM gate_labels WHERE week = ?", (WEEK,)))
        columns = [row[1] for row in store.execute("PRAGMA table_info(gate_labels)")]
    assert kept == dict(LABELS)
    assert "shape" not in columns and "note" not in columns
    assert SECRET.encode() not in (machine.state_dir / "telemetry.sqlite").read_bytes()


def test_s8_counts_corrected_and_other_done_over_the_known_outcomes_each_closer_apart(machine):
    gates(machine, "alpha", ALPHA)
    gates(machine, "beta", [S])
    path = label(machine, "alpha", WEEK, LABELS)
    machine.build()

    found = weekly(machine)

    assert found == {
        "week": WEEK,
        "labels": 13,
        "silence": 5,
        "silence_wrong": 3,
        "silence_share": 60.0,
        "word": 2,
        "word_wrong": 1,
        "word_share": 50.0,
    }
    report = wrongcloses.week(path, date.fromisoformat(WEEK), wrongcloses.gates(jbus.load()))
    assert (report.silence.wrong, report.silence.of) == (found["silence_wrong"], found["silence"])
    assert (report.user.wrong, report.user.of) == (found["word_wrong"], found["word"])


@pytest.mark.parametrize("outcome", ["unknown", "moot", "open"])
def test_a_label_of_no_known_outcome_counts_in_neither_share(machine, outcome):
    gates(machine, "alpha", [S, W])
    label(machine, "alpha", WEEK, [("alpha#1", outcome), ("alpha#2", outcome)])
    machine.build()

    found = weekly(machine)

    assert (found["labels"], found["silence"], found["word"]) == (2, 0, 0)
    assert found["silence_share"] is None and found["word_share"] is None


def test_a_week_with_no_labels_file_has_no_row_and_each_file_is_its_own_week(machine):
    gates(machine, "alpha", ALPHA)
    label(machine, "alpha", "2026-10-18", [("alpha#1", "corrected")])
    label(machine, "alpha", WEEK, [("alpha#2", "stood")])
    (machine.home_dir / "alpha" / "reports" / "gate-labels" / "notes.tsv").write_text("key\n")
    machine.build()

    assert weekly(machine, "2026-10-18")["silence_share"] == 100.0
    assert weekly(machine, WEEK)["silence_share"] == 0.0
    assert weekly(machine, "2026-11-01") is None


def test_a_labels_file_written_again_replaces_its_weeks_labels(machine):
    gates(machine, "alpha", ALPHA)
    label(machine, "alpha", WEEK, [("alpha#1", "open"), ("alpha#2", "corrected")])
    machine.build()
    assert "nothing new" in machine.build()

    label(machine, "alpha", WEEK, [("alpha#1", "stood")])
    machine.build()

    found = weekly(machine)
    assert (found["labels"], found["silence"], found["silence_wrong"]) == (1, 1, 0)
    code, out = machine.run("--rebuild", str(machine.root / "again.sqlite"))
    assert code == 0, out
    with contextlib.closing(machine.store()) as store:
        built = sorted(store.execute("SELECT * FROM gate_labels").fetchall())
    with contextlib.closing(machine.store(machine.root / "again.sqlite")) as store:
        again = sorted(store.execute("SELECT * FROM gate_labels").fetchall())
    assert built == again
    assert dump(machine.state_dir / "telemetry.sqlite") == dump(machine.root / "again.sqlite")


def test_the_labels_in_each_projects_home_count_in_their_week(machine):
    gates(machine, "alpha", ALPHA)
    gates(machine, "beta", [S])
    label(machine, "alpha", WEEK, [("alpha#1", "corrected")])
    label(machine, "beta", WEEK, [("beta#1", "stood")])

    machine.build()

    found = weekly(machine)
    assert (found["labels"], found["silence"], found["silence_wrong"]) == (2, 2, 1)
    assert labels.FOLDER.as_posix() == wrongcloses.LABELS.as_posix()


def test_a_gate_two_homes_label_in_one_week_counts_once_whichever_file_was_read_last(machine):
    gates(machine, "alpha", ALPHA)
    label(machine, "alpha", WEEK, [("alpha#1", "corrected")])
    beta = label(machine, "beta", WEEK, [("alpha#1", "stood")])
    machine.build()
    beta.write_text(beta.read_text() + "alpha#2\taudit\tstood\t\t\t\n")
    machine.build()

    found = weekly(machine)
    assert (found["silence"], found["silence_wrong"]) == (2, 1)
    code, out = machine.run("--rebuild", str(machine.root / "again.sqlite"))
    assert code == 0, out
    with contextlib.closing(machine.store(machine.root / "again.sqlite")) as store:
        again = store.execute("SELECT silence, silence_wrong FROM weekly_wrong_closes").fetchall()
    assert again == [(2, 1)]
