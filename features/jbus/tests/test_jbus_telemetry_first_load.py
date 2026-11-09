"""`jbus telemetry` keeps a record of the crew first load each time the installed files change,
and `jbus kpis` shows the latest one as the week's "Crew first load, KB". `make lint` runs
`python -m jbus.telemetry.firstload --check`, which fails a role whose start is over its budget.

The first load is what a `/crew` thread reads of jstack's before its work: the crew `SKILL.md`
and what `jbus playbook crewmate` prints, the largest print of the crewmate playbooks. The tests
count it by hand, from the file and from the real command's output, and compare the store's
record with that count. A copy of the install, its `skills.json`, crew skill and playbooks, takes
a changed `SKILL.md`.
"""

import contextlib
import io
import json
import runpy
import shutil
import sqlite3
import sys
from datetime import UTC, datetime

import pytest

import jsettings
from jbriefs import skills
from jbus import cli
from jbus.telemetry import firstload
from test_jbus_kpi_page import page_of
from test_jbus_telemetry import Machine

NAME = "Crew first load, KB (jstack's own)"


@pytest.fixture
def machine(tmp_path, monkeypatch):
    return Machine(tmp_path, monkeypatch)


@pytest.fixture
def install(tmp_path, monkeypatch):
    """A copy of the install's `skills.json`, crew skill and playbooks, which the store counts."""
    real, copy = skills.root(), tmp_path / "install"
    copy.mkdir()
    shutil.copy(real / "skills.json", copy / "skills.json")
    for path in [skills.where("skill", "crew"), *skills.listed("playbook").values()]:
        if path.is_file():
            target = copy / path.relative_to(real)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, target)
    monkeypatch.setattr(firstload, "REPO", copy)
    return copy


def printed(name):
    """What `jbus playbook crewmate --name <name>` prints, as bytes."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli.main(["playbook", "crewmate", "--name", name]) == 0
    return out.getvalue().encode()


def kept(machine):
    with contextlib.closing(sqlite3.connect(machine.state_dir / "telemetry.sqlite")) as store:
        found = store.execute(
            "SELECT hash, bytes, skill_bytes, playbook, playbook_bytes, files FROM first_loads "
            "ORDER BY at, key"
        )
        return [(*row[:5], json.loads(row[5])) for row in found]


def test_the_record_is_the_crew_skill_and_the_largest_playbook_print_counted_by_hand(machine):
    machine.build()

    [(_, total, skill_bytes, largest, print_bytes, files)] = kept(machine)
    skill = skills.where("skill", "crew")
    prints = {
        name: len(said)
        for name in skills.listed("playbook")
        if (said := printed(name)).startswith(b"/")
    }
    assert skill_bytes == len(skill.read_bytes())
    assert print_bytes == max(prints.values()) == prints[largest]
    assert total == skill_bytes + print_bytes
    assert files == {
        "features/crew/SKILL.md": skill_bytes,
        **{f"jbus playbook crewmate --name {name}": size for name, size in prints.items()},
    }


def test_a_changed_skill_md_gives_a_new_record_and_an_unchanged_install_none(machine, install):
    machine.build()
    machine.build()
    [first] = kept(machine)

    skill = install / "features" / "crew" / "SKILL.md"
    before = skill.read_bytes()
    skill.write_bytes(before + b"One more line a crew reads first.\n")
    assert "first_loads 1" in machine.build()
    machine.build()
    second = kept(machine)[1]
    assert second[0] != first[0]
    assert second[1] == first[1] + len(b"One more line a crew reads first.\n")

    skill.write_bytes(before)
    machine.build()
    assert [row[0] for row in kept(machine)] == [first[0], second[0], first[0]]


def test_a_changed_playbook_gives_a_new_record(machine, install):
    machine.build()
    path = skills.listed("playbook", install)["bug-fix"]
    path.write_text(path.read_text() + "\n99. A step more.\n")
    machine.build()

    first, second = kept(machine)
    name = "jbus playbook crewmate --name bug-fix"
    assert first[0] != second[0]
    assert second[5][name] == first[5][name] + len(b"99. A step more.\n")


def test_the_kpi_page_shows_the_latest_first_load_in_kb_against_16(machine):
    machine.build()
    [(_, total, *_)] = kept(machine)

    today = jsettings.load().local(datetime.now(UTC)).date()
    _, rows, _ = page_of(machine, today.isoformat())

    row = rows[NAME]
    kb = f"{round(total / 1000, 1):g}"
    assert row[3] == "≤ 16 KB"
    assert row[5] == f"{kb} KB n 1 {'met' if total / 1000 <= 16 else 'missed'}"
    assert row[4] == "n/a n 0 no data"


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A copy of every file a role's start is counted from: `skills.json`, the files it lists,
    this repo's own skills and each role's start files; `BUDGET` set to each role's count."""
    real, copy = skills.root(), tmp_path / "tree"
    catalog = json.loads((real / "skills.json").read_text())
    paths = [item["path"] for item in catalog["items"]]
    paths += [f"{own['path']}/SKILL.md" for own in catalog["projectSkills"]]
    paths += [name for _, files in firstload.ROLES.values() for name in files]
    for name in ["skills.json", *paths]:
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(real / name, target)
    monkeypatch.setattr(firstload, "REPO", copy)
    for role, start in firstload.starts(copy).items():
        monkeypatch.setitem(firstload.BUDGET, role, start.tokens)
    return copy


