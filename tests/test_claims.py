"""The files every brief still out holds are printed by one command, `jmerge --claims`, for
the homes of a repo to read before a launch. It is run as a home runs `jmerge`, against a fake
`gh` and a temporary state directory."""

import json

import pytest

from test_home_merge import ME, OTHER, Home
from test_home_thread import READERS, about_the_home_id, paths

PULLS = "https://example.test/pull/{}"
WHERE = "`src/alpha/`, a new test file"


def brief(slug, thread=True, result="", home="", where=WHERE):
    """A brief as a home writes it, then what its crewmate added."""
    return (
        f"# {slug}: a task\n"
        'Task: "do it"\n'
        + (f"Where: {where}\n" if where else "")
        + (f"Home: {home}\n" if home else "")
        + (f"Thread: mcp:thread-of-{slug}\n" if thread else "")
        + result
    )


def result(pull="none", status="done"):
    return f"\n## Result\nStatus: {status}\nBranch: alpha   Pull request: {pull}\nLeft: none\n"


class Claims:
    def __init__(self, home):
        self.home = home
        (home.state / "home-id").write_text(f"{ME}\n")
        self.open()

    def open(self, *numbers):
        """The pull requests GitHub lists as open."""
        listed = [{"number": number, "url": PULLS.format(number)} for number in numbers]
        (self.home.stub / "list.json").write_text(json.dumps(listed))

    def write(self, slug, **said):
        (self.home.tasks / f"{slug}.md").write_text(brief(slug, **said))

    def run(self):
        said = self.home.run("--claims")
        assert self.home.stderr == ""
        return said


@pytest.fixture
def claims(tmp_path):
    return Claims(Home(tmp_path))


def test_a_brief_with_no_thread_line_is_not_launched(claims):
    claims.write("alpha", thread=False)
    assert claims.run() == [f"alpha not launched root Where: {WHERE}"]


def test_a_launched_brief_with_no_result_is_out(claims):
    claims.write("alpha")
    assert claims.run() == [f"alpha out root Where: {WHERE}"]


def test_a_brief_whose_pull_request_is_open_holds_its_files_under_its_number(claims):
    claims.write("alpha", result=result(PULLS.format(12)))
    claims.open(7, 12)
    assert claims.run() == [f"alpha pull request 12 root Where: {WHERE}"]


def test_the_last_result_is_the_one_that_counts(claims):
    claims.write("alpha", result=result(PULLS.format(7)) + result(PULLS.format(12)))
    claims.open(12)
    assert claims.run() == [f"alpha pull request 12 root Where: {WHERE}"]
    claims.open(7)
    assert claims.run() == []


def test_a_brief_whose_pull_request_is_no_longer_open_claims_nothing(claims):
    claims.write("alpha", result=result(PULLS.format(12)))
    claims.write("beta")
    claims.open(7)
    assert claims.run() == [f"beta out root Where: {WHERE}"]


def test_a_brief_folded_into_another_claims_nothing(claims):
    """As `fewer-messages` was: the home wrote its Result, which names no pull request."""
    folded = "\n## Result\nStatus: done (folded into `home-listens`, pull request 31, merged)\n"
    claims.write("alpha", result=folded)
    claims.write("beta", result=result())
    claims.write("gamma", thread=False)
    assert claims.run() == [f"gamma not launched root Where: {WHERE}"]


def test_a_paused_brief_still_holds_its_files_with_and_without_a_pull_request(claims):
    claims.write("alpha", result=result(status="paused"))
    claims.write("beta", result=result(PULLS.format(12), status="paused"))
    claims.write("gamma", result=result(PULLS.format(7), status="paused"))
    claims.write("delta", result=result(status="paused, wip at abc123"))
    claims.open(12)
    assert claims.run() == [
        f"alpha paused root Where: {WHERE}",
        f"beta paused pull request 12 root Where: {WHERE}",
        f"delta paused root Where: {WHERE}",
    ]


def test_a_brief_that_was_paused_and_then_ended_claims_nothing(claims):
    claims.write("alpha", result=result(status="paused") + result())
    assert claims.run() == []


def test_a_brief_of_a_scoped_home_is_under_its_scope(claims):
    scope = claims.home.state / "pstack"
    scope.mkdir()
    (scope / "home-id").write_text(f"{OTHER}\n")
    claims.write("alpha", home=ME)
    claims.write("ps-alpha", home=f"{OTHER} (the pstack home)", where="`playbooks/`")
    assert claims.run() == [
        f"alpha out root Where: {WHERE}",
        "ps-alpha out pstack Where: `playbooks/`",
    ]


