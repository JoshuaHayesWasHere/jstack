from pathlib import Path

import pytest

from jbriefs import asks, below, cli, findings, home, page, parse, paths, proof, runnable, skills
from testing.paths import REPO

TEMPLATE = REPO / "features" / "jbriefs" / "templates" / "brief.md"
FINDINGS = ("Read:", "Instruments:", "Change:", "Rests on:", "Sources:", "Ruled out:")

PLAN = """\
# demo: plan

Order: alpha, then beta.

## alpha: the first task
Status: with crewmate
Done when:
- `make check` passes.
- The page shows it,
  on two lines.
Decisions:
- 2026-10-10: "do it"

## beta: a task nobody has a brief for
Stage: planned (after alpha)
Done when:
- It is planned.

## gamma: finished but not cleared yet
Status: done 2026-10-10. Merged.

## Waiting on the user, nothing to build
- A card in billing.
"""

BRIEF = """\
# alpha: the first task
Task: "do the first task"
Done when:
- `make check` passes.
Where: `src/`
Do not touch: `docs/`
Decisions: none
Pull request: open one when done
Thread: mcp:1111-aaaa
"""

RESULT = """
## Result
Status: done
Done when: `make check` passes (holds)
Branch: alpha   Pull request: https://github.com/someone/demo/pull/7
Changed: one file.
Steers: none
Noticed: none
Left: none
"""

FOLLOW_UP = """
## Result, follow-up (2026-10-10)
Status: not done (waiting on a change set)
Left: the user runs the change set.
"""

HANDOFF = """\
# demo: handoff, 2026-10-10 16:50

## Where things stand
Built, not pushed.

## Next
Take `beta` from plan.md.

## Open decisions
- Push now, or later?
- Rename the repo?

## Do not redo
None
"""


def make_repo(state: Path, name: str, *, plan=None, handoff=None, briefs=None) -> Path:
    path = state / name
    (path / "tasks").mkdir(parents=True)
    if plan is not None:
        (path / "plan.md").write_text(plan)
    if handoff is not None:
        (path / "handoff.md").write_text(handoff)
    for slug, text in (briefs or {}).items():
        (path / "tasks" / f"{slug}.md").write_text(text)
    return path


def test_plan_entries_carry_slug_title_status_and_done_when():
    alpha, beta, gamma = parse.plan_entries(PLAN)
    assert (alpha.slug, alpha.title, alpha.status) == ("alpha", "the first task", "with crewmate")
    assert alpha.done_when == ("`make check` passes.", "The page shows it, on two lines.")
    assert (beta.slug, beta.status) == ("beta", "planned (after alpha)")
    assert beta.done_when == ("It is planned.",)
    assert gamma.done_when == ()


def test_a_section_that_is_not_an_entry_is_left_out():
    assert [entry.slug for entry in parse.plan_entries(PLAN)] == ["alpha", "beta", "gamma"]


def test_an_entry_is_open_until_its_status_says_done():
    assert [entry.open for entry in parse.plan_entries(PLAN)] == [True, True, False]


def test_a_loose_done_when_list_is_read_whole():
    text = "## delta: loose\nDone when:\n\n- one\n\n* two\n\nDecisions:\n- not a check\n"
    (entry,) = parse.plan_entries(text)
    assert entry.done_when == ("one", "two")


def test_an_entry_with_no_status_line_is_open():
    (entry,) = parse.plan_entries("## delta: no status yet\nDone when:\n- Something.\n")
    assert entry.status == ""
    assert entry.open


def test_a_brief_with_no_result():
    brief = parse.brief("alpha", BRIEF)
    assert brief.title == "the first task"
    assert brief.state == parse.NO_RESULT
    assert brief.results == ()
    assert brief.pull_request is None
    assert brief.thread == "mcp:1111-aaaa"
    assert brief.thread_title == "crew: alpha"
    assert brief.body == BRIEF.strip()


def test_a_brief_with_no_thread_has_no_thread_title():
    brief = parse.brief("alpha", BRIEF.replace("Thread: mcp:1111-aaaa\n", ""))
    assert brief.thread is None
    assert brief.thread_title is None


def test_a_done_result_names_its_pull_request():
    brief = parse.brief("alpha", BRIEF + RESULT)
    assert brief.state == parse.DONE
    assert brief.pull_request == parse.PullRequest(
        "https://github.com/someone/demo/pull/7", "https://github.com/someone/demo/pull/7"
    )
    assert brief.body == BRIEF.strip()
    (result,) = brief.results
    assert result.heading == "Result"
    assert "Changed: one file." in result.text


def test_the_pull_request_line_of_the_brief_itself_is_not_a_result():
    assert parse.brief("alpha", BRIEF).pull_request is None


