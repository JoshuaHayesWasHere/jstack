"""`features/jmerge/scripts/force_pushes.py` gives each force-push of a merged pull request the
cause jbus told its crew last before it."""

import importlib.util
from datetime import datetime

from testing.paths import REPO

SCRIPT = REPO / "features" / "jmerge" / "scripts" / "force_pushes.py"
SPEC = importlib.util.spec_from_file_location("force_pushes", SCRIPT)
pushes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pushes)

SINCE = datetime.fromisoformat("2026-10-26T14:00:00+00:00")
UNTIL = datetime.fromisoformat("2026-11-02T14:00:00+00:00")


def pull(number, branch, *pushed, merged="2026-10-28T12:00:00Z"):
    return {"number": number, "branch": branch, "merged": merged, "pushes": list(pushed)}


def event(kind, slug, at, line="", text=""):
    return {"event": kind, "slug": slug, "at": at, "line": f"{kind} {slug}: {line}", "text": text}


def test_each_push_takes_the_cause_jbus_told_last_before_it():
    pulls = [
        pull(
            7,
            "seven",
            "2026-10-27T10:30:00Z",
            "2026-10-27T12:30:00Z",
            "2026-10-27T14:30:00Z",
            "2026-10-27T16:30:00Z",
        ),
        pull(8, "eight", "2026-10-27T10:30:00Z"),
    ]
    events = [
        event("failed", "seven", "2026-10-27T10:00:00Z", "told the crew (#7, abc)"),
        event("restack", "seven", "2026-10-27T12:00:00Z", "told the crew one merged (#6, abc)"),
        event(
            "rebase",
            "seven",
            "2026-10-27T14:00:00Z",
            "told the crew (#7, abc)",
            "jbus: main moved under your pull request #7 (it conflicts with its base).",
        ),
        event("review", "seven", "2026-10-27T15:00:00Z", "clean"),
    ]
    assert pushes.causes(pulls, events, SINCE, UNTIL) == {
        "crew fix": 1,
        "stack move": 1,
        "conflict": 1,
        "other": 2,
    }


def test_a_restack_names_the_pull_request_that_merged_and_counts_for_the_stacked_one():
    pulls = [pull(6, "six"), pull(7, "seven", "2026-10-27T12:30:00Z")]
    events = [event("restack", "seven", "2026-10-27T12:00:00Z", "told the crew six merged (#6)")]
    assert pushes.causes(pulls, events, SINCE, UNTIL)["stack move"] == 1


def test_a_push_with_no_event_in_two_hours_takes_the_last_since_the_push_before_it():
    pulls = [pull(7, "seven", "2026-10-27T08:00:00Z", "2026-10-27T20:00:00Z")]
    events = [event("review", "seven", "2026-10-27T09:00:00Z", "findings")]
    assert pushes.causes(pulls, events, SINCE, UNTIL) == {
        "crew fix": 1,
        "stack move": 0,
        "conflict": 0,
        "other": 1,
    }


def test_only_the_pull_requests_merged_in_the_period_are_counted():
    pulls = [
        pull(7, "seven", "2026-10-20T10:00:00Z", merged="2026-10-20T12:00:00Z"),
        pull(8, "eight", "2026-10-27T10:00:00Z", merged=None),
    ]
    assert sum(pushes.causes(pulls, [], SINCE, UNTIL).values()) == 0
