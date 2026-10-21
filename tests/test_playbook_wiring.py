"""A brief or a scout's request names a playbook, and the thread that takes it opens that
file; a home opens its own, named in the head of its plan, and an expert the one of the kind
of ask it has. Each opens it with `jbus playbook <role>`: the step is that call in the crew,
scout, home and expert skills, lifted from each and run here, through a `uv` that runs the
verb with the repo the skill lives in as its `$T/..`. Each opens a playbook of its own role
and refuses another role's. The real `uv` runs the call once under `sh` and once under `zsh`.
The home's block that lists the playbooks is lifted from the home skill and run against
`playbooks/` and against a directory with a file added."""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import crew.helpers as crew
import test_home_merge as merge
import test_playbooks as shape
from test_home_thread import as_read
from testing.layouts import assembled
from testing.paths import REPO, playbooks

TEMPLATES = REPO / "templates"
COPY = assembled()
PLAYBOOK = playbooks()
NAMES = sorted(PLAYBOOK)
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
SLUG = "alpha"
READERS = {"crew": ("tasks", "brief.md"), "scout": ("scouts", "scout-request.md")}
READERS_OF = {"a crewmate": "crew", "a scout": "scout"}
WHOSE = {
    "crew": "a crewmate's",
    "scout": "a scout's",
    "home": "the home's",
    "expert": "an expert's",
}
EXPERT = "sage"
THREAD = "mcp:thread-one"
PLAN = "# a repo: plan\n\nGoal: the work of one queue.\n{}\n## alpha: a task\nStatus: planned\n"
MADE = {
    "for-a-crewmate": "a crewmate, for a kind of task.",
    "for-a-scout": "a scout, for a kind of question.",
    "for-the-home": "the home, for a queue of tasks.",
    "for-an-expert": "an expert, for a kind of ask.",
}


def opening(skill):
    """The skill's block that opens the playbook, and its `T=` line, as an agent reads them.
    An expert's `T=` line is in the block it runs before every other, which finds its folder:
    that block whole."""
    text = as_read(REPO / "skills" / skill / "SKILL.md")
    (block,) = [
        found
        for found in FENCED.findall(text)
        if "jbus playbook" in found and "--named" not in found
    ]
    (setting,) = [line for line in text.splitlines() if line.startswith("T=")]
    if skill == "expert":
        (setting,) = [found for found in FENCED.findall(text) if f"\n{setting}\n" in found]
    return textwrap.dedent(setting), textwrap.dedent(block)


def uv(where):
    """A `uv` in `where` that runs `uv run --project <repo> jbus ...` as `jbus` does, with
    `<repo>` as the repo whose `playbooks/` and `principles/` it opens: the first folder from
    `<repo>` up that has a `pyproject.toml`, as uv finds the project, else `<repo>` where it
    has a `skills.json`. A layout has neither: uv runs the `jbus` on PATH, this checkout's."""
    where.mkdir(parents=True, exist_ok=True)
    run = (
        "import sys; from pathlib import Path; from jbus import cli, playbook; "
        "at = Path(sys.argv[1]).resolve(); "
        'up = [d for d in (at, *at.parents) if (d / "pyproject.toml").is_file()]; '
        'up += [at] if (at / "skills.json").is_file() else []; '
        "playbook.REPO = up[0] if up else playbook.REPO; "
        "sys.exit(cli.main(sys.argv[2:]))"
    )
    (where / "uv").write_text(
        '#!/bin/sh\n[ "$1 $2 $4" = "run --project jbus" ] || exit 64\nrepo=$3\nshift 4\n'
        f'exec {sys.executable} -c \'{run}\' "$repo" "$@"\n'
    )
    (where / "uv").chmod(0o755)
    return where


def written(skill, line):
    """What the home wrote from the skill's template, with `line` as its `Playbook:` line.
    For the home itself it is a plan, with the line in its head. An expert has no such line:
    it is given the name, or the kind of ask."""
    if skill == "home":
        return PLAN.format(f"{line}\n" if line else "")
    if skill == "expert":
        return line.removeprefix("Playbook:").strip()
    lines = (TEMPLATES / READERS[skill][1]).read_text().splitlines()
    (at,) = [n for n, text in enumerate(lines) if text.startswith("Playbook:")]
    lines[at : at + 1] = [line] if line else []
    return "\n".join(lines) + "\n"