def test_a_result_with_no_pull_request():
    result = RESULT.replace("https://github.com/someone/demo/pull/7", "none")
    assert parse.brief("alpha", BRIEF + result).pull_request is None


def test_a_pull_request_named_without_a_url_has_no_link():
    result = RESULT.replace("https://github.com/someone/demo/pull/7", "#200 (not merged)")
    assert parse.brief("alpha", BRIEF + result).pull_request == parse.PullRequest(
        "#200 (not merged)", None
    )


def test_markdown_around_a_pull_request_url_is_not_part_of_the_link():
    url = "https://github.com/someone/demo/pull/7"
    for named in (f"`{url}`", f"**{url}**", f"{url}."):
        assert parse.brief("alpha", BRIEF + RESULT.replace(url, named)).pull_request.url == url


def test_each_state_is_read_from_the_status_line():
    def state(status):
        return parse.brief("alpha", BRIEF + RESULT.replace("Status: done", status)).state

    assert state("Status: done, with one line to read closely") == parse.DONE
    assert state("Status: not done") == parse.NOT_DONE
    assert state("Status: blocked (needs a token)") == parse.BLOCKED
    assert state("Status: paused") == parse.PAUSED
    assert state("Status: who knows") == parse.UNCLEAR


def test_the_last_result_decides_the_state_and_an_earlier_one_keeps_the_pull_request():
    brief = parse.brief("alpha", BRIEF + RESULT + FOLLOW_UP)
    assert [result.heading for result in brief.results] == [
        "Result",
        "Result, follow-up (2026-10-10)",
    ]
    assert brief.state == parse.NOT_DONE
    assert brief.pull_request.url == "https://github.com/someone/demo/pull/7"


RESULT_TEMPLATE = REPO / "features" / "crew" / "templates" / "result.md"


def reported(line):
    """The steps that jbriefs reads from a Result that has `line` under its `Changed:` line."""
    text = BRIEF + RESULT.replace("Changed: one file.\n", f"Changed: one file.\n{line}\n")
    (result,) = parse.brief("alpha", text).results
    return result.playbook


def test_each_step_a_result_reports_is_read_as_done_or_skipped_with_its_reason():
    said = reported("Playbook: bug-fix; 1 done; 2 skip: the brief gives the repro, as is; 3 done")
    assert said == parse.Steps(
        "bug-fix",
        (
            parse.Step(1),
            parse.Step(2, "the brief gives the repro, as is"),
            parse.Step(3),
        ),
    )


def test_a_result_with_no_playbook_line_reports_none_and_one_that_says_none_reports_no_step():
    assert reported("") is None
    assert reported("Playbook: none") == parse.Steps("none")


@pytest.mark.parametrize(
    ("line", "fault"),
    [
        ("Playbook: bug-fix", "reports no step"),
        ("Playbook: none; 1 done", "reports steps of no playbook"),
        (
            "Playbook: bug-fix; 1 done; 2 skipped",
            "has `2 skipped`, not `<n> done` or `<n> skip: <reason>`",
        ),
        (
            "Playbook: bug-fix; 1 done; 2 skip:",
            "has `2 skip:`, not `<n> done` or `<n> skip: <reason>`",
        ),
        ("Playbook: bug-fix; 1 done; 3 done", "does not number its steps 1 to the last in order"),
        ("Playbook: bug-fix; 2 done; 1 done", "does not number its steps 1 to the last in order"),
        ("Playbook: ; 1 done", "names no playbook"),
    ],
)
def test_a_playbook_line_out_of_the_templates_shape_is_read_with_one_line_saying_why(line, fault):
    assert reported(line).fault == fault


def test_the_templates_own_playbook_line_is_refused_until_it_is_filled_in():
    (line,) = [
        line for line in RESULT_TEMPLATE.read_text().splitlines() if line.startswith("Playbook:")
    ]
    assert reported(line).fault == "names no playbook"
    filled = "Playbook: bug-fix; 1 done; 2 skip: no reason to"
    assert reported(filled) == parse.Steps(
        "bug-fix", (parse.Step(1), parse.Step(2, "no reason to"))
    )


def test_the_playbook_line_of_the_brief_itself_is_not_a_report():
    (result,) = parse.brief("alpha", BRIEF + "Playbook: bug-fix\n" + RESULT).results
    assert result.playbook is None


def test_the_last_results_playbook_line_is_its_own():
    follow = FOLLOW_UP.rstrip("\n") + "\nPlaybook: feature; 1 done\n"
    first, last = parse.brief("alpha", BRIEF + RESULT + follow).results
    assert first.playbook is None
    assert last.playbook == parse.Steps("feature", (parse.Step(1),))


