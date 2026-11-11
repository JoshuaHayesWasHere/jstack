"""A brief's `Why:` line: why the change is wanted, which `jbus queue add` asks of a new brief,
through `jbriefs.parse.faults` and its check `jbriefs.why`."""

import pytest

from jbriefs import parse

HEAD = (
    '# alpha: the queue drops a row on restart\nTask: "the queue drops a row when jbus restarts"\n'
)
REST = (
    "Done when:\n- it is done (in `src/alpha/q.py`)\nProves it: `make check`\nSize: S\n"
    "Where: `src/alpha/`\nPull request: open one when done\nReview: review\n"
    "Playbook: bug-fix\nSkills: tdd\n"
)
WHY = (
    "Why: two of yesterday's 14 rows were lost when jbus restarted at 03:10, and their threads "
    "never launched, so the user queued them by hand\n"
)


def _faults(why: str) -> list[str]:
    return [fault for fault in parse.faults(HEAD + why + REST) if "Why" in fault]


def test_a_brief_whose_why_gives_the_reason_queues():
    assert parse.faults(HEAD + WHY + REST) == []


@pytest.mark.parametrize(
    "why, fault",
    [
        ("", "brief has no Why: line"),
        ("Why:\n", "brief's Why: line is empty"),
        ("Why: <why the change is wanted>\n", "brief's Why: line is the template's own text"),
    ],
    ids=["no line", "empty", "placeholder"],
)
def test_a_brief_with_no_why_is_refused_naming_the_line(why, fault):
    assert _faults(why) == [fault]


@pytest.mark.parametrize(
    "why",
    [
        "Why: the queue drops a row when jbus restarts\n",
        'Why: because "the queue drops a row on restart".\n',
        "Why: the queue drops a row\n  when jbus restarts, so we need it\n",
    ],
    ids=["the task", "the title, quoted", "the task, wrapped"],
)
def test_a_why_that_only_repeats_the_title_or_task_is_refused(why):
    (fault,) = _faults(why)
    assert fault.startswith("brief's Why: line says nothing its title and Task: do not")


@pytest.mark.parametrize("why", ["Why: we need it\n", "Why: for the user\n"])
def test_a_why_of_filler_words_alone_is_refused(why):
    (fault,) = _faults(why)
    assert fault.startswith("brief's Why: line says nothing its title and Task: do not")


def test_a_why_built_on_the_users_words_with_evidence_of_its_own_queues():
    said = "Why: the queue drops a row when jbus restarts, as 2 rows of 14 showed on 2026-11-10\n"
    assert _faults(said) == []
