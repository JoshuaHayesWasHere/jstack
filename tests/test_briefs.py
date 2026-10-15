from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

import pytest

from jbriefs import cli, page, parse
from jbus import dispatch

TEMPLATE = Path(__file__).parent.parent / "templates" / "brief.md"
FINDINGS = ("Read:", "Change:", "Rests on:", "Sources:", "Ruled out:")

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


def written(*, by_a_scout):
    """A brief in the template's shape with every field filled in, as a scout or a home writes it.

    A scout's findings are filled with what a result holds, to show they are not read as one.
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
    assert line in text and dispatch.designed(text) == dispatch.NO_DESIGN
    for said in ("Design: scouts/alpha-design.md", "Design: none, a one-line fix"):
        assert dispatch.designed(text.replace(line, said)) == ""
        assert dispatch.designed(text.replace(line + "\n", "") + RESULT + said) != ""


PROOFS = {
    "a test path": ("tests/test_briefs.py passes", "a test"),
    "a test's name": ("test_a_brief_is_proven_by_what_is_outside_the_agent", "a test"),
    "the tests": ("the parser tests above", "a test"),
    "a command": ("`jbus --project jstack queue show` prints the row", "a test"),
    "make": ("make check exits 0", "a test"),
    "a metric": ("the p95 latency of a pass, from jgauge", "a metric"),
    "a percentage": ("under 2% of passes gated", "a metric"),
    "a dataset": ("the ten past briefs of the eval dataset", "a dataset"),
    "an external judge": ("CI on the pull request", "an external judge"),
    "a judge by name": ("an external judge, blind to which brief is which", "an external judge"),
    "the user": ("the user, on the page", "the user"),
    "the operator": ("the operator's word on the screenshot", "the user"),
    "the owner": ("the owner of the repo signs it off", "the user"),
    "a review by the user": ("reviewed by the user", "the user"),
    "a test the crewmate runs": ("the crewmate runs tests/test_briefs.py", "a test"),
    "a command with no path": ("`jbus queue show` prints the row", "a test"),
    "a linter": ("`ruff check src` is clean", "a test"),
    "a make target": ("make build exits 0", "a test"),
    "another make target": ("make e2e passes", "a test"),
    "a hyphenated test": ("the unit-tests pass", "a test"),
    "a smoke test": ("the smoke-test passes", "a test"),
    "a bare percentage": ("coverage stays above 90%", "a metric"),
    "a rate": ("error rate under 2%", "a metric"),
    "a judge": ("a human judge scores it", "an external judge"),
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


@pytest.mark.parametrize("case", PROOFS)
def test_a_proof_that_names_something_outside_the_agent_holds(case):
    said, kind = PROOFS[case]
    proof = parse.proof(said)
    assert (proof.said, proof.kind, proof.why) == (said, kind, "")


@pytest.mark.parametrize("case", REFUSED)
def test_a_proof_by_the_agents_own_word_is_refused_with_one_line_saying_why(case):
    said, fault = REFUSED[case]
    proof = parse.proof(said)
    assert proof.kind == ""
    assert proof.why == f"brief's Proves it: line {fault} {ASKED}"


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
    assert dispatch.proven(text) == parse.brief("alpha", text).proof.why
    filled = text.replace(line, "Proves it: tests/test_alpha.py passes")
    assert parse.brief("alpha", filled).proof.kind == "a test"
    assert dispatch.proven(filled) == ""


def test_a_brief_with_no_proves_it_line_is_launched_as_before_and_one_under_its_head_is_not_read():
    """Briefs queued before the line was asked for have none: they are grandfathered."""
    assert parse.brief("alpha", BRIEF).proof is None
    assert dispatch.proven(BRIEF) == ""
    under = BRIEF + RESULT + "Proves it: reviewed by crewmate\n"
    assert parse.brief("alpha", under).proof is None
    assert dispatch.proven(under) == ""
    first = BRIEF + "Proves it: the crewmate\nProves it: tests/test_alpha.py\n"
    assert (
        dispatch.proven(first)
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


class Thread(NamedTuple):
    shown: str
    copied_by_its_button: str


class Page(HTMLParser):
    """The rendered page as a browser reads it: its links, and each thread a brief names."""

    def __init__(self, html: str):
        super().__init__()
        self.hrefs: list[str] = []
        self.threads: list[Thread] = []
        self._words: list[str] | None = None
        self._depth = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        found = dict(attrs)
        if tag == "a":
            self.hrefs.append(found.get("href") or "")
        if self._words is not None:
            self._depth += 1
            if tag == "button" and "data-copy" in found:
                self.threads.append(Thread(" ".join(self._words), found["data-copy"]))
        elif found.get("data-part") == "thread":
            self._words, self._depth = [], 1

    def handle_endtag(self, tag):
        if self._words is not None:
            self._depth -= 1
            if not self._depth:
                self._words = None

    def handle_data(self, data):
        if self._words is not None and data.strip():
            self._words.append(data.strip())


def test_the_page_with_no_repos_says_so():
    html = page.render([], state=Path("/tmp/state"), generated="now")
    assert "No repo has a home yet" in html
    assert "/tmp/state" in html


def test_the_page_shows_the_handoff_the_entries_and_the_briefs(tmp_path):
    briefs = {"alpha": BRIEF + RESULT, "cleared": BRIEF}
    make_repo(tmp_path, "demo", plan=PLAN, handoff=HANDOFF, briefs=briefs)
    html = page.render(parse.repos(tmp_path), state=tmp_path, generated="now")

    assert "Take <code>beta</code> from plan.md." in html
    assert "Rename the repo?" in html
    assert "a task nobody has a brief for" in html
    assert "It is planned." in html
    assert "finished but not cleared yet" not in html
    assert 'href="https://github.com/someone/demo/pull/7"' in html
    hrefs = Page(html).hrefs
    assert [href for href in hrefs if not href.startswith(("https://", "http://", "#"))] == []
    assert "Do not touch:" in html
    assert "Changed:" in html


def test_the_page_shows_a_paused_brief_as_paused_and_not_as_unclear(tmp_path):
    briefs = {"alpha": BRIEF + RESULT.replace("Status: done", "Status: paused")}
    make_repo(tmp_path, "demo", plan=PLAN, handoff=HANDOFF, briefs=briefs)
    html = page.render(parse.repos(tmp_path), state=tmp_path, generated="now")

    assert ">1 paused<" in html
    assert ">paused<" in html
    assert "unclear" not in html


def test_a_brief_shows_its_thread_as_a_title_and_an_id_to_copy(tmp_path):
    no_thread = BRIEF.replace("Thread: mcp:1111-aaaa\n", "")
    briefs = {"alpha": BRIEF + RESULT, "cleared": BRIEF.replace("1111-aaaa", "2222-bbbb")}
    make_repo(tmp_path, "demo", plan=PLAN, handoff=HANDOFF, briefs=briefs | {"bare": no_thread})
    found = Page(page.render(parse.repos(tmp_path), state=tmp_path, generated="now"))

    assert found.threads == [
        ("crew: alpha mcp:1111-aaaa", "mcp:1111-aaaa"),
        ("crew: cleared mcp:2222-bbbb", "mcp:2222-bbbb"),
    ]


def test_a_cleared_brief_is_collapsed_and_apart_from_the_live_ones(tmp_path):
    make_repo(tmp_path, "demo", plan=PLAN, briefs={"alpha": BRIEF, "cleared": BRIEF + RESULT})
    html = page.render(parse.repos(tmp_path), state=tmp_path, generated="now")

    live, _, apart = html.partition('data-part="cleared"')
    assert 'id="demo-alpha"' in live
    assert 'id="demo-cleared"' in apart
    assert "<details open" not in apart
    assert "1 brief with no open plan entry" in html


def test_the_text_of_a_brief_cannot_inject_markup(tmp_path):
    make_repo(tmp_path, "demo", plan=PLAN, briefs={"alpha": BRIEF + "<script>alert(1)</script>\n"})
    html = page.render(parse.repos(tmp_path), state=tmp_path, generated="now")
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)" in html


def test_a_bold_line_that_ends_in_a_url_keeps_its_link_and_closes_its_bold():
    assert page.inline("**see https://github.com/o/r/pull/5** now") == (
        '<strong>see <a class="link" href="https://github.com/o/r/pull/5">'
        "https://github.com/o/r/pull/5</a></strong> now"
    )


def test_only_a_status_that_names_a_pull_request_gets_its_badge():
    def badge(status):
        return "pull request" in page._entry_badge(status)

    assert badge("PR https://github.com/o/r/pull/5")
    assert badge("pr #5")
    assert not badge("proposed (not approved)")
    assert not badge("problem with CI")


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
    assert cli.DEFAULT_STATE == Path.home() / ".local" / "state" / "home"
