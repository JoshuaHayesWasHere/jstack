"""The repo standard's guards run on a repo that is not jstack, from its `.repo-standard.yml` alone.

Each test builds a small git repo in a temporary folder: two features, a core schema, a Makefile, a
README and a generator, with a config that names them. Every guard passes there, and each fails
on a fault planted in it. The guards run through `repo_standard.cli.main`, the entry point
`python -m repo_standard` calls, and one test runs that command itself from outside jstack.

The guards are `repo_standard.borders`, `repo_standard.stale`, `repo_standard.docs_true` and
`repo_standard.size`, which reads comments with `repo_standard.lexers`. Each reads the repo through
`repo_standard.tree` and its config through `repo_standard.config`.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from repo_standard import config as config_module
from repo_standard import schema
from repo_standard.cli import main
from testing.paths import REPO

SOURCE = REPO / "features" / "repo-standard" / "src"
CORE = REPO / "schemas" / "feature.core.schema.json"
CONFIG = """\
standard: 1   # the version the repo pins
features: features
manifest-schema: schemas/feature.core.schema.json
layout: [features/, schemas/, scripts/]
owners:
  INFRA:
    - Makefile
    - .repo-standard.yml
    - README.md
    - INDEX.md
    - "schemas/**"
    - scripts/gen.py
generators:
  - [{python}, scripts/gen.py]
docs:
  pages: ["*.md", "features/*/docs/**/*.md"]
  exclude: [I?DEX.md]
  roots: [features, scripts, schemas]
  elsewhere:
    scripts/deploy: another repo's deploy command
size:
  - files: ["features/*/src/**"]
    exclude: ["features/*/src/fixtures/**"]
    cap: 10
    over:
      features/beta/src/long.sh: 12
comments:
  files: ["features/*/src/**", "scripts/*.py"]
  exclude: ["features/*/src/fixtures/**"]
  readers:
    .go: script
  allow: ["# type:"]
  links: [.go]
