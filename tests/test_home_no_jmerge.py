"""One merger for a repo: jbus runs `jmerge` while `home-thread` is empty or missing, so no
skill step may run it then. Every `sh` block of a skill that runs `jmerge` to merge, land or
sweep is lifted and run, with the blocks its skill says to run first, against a stub `jmerge`
that records its calls."""

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

SKILLS = Path(__file__).parent.parent / "skills"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
RUNS = re.compile(r"\bjmerge(?=[ \t]*(?:$|[;|&)]|-))(?![ \t]+--(?:checks|claims|scope)\b)", re.M)
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
    """Each `sh` block of a skill, with the line it starts on: of the file alone, or with
    `as_read`, of the skill as an agent reads it."""
    text = read(skill)
    return [
        (text.count("\n", 0, found.start(1)) + 1, textwrap.dedent(found.group(1)))
        for found in FENCED.finditer(text)
    ]


def first(skill):
    """The blocks a skill says to run first: the one at its top, the one that finds this
    home, and the one that says who merges, for the skill that has them."""
    found = []
    for mark in (r"^H=", r"^ME=", r"\bmerges="):
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
        """Run blocks in one call, as a home would, each placeholder in quotes filled in."""
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
        """What `jmerge` was run with, a line for each run."""
        try:
            return (self.stub / "calls").read_text().splitlines()
        except FileNotFoundError:
            return []

    def merge(self, *flags, me=ME):
        """The merge step, as the home skill says to run it, with what it says to add to
        its `jmerge` line."""
        (step,) = [text for _, text in blocks(HOME, as_read) if "flags=''" in text]
        (line,) = [line for line in step.splitlines() if line.startswith("flags=")]
        return self.sh(*first(HOME), step.replace(line, f"flags='{' '.join(flags)}'"), me=me)

    def log(self, *lines):
        """`jmerge`, run by jbus, prints these: each is appended to the log, dated, and a
        `wait` or `hold` line is kept as the last one said of its pull request."""
        with (self.state / "merge.log").open("a") as log:
            log.writelines(f"2026-10-12 13:40 {line}\n" for line in lines)
        last = self.state / "merge.log.last"
        kept = json.loads(last.read_text()) if last.exists() else {}
        kept.update({line.split()[1]: line for line in lines if not line.startswith("merged")})
        last.write_text(json.dumps(kept))


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_the_skills_have_blocks_that_run_jmerge():
    assert [param.id.split(":")[0] for param in MERGING] == ["home"] * 2
    assert not RUNS.search('said=$(uv run --project "$T/.." jmerge --claims)')
    assert not RUNS.search("<the lines step 2's jmerge printed in this tick>")
    assert RUNS.search('uv run --project "$T/.." jmerge')


@pytest.mark.parametrize("held", [None, "", " \n"], ids=["missing", "empty", "blank"])
@pytest.mark.parametrize(("skill", "text"), MERGING)
def test_no_block_runs_jmerge_while_jbus_merges(repo, skill, text, held):
    repo.switch(held)
    said = repo.sh(*first(skill), text)
    assert repo.calls() == []
    assert (repo.code, repo.stderr, said[0]) == (0, "", "jbus merges")


@pytest.mark.parametrize(("skill", "text"), MERGING)
def test_each_block_runs_jmerge_once_when_the_switch_holds_an_id(repo, skill, text):
    repo.switch("mcp:some-home\n")
    said = repo.sh(*first(skill), text)
    (call,) = repo.calls()
    assert (repo.code, repo.stderr, said) == (0, "", ["home merges"])
    assert call.split()[0] in ("--home", "--sweep")


@pytest.mark.parametrize(("skill", "text"), MERGING)
def test_a_block_run_without_the_switch_runs_no_jmerge(repo, skill, text):
    repo.switch("mcp:some-home\n")
    top, home, _ = first(skill)
    assert repo.sh(top, home, text) == []
    assert repo.calls() == []
    assert repo.code != 0


