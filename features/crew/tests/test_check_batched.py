"""The check block of "Do the task" runs the files it selects in a few takes of the short lane,
each step as many files as fit its measured test time, with the same files and the same verdicts
as one take a file. One take a file cost 272 slot takes a merged pull request on 2026-11-12, and
127 agent-hours of waiting for a slot that day."""

import re

import test_room as room
from crew_helpers import git
from test_crew_check_command import a_brief, alone, checked, lanes, lint, selected, stubbed, touching

TOUCHED = tuple(f"tests/test_{one}.py" for one in "abcdef")
GUARDS = tuple(f"features/repo-guards/tests/test_{one}.py" for one in "ghi")
NAMES = ("tests/test_m.py", "tests/test_n.py", "tests/test_o.py")


def measured(repo, seconds, *files):
    """Each of `files` measured at `seconds` by a check before, in the times every worktree of
    the repo shares."""
    with (repo / ".git" / "crew-check-times").open("a") as times:
        times.writelines(f"{one} {seconds}\n" for one in files)


def kept(repo, name):
    found = repo / ".git" / name
    return found.read_text().splitlines() if found.exists() else []


def test_twelve_selected_files_of_measured_times_run_in_a_take_of_each_kind(tmp_path):
    """The reproduction: 6 touched files, 3 guards and 3 that read the change, each measured at
    5 s, ran in 13 takes, the lint and one a file. Each kind's files fit one step of the short
    lane, so the check is 4 takes, of the same 12 files, and it passes as before."""
    selector = touching(*TOUCHED, cross=GUARDS, names=NAMES)
    repo = stubbed(tmp_path, selector)
    measured(repo, 5, *TOUCHED, *GUARDS, *NAMES)
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo)
    assert len(ran) == 4, ran
    assert ran == [
        lint(base),
        alone(" ".join(TOUCHED), base),
        alone(" ".join(GUARDS), base),
        alone(" ".join(NAMES), base),
    ]
    assert said[0] == (
        "touched: 6 test files, then 3 cross-cutting guard tests, then 0 test files CI failed on, "
        "then 3 test files that read the change, in 3 steps of the short lane after the lint; "
        "CI's check runs the rest of the selection"
    ), said
    assert code == 0, said
    head = git(repo, "rev-parse", "HEAD")
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )
    assert {f"passed {one}" for one in (*TOUCHED, *GUARDS, *NAMES)} <= set(
        kept(repo, "crew-check-steps")
    )


def test_a_step_holds_no_more_than_a_minute_of_measured_time(tmp_path):
    """A step takes files in order while their measured seconds sum to 60 at most, the most the
    names part puts in a line, so it ends well inside the short lane's 120 s."""
    repo = stubbed(tmp_path, touching(*TOUCHED))
    measured(repo, 25, *TOUCHED[:4])
    measured(repo, 70, TOUCHED[4])
    measured(repo, 1, TOUCHED[5])
    a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo)
    assert ran == [
        lint(base),
        alone(" ".join(TOUCHED[:2]), base),
        alone(" ".join(TOUCHED[2:4]), base),
        alone(TOUCHED[4], base),
        alone(TOUCHED[5], base),
    ]
    assert code == 0, said


def test_a_file_of_no_measured_time_runs_alone_and_its_run_measures_it(tmp_path):
    """A file no check has measured runs alone, and a line of the names part as the selector
    gave it, as each did before. The run's pytest report measures each file, so the next head's
    check, in any worktree of the repo, packs them."""
    repo = stubbed(tmp_path, touching(*TOUCHED[:3], names=("tests/test_m.py tests/test_n.py",)))
    a_brief(tmp_path)
    junit = ({}, [])
    said, code, ran, base = selected(tmp_path, repo, junit=junit)
    assert ran == [
        lint(base),
        *(alone(one, base) for one in TOUCHED[:3]),
        alone("tests/test_m.py tests/test_n.py", base),
    ]
    assert code == 0, said
    (repo / "page.md").write_text("A new head.\n")
    git(repo, "commit", "-qam", "a new head")
    said, code, ran, base = selected(tmp_path, repo, junit=junit)
    assert ran == [
        lint(base),
        alone(" ".join(TOUCHED[:3]), base),
        alone("tests/test_m.py tests/test_n.py", base),
    ]
    assert code == 0, said


def test_a_failing_step_names_each_failing_file_and_keeps_it_until_it_passes(tmp_path):
    """A step of four files fails on one: the block names that file from pytest's report, keeps
    it in `crew-failed-files` as CI's failed files are kept, keeps no file of the step as passed,
    and ends with the step's exit. Run again at the head, the step runs whole, and once it passes
    the kept name goes."""
    repo = stubbed(tmp_path, touching(*TOUCHED[:4]))
    measured(repo, 5, *TOUCHED[:4])
    brief = a_brief(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    said, code, ran, base = selected(
        tmp_path, repo, exits={"*test_c.py*": 1}, junit=({}, [TOUCHED[2]])
    )
    batch = alone(" ".join(TOUCHED[:4]), base)
    assert ran == [lint(base), batch]
    assert f"{TOUCHED[2]}: failed in step {','.join(TOUCHED[:4])}" in said, said
    assert kept(repo, "crew-failed-files") == [TOUCHED[2]]
    assert not [one for one in kept(repo, "crew-check-steps") if one.startswith("passed tests/")]
    assert code == 1
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 1 at {head}\n"
    )
    said, code, ran, base = selected(tmp_path, repo, junit=({}, []))
    assert (ran, code) == ([batch], 0), said
    assert kept(repo, "crew-failed-files") == []


