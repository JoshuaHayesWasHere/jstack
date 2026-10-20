"""`scripts/hot_files.py` prints, for a date range, the merged pull requests per file, the
pairs of them open at once per file, and the rebases that dropped lines per file.

The script is run as a user runs it, against a fake `gh` on `PATH` that answers from fixed
pull requests and writes down what it was asked, and a temporary home with a `merge.log` and
two briefs. The home skill's weekly block is run too, with the same fake `gh`."""

import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "hot_files.py"
SKILL = REPO / "skills" / "home" / "SKILL.md"
FENCED = re.compile(r"^```sh\n(.*?)^```", re.M | re.S)
URL = "https://github.com/o/r"
SHA = {name: name * 40 for name in "abcdef"}

GH = """\
#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GH/asked"
case "$1 $2" in
"pr list") cat "$FAKE_GH/prs.json" ;;
"repo view") printf '{"url": "%s"}\\n' "$FAKE_GH_URL" ;;
*) echo "fake gh: not this: $*" >&2; exit 1 ;;
esac
"""


def pull(number, created, merged, paths):
    """A merged pull request as `gh pr list --json number,files,createdAt,mergedAt` gives it."""
    return {
        "number": number,
        "createdAt": f"2026-10-{created}Z",
        "mergedAt": f"2026-10-{merged}Z",
        "files": [{"path": path, "additions": 1, "deletions": 0} for path in paths],
    }


PULLS = [
    pull(1, "01T00:00:00", "03T00:00:00", ["a.md", "b.py"]),
    pull(2, "02T00:00:00", "04T00:00:00", ["a.md"]),
    pull(3, "05T00:00:00", "06T00:00:00", ["a.md", "b.py"]),
    pull(4, "03T12:00:00", "05T12:00:00", ["a.md", *[f"gen/f{n:03}.txt" for n in range(1, 100)]]),
]

DROP = "the rebase dropped {lost} with no Dropped on rebase line at {head}"
BOTH = "1 of main's lines in a.md and 2 of its own in b.py"
OTHER = "https://github.com/o/other"
LOG = f"""\
2026-09-20 10:00 wait 1 {URL}/pull/1: {DROP.format(lost="9 of its own in a.md", head="e" * 12)}
2026-10-02 10:00 wait 1 {URL}/pull/1: {DROP.format(lost=BOTH, head="a" * 12)}
2026-10-02 10:05 merge 3 {URL}/pull/3
2026-10-02 10:30 wait 1 {URL}/pull/1: {DROP.format(lost=BOTH, head="a" * 12)}
2026-10-02 11:00 wait 1 {URL}/pull/1: {DROP.format(lost="3 of its own in a.md", head="b" * 12)}
2026-10-03 09:00 hold 2 {URL}/pull/2: needs Josh, the rebase dropped 4 of main's lines in a.md
2026-10-03 09:10 wait 9 {OTHER}/pull/9: {DROP.format(lost="5 of its own in a.md", head="c" * 12)}
"""

ONE = f"""\
# one: a task

## Result
Branch: one   Pull request: {URL}/pull/3
Rebase: patch changed in a.md b.py, before {SHA["a"]}, head {SHA["b"]}
Rebase: patch changed in a.md b.py, before {SHA["a"]}, head {SHA["b"]}
Rebase: patch unchanged, before {SHA["b"]}, head {SHA["c"]}
Rebase: patch changed in a.md, before {SHA["c"]}, head {SHA["d"]}
"""
TWO = f"""\
# two: a task

## Result
Branch: two   Pull request: {URL}/pull/7
Rebase: patch changed in a.md, before {SHA["e"]}, head {SHA["f"]}
"""


def kitchen(tmp_path, pulls=PULLS):
    """The fake `gh` and the home. The environment to run in, and the home.

    a.md is open in #1 (1st to 3rd), #2 (2nd to 4th), #4 (3rd noon to 5th noon) and #3 (5th
    to 6th): #1 and #2, #2 and #4, #4 and #3 overlap, three pairs. #1 ends before #4 starts,
    and #1 and #3 never meet. #4 lists 100 files, gh's cap.

    The merge.log drops lines for #1 at two heads, one logged twice, and for #2 in a hold line
    with no head. A drop before the range and one of another repo do not count.

    One brief is of #3, merged in the range: two rebases changed its patch, one of them written
    twice. The other is of #7, which did not merge in the range.
    """
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "gh").write_text(GH)
    (stub / "gh").chmod(0o755)
    (stub / "prs.json").write_text(json.dumps(pulls))
    home = tmp_path / "home"
    (home / "tasks").mkdir(parents=True)
    (home / "merge.log").write_text(LOG)
    (home / "tasks" / "one.md").write_text(ONE)
    (home / "tasks" / "two.md").write_text(TWO)
    env = {
        **os.environ,
        "PATH": f"{stub}:{os.environ['PATH']}",
        "FAKE_GH": str(stub),
        "FAKE_GH_URL": URL,
        "TZ": "UTC",
    }
    return env, home