def catalogued(repo):
    """The `skills.json` of a made repo: each playbook and principle it holds, which is how
    `jbus playbook` finds them."""
    items = [
        {"name": path.stem, "kind": kind, "path": str(path.relative_to(repo))}
        for kind, folder in (("playbook", "playbooks"), ("principle", "principles"))
        for path in sorted((repo / folder).glob("*.md"))
    ]
    (repo / "skills.json").write_text(json.dumps({"items": items}))


def opened(skill, text, tmp_path, repo=REPO, name="", shell="sh", real=False):
    """What the block prints for a brief, a request or a plan, run as the user has the
    skill: a symlink under ~/.claude/skills, used from another repo, by `shell`. `repo` is
    the repo the skill lives in, and `name` is the name a home is given in place of its
    plan's. An expert is given `text` as the name, after the block that finds its folder
    under that user's home, where `home-id` says this thread is the expert. `real` runs the
    `uv` on the PATH, which runs the verb of this checkout, in place of `uv` above."""
    if repo != REPO:
        catalogued(repo)
    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    linked = COPY if repo == REPO else repo
    (user / ".claude" / "skills" / skill).symlink_to(linked / "skills" / skill)
    state = tmp_path / "state"
    if skill == "home":
        state.mkdir()
        (state / "plan.md").write_text(text)
    elif skill == "expert":
        folder = user / ".local" / "state" / "home" / f"_{EXPERT}"
        folder.mkdir(parents=True)
        (folder / "CHARTER.md").write_text("# A subject\n")
        (folder / "home-id").write_text(f"{THREAD}\n")
        name = EXPERT
    else:
        (state / READERS[skill][0]).mkdir(parents=True)
        (state / READERS[skill][0] / f"{SLUG}.md").write_text(text)
    elsewhere = tmp_path / "another-repo"
    elsewhere.mkdir()
    setting, block = opening(skill)
    block = block.replace("<slug>", SLUG).replace("<name>", name).replace("<playbook>", text)
    setting = setting.replace("<name>", name)
    block = block.replace("<threadId>", THREAD)
    path = os.environ["PATH"] if real else f"{uv(tmp_path / 'bin')}{os.pathsep}{os.environ['PATH']}"
    cache = {"UV_CACHE_DIR": merge.uv_cache()} if real else {}
    ran = subprocess.run(
        [shell, "-c", f"{setting}\nS={SLUG}\n{block}"],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(user),
            "H": str(state),
            "M": str(state),
            "PATH": path,
            **cache,
        },
        cwd=elsewhere,
        check=True,
    )
    assert ran.stderr == ""
    return ran.stdout.splitlines()


def role(path):
    return run_by(path).split(",")[0]


def refused(skill, name, by):
    return [f"not {WHOSE[skill]}: playbooks/{name}.md is for {by}"]


@pytest.mark.parametrize("skill", WHOSE)
@pytest.mark.parametrize("name", NAMES)
def test_a_named_playbook_is_opened_by_its_role_alone_from_the_repo_the_skill_lives_in(
    skill, name, tmp_path
):
    by = role(PLAYBOOK[name])
    said = opened(skill, written(skill, f"Playbook: {name}"), tmp_path)
    if shape.ROLES[by] == skill:
        assert Path(said[0]) == PLAYBOOK[name].resolve()
        assert not any(line.startswith("not ") for line in said)
    else:
        assert said == refused(skill, name, by)


def made(tmp_path, asks=""):
    """A repo with the four skills and one playbook for each role. `asks` is what each
    `Run by:` line goes on to ask of the brief."""
    repo = tmp_path / "repo"
    (repo / "templates").mkdir(parents=True)
    (repo / "playbooks").mkdir()
    for skill in WHOSE:
        (repo / "skills" / skill).mkdir(parents=True)
    for name, by in MADE.items():
        said = by.removesuffix(".") + asks + "."
        (repo / "playbooks" / f"{name}.md").write_text(f"# A kind\n\nRun by: {said}\n")
    return repo


