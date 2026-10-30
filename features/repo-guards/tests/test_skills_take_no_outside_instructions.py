"""No skill or playbook takes its instructions from a file outside the jstack repo.

The rule is the user's (2026-10-14, standing rule 23, and 2026-10-26: a rule the homes juggle
becomes a lint): skills take no instructions from outside the jstack repo, and the state folders
hold facts, never instructions. What a thread follows is skill text, and skill text is in the
repo, reviewed and versioned; a rule kept in `~/.local/state`, `~/.config` or another repo
changes what every thread does with no pull request and no test.

The lint reads every skill, playbook, principle and template file as the harness installs them
(`testing.layouts.assembled`) and finds each text file it names outside the repo: a path under
`~/.local/state`, `~/.config` or `~/repos`, written as it is or through a shell variable a skill
sets to one (`H=~/.local/state/home/$R`, then `M=$H` and `B="$H/tasks/<slug>.md"`). A text file
is one with an extension of `TEXT`, the kind a thread reads as prose. A file whose content is
data a block or a command reads (an id, a log, a lock, a JSON record, a stamp) is no instruction
and is not checked here.

Each text file found under `~/.local/state` must be on `FACTS`, the fact files, each with why it
holds facts and not instructions. None under `~/.config` or another repo is: a config holds
settings, and a text file of another repo is that repo's. A file that holds rules is moved into
the repo, as skill text or a template, and never added to `FACTS`.
"""

import re
from fnmatch import fnmatchcase

import pytest

from testing.layouts import assembled


def variable(name):
    """A shell variable as a pattern: `$H`, `${H}`, or `${H:-<its default>}`, with `-`, `=` or `:=`
    in place of `:-` too. A default is read only inside braces: `$H-based` is `$H`."""
    return rf"\$(?:\{{{name}:?[-=][^}}]*\}}|\{{?{name}\b\}}?)"


READ_SET = ("*.md",)
INSTALLED = ("skills/**/*.md", "playbooks/*.md", "principles/*.md", "templates/**/*.md")
ROOTS = {
    r"~/\.local/state": "state",
    r"\$HOME/\.local/state": "state",
    variable("XDG_STATE_HOME"): "state",
    r"~/\.config": "config",
    r"\$HOME/\.config": "config",
    variable("XDG_CONFIG_HOME"): "config",
    r"~/repos": "repos",
    r"\$HOME/repos": "repos",
}
FENCED = re.compile(r"^[ \t]*```(?:sh|bash|shell|zsh)\n(.*?)^[ \t]*```[ \t]*$", re.M | re.S)
ASSIGNED = re.compile(r"(?<![\w$])([A-Za-z_]\w*)=(\S+)")
SEGMENT = r"(?:/[A-Za-z0-9_.<>*{}$:%#-]+)"
TEXT = (".md", ".markdown", ".mdx", ".txt", ".prompt")

FACTS = {
    "tasks/*.md": "a brief: one task, written by the home for one thread, and its Result",
    "scouts/*.md": "a scout request: one question, written by the home for one scout",
    "plan.md": "a home's plan: the tasks it holds and their order",
    "standing.md": "the user's standing rules, at most three, each coded or on its way to code"
    " (fl-standing-cap)",
    "handoff.md": "the note one home leaves the next: where things stand",
    "handoff.next.md": "a handoff written ahead of the one it replaces, the same note",
    "plan-archived.md": "an archived scope's plan, moved out of plan.md: the same facts",
    "gates.md": "a home's open questions to the user and the defaults taken",
    "gates-moved.md": "a gates.md jbus has moved its questions out of, kept as a record",
    "RESTART.md": "the page a handoff writes of what a restarted home finds, where things stand",
    "reports/*.md": "a report a scout or a skill writes of what it found",
    "notes/*.md": "an expert's notes and their index: what it understood, each claim with its"
    " source",
    "CHARTER.md": "an expert's subject and its bounds, written by the user, as a brief is",
    "sources.md": "where an expert's truth lives, each source pinned to a revision",
    "corrections.md": "the user's corrections of an expert, in the user's words",
    "unknowns.md": "what an expert could not answer: its study list",
    "syllabus.md": "the questions an expert studies, in order, written by the user",
}


def files():
    at = assembled()
    for pattern in INSTALLED:
        for path in sorted(at.glob(pattern)):
            yield path.relative_to(at).as_posix(), path.read_text()


def roots(texts):
    """The roots outside the repo, each a pattern with the place it is in: the literal ones of
    `ROOTS`, and each shell variable a skill sets to one, as a pattern that matches it written
    `$H`, `${H}` or `${H:-<a default>}`. A variable set from another one outside is in the same
    place: `M=$H` and `M=${H%/*}/_$P`."""
    texts, found = list(texts), dict(ROOTS)
    while True:
        more = {
            variable(name): place
            for text in texts
            for name, value in ASSIGNED.findall(text)
            for root, place in found.items()
            if re.match(rf"""["']?(?:\$\{{\w+:-)?(?:{root})""", value)
        }
        if more.keys() <= found.keys():
            return found
        found = more | found


def named(text, found):
    """Each text file `text` names outside the repo, as `(place, the path past its root)`."""
    for root, place in found.items():
        for match in re.finditer(rf"(?:{root})({SEGMENT}+)", text):
            path = re.sub(r"(?:#[\w.-]*|:\d+|[*_.,:;])+$", "", match.group(1))
            if path.endswith(TEXT):
                yield place, path


