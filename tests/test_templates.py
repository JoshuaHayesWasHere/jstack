import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from test_home_thread import as_read, named

REPO = Path(__file__).parent.parent
TEMPLATES = REPO / "templates"
HOOK = REPO / "hooks" / "home-start.sh"
NAMES = [
    "brief.md",
    "expert-answer.md",
    "grill-page.html",
    "handoff.md",
    "hook-message.md",
    "plan-entry.md",
    "result.md",
    "review.md",
    "scout-report.md",
    "scout-request.md",
]
SKILLS = sorted(path.parent.name for path in REPO.glob("skills/*/SKILL.md"))
SHORTEST_WORDING = 20

HOOK_PRINTED = "\n".join(
    [
        "[home] This thread opened in the main checkout of {repo}, which has a home at {home_dir}.",
        "This thread is that repo's home. Before replying to the user's first message,"
        f" read {REPO / 'skills' / 'home' / 'SKILL.md'} and follow it.",
        "The first message is the user's opening request, not a command:"
        " give the skill's short status, then take the message as the start of planning.",
        "A first message that starts with /home is that command and not a request:"
        " follow the home skill with it as typed, the words after /home included.",
        "Do not do this if the first message starts with /crew, /expert, /nohome or /handoff:"
        " follow that skill instead.",
        "The user can type /nohome at any time to make this an ordinary thread.",
        "",
    ]
)


def carriers():
    """Every file that could carry its own copy of a template: each skill, each file a skill
    says to read now, and each hook."""
    skills = sorted(REPO.glob("skills/*/SKILL.md"))
    beside = [found for skill in skills for found in named(skill)]
    return skills + beside + sorted((REPO / "hooks").iterdir())


def wording(name):
    lines = (line.strip() for line in (TEMPLATES / name).read_text().splitlines())
    return [line for line in lines if len(line) >= SHORTEST_WORDING]


def a_home(tmp_path, repo):
    """A user's home directory with a home for `repo`, and that repo's main checkout."""
    user = tmp_path / "user"
    home_dir = user / ".local" / "state" / "home" / repo
    home_dir.mkdir(parents=True)
    (home_dir / "plan.md").write_text("")
    checkout = tmp_path / "code" / repo
    checkout.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    return user, home_dir, checkout


def start_hook(user, checkout, *, hook=HOOK, cwd=None):
    """Run the session-start hook as the harness does for a new T3 Code thread."""
    env = {**os.environ, "HOME": str(user), "T3_CODE_MCP_AUTHORIZATION": "x"}
    stdin = json.dumps({"source": "startup", "cwd": str(checkout)})
    done = subprocess.run(
        ["sh", str(hook)], input=stdin.encode(), capture_output=True, env=env, cwd=cwd, check=True
    )
    return done.stdout.decode()


def copied(name, text):
    """The lines of a template's wording that `text` carries."""
    return [line for line in wording(name) if line in text]


def test_lint_each_template_is_a_file_under_templates():
    assert [name for name in NAMES if not wording(name)] == []


@pytest.mark.parametrize("name", NAMES)
def test_lint_no_skill_and_no_hook_carries_a_copy_of_a_template(name):
    copies = {
        path.relative_to(REPO).as_posix(): copied(name, path.read_text()) for path in carriers()
    }
    assert {path: lines for path, lines in copies.items() if lines} == {}


@pytest.mark.parametrize("name", NAMES)
def test_lint_a_template_put_back_into_a_skill_or_the_hook_is_caught(name):
    template = (TEMPLATES / name).read_text()
    indented = "".join(f"   {line}" for line in template.splitlines(keepends=True))
    for carrier in carriers():
        assert copied(name, f"{carrier.read_text()}\n```markdown\n{indented}```\n") == wording(name)


def setting(skill):
    """The skill's own `T=` line. A skill that reads no template has none."""
    text = (REPO / "skills" / skill / "SKILL.md").read_text()
    return "\n".join(line for line in text.splitlines() if line.startswith("T="))


def resolved(skill, tmp_path):
    """What the skill's `T=` line gives, and where each `$T/<path>.md` it names leads.

    Run as the user has the skill: a symlink under ~/.claude/skills, used from another repo.
    """
    text = as_read(REPO / "skills" / skill / "SKILL.md")
    named = sorted(set(re.findall(r"`(\$T/[^`<>\s]+\.(?:md|html))`", text)))
    user = tmp_path / skill / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / skill).symlink_to(REPO / "skills" / skill)
    elsewhere = tmp_path / skill / "another-repo"
    elsewhere.mkdir()
    listed = "\n".join(
        f'if [ -f "{path}" ]; then realpath "{path}"; else echo \'missing: {path}\'; fi'
        for path in named
    )
    done = subprocess.run(
        ["sh", "-c", f"{setting(skill)}\nprintf '%s\\n' \"$T\"\n{listed}"],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(user), "T": ""},
        cwd=elsewhere,
        check=True,
    )
    found, *files = done.stdout.splitlines()
    return Path(found), files


READS = {
    "crew": {"gates.md", "rerun.md", "result.md", "skill-artifacts.md"},
    "expert": {"expert-answer.md", "gates.md"},
    "grilling": {"grill-page.html"},
    "handoff": {"handoff-seed.md", "handoff.md"},
    "home": {"brief.md", "context", "gates.md", "plan-entry.md", "scout-request.md"},
    "pr-review": {"rerun.md", "review.md"},
    "scout": {
        "brief.md",
        "gates.md",
        "grill-page.html",
        "scout-report.md",
        "scout-request.md",
        "skill-artifacts.md",
    },
    "technical-writing": {"pr-body.md"},
}