@pytest.mark.parametrize("skill", WHOSE)
@pytest.mark.parametrize("name", MADE)
def test_each_role_opens_its_own_playbook_and_refuses_the_other_three(skill, name, tmp_path):
    repo = made(tmp_path)
    by = MADE[name].split(",")[0]
    said = opened(skill, written(skill, f"Playbook: {name}"), tmp_path, repo)
    if shape.ROLES[by] == skill:
        assert said == [str((repo / "playbooks" / f"{name}.md").resolve())]
    else:
        assert said == refused(skill, name, by)


@pytest.mark.parametrize("skill", WHOSE)
@pytest.mark.parametrize("line", ["Playbook: none", "Playbook:", ""])
def test_with_none_or_no_line_no_playbook_is_opened(skill, line, tmp_path):
    assert opened(skill, written(skill, line), tmp_path) == []


@pytest.mark.parametrize("skill", WHOSE)
@pytest.mark.parametrize("name", ["bugfix", "bug-fix.md", "../skills/crew/SKILL"])
def test_a_name_that_is_no_file_in_playbooks_is_said_and_opens_nothing(skill, name, tmp_path):
    assert opened(skill, written(skill, f"Playbook: {name}"), tmp_path) == [
        f"no playbook: playbooks/ has no {name}.md"
    ]


@pytest.mark.parametrize("skill", READERS)
def test_only_the_first_playbook_line_is_the_homes(skill, tmp_path):
    text = written(skill, "Playbook: none") + "\n## Result\nPlaybook: bug-fix\n"
    assert opened(skill, text, tmp_path) == []


def test_a_home_reads_no_playbook_line_below_the_head_of_its_plan(tmp_path):
    repo = made(tmp_path)
    plan = written("home", "") + "Playbook: for-the-home\n"
    assert opened("home", plan, tmp_path, repo) == []


def test_a_name_given_to_a_home_is_opened_in_place_of_its_plans(tmp_path):
    repo = made(tmp_path)
    plan = written("home", "Playbook: none")
    assert opened("home", plan, tmp_path, repo, "for-the-home") == [
        str((repo / "playbooks" / "for-the-home.md").resolve())
    ]


ASKED = ["Pull request: ask first", "Review: none"]
ASKS = ", in a brief with `Pull request: ask first` and `Review: none`"


@pytest.mark.parametrize("skill", READERS)
def test_what_a_playbook_asks_of_the_brief_is_checked_against_it(skill, tmp_path):
    repo = made(tmp_path, ASKS)
    (name,) = [name for name, by in MADE.items() if shape.ROLES[by.split(",")[0]] == skill]
    text = written(skill, f"Playbook: {name}") + "Pull request: ask first\n"
    _, *said = opened(skill, text, tmp_path, repo)
    assert said == [
        "has the line the playbook asks for: Pull request: ask first",
        "lacks the line the playbook asks for: Review: none",
    ]


def test_what_a_homes_playbook_asks_of_a_brief_is_printed(tmp_path):
    repo = made(tmp_path, ASKS)
    _, *said = opened("home", written("home", "Playbook: for-the-home"), tmp_path, repo)
    assert said == [f"asks of its brief: {line}" for line in ASKED]


@pytest.mark.parametrize("name", ["prototype", "runtime-forensics"])
def test_a_playbook_that_asks_first_before_a_pull_request_says_so_when_opened(name, tmp_path):
    brief = written("crew", f"Playbook: {name}").replace(
        "Pull request: open one when done | ask first", "Pull request: open one when done"
    )
    _, *said = opened("crew", brief, tmp_path / "open")
    assert "lacks the line the playbook asks for: Pull request: ask first" in said
    brief = brief.replace("Pull request: open one when done", "Pull request: ask first")
    _, *said = opened("crew", brief, tmp_path / "ask")
    assert "has the line the playbook asks for: Pull request: ask first" in said


def offered(template):
    (line,) = [
        line
        for line in (TEMPLATES / template).read_text().splitlines()
        if line.startswith("Playbook:")
    ]
    values = [value.strip() for value in line.removeprefix("Playbook:").split("|")]
    return [value for value in values if not value.startswith("<")]


@pytest.mark.parametrize("skill", READERS)
def test_each_value_a_template_offers_opens_a_playbook_or_is_none(skill, tmp_path):
    values = offered(READERS[skill][1])
    assert "none" in values
    for n, value in enumerate(values):
        said = opened(skill, written(skill, f"Playbook: {value}"), tmp_path / str(n))
        assert said[:1] == ([] if value == "none" else [str(PLAYBOOK[value].resolve())])


