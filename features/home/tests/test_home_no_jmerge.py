"""A repo has one merger, jbus, which runs `jmerge` on each pass whatever `home-thread` holds, so
no skill step runs it to merge or land. The one block that runs it is the sweep, and only while
`home-thread` holds an id. The tests take every `sh` block of a skill that runs `jmerge`, and run
it after the blocks that its skill says to run first. The blocks run against a stub `jmerge` that
records its calls."""

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import jsettings
from jmerge import claims, cli, ready
from test_home_thread import as_read, named
from testing.layouts import assembled

SKILLS = assembled() / "skills"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
RUNS = re.compile(
    r"\bjmerge(?=[ \t]*(?:$|[;|&)]|-))(?![ \t]+--(?:checks|claims|scope|range-diff|remake)\b)",
    re.M,
)
FILLED = re.compile(r"'<[^'<>\n]+>'")
NAME = "demo"
ME = "mcp:this-home"
URL = "https://example.test/pull/7"
HOLD = f"hold 7 {URL}: needs user, touches secrets/prod.json"
WAIT = f"wait 8 {URL}8: check has not passed"

UV = """\
#!/bin/sh
[ "$1 $2" = "run --project" ] || exit 64
shift 3
exec "$@"
"""
JMERGE = """\
#!/bin/sh
echo "$*" >> "$CALLS"
log="$HOME/.local/state/home/demo/merge.log"
if [ -f "$SAYS" ]; then cat "$SAYS" && sed 's/^/2026-10-12 13:41 /' "$SAYS" >> "$log"; fi
if [ -f "$LOGS" ]; then sed 's/^/2026-10-12 13:41 /' "$LOGS" >> "$log"; fi
ends=$(cat "$ENDS" 2> /dev/null || echo 0)
if [ "$ends" = killed ]; then kill -9 "-$(ps -o pgid= -p "$$" | tr -d ' ')"; fi
exit "$ends"
"""
GH = """\
#!/bin/sh
[ "$1 $2 $3 $4" = "pr list --repo https://example.test/demo" ] || exit 64
[ "$5 $6 $7 $8 $9 ${10} ${11}" = "--state open --limit 200 --json number,url --jq" ] || exit 64
cat "$OPEN"
"""


def blocks(skill, read=Path.read_text):
    """Each `sh` block of a skill, with the number of the line it starts on. By default the
    number counts the lines of the file alone. With `as_read` it counts the lines of the skill as
    an agent reads it."""
    text = read(skill)
    return [
        (text.count("\n", 0, found.start(1)) + 1, textwrap.dedent(found.group(1)))
        for found in FENCED.finditer(text)
    ]


def first(skill):
    """The blocks a skill says to run first: the one at its top and the one that finds this
    home, for the skill that has them."""
    found = []
    for mark in (r"^H=", r"^ME="):
        found += [text for _, text in blocks(skill, as_read) if re.search(mark, text, re.M)][:1]
    return found


MERGING = [
    pytest.param(skill, text, id=f"{skill.parent.name}:{doc.relative_to(skill.parent)}:{line}")
    for skill in sorted(SKILLS.glob("**/SKILL.md"))
    for doc in [skill, *named(skill)]
    for line, text in blocks(doc)
    if RUNS.search(text)
]
HOME = SKILLS / "home" / "SKILL.md"


