"""`jbus queue add` warns of a brief whose `Proves it:` or `Done when:` asks a crewmate to run the
whole suite at the desk: a `make check-fast` with no `PART=`, or a bare `make check` where the
home's `fresh-check` names a `make check-fast`. The desk's check is the touched one, and CI's check
on the pull request runs the whole selection. The brief is queued all the same. The test runs the
real command against a faked T3 Code server, as `test_jbus_kitchen.py` does."""

import pytest

from test_jbus_kitchen import Kitchen
from test_jbus_queue import brief

FAST = "jgauge test-slot -- make check-fast BASE=origin/main\n"
TOUCHED = "the touched check, `make check-fast BASE=<base> PART=touched`"
WHOLE = "`make check-fast BASE=origin/main` passes"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def added(kitchen, done, proves, check=None):
    """Queue alpha with `done` as its one Done when: item and `proves` as its Proves it: line,
    and return the warnings of a whole suite at the desk."""
    if check is not None:
        (kitchen.home / "fresh-check").write_text(check)
    text = (
        brief("alpha")
        .replace("- `make check` passes (in none)\n", f"- {done} (in none)\n")
        .replace("Proves it: `make check`\n", f"Proves it: {proves}\n")
    )
    code, said = kitchen.main(
        "--project", "demo", "queue", "add", "alpha", "--priority", "1", stdin=text
    )
    assert code == 0, said
    assert (kitchen.state_dir / "demo" / "briefs" / "alpha.md").is_file()
    return [line for line in said.splitlines() if "whole suite" in line]


@pytest.mark.parametrize(
    ("done", "proves", "check", "labels"),
    [
        (
            "the doors stop",
            "`jgauge test-slot -- make check-fast BASE=origin/main`",
            None,
            "Proves it:",
        ),
        (WHOLE, "a test of the doors passes", None, "Done when:"),
        (WHOLE, "`make check`", FAST, "Done when: and Proves it:"),
        ("`make check` passes", "a test of the doors passes", FAST, "Done when:"),
    ],
)
def test_a_whole_suite_at_the_desk_is_warned_of_and_names_the_touched_check(
    kitchen, done, proves, check, labels
):
    [warned] = added(kitchen, done, proves, check)
    assert warned.startswith(f"warning: alpha's brief's {labels} runs the whole suite at the desk")
    assert TOUCHED in warned
    assert warned.endswith("the whole suite is CI's check on the pull request")


@pytest.mark.parametrize(
    ("done", "proves", "check"),
    [
        (
            "`make check-fast BASE=origin/main PART=touched` passes",
            "`jgauge test-slot -- make check-fast BASE=origin/main PART=touched`",
            FAST,
        ),
        ("`make check` passes", "`make check`", None),
        ("`make check` passes", "`make check`", "make check\n"),
    ],
)
def test_the_touched_check_or_a_repo_whose_check_selects_nothing_is_not_warned_of(
    kitchen, done, proves, check
):
    assert added(kitchen, done, proves, check) == []