def rows(templates):
    """What the home's block prints with `$T` at `templates`: a row for each file in the
    `playbooks/` beside it, as the name and what follows `Run by:`."""
    text = as_read(REPO / "skills" / "home" / "SKILL.md")
    (block,) = [
        found for found in FENCED.findall(text) if "Run by:" in found and "Playbook:" not in found
    ]
    ran = subprocess.run(
        ["sh", "-c", textwrap.dedent(block)],
        capture_output=True,
        text=True,
        env={**os.environ, "T": str(templates)},
        check=True,
    )
    assert ran.stderr == ""
    return [tuple(row.split(" | ", 1)) for row in ran.stdout.splitlines()]


def run_by(path):
    (said,) = re.findall(r"^Run by: (.*)$", path.read_text(), re.M)
    return said


def test_the_homes_block_prints_a_row_for_every_playbook_and_a_last_one_for_none():
    *said, last = rows(COPY / "templates")
    assert sorted(said) == [(name, run_by(PLAYBOOK[name])) for name in NAMES]
    assert last[0] == "none"


def test_a_playbook_added_to_the_directory_gets_a_row_with_no_other_edit(tmp_path):
    (tmp_path / "templates").mkdir()
    shutil.copytree(COPY / "playbooks", tmp_path / "playbooks")
    before = rows(tmp_path / "templates")
    assert before == rows(COPY / "templates")
    (tmp_path / "playbooks" / "a-new-kind.md").write_text(
        "# A new kind\n\nRun by: a crewmate, for a kind of task nobody wrote down before.\n"
    )
    added = ("a-new-kind", "a crewmate, for a kind of task nobody wrote down before.")
    after = rows(tmp_path / "templates")
    assert sorted(after[:-1]) == sorted([*before[:-1], added])
    assert after[-1] == before[-1]


def test_with_no_playbook_the_block_prints_the_row_for_none_alone(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "playbooks").mkdir()
    assert [name for name, _ in rows(tmp_path / "templates")] == ["none"]


@pytest.mark.parametrize("name", ["investigation", "opening-a-pr"])
def test_the_row_of_a_playbook_no_brief_names_says_it_is_never_picked(name):
    assert "never" in dict(rows(TEMPLATES))[name]


PROVEN = [
    "`make check` passes: `make check` printed `604 passed`, and the `Fixed: none` case",
    "the page shows it: opened the page, and the Review: line is there",
]
ENDED = ["it runs twice", f"the head {merge.REVIEWED} is old", "`git log -1` names the new one"]


def result(lines):
    """A Result's lines in the template's order: `lines` are the ones a test gives (`Fixed:`,
    `Rebase:`), and the template's own `Proof:` and `Finding:` lines are filled in."""
    given = {line.split()[0]: line for line in lines.splitlines()}
    filled = []
    for line in (TEMPLATES / "result.md").read_text().splitlines():
        label = line.split()[0]
        if label == "Proof:":
            filled.append(line)
        elif line.startswith("- <"):
            filled += [f"- {proof}" for proof in PROVEN]
        elif label == "Finding":
            shapes, _ = line.removeprefix("Finding F<n>:").split("   <")
            filled += [
                f"Finding F{n}: " + re.sub(r"<[^>]+>", "{}", shape.strip())
                for n, shape in enumerate(shapes.split("|"), 1)
            ]
            filled[-2:] = "\n".join(filled[-2:]).format(*ENDED).splitlines()
        elif label in given:
            filled.append(given.pop(label))
    assert given == {}
    return "".join(f"{line}\n" for line in filled)


@pytest.mark.parametrize(
    ("review", "lines", "head"),
    [
        ("findings", f"Fixed: {merge.PUSHED}\n", merge.PUSHED),
        ("findings", "Fixed: none needed, both are the brief's own shape\n", merge.REVIEWED),
        ("findings", "", merge.PUSHED),
        ("findings", f"Fixed: {merge.PUSHED}\n", merge.REVIEWED),
        ("clean", "", merge.REVIEWED),
        ("clean", f"Rebase: range-diff empty, head {merge.PUSHED}\n", merge.PUSHED),
        ("", "", merge.REVIEWED),
    ],
)
def test_proof_and_finding_lines_do_not_change_what_jmerge_says_is_ready(
    review, lines, head, tmp_path
):
    said = []
    answers = "".join(f"{line}\n" for line in result(lines).splitlines() if line[:7] == "Finding")
    for n, text in enumerate([lines + answers, result(lines)]):
        home = merge.Home(tmp_path / str(n))
        section = merge.review(review) if review else ""
        (home.tasks / "alpha.md").write_text(merge.brief(section, text))
        home.open_pull_request(head)
        said.append(home.ready())
    assert said[0] == said[1]
    assert said[0][0].split()[0] in ("ready", "wait")