def written(*, by_a_scout):
    """A brief in the template's shape with every field filled in, as a scout or a home writes it.

    The scout's findings contain what a result contains, to show that jbriefs does not read them
    as a result.
    """
    filled = {
        "Sources:": "Sources: https://github.com/someone/demo/pull/3, the part on retries",
        "Rests on:": "Rests on: Status: done in `tasks/beta.md`, and its Pull request: line",
    }
    lines = []
    for line in TEMPLATE.read_text().splitlines():
        label = next((label for label in FINDINGS if line.startswith(label)), None)
        if label and not by_a_scout:
            continue
        if line.startswith("<"):
            continue
        lines.append(filled.get(label, line.replace("<slug>: <one line>", "alpha: the first task")))
    return "\n".join([*lines, "Thread: mcp:1111-aaaa", ""])


@pytest.mark.parametrize("by_a_scout", [True, False])
def test_a_brief_is_read_the_same_with_and_without_a_scouts_findings(by_a_scout):
    text = written(by_a_scout=by_a_scout)
    found = [label for line in text.splitlines() for label in FINDINGS if line.startswith(label)]
    assert found == (list(FINDINGS) if by_a_scout else [])

    brief = parse.brief("alpha", text)
    assert (brief.title, brief.thread) == ("the first task", "mcp:1111-aaaa")
    assert (brief.state, brief.results, brief.pull_request) == (parse.NO_RESULT, (), None)
    assert brief.body == text.strip()

    done = parse.brief("alpha", text + RESULT)
    assert done.state == parse.DONE
    assert done.pull_request.url == "https://github.com/someone/demo/pull/7"
    assert done.body == text.strip()


def test_the_template_has_a_design_line_that_jbus_launches_only_once_it_is_filled_in():
    """`jbus` reads the line where the template puts it: in the head, above any result."""
    (line,) = [line for line in TEMPLATE.read_text().splitlines() if line.startswith("Design:")]
    text = written(by_a_scout=False)
    assert line in text and parse.designed(text) == parse.NO_DESIGN
    for said in ("Design: scouts/alpha-design.md", "Design: none, a one-line fix"):
        assert parse.designed(text.replace(line, said)) == ""
        assert parse.designed(text.replace(line, "Design: TBD") + RESULT + said) != ""
    assert parse.designed(text.replace(line + "\n", "") + RESULT + "Design: TBD") == ""


CLEAN = (
    '# alpha: a task\nTask: "do alpha"\nDone when:\n- it is done\nProves it: `make check`\n'
    "Size: S\nWhere: `src/alpha/`\nPull request: open one when done\nReview: twice\n"
    "Playbook: none\n"
)


@pytest.mark.parametrize(
    "lines",
    ["", "Design: none, a removal\n", "Skills: none\n", "Design: none, a fix\nSkills: none\n"],
    ids=["both left out", "design written", "skills written", "both written"],
)
def test_a_brief_may_leave_out_design_and_skills_where_they_would_say_none(lines):
    """A brief with no `Design:` or `Skills:` line needs no design and names no skill, as `none`
    would say, and one that writes them still lints."""
    assert parse.faults(CLEAN + lines) == []


PROOFS = {
    "a test path": ("tests/test_briefs.py passes", "a test"),
    "a test's name": ("test_a_brief_is_proven_by_what_is_outside_the_agent", "a test"),
    "a command": ("`jbus --project jstack queue show` prints the row", "a test"),
    "make": ("make check exits 0", "a test"),
    "a metric": ("the p95 latency of a pass, from jgauge", "a metric"),
    "a percentage": ("under 2% of passes gated", "a metric"),
    "a dataset": ("the ten past briefs of the eval dataset", "a dataset"),
    "a judge by name": ("an external judge, blind to which brief is which", "an external judge"),
    "a test the crewmate runs": ("the crewmate runs tests/test_briefs.py", "a test"),
    "a command with no path": ("`jbus queue show` prints the row", "a test"),
    "a linter": ("`ruff check src` is clean", "a test"),
    "a make target": ("make build exits 0", "a test"),
    "another make target": ("make e2e passes", "a test"),
    "a bare percentage": ("coverage stays above 90%", "a metric"),
    "a rate": ("error rate under 2%", "a metric"),
    "a judge": ("a human judge scores it", "an external judge"),
    "a test path with its test": ("tests/test_briefs.py::test_x passes", "a test"),
    "a judged line": ("judged: only the user can say the page reads well", "judged"),
    "the user, judged": ("judged: the user's eye on the screenshot", "judged"),
    "CI by its command": ("`gh pr checks` passes on the pull request", "a test"),
}

