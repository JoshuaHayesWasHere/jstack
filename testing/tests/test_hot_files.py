"""`scripts/hot_files.py` prints, for each file in a date range, the merged pull requests that
touched it, the pairs of them that were open at once, and the rebases that dropped lines in it.

The test runs the script as a user runs it, with a temporary home that holds a `merge.log` and two
briefs. A fake `gh` on `PATH` answers from fixed pull requests and writes down what it was asked.
The test also runs the home skill's weekly block, with the same fake `gh`.

"""

import json
import os
import re
import subprocess
import sys
import textwrap
import time

from jmerge import ready
from test_home_thread import as_read
from testing.paths import REPO

SCRIPT = REPO / "scripts" / "hot_files.py"
SKILL = REPO / "features" / "home" / "skills" / "home" / "SKILL.md"
FENCED = re.compile(r"^```sh\n(.*?)^```", re.M | re.S)
URL = "https://github.com/o/r"
SHA = {name: name * 40 for name in "0123456789abcdef"}

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
    pull(3, "05T00:00:00", "06T00:00:00", ["a.md", "b.py", "docs/c.md"]),
    pull(4, "03T12:00:00", "05T12:00:00", ["a.md", *[f"gen/f{n:03}.txt" for n in range(1, 100)]]),
]


def dropped(head, *drops):
    """The reason of a jmerge wait for a rebase that dropped lines, in jmerge's own words:
    each drop is (file, main's lines, its own)."""
    lost = tuple(ready.Drop(file=file, mains=mains, own=own) for file, mains, own in drops)
    return ready.DROPPED.format(lost=ready._lost(lost), head=head * 12)


BOTH = dropped("a", ("a.md", 1, 0), ("b.py", 0, 2))
OTHER = "https://github.com/o/other"
LOG = f"""\
2026-09-20 10:00 wait 1 {URL}/pull/1: {dropped("e", ("a.md", 0, 9))}
2026-10-02 10:00 wait 1 {URL}/pull/1: {BOTH}
2026-10-02 10:05 merge 3 {URL}/pull/3
2026-10-02 10:30 wait 1 {URL}/pull/1: {BOTH}
2026-10-02 11:00 wait 1 {URL}/pull/1: {dropped("b", ("a.md", 0, 3))}
2026-10-03 09:00 hold 2 {URL}/pull/2: needs Josh, the rebase dropped 4 of main's lines in a.md
2026-10-03 09:10 wait 9 {OTHER}/pull/9: {dropped("c", ("a.md", 0, 5))}
"""

ONE = f"""\
# one: a task

## Result
Branch: one   Pull request: {URL}/pull/3
Rebase: patch changed in a.md b.py, before {SHA["a"]}, head {SHA["b"]}
Rebase: patch changed in a.md b.py, before {SHA["a"]}, head {SHA["b"]}
Rebase: patch unchanged, before {SHA["b"]}, head {SHA["c"]}
Rebase: patch changed in a.md, before {SHA["c"]}, head {SHA["d"]}
Rebase: patch changed in b.py and c.md, before {SHA["d"]}, head {SHA["1"]}
Rebase: patch changed in 2 feature files, before {SHA["1"]}, head {SHA["2"]}
"""
TWO = f"""\
# two: a task

## Result
Branch: two   Pull request: {URL}/pull/7
Rebase: patch changed in a.md, before {SHA["e"]}, head {SHA["f"]}
"""


def kitchen(tmp_path, pulls=PULLS):
    """Set up the fake `gh` and the home, and return the environment to run in and the home.

    a.md is open in four pull requests: #1 from the 1st to the 3rd, #2 from the 2nd to the
    4th, #4 from noon on the 3rd to noon on the 5th, and #3 from the 5th to the 6th. So three
    pairs overlap: #1 and #2, #2 and #4, and #4 and #3. #1 ends before #4 starts, and #1 and
    #3 are never open together. #4 lists 100 files, which is gh's cap.

    The merge.log records dropped lines for #1 at two heads, and logs one of those twice. It also
    records dropped lines for #2, in a hold line with no head: jmerge wrote hold lines in that form
    before they named the review. A drop before the range and a drop in another repo do not count.

    One brief is of #3, which merged in the range. Four rebases changed its patch, and the brief
    lists one of them twice. One of those lines names a file only by the last part of its path,
    after an "and", as briefs do. Another line names no file. The other brief is of #7, which did
    not merge in the range.
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
    """Each table's title and its rows, with the numbers as ints and the file as the last
    item."""
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
    assert merged[:4] == [(4, "a.md"), (2, "b.py"), (1, "docs/c.md"), (1, "gen/f001.txt")]
    assert len(merged) == 20
    assert pairs == [(3, "a.md")]
    assert drops == [(3, 8, 2, "a.md"), (1, 2, 2, "b.py"), (0, 0, 1, "docs/c.md")]


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

    assert ran.stderr.splitlines()[0] == (
        "undercounted: #4 lists 100 files, gh's cap, so a file past its 100th is not counted"
    )


def test_a_rebase_line_that_names_no_file_of_its_pull_request_is_named(tmp_path):
    env, home = kitchen(tmp_path)

    ran = run(env, "--since", "2026-10-01", "--until", "2026-10-07", "--home", str(home))

    assert ran.stderr.splitlines()[1:] == [
        "unread: one.md at 222222222222 names 2 feature files, no path of #3, so it is not counted"
    ]


def test_a_drop_outside_the_range_is_not_counted(tmp_path):
    env, home = kitchen(tmp_path)

    ran = run(env, "--since", "2026-10-03", "--until", "2026-10-07", "--home", str(home))

    assert tables(ran.stdout)[2][1] == [
        (1, 4, 2, "a.md"),
        (0, 0, 2, "b.py"),
        (0, 0, 1, "docs/c.md"),
    ]


def test_with_no_home_the_third_table_says_so(tmp_path):
    env, home = kitchen(tmp_path)

    ran = run(env, "--since", "2026-10-01", "--home", str(tmp_path / "nowhere"))

    title, rows = tables(ran.stdout)[2]
    assert rows == []
    assert "no merge.log" in title


def weekly(home):
    """The home skill's weekly block, with `$H` set to the home and `$T` set to the home feature's
    templates."""
    (found,) = [text for text in FENCED.findall(as_read(SKILL)) if "hot_files.py" in text]
    return f'H="{home}"\nT="{REPO / "features" / "home" / "templates"}"\n' + textwrap.dedent(found)


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