"""
GENERATOR = '''\
"""Write INDEX.md, the list of the features, or with --check say whether it is current."""
import sys
from pathlib import Path

names = sorted(p.parent.name for p in Path("features").glob("*/feature.json"))
text = "".join(f"- {name}\\n" for name in names)
if "--check" in sys.argv:
    current = Path("INDEX.md").read_text() == text
    print("INDEX.md is current" if current else "INDEX.md is stale")
    sys.exit(0 if current else 1)
Path("INDEX.md").write_text(text)
'''


def git(root, *args):
    command = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args]
    subprocess.run(command, check=True, capture_output=True)


def write(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(
            textwrap.dedent(text) if isinstance(text, str) else json.dumps(text)
        )


def manifest(name):
    return {"$schema": "../../schemas/feature.core.schema.json", "name": name, "description": "x."}


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "other"
    write(
        root,
        {
            ".repo-standard.yml": CONFIG.replace("{python}", json.dumps(sys.executable)),
            "schemas/feature.core.schema.json": CORE.read_text(),
            "scripts/gen.py": GENERATOR,
            "Makefile": "lint:\n\tpython3 scripts/gen.py --check\ntest check: lint\n\ttrue\n",
            "README.md": """\
                # other

                Run `make lint`, or `make test TESTS=a` for one.
                The index is written by scripts/gen.py.
                Alpha's page is features/alpha/docs/a.md.
                A feature lives in features/<name>/, its pages are features/alpha/docs/*.md.
                Not here: /tmp/scripts/x, and scripts/deploy, which another repo has.

                ```sh
                make check
                make -C elsewhere build
                ```
                """,
            "features/alpha/feature.json": manifest("alpha"),
            "features/alpha/docs/a.md": "See schemas/feature.core.schema.json.\n",
            "features/alpha/src/alpha.py": "#!/usr/bin/env python3\nx = '# no'  # type: int\n",
            "features/alpha/src/main.go": "package a // https://go.dev/ref/spec\n",
            "features/alpha/src/fixtures/made.py": "# a fixture may say anything\n" * 20,
            "features/beta/feature.json": manifest("beta"),
            "features/beta/src/long.sh": "#!/bin/sh\n" + "echo '#1'\n" * 11,
        },
    )
    git(root, "init", "-q", "-b", "main")
    subprocess.run([sys.executable, "scripts/gen.py"], cwd=root, check=True)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    return root


def warned(lines):
    """Each warning as `<file>: <why>`, once each line is one GitHub reads as a warning."""
    prefix = "::warning file="
    assert all(line.startswith(prefix) for line in lines)
    return [line[len(prefix) :].replace("::", ": ", 1) for line in lines]


def run(root, *args, capsys):
    code = main([*args, "--root", str(root)])
    out = capsys.readouterr()
    return code, out.out.splitlines(), out.err


@pytest.mark.parametrize("guard", ["borders", "stale", "docs", "size", "comments"])
def test_each_guard_passes_on_a_repo_that_holds_to_its_config(repo, capsys, guard):
    hard = ["--hard"] if guard == "borders" else []
    assert run(repo, guard, *hard, capsys=capsys)[:2] == (0, [])


def test_the_command_runs_from_outside_jstack_and_fails_on_a_planted_fault(repo):
    (repo / "notes.txt").write_text("a stray file\n")
    env = {**os.environ, "PYTHONPATH": str(SOURCE)}
    command = [sys.executable, "-m", "repo_standard", "borders", "--hard"]
    ran = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True)
    assert ran.returncode == 1
    assert "::warning file=notes.txt::no owner" in ran.stdout


def test_borders_reads_the_layout_and_owners_from_the_config_and_the_manifests(repo, capsys):
    write(
        repo,
        {
            "notes.txt": "a stray file\n",
            "docs/page.md": "a folder outside the layout\n",
            "features/gamma/x.py": "x = 1\n",
            "features/delta/feature.json": manifest("epsilon"),
            "features/zeta/feature.json": {**manifest("zeta"), "owns": ["api/**"]},
            "features/eta/feature.json": "{not json",
            "features/stray.md": "no feature's\n",
        },
    )
    text = (repo / ".repo-standard.yml").read_text()
    (repo / ".repo-standard.yml").write_text(
        text.replace("- Makefile", "- Makefile\n    - features/alpha/**")
    )
    code, lines, _ = run(repo, "borders", "--hard", capsys=capsys)
    assert code == 1
    outside = "outside features/, schemas/, scripts/ and the repo's own paths"
    twice = "owned twice, by alpha, INFRA"
    assert warned(lines) == [
        f"docs/page.md: a file under docs/, {outside}",
        "docs/page.md: no owner",
        f"features/alpha/docs/a.md: {twice}",
        f"features/alpha/feature.json: {twice}",
        f"features/alpha/src/alpha.py: {twice}",
        f"features/alpha/src/fixtures/made.py: {twice}",
        f"features/alpha/src/main.go: {twice}",
        "features/delta/feature.json: /name: names 'epsilon', not its folder 'delta'",
        "features/eta/feature.json: is not JSON, at line 1, column 2",
        "features/gamma: has no feature.json",
        "features/stray.md: no owner",
        "features/zeta/feature.json: /: has owns, which the schema does not allow",
        f"notes.txt: a file at the root, {outside}",
        "notes.txt: no owner",
    ]
    assert run(repo, "borders", capsys=capsys)[0] == 0


def test_borders_fails_a_diff_across_two_features_unless_it_is_labelled(repo, capsys):
    git(repo, "checkout", "-q", "-b", "change")
    write(repo, {"features/alpha/src/b.py": "y = 2\n", "features/beta/src/c.sh": "true\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "both")
    code, lines, _ = run(repo, "borders", "--hard", "--base", "main", capsys=capsys)
    assert code == 1
    assert warned(lines) == [
        "features/alpha/src/b.py: the diff touches 2 features, alpha, beta: "
        "split it, or label it cross-cutting"
    ]
    labelled = run(
        repo, "borders", "--hard", "--base", "main", "--labels", "a,cross-cutting", capsys=capsys
    )
    assert labelled[:2] == (0, [])
    assert run(repo, "borders", "--base", "nowhere", capsys=capsys)[0] == 2


def test_stale_runs_each_generator_with_check_and_fails_on_stale_output(repo, capsys):
    write(repo, {"features/gamma/feature.json": manifest("gamma")})
    code, lines, _ = run(repo, "stale", capsys=capsys)
    assert code == 1
    assert (
        lines[0]
        == f"scripts/gen.py: `{sys.executable} scripts/gen.py --check` exits 1: its output is stale"
    )
    assert lines[1:] == ["INDEX.md is stale"]
    text = (repo / ".repo-standard.yml").read_text()
    (repo / ".repo-standard.yml").write_text(
        text.replace("  - [", "  - [no-such-generator]\n  - [")
    )
    code, lines, _ = run(repo, "stale", capsys=capsys)
    assert (
        lines[0]
        == "no-such-generator: `no-such-generator --check` cannot run: No such file or directory"
    )


def test_docs_fails_a_page_that_names_a_path_or_a_make_target_the_tree_lacks(repo, capsys):
    write(
        repo,
        {
            "features/alpha/docs/b.md": """\
                Run scripts/missing.sh, then `make deploy`.
                The log says `make lint: test` and `make check BASE=$(git merge-base a HEAD)`.
                The folders features/beta/ and features/beta/src exist.

                ~~~
                make lint release
                ~~~
                """
        },
    )
    code, lines, _ = run(repo, "docs", capsys=capsys)
    assert (code, lines) == (
        1,
        [
            "features/alpha/docs/b.md:1: names scripts/missing.sh, which the tree lacks",
            "features/alpha/docs/b.md:1: runs make deploy, which the Makefile lacks",
            "features/alpha/docs/b.md:6: runs make release, which the Makefile lacks",
        ],
    )
    (repo / "Makefile").unlink()
    code, lines, _ = run(repo, "docs", capsys=capsys)
    assert "README.md:3: runs make lint, with no Makefile" in lines


def test_docs_reads_the_targets_of_the_make_files_the_makefile_includes(repo, capsys):
    """An included make file's targets count, an include back is read once, and one with a
    variable in its path is not read."""
    makefile = repo / "Makefile"
    makefile.write_text(f"include scripts/stack.mk $(EXTRA).mk\n{makefile.read_text()}")
    write(
        repo,
        {
            "scripts/stack.mk": "-include Makefile\ndeploy:\n\ttrue\n",
            "features/alpha/docs/b.md": "Run `make deploy`, then `make release`.\n",
        },
    )
    code, lines, _ = run(repo, "docs", capsys=capsys)
    assert (code, lines) == (
        1,
        ["features/alpha/docs/b.md:1: runs make release, which the Makefile lacks"],
    )


def test_size_reads_its_caps_and_globs_from_the_config(repo, capsys):
    write(
        repo,
        {
            "features/alpha/src/grown.ts": "x;\n" * 11,
            "features/beta/src/long.sh": "true\n" * 10,
            "features/alpha/src/fixtures/long.py": "x = 1\n" * 50,
        },
    )
    code, lines, _ = run(repo, "size", capsys=capsys)
    assert (code, lines) == (
        1,
        [
            "features/alpha/src/grown.ts: has 11 lines, over 10: split it",
            "features/beta/src/long.sh: has 10 lines, under 10: take it off `over`",
        ],
    )
    (repo / "features/beta/src/long.sh").unlink()
    assert (
        run(repo, "size", capsys=capsys)[1][-1]
        == "features/beta/src/long.sh: is gone: take it off `over`"
    )


def test_comments_read_each_language_by_its_extension(repo, capsys):
    write(
        repo,
        {
            "features/alpha/src/why.py": "x = 1  # why\n",
            "features/alpha/src/why.go": "package a\n/* why */\nvar re = 1 // https://go.dev\n",
            "features/alpha/src/page.html": "<script>\nlet a = /b/; // why\n</script>\n",
            "features/beta/src/run.sh": '#!/bin/sh\necho \\# "#1" # why\n',
            "features/alpha/src/tricky.js": "say('a\\'b // no', `t\n// no`);\n"
            "var r = /[/]\\//g; // why\nvar u = /open\n",
            "features/beta/src/unit.service": "[Unit]\n; why\n",
            "features/beta/src/list.yml": "a: 1 # why\n",
        },
    )
    code, lines, _ = run(repo, "comments", capsys=capsys)
    assert (code, lines) == (
        1,
        [
            "features/alpha/src/page.html:2: a plain comment: // why",
            "features/alpha/src/tricky.js:3: a plain comment: // why",
            "features/alpha/src/why.go:2: a plain comment: /* why */",
            "features/alpha/src/why.py:1: a plain comment: # why",
            "features/beta/src/list.yml:1: a plain comment: # why",
            "features/beta/src/run.sh:2: a plain comment: # why",
            "features/beta/src/unit.service:2: a plain comment: ; why",
        ],
    )
    write(repo, {"features/beta/src/lib.rs": "fn a() {}\n"})
    code, _, err = run(repo, "comments", capsys=capsys)
    assert code == 2
    assert "features/beta/src/lib.rs: no comment reader for .rs: map it" in err