LOOSE = {
    "CI": ("CI on the pull request", "an external judge", "names CI, which runs nothing by itself"),
    "github": ("github says green", "an external judge", "names CI, which runs nothing by itself"),
    "the user": ("the user, on the page", "the user", "names the user with no judged: <why>"),
    "the operator": (
        "the operator's word on the screenshot",
        "the user",
        "names the user with no judged: <why>",
    ),
    "the owner": (
        "the owner of the repo signs it off",
        "the user",
        "names the user with no judged: <why>",
    ),
    "a review by the user": (
        "reviewed by the user",
        "the user",
        "names the user with no judged: <why>",
    ),
    "the tests": ("the parser tests above", "a test", "names a test by the word alone"),
    "a hyphenated test": ("the unit-tests pass", "a test", "names a test by the word alone"),
    "a smoke test": ("the smoke-test passes", "a test", "names a test by the word alone"),
    "tests beside the crew": (
        "the skill text tests, and the crew's lines",
        "a test",
        "names a test by the word alone",
    ),
    "the crewmate's tests": ("the crewmate's tests", "a test", "names a test by the word alone"),
    "an empty judged": ("judged:", "", "is empty"),
}

REFUSED = {
    "an empty line": ("", "is empty"),
    "white space": ("   ", "is empty"),
    "the crewmate": ("reviewed by crewmate", "names the crewmate, the agent's own word"),
    "the reviewer": ("reviewed by reviewer", "names the reviewer, the agent's own word"),
    "the crew": ("the crew says so", "names the crew, the agent's own word"),
    "the agent": ("the agent checks it", "names the agent, the agent's own word"),
    "self": ("self-review", "names the agent itself, the agent's own word"),
    "itself": ("it checks itself", "names the agent itself, the agent's own word"),
    "the model": ("the model judges it", "names the model, the agent's own word"),
    "a review alone": ("a careful review", "names a review alone, the agent's own word"),
    "nothing": ("it works", "names nothing outside the agent"),
    "make sure": (
        "the crewmate will make sure it works",
        "names the crewmate, the agent's own word",
    ),
    "a self-test by the agent": (
        "a self-test by the agent",
        "names the agent, the agent's own word",
    ),
    "a self-test": ("a self-test", "names the agent itself, the agent's own word"),
    "a self test by the agent": (
        "a self test by the agent",
        "names the agent, the agent's own word",
    ),
    "the crewmate will test it": (
        "the crewmate will test it",
        "names the crewmate, the agent's own word",
    ),
    "the agent tests it": ("the agent tests it", "names the agent, the agent's own word"),
    "it tests": ("the crewmate says it tests well", "names the crewmate, the agent's own word"),
    "two spans in backticks": (
        "the `crewmate` says so. The `reviewer` agrees",
        "names the crewmate, the agent's own word",
    ),
    "a sentence in backticks": (
        "`the crewmate said so.`",
        "names the crewmate, the agent's own word",
    ),
    "a percentage of sure": (
        "the reviewer is 100% sure",
        "names the reviewer, the agent's own word",
    ),
    "the model as judge": ("the model is the judge", "names the model, the agent's own word"),
    "a word in backticks": ("`the crewmate` says so", "names the crewmate, the agent's own word"),
}

ASKED = "(name a test, a command, a metric, a dataset, an external judge or the user)"
RUNS = (
    "(name a command in backticks, a `tests/...py[::name]` path, or `judged: <why>` for what "
    "only a person can judge)"
)


@pytest.mark.parametrize("case", PROOFS)
def test_a_proof_that_names_something_outside_the_agent_holds(case):
    said, kind = PROOFS[case]
    judged = proof.proof(said)
    assert (judged.said, judged.kind, judged.why) == (said, kind, "")


@pytest.mark.parametrize("case", REFUSED)
def test_a_proof_by_the_agents_own_word_is_refused_with_one_line_saying_why(case):
    said, fault = REFUSED[case]
    judged = proof.proof(said)
    assert judged.kind == ""
    assert judged.why == f"brief's Proves it: line {fault} {ASKED}"


@pytest.mark.parametrize("case", LOOSE)
def test_a_proof_by_ci_the_user_or_the_word_test_alone_is_not_taken(case):
    """proof.py once took these as a proof. It no longer does: each names nothing anyone can run,
    so the line says the command, the test's path, or `judged: <why>`. `was` keeps the kind the
    older rule took, so jbus warns of the line before it refuses it (`parse.WARNED`)."""
    said, was, fault = LOOSE[case]
    judged = proof.proof(said)
    assert (judged.kind, judged.was) == ("", was)
    if was:
        assert judged.why == f"brief's Proves it: line {fault} {RUNS}"