class Repo:
    """A user's home directory, a repo's checkout and its state, and a stub `jmerge`."""

    def __init__(self, tmp_path):
        self.user = tmp_path / "user"
        (self.user / ".claude").mkdir(parents=True)
        (self.user / ".claude" / "skills").symlink_to(SKILLS)
        self.state = self.user / ".local" / "state" / "home" / NAME
        self.state.mkdir(parents=True)
        (self.state / "home-id").write_text(f"{ME}\n")
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "open").write_text(f"7 {URL}\n8 {URL}8\n")
        for name, text in (("uv", UV), ("jmerge", JMERGE), ("gh", GH)):
            (self.stub / name).write_text(text)
            (self.stub / name).chmod(0o755)
        self.main = tmp_path / "code" / NAME
        self.main.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.main, check=True)
        origin = ["git", "remote", "add", "origin", "https://example.test/demo"]
        subprocess.run(origin, cwd=self.main, check=True)
        (self.state / "tasks").mkdir()

    def switch(self, held):
        """What `home-thread` holds, or `None` for no file."""
        if held is not None:
            (self.state / "home-thread").write_text(held)

    def sh(self, *texts, me=ME):
        """Replace each placeholder with `me` in single quotes, and run the blocks in one call, as
        a home would."""
        script = FILLED.sub(f"'{me}'", "\n".join(texts))
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            cwd=self.main,
            start_new_session=True,
            env={
                **os.environ,
                "HOME": str(self.user),
                "PATH": f"{self.stub}:{Path(sys.executable).parent}:{os.environ['PATH']}",
                "CALLS": str(self.stub / "calls"),
                "OPEN": str(self.stub / "open"),
                "SAYS": str(self.stub / "says"),
                "LOGS": str(self.stub / "logs"),
                "ENDS": str(self.stub / "ends"),
            },
        )
        self.code, self.stderr = ran.returncode, ran.stderr
        return ran.stdout.splitlines()

    def calls(self):
        """The arguments the blocks gave `jmerge`, a line for each run."""
        try:
            return (self.stub / "calls").read_text().splitlines()
        except FileNotFoundError:
            return []

    def merge(self, me=ME):
        """The merge step, as the home skill says to run it."""
        return self.sh(*first(HOME), step(), me=me)

    def log(self, *lines):
        """Write lines that `jmerge` prints when jbus runs it, the way jbus keeps them. jbus
        appends each line to the log with a date. For each pull request, jbus also keeps the
        last `wait` or `hold` line that `jmerge` printed about it."""
        with (self.state / "merge.log").open("a") as log:
            log.writelines(f"2026-10-12 13:40 {line}\n" for line in lines)
        last = self.state / "merge.log.last"
        kept = json.loads(last.read_text()) if last.exists() else {}
        kept.update({line.split()[1]: line for line in lines if not line.startswith("merged")})
        last.write_text(json.dumps(kept))


def step():
    (found,) = [text for _, text in blocks(HOME, as_read) if "first}/merge-seen" in text]
    return found


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


@pytest.mark.parametrize("held", [None, "", " \n"], ids=["missing", "empty", "blank"])
@pytest.mark.parametrize(("skill", "text"), MERGING)
def test_no_block_runs_jmerge_while_the_switch_is_empty(repo, skill, text, held):
    repo.switch(held)
    said = repo.sh(*first(skill), text)
    assert repo.calls() == []
    assert (repo.code, repo.stderr) == (0, "")
    assert said == ["sweep off: home-thread is empty, so no home runs jmerge --sweep"]


@pytest.mark.parametrize(("skill", "text"), MERGING)
def test_the_sweep_runs_jmerge_once_when_the_switch_holds_an_id(repo, skill, text):
    repo.switch("mcp:some-home\n")
    said = repo.sh(*first(skill), text)
    assert (repo.code, repo.stderr, said, repo.calls()) == (0, "", [], ["--sweep"])


def test_the_merge_step_runs_no_jmerge_whatever_the_switch_holds(repo):
    (repo.stub / "open").write_text("")
    for held in (None, f"{ME}\n"):
        repo.switch(held)
        assert repo.merge() == []
    assert repo.calls() == []
    assert (repo.code, repo.stderr) == (0, "")


MERGED = 'merged 9 beta abc1234 "feat: it", revert: gh pr revert x'


def test_the_merge_step_tells_a_merge_once_and_what_each_open_pull_request_waits_for(repo):
    repo.log(MERGED, WAIT, HOLD)
    assert repo.merge() == [f"{HOLD}", WAIT]
    repo.log(MERGED.replace("beta", "gamma"))
    assert repo.merge() == [MERGED.replace("beta", "gamma"), HOLD, WAIT]
    assert repo.merge() == [HOLD, WAIT]
    (repo.stub / "open").write_text(f"8 {URL}8\n9 {URL}9\n")
    nothing = f"wait 9 {URL}9: jbus has said nothing of it yet"
    assert repo.merge() == [WAIT, nothing]
    assert repo.calls() == []
    assert (repo.code, repo.stderr) == (0, "")


