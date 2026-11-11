"""A `Status:` line, as every reader reads it: `jbriefs.status` turns it into one value, and the
home's awk that lists a scope's open plan entries reads it the same way."""

import re
import subprocess
from pathlib import Path

import pytest

from jbriefs import status
from jbriefs.status import Status

REPO = Path(__file__).resolve().parents[3]
SCOPED_HOMES = REPO / "features" / "home" / "skills" / "home" / "scoped-homes.md"

CASES = [
    ("Status: done", Status.DONE),
    ("Status: done (both ran the same cases)", Status.DONE),
    ("Status: done.", Status.DONE),
    ("Status: open", Status.OPEN),
    ("Status: left", Status.OTHER),
    ("Status: who knows", Status.OTHER),
    ("Status: done, mostly", Status.OTHER),
    ("Status: done: but", Status.OTHER),
    ("Status: not done", Status.NOT_DONE),
    ("Status: blocked, the bench is down", Status.BLOCKED),
    ("Status: paused, waits on a-b", Status.PAUSED),
    ("Status: paused: waits on a-b", Status.PAUSED),
    ("Status: answered (tea)", Status.ANSWERED),
    ("Status:", Status.NONE),
]


@pytest.mark.parametrize(("line", "value"), CASES)
def test_a_status_line_is_read_as_one_value(line, value):
    assert status.of(f"## Result\n{line}\nLeft: none\n") is value


def test_text_with_no_status_line_has_none():
    assert status.of("## Result\nLeft: none\n") is Status.NONE


def test_the_first_status_line_is_the_one_read():
    assert status.of("Status: open\nStatus: done\n") is Status.OPEN


def open_entries(plan: str, tmp_path: Path) -> list[str]:
    """Run the home's awk that lists a scope's plan entries that are not done, on `plan`, and
    return the headings it prints."""
    text = SCOPED_HOMES.read_text()
    (program,) = re.findall(r"awk '\n(\s+function entry\(\).*?)' \"\$plan\"", text, re.DOTALL)
    file = tmp_path / "plan.md"
    file.write_text(plan)
    ran = subprocess.run(["awk", program, str(file)], capture_output=True, text=True, check=True)
    return [one for one in ran.stdout.splitlines() if not one.startswith("Status:")]


def test_the_homes_awk_and_the_parser_agree_on_each_case(tmp_path):
    plan = "# demo, second: plan\n\n" + "".join(
        f"## e{at}: an entry\n{line}\n\n" for at, (line, _) in enumerate(CASES)
    )
    shown = open_entries(plan, tmp_path)
    assert shown == [
        f"e{at}: an entry" for at, (line, _) in enumerate(CASES) if status.of(line) != Status.DONE
    ]