def test_a_loose_proof_warns_and_an_agents_own_word_still_refuses():
    text = CLEAN.replace("Proves it: `make check`", "Proves it: CI on the pull request")
    warned = f"brief's Proves it: line names CI, which runs nothing by itself {RUNS}"
    assert parse.faults(text) == []
    assert warned in parse.warnings(text, "")
    own = CLEAN.replace("Proves it: `make check`", "Proves it: the crewmate says so")
    assert parse.faults(own) == [
        f"brief's Proves it: line names the crewmate, the agent's own word {ASKED}"
    ]


DONE_WHEN_FAULT = (
    "brief's Done when: has {n} of {of} items that run nothing, the first: {first} (in each, a "
    "command in backticks that starts with a runner, a `tests/...py[::name]` path, or "
    "`judged: <why>`)"
)

RUNNABLE = {
    "a uv run command": "`uv run pytest -q features/x` passes",
    "jbus": "`jbus --project jstack queue check` prints nothing",
    "rg": "`rg -n TODO src` finds none",
    "a test path": "features/jbriefs/tests/test_briefs.py passes",
    "a test path and name": "tests/test_x.py::test_y fails at the base and passes at the head",
    "a test path in backticks": "`features/jbus/tests/test_q.py::test_z` passes",
    "test": "`test -f out.json` holds",
    "judged": "judged: the page reads well, which only the user can say",
}
PROSE = {
    "bare prose": "it is done",
    "a backticked path that runs nothing": "`features/jbriefs/src/jbriefs/proof.py` is tighter",
    "a backticked word that is no runner": "`CHECKS` has a new entry",
    "a runner word with no backticks": "uv run pytest passes",
    "a test path that is no python": "tests/fixtures/a.md is updated",
    "an empty judged": "judged:",
}


@pytest.mark.parametrize("case", RUNNABLE)
def test_a_done_when_item_that_runs_something_is_no_fault(case):
    text = CLEAN.replace("- it is done", f"- {RUNNABLE[case]} (in none)")
    assert runnable.runnable(text) == ""
    assert parse.warnings(text, "") == []


@pytest.mark.parametrize("case", PROSE)
def test_a_done_when_item_in_prose_alone_is_warned_of_and_still_queued(case):
    text = CLEAN.replace("- it is done", f"- {PROSE[case]}")
    fault = DONE_WHEN_FAULT.format(n=1, of=1, first=PROSE[case])
    assert runnable.runnable(text) == fault
    assert fault in parse.warnings(text, "")
    assert parse.faults(text) == []


def test_the_done_when_fault_counts_the_items_and_names_the_first_that_runs_nothing():
    text = CLEAN.replace(
        "- it is done", "- `make check` passes\n- the page loads\n- it is done\n- judged: it reads"
    )
    assert runnable.runnable(text) == DONE_WHEN_FAULT.format(n=2, of=4, first="the page loads")


def test_the_template_has_a_proves_it_line_after_done_when_that_is_refused_until_filled_in():
    lines = TEMPLATE.read_text().splitlines()
    (line,) = [line for line in lines if line.startswith("Proves it:")]
    after = lines.index("Done when:") + 1
    while lines[after].startswith("- "):
        after += 1
    assert lines[after] == line
    text = written(by_a_scout=False)
    assert parse.brief("alpha", text).proof.why == (
        f"brief's Proves it: line is the template's own text {ASKED}"
    )
    assert parse.proven(text) == parse.brief("alpha", text).proof.why
    filled = text.replace(line, "Proves it: tests/test_alpha.py passes")
    assert parse.brief("alpha", filled).proof.kind == "a test"
    assert parse.proven(filled) == ""


def test_a_brief_with_no_proves_it_line_is_launched_as_before_and_one_under_its_head_is_not_read():
    """Briefs queued before the template asked for the line have no such line, and jbus
    launches them anyway."""
    assert parse.brief("alpha", BRIEF).proof is None
    assert parse.proven(BRIEF) == ""
    under = BRIEF + RESULT + "Proves it: reviewed by crewmate\n"
    assert parse.brief("alpha", under).proof is None
    assert parse.proven(under) == ""
    first = BRIEF + "Proves it: the crewmate\nProves it: tests/test_alpha.py\n"
    assert (
        parse.proven(first)
        == f"brief's Proves it: line names the crewmate, the agent's own word {ASKED}"
    )


def test_handoff_sections_are_read_by_heading():
    handoff = parse.handoff(HANDOFF)
    assert handoff.title == "demo: handoff, 2026-10-10 16:50"
    assert handoff.section("Next") == "Take `beta` from plan.md."
    assert handoff.section("Open decisions") == "- Push now, or later?\n- Rename the repo?"
    assert handoff.section("Loose ends") == ""


