"""A merge that changes the package list of pyproject.toml reinstalls, once, the tool that uv
has as an editable install of the main checkout, and says so on its `merged` line. The tests
run `jmerge` as `tests/test_home_merge.py` runs it, against its fake `gh` and a temporary
origin."""

import json
import shlex
import shutil

import pytest

from jinstall import layout
from jinstall.harnesses import HARNESSES
from test_home_merge import brief, git, merged_line, review

FAKE_UV = """\
#!/bin/sh
case "$1 $2" in
"tool install" | "sync ")
    echo "$*" >> "$STUB/uv-calls"
    [ ! -f "$STUB/uv-fails" ] || { cat "$STUB/uv-fails" >&2; exit 2; } ;;
*) exec REAL "$@" ;;
esac
"""
LISTED = '[project]\nname = "demo-tool"\n\n[tool.hatch.build.targets.wheel]\npackages = {}\n'


class Tooled:
    """A merged pull request whose checkout is a Python project, `demo-tool`, that uv has as an
    editable tool of this checkout. Its main lists the package `src/a`, and the pull
    request's head lists `moved`. A `uv` in front of the real one records each
    `uv tool install` and `uv sync` it is asked for, and runs neither."""

    def __init__(self, merged, tmp_path, monkeypatch, moved):
        self.merged, self.stub = merged, merged.home.stub
        main, tree = merged.home.main, merged.tree
        (self.stub / "uv").write_text(FAKE_UV.replace("REAL", shutil.which("uv")))
        (self.stub / "uv").chmod(0o755)
        (main / "pyproject.toml").write_text(LISTED.format('["src/a"]'))
        git(main, "add", "pyproject.toml")
        git(main, "commit", "-q", "-m", "a project")
        git(main, "push", "-q", "origin", "main")
        git(tree, "rebase", "-q", "origin/main")
        (tree / "pyproject.toml").write_text(LISTED.format(json.dumps(moved)))
        git(tree, "commit", "-q", "--allow-empty", "-am", "the move")
        git(tree, "push", "-q", "-f", "origin", "alpha")
        merged.head = git(tree, "rev-parse", "HEAD")
        (merged.home.tasks / "alpha.md").write_text(brief(review("clean", merged.head)))
        merged.home.open_pull_request(merged.head)
        tools = tmp_path / "uv-tools"
        record = tools / "demo-tool" / "lib" / "python3" / "site-packages"
        record = record / "demo_tool-0.1.0.dist-info" / "direct_url.json"
        record.parent.mkdir(parents=True)
        url = {"url": f"file://{main}", "dir_info": {"editable": True}}
        record.write_text(json.dumps(url))
        monkeypatch.setenv("UV_TOOL_DIR", str(tools))

    def calls(self):
        path = self.stub / "uv-calls"
        return path.read_text().splitlines() if path.exists() else []


REINSTALLED = "reinstalled the tool demo-tool from {}: its package list changed"


def test_a_merge_that_moves_a_package_reinstalls_the_tool_once(merged, tmp_path, monkeypatch):
    tooled = Tooled(merged, tmp_path, monkeypatch, ["features/a/src/a"])
    said = merged.run()
    commit, pulled = merged.on_main()
    assert pulled == commit
    main = merged.home.main
    assert said == [merged_line(commit, REINSTALLED.format(main))]
    assert tooled.calls() == [f"tool install --editable {main} --reinstall", "sync"]


def test_a_merge_that_leaves_the_package_list_reinstalls_nothing(merged, tmp_path, monkeypatch):
    tooled = Tooled(merged, tmp_path, monkeypatch, ["src/a"])
    said = merged.run()
    assert said == [merged_line(merged.on_main()[0])]
    assert tooled.calls() == []


def test_a_reinstall_that_fails_is_said_on_the_merged_line(merged, tmp_path, monkeypatch):
    tooled = Tooled(merged, tmp_path, monkeypatch, ["features/a/src/a"])
    (tooled.stub / "uv-fails").write_text("error: no network\n")
    main = merged.home.main
    said = merged.run()
    not_done = (
        "the tool demo-tool was not reinstalled after its package list changed "
        f"(uv tool install --editable {shlex.quote(str(main))} --reinstall: error: no network)"
    )
    assert said == [merged_line(merged.on_main()[0], not_done)]
    assert tooled.calls() == [f"tool install --editable {main} --reinstall"]


INSTALL = """\
#!/bin/sh
echo "$*" >> "$STUB/install-calls"
[ ! -f "$STUB/install-fails" ] || { cat "$STUB/install-fails"; exit 1; }
"""
CATALOG = '{{"items": [{{"name": "demo", "kind": "skill", "path": "{}/demo/SKILL.md"}}]}}\n'
PLUGIN = '{"repository": "https://github.com/someone/demo"}\n'
LINKED = "[the install](../../install.sh)\n"


