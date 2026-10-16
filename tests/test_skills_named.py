"""A brief's `Skills:` line: each name resolved by the one resolver, refused at the queue and
at the launch when it is no skill or principle, and held at the merge until the Result has
an artifact for it. The names are pstack's, and the old principle names still resolve."""

import hashlib
import re
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

import test_home_merge as merge
from jbriefs import parse, skills
from jmerge import ready
from test_jbus_kitchen import NOW
from test_jbus_queue import add, brief, gates, queued_before
from test_pr_review_skill import BRIEF, intent, reviewer  # noqa: F401

REPO = Path(__file__).parent.parent
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
    reason = ready.SKILLS_UNRUN.format(names="principle-prove-it-works")
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
    assert skills.hollow("skip: no time") and skills.hollow("Skipped")


UNKNOWN = "Skills: architect, poteto-mode, principle-made-up\n"


def test_an_unknown_skill_name_is_refused_at_queue_time_and_nothing_is_queued(kitchen):
    argv = ["--project", "demo", "queue", "add", "alpha", "--priority", "1"]
    code, said = kitchen.main(*argv, stdin=brief("alpha", UNKNOWN))
    assert code != 0
    assert "refused: alpha's brief has 1 fault, and nothing is queued" in said
    assert "Skills: line names poteto-mode, principle-made-up, which are no skill" in said
    assert not (kitchen.state / "briefs" / "alpha.md").exists()
    assert kitchen.main(*argv, stdin=brief("alpha", NAMED))[0] == 0


def test_a_row_queued_before_with_an_unknown_name_is_a_gate_that_names_it(kitchen):
    kitchen.config(max_running=6)
    queued_before(kitchen, "alpha", brief("alpha", UNKNOWN))
    add(kitchen, "beta", priority=2)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    why = skills.unknown(UNKNOWN)
    assert "poteto-mode, principle-made-up" in why
    assert gates(kitchen) == [f"condition alpha: {why}"]
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: beta"]


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
    """The block the crew skill runs at its start, run as written, over a brief."""
    task = tmp_path / "alpha.md"
    task.write_text(brief("alpha", NAMED))
    text = (REPO / "skills" / "crew" / "SKILL.md").read_text()
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
    model = (REPO / "principles" / "principle-model-the-domain.md").read_text()
    assert "==> principles/principle-model-the-domain.md <==\n" + model.rstrip() in said
    table = skills.artifacts()
    assert said.endswith(f"- principle-prove-it-works: {table['principle-prove-it-works']}\n")


def pinned():
    """The skill names of pstack at the pin, and the commit they are of."""
    lines = (FIXTURES / "pstack-names.txt").read_text().splitlines()
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
    """A name in a Grok Bot brief reads the same in T3: each of pstack's resolves to a file
    here, by its own name or an alias, unless jstack did not take that skill. `poteto-mode`
    and `figure-it-out` are pstack's own way of running, which jstack's home and playbooks
    stand in for, and the rest are on the `Not taken:` line."""
    _, names = pinned()
    refused = {name for name in names if skills.resolve(name).path is None}
    assert refused == {"poteto-mode", "figure-it-out"} | not_taken()
    for name in names:
        one = skills.resolve(name)
        if name.startswith("principle-"):
            assert (one.kind, one.name) == ("principle", name)
        elif one.path is not None:
            assert one.kind in ("skill", "playbook")


def test_every_principle_has_pstacks_name_and_its_old_name_still_resolves():
    files = sorted((REPO / "principles").glob("*.md"))
    assert len(files) == 25
    for path in files:
        assert path.stem.startswith("principle-")
        old = path.stem.removeprefix("principle-")
        assert skills.resolve(old).path == path
        assert skills.resolve(old).name == path.stem == skills.resolve(path.stem).name


def test_no_principle_lost_a_line_in_the_rename():
    """Each principle is the file it was at c228ac6, but for its links to the others, which
    name their new files."""
    lines = (FIXTURES / "principles-before-rename.txt").read_text().splitlines()
    before = dict(line.split() for line in lines if not line.startswith("#"))
    assert len(before) == 25
    for old, digest in before.items():
        text = (REPO / "principles" / f"principle-{old}.md").read_text()
        back = re.sub(r"\]\(principle-([a-z0-9-]+\.md)", r"](\1", text)
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
    """The queue refuses it and the launch gates it: the merge does not say it again."""
    text = merge.brief("", "Skills run:\n- architect: A or B\n", "Skills: architect, then\n")
    assert skills.missing(text) == ()


def test_a_line_of_prose_is_gated_with_the_first_five_names_it_does_not_resolve():
    line = "Skills: in-your-own-words, then sharpen; before done, prove-it-works against the app\n"
    why = skills.unknown(line)
    assert "names then, before, done, against, the and 1 more, which are no skill" in why


def test_the_reviewer_reads_the_skills_line_and_each_artifact_as_jmerge_reads_it(reviewer):  # noqa: F811
    text = BRIEF.replace("Pull request:", f"Design: none, small\n{NAMED}Pull request:")
    result = ARTIFACTS.replace("  42 passed\n", "").replace(
        "uv run pytest tests/test_skills_named.py", "<the command>"
    )
    reviewer.brief.write_text(f"{text}\n## Result\nStatus: done\n{result}")
    told = intent(reviewer)
    skills_line = NAMED.removeprefix("Skills: ").strip()
    assert f"\nSkills: {skills_line}. The crewmate loaded each in full" in told
    assert told.count("Skills: in-your-own-words") == 1
    assert (
        "What the Results hold under Skills run:, as jmerge reads it:\n"
        "- in-your-own-words: the user wants each skill a brief names to reach the crewmate\n"
        "- principle-model-the-domain: Named(said, path), resolved once; missing() is the gap\n"
        "- principle-prove-it-works: no artifact\n"
    ) in told