def test_a_log_shorter_than_the_mark_is_read_from_its_start(repo):
    repo.log(WAIT, WAIT, WAIT)
    repo.merge()
    (repo.state / "merge.log").write_text("")
    repo.log(MERGED)
    (repo.stub / "open").write_text(f"8 {URL}8\n")
    assert repo.merge() == [MERGED, WAIT]


def test_a_home_is_told_its_own_lines_and_no_other_homes(repo):
    scope = repo.state / "billing"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:scoped\n")
    tasks = repo.state / "tasks"
    (tasks / "alpha.md").write_text(f"# alpha\nBranch: alpha   Pull request: {URL}\n")
    (tasks / "beta.md").write_text(
        f"# beta\nHome: mcp:scoped\nBranch: beta   Pull request: {URL}8\n"
    )
    (tasks / "gamma.md").write_text("# gamma\nHome: billing (the scope)\n")
    mine, theirs = MERGED.replace("beta", "alpha"), MERGED.replace("beta", "gamma")
    nothing = f"wait 8 {URL}8: jbus has said nothing of it yet"
    assert repo.merge(me="mcp:scoped") == [nothing]
    repo.merge()
    repo.log(mine, MERGED, theirs, WAIT, HOLD)
    scoped = repo.merge(me="mcp:scoped")
    assert scoped == [MERGED, theirs, WAIT]
    assert repo.merge() == [mine, HOLD]
    assert (scope / "merge-seen").read_text() == (repo.state / "merge-seen").read_text() == "5\n"


def test_an_open_pull_request_is_the_home_of_the_brief_whose_branch_line_ends_on_it(repo):
    scope = repo.state / "billing"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:scoped\n")
    tasks = repo.state / "tasks"
    (tasks / "alpha.md").write_text(f"# alpha\nDecisions: as {URL} did\n")
    (tasks / "beta.md").write_text(
        f"# beta\nHome: mcp:scoped\nsee {URL}\n## Result\nBranch: beta   Pull request: {URL}\n"
    )
    (repo.stub / "open").write_text(f"7 {URL}\n")
    repo.log(HOLD)
    assert ready.brief_of(URL, tasks) == tasks / "beta.md"
    assert repo.merge() == []
    assert repo.merge(me="mcp:scoped") == [HOLD]
    assert (repo.code, repo.stderr) == (0, "")


OWN, THEIRS = MERGED.replace("beta", "gamma"), MERGED.replace("beta", "delta")


def test_two_briefs_of_one_pull_request_are_told_apart_as_jmerge_does(repo, monkeypatch):
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    scope = repo.state / "billing"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:scoped\n")
    tasks = repo.state / "tasks"
    (tasks / "foo.md").write_text(f"# foo\nBranch: foo   Pull request: {URL}\n")
    (tasks / "foo-z.md").write_text(
        f"# foo-z\nHome: billing\nBranch: foo-z   Pull request: {URL}\n"
    )
    (repo.stub / "open").write_text(f"7 {URL}\n")
    repo.log(HOLD)
    assert ready.brief_of(URL, tasks) == tasks / "foo-z.md"
    assert repo.merge() == []
    assert repo.merge(me="mcp:scoped") == [HOLD]


NAMED = {
    "none": "",
    "root": f"Home: {ME}\n",
    "root-before": "Home: mcp:root-before\n",
    "scoped": "Home: mcp:scoped  \n",
    "scope": "Home: billing (the scope)\n",
    "scoped-before": "Home: mcp:scoped-before\n",
    "no-scope": "Home: reports\n",
    "tasks": "Home: tasks\n",
    "nobody": "Home: mcp:nobody\n",
}


OWNERS = {
    "none": claims.ROOT,
    "root": claims.ROOT,
    "root-before": claims.ROOT,
    "scoped": "billing",
    "scope": "billing",
    "scoped-before": "billing",
    "no-scope": claims.ROOT,
    "tasks": claims.ROOT,
    "nobody": claims.ROOT,
}


