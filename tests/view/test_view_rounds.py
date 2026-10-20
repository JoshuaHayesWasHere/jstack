"""The Rounds panel: the review sections of a brief, as `jmerge` reads them."""

import os

import pytest

from jmerge import ready
from view.scene import ago, iso, rounded


def test_the_rounds_of_a_brief_are_its_review_sections_as_jmerge_reads_them(scene, served):
    brief, first, fixed = rounded(scene)
    said = {one["slug"]: one for one in served.json("/state.json?project=demo")["rounds"]}
    assert said["oat-milk"] == {
        "slug": "oat-milk",
        "read": True,
        "why": "",
        "reviews": [
            {"verdict": "findings", "head": first, "findings": 2, "at": iso(ago(minutes=20))},
            {"verdict": "clean", "head": fixed, "findings": 0, "at": None},
        ],
        "second": True,
        "scoped": True,
        "woke": 3,
        "rebases": 1,
    }
    merged = ready.said_of(brief)
    assert [(one.verdict, one.head, one.found) for one in merged.rounds] == [
        (one["verdict"], one["head"], one["findings"]) for one in said["oat-milk"]["reviews"]
    ]
    assert merged.found == 2 and merged.reviewed == fixed and merged.verdict == "clean"
    assert (
        served.json("/panel/rounds.json?project=demo")["data"]["rounds"]
        == served.json("/state.json?project=demo")["rounds"]
    )


def test_a_brief_that_cannot_be_read_says_so_and_counts_nothing(scene, served):
    rounded(scene, "oat-bowl")
    (scene.home / "tasks" / "oat-bowl.md").chmod(0)
    said = {one["slug"]: one for one in served.json("/state.json?project=demo")["rounds"]}
    if os.access(scene.home / "tasks" / "oat-bowl.md", os.R_OK):
        pytest.skip("this user reads a file of mode 0")
    assert said["oat-bowl"] == {
        "slug": "oat-bowl",
        "read": False,
        "why": "its brief could not be read: Permission denied",
        "reviews": [],
    }
    assert said["oat-milk"] == {
        "slug": "oat-milk",
        "read": False,
        "why": "it has no brief in its home or in jbus's copies",
        "reviews": [],
    }
