"""These tests cover a brief's `Skills:` line. The one resolver resolves each name. The
queue and the launch refuse a name that is no skill or principle, and the merge waits until
the Result has an artifact for each name. The names are pstack's, and the old principle
names still resolve."""

import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import test_home_merge as merge
from jbriefs import parse, skills
from jmerge import ready
from test_jbus_queue import add, brief, gates, queued_before
from testing.paths import REPO, sources
from testing.paths import skills as skill_folders

FIXTURES = Path(__file__).parent / "fixtures"
THIRD_PARTY = REPO / "THIRD_PARTY.md"
NAMED = "Skills: in-your-own-words, principle-model-the-domain, prove-it-works\n"
ARTIFACTS = (
    "Skills run:\n"
    "- in-your-own-words: the user wants each skill a brief names to reach the crewmate\n"
    "- model-the-domain: Named(said, path), resolved once; missing() is the gap\n"
    "- principle-prove-it-works: uv run pytest tests/test_skills_named.py\n"
    "  42 passed\n"
)


@pytest.fixture
def home(tmp_path):
    return merge.Home(tmp_path)


def reviewed(result):
    """A brief that names three skills, its Result, and a clean review of its head."""
    return merge.brief(merge.review("clean"), result, NAMED)


def test_a_result_with_an_artifact_for_each_named_skill_merges(home):
    (home.tasks / "alpha.md").write_text(reviewed(ARTIFACTS))
    home.open_pull_request(merge.REVIEWED)
    assert home.ready() == [f"ready 7 {merge.REVIEWED} alpha alpha"]


HOLLOW = {
    "no item": "",
    "an empty one": "- principle-prove-it-works:\n",
    "a placeholder": "- principle-prove-it-works: <the command and its output>\n",
    "none": "- prove-it-works: none\n",
    "TBD": "- prove-it-works: TBD\n",
    "a skip": "- prove-it-works: skip: no time\n",
}


@pytest.mark.parametrize("case", HOLLOW)
def test_a_result_missing_an_artifact_waits_and_names_the_skill(home, case):
    result = ARTIFACTS.replace(
        "- principle-prove-it-works: uv run pytest tests/test_skills_named.py\n  42 passed\n",
        HOLLOW[case],
    )
    (home.tasks / "alpha.md").write_text(reviewed(result))
    home.open_pull_request(merge.REVIEWED)
    reason = ready.SKILLS_UNRUN.format(names="prove-it-works")
    assert home.ready() == [f"wait 7 {merge.URL}: {reason}"]


@pytest.mark.parametrize(
    ("named", "ran"),
    [
        ("build-the-lever", "principle-build-the-lever"),
        ("principle-build-the-lever", "build-the-lever"),
    ],
)
def test_a_principle_s_bare_and_prefixed_names_are_one_name_at_the_merge(home, named, ran):
    """Winnifred's briefs write `build-the-lever`. The brief's spelling and the Result's need
    not agree, and the wait names the skill as the brief wrote it."""
    line = f"Skills: {named}\n"
    (home.tasks / "alpha.md").write_text(
        merge.brief(merge.review("clean"), f"Skills run:\n- {ran}: one script, run twice\n", line)
    )
    home.open_pull_request(merge.REVIEWED)
    assert home.ready() == [f"ready 7 {merge.REVIEWED} alpha alpha"]
    (home.tasks / "alpha.md").write_text(merge.brief(merge.review("clean"), "Skills run:\n", line))
    reason = ready.SKILLS_UNRUN.format(names=named)
    assert home.ready() == [f"wait 7 {merge.URL}: {reason}"]


def test_a_later_result_can_write_the_artifact_an_earlier_one_left_out(home):
    first = ARTIFACTS.replace("  42 passed\n", "").replace(
        "uv run pytest tests/test_skills_named.py", "<later>"
    )
    later = "\n## Result, follow-up (2026-10-16, the proof)\nSkills run:\n- prove-it-works: ok\n"
    (home.tasks / "alpha.md").write_text(reviewed(first) + later)
    home.open_pull_request(merge.REVIEWED)
    assert home.ready() == [f"ready 7 {merge.REVIEWED} alpha alpha"]


