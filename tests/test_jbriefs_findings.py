"""`jbriefs --findings <brief>`: every `## Review` section's findings as one triaged list,
each with its id, the reviewers that raised it, its bucket, and the answer the crew gave it
by id. Run through the command, over briefs as the skills write them."""

import subprocess
import sys
from pathlib import Path

from jbriefs import findings

SAW, LATER = "a" * 40, "c" * 40
RESULT = "# alpha: a task\n\n## Result\nStatus: done\n"
CODEX = "codex gpt-6-sol xhigh"
CURSOR = "cursor grok-4.7 xhigh"


def section(listed, by="", head=SAW, dismissed=()):
    lines = "".join(f"- {one}\n" for one in listed) or "- none\n"
    who = f"By: {by}\n" if by else ""
    verdict = "findings" if listed else "clean"
    gone = "".join(f"- {one}\n" for one in dismissed)
    return (
        f"\n## Review\n{who}Verdict: {verdict}\nHead: {head}\nFindings:\n{lines}Dropped: 0\n"
        f"Noted: 0\nDismissed: {len(dismissed) or 'none'}\n{gone}Sent to: mcp:1\n"
    )


def tagged(text, bucket="Act on", principle="none", risk=""):
    return f"{text} (principle: {principle}) (bucket: {bucket})" + (
        f" (risk: {risk})" if risk else ""
    )


