"""Every test that runs a facility only Linux has carries a Linux-only mark, so the macOS nightly
skips it instead of failing it.

A Linux-only mark is a `pytest.mark.skipif` whose condition reads the platform (`sys.platform`,
or a name such as jinstall's `MAC` that holds it) or asks `shutil.which` for the tool, on the
test, on its class, or as its module's `pytestmark`, written there or bound to a name the module
defines or imports.

The facilities are the ones that broke the macOS nightly: libc.so.6 loaded through ctypes,
inotify, a `systemctl` a test runs through `subprocess`, and a sed script a test runs whose form
BSD sed refuses (`test_portable_shell.GNU_ONLY`, `test_portable_sed.unended`). The guard reads
each test's own code and, by name, each function, class, fixture and test helper module the test
reaches, and each helper script beside it that the test runs, as the 3 tests of
`test_checks_bound_probe.py` reached libc.so.6 by running `checks_bound_probe.py`. A string the
code only holds as data is not a use: a command is a use when the code hands it to `subprocess`.
A `systemctl` stand-in a test writes is run by its path, so a run of the bare name is the real one.
"""

import ast
import re
import textwrap
from functools import cache

from test_portable_sed import scripts, unended
from test_portable_shell import GNU_ONLY
from testing.paths import REPO

RUNS = {"run", "Popen", "check_call", "check_output", "call", "getoutput", "getstatusoutput"}
LOADERS = {"CDLL", "PyDLL", "LoadLibrary"}
GNU_SED = [re.compile(pattern) for pattern, _ in GNU_ONLY if "sed" in pattern]
PLATFORM = re.compile(r"\bplatform\b|\bMAC\b|\bwhich\(")


def folders(root):
    yield from sorted(root.glob("features/*/tests"))
    yield root / "testing" / "tests"


def gnu_sed(command):
    """Whether a command line runs sed in a form only GNU sed takes."""
    return any(rule.search(command) for rule in GNU_SED) or any(
        unended(script) for script in scripts(command)
    )


def runs(call):
    """Whether a call hands its arguments to a process: a call of `subprocess`'s."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in RUNS
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def command_lines(call):
    """The literal command lines a `subprocess` call runs: an argv list's words joined, and each
    string among its arguments."""
    for arg in call.args[:1]:
        if isinstance(arg, (ast.List, ast.Tuple)):
            words = [getattr(one, "value", None) for one in arg.elts]
            if words and all(isinstance(word, str) for word in words):
                yield words
    for node in ast.walk(ast.Module(body=[ast.Expr(arg) for arg in call.args], type_ignores=[])):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def own_facilities(node):
    """The Linux-only facilities a function's or class's own code uses."""
    found = set()
    for one in ast.walk(node):
        if (
            isinstance(one, ast.Call)
            and getattr(one.func, "attr", getattr(one.func, "id", None)) in LOADERS
            and any(isinstance(arg, ast.Constant) and arg.value == "libc.so.6" for arg in one.args)
        ):
            found.add("libc.so.6")
        elif isinstance(one, ast.Attribute) and one.attr.startswith("inotify_"):
            found.add("inotify")
        elif isinstance(one, ast.Call) and runs(one):
            for line in command_lines(one):
                if isinstance(line, list):
                    if line[0] == "systemctl":
                        found.add("systemctl")
                    line = " ".join(line)
                if gnu_sed(line):
                    found.add("GNU-only sed")
    return found


class Module:
    """A test folder's Python file: what it defines at the top, and what it imports by name."""

    def __init__(self, path):
        self.path = path
        self.tree = ast.parse(path.read_text(), filename=str(path))
        self.defs, self.imports = {}, {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.defs[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.defs[target.id] = node
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = (node.module, alias.name)

    def sibling(self, name):
        """The module `name` beside this one, or under testing/, when it is a test helper."""
        for folder in (self.path.parent, REPO):
            path = folder.joinpath(*name.split(".")).with_suffix(".py")
            if path.is_file():
                return module(path)
        return None

    def resolve(self, name):
        """The module and the top-level node that a name used in this module means."""
        if name in self.defs:
            return self, self.defs[name]
        if name in self.imports:
            source, original = self.imports[name]
            other = self.sibling(source)
            if other is not None and original in other.defs:
                return other, other.defs[original]
        return None


@cache
def module(path):
    return Module(path)


def names(node):
    return {one.id for one in ast.walk(node) if isinstance(one, ast.Name)}


def fixtures(mod, node):
    """The fixtures a test asks for by argument that the module or its conftest.py defines."""
    conftest = mod.path.parent / "conftest.py"
    places = [mod, module(conftest)] if conftest.is_file() else [mod]
    for arg in node.args.args:
        for place in places:
            if arg.arg in place.defs:
                yield place, place.defs[arg.arg]
                break


def scripts_run(mod, node):
    """The test helper scripts beside the module that a node runs through `subprocess`."""
    for one in ast.walk(node):
        if isinstance(one, ast.Call) and runs(one):
            for line in command_lines(one):
                for word in [line] if isinstance(line, str) else line:
                    path = mod.path.parent / word
                    if word.endswith(".py") and "/" not in word and path.is_file():
                        yield module(path)


def facilities(mod, node, seen=None):
    """The Linux-only facilities a test reaches: in its own code, and in what it reaches by
    name, across the test helpers of its folder."""
    seen = set() if seen is None else seen
    if (mod.path, id(node)) in seen:
        return set()
    seen.add((mod.path, id(node)))
    found = own_facilities(node)
    reached = [mod.resolve(name) for name in names(node)]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        reached += list(fixtures(mod, node))
    reached += [(script, script.tree) for script in scripts_run(mod, node)]
    for one in filter(None, reached):
        found |= facilities(*one, seen)
    return found


def linux_only(mod, expr, depth=0):
    """Whether a decorator, or a `pytestmark`, is a skip on the platform."""
    if depth > 3:
        return False
    if isinstance(expr, (ast.List, ast.Tuple)):
        return any(linux_only(mod, one, depth) for one in expr.elts)
    text = ast.unparse(expr)
    if "skipif" in text and PLATFORM.search(text):
        return True
    target = expr.func if isinstance(expr, ast.Call) else expr
    if isinstance(target, ast.Name) and (found := mod.resolve(target.id)):
        other, node = found
        value = node.value if isinstance(node, ast.Assign) else node
        if isinstance(value, (ast.FunctionDef, ast.AsyncFunctionDef)):
            returned = [one.value for one in ast.walk(value) if isinstance(one, ast.Return)]
            return any(one is not None and linux_only(other, one, depth + 1) for one in returned)
        return linux_only(other, value, depth + 1)
    return False


def marked_tests(mod):
    """Each test of a module with the marks that cover it: its own, its class's, its module's."""
    module_marks = [
        node.value
        for node in mod.tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(one, ast.Name) and one.id == "pytestmark" for one in node.targets)
    ]
    for node in mod.tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test"
        ):
            yield node.name, node, [*module_marks, *node.decorator_list]
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    method.name.startswith("test")
                ):
                    marks = [*module_marks, *node.decorator_list, *method.decorator_list]
                    yield f"{node.name}::{method.name}", method, marks