def checked(capsys):
    code = firstload.main(["--check"])
    return code, capsys.readouterr().out


def line_of(role):
    """The line of `BUDGET` that gives `role` its number, in the module's own source."""
    source = firstload.__file__
    with open(source) as text:
        lines = text.read().splitlines()
    table = lines.index("BUDGET = {")
    at = next(
        n for n, line in enumerate(lines, 1) if n > table and line.startswith(f'    "{role}": ')
    )
    return f"features/jbus/src/jbus/telemetry/firstload.py:{at}"


def test_a_start_at_its_budget_passes_and_one_character_over_fails(tree, capsys):
    skill = tree / "features" / "crew" / "SKILL.md"
    characters = firstload.starts(tree)["crew"].characters
    budget = (characters // 29 + 1) * 10
    skill.write_text(skill.read_text() + "x" * (budget * 29 // 10 - characters))
    firstload.BUDGET["crew"] = budget

    code, out = checked(capsys)
    assert code == 0, out
    lines = out.splitlines()
    assert [line.split(":")[0] for line in lines] == ["crew", "reviewer", "scout", "home"]
    assert lines[0] == f"crew: {budget * 29 // 10} characters, {budget} tokens, budget {budget}"

    skill.write_text(skill.read_text() + "x")
    code, out = checked(capsys)
    assert code == 1
    assert (
        f"fault: crew: {budget + 1} tokens, over its budget of {budget}: cut its start, "
        f"or raise its budget at {line_of('crew')}"
    ) in out


def test_a_budget_more_than_ten_percent_above_the_count_fails(tree, capsys):
    characters = firstload.starts(tree)["scout"].characters
    firstload.BUDGET["scout"] = characters * 11 // 29
    assert checked(capsys)[0] == 0

    tokens = firstload.starts(tree)["scout"].tokens
    firstload.BUDGET["scout"] = -(-tokens * 111 // 100)
    code, out = checked(capsys)
    assert code == 1
    assert (
        f"fault: scout: {tokens} tokens, its budget of {firstload.BUDGET['scout']} is more than "
        f"10% above: lower it at {line_of('scout')}"
    ) in out


def test_a_start_file_that_is_not_there_fails(tree, capsys):
    (tree / "features" / "pr-review" / "the-review.md").unlink()

    code, out = checked(capsys)
    assert code == 1
    assert "fault: reviewer: features/pr-review/the-review.md is not there" in out


def test_the_module_run_as_make_lint_runs_it_prints_a_line_a_role(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["firstload"])
    with pytest.raises(SystemExit) as ended:
        runpy.run_module("jbus.telemetry.firstload", run_name="__main__")
    assert ended.value.code == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in lines[:4]] == ["crew", "reviewer", "scout", "home"]
