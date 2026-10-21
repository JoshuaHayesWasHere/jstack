"""A test that reads a skill's words and runs nothing fails here.

The rule is the user's (2026-10-10): "we need to ensure the test do not only nmath the skills
wording and execute nothign". A test that reads a file under `skills/`, `playbooks/`,
`principles/` or `templates/`, asserts with words of its own, and runs nothing passes on any
behaviour and fails on a rewording. The lint reads every test module with `ast` and follows
what a test calls: a helper of its own module, a test module it imports, a fixture it asks
for. A test runs something when that reaches `subprocess` (the shared block runner does), a
package of `src/`, or `jsonschema` (a JSON call of a skill checked against the tool's schema).

Such tests are common, so the lint fails only on a test function added or changed against the
merge-base with `origin/main`. An exception is a comment on the test's own `def` line, with its
reason and the user's word: `# words only: <reason> (the user, <when>: "<their words>")`.

A lint over every file that asserts a property and no words of its own, as
`test_templates.py` does, is not a wording test: it has no phrase to match.

The tests of the lint give it modules to read: one in the shape of the five tests that
`tasks/crew-stays-on-pr.md` flagged, which only found phrases in the crew skill, and others
that run the block they read.
"""

import ast
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from testing.paths import REPO

TESTS = REPO / "tests"
DOCS = ("skills", "playbooks", "principles", "templates")
DOC_PATH = re.compile(rf"^(\.*/)*({'|'.join(DOCS)})(/|$)|/({'|'.join(DOCS)})/")
FILE_NAME = re.compile(r"^[\w.*/-]*\.(md|py|sh|json|toml|txt|yml|yaml|html|css|js)$")
SRC = frozenset(path.name.removesuffix(".py") for path in (REPO / "src").iterdir())
RUNNERS = frozenset({"subprocess", "jsonschema"})
READS = frozenset({"read_text", "read_bytes", "open", "read", "readlines"})
SHELL = frozenset({"system", "popen", "spawnl", "spawnv", "spawnlp", "spawnvp", "execv", "execvp"})
LITERALS = (ast.Constant, ast.Tuple, ast.List, ast.Set, ast.Dict)
PATH_CALLS = frozenset({"Path", "glob", "rglob", "joinpath", "relative_to", "with_name"})
EXCEPTION = re.compile(
    r"#\s*words only:\s*(?P<reason>\S.*?)\s*\(the user[,:]\s*(?P<word>[^)]*\S)\)\s*$"
)
WHAT_TO_DO = (
    "run the block it reads (the shared block runner, or subprocess in a temporary repo) or "
    "the command it names, and assert what that does"
)


@dataclass
class Facts:
    """What a piece of code does, with all it reaches."""

    runs: bool = False
    reads: bool = False
    docs: bool = False
    asserts: bool = False

    def add(self, other):
        self.runs |= other.runs
        self.reads |= other.reads
        self.docs |= other.docs
        self.asserts |= other.asserts


