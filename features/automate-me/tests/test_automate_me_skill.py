"""The automate-me skill's block: it finds the mode skills and when each last changed."""

import time

from skill_blocks import aged, block, home, repo, run

__all__ = ["home", "repo"]


def test_automate_me_finds_the_mode_skills_and_when_each_last_changed(repo, home):
    own = aged(home / ".claude" / "skills" / "jay-mode" / "SKILL.md", 3)
    shared = aged(repo / ".claude" / "skills" / "priya-mode" / "SKILL.md", 0)
    aged(home / ".claude" / "skills" / "unslop" / "SKILL.md", 0)
    when = [time.strftime("%F", time.localtime(path.stat().st_mtime)) for path in (own, shared)]
    assert run(block("automate-me", "-mode"), repo, home) == [
        f"{own}, last changed {when[0]}",
        f"{shared}, last changed {when[1]}",
    ]


def test_automate_me_says_so_when_there_is_no_mode_skill(repo, home):
    aged(home / ".claude" / "skills" / "unslop" / "SKILL.md", 0)
    assert run(block("automate-me", "-mode"), repo, home) == [
        "no mode skill: none under ~/.claude/skills or .claude/skills"
    ]