@pytest.mark.parametrize(
    "line", ["", "Skills: none\n", "Skills: none.\n", "Skills: None.\n", "Skills: none, docs\n"]
)
def test_a_brief_that_names_no_skill_owes_no_artifact_and_has_no_fault(line):
    assert skills.missing(merge.brief(merge.review("clean"), "", line)) == ()
    assert skills.unknown(line) == ""
    assert parse.faults(brief("alpha", line)) == []


def test_an_artifact_that_says_it_skipped_part_of_the_work_is_still_one():
    assert not skills.hollow("Skipped the arena; sketched A and B, picked A")
    for said in (
        "skip: no time",
        "Skipped",
        "Skipped.",
        "skip.",
        "skip - not needed",
        "Skipped, no UI change",
        "Skipped (no UI)",
    ):
        assert skills.hollow(said), said


UNKNOWN = "Skills: architect, poteto-mode, principle-made-up\n"


def test_an_unknown_skill_name_is_refused_at_queue_time_and_nothing_is_queued(kitchen):
    argv = ["--project", "demo", "queue", "add", "alpha", "--priority", "1"]
    code, said = kitchen.main(*argv, stdin=brief("alpha", UNKNOWN))
    assert code != 0
    assert "refused: alpha's brief has 1 fault, and nothing is queued" in said
    assert "Skills: line names poteto-mode, principle-made-up, which are no skill" in said
    assert not (kitchen.state / "briefs" / "alpha.md").exists()
    assert kitchen.main(*argv, stdin=brief("alpha", NAMED))[0] == 0


def test_a_row_queued_before_with_an_unknown_name_is_grandfathered_and_launches(kitchen):
    """A lint runs only when a row is first queued. So when a row already has a go and names a
    skill that a later check does not know, the launch does not gate that row."""
    kitchen.config(max_running=6)
    queued_before(kitchen, "alpha", brief("alpha", UNKNOWN))
    add(kitchen, "beta", priority=2)
    kitchen.poll()
    assert "poteto-mode, principle-made-up" in skills.unknown(UNKNOWN)
    assert gates(kitchen) == []
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha", "crew: beta"]


@pytest.mark.parametrize(
    ("line", "fault"),
    [
        ("Skills:\n", "is empty"),
        ("Skills: <names> | none\n", "is the template's own text"),
        ("Skills: /architect\n", "names /architect, which is no skill"),
        ("Skills: skills/architect\n", "names skills/architect, which is no skill"),
        ("Skills: Architect\n", "names Architect, which is no skill"),
    ],
)
def test_a_name_in_any_other_spelling_is_a_fault(line, fault):
    assert fault in skills.unknown(line)
    assert any(fault in each for each in parse.faults(brief("alpha", line)))


def test_the_crew_skill_block_prints_each_named_file_in_full_and_what_it_owes(tmp_path):
    """The block that the crew skill runs at its start, run as written over a brief."""
    task = tmp_path / "alpha.md"
    task.write_text(brief("alpha", NAMED))
    text = (REPO / "features" / "crew" / "SKILL.md").read_text()
    (code,) = [one for one in re.findall(r"```sh\n(.*?)```", text, re.S) if "--skills" in one]
    script = f"H={tmp_path}\nT={REPO / 'templates'}\n" + code.replace(
        '"$H/tasks/<slug>.md"', str(task)
    )
    said = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=True).stdout
    first, *rest = said.splitlines()
    assert first == (
        "loaded: in-your-own-words principle-model-the-domain principle-prove-it-works, "
        "the names on the Skills: line, each in full below"
    )
    model = REPO / "features" / "principles" / "skills" / "principle-model-the-domain" / "SKILL.md"
    shown = f"==> {model.relative_to(REPO)} <==\n" + model.read_text().rstrip()
    assert shown in said
    table = skills.artifacts()
    assert said.endswith(f"- principle-prove-it-works: {table['principle-prove-it-works']}\n")


def pinned():
    """The skill names of pstack at the pin, and the commit they come from."""
    lines = (
        (REPO / "features" / "jdrift" / "tests" / "fixtures" / "pstack-names.txt")
        .read_text()
        .splitlines()
    )
    (commit,) = re.findall(r"[0-9a-f]{40}", lines[0])
    return commit, [line for line in lines if line and not line.startswith("#")]