def fact(place, path):
    """The `FACTS` line that covers `path`, matched on its last part, or on its last two when
    the last is a placeholder: `tasks/<slug>.md` is `tasks/*.md`. Only a file in the state
    folders can be one."""
    if place != "state":
        return None
    parts = [re.sub(r"<[^>]*>|\$\{[^}]*\}|\$\w+", "*", one) for one in path.split("/")[-2:]]
    for key in FACTS:
        if fnmatchcase(parts[-1], key) or fnmatchcase("/".join(parts), key):
            return key
    return None


def scopes(read):
    """The roots each file sees. A skill's files see the variables its own folder sets, since
    `SKILL.md` sets them for the files it sends a thread to. A playbook, a principle or a
    template sets none and is read under a skill's block at the top, the first block of its
    `SKILL.md`, so it sees the variables those blocks set."""
    folders = {}
    for name, text in read:
        if name.startswith("skills/"):
            folders.setdefault("/".join(name.split("/")[:2]), []).append(text)
    tops = [FENCED.search(text) for name, text in read if name.endswith("/SKILL.md")]
    shared = roots(top.group(1) for top in tops if top)
    seen = {folder: roots(texts) for folder, texts in folders.items()}
    for name, _ in read:
        yield seen.get("/".join(name.split("/")[:2]), shared)


def outside():
    """Each text file outside the repo a skill names, as `(file, place, path)`."""
    read = list(files())
    for (name, text), found in zip(read, scopes(read), strict=True):
        for place, path in named(text, found):
            yield name, place, path


def disagreements():
    """Where the skills and `FACTS` disagree: each text file outside the repo a skill names
    that `FACTS` does not cover, as `(file, place, path)`, then each `FACTS` line that covers
    no file a skill names, so that the list cannot keep a fact file no skill reads."""
    found = list(outside())
    flagged = {(name, place, path) for name, place, path in found if not fact(place, path)}
    covered = {fact(place, path) for _, place, path in found}
    return sorted(flagged) + [("FACTS", "unused", key) for key in FACTS if key not in covered]


def test_no_skill_takes_instructions_from_outside_the_repo():
    assert disagreements() == []


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("Read `~/.local/state/home/_experts/README.md` whole.", ["/home/_experts/README.md"]),
        ("H=~/.local/state/home/$R\n\nRead `$H/rules.md` and follow it.", ["/rules.md"]),
        ('H=~/.local/state/home/$R\nM=${H%/*}/_$P\ncat "$M/how-to.md"', ["/how-to.md"]),
        ("H=${XDG_STATE_HOME}/home\nRead `$H/rules.prompt`.", ["/rules.prompt"]),
        ("H=~/.local/state/home/$R\nRead `${H}/tasks/<slug>.md`.", []),
        ("Read `~/.config/jstack/rules.txt`.", ["/jstack/rules.txt"]),
        ("Read `~/.config/jstack/notes.md`.", ["/jstack/notes.md"]),
        ("Follow `~/repos/hydra/skills/home/SKILL.md`.", ["/hydra/skills/home/SKILL.md"]),
        ("Read `~/repos/hydra/plan.md`.", ["/hydra/plan.md"]),
        ("H=~/.local/state/home/$R\nRead `$H/plan.md`, `$H/home-id` and `$H/merge.log`.", []),
        ("H=~/.local/state/home/$R\nRead `$H/notes.md`.", ["/notes.md"]),
        ("Read `$T/../skills/crew/do-the-task.md` and `$H/rules.md`.", []),
        ("C=$(git rev-parse --show-toplevel)\nRead `$C/docs/notes.md`.", []),
        ("Read `$HOME/notes.md` and `$HOMEDIR/x/rules.md`.", []),
        ("Read **~/.local/state/home/x/rules.md** and follow it.", ["/home/x/rules.md"]),
        ("Read _~/.local/state/home/x/rules.md_.", ["/home/x/rules.md"]),
        ("See ~/.local/state/home/x/rules.md:12, then follow it.", ["/home/x/rules.md"]),
        ("Read ~/.local/state/home/x/rules.md#section and follow it.", ["/home/x/rules.md"]),
        ("Read `${XDG_STATE_HOME:-~/.local/state}/home/x/rules.md`.", ["/home/x/rules.md"]),
        ("H=~/.local/state/home/$R\nRead `${H:-/tmp}/rules.md`.", ["/rules.md"]),
        ("Read `${XDG_STATE_HOME-~/.local/state}/home/x/rules.md`.", ["/home/x/rules.md"]),
        ("Read `${XDG_STATE_HOME=~/.local/state}/home/x/rules.md`.", ["/home/x/rules.md"]),
        ("Read `${XDG_STATE_HOME:=~/.local/state}/home/x/rules.md`.", ["/home/x/rules.md"]),
        ("H=~/.local/state/home/$R\nThe $H-based files stay put.\nSee ./docs/guide.md.", []),
        ("H=~/.local/state/home/$R\nSet $H=1, then see ./docs/guide.md.", []),
    ],
)
def test_the_lint_finds_a_text_file_outside_the_repo_that_is_no_fact_file(text, said):
    found = [path for place, path in named(text, roots([text])) if not fact(place, path)]
    assert found == said