def run(tmp_path, brief, *flags):
    path = tmp_path / "alpha.md"
    path.write_text(brief)
    ran = subprocess.run(
        [sys.executable, "-m", "jbriefs", *flags, "--findings", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return ran.stdout


def test_each_finding_has_an_id_its_reviewer_severity_place_and_bucket(tmp_path):
    brief = RESULT + section(
        [tagged("error src/a.py:10 it runs twice"), tagged("info src/b.py a name", "Consider")],
        CODEX,
    )
    triage = findings.triage(brief)
    first, second = triage.findings
    assert (first.id, first.bucket, first.severity, first.path, first.line) == (
        "F1",
        "Act on",
        "error",
        "src/a.py",
        10,
    )
    assert first.reviewers == (CODEX,)
    assert (second.id, second.bucket, second.path, second.line) == (
        "F2",
        "Consider",
        "src/b.py",
        None,
    )
    out = run(tmp_path, brief)
    assert out.startswith("F1 [Act on] error src/a.py:10 it runs twice")
    assert "F2 [Consider] info src/b.py a name" in out


def test_two_reviewers_on_one_file_within_five_lines_and_one_category_are_one_id(tmp_path):
    one = tagged("error src/a.py:10 it runs twice", principle="model-the-domain")
    near = tagged("warning src/a.py:15 the loop repeats", "Consider", principle="model-the-domain")
    far = tagged("warning src/a.py:16 another thing", principle="model-the-domain")
    other = tagged("warning src/a.py:11 a different kind", principle="prove-it-works")
    brief = RESULT + section([one], CODEX) + section([near, far, other], CURSOR)
    listed = findings.triage(brief).findings
    assert [found.id for found in listed] == ["F1", "F2", "F3"]
    assert listed[0].reviewers == (CODEX, CURSOR)
    assert listed[0].bucket == "Act on"
    assert listed[0].severity == "error"
    assert findings.NEAR == 5


def test_one_reviewer_never_merges_with_itself_nor_across_heads():
    one = tagged("error src/a.py:10 it runs twice")
    same = tagged("error src/a.py:11 it runs twice again")
    brief = RESULT + section([one, same], CODEX) + section([one], CURSOR, head=LATER)
    assert [found.id for found in findings.triage(brief).findings] == ["F1", "F2", "F3"]


def test_a_finding_the_other_reviewer_dismisses_in_so_many_words_is_kept_as_two_side_by_side(
    tmp_path,
):
    raised = tagged("error src/a.py:10 it runs twice", principle="model-the-domain")
    other = tagged("warning src/z.py:1 unrelated")
    gone = "error src/a.py:12 it runs twice (principle: model-the-domain)"
    gone += " (dismissed: the guard stops it)"
    brief = RESULT + section([raised, other], CODEX) + section([], CURSOR, dismissed=[gone])
    listed = findings.triage(brief).findings
    assert [(found.id, found.bucket, found.contradicts) for found in listed] == [
        ("F1", "Act on", ""),
        ("F2", "Act on", ""),
        ("F3", "Dismissed", "F1"),
    ]
    ids = [line.split()[0] for line in run(tmp_path, brief).splitlines() if line[:1] == "F"]
    assert ids == ["F1", "F3", "F2"]


def test_answers_are_keyed_by_id_and_only_act_on_blocks(tmp_path):
    brief = RESULT + section(
        [tagged("error src/a.py:10 x"), tagged("error src/b.py:1 y", "Consider")], CODEX
    )
    brief += "Finding F1: not fixed, x, because src/a.py:4 guards it\n"
    triage = findings.triage(brief)
    assert triage.answers["F1"].fixed is False
    assert triage.blocking() == ()
    assert "answer: not fixed, x, because src/a.py:4 guards it" in run(tmp_path, brief)


def test_a_brief_from_before_ids_has_ids_and_its_answers_matched_by_count(tmp_path):
    brief = RESULT + section(["error a.py:3 it runs twice", "warning b.py the name lies"])
    brief += "Finding: fixed, it runs twice\n"
    triage = findings.triage(brief)
    assert [(found.id, found.bucket, found.legacy) for found in triage.findings] == [
        ("F1", "Act on", True),
        ("F2", "Act on", True),
    ]
    assert [found.id for found in triage.blocking()] == ["F2"]
    assert run(tmp_path, brief, "--left") == "not yet: 1 of 2 findings have no Finding: line\n"


def test_the_list_is_the_same_on_every_run(tmp_path):
    brief = RESULT + section([tagged("error src/a.py:10 x")], CODEX)
    brief += section([tagged("warning src/a.py:12 y")], CURSOR)
    assert run(tmp_path, brief) == run(tmp_path, brief)


def test_the_rounds_the_second_pass_reads_come_from_the_same_parser(tmp_path):
    brief = RESULT + section([tagged("error src/a.py:10 x")], CODEX) + section([], CURSOR, LATER)
    assert run(tmp_path, brief, "--rounds") == f"2 {LATER} {SAW},{LATER} -\n"
    assert run(tmp_path, RESULT, "--rounds") == "0 - - -\n"


def test_a_brief_that_cannot_be_read_is_said(tmp_path):
    ran = subprocess.run(
        [sys.executable, "-m", "jbriefs", "--findings", str(Path(tmp_path) / "none.md")],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 1
    assert "cannot be read" in ran.stderr


def test_one_finding_takes_at_most_one_line_from_each_reviewer_the_nearest():
    one = tagged("error src/a.py:10 x", principle="model-the-domain")
    far = tagged("error src/a.py:14 far", principle="model-the-domain")
    near = tagged("error src/a.py:11 near", principle="model-the-domain")
    brief = RESULT + section([one], CODEX) + section([far, near], CURSOR)
    listed = findings.triage(brief).findings
    assert [(found.id, [r.what for r in found.raised]) for found in listed] == [
        ("F1", ["x", "far"]),
        ("F2", ["near"]),
    ]


def test_two_findings_tagged_with_no_principle_are_never_one():
    one, other = tagged("error src/a.py:10 x"), tagged("error src/a.py:11 y")
    brief = RESULT + section([one], CODEX) + section([other], CURSOR)
    assert [found.id for found in findings.triage(brief).findings] == ["F1", "F2"]


def test_a_section_its_reviewer_wrote_again_at_one_head_keeps_its_ids_and_blocks_nothing(
    tmp_path,
):
    first = section([tagged("error src/a.py:10 x")], CODEX).replace("findings", "not run", 1)
    again = section([tagged("warning src/b.py:2 y")], CODEX)
    triage = findings.triage(RESULT + first + again)
    assert [(one.id, one.superseded) for one in triage.findings] == [("F1", True), ("F2", False)]
    assert [one.id for one in triage.blocking()] == ["F2"]
    assert "superseded" in run(tmp_path, RESULT + first + again)


def test_a_decline_by_id_of_a_finding_from_before_the_ids_answers_it():
    brief = RESULT + section(["error a.py:3 x", "warning b.py:1 y"])
    brief += "Finding F2: fixed, y\nFinding: fixed, x\n"
    assert findings.triage(brief).blocking() == ()


TWO = Path(__file__).parent / "fixtures" / "findings" / "two-reviewers.md"


def test_a_brief_two_reviewers_wrote_is_one_list_with_both_named_and_a_dismissal_beside(tmp_path):
    from jmerge import ready

    out = run(tmp_path, TWO.read_text())
    heads = [line.split()[:2] for line in out.splitlines() if line[:1] == "F"]
    assert heads == [
        ["F1", "[Act"],
        ["F2", "[Act"],
        ["F3", "[Consider]"],
        ["F4", "[Act"],
        ["F5", "[Dismissed]"],
    ]
    assert f"  by: {CODEX}; {CURSOR}" in out.split("F2 ")[0]
    assert "  contradicts: F4" in out.split("F5 ")[1]
    assert (
        out.splitlines()[-1]
        == "next: write Fixed: <the head you pushed>, 4 findings each have their ending"
    )
    head = "1e16fb7dd82ea2dae3209f561f5273e559b46b4a"
    assert ready.short_of(TWO.read_text(), head) == ready.DECLINES_UNRULED.format(ids="F2")
    assert "  ruling: none, a scoped pass rules on it before the merge" in out.split("F3 ")[0]


def test_a_re_run_at_one_head_moves_no_id_and_no_answer():
    a = tagged("error src/a.py:10 x", principle="model-the-domain")
    b = tagged("warning src/a.py:12 y", principle="model-the-domain")
    d = tagged("error src/d.py:1 z")
    before = RESULT + section([a], CODEX) + section([b, d], CURSOR)
    before += "Finding F1: fixed, x\nFinding F2: fixed, z\n"
    after = before + section([a], CODEX)
    triage = findings.triage(after)
    ids = [(one.id, one.path, one.superseded) for one in triage.findings]
    assert ids == [("F1", "src/a.py", False), ("F2", "src/d.py", False)]
    assert triage.findings[0].reviewers == (CODEX, CURSOR, CODEX)
    assert triage.answers["F2"].what == "z"
    assert triage.blocking() == ()


def test_a_risky_consider_finding_blocks_and_its_decline_needs_a_gate():
    risky = tagged("warning src/auth.py:5 the token is logged", "Consider", risk="auth")
    declined = "Finding F1: not fixed, the token, because consider: left for a follow-up\n"
    triage = findings.triage(RESULT + section([risky], CODEX) + declined)
    (one,) = triage.blocking()
    assert one.refused == findings.UNASKED


def test_a_risk_tag_on_a_line_its_reviewer_wrote_again_holds_nothing():
    risky = tagged("error src/a.py:10 x", "Consider", principle="model-the-domain", risk="auth")
    near = tagged("warning src/a.py:12 y", "Consider", principle="model-the-domain")
    brief = RESULT + section([risky], CODEX) + section([near], CURSOR) + section([], CODEX)
    brief += "Finding F1: not fixed, y, because consider: left for a follow-up\n"
    (one,) = findings.triage(brief).findings
    assert (one.risk, one.severity, one.blocks, one.refused) == ("", "warning", False, "")
