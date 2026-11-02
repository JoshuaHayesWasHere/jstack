"""The weekly report (`jbus ci --report`) gives S8, the wrong closes of gates, for each labelled
week, and queues the scout that labels the week that ended last.

Every test runs `jbus-ci.service`'s command in the kitchen, with GitHub's recorded answers. The
gates are records of `questions.json`, as `jbus gate` and `jbus answer` write them, and the labels
are files of `reports/gate-labels/` in the home, as the scout writes them. The two labelled weeks
hold the counts the gate-quality scout found by hand over the two weeks of the week audit
(`reports/gate-quality/tally.py` in the root home): base 12 of 91, audit 24 of 132.
"""

from dataclasses import asdict
from datetime import UTC, datetime

import pytest

import jbus
from jbus import questions, queue, verbs
from jbus.questions import Answer, Question
from jmerge import judgement
from test_jbus_ci import service
from test_jbus_kitchen import Kitchen
from test_jbus_queue import brief

BASE, AUDIT = "2026-10-18", "2026-10-25"
MONDAY = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
LABELS = ("key", "week", "outcome", "outcome_evidence", "klass", "note")


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.second()
    made.other = made.sides[0]
    path = made.config_dir / "config.toml"
    path.write_text(
        path.read_text().replace('state = "demo"\n', 'state = "demo"\nci_report = true\n')
    )
    yield made
    made.close()


def gates(state, made):
    """Write the gates `made`, each `(number, asked_at, closed_by)`, as `questions.json`: a
    `closed_by` of None is a gate still open."""
    records = []
    for number, asked, closed in made:
        answer = None
        if closed is not None:
            answer = Answer("q", "jbus" if closed == questions.SILENCE else "Josh", asked, "", True)
            answer = Answer(**{**asdict(answer), "closed_by": closed})
        records.append(
            Question(number, "row", "thread", f"q{number}?", "d", "", "", asked, answer=answer)
        )
    state.mkdir(parents=True, exist_ok=True)
    jbus.write_json(
        questions.path(state),
        {"next": len(records) + 1, "records": [asdict(one) for one in records]},
    )


def labels(home, first, rows):
    """Write the labels file of the week from `first`, each row `(key, outcome)`."""
    folder = home / "reports" / "gate-labels"
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(LABELS)]
    lines += [f"{key}\t{first}\t{outcome}\tevidence\tstanding\t" for key, outcome in rows]
    (folder / f"{first}.tsv").write_text("\n".join(lines) + "\n")


def week(project, first, n, silence, user, uncounted):
    """The gates of one week and their labels: `silence` and `user` are `(stood, corrected,
    other_done)` for the gates closed by silence and by the user's word; `uncounted` are labels
    S8 leaves out, each `(closed_by, outcome)`. Numbers start at `n`."""
    made, rows = [], []
    asked = f"{first}T16:00:00+00:00"
    for closed, outcomes in ((questions.SILENCE, silence), (questions.COMMAND, user)):
        for outcome, count in zip(("stood", "corrected", "other_done"), outcomes, strict=True):
            for _ in range(count):
                made.append((n, asked, closed))
                rows.append((f"{project}#{n}", outcome))
                n += 1
    for closed, outcome in uncounted:
        made.append((n, asked, closed))
        rows.append((f"{project}#{n}", outcome))
        n += 1
    return made, rows, n


def fortnight(kitchen):
    """The two labelled weeks. The base week's gates are all the demo project's. The audit week
    has its silence in the other project, so S8 reads every project's gates."""
    base, base_rows, n = week(
        "demo",
        BASE,
        1,
        silence=(17, 2, 2),
        user=(62, 2, 6),
        uncounted=[(questions.SILENCE, "unknown"), (questions.COMMAND, "moot")],
    )
    other, other_rows, _ = week(
        "other",
        AUDIT,
        1,
        silence=(88, 14, 10),
        user=(0, 0, 0),
        uncounted=[(None, "open"), (questions.HOME, "corrected"), (questions.CLEARED, "corrected")],
    )
    audit, audit_rows, n = week("demo", AUDIT, n, silence=(0, 0, 0), user=(20, 0, 0), uncounted=[])
    return base + audit, other, base_rows, other_rows + audit_rows, n


def run(kitchen, monkeypatch, now=MONDAY):
    monkeypatch.setattr(verbs, "clock", lambda: now)
    code, said, project = service(kitchen, monkeypatch)
    assert code == 0, said
    report = next((kitchen.home / "reports").glob("ci-week-*.md")).read_text()
    return said, report


