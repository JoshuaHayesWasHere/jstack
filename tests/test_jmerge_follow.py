"""A merge that changes pyproject.toml's package list reinstalls the tool uv has as an editable
install of the main checkout, once, and says so on its `merged` line: run as
`tests/test_home_merge.py` runs `jmerge`, against its fake `gh` and a temporary origin."""

import json
import shlex
import shutil

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
    """A merged pull request whose checkout is a Python project, `demo-tool`, that uv has as
    an editable tool of this checkout; its main lists the package `src/a`, and the pull
    request's head lists `moved`. A `uv` in front of the real one keeps each `uv tool install`
    and `uv sync` it is asked for, and runs neither."""

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
