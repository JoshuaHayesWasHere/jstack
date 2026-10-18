"""The README, every page under `docs/` and every `skills/*/SKILL.md` agree with the tree.

`test_docs_true.py` holds the commands and their flags to `--help`. This module holds the rest of
what a page says about the tree, and reports each failure as `file:line: what is wrong`:

- A skill named as a slash command, `/<skill>`, as the first word of a code span or of a line
  of a fenced block, or in prose as "the `<skill>` skill", has a folder under `skills/`. A slash
  word that is no skill is listed in `NOT_SKILLS` with the reason.
- A path that starts at a folder of `ROOTS`, such as `skills/<skill>/SKILL.md` or
  `templates/brief.md`, is a file or folder that exists. A path with a placeholder, a glob, or a
  `/` before it (`~/.claude/skills/<skill>`, `$T/../playbooks/$name.md`) is somewhere else and is
  not read.
- A relative Markdown link points at a file that exists and, when it has a `#anchor` into a
  Markdown file, at a heading of that file as GitHub makes its anchor.
- A count of skills, commands, principles or playbooks that follows `has`, `holds`, `are` and the
  like, in the README or a page of `docs/`, is the number the tree has. A skill's own text counts
  things of its own, so it is not read for counts. The README's counts of skills, and every
  count of commands, are also held by `test_docs_true.py`.

`python tests/test_docs_tree.py [root]` prints the problems of a root and exits 1 when there is
one. The tests run it so, on the tree and on a copy of it with a fault put in.
"""

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote

import pytest

REPO = Path(__file__).parent.parent

NOT_SKILLS = {
    "clear": "a Claude Code command",
    "answer": "a reply to an item jbus asked about, in a webhook's reply",
    "ack": "the relay's route that takes an acknowledgement",
    "tmp": "the machine's temporary folder",
    "proc": "the machine's process folder",
}
ROOTS = ("skills", "templates", "playbooks", "principles", "hooks", "docs")
NUMBERS = (
    "zero one two three four five six seven eight nine ten "
    "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
).split()
HAS = r"(?:has|have|holds?|lists?|contains?|ships|are|is)"


def pages(root):
    """The files a root's checks read: the README, `docs/*.md` and each skill's `SKILL.md`."""
    return [
        root / "README.md",
        *sorted((root / "docs").glob("*.md")),
        *sorted((root / "skills").glob("*/SKILL.md")),
    ]


def lines_of(text):
    """Each line of a text with its number and whether it is inside a fenced block."""
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(("```", "~~~")):
            fenced = not fenced
            yield number, line, None
        else:
            yield number, line, fenced


def code_of(text):
    """Each piece of code: (line, piece), a line of a fenced block or one inline span."""
    for number, line, fenced in lines_of(text):
        if fenced:
            yield number, line.strip()
        elif fenced is not None:
            for piece in re.findall(r"`([^`\n]+)`", line):
                yield number, piece


def blank_code(line):
    """The line with its inline code spans blanked, so a link in a span is not a link."""
    return re.sub(r"`[^`\n]*`", lambda span: " " * len(span[0]), line)


def slug_of(heading):
    """The anchor GitHub gives a heading: no markup, lower case, no punctuation, `-` for space."""
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"[`*]", "", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")


def anchors_of(text):
    """The anchors of a Markdown text: its headings, repeats numbered, and its `id` and `name`s."""
    seen, found = {}, set()
    for _, line, fenced in lines_of(text):
        heading = re.match(r"#{1,6}\s+(.*?)\s*#*\s*$", line)
        if heading and fenced is False:
            slug = slug_of(heading[1])
            found.add(slug if slug not in seen else f"{slug}-{seen[slug]}")
            seen[slug] = seen.get(slug, 0) + 1
    return found | set(re.findall(r"""\b(?:id|name)=["']([^"']+)["']""", text))


def link_problems(root, page, text):
    found = []
    for number, line, fenced in lines_of(text):
        if fenced is not False:
            continue
        for target in re.findall(r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)", blank_code(line)):
            if re.match(r"([a-z][a-z0-9+.-]*:|//)", target, re.I):
                continue
            path, _, anchor = unquote(target).partition("#")
            at = (page.parent / path) if path else page
            if not at.exists():
                found.append(f"{number}: the link {target} goes to a file that is not there")
            elif anchor and at.suffix == ".md" and anchor not in anchors_of(at.read_text()):
                found.append(f"{number}: the link {target} goes to a heading that is not there")
    return found


