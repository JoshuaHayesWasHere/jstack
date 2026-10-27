"""`jmerge` merges on the checks a repo names in a `required-checks` file in its state directory,
one name to a line, and on the check named `check` alone where the repo names none. A repo
whose workflows run no `borders` check still merges, and jstack, which names `check` and
`borders`, waits for both.

The tests run the command against the fake `gh` and real origin of `test_home_merge`, with
GitHub listing only the checks each test names."""

import json
import re

import pytest

import test_home_merge as merge
from jmerge import ready

BORDERS = merge.run("SUCCESS", "borders")
JSTACK = "check\nborders\n"


@pytest.fixture
def merged(tmp_path):
    return merge.Merged(merge.Home(tmp_path), tmp_path)


def listing(merged, *checks):
    """GitHub lists `checks` for the pull request and no other."""
    listed = json.loads((merged.home.stub / "list.json").read_text())
    listed[0]["statusCheckRollup"] = list(checks)
    (merged.home.stub / "list.json").write_text(json.dumps(listed))


def test_a_repo_that_names_no_checks_merges_on_check_alone(merged):
    listing(merged, merge.PASSED)
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_repo_that_names_check_and_borders_waits_for_a_borders_that_never_ran(merged):
    (merged.home.state / "required-checks").write_text(JSTACK)
    listing(merged, merge.PASSED)
    (said,) = merged.run()
    assert re.fullmatch(
        f"wait 7 {re.escape(merge.URL)}: borders has no run at [0-9a-f]{{12}}", said
    )
    assert merged.untouched()


def test_jstack_merges_once_check_and_borders_both_passed(merged):
    (merged.home.state / "required-checks").write_text(JSTACK)
    listing(merged, merge.PASSED, BORDERS)
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


@pytest.mark.parametrize(
    ("text", "required"),
    [
        ("", ("check",)),
        ("\n  \n", ("check",)),
        (JSTACK, ("check", "borders")),
        ("  test \nlint\ntest\n", ("test", "lint")),
    ],
)
def test_the_file_names_one_check_to_a_line_and_none_means_check(text, required):
    assert ready.required_of(text) == required
