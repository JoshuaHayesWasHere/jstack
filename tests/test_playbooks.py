import re
import shutil

import pytest

from jdrift.explained import COMMENT as CARD
from testing.paths import REPO

PLAYBOOKS = REPO / "playbooks"
TEMPLATE = "templates/playbook.md"
COPY = "harness/jstack/claude-code"
EM_DASH = "\N{EM DASH}"
FILES = sorted(PLAYBOOKS.glob("*.md"))
ROLES = {"a crewmate": "crew", "a scout": "scout", "the home": "home", "an expert": "expert"}
MAX_WORDS = 900
CREW_ENDS_IN = ("playbooks/opening-a-pr.md", "skills/crew/SKILL.md")
NAMED = re.compile(r"\b(?:principles|playbooks|skills|templates)/[A-Za-z0-9_/-]+\.md\b")
OPEN = re.compile(r"skills/<[^>]+>/SKILL\.md")


def named(text):
    return sorted(set(NAMED.findall(text)))


def steps(text):
    """The numbers of the playbook's steps, the lines a reader copies in as todos."""
    return [int(n) for n in re.findall(r"^(\d+)\. \S", text, re.M)]


def paragraphs(text):
    """The paragraphs of `text`, each with its line breaks read as spaces: a paragraph written
    one sentence a line, as `scripts/prose_lint.py` asks of a new line, is the same paragraph."""
    return [" ".join(part.split()) for part in re.split(r"\n\s*\n", text.strip())]


def line(label, text):
    found = re.search(rf"^{label}: (.*)$", text, re.M)
    return found.group(1) if found else None


def frame(root):
    """What every playbook carries as the template at `root` has it: the two standing
    paragraphs, the label of the list of what is never done, and that of the hand-over line."""
    parts = paragraphs((root / TEMPLATE).read_text())
    return parts[3:5], parts[-3], re.match(r"\*\*[^*]+\*\*", parts[-1]).group()


def standing(root, skill):
    """The two standing paragraphs as a playbook of the role that reads `skill` carries them."""
    return [OPEN.sub(f"skills/{skill}/SKILL.md", part) for part in frame(root)[0]]


def problems(path, root):
    """What stops a reader from following the playbook at `path`, in a repo at `root`."""
    text = path.read_text()
    parts = paragraphs(text)
    paragraph, never, hand = frame(root)
    found = []
    if not re.match(r"# \S", text):
        found.append("does not open with a heading")
    run = line("Run by", text)
    role = re.fullmatch(rf"({'|'.join(ROLES)}), for \S.*", run or "")
    if run is None:
        found.append("has no `Run by:` line")
    elif not role:
        found.append(f"is not run by one of {', '.join(ROLES)}, for a trigger")
    source = line("Source", text) or ""
    if not re.fullmatch(r"this repo|pstack, \S.*", source):
        found.append("has no `Source:` line that says `this repo` or `pstack, <file>`")
    for n, part in enumerate(paragraph, 1):
        if role:
            part = OPEN.sub(f"skills/{ROLES[role.group(1)]}/SKILL.md", part)
        if part not in parts and (role or not OPEN.search(part)):
            found.append(f"does not carry standing paragraph {n} of {TEMPLATE}")
    first = next((n for n, part in enumerate(parts) if re.match(r"1\. ", part)), len(parts))
    if not any(part.startswith("**") and not part.startswith(hand) for part in parts[:first]):
        found.append("has no bold line before step 1 that says what its reader owns")
    if not steps(text):
        found.append("has no steps")
    elif steps(text) != list(range(1, len(steps(text)) + 1)):
        found.append(f"numbers its steps {steps(text)}")
    names = named("\n".join(row for row in text.splitlines() if not row.startswith("Source:")))
    # A named path is read from the copy an agent is linked to, where the repo has one.
    read = root / COPY if (root / COPY).is_dir() else root
    found += [f"names {name}, which is not there" for name in names if not (read / name).is_file()]
    if not any(name.startswith("principles/") for name in names):
        found.append("names no principle")
    if never not in parts[:-1] or not parts[parts.index(never) + 1].startswith("- "):
        found.append(f"has no list under `{never}`")
    if not parts[-1].startswith(f"{hand} "):
        found.append(f"does not end with its `{hand}` line")
    bodies = re.findall(r"^\d+\. (.*)$", text, re.M)
    if role and role.group(1) == "a crewmate" and bodies:
        if not any(name in bodies[-1] for name in CREW_ENDS_IN):
            found.append(
                f"is a crewmate's, and its last step names neither of {', '.join(CREW_ENDS_IN)}"
            )
    words = len(CARD.sub("", text).split())
    if words > MAX_WORDS:
        found.append(f"has {words} words, over {MAX_WORDS}")
    lines = [n for n, row in enumerate(text.splitlines(), 1) if EM_DASH in row]
    if lines:
        found.append(f"has an em dash on line {lines}")
    credit = root / "THIRD_PARTY.md"
    if source.startswith("pstack, ") and not (
        credit.is_file() and f"`{path.name}`" in credit.read_text()
    ):
        found.append("is drawn from pstack, and THIRD_PARTY.md does not name it")
    return found


