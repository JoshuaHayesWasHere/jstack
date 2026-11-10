"""Drift (S4): each standing word has a probe that reads the code or the files it is about
(`jbus.drift`), and the KPI is the probes not held in each week's last run.

Each probe is run on a tree that keeps its word and on one that breaks it. A probe that raises is
`unrun`, never `held`, and keeps the name of what it raised and no word of its message. A run
appends one line a probe to `drift.jsonl`, all under one `at`, and a pass runs the probes at most
once a day of the user's. The real `jbus telemetry` keeps the lines (`jbus.telemetry.machine`), and
the real `jbus kpis` shows the week's last run on the page.
"""

import json
from datetime import timedelta

import pytest

import jbus
from jbriefs import findings
from jbus import drift, poll, rules
from test_jbus_kpi_page import Cells, run
from test_jbus_telemetry import NOW, SECRET, Machine


@pytest.fixture
def machine(tmp_path, monkeypatch):
    made = Machine(tmp_path, monkeypatch)
    monkeypatch.setattr(rules, "agent_homes", lambda: [tmp_path / "agent"])
    return made


def tree(machine, ketchup="Catch the user up, in plain lines.\n"):
    """A source tree whose `skills.json` lists the ketchup skill, with `ketchup` as its text."""
    root = machine.root / "tree"
    (root / "features" / "ketchup").mkdir(parents=True, exist_ok=True)
    (root / "features" / "ketchup" / "SKILL.md").write_text(ketchup)
    listed = {"items": [{"name": "ketchup", "kind": "skill", "path": "features/ketchup/SKILL.md"}]}
    (root / "skills.json").write_text(json.dumps(listed))
    return root


def ground(machine, now=NOW, **given):
    return drift.Ground(jbus.load(), now, given.pop("root", None) or tree(machine), **given)


def status(name, at):
    one = next(probe for probe in drift.PROBES if probe.name == name)
    return drift.probe(one, at).status


def test_d1_holds_while_a_later_warning_is_kept_for_the_days_row_and_breaks_otherwise(
    machine, monkeypatch
):
    assert status("D1", ground(machine)) == "held"
    assert status("D1", ground(machine, steps=lambda: {"notes.tell"})) == "broken"
    monkeypatch.setitem(findings._LATER[findings.REVIEW], "warning", findings.DROPPED)
    assert status("D1", ground(machine)) == "broken"


def test_d2_breaks_on_a_standing_md_or_an_auto_memory_file(machine):
    assert status("D2", ground(machine)) == "held"
    standing = machine.home_dir / "alpha" / "standing.md"
    standing.write_text("1. Always do the thing.\n")
    assert status("D2", ground(machine)) == "broken"
    standing.unlink()
    memory = machine.root / "agent" / "projects" / rules.memory_name(machine.root / "beta")
    (memory / "memory").mkdir(parents=True)
    (memory / "memory" / "a-rule.md").write_text("Always do the thing.\n")
    assert status("D2", ground(machine)) == "broken"


def test_d3_breaks_on_mermaid_in_the_ketchup_skill_in_any_case(machine):
    assert status("D3", ground(machine)) == "held"
    assert status("D3", ground(machine, root=tree(machine, "Draw it as a ```mermaid chart\n"))) == (
        "broken"
    )


def test_d4_breaks_on_a_dated_line_in_a_homes_notes_or_a_scopes(machine):
    notes = machine.home_dir / "alpha" / "notes.md"
    notes.write_text("# notes\n\nNothing dated here.\n")
    assert status("D4", ground(machine)) == "held"
    scope = machine.home_dir / "beta" / "web"
    scope.mkdir()
    (scope / "plan.md").write_text("# a plan\n")
    (scope / "home-id").write_text("mcp:1\n")
    (scope / "notes.md").write_text("- 2026-11-02: always do the thing\n")
    assert status("D4", ground(machine)) == "broken"


def pull(number, at, head, base="main"):
    """A pull request as GitHub lists it merged, and `merged.json` keeps it."""
    return {
        "number": number,
        "mergedAt": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headRefOid": head,
        "baseRefName": base,
        "mergeCommit": {"oid": f"{number:040d}"},
    }