def unmarked(root):
    """Each test under `root` that reaches a Linux-only facility with no Linux-only mark, as
    `path::test: facility, ...`."""
    module.cache_clear()
    found = []
    for folder in folders(root):
        for path in sorted(folder.rglob("test_*.py")):
            mod = module(path)
            for name, node, marks in marked_tests(mod):
                used = facilities(mod, node)
                if used and not any(linux_only(mod, mark) for mark in marks):
                    found.append(f"{path.relative_to(root)}::{name}: {', '.join(sorted(used))}")
    return found


def test_every_test_that_reaches_a_linux_only_facility_is_marked_linux_only():
    assert unmarked(REPO) == []


def plant(root, name, text):
    path = root / "features" / "demo" / "tests" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_a_planted_test_that_reaches_each_facility_unmarked_is_named_and_marked_is_not(tmp_path):
    plant(
        tmp_path,
        "probe.py",
        """
        import ctypes
        class Probe:
            def __init__(self):
                self.fd = ctypes.CDLL("libc.so.6").inotify_init1(0)
        """,
    )
    plant(tmp_path, "watch.py", 'import ctypes\nctypes.CDLL("libc.so.6")\n')
    plant(
        tmp_path,
        "test_demo.py",
        """
        import subprocess, sys
        from pathlib import Path
        import pytest
        from probe import Probe
        LINUX = pytest.mark.skipif(sys.platform != "linux", reason="Linux's case")

        @pytest.fixture
        def probe():
            return Probe()

        def test_probe(probe):
            assert probe.fd

        def test_units():
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)

        def test_edit(tmp_path):
            subprocess.run(f"sed -i 's/a/b/' {tmp_path}/f", shell=True)

        def test_watch():
            subprocess.run([sys.executable, str(Path(__file__).with_name("watch.py"))])

        def test_said():
            assert "sed -i 's/a/b/' f" != "systemctl"

        @LINUX
        def test_marked(probe):
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        """,
    )
    assert unmarked(tmp_path) == [
        "features/demo/tests/test_demo.py::test_probe: inotify, libc.so.6",
        "features/demo/tests/test_demo.py::test_units: systemctl",
        "features/demo/tests/test_demo.py::test_edit: GNU-only sed",
        "features/demo/tests/test_demo.py::test_watch: libc.so.6",
    ]
    (tmp_path / "features" / "demo" / "tests" / "test_demo.py").write_text(
        "import pytest, sys\n"
        "pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux')\n"
        + (tmp_path / "features" / "demo" / "tests" / "test_demo.py").read_text()
    )
    assert unmarked(tmp_path) == []


def test_the_marks_jinstall_and_jbus_write_count_as_linux_only():
    """jinstall's `linux_only(darwin)`, imported from test_install.py, returns its skip, and
    jbus's `INOTIFY` is bound to one."""
    units = module(REPO / "features" / "jinstall" / "tests" / "test_install_units.py")
    marked = {
        name for name, _, marks in marked_tests(units) if any(linux_only(units, m) for m in marks)
    }
    assert "test_the_units_are_linked_and_the_timer_enabled_once_jbus_has_a_config" in marked
    probe = module(REPO / "features" / "jbus" / "tests" / "test_checks_bound_probe.py")
    assert linux_only(probe, ast.Name("INOTIFY"))