def uncited(root):
    """The principles at `root` that no playbook there names, so no thread is sent to read them."""
    cited = set()
    for path in (root / "playbooks").glob("*.md"):
        rows = path.read_text().splitlines()
        cited.update(named("\n".join(row for row in rows if not row.startswith("Source:"))))
    every = (f"principles/{path.name}" for path in (root / "principles").glob("*.md"))
    return sorted(name for name in every if name not in cited)


PRINCIPLES_OF_TESTS_AND_CODE = (
    "principles/principle-test-behavior-not-implementation.md",
    "principles/principle-sequence-verifiable-units.md",
)


def design_problems(text):
    """What is wrong with the design step of a playbook: one read-only subagent, before code."""
    bodies = re.findall(r"^\d+\. (.*)$", text, re.M)
    design = [
        n
        for n, body in enumerate(bodies, 1)
        if "`Explore`" in body and "read-only" in body and "size M and up" in body
    ]
    if not design:
        return ["has no design step"]
    code = [
        n
        for n, body in enumerate(bodies, 1)
        if any(name in body for name in PRINCIPLES_OF_TESTS_AND_CODE)
    ]
    if code and design[0] > code[0]:
        return [f"has its design step {design[0]} after step {code[0]}, which writes code"]
    if "counts as S" not in bodies[design[0] - 1]:
        return ["does not say what size a brief with none has"]
    return []


def test_the_directory_holds_playbooks_and_nothing_else():
    assert sorted(PLAYBOOKS.iterdir()) == FILES


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.stem)
def test_a_playbook_has_the_shape_and_can_be_followed(path):
    assert problems(path, REPO) == []


def test_every_principle_is_named_by_a_playbook():
    assert uncited(REPO) == []


@pytest.fixture
def root(tmp_path):
    """A repo with the real template, and the files the playbook built below names."""
    (tmp_path / "templates").mkdir()
    shutil.copy(REPO / TEMPLATE, tmp_path / TEMPLATE)
    for skill in ROLES.values():
        (tmp_path / "skills" / skill).mkdir(parents=True)
        (tmp_path / "skills" / skill / "SKILL.md").write_text("# There\n")
    for name in ("principles/one.md", "playbooks/opening-a-pr.md"):
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_text("# There\n")
    return tmp_path


OWNS = "**You own the thing.** All of it."


def written(root, skill="crew", **changed):
    copy, paths = standing(root, skill)
    _, never, hand = frame(root)
    parts = {
        "heading": "# A playbook",
        "run": "Run by: a crewmate, for a kind of task.",
        "source": "Source: this repo",
        "copy": copy,
        "paths": paths,
        "owns": OWNS,
        "steps": "1. Read `principles/one.md`.\n2. Run `playbooks/opening-a-pr.md`.",
        "never": never,
        "list": "- **Merging.** The home does.",
        "hand": f"{hand} in the Result, to the home: what was done.",
    } | changed
    return "\n\n".join(part for part in parts.values() if part is not None) + "\n"


def check(root, skill="crew", **changed):
    path = root / "playbooks" / "a-playbook.md"
    path.write_text(written(root, skill, **changed))
    return problems(path, root)


def test_a_playbook_with_every_part_has_no_problem(root):
    assert check(root) == []


@pytest.mark.parametrize("gone", ["principles/one.md", "playbooks/opening-a-pr.md"])
def test_a_named_file_that_is_missing_is_a_problem(root, gone):
    (root / gone).unlink()
    assert check(root) == [f"names {gone}, which is not there"]


def test_no_heading_is_a_problem(root):
    assert check(root, heading=None) == ["does not open with a heading"]


def test_no_run_by_line_is_a_problem(root):
    assert check(root, run=None) == ["has no `Run by:` line"]


@pytest.mark.parametrize(
    "run",
    [
        "Run by: an agent, for a kind of task.",
        "Run by: a crewmate or a scout, for a kind of task.",
        "Run by: a crewmate, as the last step.",
    ],
)
def test_an_unknown_role_or_no_trigger_is_a_problem(root, run):
    assert check(root, run=run) == [
        "is not run by one of a crewmate, a scout, the home, an expert, for a trigger"
    ]


@pytest.mark.parametrize("source", [None, "Source: somewhere", "Source: pstack"])
def test_a_source_that_is_neither_this_repo_nor_a_pstack_file_is_a_problem(root, source):
    assert check(root, source=source) == [
        "has no `Source:` line that says `this repo` or `pstack, <file>`"
    ]


def test_a_standing_paragraph_that_differs_from_the_template_is_a_problem(root):
    copy, paths = standing(root, "crew")
    assert check(root, copy=copy.replace("word for word", "roughly")) == [
        "does not carry standing paragraph 1 of templates/playbook.md"
    ]
    assert check(root, paths=None) == [
        "does not carry standing paragraph 2 of templates/playbook.md"
    ]


def test_a_scouts_playbook_carries_the_scout_skills_path_and_not_the_crews(root):
    scout = {
        "run": "Run by: a scout, for a kind of question.",
        "steps": "1. Read `principles/one.md`.\n2. Write the report.",
    }
    assert check(root, "scout", **scout) == []
    assert check(root, "crew", **scout) == [
        "does not carry standing paragraph 2 of templates/playbook.md"
    ]