def skill_names(root):
    return {path.parent.name for path in (root / "skills").glob("*/SKILL.md")}


def skill_problems(root, text):
    skills = skill_names(root)
    found = []
    for number, piece in code_of(text):
        word = piece.split()[0] if piece.split() else ""
        name = word[1:]
        if re.fullmatch(r"/[a-z][a-z0-9-]*", word) and name not in skills | set(NOT_SKILLS):
            found.append(f"{number}: /{name} is named as a skill and skills/ has no {name}")
    for number, line, fenced in lines_of(text):
        for pair in re.findall(
            r"`([a-z][a-z0-9-]*)` skills?\b|\bskills? `([a-z][a-z0-9-]*)`", line
        ):
            name = pair[0] or pair[1]
            if fenced is False and name not in skills:
                found.append(f"{number}: {name} is named as a skill and skills/ has no {name}")
    return sorted(found, key=lambda line: int(line.partition(":")[0]))


def path_problems(root, text):
    found = []
    pattern = rf"(?<![\w/.~<>*$-])((?:{'|'.join(ROOTS)})/[\w.-]+(?:/[\w.-]+)*)"
    for number, line, _ in lines_of(text):
        for path in re.findall(pattern, re.sub(r"\]\([^)]*\)", "]", line)):
            path = path.rstrip(".,:;")
            if not (root / path).exists():
                found.append(f"{number}: {path} is named and the tree has no such path")
    return found


def tree_counts(root):
    scripts = tomllib.loads((root / "pyproject.toml").read_text())["project"]["scripts"]
    return {
        "skills": len(list((root / "skills").glob("*/SKILL.md"))),
        "commands": len(scripts),
        "principles": len(list((root / "principles").glob("*.md"))),
        "playbooks": len(list((root / "playbooks").glob("*.md"))),
    }


def count_problems(root, text):
    tree = tree_counts(root)
    found = []
    for number, line, _ in lines_of(text):
        for noun, have in tree.items():
            for said in re.findall(
                rf"\b{HAS} (?:the |all )?(\d+|{'|'.join(NUMBERS)}) {noun}\b", line, re.I
            ):
                said = int(said) if said.isdigit() else NUMBERS.index(said.lower())
                if said != have:
                    found.append(f"{number}: it counts {said} {noun} and the tree has {have}")
    return found


def problems(root):
    """Every line of every page that says what the tree under `root` does not have."""
    found = []
    for page in pages(root):
        text = page.read_text()
        checks = [skill_problems, path_problems]
        if page.name != "SKILL.md":
            checks.append(count_problems)
        said = link_problems(root, page, text) + [
            line for check in checks for line in check(root, text)
        ]
        found += [f"{page.relative_to(root)}:{line}" for line in said]
    return found


def main(argv):
    """The command the tests run: each problem of the tree at argv[0], and 1 when there is one."""
    found = problems(Path(argv[0]) if argv else REPO)
    if found:
        print("\n".join(found))
    return 1 if found else 0


def ran(root):
    """The lines this module prints when run as a command on a root, and its exit code agreed."""
    done = subprocess.run(
        [sys.executable, __file__, str(root)], capture_output=True, text=True, check=False
    )
    assert done.stderr == ""
    assert done.returncode == (1 if done.stdout else 0)
    return done.stdout.splitlines()


def test_the_readme_the_docs_and_the_skills_say_nothing_the_tree_does_not_have():
    assert ran(REPO) == []


def test_the_tree_is_read_whole_and_counted():
    counts = tree_counts(REPO)
    assert len(counts) == 4 and all(count >= 7 for count in counts.values())
    assert len(pages(REPO)) > 40