def test_repos_are_read_from_the_state_directory(tmp_path):
    make_repo(tmp_path, "zeta", plan=PLAN, handoff=HANDOFF, briefs={"alpha": BRIEF + RESULT})
    make_repo(tmp_path, "Beta", briefs={"lone": BRIEF})
    (tmp_path / "empty").mkdir()
    (tmp_path / "a-file").write_text("not a repo")

    beta, zeta = parse.repos(tmp_path)
    assert (beta.name, zeta.name) == ("Beta", "zeta")
    assert beta.handoff is None and beta.entries == ()
    assert [brief.slug for brief in zeta.briefs] == ["alpha"]


def test_a_missing_state_directory_has_no_repos(tmp_path):
    assert parse.repos(tmp_path / "nowhere") == []


def test_a_brief_is_live_only_under_an_open_plan_entry(tmp_path):
    briefs = {"alpha": BRIEF, "gamma": BRIEF + RESULT, "cleared": BRIEF + RESULT}
    make_repo(tmp_path, "demo", plan=PLAN, briefs=briefs)
    (repo,) = parse.repos(tmp_path)

    assert [(entry.slug, brief and brief.slug) for entry, brief in repo.live] == [
        ("alpha", "alpha"),
        ("beta", None),
    ]
    assert [brief.slug for brief in repo.cleared] == ["cleared", "gamma"]


def test_the_text_of_a_brief_cannot_inject_markup(tmp_path):
    make_repo(tmp_path, "demo", plan=PLAN, briefs={"alpha": BRIEF + "<script>alert(1)</script>\n"})
    html = page.render(parse.repos(tmp_path), state=tmp_path, generated="now")
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)" in html


def test_the_command_writes_one_page_and_prints_its_path(tmp_path, capsys):
    state = tmp_path / "state"
    make_repo(state, "demo", plan=PLAN, handoff=HANDOFF, briefs={"alpha": BRIEF})
    out = tmp_path / "out" / "briefs.html"

    assert cli.main([str(state), "--out", str(out)]) == 0

    assert capsys.readouterr().out.strip() == str(out)
    assert out.read_text().startswith("<!doctype html>")
    assert sorted(path.name for path in (state / "demo").iterdir()) == [
        "handoff.md",
        "plan.md",
        "tasks",
    ]


def test_the_default_page_is_outside_the_state_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert cli.default_out() == tmp_path / "cache" / "jbriefs" / "briefs.html"
    monkeypatch.delenv("JBUS_HOME_DIR", raising=False)
    assert home.homes_dir() == Path.home() / ".local" / "state" / "home"


def test_the_homes_state_is_jbus_home_dir_as_jbus_reads_it(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("JBUS_HOME_DIR", str(tmp_path / "homes"))
    assert home.homes_dir() == tmp_path / "homes"


SHAPED = BRIEF.replace("Done when:", "Size: S\nPlaybook: feature\nDone when:", 1)
PLAYBOOK_ASKED = "(name a file in playbooks/, without its .md, or none)"


def test_a_brief_with_a_size_and_a_real_playbook_holds():
    assert (parse.sized(SHAPED), parse.playbook(SHAPED)) == ("", "")
    for size in parse.SIZES:
        assert parse.sized(SHAPED.replace("Size: S", f"Size: {size}")) == ""
    for name in ("none", "bug-fix", "authoring-a-skill"):
        assert parse.playbook(SHAPED.replace("Playbook: feature", f"Playbook: {name}")) == ""


def test_a_brief_with_no_playbook_line_counts_as_none():
    assert parse.playbook(SHAPED.replace("Playbook: feature\n", "")) == ""


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ("fix", "names fix, which is no file in playbooks/"),
        ("feature.", "names feature., which is no file in playbooks/"),
        ("../feature", "names ../feature, which is no file in playbooks/"),
        ("", "is empty"),
        ("<a row `a crewmate` runs>", "is the template's own text"),
    ],
    ids=["fix", "feature.", "a path", "empty", "the template"],
)
def test_a_playbook_that_is_no_file_is_refused_with_one_line(said, why):
    text = SHAPED.replace("Playbook: feature", f"Playbook: {said}".rstrip())
    assert parse.playbook(text) == f"brief's Playbook: line {why} {PLAYBOOK_ASKED}"


@pytest.mark.parametrize(
    ("line", "why"),
    [
        (None, "brief has no Size: line"),
        ("Size:", "brief's Size: line is empty"),
        ("Size: medium", "brief's Size: line says medium"),
        ("Size: S.", "brief's Size: line says S."),
        ("Size: <S | M | L>", "brief's Size: line is the template's own text"),
        ("Size: XL", "brief's Size: line says XL"),
    ],
    ids=["no size", "empty", "a word", "a stop after it", "the template", "XL"],
)
def test_a_brief_with_no_size_is_refused_with_one_line(line, why):
    text = SHAPED.replace("Size: S\n", f"{line}\n" if line else "")
    assert parse.sized(text) == f"{why} (S, M or L)"