def test_whose_a_brief_is_agrees_with_jmerge(repo):
    """Three readers agree on each case: the skill's `whose`, the `homes` of `jmerge --claims`, and
    the `others` of `jmerge --home`. A `Home:` line that names no home is the root's."""
    scope = repo.state / "billing"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:scoped\n")
    (scope / "handoff.md").write_text("# handoff\nWas home: mcp:scoped-before\n")
    (repo.state / "handoff.md").write_text("# handoff\nWas home: mcp:root-before\n")
    (repo.state / "reports").mkdir()
    for slug, line in NAMED.items():
        (repo.state / "tasks" / f"{slug}.md").write_text(f"# {slug}\n{line}")
    (repo.stub / "open").write_text("")
    repo.merge()
    repo.merge(me="mcp:scoped")
    repo.log(*(MERGED.replace("beta", slug) for slug in NAMED))
    homes = cli.Repo(repo.main, repo.state, None, False, user=jsettings.DEFAULTS).homes.known
    assert {slug: claims.of_brief(slug, NAMED[slug], {}, homes).home for slug in NAMED} == OWNERS
    for me, name in ((ME, claims.ROOT), ("mcp:scoped", "billing"), (None, claims.ROOT)):
        theirs = [slug for slug in NAMED if OWNERS[slug] == name]
        assert mine(repo, me) == theirs
        if me:
            told = repo.merge(me=me)
            assert [line.split()[2] for line in told] == theirs


def mine(repo, me):
    """The briefs `jmerge --home <me>` does not leave to another home, whatever the switch holds.
    jbus's own run, with no `--home`, judges every home's."""
    asking = cli.Repo(repo.main, repo.state, me, False, user=jsettings.DEFAULTS)
    return [slug for slug in NAMED if not asking.others(NAMED[slug])]


def test_a_brief_has_one_home_whoever_asks(repo):
    """For a thread that is no home now, `jmerge --home` leaves every brief to another home,
    including a brief that names the thread. Such a thread has an id that is in no `home-id`, or
    it handed off and has a `Was home:` id."""
    scope = repo.state / "billing"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:scoped\n")
    (scope / "handoff.md").write_text("# handoff\nWas home: mcp:scoped-before\n")
    (repo.state / "handoff.md").write_text("# handoff\nWas home: mcp:root-before\n")
    for asker in ("mcp:nobody", "mcp:root-before", "mcp:scoped-before", "billing"):
        assert mine(repo, asker) == []
    homes = cli.Repo(repo.main, repo.state, None, False, user=jsettings.DEFAULTS).homes.known
    owners = {slug: claims.of_brief(slug, NAMED[slug], {}, homes).home for slug in NAMED}
    assert owners == OWNERS
    (repo.state / "home-id").unlink()
    homes = cli.Repo(repo.main, repo.state, None, False, user=jsettings.DEFAULTS).homes.known
    assert {slug: claims.of_brief(slug, NAMED[slug], {}, homes).home for slug in NAMED} == OWNERS
    roots = [slug for slug in NAMED if OWNERS[slug] == claims.ROOT]
    assert mine(repo, None) == roots
    assert mine(repo, "mcp:nobody") == roots
    assert mine(repo, "mcp:scoped") == [slug for slug in NAMED if OWNERS[slug] == "billing"]
    assert mine(repo, "mcp:scoped-before") == []


def test_an_id_in_two_home_id_files_asks_as_the_home_its_briefs_are(repo):
    for scope in ("billing", "reports"):
        (repo.state / scope).mkdir()
        (repo.state / scope / "home-id").write_text("mcp:scoped\n")
    asking = cli.Repo(repo.main, repo.state, "mcp:scoped", False, user=jsettings.DEFAULTS)
    assert asking.homes.known["mcp:scoped"] == asking.asking == "reports"
    assert mine(repo, "mcp:scoped") == ["scoped", "no-scope"]


def test_a_github_that_cannot_be_asked_is_said_and_no_line_is_read(repo):
    repo.log(HOLD)
    (repo.stub / "open").unlink()
    assert repo.merge() == ["wait: could not ask GitHub"]
    assert repo.calls() == []
