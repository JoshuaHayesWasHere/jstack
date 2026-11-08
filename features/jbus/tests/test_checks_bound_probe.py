"""`checks_bound_probe.round_end` ends a head's round of checks where jmerge's verdict on it is
settled: at its first failed required job, or at the end of its last required job. A job of a
workflow no required check names, such as `browser`, neither ends a round nor holds one open.

The check runs are shaped as GitHub's `commits/<head>/check-runs` gives them: the workflow run of
each is the number in its `html_url`.
"""

from datetime import datetime

from checks_bound_probe import round_end

REQUIRED = ("check", "borders", "macos")
WORKFLOW_OF = {"1": "check", "2": "borders", "3": "macos", "4": "browser"}
RUN_OF = {workflow: run for run, workflow in WORKFLOW_OF.items()}


def job(name: str, workflow: str, ended: str = "", conclusion: str = "success") -> dict:
    return {
        "name": name,
        "status": "completed" if ended else "in_progress",
        "conclusion": conclusion if ended else None,
        "completed_at": f"2026-11-08T05:{ended}Z" if ended else None,
        "html_url": f"https://github.com/o/r/actions/runs/{RUN_OF[workflow]}/job/{len(name)}",
    }


def at(ended: str) -> float:
    return datetime.fromisoformat(f"2026-11-08T05:{ended}Z").timestamp()


PASSED = [
    *(job(f"check {n} of 8", "check", f"20:{n:02}") for n in range(1, 9)),
    job("check", "check", "20:30"),
    job("borders", "borders", "19:40"),
    job("macos 1 of 3", "macos", "20:10"),
    job("macos", "macos", "20:20"),
]


def test_a_failed_required_job_ends_the_round_while_others_go():
    runs = [
        job("check 1 of 8", "check"),
        job("check 2 of 8", "check", "18:44", "failure"),
        job("check 6 of 8", "check", "19:08", "failure"),
        job("borders", "borders", "18:10"),
        job("macos 1 of 3", "macos"),
        job("browser", "browser", "18:00", "failure"),
    ]
    assert round_end(runs, WORKFLOW_OF, REQUIRED) == (at("18:44"), "failed")


def test_a_passed_round_ends_at_its_last_required_job():
    assert round_end(PASSED, WORKFLOW_OF, REQUIRED) == (at("20:30"), "passed")


def test_a_late_non_required_job_neither_holds_nor_moves_the_end():
    going = [*PASSED, job("browser", "browser")]
    ended = [*PASSED, job("browser", "browser", "21:50", "failure")]
    assert round_end(going, WORKFLOW_OF, REQUIRED) == (at("20:30"), "passed")
    assert round_end(ended, WORKFLOW_OF, REQUIRED) == (at("20:30"), "passed")


def test_a_required_check_github_lists_no_run_of_yet_holds_the_round():
    """GitHub lists `check` only once the shards it needs have ended (#1246)."""
    shards = [one for one in PASSED if one["name"] != "check"]
    assert round_end(shards, WORKFLOW_OF, REQUIRED) is None
