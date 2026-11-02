"""`features/jbus/scripts/needs_replay.py` replays `jbus needs` over a week's records. The test runs
it over a small made-up week and checks each count it prints."""

import importlib.util
import json

from testing.paths import REPO

SCRIPT = REPO / "features" / "jbus" / "scripts" / "needs_replay.py"


def loaded():
    spec = importlib.util.spec_from_file_location("needs_replay", SCRIPT)
    made = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(made)
    return made


def gate(number, holds, closed_by, answered_by, answered_at="2026-10-28T12:00:00Z"):
    return {
        "project": "demo",
        "number": number,
        "slug": "alpha",
        "asked_at": "2026-10-28T09:00:00Z",
        "answered_at": answered_at,
        "answered_by": answered_by,
        "closed_by": closed_by,
        "default": "the first one",
        "holds": holds,
        "question": f"question {number}?",
    }


def row(slug, basis, approved_at):
    return {
        "project": "demo",
        "slug": slug,
        "t_first_record": "2026-10-28T09:00:00Z",
        "approval_ran_at": approved_at,
        "approval_basis": basis,
        "t_launched": None,
        "t_removed": None,
    }


def ask(at, text="what needs me?"):
    return {"project": "demo", "at": at, "week": "audit", "kind": "text", "text": text}


def written(tmp_path, **files):
    for name, records in files.items():
        (tmp_path / f"{name}.jsonl").write_text("".join(json.dumps(one) + "\n" for one in records))
    return tmp_path


def test_the_replay_counts_the_asks_it_answers_and_the_items_that_needed_no_one(tmp_path):
    dataset = written(
        tmp_path,
        messages=[
            ask("2026-10-28T10:00:00Z"),
            ask("2026-10-28T13:00:00Z", "Anything need me?"),
            ask("2026-10-28T10:00:00Z", "a word with no ask"),
        ],
        gates=[
            gate(1, "deletes data", "jbus answer", "user"),
            gate(2, "", "silence", "jbus"),
            gate(3, "", "jbus answer", "user"),
        ],
        rows=[
            row("by-rule", "rule", "2026-10-28T11:00:00Z"),
            row("by-word", "word", "2026-10-28T11:00:00Z"),
        ],
    )
    assert loaded().replay(dataset) == {
        "asks": 2,
        "answered": 2,
        "answered with items": 1,
        "answered with nothing waits": 1,
        "asks with a gate left out that the user answered later": 1,
        "items shown": 3,
        "items shown that needed no one": 1,
        "corrections, no Holds: line": 1,
        "old list items": 3,
        "old list items that needed no one": 1,
    }
