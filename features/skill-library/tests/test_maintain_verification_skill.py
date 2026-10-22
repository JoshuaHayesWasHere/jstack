"""The maintain-verification-skill skill's first block: it finds the repo's verify skill, a
folder the repo tracks in `.claude/skills/verify-<app>/` or one that a `verify-<app>` item of
`skills.json`'s `projectSkills` names, and writes one scout request for each of its feature
files. It says there is no verify skill only when neither place has one. The folder each
playbook's `Verify skill:` line names for jstack is one the lookup finds from jstack's own
`skills.json`."""

import json
import re
import subprocess

import pytest

from skill_blocks import block, git, home, repo, run
from testing.paths import REPO, playbooks

__all__ = ["home", "repo"]

VERIFY_LINES = sorted(
    path for path in playbooks().values() if re.search(r"^Verify skill: ", path.read_text(), re.M)
)


def commit(repo, files):
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add")
    return git_head(repo)


def git_head(repo):
    said = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"], cwd=repo, capture_output=True, text=True
    )
    return said.stdout.strip()


def lookup(repo, home):
    return run(block("maintain-verification-skill", "no verify skill"), repo, home)


def scouts(home):
    return home / ".local" / "state" / "home" / "demo" / "scouts"


def test_a_tracked_verify_skill_is_found(repo, home):
    head = commit(
        repo,
        {
            ".claude/skills/verify-demo/SKILL.md": "# verify-demo\n",
            ".claude/skills/verify-demo/features/login.md": "# login\n",
        },
    )
    run_name = f"maintain-demo-{head}"
    assert lookup(repo, home) == [
        f"wrote: scouts/{run_name}-login.md",
        f"run: {run_name}, 1 feature files, launch them ten at a time",
    ]
    assert (scouts(home) / f"{run_name}.dir").read_text() == ".claude/skills/verify-demo\n"


def test_a_verify_skill_declared_only_as_a_project_skill_is_found(repo, home):
    declared = {"projectSkills": [{"name": "verify-demo", "path": "features/verify/skill"}]}
    head = commit(
        repo,
        {
            "skills.json": json.dumps(declared),
            "features/verify/skill/SKILL.md": "# verify-demo\n",
            "features/verify/skill/features/login.md": "# login\n",
        },
    )
    run_name = f"maintain-demo-{head}"
    assert lookup(repo, home) == [
        f"wrote: scouts/{run_name}-login.md",
        f"run: {run_name}, 1 feature files, launch them ten at a time",
    ]
    assert (scouts(home) / f"{run_name}.dir").read_text() == "features/verify/skill\n"
    request = (scouts(home) / f"{run_name}-login.md").read_text()
    assert "`features/verify/skill/features/login.md`" in request


def test_a_project_skill_that_is_no_verify_skill_is_not_found(repo, home):
    declared = {"projectSkills": [{"name": "lint-demo", "path": "features/lint/skill"}]}
    commit(repo, {"skills.json": json.dumps(declared), "features/lint/skill/SKILL.md": "# l\n"})
    assert lookup(repo, home) == [
        "no verify skill: HEAD has no .claude/skills/verify-*/ and its skills.json names no"
        " verify-* project skill: brief a crewmate to run /create-verification-skill instead"
    ]


def test_with_neither_there_is_no_verify_skill(repo, home):
    assert lookup(repo, home) == [
        "no verify skill: HEAD has no .claude/skills/verify-*/ and its skills.json names no"
        " verify-* project skill: brief a crewmate to run /create-verification-skill instead"
    ]


def test_two_verify_skills_from_the_two_places_ask_which_one(repo, home):
    declared = {"projectSkills": [{"name": "verify-api", "path": "features/api/skill"}]}
    commit(
        repo,
        {
            "skills.json": json.dumps(declared),
            ".claude/skills/verify-demo/SKILL.md": "# verify-demo\n",
        },
    )
    assert lookup(repo, home) == [
        "which one: type /maintain-verification-skill <app> with one of these:",
        "  api: features/api/skill",
        "  demo: .claude/skills/verify-demo",
    ]


@pytest.mark.parametrize("path", VERIFY_LINES, ids=lambda path: path.stem)
def test_the_folder_a_playbooks_verify_skill_line_names_is_the_one_the_lookup_finds(
    path, repo, home
):
    commit(repo, {"skills.json": (REPO / "skills.json").read_text()})
    found = lookup(repo, home)
    assert found[0] == "which one: type /maintain-verification-skill <app> with one of these:"
    folders = {f"{one.split(': ', 1)[1]}/" for one in found[1:]}
    (said,) = re.findall(r"^Verify skill: (.*)$", path.read_text(), re.M)
    named = re.findall(r"`(features/[^`]+/)`", said)
    assert named != []
    assert [folder for folder in named if folder not in folders] == []