def run(env, *args, cwd=None):
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )


def tables(printed):
    """Each table's title and its rows, the numbers as ints and the file last."""
    found = []
    for part in printed.strip().split("\n\n"):
        title, *rows = part.splitlines()
        cells = [row.split() for row in rows if row.split()[0].isdigit()]
        found.append((title, [(*map(int, cell[:-1]), cell[-1]) for cell in cells]))
    return found


def test_the_three_tables(tmp_path):
    env, home = kitchen(tmp_path)

    ran = run(env, "--since", "2026-10-01", "--until", "2026-10-07", "--home", str(home))

    (merged, title1), (pairs, _), (drops, title3) = [
        (rows, title) for title, rows in tables(ran.stdout)
    ]
    assert "4 pull requests" in title1
    assert merged[:3] == [(4, "a.md"), (2, "b.py"), (1, "gen/f001.txt")]
    assert len(merged) == 20
    assert pairs == [(3, "a.md")]
    assert drops == [(3, 8, 2, "a.md"), (1, 2, 1, "b.py")]


def test_it_asks_gh_for_the_range_in_local_days(tmp_path):
    env, home = kitchen(tmp_path)

    run(env, "--since", "2026-10-01", "--until", "2026-10-07", "--home", str(home))

    asked = (tmp_path / "stub" / "asked").read_text().splitlines()
    (listed,) = [line for line in asked if line.startswith("pr list")]
    assert listed == (
        "pr list --state merged --search"
        " merged:2026-10-01T00:00:00+00:00..2026-10-07T23:59:59+00:00"
        " --limit 1000 --json number,files,createdAt,mergedAt"
    )


def test_top_cuts_each_table(tmp_path):
    env, home = kitchen(tmp_path)

    ran = run(
        env, "--since", "2026-10-01", "--until", "2026-10-07", "--home", str(home), "--top", "1"
    )

    assert [rows for _, rows in tables(ran.stdout)] == [
        [(4, "a.md")],
        [(3, "a.md")],
        [(3, 8, 2, "a.md")],
    ]


def test_a_pull_request_at_the_file_cap_is_named_as_undercounted(tmp_path):
    env, home = kitchen(tmp_path)

    ran = run(env, "--since", "2026-10-01", "--until", "2026-10-07", "--home", str(home))

    assert ran.stderr.splitlines() == [
        "undercounted: #4 lists 100 files, gh's cap, so a file past its 100th is not counted"
    ]


def test_a_drop_outside_the_range_is_not_counted(tmp_path):
    env, home = kitchen(tmp_path)

    ran = run(env, "--since", "2026-10-03", "--until", "2026-10-07", "--home", str(home))

    assert tables(ran.stdout)[2][1] == [(1, 4, 2, "a.md"), (0, 0, 1, "b.py")]


def test_with_no_home_the_third_table_says_so(tmp_path):
    env, home = kitchen(tmp_path)

    ran = run(env, "--since", "2026-10-01", "--home", str(tmp_path / "nowhere"))

    title, rows = tables(ran.stdout)[2]
    assert rows == []
    assert "no merge.log" in title


def weekly(home):
    """The home skill's weekly block, with `$H` the home and `$T` this repo's templates."""
    (found,) = [text for text in FENCED.findall(SKILL.read_text()) if "hot_files.py" in text]
    return f'H="{home}"\nT="{REPO / "templates"}"\n' + textwrap.dedent(found)


def test_the_status_runs_it_once_a_week(tmp_path):
    env, home = kitchen(tmp_path)

    def status():
        ran = subprocess.run(
            ["sh", "-c", weekly(home)],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        return ran.stdout

    first = status()
    assert [rows[0][-1] for _, rows in tables(first)] == ["a.md", "a.md", "a.md"]
    assert all(len(rows) <= 5 for _, rows in tables(first))

    assert status() == ""

    stamp = home / "hot-files.stamp"
    old = time.time() - 8 * 24 * 3600
    os.utime(stamp, (old, old))
    assert tables(status())