def test_a_hash_list_reads_a_line_that_starts_with_a_hash(repo, capsys):
    text = (repo / ".repo-standard.yml").read_text()
    (repo / ".repo-standard.yml").write_text(
        text.replace(".go: script", ".go: script\n    .txt: hash")
    )
    write(repo, {"features/beta/src/paths.txt": "a/\n  # why\nb#c\n"})
    assert run(repo, "comments", capsys=capsys)[1] == [
        "features/beta/src/paths.txt:2: a plain comment: # why"
    ]


def test_yaml_and_toml_open_a_quote_only_where_a_value_or_key_starts(repo, capsys):
    write(
        repo,
        {
            "features/beta/src/apostrophe.yml": "name: don't\nurl: 'a # no'\nb: x#y\n# why\n",
            "features/beta/src/quoted.yaml": "- 'it''s # no'\n- [\"#\", '#'] # why\n",
            "features/beta/src/table.toml": 'k = "it\'s # no"\nv = [\'a\', "#"] # why\n',
            "features/beta/src/triple.toml": "t = '''a # no\n'''\n# why\nu = 'open # no\n",
            "features/beta/src/escaped.yml": "a: '''x'\n# why\n",
        },
    )
    assert run(repo, "comments", capsys=capsys)[1] == [
        "features/beta/src/apostrophe.yml:4: a plain comment: # why",
        "features/beta/src/escaped.yml:2: a plain comment: # why",
        "features/beta/src/quoted.yaml:2: a plain comment: # why",
        "features/beta/src/table.toml:2: a plain comment: # why",
        "features/beta/src/triple.toml:3: a plain comment: # why",
    ]


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (lambda t: t + "colour: red\n", "the top has colour, which the standard does not know"),
        (lambda t: t.replace("  pages:", "\tpages:"), "indents with a tab"),
        (lambda t: t.split("docs:")[0], "has no `docs` part"),
        (
            lambda t: t.replace("cap: 10", "cap: ten"),
            "size[0].cap is not a positive number of lines",
        ),
        (lambda t: t.replace(".go: script", ".go: cobol"), "comments.readers names cobol"),
        (
            lambda t: t.replace("features: features", "features: &a features"),
            "a value the subset does not read",
        ),
        (lambda t: t.replace("layout: [", "layout: features/ #["), "layout is not a list of"),
        (lambda t: t.replace("long.sh: 12", "long.sh: twelve"), "size[0].over is not a map of int"),
    ],
)
def test_a_config_the_guards_cannot_read_is_refused(repo, capsys, change, said):
    path = repo / ".repo-standard.yml"
    path.write_text(change(path.read_text()))
    code, lines, err = run(repo, "docs", capsys=capsys)
    assert (code, lines) == (2, [])
    assert said in err