def test_a_stack_is_not_landed_while_jbus_merges(repo):
    (repo.stub / "open").write_text("")
    switch = repo.state / "home-thread"
    assert repo.merge("--check", "--land", "demo") == [
        "jbus merges",
        f"not landed: jbus merges here and lands no stack, until {switch} holds an id",
    ]
    assert repo.merge("--check") == ["jbus merges"]
    assert repo.calls() == []
    repo.switch(ME)
    assert repo.merge("--land", "demo") == ["home merges"]
    assert repo.calls() == [f"--home {ME} --land demo"]


MERGED = 'merged 9 beta abc1234 "feat: it", revert: gh pr revert x'


def test_the_merge_step_tells_a_merge_once_and_what_each_open_pull_request_waits_for(repo):
    repo.log(MERGED, WAIT, HOLD)
    assert repo.merge() == ["jbus merges", f"{HOLD}", WAIT]
    repo.log(MERGED.replace("beta", "gamma"))
    assert repo.merge() == ["jbus merges", MERGED.replace("beta", "gamma"), HOLD, WAIT]
    assert repo.merge() == ["jbus merges", HOLD, WAIT]
    (repo.stub / "open").write_text(f"8 {URL}8\n9 {URL}9\n")
    nothing = f"wait 9 {URL}9: jbus has said nothing of it yet"
    assert repo.merge() == ["jbus merges", WAIT, nothing]
    assert repo.calls() == []
    assert (repo.code, repo.stderr) == (0, "")


def test_a_log_shorter_than_the_mark_is_read_from_its_start(repo):
    repo.log(WAIT, WAIT, WAIT)
    repo.merge()
    (repo.state / "merge.log").write_text("")
    repo.log(MERGED)
    (repo.stub / "open").write_text(f"8 {URL}8\n")
    assert repo.merge() == ["jbus merges", MERGED, WAIT]


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
    assert repo.merge(me="mcp:scoped") == ["jbus merges", nothing]
    repo.merge()
    repo.log(mine, MERGED, theirs, WAIT, HOLD)
    (_, *scoped) = repo.merge(me="mcp:scoped")
    assert scoped == [MERGED, theirs, WAIT]
    assert repo.merge() == ["jbus merges", mine, HOLD]
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
    assert repo.merge() == ["jbus merges"]
    assert repo.merge(me="mcp:scoped") == ["jbus merges", HOLD]
    assert (repo.code, repo.stderr) == (0, "")


OWN, THEIRS = MERGED.replace("beta", "gamma"), MERGED.replace("beta", "delta")


def test_a_merge_jbus_logged_before_the_switch_was_set_is_told_once_and_the_homes_own_never(repo):
    (repo.stub / "open").write_text("")
    repo.merge()
    repo.log(MERGED)
    repo.switch(f"{ME}\n")
    (repo.stub / "says").write_text(f"{OWN}\n")
    assert repo.merge() == ["home merges", MERGED, OWN]
    (repo.stub / "says").unlink()
    assert repo.merge() == ["home merges"]
    assert repo.calls() == [f"--home {ME}"] * 2
    repo.switch("")
    assert repo.merge() == ["jbus merges"]
    repo.log(MERGED)
    assert repo.merge() == ["jbus merges", MERGED]


def test_a_merge_another_writer_logged_during_the_homes_run_is_told_once(repo):
    (repo.stub / "open").write_text("")
    repo.switch(f"{ME}\n")
    repo.merge()
    (repo.stub / "says").write_text(f"{OWN}\n")
    (repo.stub / "logs").write_text(f"{THEIRS}\n")
    assert repo.merge() == ["home merges", OWN, THEIRS]
    (repo.stub / "says").unlink()
    (repo.stub / "logs").unlink()
    assert repo.merge() == ["home merges"]