@dataclass
class Module:
    name: str
    tree: ast.Module
    lines: list[str]
    defs: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)
    modules: dict = field(default_factory=dict)
    imported: dict = field(default_factory=dict)
    fixtures: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, name, source):
        module = cls(name, ast.parse(source), source.splitlines())
        for node in module.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                module.defs[node.name] = node
                if fixture(node):
                    module.fixtures[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for each in ast.walk(target):
                        if isinstance(each, ast.Name):
                            module.values[each.id] = node.value
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module.modules[alias.asname or alias.name.split(".")[0]] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for alias in node.names:
                    module.imported[alias.asname or alias.name] = (node.module, alias.name)
        return module

    def tests(self):
        """Each test function, with the name pytest gives it within the module."""
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test"):
                    yield node.name, node
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for inner in node.body:
                    if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if inner.name.startswith("test"):
                            yield f"{node.name}::{inner.name}", inner


def fixture(node):
    for decorator in getattr(node, "decorator_list", []):
        called = decorator.func if isinstance(decorator, ast.Call) else decorator
        if (isinstance(called, ast.Name) and called.id == "fixture") or (
            isinstance(called, ast.Attribute) and called.attr == "fixture"
        ):
            return True
    return False


def root(node):
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


class Lint:
    """The test modules of one tree, read with `ast`, and what each test reaches."""

    def __init__(self, sources):
        self.modules = {name: Module.parse(name, text) for name, text in sources.items()}
        self.memo = {}

    def top(self, module, name):
        """The facts of a name bound at the top of a module, or None when it is not code there."""
        key = (module.name, name)
        if key in self.memo:
            return self.memo[key]
        if name in module.defs:
            nodes = [module.defs[name]]
        elif name in module.values:
            nodes = [module.values[name]]
        elif name in module.imported and module.imported[name][0] in self.modules:
            source, attr = module.imported[name]
            return self.top(self.modules[source], attr)
        else:
            return None
        facts = self.memo[key] = Facts()
        facts.add(self.walk(module, nodes))
        return facts

    def walk(self, module, nodes):
        facts = Facts()
        for node in (each for top in nodes for each in ast.walk(top)):
            if isinstance(node, ast.Assert):
                facts.asserts = True
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                facts.docs |= bool(DOC_PATH.search(node.value))
            elif isinstance(node, ast.Call):
                self.call(module, node, facts)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                found = self.top(module, node.id)
                if found:
                    facts.add(found)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                imported = module.modules.get(node.value.id)
                if imported in self.modules:
                    found = self.top(self.modules[imported], node.attr)
                    if found:
                        facts.add(found)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for each in self.asked(module, node):
                    facts.add(each)
        return facts

    def call(self, module, node, facts):
        name = root(node.func)
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            facts.reads = True
        if attr in READS:
            facts.reads = True
        if name in module.modules:
            package = module.modules[name].split(".")[0]
            facts.runs |= package in SRC or package in RUNNERS
            facts.runs |= package == "os" and attr in SHELL
        elif name in module.imported:
            package = module.imported[name][0].split(".")[0]
            facts.runs |= package in SRC or package in RUNNERS

    def asked(self, module, node):
        """The facts of each fixture a function asks for by its parameters: its module's own,
        then those of the `conftest` of each folder it is in, the nearest first."""
        parts = module.name.split(".")[:-1]
        folders = [".".join(parts[:end] + ["conftest"]) for end in range(len(parts), -1, -1)]
        conftests = [self.modules.get(name) for name in folders]
        for arg in node.args.args + node.args.kwonlyargs:
            for where in (module, *conftests):
                if where and arg.arg in where.fixtures:
                    found = self.top(where, arg.arg)
                    if found:
                        yield found
                    break

    def flagged(self, module_name):
        """Each test of a module that reads a doc, asserts on words and runs nothing."""
        module = self.modules[module_name]
        for name, node in module.tests():
            facts = self.walk(module, [node])
            if (
                facts.docs
                and facts.reads
                and facts.asserts
                and not facts.runs
                and phrases(module, node)
            ):
                yield name, node


def phrases(module, test):
    """The words a test brings to match: the string literals of its body, of the values its
    decorators give it (a parametrize list, but not its argument names), and of each literal
    the module binds to a name that either reads. A path, a file name, a keyword's value and a
    part of an f-string are no words."""
    body = test.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    given = []
    for decorator in test.decorator_list:
        if isinstance(decorator, ast.Call):
            parametrize = getattr(decorator.func, "attr", None) == "parametrize"
            given += decorator.args[1:] if parametrize else decorator.args
    named = {
        node.id
        for top in body + given
        for node in ast.walk(top)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    bound = (module.values[name] for name in sorted(named & module.values.keys()))
    nodes = body + given + [value for value in bound if isinstance(value, LITERALS)]
    skip = set()
    for node in (each for top in nodes for each in ast.walk(top)):
        if isinstance(node, ast.JoinedStr):
            skip.update(id(part) for part in ast.walk(node))
        elif isinstance(node, ast.keyword):
            skip.update(id(part) for part in ast.walk(node.value))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            skip.update((id(node.left), id(node.right)))
        elif isinstance(node, ast.Call):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else root(node.func)
            if called in PATH_CALLS:
                skip.update(id(arg) for arg in node.args)
    return [
        node.value
        for top in nodes
        for node in ast.walk(top)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.strip()
        and id(node) not in skip
        and not DOC_PATH.search(node.value)
        and not FILE_NAME.match(node.value)
    ]


def excepted(module, node):
    """Whether the test's `def` line has an exception, with its reason and the user's word."""
    return bool(EXCEPTION.search(module.lines[node.lineno - 1]))


def errors(lint, changed):
    """The lint's error for each test in `changed` ({module: names}) that it flags."""
    for module_name, names in sorted(changed.items()):
        module = lint.modules[module_name]
        for name, node in lint.flagged(module_name):
            if name in names and not excepted(module, node):
                path = f"tests/{module_name.replace('.', '/')}.py"
                yield (
                    f"{path}:{node.lineno} {name} reads a skill's, playbook's, "
                    f"principle's or template's words, asserts on them and runs nothing: "
                    f"{WHAT_TO_DO}. An exception is a comment on that line: "
                    f'# words only: <reason> (the user, <when>: "<their words>")'
                )


def git(*args, repo=REPO):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def base():
    """The commit the branch is compared with, or None. A desk has `origin/main`. CI's checkout
    of a pull request is its merge commit, alone: its first parent is the base, fetched here."""
    try:
        return git("merge-base", "HEAD", "origin/main")
    except subprocess.CalledProcessError:
        pass
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None
    parents = [
        line.split()[1]
        for line in git("cat-file", "-p", "HEAD").splitlines()
        if line.startswith("parent ")
    ]
    if len(parents) != 2:
        return None
    try:
        git("fetch", "-q", "--no-tags", "--depth=1", "origin", parents[0])
    except subprocess.CalledProcessError:
        return None
    return parents[0]


def dumped_tests(source):
    return {name: ast.dump(node) for name, node in Module.parse("", source).tests()}


def moved_from(since, repo):
    """Each test of every test file of `tests/` at the commit, by its name: a test in a file
    that is new since then is unchanged where one of its name had the same code there, so a
    test moved to another file is not counted as added."""
    listed = git("ls-tree", "-r", "--name-only", since, "--", "tests", repo=repo).splitlines()
    found = {}
    for path in listed:
        if re.fullmatch(r"tests/(\w+/)*test_\w+\.py", path):
            for name, dumped in dumped_tests(git("show", f"{since}:{path}", repo=repo)).items():
                found.setdefault(name, dumped)
    return found


def changed_tests(since, repo=REPO):
    """{module: test names} added or changed since the commit, the worktree's own edits in."""
    paths = git("diff", "--name-only", since, "--", "tests", repo=repo).splitlines()
    paths += git(
        "ls-files", "--others", "--exclude-standard", "--", "tests", repo=repo
    ).splitlines()
    changed = {}
    for path in sorted(set(paths)):
        if not re.fullmatch(r"tests/(\w+/)*test_\w+\.py", path) or not (repo / path).exists():
            continue
        try:
            before = dumped_tests(git("show", f"{since}:{path}", repo=repo))
        except subprocess.CalledProcessError:
            before = {}
        if not before:
            before = moved_from(since, repo)
        now = dumped_tests((repo / path).read_text())
        names = {name for name, dumped in now.items() if before.get(name) != dumped}
        if names:
            changed[dotted(Path(path).relative_to("tests"))] = names
    return changed


def dotted(path):
    """A module of `tests/` by the name it is imported by, as `crew.helpers` or `conftest`."""
    return ".".join(path.with_suffix("").parts).removesuffix(".__init__")


def tree():
    return Lint(
        {
            dotted(path.relative_to(TESTS)): path.read_text()
            for path in sorted(TESTS.rglob("*.py"))
            if path.relative_to(TESTS).parts[0] != "fixtures"
        }
    )


def test_no_test_added_or_changed_on_this_branch_reads_words_and_runs_nothing():
    since = base()
    if since is None:
        pytest.skip("no merge-base with origin/main here, so the changed tests are not known")
    found = list(errors(tree(), changed_tests(since)))
    assert not found, "\n".join(found)


WORDS_ONLY = """
from pathlib import Path

SKILL = REPO / "skills" / "crew" / "SKILL.md"


def sections():
    found, name = {}, None
    for line in SKILL.read_text().splitlines():
        if line.startswith("## "):
            name = line[3:]
            found[name] = []
        elif name:
            found[name].append(line)
    return {name: "\\n".join(lines) for name, lines in found.items()}


def stay():
    return sections()["Stay on the pull request"]


def test_an_open_pull_request_is_linked_then_watched_once_the_result_is_written():
    steps = ("`link_pull_request`", "Write the Result", "`watch_pull_request`")
    order = [stay().index(step) for step in steps]
    assert order == sorted(order)
    assert "end your turn" in stay()


def test_a_session_without_the_tools_says_so_and_ends():
    assert "If the session has neither tool" in stay()


def test_a_woken_crewmate_fixes_what_broke_and_idles_on_green():
    for wake in ("failed check", "comment or review", "conflict"):
        assert wake in stay()
    assert "one line to the Result" in stay()
    assert "passing checks" in stay()


def test_a_crewmate_never_merges_and_is_promised_nothing_on_merge():
    assert "Never merge" in stay()
    assert "A merge does not wake" in stay()


def test_the_thread_is_finished_only_when_there_is_no_pull_request():
    end = sections()["End"]
    assert "This thread is finished" in end
    finished = next(line for line in end.splitlines() if "This thread is finished" in line)
    assert finished.startswith("With no pull request")
"""

FIVE = [
    "test_an_open_pull_request_is_linked_then_watched_once_the_result_is_written",
    "test_a_session_without_the_tools_says_so_and_ends",
    "test_a_woken_crewmate_fixes_what_broke_and_idles_on_green",
    "test_a_crewmate_never_merges_and_is_promised_nothing_on_merge",
    "test_the_thread_is_finished_only_when_there_is_no_pull_request",
]

RUNS_THE_BLOCK = """
import subprocess

from test_words_only import sections


def block(heading):
    return sections()[heading].split("```sh\\n")[1].split("```")[0]


def test_the_end_block_says_stay_with_a_pull_request_open(tmp_path):
    done = subprocess.run(["sh", "-c", block("End")], cwd=tmp_path, capture_output=True, text=True)
    assert "stay: it has a pull request" in done.stdout
"""


def flagged(**sources):
    lint = Lint({name: textwrap.dedent(text) for name, text in sources.items()})
    return [name for module in sources for name, _ in lint.flagged(module)]


def test_the_five_tests_that_only_found_phrases_in_the_crew_skill_are_flagged():
    assert flagged(test_words_only=WORDS_ONLY) == FIVE


def test_a_test_that_runs_the_block_it_reads_passes():
    assert flagged(test_words_only=WORDS_ONLY, test_runs=RUNS_THE_BLOCK) == FIVE


def test_a_test_that_calls_a_command_of_src_on_the_words_passes():
    calls = """
    from jbus import verbs
    from test_words_only import stay

    def test_the_verb_it_names_parses():
        assert verbs.parser().parse_args(["gate", stay().split()[0]])
    """
    assert flagged(test_words_only=WORDS_ONLY, test_calls=calls) == FIVE


def test_a_runner_in_conftest_counts_through_a_fixture_or_a_helper_of_another_module():
    conftest = """
    import subprocess
    import pytest

    def run_block(text):
        return subprocess.run(["sh", "-c", text], capture_output=True, text=True).stdout

    @pytest.fixture
    def runner():
        return run_block
    """
    by_fixture = """
    from pathlib import Path
    SKILL = Path("skills/home/SKILL.md")

    def test_the_block_says_go(runner):
        assert "go" in runner(SKILL.read_text())
    """
    by_import = """
    from pathlib import Path
    import conftest
    SKILL = Path("skills/home/SKILL.md")

    def test_the_block_says_go():
        assert "go" in conftest.run_block(SKILL.read_text())
    """
    assert flagged(conftest=conftest, test_fixture=by_fixture, test_import=by_import) == []


def test_phrases_given_by_parametrize_or_a_module_constant_are_flagged():
    parametrized = """
    import pytest
    from pathlib import Path
    SKILL = Path("skills/crew/SKILL.md")

    @pytest.mark.parametrize("phrase", ["Never merge", "A merge does not wake"])
    def test_the_skill_says(phrase):
        assert phrase in SKILL.read_text()
    """
    constant = """
    from pathlib import Path
    SKILL = Path("skills/crew/SKILL.md")
    PHRASES = ("Never merge", "A merge does not wake")

    def test_the_skill_says_each():
        for phrase in PHRASES:
            assert phrase in SKILL.read_text()
    """
    found = flagged(test_parametrized=parametrized, test_constant=constant)
    assert found == ["test_the_skill_says", "test_the_skill_says_each"]


def test_a_lint_parametrized_over_file_names_has_no_words_of_its_own():
    lint = """
    import pytest
    from pathlib import Path
    TEMPLATES = Path("templates")
    NAMES = ["brief.md", "result.md"]

    @pytest.mark.parametrize("name", NAMES)
    def test_lint_each_template_has_lines(name):
        assert (TEMPLATES / name).read_text().splitlines()
    """
    assert flagged(test_lint=lint) == []


def test_a_lint_over_every_doc_with_no_words_of_its_own_passes():
    lint = """
    from pathlib import Path
    REPO = REPO

    def test_lint_every_skill_names_itself():
        skills = sorted(REPO.glob("skills/*/SKILL.md"))
        assert [path for path in skills if path.parent.name not in path.read_text()] == []
    """
    assert flagged(test_lint=lint) == []


def test_a_test_of_a_command_s_output_that_reads_no_doc_passes():
    output = """
    def test_the_words_of_a_message():
        text = "the pull request is fixed and green"
        assert "fixed and green" in text
    """
    assert flagged(test_output=output) == []


def test_the_error_names_the_test_and_says_to_run_the_block():
    lint = Lint({"test_words_only": WORDS_ONLY})
    (error,) = errors(lint, {"test_words_only": {FIVE[1]}})
    line = WORDS_ONLY.splitlines().index(f"def {FIVE[1]}():") + 1
    assert error.startswith(f"tests/test_words_only.py:{line} {FIVE[1]} reads")
    assert WHAT_TO_DO in error


def test_only_a_test_added_or_changed_since_the_base_is_an_error():
    lint = Lint({"test_words_only": WORDS_ONLY})
    assert list(errors(lint, {})) == []
    assert len(list(errors(lint, {"test_words_only": set(FIVE[:2])}))) == 2


def test_an_exception_on_the_def_line_with_josh_s_word_lets_the_test_be():
    word = '  # words only: the section has no block (the user, 2026-10-16: "keep this one")'
    marked = WORDS_ONLY.replace(f"def {FIVE[1]}():", f"def {FIVE[1]}():{word}")
    unsigned = WORDS_ONLY.replace(f"def {FIVE[1]}():", f"def {FIVE[1]}():  # words only: no block")
    above = WORDS_ONLY.replace(f"def {FIVE[1]}():", f"{word.strip()}\ndef {FIVE[1]}():")
    for source, kept in ((marked, False), (unsigned, True), (above, True)):
        lint = Lint({"test_words_only": source})
        named = [error.split()[1] for error in errors(lint, {"test_words_only": set(FIVE)})]
        assert (FIVE[1] in named) is kept


def test_a_test_is_changed_when_its_code_is_and_new_files_count_before_a_commit(tmp_path):
    def init(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))

    git("init", "-q", repo=tmp_path)
    init(
        tmp_path / "tests" / "test_a.py",
        """
    def test_kept():
        assert 1

    def test_edited():
        assert 1
    """,
    )
    init(tmp_path / "skills" / "x" / "SKILL.md", "words")
    git("add", ".", repo=tmp_path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base", repo=tmp_path)
    since = git("rev-parse", "HEAD", repo=tmp_path)
    init(
        tmp_path / "tests" / "test_a.py",
        """
    import os

    def test_kept():
        assert 1

    def test_edited():
        assert 2

    def test_added():
        assert 1
    """,
    )
    init(tmp_path / "tests" / "test_new.py", "def test_new():\n    assert 1\n")
    init(tmp_path / "tests" / "helper.py", "def test_not_a_test_module():\n    assert 1\n")
    assert changed_tests(since, tmp_path) == {
        "test_a": {"test_edited", "test_added"},
        "test_new": {"test_new"},
    }


def test_a_test_in_a_folder_reaches_its_folders_conftest_and_its_helpers_by_dotted_name():
    conftest = """
    import subprocess
    import pytest

    @pytest.fixture
    def runner():
        return lambda text: subprocess.run(["sh", "-c", text], capture_output=True).stdout
    """
    helpers = """
    from pathlib import Path
    SKILL = Path("skills/crew/SKILL.md")
    """
    test = """
    import area.helpers as words

    def test_the_block_says_go(runner):
        assert "go" in runner(words.SKILL.read_text())

    def test_the_skill_says_go():
        assert "go" in words.SKILL.read_text()
    """
    sources = {"area.conftest": conftest, "area.helpers": helpers, "area.test_go": test}
    assert flagged(**sources) == ["test_the_skill_says_go"]
    lint = Lint({name: textwrap.dedent(text) for name, text in sources.items()})
    (error,) = errors(lint, {"area.test_go": {"test_the_skill_says_go"}})
    assert error.startswith("tests/area/test_go.py:")


def test_a_changed_test_in_a_folder_is_named_by_its_dotted_name_and_a_moved_one_is_not(
    tmp_path,
):
    git("init", "-q", repo=tmp_path)
    (tmp_path / "README").write_text("x\n")
    git("add", ".", repo=tmp_path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base", repo=tmp_path)
    since = git("rev-parse", "HEAD", repo=tmp_path)
    (tmp_path / "tests" / "area").mkdir(parents=True)
    (tmp_path / "tests" / "test_old.py").write_text("def test_moved():\n    assert 1\n")
    git("add", ".", repo=tmp_path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "old", repo=tmp_path)
    since = git("rev-parse", "HEAD", repo=tmp_path)
    git("rm", "-q", "tests/test_old.py", repo=tmp_path)
    (tmp_path / "tests" / "area" / "test_deep.py").write_text(
        "def test_deep():\n    assert 1\n\n\ndef test_moved():\n    assert 1\n"
    )
    (tmp_path / "tests" / "area" / "helpers.py").write_text("def test_no():\n    assert 1\n")
    assert changed_tests(since, tmp_path) == {"area.test_deep": {"test_deep"}}


def test_a_test_under_any_test_path_counts_and_one_moved_into_a_feature_is_not_added(
    tmp_path,
):
    git("init", "-q", repo=tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests", "features/area/tests"]\n'
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_old.py").write_text("def test_moved():\n    assert 1\n")
    git("add", ".", repo=tmp_path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base", repo=tmp_path)
    since = git("rev-parse", "HEAD", repo=tmp_path)
    (tmp_path / "features" / "area" / "tests").mkdir(parents=True)
    git("mv", "tests/test_old.py", "features/area/tests/test_old.py", repo=tmp_path)
    (tmp_path / "features" / "area" / "tests" / "test_old.py").write_text(
        "def test_moved():\n    assert 1\n\n\ndef test_added():\n    assert 1\n"
    )
    (tmp_path / "features" / "area" / "tests" / "test_new.py").write_text(
        "def test_new():\n    assert 1\n"
    )
    assert changed_tests(since, tmp_path) == {
        "test_old": {"test_added"},
        "test_new": {"test_new"},
    }