def test_no_bold_line_of_what_the_reader_owns_before_step_1_is_a_problem(root):
    said = ["has no bold line before step 1 that says what its reader owns"]
    assert check(root, owns=None) == said
    assert check(root, owns="You own the thing. All of it.") == said


def test_no_steps_is_a_problem(root):
    assert check(root, steps="Read `principles/one.md`.") == ["has no steps"]


def test_a_step_out_of_order_is_a_problem(root):
    steps = "1. Read `principles/one.md`.\n3. Run `playbooks/opening-a-pr.md`."
    assert check(root, steps=steps) == ["numbers its steps [1, 3]"]


def test_no_principle_named_is_a_problem(root):
    steps = "1. Read the code.\n2. Run `playbooks/opening-a-pr.md`."
    assert check(root, steps=steps) == ["names no principle"]


def test_no_never_done_list_is_a_problem(root):
    _, never, _ = frame(root)
    said = [f"has no list under `{never}`"]
    assert never.startswith("Never done")
    assert check(root, never=None) == said
    assert check(root, never="What a crewmate does not do here:") == said
    assert check(root, **{"list": None}) == said


def test_no_hand_over_line_is_a_problem(root):
    _, _, hand = frame(root)
    said = [f"does not end with its `{hand}` line"]
    assert check(root, hand=None) == said
    assert check(root, hand="**In the Result:** what was done.") == said


def test_a_crewmates_playbook_that_does_not_end_in_the_pull_request_is_a_problem(root):
    steps = "1. Read `principles/one.md`.\n2. Stop."
    assert check(root, steps=steps) == [
        "is a crewmate's, and its last step names neither of"
        " playbooks/opening-a-pr.md, skills/crew/SKILL.md"
    ]
    assert check(root, steps=steps.replace("Stop", 'Do `skills/crew/SKILL.md` "End"')) == []


def test_more_than_900_words_is_a_problem(root):
    room = 900 - len(written(root).split())
    assert check(root, owns=OWNS + " word" * room) == []
    assert check(root, owns=OWNS + " word" * (room + 1)) == ["has 901 words, over 900"]


def test_the_card_line_of_the_explainer_page_is_not_counted(root):
    full = OWNS + " word" * (900 - len(written(root).split()))
    assert check(root, owns=f"<!-- card: A tile | 1 | What it is for. -->\n\n{full}") == []


def test_an_em_dash_is_a_problem(root):
    assert check(root, owns=f"**You own the thing.** One {EM_DASH} and another.") == [
        "has an em dash on line [11]"
    ]


def test_third_party_has_to_cover_a_playbook_only_when_its_source_is_pstack(root):
    pstack = "Source: pstack, `pstack/skills/a/SKILL.md`"
    said = ["is drawn from pstack, and THIRD_PARTY.md does not name it"]
    assert check(root, source=pstack) == said
    (root / "THIRD_PARTY.md").write_text("Covered: `another.md`.\n")
    assert check(root, source=pstack) == said
    assert check(root) == []
    (root / "THIRD_PARTY.md").write_text("Covered: `a-playbook.md`.\n")
    assert check(root, source=pstack) == []


def test_the_feature_playbook_has_its_design_step_before_code():
    assert design_problems((PLAYBOOKS / "feature.md").read_text()) == []


DESIGN = (
    "1. For a task of size M and up, start one read-only subagent (`Explore`)."
    " A brief with no size counts as S.\n"
)
BUILD = "2. Build it in small units (`principles/principle-sequence-verifiable-units.md`).\n"


def test_a_design_step_before_the_code_has_no_problem():
    assert design_problems("# A playbook\n\n" + DESIGN + BUILD) == []


def test_no_design_step_is_a_problem():
    assert design_problems("# A playbook\n\n" + BUILD) == ["has no design step"]


def test_a_design_step_after_the_code_is_a_problem():
    late = "1. " + BUILD[3:] + "2. " + DESIGN[3:]
    assert design_problems("# A playbook\n\n" + late) == [
        "has its design step 2 after step 1, which writes code"
    ]


def test_a_design_step_that_leaves_a_brief_with_no_size_open_is_a_problem():
    text = "# A playbook\n\n" + DESIGN.replace(" A brief with no size counts as S.", "") + BUILD
    assert design_problems(text) == ["does not say what size a brief with none has"]


def test_a_principle_no_playbook_names_is_uncited(root):
    (root / "principles" / "two.md").write_text("# There\n")
    check(root)
    assert uncited(root) == ["principles/two.md"]
    both = "1. Read `principles/one.md` and `principles/two.md`.\n"
    check(root, steps=both + "2. Run `playbooks/opening-a-pr.md`.")
    assert uncited(root) == []


def test_a_principle_named_only_on_the_source_line_is_uncited(root):
    check(
        root,
        source="Source: pstack, `principles/one.md`",
        steps="1. Read the code.\n2. Run `playbooks/opening-a-pr.md`.",
    )
    assert uncited(root) == ["principles/one.md"]