def test_d6_names_each_merge_of_the_last_week_into_a_merged_base_that_jmerge_did_not_log(
    machine, monkeypatch
):
    config = machine.root / "c" / "config.toml"
    config.write_text(
        config.read_text().replace(
            'projectId = "alpha-id"', 'projectId = "alpha-id"\nmerge_bases = ["train"]'
        )
    )
    at = NOW - timedelta(hours=2)
    machine.write(
        "alpha", "queue.json", [{"slug": one} for one in ("by-jmerge", "by-hand", "another-era")]
    )
    machine.write(
        "alpha",
        "merged.json",
        {
            "by-jmerge": pull(10, at, "a" * 40),
            "by-hand": pull(11, at, "b" * 40),
            "dependabot/uv/x": pull(12, at - timedelta(days=2), "c" * 40),
            "another-era": pull(13, at, "d" * 40),
            "into-train": pull(14, at, "e" * 40, base="train"),
            "into-a-branch": pull(15, at, "f" * 40, base="someones-branch"),
            "last-month": pull(9, NOW - timedelta(days=9), "9" * 40),
        },
    )
    machine.append(
        "alpha",
        "merge.log",
        f'{at:%Y-%m-%d %H:%M} merged 10 by-jmerge {10:040d} "a title", revert: gh pr revert x',
        f"2026-10-10 21:34 merged 13 ps-lessons {'0' * 40}",
        home=True,
    )
    d6 = next(probe for probe in drift.PROBES if probe.name == "D6")
    (found,) = drift.run(ground(machine), [d6])
    assert (found.status, found.found) == ("broken", 4)
    (line,) = [json.loads(one) for one in (machine.state_dir / drift.FILE).read_text().splitlines()]
    assert sorted(line["breaches"], key=lambda one: one["number"]) == [
        {
            "project": "alpha",
            "number": 11,
            "base": "main",
            "mergedAt": "2026-10-28T13:00:00Z",
            "head": "b" * 40,
        },
        {
            "project": "alpha",
            "number": 12,
            "base": "main",
            "mergedAt": "2026-10-26T13:00:00Z",
            "head": "c" * 40,
        },
        {
            "project": "alpha",
            "number": 13,
            "base": "main",
            "mergedAt": "2026-10-28T13:00:00Z",
            "head": "d" * 40,
        },
        {
            "project": "alpha",
            "number": 14,
            "base": "train",
            "mergedAt": "2026-10-28T13:00:00Z",
            "head": "e" * 40,
        },
    ]
    monkeypatch.setattr(drift, "_ground", lambda config, now: ground(machine, now))
    (machine.home_dir / "alpha" / "standing.md").write_text("1. Always do the thing.\n")
    said = []
    drift._chore(jbus.load(), None, NOW + timedelta(days=1), said.append)
    (told,) = said
    assert "D2, D6 (" in told
    assert all(f"alpha #{number}" in told for number in (11, 12, 13, 14))
    assert not any(f"#{number}" in told for number in (9, 10, 15))


def test_a_probe_that_cannot_run_is_unrun_never_held_and_keeps_no_word_of_why(machine):
    def raises(_):
        raise ValueError(SECRET)

    words = (drift.Probe("D9", "m1", "2026-11-03", "a word", raises),)
    (found,) = drift.run(ground(machine), words)
    assert (found.status, found.error) == ("unrun", "ValueError")
    assert SECRET not in (machine.state_dir / drift.FILE).read_text()
    machine.write("alpha", "merged.json", {"alpha-one": {"number": 1, "mergedAt": "x"}})
    assert status("D6", ground(machine)) == "unrun"
    assert status("D3", ground(machine, root=machine.root / "no-tree")) == "unrun"


def test_a_run_appends_one_line_a_probe_under_one_at(machine):
    drift.run(ground(machine))
    drift.run(ground(machine, NOW + timedelta(minutes=1)))
    lines = [json.loads(one) for one in (machine.state_dir / drift.FILE).read_text().splitlines()]
    assert len(lines) == 2 * len(drift.PROBES)
    assert [one["probe"] for one in lines[: len(drift.PROBES)]] == [p.name for p in drift.PROBES]
    assert len({one["at"] for one in lines}) == 2
    assert {one["status"] for one in lines} == {"held"}


def test_the_pass_runs_the_probes_at_most_once_a_users_day(machine, monkeypatch):
    monkeypatch.setattr(drift, "_ground", lambda config, now: ground(machine, now))
    (chore,) = [one for one in poll.CHORES if one.run is drift._chore]
    config, said = jbus.load(), []
    for later in (0, 1, 3):
        chore.run(config, None, NOW + timedelta(hours=later), said.append)
    chore.run(config, None, NOW + timedelta(days=1), said.append)
    lines = (machine.state_dir / drift.FILE).read_text().splitlines()
    assert len(lines) == 2 * len(drift.PROBES)


def page_row(machine, week):
    out = machine.root / "page.html"
    code, said = run("--week", week, "--out", str(out), project="alpha")
    assert code == 0, said
    cells = Cells()
    cells.feed(out.read_text())
    return cells.rows["Drift: standing words broken (S4)"]


def test_the_kpi_is_the_probes_not_held_in_the_weeks_last_run(machine):
    machine.build()
    assert page_row(machine, "2026-10-28")[5] == "n/a n 0 no data"
    drift.run(ground(machine, NOW - timedelta(days=7)))
    (machine.home_dir / "alpha" / "notes.md").write_text("- 2026-10-27: a rule\n")
    drift.run(ground(machine, NOW - timedelta(days=1)))
    (machine.home_dir / "alpha" / "notes.md").unlink()
    (machine.home_dir / "alpha" / "standing.md").write_text("a rule\n")
    drift.run(ground(machine, NOW))
    machine.build()
    row = page_row(machine, "2026-10-28")
    assert row[3] == "≤ 0"
    assert row[4] == "0 n 5 met"
    assert row[5] == "1 n 5 missed"
