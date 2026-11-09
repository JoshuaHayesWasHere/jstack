"""A mutant of `scripts/select_tests.py` for each rule of its table: the selector with that one
rule broken in its source must fail a row of test_select_tests_rules.py's table that names the
rule, so the table pins what each rule selects and no row passes on another rule.

Each mutant runs the selector over today's tree in a process of its own, so they sit apart from
the table, which every change runs. They run where a change reaches the selector, whose change
runs every test, or the table's file, whose name this file spells. It loads that file by its
path and does not import it: an import would make every path the table's file reads select
these tests too."""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from testing.paths import REPO

RULES = Path(__file__).with_name("test_select_tests_rules.py")
SPEC = importlib.util.spec_from_file_location("select_tests_rules", RULES)
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)
SCRIPT, TABLE, asked, failing, select = (
    rules.SCRIPT,
    rules.TABLE,
    rules.asked,
    rules.failing,
    rules.select,
)

MUTANTS = {
    "all": ("shared() & set(EVERY_RUN) if strict else shared()", "set()"),
    "plugin": (
        "return {modules()[one] for one in found} | whole | set(EVERYTHING)",
        "return set(EVERYTHING)",
    ),
    "imports": ("testers().get(by_path[path], set())", "test_files([by_path[path]])"),
    "chain": (
        "found.add(one)\n            todo += edges()[one]\n    return frozenset(found)",
        "found.add(one)\n            todo += edges()[one] if one == name else ()\n"
        "    return frozenset(found)",
    ),
    "process": ("if path.startswith(run)}", "if path.startswith(run) and False}"),
    "by-name": ("for loader in itself.union(", "for loader in set().union("),
    "fixture-asked": (" | asking(by_path[path])", ""),
    "conftest": ("reached |= conftests(name) & known.keys()", "reached |= set()"),
    "test-spelled": ('found["names"] |= readers(path)\n', 'found["names"] |= set()\n'),
    "beside": ('found["imports"] |= test_files(importers(users(path)))', "pass"),
    "spelled": ('found["names"] |= readers(one)', "pass"),
    "included": ("for one in {path} | includers(path):", "for one in {path}:"),
    "skill-index": ("for word in reaches(name):", "for word in ():"),
    "fixture": ('found["names"] |= named', "pass"),
    "read-set": ('found["names"] |= globbers(path)', "pass"),
    "tests-line": ('found["features"] |= set(listed_tests)', "pass"),
    "page": ('found["features"] |= feature_tests(name)', "pass"),
    "cross-cutting": (
        'found["cross-cutting"] = set(cross_cutting()) if cross else set()',
        'found["cross-cutting"] = set()',
    ),
    "browser": ("tests if runs(one)}", "tests if (ROOT / one).is_file()}"),
    "models": ("if any(owns(paths, path) for path in changed)", "if False"),
    "models-only": ("found[key] -= models().keys()", "pass"),
    "failed-on-main": ("added = set(failed) & collected() - chosen", "added = set()"),
}

MUTANT = """
import json, sys, types
script, old, new, asked, salt, where = json.load(sys.stdin)
module = types.ModuleType("select_tests")
module.__file__ = script
exec(compile(open(script).read().replace(old, new), script, "exec"), module.__dict__)
module.unowned = frozenset
module.kept = lambda: (bytes.fromhex(salt), where and module.Path(where))
print(json.dumps([module.selection(*one) for one in asked]))
"""


def parses(line):
    """Whether a break of the selector at `line` can change what `facts` finds: the line is in
    `facts`, in a function it names or one those name, or outside any function. A name a
    function binds itself, such as a local `readers`, is not the function of that name."""
    tree = ast.parse(SCRIPT.read_text())
    defs = {one.name: one for one in tree.body if isinstance(one, ast.FunctionDef)}
    found, todo = set(), ["facts"]
    while todo:
        name = todo.pop()
        if name in defs and name not in found:
            found.add(name)
            names = [one for one in ast.walk(defs[name]) if isinstance(one, ast.Name)]
            bound = {one.arg for one in ast.walk(defs[name]) if isinstance(one, ast.arg)}
            bound |= {one.id for one in names if not isinstance(one.ctx, ast.Load)}
            todo += [one.id for one in names if one.id not in bound]
    at = [name for name, one in defs.items() if one.lineno <= line <= one.end_lineno]
    return not at or at[0] in found


def mutant(old, new):
    """The `(tests, why)` for each of the table's questions from the selector with one rule
    broken, `old` swapped for `new` in its source, run as CI runs it. The catch-all is left
    out: no test of today's tree is in it, and finding that out takes each path's selection.
    A mutant whose broken line is in a function that `facts` does not run reads each module's
    facts as the selector kept them, rather than parsing every module again: they are the
    same facts. One that breaks `facts`, what it runs, or a line outside any function parses
    them itself."""
    text = SCRIPT.read_text()
    assert text.count(old) == 1, f"the rule's code moved: {old!r}"
    line = text[: text.index(old)].count("\n") + 1
    salt, where = (b"", None) if parses(line) else select.kept()
    if where:
        select.facts()
    ran = subprocess.run(
        [sys.executable, "-I", "-S", "-c", MUTANT],
        input=json.dumps([str(SCRIPT), old, new, asked(), salt.hex(), where and str(where)]),
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert ran.returncode == 0, ran.stderr
    return json.loads(ran.stdout)


def test_every_rule_of_the_table_has_a_mutant():
    rules = {rule for rule, *_ in TABLE} | {"failed-on-main"}

    assert rules - MUTANTS.keys() == {"itself", "scripts", "paths"}
    assert MUTANTS.keys() <= rules


def test_the_selector_run_as_the_mutants_run_fails_no_row():
    """The control: with no rule broken, the selector run the mutants' way gets every row
    right, so a mutant that fails a row fails it for the rule it broke."""
    assert failing(mutant("def ruled(", "def ruled(")) == []


@pytest.mark.parametrize("rule", MUTANTS)
def test_breaking_a_rule_of_the_selector_fails_a_row_of_its_rule(rule):
    """Each rule broken alone in the selector's source must fail a row of the table that names
    that rule, so the table pins what each rule selects and no row passes on another rule."""
    wrong = failing(mutant(*MUTANTS[rule]))

    assert [one for one in wrong if one.startswith(f"{rule}:")]