def test_proof_lines_are_not_counted_as_findings_or_as_their_endings(tmp_path):
    later = "\n## Result, follow-up (a steer)\nProof:\n- it still passes: `make check`\n"
    brief = crew.reviewed(crew.TWO, result("")) + later
    assert crew.said(tmp_path, "The review", "--left", brief) == [
        "write Fixed: <the head you pushed>, 2 findings each have their ending"
    ]


PRINCIPLES = {
    "first-rule": "# First rule\n\nApply when one thing.\n\nThe whole of the first rule.\n",
    "second-rule": "# Second rule\n\nApply when another.\n\nThe whole of the second rule.\n",
    "unused-rule": "# Unused rule\n\nCited by no playbook here.\n",
}


def cited(tmp_path, steps):
    """A repo whose crewmate's and scout's playbooks have `steps` as their body, with the
    three principles above in its `principles/`."""
    repo = made(tmp_path)
    (repo / "principles").mkdir()
    for name, text in PRINCIPLES.items():
        (repo / "principles" / f"{name}.md").write_text(text)
    for name in ("for-a-crewmate", "for-a-scout"):
        playbook = repo / "playbooks" / f"{name}.md"
        playbook.write_text(playbook.read_text() + steps)
    return repo


TWO_CITED = (
    "\nA path such as `principles/<name>.md` is from the root of the repo.\n\n"
    "1. Do one thing (`principles/second-rule.md`).\n"
    "2. Do another (`principles/first-rule.md`, `principles/second-rule.md`).\n"
    "3. Check it (`principles/first-rule.md`).\n"
)


@pytest.mark.parametrize("skill", READERS)
def test_each_principle_the_playbook_cites_is_printed_once_in_full_after_it(skill, tmp_path):
    repo = cited(tmp_path, TWO_CITED)
    name = "for-a-crewmate" if skill == "crew" else "for-a-scout"
    said = opened(skill, written(skill, f"Playbook: {name}"), tmp_path, repo)
    at = said.index(
        f"the principles playbooks/{name}.md cites, each in full below: second-rule first-rule"
    )
    printed = "\n".join(said[at:]) + "\n"
    assert said[0] == str((repo / "playbooks" / f"{name}.md").resolve())
    for rule in ("first-rule", "second-rule"):
        assert printed.count(PRINCIPLES[rule]) == 1
        assert said.count(f"==> principles/{rule}.md <==") == 1
    assert PRINCIPLES["unused-rule"] not in printed
    assert printed.index(PRINCIPLES["second-rule"]) < printed.index(PRINCIPLES["first-rule"])


@pytest.mark.parametrize("skill", READERS)
def test_a_playbook_that_cites_no_principle_prints_its_steps_and_nothing_more(skill, tmp_path):
    repo = cited(
        tmp_path, "\nA path such as `principles/<name>.md` is from the root.\n\n1. Do it.\n"
    )
    name = "for-a-crewmate" if skill == "crew" else "for-a-scout"
    said = opened(skill, written(skill, f"Playbook: {name}"), tmp_path, repo)
    assert said == [
        str((repo / "playbooks" / f"{name}.md").resolve()),
        f"the steps of playbooks/{name}.md, a checklist to copy into your todo list as printed:",
        "1. Do it.",
    ]


@pytest.mark.parametrize("skill", READERS)
def test_a_cited_principle_that_is_not_there_is_said_and_the_rest_printed(skill, tmp_path):
    repo = cited(tmp_path, "\n1. One (`principles/gone-rule.md`, `principles/first-rule.md`).\n")
    name = "for-a-crewmate" if skill == "crew" else "for-a-scout"
    _, *said = opened(skill, written(skill, f"Playbook: {name}"), tmp_path, repo)
    assert said[1:4] == [
        "1. One (`principles/gone-rule.md`, `principles/first-rule.md`).",
        f"no principle: playbooks/{name}.md cites principles/gone-rule.md, which is not there",
        f"the principles playbooks/{name}.md cites, each in full below: first-rule",
    ]
    assert "\n".join(said).count(PRINCIPLES["first-rule"].strip()) == 1