def not_taken():
    (line,) = re.findall(r"^Not taken: (.+)$", THIRD_PARTY.read_text(), re.M)
    return {
        path.removeprefix("pstack/skills/")
        for path in re.findall(r"`([^`]+)`", line)
        if path.count("/") == 2
    }


def test_the_names_are_of_the_pin_third_party_names():
    commit, names = pinned()
    assert f"- Commit: {commit}" in THIRD_PARTY.read_text()
    assert len(names) == 54


def test_every_pstack_name_at_the_pin_resolves_but_the_skills_jstack_did_not_take():
    """A name in a Grok Bot brief reads the same in T3. Each of pstack's names resolves to a
    file here, by its own name or an alias, unless jstack did not take that skill.
    `poteto-mode` is pstack's own way of running, which jstack's home and playbooks replace.
    The rest are on the `Not taken:` line, except one for which jstack wrote a skill of its
    own under the same name, `poteto-help`."""
    _, names = pinned()
    refused = {name for name in names if skills.resolve(name).path is None}
    own = {name for name in names if name in skill_folders()}
    assert "poteto-help" in own and "poteto-mode" not in own
    assert refused == ({"poteto-mode"} | not_taken()) - own
    for name in names:
        one = skills.resolve(name)
        if name.startswith("principle-"):
            assert (one.kind, one.name) == ("principle", name)
        elif one.path is not None:
            assert one.kind in ("skill", "playbook")


def test_every_principle_has_pstacks_name_and_its_old_name_still_resolves():
    files = sorted((REPO / "features" / "principles" / "skills").glob("*/SKILL.md"))
    assert len(files) == 25
    for path in files:
        name = path.parent.name
        assert name.startswith("principle-")
        old = name.removeprefix("principle-")
        assert skills.resolve(old).path == path
        assert skills.resolve(old).name == name == skills.resolve(name).name


def test_no_principle_lost_a_line_in_the_rename():
    """Each principle, reached by its old name through the resolver, is the file it was at
    c228ac6, with three exceptions. Its frontmatter differs, and its links to the others name
    their new files. A move also rewrote some paragraphs and list items to one sentence per
    line, and such a paragraph reads as the same text."""
    lines = (FIXTURES / "principles-before-rename.txt").read_text().splitlines()
    before = dict(line.split() for line in lines if not line.startswith("#"))
    assert len(before) == 25
    for old, digest in before.items():
        found = skills.resolve(old)
        assert found.relative == f"features/principles/skills/principle-{old}/SKILL.md"
        text = found.path.read_text().split("\n---\n\n", 1)[1]
        back = re.sub(r"\]\(\.\./principle-([a-z0-9-]+)/SKILL\.md", r"](\1.md", text)
        back = re.sub(r'(?<=\S)\n(?:  )?(?=[A-Z\["])', " ", back)
        assert hashlib.sha256(back.encode()).hexdigest() == digest, old


def test_every_name_the_map_gives_an_artifact_resolves_and_it_has_a_default():
    table = skills.artifacts()
    assert table[skills.DEFAULT]
    for name in set(table) - {skills.DEFAULT}:
        assert skills.resolve(name).name == name
    for name in ("in-your-own-words", "sharpen", "architect", "blast-radius"):
        assert name in table
    assert {"principle-model-the-domain", "principle-prove-it-works"} <= set(table)


def test_an_artifact_may_hold_a_line_that_looks_like_a_field_and_the_next_item_still_counts():
    result = (
        "Skills run:\n"
        "- architect: two shapes\n"
        "Candidate A: a check in jmerge\n"
        "Candidate B: the reviewer's verdict\n"
        "- in-your-own-words: the goal\n"
        "- prove-it-works: make check, exit 0\n"
        "Branch: alpha\n"
        "Noticed: - principle-model-the-domain: this is not an artifact\n"
    )
    text = merge.brief("", result, "Skills: architect, in-your-own-words, prove-it-works\n")
    have = skills.run(text)
    assert have["architect"] == (
        "two shapes\nCandidate A: a check in jmerge\nCandidate B: the reviewer's verdict"
    )
    assert skills.missing(text) == ()
    assert "principle-model-the-domain" not in have