@pytest.mark.parametrize(
    ("text", "keys"),
    [
        (
            "a: 'it''s'\nb: \"x: y\"\nc: [1, 'p, q', true]\nd: []\n",
            {"a": "it's", "b": "x: y", "c": [1, "p, q", True], "d": []},
        ),
        (
            "a:\n- x\n- y\nb:\n  - k: 1\n    l: [m]\n  - https://x\n",
            {"a": ["x", "y"], "b": [{"k": 1, "l": ["m"]}, "https://x"]},
        ),
        ("---\n# only a note\n", {}),
    ],
)
def test_the_config_reads_the_yaml_subset(text, keys):
    assert config_module.parse(text) == keys


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("a: 'open\n", "an unclosed string"),
        ("a: [1, 2\n", "an unclosed list"),
        ("a: [[1]]\n", "a list inside a flow list"),
        ("a: 1\na: 2\n", "a is set twice"),
        ("a:\nb: 1\n", "a has no value"),
        ("a: 1\n  b: 2\n", "indented under a line that holds a value"),
        ("- a\n", "not one map at the top"),
        ("a:\n  -\n", "a list item with nothing on its line"),
        ("just words\n", "not a `key: value` line"),
    ],
)
def test_the_config_refuses_yaml_outside_the_subset(text, said):
    with pytest.raises(config_module.Refused, match=said):
        config_module.parse(text)