@pytest.fixture
def copy(tmp_path):
    """A copy of the parts of the tree the checks read, for a test to put a fault into."""
    for source in REPO.iterdir():
        if source.is_file():
            shutil.copy(source, tmp_path / source.name)
    for name in ROOTS:
        shutil.copytree(REPO / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def test_a_copy_with_a_broken_link_an_unknown_skill_and_a_wrong_count_fails_each_time(copy):
    assert ran(copy) == []
    readme = copy / "README.md"
    readme.write_text(readme.read_text() + "\nSee [FAKE page](docs/fake-missing.md).\n")
    page = copy / "docs" / "state.md"
    page.write_text(page.read_text() + "\nRun `/fake-skill` first.\n")
    count = copy / "docs" / "playbooks.md"
    count.write_text(count.read_text() + "\nThe tree has 99 principles.\n")
    found = ran(copy)
    assert len(found) == 3, found
    assert found[0].startswith("README.md:") and "docs/fake-missing.md" in found[0]
    assert found[1].startswith("docs/playbooks.md:") and "counts 99 principles" in found[1]
    assert found[2].startswith("docs/state.md:") and "/fake-skill is named as a skill" in found[2]
    for line in found:
        assert re.match(r"[\w/.-]+:\d+: \S", line), line


def make(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


@pytest.fixture
def small(tmp_path):
    return make(
        tmp_path,
        {
            "pyproject.toml": '[project.scripts]\nfake-a = "x:y"\nfake-b = "x:y"\n',
            "skills/alpha/SKILL.md": "# Alpha\n",
            "skills/beta/SKILL.md": "# Beta\n",
            "principles/one.md": "# One\n",
            "playbooks/p.md": "# P\n",
            "templates/t.md": "# T\n",
            "README.md": "# FAKE\n",
        },
    )


def test_a_link_to_a_file_or_a_heading_that_is_not_there_is_found(small):
    make(
        small,
        {
            "docs/a.md": (
                "# Top\n\n## Same\n\n## Same\n\n## A `code` [heading](b.md) & more!\n"
                "[ok](b.md) [ok](b.md#the-second-one) [ok](#same-1) [ok](#a-code-heading--more)\n"
                "[web](https://example.com/x) [mail](mailto:a@b.c) [img](pic.svg)\n"
                "[gone](nope.md)\n[no heading](b.md#nowhere)\n[no self heading](#nowhere)\n"
                "`[inside code](nope.md)`\n```\n[in a fence](nope.md)\n```\n"
            ),
            "docs/b.md": "# B\n\n## The second one\n",
            "docs/pic.svg": "<svg/>",
        },
    )
    assert ran(small) == [
        "docs/a.md:10: the link nope.md goes to a file that is not there",
        "docs/a.md:11: the link b.md#nowhere goes to a heading that is not there",
        "docs/a.md:12: the link #nowhere goes to a heading that is not there",
    ]


def test_a_skill_named_that_the_tree_lacks_is_found_in_a_page_and_in_a_skill(small):
    make(
        small,
        {
            "docs/a.md": (
                "Run `/alpha run x`, then `/clear`, read `/tmp`, not `/tmp/x` or `/alpha/b`.\n"
                "Then `/gamma` and\n```\n/beta now\n/delta now\n```\n"
                "and `a /epsilon` is not read.\n"
                "The `alpha` skill, the skill `theta` and the `iota` skills.\n"
            ),
            "skills/beta/SKILL.md": "# Beta\n\nAsk `/zeta` for it.\n",
        },
    )
    assert ran(small) == [
        "docs/a.md:2: /gamma is named as a skill and skills/ has no gamma",
        "docs/a.md:5: /delta is named as a skill and skills/ has no delta",
        "docs/a.md:8: theta is named as a skill and skills/ has no theta",
        "docs/a.md:8: iota is named as a skill and skills/ has no iota",
        "skills/beta/SKILL.md:3: /zeta is named as a skill and skills/ has no zeta",
    ]


def test_a_path_that_is_gone_is_found_and_one_somewhere_else_is_not_read(small):
    make(
        small,
        {
            "docs/a.md": (
                "`skills/alpha/SKILL.md` `templates/t.md` `skills/gone/SKILL.md`\n"
                "`skills/alpha/missing.md.` [a link](../templates/t.md)\n"
                "`~/.claude/skills/<name>` `$T/../playbooks/$name.md` `skills/*-mode/SKILL.md`\n"
                "`.cursor/skills/other` `skills/<skill>` and `../templates/t.md`\n"
            ),
        },
    )
    assert ran(small) == [
        "docs/a.md:1: skills/gone/SKILL.md is named and the tree has no such path",
        "docs/a.md:2: skills/alpha/missing.md is named and the tree has no such path",
    ]


def test_a_count_the_tree_disagrees_with_is_found(small):
    make(
        small,
        {
            "docs/a.md": (
                "`skills/` holds 2 skills and has one principle, so there are two commands.\n"
                "It has 12 skills, holds six commands and has three principles.\n"
                "The tree has 4 playbooks, and at most three skills run it. Seven commands.\n"
            ),
        },
    )
    assert ran(small) == [
        "docs/a.md:2: it counts 12 skills and the tree has 2",
        "docs/a.md:2: it counts 6 commands and the tree has 2",
        "docs/a.md:2: it counts 3 principles and the tree has 1",
        "docs/a.md:3: it counts 4 playbooks and the tree has 1",
    ]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
