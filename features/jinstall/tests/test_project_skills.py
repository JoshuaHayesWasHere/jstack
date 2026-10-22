"""The checkout's own skills: `install.sh` links each project skill a feature declares
(`projectSkills`, which the generator lists in skills.json) into the checkout's
`.claude/skills/<name>` and `.cursor/skills/<name>`, where Claude Code and Cursor read a repo's
skills, and unlinks one whose declaration is gone. git tracks neither folder. Each test runs
the script under a temporary HOME, from a checkout inside it, but for the release's, which has
no checkout to run from."""

import json
import os
import subprocess

import pytest

from jinstall.__main__ import install as run_install
from jinstall.machine import Machine
from test_install import REPO, Ran, User, checkout_under, line_for

ROOTS = (".claude/skills", ".cursor/skills")
DECLARED = {
    "verify-jstack": "features/verify-jstack/project-skill",
    "verify-main-red": "features/jbus/project-skill/verify-main-red",
}


@pytest.fixture
def user(tmp_path):
    return User(tmp_path)


def run(user, checkout, *args):
    done = user.start(*args, checkout=checkout)
    out, _ = done.communicate()
    return done.returncode, out.splitlines()


def links(checkout):
    """Each link under the checkout's project roots, by where it points."""
    return {
        f"{root}/{one.name}": os.readlink(one)
        for root in ROOTS
        if (checkout / root).is_dir()
        for one in sorted((checkout / root).iterdir())
    }


def test_an_install_links_each_declared_project_skill_for_claude_code_and_cursor(user):
    checkout, _ = checkout_under(user)
    assert links(checkout) == {}

    code, said = run(user, checkout)

    assert links(checkout) == {
        f"{root}/{name}": str(checkout / path) for root in ROOTS for name, path in DECLARED.items()
    }
    for root in ROOTS:
        for name in DECLARED:
            link = checkout / root / name
            assert line_for(said, str(link)) == [f"ok hard {link}"]
            skill = (link / "SKILL.md").read_text()
            assert skill.startswith(f"---\nname: {name}\n")
    assert run(user, checkout, "--check") == (code, said)


def test_a_skill_that_is_no_longer_declared_is_unlinked_by_the_next_run(user):
    checkout, _ = checkout_under(user)
    run(user, checkout)
    catalog = checkout / "skills.json"
    listed = json.loads(catalog.read_text())
    listed["projectSkills"] = [
        one for one in listed["projectSkills"] if one["name"] != "verify-main-red"
    ]
    catalog.write_text(json.dumps(listed))
    gone = [checkout / root / "verify-main-red" for root in ROOTS]

    checked = run(user, checkout, "--check")[1]
    was = checkout / DECLARED["verify-main-red"]
    assert [line_for(checked, str(link)) for link in gone] == [
        [f"old hard {link} -> {was}, a skill no feature declares"] for link in gone
    ]
    said = run(user, checkout)[1]

    assert [line_for(said, str(link)) for link in gone] == [
        [f"ok hard {link} -> unlinked"] for link in gone
    ]
    assert links(checkout) == {
        f"{root}/verify-jstack": str(checkout / DECLARED["verify-jstack"]) for root in ROOTS
    }


def test_check_says_a_missing_link_is_not_ok_and_a_run_mends_it(user):
    checkout, _ = checkout_under(user)
    run(user, checkout)
    link = checkout / ".claude/skills/verify-jstack"
    link.unlink()

    code, checked = run(user, checkout, "--check")

    assert (code, line_for(checked, str(link))) == (1, [f"missing hard {link}"])
    assert not link.is_symlink()
    assert line_for(run(user, checkout)[1], str(link)) == [f"ok hard {link}"]
    assert os.readlink(link) == str(checkout / DECLARED["verify-jstack"])


def test_a_folder_of_the_users_own_where_a_link_goes_is_left_alone(user):
    checkout, _ = checkout_under(user)
    own = checkout / ".cursor/skills/verify-jstack"
    own.mkdir(parents=True)

    said = run(user, checkout)[1]

    assert line_for(said, str(own)) == [f"old hard {own} -> not a link"]
    assert own.is_dir() and not own.is_symlink()


def test_uninstall_takes_the_links_away_and_leaves_no_folder_it_made(user):
    checkout, _ = checkout_under(user)
    run(user, checkout)

    run(user, checkout, "--uninstall")

    assert not (checkout / ".claude").exists()
    assert not (checkout / ".cursor").exists()


def test_a_checkout_outside_a_sandboxed_home_and_a_release_get_no_project_links(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    def named(checkout, account, release=None):
        there = Machine(checkout, home, {}, lambda args: Ran(None, ""), account, release)
        said = run_install(there, write=False).lines
        return [line.split(" ", 2)[2] for line in said if "/.claude/skills/verify" in line]

    assert named(REPO, home) == [
        str(REPO / ".claude/skills/verify-jstack"),
        str(REPO / ".claude/skills/verify-main-red"),
    ]
    assert named(REPO, tmp_path / "account") == []
    assert named(None, home, release=REPO) == []


def test_git_tracks_nothing_under_the_checkouts_project_roots():
    listed = subprocess.run(
        ["git", "-C", REPO, "ls-files", ".claude", ".cursor"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert listed.stdout == ""