@pytest.mark.parametrize("shell", ["sh", "zsh"])
@pytest.mark.parametrize("skill", READERS)
def test_a_real_playbook_prints_the_real_principles_it_cites_under_sh_and_zsh(
    skill, shell, tmp_path
):
    """The skill's call as an agent runs it, by the real `uv`: the copy of the block it
    replaced put every cited principle on one `==>` line under zsh, which splits no word."""
    name = "authoring-a-skill" if skill == "crew" else "investigation"
    playbook = PLAYBOOK[name].read_text()
    names = list(dict.fromkeys(re.findall(r"principles/([a-z0-9-]+)\.md", playbook)))
    assert len(names) >= 2
    said = opened(skill, written(skill, f"Playbook: {name}"), tmp_path, shell=shell, real=True)
    assert (
        f"the principles playbooks/{name}.md cites, each in full below: {' '.join(names)}" in said
    )
    printed = "\n".join(said) + "\n"
    for rule in names:
        assert printed.count((REPO / "principles" / f"{rule}.md").read_text()) == 1
        assert said.count(f"==> principles/{rule}.md <==") == 1


NUMBERED = re.compile(r"^\d+\. \S.*$", re.M)


@pytest.mark.parametrize(
    ("skill", "name"),
    [
        (READERS_OF[role(PLAYBOOK[name])], name)
        for name in NAMES
        if role(PLAYBOOK[name]) in READERS_OF
    ],
)
def test_every_step_of_a_real_playbook_is_printed_word_for_word_as_a_numbered_checklist(
    skill, name, tmp_path
):
    """Each numbered step of the playbook is one line under the line that names them, as the
    playbook has it and numbered 1 to the last."""
    steps = [step[0] for step in NUMBERED.finditer(PLAYBOOK[name].read_text())]
    assert [int(step.split(".")[0]) for step in steps] == list(range(1, len(steps) + 1))
    said = opened(skill, written(skill, f"Playbook: {name}"), tmp_path)
    at = said.index(
        f"the steps of playbooks/{name}.md, a checklist to copy into your todo list as printed:"
    )
    assert said[at + 1 : at + 1 + len(steps)] == steps
    following = said[at + 1 + len(steps) :][:1]
    assert not following or following[0].startswith(f"the principles playbooks/{name}.md cites")


@pytest.mark.parametrize("skill", READERS)
def test_a_numbered_line_that_does_not_start_a_line_is_no_step(skill, tmp_path):
    repo = cited(
        tmp_path, "\n1. Do one thing.\n   2. an indented line\nSee 3. in prose.\n2. Then.\n"
    )
    name = "for-a-crewmate" if skill == "crew" else "for-a-scout"
    _, *said = opened(skill, written(skill, f"Playbook: {name}"), tmp_path, repo)
    assert said[1:] == ["1. Do one thing.", "2. Then."]


def test_every_path_a_skill_reaches_through_its_templates_link_is_in_the_layout(tmp_path):
    """`T` is `<layout>/templates` once install.sh links a skill into its harness's layout, so
    `$T/../<path>` must name a file or folder the layout holds, not one it leaves in the
    checkout. Each one is tried from a skill linked as install.sh links it."""
    reached = sorted(
        {
            found.rstrip("/.")
            for path in COPY.rglob("*.md")
            for found in re.findall(r"\$T/\.\./([A-Za-z0-9_./-]+)", path.read_text())
        }
    )
    assert "skills/crew/do-the-task.md" in reached
    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "crew").symlink_to(COPY / "skills" / "crew")
    tried = subprocess.run(
        [
            "sh",
            "-c",
            "T=$(realpath ~/.claude/skills/crew/../../templates)\n"
            'for p; do [ -e "$T/../$p" ] || echo "$p"; done',
            "sh",
            *reached,
        ],
        env={**os.environ, "HOME": str(user)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert tried.stdout.splitlines() == []