@pytest.mark.parametrize(
    ("keys", "said"),
    [
        ({"docs": ["a"]}, "docs is not a map"),
        ({"size": 3}, "size is not a list of rules"),
        ({"generators": 3}, "generators is not a list of commands"),
    ],
)
def test_a_part_of_the_wrong_shape_is_refused(keys, said):
    with pytest.raises(config_module.Refused, match=said):
        config_module.build(keys)


def test_a_missing_config_or_checkout_is_refused(tmp_path, capsys, monkeypatch):
    assert run(tmp_path, "size", capsys=capsys)[0] == 2
    monkeypatch.chdir(tmp_path)
    assert main(["size"]) == 2
    assert "not in a git checkout" in capsys.readouterr().err
    write(tmp_path, {".repo-standard.yml": "size: []\n"})
    code, _, err = run(tmp_path, "size", capsys=capsys)
    assert code == 2
    assert "git cannot list" in err


def test_a_repo_that_sets_up_one_guard_runs_it_from_its_own_checkout(repo, capsys, monkeypatch):
    write(repo, {".repo-standard.yml": "docs:\n  pages: [README.md]\n  roots: [features]\n"})
    monkeypatch.chdir(repo / "features")
    assert main(["docs"]) == 0
    assert main(["size"]) == 2
    assert "has no `size` part" in capsys.readouterr().err


def test_the_manifest_schema_reads_an_extension_by_ref_and_refuses_what_it_cannot_read(tmp_path):
    (tmp_path / "core.json").write_text(CORE.read_text())
    extension = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"$ref": "core.json#/properties/name"},
            "kind": {"enum": ["a", "b"]},
            "on": {"const": True},
            "weight": {"type": ["number", "null"]},
            "tags": {"type": "array", "items": {"type": "string", "minLength": 2}},
            "extra": {"type": "object", "additionalProperties": {"type": "integer"}},
        },
    }
    (tmp_path / "ext.json").write_text(json.dumps(extension))
    rules = schema.load(tmp_path / "ext.json")
    assert (
        schema.validate(
            {"name": "a-b", "kind": "a", "on": True, "weight": None, "extra": {"n": 1}}, rules
        )
        == []
    )
    assert schema.validate(
        {
            "name": "x" * 65 + "-",
            "kind": "c",
            "on": 1,
            "weight": "1",
            "tags": ["x", 1],
            "extra": {"n": "1"},
        },
        rules,
    ) == [
        "/name: is longer than 64",
        "/name: does not match ^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
        '/kind: is not one of ["a", "b"]',
        "/on: is not true",
        "/weight: is not of type number or null",
        "/tags/0: is shorter than 2",
        "/tags/1: is not of type string",
        "/extra/n: is not of type integer",
    ]
    (tmp_path / "bad.json").write_text(json.dumps({"allOf": []}))
    with pytest.raises(schema.Unsupported, match="allOf"):
        schema.load(tmp_path / "bad.json")
    (tmp_path / "lost.json").write_text(json.dumps({"$ref": "core.json#/nowhere"}))
    with pytest.raises(schema.Unsupported, match="names nothing"):
        schema.load(tmp_path / "lost.json")


def test_a_manifest_schema_the_guard_cannot_read_is_refused(repo, capsys):
    (repo / "schemas/feature.core.schema.json").write_text("{")
    code, _, err = run(repo, "borders", capsys=capsys)
    assert code == 2
    assert "cannot read the manifest schema" in err