@pytest.mark.parametrize("before", [(), (MERGED,)], ids=["no log", "a log"])
def test_a_merge_step_cut_short_inside_jmerge_tells_each_line_once(repo, before):
    (repo.stub / "open").write_text("")
    repo.merge()
    repo.log(*before)
    repo.switch(f"{ME}\n")
    (repo.stub / "says").write_text(f"{OWN}\n")
    (repo.stub / "logs").write_text(f"{THEIRS}\n")
    (repo.stub / "ends").write_text("killed\n")
    assert repo.merge() == ["home merges", *before]
    assert repo.code == -9
    for name in ("says", "logs", "ends"):
        (repo.stub / name).unlink()
    assert repo.merge() == ["home merges", OWN, THEIRS]
    assert repo.merge() == ["home merges"]
    assert repo.code == 0


PLAYBOOKS = SKILLS.parent / "playbooks"
LANDING = re.compile(r"`(flags='[^'`]*--land <name>')`")


@pytest.mark.parametrize(
    ("playbook", "asked"),
    [
        ("autopilot-stack", ["--check --land demo"]),
        ("shipping", ["--check --land demo", "--land demo"]),
    ],
)
def test_a_playbooks_landing_is_the_merge_step_with_its_flags_line(repo, playbook, asked):
    """The `flags=` lines a playbook gives are put in place of the merge step's own, as it
    says, and the step is run: they reach its one `jmerge` line, and no other block runs."""
    given = LANDING.findall((PLAYBOOKS / f"{playbook}.md").read_text())
    assert [line.replace("<name>", "demo") for line in given] == [f"flags='{a}'" for a in asked]
    (step,) = [text for _, text in blocks(HOME, as_read) if "flags=''" in text]
    (own,) = [line for line in step.splitlines() if line.startswith("flags=")]
    repo.switch(ME)
    for line in given:
        assert repo.sh(*first(HOME), step.replace(own, line.replace("<name>", "demo"))) == [
            "home merges"
        ]
    assert repo.calls() == [f"--home {ME} {a}" for a in asked]


def test_what_a_landing_merged_is_not_news_to_the_merge_step(repo):
    (repo.stub / "open").write_text("")
    repo.merge()
    repo.log(MERGED)
    repo.switch(f"{ME}\n")
    (repo.stub / "says").write_text(f"{OWN}\n")
    assert repo.merge("--land", "demo") == ["home merges", MERGED, OWN]
    (repo.stub / "says").unlink()
    assert repo.merge() == ["home merges"]
    assert repo.calls() == [f"--home {ME} --land demo", f"--home {ME}"]


def test_a_sweep_joined_after_the_merge_step_still_runs(repo):
    (step,) = [text for _, text in blocks(HOME, as_read) if "flags=''" in text]
    (sweep,) = [text for _, text in blocks(HOME, as_read) if "--sweep" in text]
    repo.switch(f"{ME}\n")
    (repo.stub / "ends").write_text("3\n")
    assert repo.sh(*first(HOME), step, sweep) == ["home merges"]
    assert repo.calls() == [f"--home {ME}", "--sweep"]
    assert repo.merge() == ["home merges"]
    assert repo.code == 3


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
    assert repo.merge() == ["jbus merges"]
    assert repo.merge(me="mcp:scoped") == ["jbus merges", HOLD]


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
    """One case, three readers: the skill's `whose`, the `homes` of `jmerge --claims`, and
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
        asking = cli.Repo(repo.main, repo.state, me, False, user=jsettings.DEFAULTS)
        assert [slug for slug in NAMED if not asking.others(NAMED[slug])] == theirs
        if me:
            (_, *told) = repo.merge(me=me)
            assert [line.split()[2] for line in told] == theirs


def mine(repo, me):
    """The briefs `jmerge --home <me>` does not leave to another home."""
    asking = cli.Repo(repo.main, repo.state, me, False, user=jsettings.DEFAULTS)
    return [slug for slug in NAMED if not asking.others(NAMED[slug])]


def test_a_brief_has_one_home_whoever_asks(repo):
    """A thread that is no home now is left every brief, the ones that name it too: one
    whose id is in no `home-id`, and one that handed off, a `Was home:` id."""
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
    assert repo.merge() == ["jbus merges", "wait: could not ask GitHub"]
    assert repo.calls() == []
