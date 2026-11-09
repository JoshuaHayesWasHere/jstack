"""The root home owns no row: a brief no scope claims is the `uncategorized` home's.

`uncategorized` is the catch-all scope. A brief with no `Home:` line, `Home: root`, a root id, a
name that is no scope, or a scope whose plan `/handoff` archived, belongs to it, made or not. A
scope is a directory with a `plan.md` (what the home skill makes and `/home <scope>` starts),
whether or not it has ids (`home-id`, `Was home:`) yet, so one whose plan is archived is none.
The catch-all is named without a read of the root's ids or of any scope, and a brief that
names a scope still finds it.
"""

import pathlib

import pytest

from jbriefs import home

ROOT_ID = "mcp:root-thread"


def brief(line: str = "") -> str:
    return f"# a-row: a task\nTask: a task\n{line}\n## Result\nHome: cicd\n"


@pytest.fixture
def state(tmp_path):
    (tmp_path / "home-id").write_text(f"{ROOT_ID}\n")
    (tmp_path / "cicd").mkdir()
    (tmp_path / "cicd" / "home-id").write_text("mcp:cicd-thread\n")
    (tmp_path / "cicd" / "plan.md").write_text("# plan\n")
    (tmp_path / "duet").mkdir()
    (tmp_path / "duet" / "plan-archived.md").write_text("# plan\n")
    (tmp_path / "duet" / "handoff.md").write_text("Was home: mcp:duet-thread\n")
    return tmp_path


@pytest.mark.parametrize(
    "line",
    [
        "",
        "Home: root",
        f"Home: {ROOT_ID}",
        "Home: docs",
        "Home: duet",
        "Home: mcp:duet-thread",
        "Home: uncategorized",
    ],
    ids=["no line", "root", "root id", "unknown scope", "archived scope", "archived id", "named"],
)
def test_a_brief_no_scope_claims_is_the_uncategorized_home_s(state, line):
    assert home.home_of(state, brief(line)) == state / "uncategorized"


def test_a_brief_of_a_live_scope_stays_that_scope_s(state):
    assert home.home_of(state, brief("Home: cicd")) == state / "cicd"
    assert home.home_of(state, brief("Home: mcp:cicd-thread")) == state / "cicd"


def test_uncategorized_is_the_home_of_its_briefs_made_started_or_neither(state):
    catchall = state / "uncategorized"
    assert home.home_of(state, brief()) == catchall
    catchall.mkdir()
    (catchall / "plan.md").write_text("# plan\n")
    assert home.home_of(state, brief()) == catchall
    assert home.home_of(state, brief("Home: uncategorized")) == catchall
    (catchall / "home-id").write_text("mcp:uncategorized-thread\n")
    assert catchall in [one for one, _, _ in home.scopes(state)]
    assert home.home_of(state, brief("Home: mcp:uncategorized-thread")) == catchall
    assert home.thread_of(home.home_of(state, brief())) == "mcp:uncategorized-thread"


def test_until_its_home_starts_the_catch_all_s_thread_is_the_root_s(state):
    assert home.thread_of(home.home_of(state, brief())) == ROOT_ID
    assert home.thread_of(state / "cicd") == "mcp:cicd-thread"


def test_an_archived_scope_is_no_scope_as_the_home_skill_counts_it(state):
    assert [one.name for one, _, _ in home.scopes(state)] == ["cicd"]
    (state / "duet" / "plan-archived.md").rename(state / "duet" / "plan.md")
    assert [one.name for one, _, _ in home.scopes(state)] == ["cicd", "duet"]
    assert home.home_of(state, brief("Home: duet")) == state / "duet"


@pytest.mark.parametrize("name", ["uncategorized", "cicd"])
def test_uncategorized_and_a_scope_are_names_a_brief_may_be_queued_with(state, name):
    assert home.fault(state, brief(f"Home: {name}"), "demo") == ""


def test_the_root_owns_no_row_so_a_brief_may_not_name_it(state):
    assert home.fault(state, brief("Home: root"), "demo") == (
        "Home: line names root, which owns no row: name uncategorized or the row's scope (cicd)"
    )


def test_a_name_that_is_no_scope_is_refused_and_the_fault_names_uncategorized(state):
    said = home.fault(state, brief("Home: duet"), "demo")
    assert said == (
        "Home: line names duet, which is no home of demo: name uncategorized or the row's scope "
        "(cicd)"
    )


@pytest.fixture
def counted(tmp_path, monkeypatch):
    """A root home with an id and three scopes, and the list of every file read under it."""
    (tmp_path / "home-id").write_text("root-thread\n")
    for name in ("aa", "bb", "cc"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "plan.md").write_text("# plan\n")
        (tmp_path / name / "home-id").write_text(f"{name}-thread\n")
    reads = []
    real = pathlib.Path.read_text

    def read_text(self, *args, **kwargs):
        if self.is_relative_to(tmp_path):
            reads.append(self)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)
    return tmp_path, reads


@pytest.mark.parametrize("line", ["", "Home: root"])
def test_a_brief_that_names_no_scope_is_the_catch_all_s_and_reads_no_home(counted, line):
    root, reads = counted
    assert home.home_of(root, brief(line)) == root / "uncategorized"
    assert reads == []


def test_a_brief_that_names_a_scope_or_its_thread_finds_it(counted):
    root, reads = counted
    assert home.home_of(root, brief("Home: bb")) == root / "bb"
    assert home.home_of(root, brief("Home: cc-thread")) == root / "cc"
    assert home.home_of(root, brief("Home: root-thread")) == root / "uncategorized"
    assert home.home_of(root, brief("Home: nowhere")) == root / "uncategorized"
    assert reads


def test_a_reader_reads_each_home_once_however_many_briefs_it_answers(counted):
    root, reads = counted
    of = home.reader(root)
    assert [of(brief()) for _ in range(5)] == [root / "uncategorized"] * 5
    assert reads == []
    assert [of(brief(f"Home: {name}")) for name in ("aa", "bb", "aa", "cc")] == [
        root / "aa",
        root / "bb",
        root / "aa",
        root / "cc",
    ]
    assert len(reads) == len(set(reads))
