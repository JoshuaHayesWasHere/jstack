import os
import re
import subprocess

import pytest

from testing.paths import REPO

SKILLS = REPO / "skills"
LOG = SKILLS / "show-me-your-work" / "scripts" / "log.sh"
RUNS = SKILLS / "benchmark-checklist" / "scripts" / "runs.sh"
COLUMNS = ["ts", "phase", "decision", "why", "evidence", "result"]
CELLS = ["harness", "froze the harness", "one command gives the number", "commit 3a9f1c2", "open"]
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def log(path, *cells):
    return subprocess.run(["sh", str(LOG), str(path), *cells], capture_output=True, text=True)


def rows(path):
    return [line.split("\t") for line in path.read_text().splitlines()]


def test_the_first_row_comes_after_a_header_of_the_six_columns(tmp_path):
    path = tmp_path / "decisions.tsv"
    assert log(path, *CELLS).returncode == 0
    header, row = rows(path)
    assert header == COLUMNS
    assert STAMP.fullmatch(row[0])
    assert row[1:] == CELLS


def test_a_second_row_is_appended_and_the_header_is_written_once(tmp_path):
    path = tmp_path / "decisions.tsv"
    log(path, *CELLS)
    log(path, "a1", *CELLS[1:])
    assert [row[1] for row in rows(path)] == ["phase", "harness", "a1"]


def test_a_log_in_a_directory_that_is_not_there_yet_is_made(tmp_path):
    path = tmp_path / "audit" / "a-slug.tsv"
    assert log(path, *CELLS).returncode == 0
    assert len(rows(path)) == 2


def test_a_tab_or_a_newline_in_a_cell_does_not_break_the_row(tmp_path):
    path = tmp_path / "decisions.tsv"
    log(path, "a\tb", "two\nlines", "a\r\nreturn", "e", "r")
    _, row = rows(path)
    assert row[1:] == ["a b", "two lines", "a  return", "e", "r"]


@pytest.mark.parametrize("first", ["=", "+", "-", "@"])
def test_a_cell_a_spreadsheet_would_run_is_quoted(tmp_path, first):
    path = tmp_path / "decisions.tsv"
    log(path, "p", f"{first}SUM(A1)", "w", "e", "r")
    assert rows(path)[1][2] == f"'{first}SUM(A1)"


@pytest.mark.parametrize("cells", [CELLS[:4], [*CELLS, "one more"]])
def test_any_other_number_of_cells_is_refused_and_writes_nothing(tmp_path, cells):
    path = tmp_path / "decisions.tsv"
    done = log(path, *cells)
    assert done.returncode != 0
    assert "usage" in done.stderr
    assert not path.exists()


def block(skill, tmp_path, cells, before=""):
    """Run the one `sh` block of a skill with its placeholders filled, as a crewmate has it:
    the crew skill is a symlink under ~/.claude/skills, this skill has no link of its own,
    and the work is in another repo. Gives what it printed, and that repo."""
    (body,) = re.findall(
        r"^```sh\n(.*?)^```$", (SKILLS / skill / "SKILL.md").read_text(), re.M | re.S
    )
    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "crew").symlink_to(SKILLS / "crew")
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    filled = iter(cells)
    done = subprocess.run(
        ["sh", "-c", before + PLACEHOLDER.sub(lambda _: next(filled), body)],
        capture_output=True,
        text=True,
        cwd=work,
        env={**os.environ, "HOME": str(user)},
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    return done.stdout.splitlines(), work


def test_the_block_the_skill_gives_writes_a_row_into_the_worktrees_git_directory(tmp_path):
    said, work = block("show-me-your-work", tmp_path, CELLS)
    assert said == [f"{work}/.git/decisions.tsv: 1 rows"]
    header, row = rows(work / ".git" / "decisions.tsv")
    assert header == COLUMNS
    assert row[1:] == CELLS
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=work) == b""


def runs(*args):
    done = subprocess.run(["sh", str(RUNS), *args], capture_output=True, text=True)
    return done.returncode, [line.split("\t") for line in done.stdout.splitlines()], done.stderr


def test_two_sides_are_run_in_turn_and_each_run_is_a_row():
    code, printed, _ = runs("3", "true", "exit 3")
    assert code == 0
    assert printed[0] == ["round", "side", "seconds", "exit", "said"]
    each = printed[1:7]
    assert [(row[0], row[1], row[3]) for row in each] == [
        ("1", "A", "0"),
        ("1", "B", "3"),
        ("2", "A", "0"),
        ("2", "B", "3"),
        ("3", "A", "0"),
        ("3", "B", "3"),
    ]
    assert all(float(row[2]) >= 0 for row in each)


def test_each_side_gets_its_median_its_range_and_its_count_of_failed_runs():
    _, printed, _ = runs("3", "true", "exit 3")
    assert printed[7] == ["side", "runs", "failed", "median", "min", "max", "command"]
    a, b = printed[8:]
    assert (a[0], a[1], a[2], a[6]) == ("A", "3", "0", "true")
    assert (b[0], b[1], b[2], b[6]) == ("B", "3", "3", "exit 3")
    for side in (a, b):
        low, median, high = float(side[4]), float(side[3]), float(side[5])
        assert low <= median <= high


def test_the_median_is_of_the_time_the_command_took(tmp_path):
    count = tmp_path / "count"
    command = f'echo >> {count}; if [ "$(wc -l < {count})" -eq 2 ]; then sleep 0.8; fi'
    _, printed, _ = runs("3", command)
    side = printed[-1]
    assert float(side[3]) < 0.5 <= float(side[5])
    assert count.read_text().count("\n") == 3


def test_the_last_line_a_run_prints_is_kept_beside_it():
    _, printed, said = runs("1", "echo one; echo; echo '12\tpassed'", "echo oops >&2; exit 2")
    assert [row[3:] for row in printed[1:3]] == [["0", "12 passed"], ["2", "oops"]]
    assert said == ""
    assert runs("1", "true")[1][1][3:] == ["0", ""]


def test_a_command_with_a_backslash_is_printed_as_it_was_run():
    command = r"printf 'a\n' | grep -c '\.'"
    code, printed, said = runs("1", command)
    assert (code, said) == (0, "")
    assert len(printed) == 4
    assert printed[1][3:] == ["1", "0"]
    assert printed[-1][6] == command


def test_one_side_alone_is_a_baseline():
    code, printed, _ = runs("2", "true")
    assert code == 0
    assert [row[1] for row in printed[1:3]] == ["A", "A"]
    assert len(printed) == 5


@pytest.mark.parametrize("args", [[], ["3"], ["none", "true"], ["0", "true"]])
def test_no_count_or_no_command_is_refused(args):
    code, printed, said = runs(*args)
    assert code != 0
    assert printed == []
    assert "usage" in said


def test_the_block_the_checklist_gives_runs_both_commands_in_the_directory_it_is_run_in(tmp_path):
    said, work = block("benchmark-checklist", tmp_path, ["touch a", "touch b"], "ROUNDS=2\n")
    assert [line.split("\t")[:2] for line in said[1:5]] == [
        ["1", "A"],
        ["1", "B"],
        ["2", "A"],
        ["2", "B"],
    ]
    assert sorted(path.name for path in work.iterdir()) == [".git", "a", "b"]
