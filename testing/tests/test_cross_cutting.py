"""Every test file that reads the real tree is on the `Cross-cutting:` list of verify-jstack's map,
so every diff runs it.

`scripts/select_tests.py` selects a test by what it imports and the paths it spells. A test
that globs, walks or lists a folder of the checkout reads files it neither imports nor spells,
so a change to one of them does not select it, and main goes red after the merge: #330 grew
`jbus/wake.py` over `test_module_size.py`'s cap, and #337 put a URL in a view test that
`test_view_sources.py` reads.

A test reads the real tree when it calls `glob`, `rglob`, `iterdir` or `walk` on a path built from
`REPO` or `ROOT`, when it iterates what `sources()`, `skills()` or `playbooks()` of `testing.paths`
found there, or when it runs `git ls-files` with `REPO`. A path the test builds from `tmp_path` is
no read of the tree. Nor is a helper whose result the test only looks one name up in, such as
`skills()["home"]`: the test spells the name, and the script follows it.
"""

import ast
import importlib.util

import pytest

from testing.paths import REPO

SCRIPT = REPO / "scripts" / "select_tests.py"
SPEC = importlib.util.spec_from_file_location("select_tests", SCRIPT)
select = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(select)

ROOTS = {"REPO", "ROOT"}
HELPERS = {"sources", "skills", "playbooks"}
READS = {"glob", "rglob", "iterdir", "walk"}
WRAPPERS = {"sorted", "list", "tuple", "set", "Path"}


class Reader:
    """The reads of the real tree in one module's source."""

    def __init__(self, source):
        self.tree = ast.parse(source)
        self.bound = {}
        for node in ast.walk(self.tree):
            for name, value in bindings(node):
                self.bound.setdefault(name, []).append(value)
        self.keyed = {id(node.value) for node in ast.walk(self.tree) if is_key(node)}
        self.looked_up = self.lookups()
        self.seen = set()

    def lookups(self):
        """The helper calls whose result is only looked up by a name: called and indexed at once,
        or put in a name that is only ever indexed."""
        found = set(self.keyed)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                (target, *more) = node.targets
                if more or not isinstance(target, ast.Name):
                    continue
                uses = [
                    one
                    for one in ast.walk(self.tree)
                    if isinstance(one, ast.Name)
                    and one.id == target.id
                    and isinstance(one.ctx, ast.Load)
                ]
                if uses and all(id(one) in self.keyed for one in uses):
                    found.add(id(node.value))
        return found

    def real(self, node):
        """Whether `node` is a path, or paths, of the checkout."""
        if isinstance(node, ast.Name):
            if node.id in ROOTS and node.id not in self.bound:
                return True
            if node.id in self.seen:
                return False
            self.seen.add(node.id)
            try:
                return any(self.real(value) for value in self.bound.get(node.id, ()))
            finally:
                self.seen.discard(node.id)
        if isinstance(node, ast.BinOp):
            return self.real(node.left)
        if isinstance(node, ast.BoolOp):
            return any(self.real(value) for value in node.values)
        if isinstance(node, (ast.Subscript, ast.Attribute)):
            return self.real(node.value)
        if isinstance(node, ast.Call):
            return self.real_call(node)
        return False

    def real_call(self, node):
        function = node.func
        if isinstance(function, ast.Name) and function.id in HELPERS:
            return all(self.real(one) for one in node.args)
        if isinstance(function, ast.Name) and function.id in WRAPPERS and node.args:
            return self.real(node.args[0])
        return isinstance(function, ast.Attribute) and self.real(function.value)

    def reads(self):
        """Each read of the real tree, as its source."""
        found = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and self.reads_tree(node):
                found.append(ast.unparse(node))
        return found

    def reads_tree(self, node):
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr in READS:
            module = function.value.id if isinstance(function.value, ast.Name) else None
            if module == "ast":
                return False
            if module == "os":
                return bool(node.args) and self.real(node.args[0])
            return self.real(function.value)
        if isinstance(function, ast.Name) and function.id in HELPERS:
            return id(node) not in self.looked_up and all(self.real(one) for one in node.args)
        words = {one.value for one in ast.walk(node) if isinstance(one, ast.Constant)}
        named = {one.id for one in ast.walk(node) if isinstance(one, ast.Name)}
        return "ls-files" in words and "REPO" in named


def bindings(node):
    """`(name, value)` for each name `node` binds to a value, or to the items of one."""
    if isinstance(node, ast.Assign):
        return [(one.id, node.value) for one in node.targets if isinstance(one, ast.Name)]
    if isinstance(node, ast.AnnAssign) and node.value and isinstance(node.target, ast.Name):
        return [(node.target.id, node.value)]
    if isinstance(node, (ast.For, ast.comprehension)):
        return [(one.id, node.iter) for one in ast.walk(node.target) if isinstance(one, ast.Name)]
    return []


def is_key(node):
    return isinstance(node, ast.Subscript) and not isinstance(node.slice, ast.Slice)


def reads(source):
    return Reader(source).reads()


def every_test_file():
    return sorted(path for path in select.modules().values() if select.TEST.fullmatch(path))


def test_every_test_file_that_reads_the_real_tree_is_cross_cutting():
    cross = set(select.cross_cutting())

    missing = [
        f"{path}: {reads((REPO / path).read_text())[0]}"
        for path in every_test_file()
        if path not in cross and reads((REPO / path).read_text())
    ]

    assert missing == [], f"add each to Cross-cutting: in {select.CROSS}"


@pytest.mark.parametrize(
    "source",
    [
        "from testing.paths import REPO\nfiles = REPO.glob('features/*/feature.json')\n",
        "VIEW = REPO / 'features' / 'jbus' / 'tests'\nfiles = sorted(VIEW.rglob('*.py'))\n",
        "def size(*roots):\n    return [p for r in roots or sources() for p in r.rglob('*')]\n",
        "SKILLS = [folder / 'SKILL.md' for folder in skills().values()]\n",
        "listed = subprocess.run(['git', '-C', REPO, 'ls-files'], capture_output=True)\n",
        "for at, dirs, files in os.walk(ROOT / 'features'):\n    pass\n",
    ],
    ids=["a glob of the root", "a folder of tests", "sources", "skills", "git ls-files", "a walk"],
)
def test_a_read_of_the_checkout_is_a_read_of_the_tree(source):
    assert reads(source)


@pytest.mark.parametrize(
    "source",
    [
        "def test_it(tmp_path):\n    assert not list(tmp_path.rglob('*'))\n",
        "def test_it(tmp_path):\n    REPO = tmp_path\n    assert not list(REPO.glob('*'))\n",
        "SKILL = skills()['home'] / 'SKILL.md'\n",
        "SKILLS = skills()\nLOG = SKILLS['show-me-your-work'] / 'log.sh'\n",
        "for node in ast.walk(tree):\n    pass\n",
    ],
    ids=["tmp_path", "a REPO of its own", "one skill", "a name only indexed", "ast.walk"],
)
def test_a_read_of_a_folder_the_test_made_or_of_one_named_file_is_not(source):
    assert reads(source) == []
