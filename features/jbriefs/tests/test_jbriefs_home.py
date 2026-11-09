"""Which home a brief belongs to (`jbriefs.home.home_of`): a brief with no `Home:` line, or one
that names `root`, is the root's without a read of the root's ids or of any scope, and a brief
that names a scope still finds it."""

import pathlib

import pytest

from jbriefs import home


@pytest.fixture
def state(tmp_path, monkeypatch):
    """A root home with an id and three scopes, and the list of every file read under it."""
    (tmp_path / "home-id").write_text("root-thread\n")
    for name in ("aa", "bb", "cc"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "home-id").write_text(f"{name}-thread\n")
    reads = []
    real = pathlib.Path.read_text

    def read_text(self, *args, **kwargs):
        if self.is_relative_to(tmp_path):
            reads.append(self)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)
    return tmp_path, reads


def brief(line=""):
    return f"# x: a task\n{line}\nSize: S\n\n## Result\n"


@pytest.mark.parametrize("line", ["", "Home: root"])
def test_a_brief_that_names_no_scope_is_the_roots_and_reads_no_home(state, line):
    root, reads = state
    assert home.home_of(root, brief(line)) == root
    assert reads == []


def test_a_brief_that_names_a_scope_or_its_thread_finds_it(state):
    root, reads = state
    assert home.home_of(root, brief("Home: bb")) == root / "bb"
    assert home.home_of(root, brief("Home: cc-thread")) == root / "cc"
    assert home.home_of(root, brief("Home: root-thread")) == root
    assert home.home_of(root, brief("Home: nowhere")) == root
    assert reads


def test_a_reader_reads_each_home_once_however_many_briefs_it_answers(state):
    root, reads = state
    of = home.reader(root)
    assert [of(brief()) for _ in range(5)] == [root] * 5
    assert reads == []
    assert [of(brief(f"Home: {name}")) for name in ("aa", "bb", "aa", "cc")] == [
        root / "aa",
        root / "bb",
        root / "aa",
        root / "cc",
    ]
    assert len(reads) == len(set(reads))