class Skilled:
    """A merged pull request whose checkout is the jstack checkout that the machine's install
    was made from. The `source` of the Claude Code layout links to it, and the layout is what
    the install assembles from main, except with `stale`, which leaves out the skill's
    `SKILL.md`. Its main has the skill `demo` at `skills/demo/`, and an `install.sh` that
    records each run and changes nothing. With `moved`, the pull request's head moves the
    skill to `features/demo/` and changes `skills.json` as the generator would. To each
    path of `touched` it writes a line, `more` or the text it gives, in a file it adds or one
    it changes."""

    def __init__(self, merged, moved=False, touched=(), stale=False):
        self.merged, self.stub = merged, merged.home.stub
        main, tree = merged.home.main, merged.tree
        (main / "install.sh").write_text(INSTALL)
        (main / "skills.json").write_text(CATALOG.format("skills"))
        (main / "plugin.json").write_text(PLUGIN)
        (main / "skills" / "demo").mkdir(parents=True)
        (main / "skills" / "demo" / "SKILL.md").write_text("# demo\n")
        git(main, "add", "install.sh", "skills.json", "plugin.json", "skills")
        git(main, "commit", "-q", "-m", "a skill")
        git(main, "push", "-q", "origin", "main")
        git(tree, "rebase", "-q", "origin/main")
        if moved:
            (tree / "features").mkdir()
            git(tree, "mv", "skills/demo", "features/demo")
            (tree / "skills.json").write_text(CATALOG.format("features"))
        for path in touched:
            path, text = path if isinstance(path, tuple) else (path, "more\n")
            (tree / path).parent.mkdir(parents=True, exist_ok=True)
            with (tree / path).open("a") as written:
                written.write(text)
            git(tree, "add", path)
        git(tree, "commit", "-q", "--allow-empty", "-am", "the change")
        git(tree, "push", "-q", "-f", "origin", "alpha")
        merged.head = git(tree, "rev-parse", "HEAD")
        (merged.home.tasks / "alpha.md").write_text(brief(review("clean", merged.head)))
        merged.home.open_pull_request(merged.head)
        self.layout = merged.home.user / ".local" / "share" / "jstack" / "harness" / "claude-code"
        for path, entry in layout.assemble(main, HARNESSES[0]).entries.items():
            if stale and path == "skills/demo/SKILL.md":
                continue
            (self.layout / path).parent.mkdir(parents=True, exist_ok=True)
            if isinstance(entry, layout.Linked):
                (self.layout / path).symlink_to(entry.source)
            else:
                (self.layout / path).write_bytes(entry.content)

    def calls(self):
        path = self.stub / "install-calls"
        return path.read_text().splitlines() if path.exists() else []


INSTALLED = "ran the install again in {}: the merge changed what it assembles"


def test_a_merge_that_moves_a_skill_runs_the_install_once(merged, monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    skilled = Skilled(merged, moved=True)
    said = merged.run()
    commit, pulled = merged.on_main()
    assert pulled == commit
    assert said == [merged_line(commit, INSTALLED.format(merged.home.main))]
    assert skilled.calls() == [""]


@pytest.mark.parametrize(
    "touched",
    ["skills/demo/notes.md", ("skills/demo/SKILL.md", LINKED), "skills.json"],
    ids=["a file added to a skill", "a link the layout rewrites", "a catalog it cannot read"],
)
def test_a_merge_that_changes_what_the_install_makes_runs_it_once(merged, monkeypatch, touched):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    skilled = Skilled(merged, touched=[touched])
    said = merged.run()
    assert said == [merged_line(merged.on_main()[0], INSTALLED.format(merged.home.main))]
    assert skilled.calls() == [""]


@pytest.mark.parametrize(
    "touched",
    [
        (),
        ("src/demo/a.py",),
        ("skills/demo/tests/test_a.py",),
        ("skills/demo/.notes",),
        ("skills/demo/SKILL.md",),
    ],
    ids=[
        "nothing else",
        "code outside every skill",
        "a skill's tests",
        "a hidden file",
        "an edit the link makes live",
    ],
)
def test_a_merge_that_leaves_the_layout_as_it_is_runs_nothing(merged, monkeypatch, touched):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    skilled = Skilled(merged, touched=touched)
    said = merged.run()
    assert said == [merged_line(merged.on_main()[0])]
    assert skilled.calls() == []


def test_a_layout_an_earlier_install_left_stale_is_installed_after_any_merge(merged, monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    skilled = Skilled(merged, stale=True)
    said = merged.run()
    assert said == [merged_line(merged.on_main()[0], INSTALLED.format(merged.home.main))]
    assert skilled.calls() == [""]


def test_a_machine_installed_from_elsewhere_is_not_installed_from_this_checkout(
    merged, tmp_path, monkeypatch
):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    skilled = Skilled(merged, moved=True)
    (skilled.layout / "source").unlink()
    (skilled.layout / "source").symlink_to(tmp_path)
    said = merged.run()
    assert said == [merged_line(merged.on_main()[0])]
    assert skilled.calls() == []


def test_an_install_that_fails_is_said_on_the_merged_line(merged, monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    skilled = Skilled(merged, moved=True)
    (skilled.stub / "install-fails").write_text(
        "ok hard layout claude-code /x\nold hard layout codex /y -> stale: skills/demo/SKILL.md\n"
    )
    said = merged.run()
    not_done = (
        "the install was not run again after the merge changed what it assembles "
        "(sh install.sh: old hard layout codex /y -> stale: skills/demo/SKILL.md)"
    )
    assert said == [merged_line(merged.on_main()[0], not_done)]
    assert skilled.calls() == [""]