def test_only_the_head_of_a_brief_is_read_for_its_size_and_playbook():
    after = SHAPED.replace("Size: S\nPlaybook: feature\n", "") + RESULT
    assert parse.sized(after + "Size: S\n") == "brief has no Size: line (S, M or L)"
    assert parse.playbook(after + "Playbook: fix\n") == ""


def test_the_templates_have_a_size_line_and_the_brief_is_refused_until_it_is_filled_in():
    (line,) = [one for one in TEMPLATE.read_text().splitlines() if one.startswith("Size:")]
    text = written(by_a_scout=False)
    assert line in text and parse.sized(text).endswith("is the template's own text (S, M or L)")
    filled = text.replace(line, "Size: M").replace(
        next(one for one in text.splitlines() if one.startswith("Playbook:")), "Playbook: feature"
    )
    assert (parse.sized(filled), parse.playbook(filled)) == ("", "")
    entry = (REPO / "features" / "home" / "templates" / "plan-entry.md").read_text().splitlines()
    assert [one for one in entry if one.startswith("Size:")] == [line]


def test_every_crewmate_playbook_on_disk_is_a_name_the_parser_takes_and_no_other():
    """A brief may name only a playbook that a crewmate runs. That rules out a scout's, a
    home's or an expert's playbook, and `opening-a-pr`, which is the last step of every other
    one."""
    taken = set()
    for path in skills.listed("playbook").values():
        by = next(line for line in path.read_text().splitlines() if line.startswith("Run by: "))
        asked = "".join(f"{line}\n" for line in asks.asked(path.read_text()))
        named = SHAPED.replace("Playbook: feature\n", f"Playbook: {path.stem}\n{asked}")
        said = parse.playbook(named)
        if by.startswith("Run by: a crewmate,") and "never picked for a brief" not in by:
            assert said == "", path.stem
            taken.add(path.stem)
        else:
            assert "which is not a crewmate's playbook" in said, path.stem
    assert {"feature", "bug-fix"} <= taken
    assert {"opening-a-pr", "autopilot-full", "investigation", "expert-study"}.isdisjoint(taken)


SKILLS_REAL = (
    "`principles/` (renames only), every file that names a principle, `templates/brief.md`, "
    "`skills/home/SKILL.md` (only where it says how a brief is written), the brief lint in "
    "`src/jbus/` or `src/jbriefs/`, `src/jmerge/ready.py` if the gate goes there, the new map "
    "file, their tests, `docs/`"
)
WHERES = {
    "backticks, prose, and a trailing list of things that are no path": (
        SKILLS_REAL,
        (
            "principles",
            "templates/brief.md",
            "skills/home/SKILL.md",
            "src/jbus",
            "src/jbriefs",
            "src/jmerge/ready.py",
            "docs",
        ),
    ),
    "a directory with the names of its files in parentheses": (
        "tests/ (conftest.py, test_gate_skills.py), pyproject.toml, "
        "src/jbus/view/__init__.py:368 (one line)",
        ("tests", "pyproject.toml", "src/jbus/view/__init__.py"),
    ),
    "a path with a line range, and words that are no path": (
        "`src/a.py:10-20`, the eval's run directory this branch adds under `evals/skill-cut/`",
        ("src/a.py", "evals/skill-cut"),
    ),
    "a path with no backticks, then prose and a flag in backticks": (
        "src/jmerge/cli.py, docs/ pages tied to `--help`, the tests",
        ("src/jmerge/cli.py", "docs"),
    ),
    "the whole repo, with the words that say so": ("`.` (the whole repo, jbus filed it)", (".",)),
    "globs": ("`tests/test_*.py`, `skills/*/SKILL.md`", ("tests/test_*.py", "skills/*/SKILL.md")),
    "brace sets, bare and in backticks, one in another": (
        "src/jmerge/{claims,cli}.py, `docs/{flow.html,jbus.md}`, tests/test_{a,b{1,2}}.py",
        (
            "src/jmerge/claims.py",
            "src/jmerge/cli.py",
            "docs/flow.html",
            "docs/jbus.md",
            "tests/test_a.py",
            "tests/test_b1.py",
            "tests/test_b2.py",
        ),
    ),
    "bare paths after prose in their item": (
        "the pull request's own files, plus templates/jbus-ci.service and what #88 added, "
        "whichever files `jleak --all` names: mostly tests/, some of src/, the Makefile",
        ("templates/jbus-ci.service", "tests", "src"),
    ),
    "none of these is a path in the repo": (
        "wherever it takes, `make check`, `/etc/hosts`, `../outside.py`, `~/x`",
        (),
    ),
}