def test_a_name_that_resolves_to_nothing_owes_no_artifact_at_the_merge():
    """The queue refuses such a name and the launch gates it, so `jmerge` does not report it
    again at the merge."""
    text = merge.brief("", "Skills run:\n- architect: A or B\n", "Skills: architect, then\n")
    assert skills.missing(text) == ()


def test_a_line_of_prose_is_gated_with_the_first_five_names_it_does_not_resolve():
    line = "Skills: in-your-own-words, then sharpen; before done, prove-it-works against the app\n"
    why = skills.unknown(line)
    assert "names then, before, done, against, the and 1 more, which are no skill" in why


def test_skills_json_is_what_the_generator_writes_and_lists_every_skill_and_principle():
    listed = json.loads((REPO / skills.CATALOG).read_text())["items"]
    on_disk = set(skill_folders())
    named = {item["name"] for item in listed if item["kind"] in ("skill", "principle")}
    assert named == on_disk
    assert {item["source"] for item in listed} <= {"pstack", "adapted", "jstack"}
    stale = subprocess.run(
        [sys.executable, "scripts/generate-jstack-trees.py", "--check"],
        cwd=REPO,
        capture_output=True,
    )
    assert stale.returncode == 0, stale.stderr


def test_a_skills_json_written_when_jstacks_own_items_were_josh_still_lists_them():
    """The generator once wrote `josh` for the source that is now `jstack`, and the fixture tree
    still holds the old value. Nothing reads `source`, so the old list gives its files the same."""
    tree = REPO / "testing" / "tests" / "fixtures" / "skills" / "named-tree"
    items = json.loads((tree / skills.CATALOG).read_text())["items"]
    assert {item["source"] for item in items} == {"josh"}
    assert skills.where("skill", "fake-skill", tree) == tree / "skills/fake-skill/SKILL.md"
    assert skills.listed("principle", tree) == {
        "principle-fake": tree / "principles/principle-fake.md"
    }


def test_a_name_skills_json_does_not_list_is_refused_and_an_alias_is_its_canonical_name(
    monkeypatch,
):
    """The list is skills.json, not the directories. The resolver refuses a skill whose file is
    there but which skills.json leaves out, and resolves pstack's name for an item to
    jstack's."""
    item = {"name": "sharpen", "kind": "skill", "path": "features/sharpen/SKILL.md"}
    alias = item | {"pstack_name": "deeper"}
    monkeypatch.setattr(skills, "_listed", lambda: ({"sharpen": alias}, {"deeper": alias}))
    assert skills.resolve("architect").path is None
    assert "names architect, which is no skill" in skills.unknown("Skills: architect\n")
    one = skills.resolve("deeper")
    assert (one.name, one.kind, one.relative) == ("sharpen", "skill", item["path"])
    assert [found.name for found in skills.named("Skills: deeper, sharpen\n")] == ["sharpen"]


def test_where_finds_each_kind_from_skills_json_and_refuses_what_it_does_not_list():
    assert skills.root() == REPO.resolve()
    gates = REPO.resolve() / "features" / "home" / "templates" / "gates.md"
    assert skills.where("template", "gates.md") == gates
    assert skills.where("skill", "crew") == REPO.resolve() / "features" / "crew" / "SKILL.md"
    assert skills.where("playbook", "feature").is_file()
    assert skills.where("principle", "principle-prove-it-works").is_file()
    with pytest.raises(LookupError, match="skills.json lists no playbook crew"):
        skills.where("playbook", "crew")


def source_modules():
    return {path for root in sources() for path in root.rglob("*.py")}


def test_the_source_modules_are_every_module_the_wheel_ships():
    wheel = tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["hatch"]["build"][
        "targets"
    ]["wheel"]
    shipped = {path for package in wheel["packages"] for path in (REPO / package).rglob("*.py")}
    assert shipped - source_modules() == set()


def test_no_module_reads_a_file_of_the_checkout_from_its_own_place_in_it():
    """The one `parents[2]` left is the view's own source root. It bounds the modules that the
    view watches for a newer copy, and the view reads no file through it."""
    found = {
        str(path.relative_to(REPO))
        for path in source_modules()
        if re.search(r"parents\[[24]\]", path.read_text())
    }
    assert found == {"features/jbus/src/jbus/view/__init__.py"}