def test_a_failing_step_whose_report_names_no_file_keeps_each_of_its_files(tmp_path):
    """Where pytest wrote no report, as when it cannot start, the block cannot tell which file
    failed, so it keeps each file of the step, and each runs until it passes."""
    repo = stubbed(tmp_path, touching(*TOUCHED[:2]))
    measured(repo, 5, *TOUCHED[:2])
    a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo, exits={"*test_a.py*": 2})
    assert code == 2
    assert kept(repo, "crew-failed-files") == list(TOUCHED[:2])


def test_a_step_stopped_at_the_lanes_limit_is_split_and_its_files_run_again_never_passed(
    tmp_path,
):
    """A step of three files the short lane stops at its limit (exit 124) reached no verdict:
    no file of it is kept as passed, its files are measured afresh, and each runs again alone,
    a file the lane stops again in a full slot, as before. The check's verdict is theirs."""
    repo = stubbed(tmp_path, touching(*TOUCHED[:3]))
    measured(repo, 5, *TOUCHED[:3])
    brief = a_brief(tmp_path)
    batch = " ".join(TOUCHED[:3])
    stopped = {
        f"*{batch} BASE=* short=held*": 124,
        f"*{TOUCHED[1]} BASE=* short=held*": 124,
    }
    said, code, ran, base = selected(tmp_path, repo, exits=stopped)
    head = git(repo, "rev-parse", "HEAD")
    assert ran == [
        lint(base),
        alone(batch, base),
        alone(TOUCHED[0], base),
        alone(TOUCHED[1], base),
        alone(TOUCHED[1], base, "short=free full=held"),
        alone(TOUCHED[2], base),
    ]
    assert (
        f"{','.join(TOUCHED[:3])}: stopped at the short lane's limit, no verdict: "
        "its 3 files run again, each alone"
    ) in said, said
    assert code == 0, said
    times = (repo / ".git" / "crew-check-times").read_text().splitlines()
    assert times[-3:] == [f"{one} -" for one in TOUCHED[:3]]
    assert brief.read_text().endswith(
        f"Checked: make check-fast BASE={base} PART=touched exit 0 at {head}\n"
    )


def test_a_split_step_whose_file_fails_ends_the_check_with_that_failure(tmp_path):
    repo = stubbed(tmp_path, touching(*TOUCHED[:2]))
    measured(repo, 5, *TOUCHED[:2])
    a_brief(tmp_path)
    stopped = {f"*{' '.join(TOUCHED[:2])} BASE=*": 124, f"*TESTS={TOUCHED[1]} BASE=*": 1}
    said, code, ran, base = selected(tmp_path, repo, exits=stopped)
    assert ran[-1] == alone(TOUCHED[1], base)
    assert code == 1
    assert "passed " + TOUCHED[1] not in kept(repo, "crew-check-steps")
    assert "passed " + TOUCHED[0] in kept(repo, "crew-check-steps")


def test_the_block_starts_no_batched_step_it_cannot_end_in_its_call(tmp_path, monkeypatch):
    """#1612 holds for a step of many files as for one: with each take 150 s, the lint and the
    steps of the touched files and the guards end at 450 s, and the step of the names part is not
    started, so the call ends inside its 540 s, says one step is left, and checks nothing yet."""
    monkeypatch.delenv("JGAUGE_SHORT_WAIT_SECONDS", raising=False)
    repo = stubbed(tmp_path, touching(*TOUCHED, cross=GUARDS, names=NAMES))
    measured(repo, 5, *TOUCHED, *GUARDS, *NAMES)
    brief = a_brief(tmp_path)
    said, code, ran, base = selected(tmp_path, repo, takes=150)
    assert ran == [lint(base), alone(" ".join(TOUCHED), base), alone(" ".join(GUARDS), base)]
    assert (said[-1], code) == ("running: 1 steps left", 76), said
    assert "Checked:" not in brief.read_text()
    said, code, ran, base = selected(tmp_path, repo, takes=150)
    assert (ran, code) == ([alone(" ".join(NAMES), base)], 0), said


def test_a_batched_step_that_passed_over_work_the_head_lacks_keeps_none_of_its_files(tmp_path):
    """#1754 holds for a step of many files: the step ran over an edit made while it ran, which
    the head does not have, so no file of it is kept as passed and the block writes no `Checked:`
    line."""
    repo = stubbed(tmp_path, touching(*TOUCHED[:3]))
    measured(repo, 5, *TOUCHED[:3])
    brief = a_brief(tmp_path)
    stub, edit = tmp_path / "stub", repo / "edit.txt"
    stub.mkdir()
    room.uv(stub)
    lanes(stub, tmp_path / "home" / ".local" / "state" / "locks", tmp_path / "make.log")
    (stub / "make").rename(stub / "make.real")
    (stub / "make").write_text(
        "#!/bin/sh\n"
        f'case "$*" in *test_a.py*) echo an edit > {edit} ;; esac\n'
        f'exec {stub / "make.real"} "$@"\n'
    )
    (stub / "make").chmod(0o755)
    said, code, _ = checked(tmp_path, "echo the full lane")
    steps = kept(repo, "crew-check-steps")
    assert "passed lint" in steps
    assert not [one for one in steps if one.startswith("passed tests/")], steps
    assert re.search(r"passed over work that \w+ does not have, so it is not kept$", said[-1])
    assert code == 76
    assert "Checked:" not in brief.read_text()