def top(path):
    """A file of a folder under `templates/`, as the folder: the skeleton of a context pack is
    read as one template."""
    if TEMPLATES.resolve() in path.parents:
        return TEMPLATES.resolve() / path.relative_to(TEMPLATES.resolve()).parts[0]
    return path


@pytest.mark.parametrize("skill", SKILLS)
def test_each_skill_names_the_templates_it_reads(skill, tmp_path):
    found = {top(Path(file)) for file in resolved(skill, tmp_path)[1]}
    names = {path.name for path in found if path.parent == TEMPLATES.resolve()}
    reads = READS.get(skill, set())
    lost = ", ".join(f"$T/{name}" for name in sorted(reads - names))
    new = ", ".join(f"$T/{name}" for name in sorted(names - reads))
    assert not lost, f"the {skill} skill no longer names {lost}"
    assert not new, f"the {skill} skill names {new}: add it to READS in this test"


@pytest.mark.parametrize("skill", SKILLS)
def test_every_file_a_skill_names_under_its_templates_is_there(skill, tmp_path):
    found, files = resolved(skill, tmp_path)
    assert [file for file in files if file.startswith("missing: ")] == []
    if setting(skill):
        assert found == TEMPLATES.resolve()


def test_the_skills_between_them_read_every_template_but_the_hooks_and_the_playbooks(tmp_path):
    read = set()
    for skill in SKILLS:
        read.update(top(Path(file)) for file in resolved(skill, tmp_path)[1])
    in_templates = {path for path in read if path.parent == TEMPLATES.resolve()}
    units = {
        path for path in TEMPLATES.resolve().iterdir() if path.suffix in (".service", ".timer")
    }
    assert in_templates == set(TEMPLATES.resolve().iterdir()) - units - {
        TEMPLATES.resolve() / name for name in ("hook-message.md", "playbook.md")
    }


@pytest.mark.parametrize(
    ("reviewed", "says"),
    [
        (True, "review: launch no reviewer, this pull request has had its one"),
        (False, "review: launch a reviewer"),
    ],
)
def test_the_crew_check_before_a_launch_finds_a_review_written_from_the_template(
    reviewed, says, tmp_path
):
    crew = as_read(REPO / "skills" / "crew" / "SKILL.md")
    (check,) = [text for text in crew.split("```") if 'echo "$mode: launch a reviewer"' in text]
    brief = "# alpha: a task\nDone when:\n- it works\n\n## Result\nStatus: done\n"
    if reviewed:
        brief += "\n" + (TEMPLATES / "review.md").read_text()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "alpha.md").write_text(brief)
    found = subprocess.run(
        ["sh", "-c", check.removeprefix("sh\n").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        env={**os.environ, "H": str(tmp_path)},
        check=True,
    )
    assert found.stdout == says + "\n"


def a_copy_of_the_hook(tmp_path):
    """The hook in a `hooks/` of its own, with no `templates/` beside it yet."""
    copy = tmp_path / "elsewhere" / "hooks" / HOOK.name
    copy.parent.mkdir(parents=True)
    copy.write_text(HOOK.read_text())
    return copy


def test_the_hook_prints_the_template_beside_it_whatever_that_says(tmp_path):
    user, home_dir, checkout = a_home(tmp_path, "demo")
    copy = a_copy_of_the_hook(tmp_path)
    (copy.parent.parent / "templates").mkdir()
    (copy.parent.parent / "templates" / "hook-message.md").write_text(
        "Other words for $repo.\nIts home is $home_dir, and $repo has no other.\n"
    )
    assert start_hook(user, checkout, hook=copy) == (
        f"Other words for demo.\nIts home is {home_dir}, and demo has no other.\n"
    )


@pytest.mark.parametrize(
    ("has_a_home", "says"),
    [
        (True, "The usual line for demo.\nA line for both, $first included.\n"),
        (False, "No home yet for demo.\nA line for both, $first included.\nOnly the first.\n"),
    ],
)
def test_the_hook_prints_a_line_marked_first_only_in_a_repo_with_no_home(
    has_a_home, says, tmp_path
):
    user, home_dir, checkout = a_home(tmp_path, "demo")
    if not has_a_home:
        (home_dir / "plan.md").unlink()
    copy = a_copy_of_the_hook(tmp_path)
    (copy.parent.parent / "templates").mkdir()
    (copy.parent.parent / "templates" / "hook-message.md").write_text(
        "$firstNo home yet for $repo.\nThe usual line for $repo.\n"
        "A line for both, $first included.\n$firstOnly the first.\n"
    )
    assert start_hook(user, checkout, hook=copy) == says


def test_the_hook_prints_nothing_with_no_template_beside_it(tmp_path):
    user, home_dir, checkout = a_home(tmp_path, "demo")
    assert start_hook(user, checkout, hook=a_copy_of_the_hook(tmp_path)) == ""


@pytest.mark.parametrize("repo", ["demo", r"an odd & name | with \n $repo $home_dir"])
def test_the_hook_prints_what_it_printed_before_the_move(tmp_path, repo):
    user, home_dir, checkout = a_home(tmp_path, repo)
    assert start_hook(user, checkout) == HOOK_PRINTED.format(repo=repo, home_dir=home_dir)


def test_the_hook_names_a_home_skill_file_that_is_there(tmp_path):
    user, home_dir, checkout = a_home(tmp_path, "demo")
    named = re.findall(r"read (\S+) and follow it", start_hook(user, checkout))
    assert [Path(path).is_file() for path in named] == [True]


def test_the_hook_finds_its_template_when_run_by_a_relative_path(tmp_path):
    user, home_dir, checkout = a_home(tmp_path, "demo")
    printed = start_hook(user, checkout, hook=HOOK.relative_to(REPO), cwd=REPO)
    assert printed == HOOK_PRINTED.format(repo="demo", home_dir=home_dir)