def test_the_report_gives_s8_for_each_labelled_week_split_silence_and_the_user(
    kitchen, monkeypatch
):
    demo, other, base_rows, audit_rows, n = fortnight(kitchen)
    gates(kitchen.state, [*demo, (n, "2026-11-03T16:00:00+00:00", questions.SILENCE)])
    gates(kitchen.other.state, other)
    labels(kitchen.home, BASE, base_rows)
    labels(kitchen.home, AUDIT, audit_rows)

    said, report = run(kitchen, monkeypatch)

    shown = [line for line in report.splitlines() if line.startswith("- week from ")]
    assert shown[0] == "- week from 2026-10-18: 12 of 91 (13%); silence 4 of 21, your word 8 of 70"
    assert (
        shown[1] == "- week from 2026-10-25: 24 of 132 (18%); silence 24 of 112, your word 0 of 20"
    )
    assert shown[2].startswith("- week from 2026-11-01: not labelled yet")
    assert not any(char.isdigit() for char in shown[2].split(":", 1)[1].split(",")[0])
    assert len(shown) == 3
    assert "ci: S8 week from 2026-10-18: 12 of 91" in said


def test_a_week_with_no_labels_file_says_not_labelled_and_gives_no_number(kitchen, monkeypatch):
    gates(kitchen.state, [(1, "2026-11-02T16:00:00+00:00", questions.SILENCE)])

    _, report = run(kitchen, monkeypatch)

    (line,) = [line for line in report.splitlines() if line.startswith("- week from ")]
    assert line == (
        "- week from 2026-11-01: not labelled yet, scout-gate-labels-2026-11-01 labels it"
    )


def test_each_report_queues_one_scout_whose_one_output_is_the_weeks_labels_file(
    kitchen, monkeypatch
):
    gates(kitchen.state, [(1, "2026-11-02T16:00:00+00:00", questions.SILENCE)])
    gates(kitchen.other.state, [(4, "2026-11-07T23:00:00+00:00", questions.COMMAND)])

    run(kitchen, monkeypatch)
    run(kitchen, monkeypatch)

    slug = "scout-gate-labels-2026-11-01"
    rows = [row for row in queue.load(kitchen.state) if row["slug"].startswith("scout-")]
    assert [row["slug"] for row in rows] == [slug]
    text = (kitchen.state / "briefs" / f"{slug}.md").read_text()
    assert queue.requested(text) and queue.request_faults(slug, text) == []
    deliver = text.split("Deliver:\n", 1)[1].split("\nPlaybook:", 1)[0]
    assert deliver.count("\n- ") == 0 and deliver.startswith("- ")
    assert "`reports/gate-labels/2026-11-01.tsv`" in deliver and "the only output" in deliver
    assert "`features/jbus/docs/jbus/gate-labels.md`" in text
    assert "demo#1" in text and "other#4" in text
    assert "write nothing but `reports/gate-labels/2026-11-01.tsv`" in text


def test_the_scout_row_is_approved_by_rule_as_a_follow_up_of_the_rows_go(kitchen, monkeypatch):
    parent = brief("scorecard-s8")
    add = ["queue", "add", "scorecard-s8", "--priority", "1", "--entry", "gate-quality-rows"]
    assert kitchen.main(*add, stdin=parent)[0] == 0
    sha = judgement.brief_sha(parent)[:12]
    approve = ["queue", "approve", "scorecard-s8", "--word", kitchen.word(), "--sha", sha]
    assert kitchen.main(*approve)[0] == 0
    gates(kitchen.state, [(1, "2026-11-02T16:00:00+00:00", questions.SILENCE)])

    run(kitchen, monkeypatch)

    (row,) = [row for row in queue.load(kitchen.state) if row["slug"].startswith("scout-")]
    assert row["approved"] and "follow-up of scorecard-s8" in row["approved"]


def test_a_week_already_labelled_or_with_no_gate_queues_no_scout(kitchen, monkeypatch):
    gates(kitchen.state, [(1, "2026-10-27T16:00:00+00:00", questions.SILENCE)])
    labels(kitchen.home, AUDIT, [("demo#1", "stood")])

    _, report = run(kitchen, monkeypatch, now=datetime(2026, 11, 2, 15, 0, tzinfo=UTC))
    assert "- week from 2026-10-25: 0 of 1 (0%); silence 0 of 1, your word 0 of 0" in report

    _, report = run(kitchen, monkeypatch)
    assert "- week from 2026-11-01: not labelled, no gate was asked in it" in report
    assert not [row for row in queue.load(kitchen.state) if row["slug"].startswith("scout-")]