def test_a_scoped_home_is_also_known_by_its_directory_and_by_the_home_it_took_over_from(claims):
    scope = claims.home.state / "review-speed"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:the-next-one\n")
    (scope / "handoff.md").write_text(f"# Handoff\nWas home: {OTHER}\n")
    (claims.home.state / "handoff.md").write_text("# Handoff\nWas home: mcp:the-root-before\n")
    claims.write("rs-alpha", home="review-speed (a second home of this repo)")
    claims.write("rs-beta", home=OTHER)
    claims.write("alpha", home="mcp:the-root-before")
    claims.write("stray", home="mcp:nobody-here")
    assert claims.run() == [
        f"alpha out root Where: {WHERE}",
        f"rs-alpha out review-speed Where: {WHERE}",
        f"rs-beta out review-speed Where: {WHERE}",
        f"stray out root Where: {WHERE}",
    ]


@pytest.mark.parametrize(
    ("line", "home"),
    [
        ("", "root"),
        ("pstack", "pstack"),
        ("pstack (a second home of this repo)", "pstack"),
        (OTHER, "pstack"),
        (ME, "root"),
        ("mcp:a-home-of-long-ago", "root"),
        ("tasks", "root"),
    ],
)
def test_a_brief_has_one_home_by_each_of_the_three_kinds_of_home_line(claims, line, home):
    """No line, a scope's name, and the thread id a brief written before has."""
    scope = claims.home.state / "pstack"
    scope.mkdir()
    (scope / "plan.md").write_text("# a plan\n")
    (scope / "home-id").write_text(f"{OTHER}\n")
    claims.write("alpha", home=line)
    assert claims.run() == [f"alpha out {home} Where: {WHERE}"]


SCOPES = {
    "running": {"home-id": f"{OTHER} \n", "handoff.md": "# Handoff\nWas home: mcp:before\n"},
    "handed off": {"handoff.md": "# Handoff\nNone\n\nWas home:  mcp:before (the last)\n"},
    "a plan and nothing more": {"handoff.md": "# Handoff\nNone\nmcp:before\n"},
    "an empty home-id": {"home-id": "\n"},
}
LINES = ["", "speed", "speed (a second home)", OTHER, "mcp:before", ME, "mcp:root-before", "None"]


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("scope", SCOPES)
def test_a_thread_finds_a_brief_the_home_jmerge_gives_it(claims, reader, scope):
    """The block a thread finds its home with and `jmerge --claims` are run over one state
    directory, for every kind of `Home:` line and every state a scope is left in."""
    state = claims.home.state
    (state / "handoff.md").write_text("# Handoff\nWas home: mcp:root-before\n")
    (state / "speed").mkdir()
    (state / "speed" / "plan.md").write_text("# a plan\n")
    for name, text in SCOPES[scope].items():
        (state / "speed" / name).write_text(text)
    for at, line in enumerate(LINES):
        claims.write(f"brief-{at}", home=line)
    by_jmerge = [line.split()[2] for line in claims.run()]

    block = about_the_home_id(reader)
    (last,) = [line for line in block.splitlines() if '-s "$D/home-id"' in line]
    block = block.replace(last, 'if [ "$D" = "$H" ]; then echo root; else echo "${D##*/}"; fi')
    by_thread = [
        claims.home.sh(f'{paths(reader)}\nB="$H/tasks/brief-{at}.md"\n{block}')
        for at in range(len(LINES))
    ]
    assert claims.home.stderr == ""
    assert by_thread == [[home] for home in by_jmerge]
    assert "speed" in by_jmerge or scope in ("a plan and nothing more", "an empty home-id")


def test_a_brief_with_no_where_line_is_still_listed(claims):
    claims.write("alpha", where="")
    assert claims.run() == ["alpha out root no Where line"]


def kept(state):
    """Every file of the state but the mark of the merge step, which this test runs it in."""
    return [path for path in state.rglob("*") if path.is_file() and path.name != "merge-seen"]


def test_it_asks_github_once_and_merges_removes_and_logs_nothing(claims):
    claims.write("alpha", result=result(PULLS.format(12)))
    claims.write("beta")
    claims.open(12)
    before = {path: path.read_bytes() for path in kept(claims.home.state)}
    assert len(claims.run()) == 2
    assert claims.home.code == 0
    calls = (claims.home.stub / "calls").read_text().splitlines()
    assert calls == ["pr list --state open --limit 1000 --json number,url"]
    after = {path: path.read_bytes() for path in kept(claims.home.state)}
    assert after == before


def test_when_github_cannot_be_asked_it_waits(claims):
    claims.write("alpha")
    (claims.home.stub / "list.json").unlink()
    assert claims.run() == ["wait: could not ask GitHub"]
    assert claims.home.code == 1
    assert not (claims.home.state / "merge.log").exists()
