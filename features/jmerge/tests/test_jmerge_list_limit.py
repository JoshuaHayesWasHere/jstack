"""`jmerge` asks `gh pr list` for 100 open pull requests, the cap jbus's own lists use, where `gh`
gives 30 when it is not told a limit. A list that comes back full says so in its own line, and
keeps the records of every pull request, since the ones past the cap are still open.

The tests run the command against a fake `gh` that lists at most `--limit` pull requests, 30
when it is given none, as the real one does."""

import json

import pytest

import test_home_merge as merge

GH = """\
#!/bin/sh
echo "$*" >> "$STUB/calls"
case "$1 $2" in
    "pr list")
        limit=30
        while [ "$#" -gt 0 ]; do
            [ "$1" = "--limit" ] && limit=$2
            shift
        done
        jq ".[:$limit]" "$STUB/list.json" ;;
    "repo view") echo main ;;
    *) exit 64 ;;
esac
"""


def listed(number, head):
    return {
        "number": number,
        "url": f"https://example.test/pull/{number}",
        "title": f"feat: task {number}",
        "headRefName": f"task-{number}",
        "headRefOid": head,
        "baseRefName": "main",
        "mergeable": "MERGEABLE",
        "statusCheckRollup": merge.rollup((merge.PASSED,)),
        "files": [merge.file("a.txt")],
        "changedFiles": 1,
        "isDraft": False,
    }


@pytest.fixture
def home(tmp_path):
    home = merge.Home(tmp_path)
    (home.stub / "gh").write_text(GH)
    return home


def opened(home, count):
    (home.stub / "list.json").write_text(
        json.dumps([listed(number, merge.PUSHED) for number in range(1, count + 1)])
    )


def judged(said):
    return sorted(line.number for line in map(merge.lines.one, said) if line)


def test_thirty_one_open_pull_requests_are_all_judged(home):
    opened(home, 31)
    said = home.ready()
    assert home.code == 0
    assert judged(said) == list(range(1, 32))
    (asked,) = [call for call in merge.calls(home) if call.startswith("pr list --state open")]
    assert " --limit 100 " in f"{asked} "


def test_a_full_list_says_so_and_keeps_the_holds_of_the_pull_requests_past_it(home):
    opened(home, 101)
    (home.state / "holds.json").write_text(json.dumps({"101": merge.PUSHED}))
    said = home.run()
    assert judged(said) == list(range(1, 101))
    assert "listed: GitHub gave 100 open pull requests, the most jmerge asks for" in said[0]
    assert json.loads((home.state / "holds.json").read_text()) == {"101": merge.PUSHED}
