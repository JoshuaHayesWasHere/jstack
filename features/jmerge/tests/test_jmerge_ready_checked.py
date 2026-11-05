"""A brief's last `Checked:` line binds only where the desk's guards passed at the head:
`PART=guards exit 0`, as the crew's check block (features/crew/do-the-task.md) writes it, at the
head or at a head whose patch the head carries unchanged. These drive `ready.short_on_checked`,
which `jmerge` calls before a merge and the crew's push block before the first push, through
each way a line falls short: a missing line, a failed one, a time limit's 124 (a check cut
short reached no verdict) and a line of a head whose patch changed since. Each hold says what
the crew runs to clear it. test_jmerge_cli_checked.py runs the same holds through `jmerge`."""

import pytest

from jmerge import ready

BASE = "c" * 40
HEAD = "d" * 40
EARLIER = "e" * 40
GUARDS = f"make check-fast BASE={BASE} PART=guards"
LINT = f"make check-fast BASE={BASE} PYTEST=: PART=guards"


def checked(code=0, head=HEAD, command=GUARDS):
    return f"Checked: {command} exit {code} at {head}\n"


def result(lines=""):
    return f"# alpha: a task\n\n## Result\nStatus: done\n{lines}"


@pytest.mark.parametrize(
    ("lines", "short"),
    [
        pytest.param(checked(), "", id="the guards passed"),
        pytest.param(checked(command=LINT), "", id="the lint passed, no test selected"),
        pytest.param(checked(command="jgauge check"), "", id="another repo's check passed"),
        pytest.param("", ready.CHECKED_MISSING.format(head=HEAD[:12]), id="missing"),
        pytest.param(
            checked(1),
            ready.CHECKED_FAILED.format(exit=1, at=HEAD[:12], head=HEAD[:12]),
            id="exit 1",
        ),
        pytest.param(
            checked(124), ready.CHECKED_CUT.format(at=HEAD[:12], head=HEAD[:12]), id="exit 124"
        ),
        pytest.param(
            checked(head=EARLIER),
            ready.CHECKED_STALE.format(at=EARLIER[:12], head=HEAD[:12]),
            id="stale",
        ),
        pytest.param(
            checked(
                124,
                command=f"{GUARDS} exit 0 (took 150 s), then the import-reached remainder, "
                f"where exit 124 is the short lane's time limit and passes: "
                f"make check-fast BASE={BASE} PART=rest",
            ),
            ready.CHECKED_CUT.format(at=HEAD[:12], head=HEAD[:12]),
            id="the old short lane's 124",
        ),
        pytest.param(
            checked(command=f"make check-fast BASE={BASE} PART=rest"),
            ready.CHECKED_PART.format(
                command=f"make check-fast BASE={BASE} PART=rest", head=HEAD[:12]
            ),
            id="the rest alone",
        ),
        pytest.param(checked(124) + checked(), "", id="the last line is read, a pass after a 124"),
        pytest.param(
            checked() + checked(124),
            ready.CHECKED_CUT.format(at=HEAD[:12], head=HEAD[:12]),
            id="the last line is read, a 124 after a pass",
        ),
    ],
)
def test_the_line_binds_only_where_the_guards_exited_0_at_the_head(lines, short):
    assert ready.short_on_checked(result(lines), HEAD) == short
    if short:
        assert ready.code_of(str(short)) == short.code
        assert short.code.startswith("checked-")
        assert ready.step_of(short.code) == "result"


def test_a_line_of_another_head_binds_only_where_the_head_carries_its_patch():
    text = result(checked(head=EARLIER))
    stale = ready.CHECKED_STALE.format(at=EARLIER[:12], head=HEAD[:12])
    assert ready.short_on_checked(text, HEAD) == stale
    assert ready.short_on_checked(text, HEAD, lambda at: at == EARLIER) == ""
    cut = result(checked(124, head=EARLIER))
    assert ready.short_on_checked(cut, HEAD, lambda at: at == EARLIER) == ready.CHECKED_CUT.format(
        at=EARLIER[:12], head=HEAD[:12]
    )


@pytest.mark.parametrize(
    "reason",
    [
        ready.CHECKED_MISSING,
        ready.CHECKED_STALE,
        ready.CHECKED_CUT,
        ready.CHECKED_FAILED,
        ready.CHECKED_PART,
    ],
)
def test_each_hold_names_what_the_crew_runs_to_clear_it(reason):
    assert "the crew's check block (features/crew/do-the-task.md)" in reason
    assert "PART=guards" in reason