@pytest.mark.parametrize(("line", "paths"), WHERES.values(), ids=WHERES)
def test_a_where_line_is_the_paths_and_globs_it_names(line, paths):
    assert parse.where(f"# a: b\nWhere: {line}\n") == paths


def test_only_the_where_line_of_the_head_is_read():
    assert parse.where("# a: b\nWhere: `src/`\n\n## Result\nWhere: `docs/`\n") == ("src",)
    assert parse.where("# a: b\nTask: `src/`\n") == ()


@pytest.mark.parametrize(
    ("patterns", "path", "covered"),
    [
        (("src",), "src/a/b.py", True),
        (("src",), "src2/a.py", False),
        (("src/a.py",), "src/a.py", True),
        (("src/a.py",), "src/a.pyc", False),
        (("tests/test_*.py",), "tests/test_a.py", True),
        (("tests/test_*.py",), "tests/deep/test_a.py", False),
        (("skills/*",), "skills/crew/SKILL.md", True),
        (("**/SKILL.md",), "skills/crew/SKILL.md", True),
        (("docs/**",), "docs/a/b.md", True),
        (("src/?.py",), "src/a.py", True),
        (("src/?.py",), "src/ab.py", False),
        ((), "src/a.py", False),
        ((".",), "src/a.py", True),
    ],
)
def test_a_path_is_covered_by_what_it_is_or_sits_under(patterns, path, covered):
    assert paths.covers(patterns, path) is covered


def test_the_brief_for_a_red_main_with_no_changed_file_has_a_where_the_lint_takes():
    text = (REPO / "features/jbus/tests/fixtures/fix-briefs/main-quiet.md").read_text()
    assert parse.where(text) == (".",)
    assert not [fault for fault in parse.faults(text) if "Where" in fault]


def test_a_brief_whose_where_names_no_path_is_refused_with_the_line():
    fault = "wherever it takes, the tests"
    (said,) = [each for each in parse.faults(BRIEF.replace("`src/`", fault)) if "Where" in each]
    assert said.startswith("brief's Where: line names no path under the repo")
    assert said.endswith(f": {fault}")
    assert not [each for each in parse.faults(BRIEF) if "Where" in each]


def test_a_thread_line_below_the_first_heading_still_names_the_thread():
    brief = "# alpha: a task\nWhere: src/\n\n## Notes\nThread: mcp:low\n\n## Result\nStatus: done\n"
    assert parse.thread_of(brief) == "mcp:low"
    assert parse.brief("alpha", brief).thread == "mcp:low"
    assert parse.head(brief, "Thread:") is None


def test_reviewer_lines_are_read_by_kind_and_a_scoped_one_by_its_head():
    head, other = "a" * 40, "b" * 40
    brief = (
        "# alpha: a task\n\n## Result\nStatus: done\nReviewer: mcp:one #1\n"
        "Second reviewer: none, no launch tool\n"
        f"Scoped reviewer: mcp:two of {other}\nScoped reviewer: none, no launch tool of {head}\n"
    )
    assert below.reviewers(brief, "Reviewer") == ["mcp:one #1"]
    assert below.reviewers(brief, "Scoped reviewer", head) == [f"none, no launch tool of {head}"]
    assert [below.launched(one) for one in below.reviewers(brief, "Scoped reviewer")] == [
        True,
        False,
    ]
    assert not below.launched(below.reviewers(brief, "Second reviewer")[0])


def test_a_reviewer_line_in_the_head_is_guidance_and_names_no_reviewer():
    head = (
        "# alpha: a task\nReviewer: check that the ask is one question\n\n## Result\nStatus: done\n"
    )
    assert below.reviewers(head, "Reviewer") == []
    assert findings.roster(head) == findings.Legacy(0)
    launched = head + "Reviewer: mcp:one #1\n"
    assert below.reviewers(launched, "Reviewer") == ["mcp:one #1"]
    assert findings.roster(launched) == findings.Numbered(frozenset({1}))


@pytest.mark.parametrize(
    ("line", "label"),
    [("Fail-safe: a bundle", "Fail-safe"), ("Built on it: nothing", "Built on it")],
)
def test_a_label_word_may_hold_a_hyphen_between_letters(line, label):
    said = parse.fields(f"# a: b\nHolds: rewrites history\n{line}\n")
    assert [one for one, _ in said] == [parse.TITLE, "Holds", label]


@pytest.mark.parametrize("line", ["Wait - then Foo: bar", "Foo-: x", "Foo--bar: x"])
def test_a_line_whose_hyphen_is_not_between_letters_continues_the_field_above(line):
    said = parse.fields(f"# a: b\nHolds: rewrites history\n{line}\n")
    assert said[1:] == [("Holds", ["rewrites history", line])]
