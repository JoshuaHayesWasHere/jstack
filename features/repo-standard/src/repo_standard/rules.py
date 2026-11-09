"""The checks behind the rules of the standard, one function a rule, each over a `Repo`.

A check returns the faults it finds, as lines of text, and an empty list when the repo meets the
rule. Some checks run a guard: a guard whose config part is missing raises `Refused`, which
`conform` records as that rule's fault. The rest read the tree: the Makefile's targets, the text of
the workflows, the manifests and the config.

A rule that no check of the tree can judge in every stack is met by the files that enforce it in
the repo, named in the config's `enforced-by`. `enforcer` holds each named file to two things: git
tracks it, and something the checks run reaches it. A test file, a workflow, and a file a workflow,
the Makefile or a make file it includes names by its path are reached, and so is a script the
adapter of one of the config's `stacks` runs, so a page or a file nothing runs does not meet it.

A check may return an `Advice`, a fault that warns whatever its rule's level and fails nothing.

A workflow that calls the standard's shared check at a version's tag runs what that workflow runs:
`make select`, `make lint` and the selected tests on a pull request, and `make check` on main.

A file the pinned version owns (`repo_standard.owned`) is held to that version's copy, read from
the tag's tree, which `Repo.upstream` clones when the tool's own tree is not that tree.
"""

from __future__ import annotations

import fnmatch
import importlib
import json
import re
import sys
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Any

from repo_standard import TAG, VERSION, borders, docs_true, owned, size, stale
from repo_standard.adapters import COMMANDS
from repo_standard.config import Config, Refused, Stack
from repo_standard.tree import Fault

WORKFLOWS = ".github/workflows/"
TEST_FILE = re.compile(r"^(test_.+\.py|.+_test\.(py|go)|.+\.test\.(js|ts|mjs))$")
BARE_PYTHON = re.compile(r"(?:^|[\s;&|(])python3\s+([\w./-]+\.py)\b")
RUNS_SCRIPT = re.compile(r"(?:^|[\s;&|(])(?:python3?|bash|sh|uv run)\s+([\w./-]+\.(?:py|sh))\b")
IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+(?:\s*,\s*[\w.]+)*))", re.M)
JOB = re.compile(r"^  ([\w-]+):\s*$", re.M)
FRONT_NAME = re.compile(
    r"\A---\n(?:.*\n)*?name:\s*['\"]?([^'\"\n]+?)['\"]?\s*\n(?:.*\n)*?---", re.M
)
GATED = ("deploy", "release")
GREEN = re.compile(
    r"(?:\brepo-standard|-m\s+repo_standard|\$[({]REPO_STANDARD[)}])\s+green(?![\w-])"
)
"""A command that runs `repo-standard green`: the command, `python3 -m repo_standard`, or the
skeleton Makefile's `$(REPO_STANDARD)`."""
_FLAGS = r"(?:\s+--?[\w-]+(?:[= ](?!-)\S+)?)*"
DEPLOY = {
    "aws s3 sync": rf"\baws{_FLAGS}\s+s3{_FLAGS}\s+sync\b",
    "aws cloudfront create-invalidation": (
        rf"\baws{_FLAGS}\s+cloudfront{_FLAGS}\s+create-invalidation\b"
    ),
    "sam deploy": rf"\bsam{_FLAGS}\s+deploy\b",
    "terraform apply": rf"\bterraform{_FLAGS}\s+apply\b",
    "cdk deploy": rf"\bcdk{_FLAGS}\s+deploy\b",
}
"""The deploy commands conform looks for, each with the pattern that finds it: the AWS CLI's S3
sync and CloudFront invalidation, and the deploy or apply of SAM, Terraform and CDK. A global
flag may stand between the tool and its verb, as in `aws --profile prod s3 sync`."""
DEPLOYS = re.compile("|".join(f"(?P<d{at}>{one})" for at, one in enumerate(DEPLOY.values())))
SHELL_SUFFIXES = (".sh", ".bash", ".zsh", ".ksh")
SHEBANG = re.compile(r"^#!.*\b(?:ba|z|k|da)?sh\b")
COMMAND_END = re.compile(r"&&|\|\||[;|]")
GOES_ON = re.compile(r"&&|\|\||[;|]|(?<![<>&])&(?![>&])")
"""What may follow a command on its line: only `&&` stops the line when the command fails, and
`||`, `;`, `|` and a lone `&` (not the `&` of a redirect such as `2>&1`) go on."""
MAKEFLAGS = re.compile(r"^ *(?:(?:override|export)\s+)*MAKEFLAGS\s*(?:[+?!]|:{1,3})?=(.*)$", re.M)
GOES_ON_FLAG = {"i": "--ignore-errors", "k": "--keep-going"}
ARGUMENT_FLAGS = "CfIjloWOE"
"""The make flags that go on past a failing recipe line, `-i` that ignores its error and `-k` that
keeps going with the rest of the goal, and the short flags that take the rest of their word."""
CONDITIONAL = re.compile(r"^\s*(?:ifeq|ifneq|ifdef|ifndef|else|endif)\b")
SHARED_CHECK = re.compile(
    r"^\s*uses:\s*['\"]?[\w.-]+/[\w.-]+/\.github/workflows/repo-standard-check\.yml"
    r"@repo-standard-v\d+['\"]?\s*(?:#.*)?$",
    re.M,
)


class Advice(str):
    """A fault that `conform` prints as a warning, whatever the level of its rule."""


@dataclass
class Repo:
    """What the checks read of one repo, each part read once."""

    root: Path
    config: Config
    paths: list[str]
    upstream: str | None = None
    _borders: tuple[set[str], list[Fault]] | None = field(default=None, repr=False)

    def read(self, path: str) -> str:
        try:
            return (self.root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    @cached_property
    def workflows(self) -> dict[str, str]:
        return {
            path: self.read(path)
            for path in self.paths
            if path.startswith(WORKFLOWS) and path.endswith((".yml", ".yaml"))
        }

    @cached_property
    def makefiles(self) -> dict[str, str]:
        return docs_true.makefiles(self.root)

    @cached_property
    def targets(self) -> set[str]:
        return docs_true.targets(self.root) or set()

    @cached_property
    def features(self) -> dict[str, list[str]]:
        """Each folder of the config's `features` folder, and the paths under it from its root."""
        found: dict[str, list[str]] = {}
        for path in self.paths:
            parts = path.split("/")
            if parts[0] == self.config.features and len(parts) > 2:
                found.setdefault(parts[1], []).append("/".join(parts[2:]))
        return found

    @cached_property
    def manifests(self) -> dict[str, dict[str, Any]]:
        found = {}
        for name in self.features:
            try:
                manifest = json.loads(self.read(f"{self.config.features}/{name}/feature.json"))
            except json.JSONDecodeError:
                continue
            if isinstance(manifest, dict):
                found[name] = manifest
        return found

    def manifest_faults(self) -> list[Fault]:
        if self._borders is None:
            self._borders = borders.features(self.root, self.config, self.paths)
        return self._borders[1]

    def ownership(self) -> list[Fault]:
        if self._borders is None:
            self._borders = borders.features(self.root, self.config, self.paths)
        return borders.ownership(self.config, self.paths, self._borders[0])


def _faults(found: list[Fault]) -> list[str]:
    return [str(one) for one in sorted(found)]


def _workflows_with(repo: Repo, *words: str) -> list[str]:
    return [path for path, text in repo.workflows.items() if all(word in text for word in words)]


def _makes(text: str, target: str) -> bool:
    return re.search(rf"(?:^|[\s;&|'\"]){re.escape(f'make {target}')}(?![\w-])", text) is not None


def place(repo: Repo) -> list[str]:
    if not repo.config.layout:
        raise Refused("the config sets no `layout`, so no file has a place")
    return _faults([one for one in repo.ownership() if "outside" in one.why])


def owner(repo: Repo) -> list[str]:
    if not repo.config.owners:
        raise Refused("the config sets no `owners`, so the repo owns no path")
    return _faults([one for one in repo.ownership() if "outside" not in one.why])


def own_folder(repo: Repo) -> list[str]:
    where = repo.config.part("manifest-schema")
    try:
        rules = json.loads(repo.read(where))
    except json.JSONDecodeError as error:
        return [f"{where}: is not JSON: {error.msg}"]
    if not isinstance(rules, dict) or rules.get("additionalProperties") is not False:
        return [f"{where}: is open, so a manifest could add a key that claims a path"]
    return []


def one_feature(repo: Repo) -> list[str]:
    on = _workflows_with(repo, "pull_request", "labeled", "unlabeled")
    if on:
        return []
    return ["no workflow runs again when a pull request's labels change (`labeled`, `unlabeled`)"]


def named_folders(repo: Repo) -> list[str]:
    top = repo.config.features
    faults = [
        f"{top}/{name}/feature.json: page {page} is not in docs/"
        for name, manifest in sorted(repo.manifests.items())
        for page in manifest.get("docs", [])
        if isinstance(page, str) and not page.startswith("docs/")
    ]
    return faults + [
        f"{top}/{name}/{path}: a test outside tests/"
        for name, inner in sorted(repo.features.items())
        for path in inner
        if path.endswith(".py")
        and TEST_FILE.match(PurePosixPath(path).name)
        and "tests" not in path.split("/")[:-1]
    ]


def manifest(repo: Repo) -> list[str]:
    return _faults(repo.manifest_faults())


def _declared(value: Any, key: str = "") -> list[str]:
    """The paths a manifest declares in its folder: a string in a list, or a `script`, that holds
    a `/`. `reads` names files across the repo, and `declared` reads it apart."""
    if isinstance(value, dict):
        return [one for k, v in value.items() if k != "reads" for one in _declared(v, k)]
    if isinstance(value, list):
        found = [one for v in value if not isinstance(v, str) for one in _declared(v)]
        return found + [v for v in value if isinstance(v, str) and "/" in v and " " not in v]
    if key == "script" and isinstance(value, str):
        return [value]
    return []


def declared(repo: Repo) -> list[str]:
    faults = []
    for name, manifest in sorted(repo.manifests.items()):
        held = set(repo.features[name])
        for path in _declared(manifest):
            path = path.rstrip("/")
            if path not in held and not any(one.startswith(f"{path}/") for one in held):
                where = f"{repo.config.features}/{name}/feature.json"
                faults.append(f"{where}: declares {path}, which is not there")
        reads = manifest.get("reads", [])
        for glob in reads if isinstance(reads, list) else []:
            if isinstance(glob, str) and not fnmatch.filter(repo.paths, glob):
                where = f"{repo.config.features}/{name}/feature.json"
                faults.append(f"{where}: reads {glob}, which matches no file")
    return faults


def one_name(repo: Repo) -> list[str]:
    faults, seen = [], {}
    for name, inner in sorted(repo.features.items()):
        for path in inner:
            if PurePosixPath(path).name != "SKILL.md":
                continue
            where = f"{repo.config.features}/{name}/{path}"
            found = FRONT_NAME.match(repo.read(where))
            folder = PurePosixPath(where).parent.name
            if not found:
                faults.append(f"{where}: names no skill in its front matter")
                continue
            skill = found[1].strip()
            if skill not in (folder, name):
                faults.append(f"{where}: names {skill}, not its folder {folder}")
            if skill in seen:
                faults.append(f"{where}: names {skill}, as {seen[skill]} does")
            seen.setdefault(skill, where)
    return faults


def generated(repo: Repo) -> list[str]:
    if not repo.config.part("generators"):
        return ["the config's `generators` is empty, so no index is generated"]
    return []


def fresh(repo: Repo) -> list[str]:
    return _faults(stale.check(repo.root, repo.config))


def pages_home(repo: Repo) -> list[str]:
    faults = []
    for name, inner in sorted(repo.features.items()):
        listed = repo.manifests.get(name, {}).get("docs", [])
        top = [page for page in inner if re.fullmatch(r"docs/[^/]+\.md", page)]
        where = f"{repo.config.features}/{name}/feature.json"
        if top and not listed:
            faults.append(f"{where}: lists none of its pages, so it has no main page")
        faults += [
            f"{where}: page {page} leaves its folder"
            for page in listed
            if isinstance(page, str) and ".." in PurePosixPath(page).parts
        ]
    return faults


def no_index(repo: Repo) -> list[str]:
    names = sorted(repo.features)
    if len(names) < 2:
        return []
    faults = []
    for name, inner in sorted(repo.features.items()):
        for path in inner:
            if not path.endswith(".md"):
                continue
            where = f"{repo.config.features}/{name}/{path}"
            text = repo.read(where)
            if all(f"{repo.config.features}/{other}/" in text for other in names):
                faults.append(f"{where}: lists every feature, an index no feature owns")
    return faults


def docs_true_(repo: Repo) -> list[str]:
    return _faults(docs_true.check(repo.root, repo.config, repo.paths))


def make_targets(repo: Repo) -> list[str]:
    lacking = [one for one in ("lint", "test", "check") if one not in repo.targets]
    faults = [f"Makefile: has no `{one}` target" for one in lacking]
    for root in (
        r for one in repo.config.stacks.values() if one.adapter == "node-vite" for r in one.roots
    ):
        faults += _npm_root(repo, root)
    return faults


def _npm_root(repo: Repo, root: str) -> list[str]:
    """A node-vite root's faults: `make lint` runs its package's `check` script and `make test`
    its `test` script, and CI's setup reads its Node version from `.nvmrc` or `engines.node`."""
    where = "package.json" if root == "." else f"{root}/package.json"
    try:
        package = json.loads(repo.read(where))
    except json.JSONDecodeError:
        package = None
    if not isinstance(package, dict):
        return [f"{where}: is not there, or is not a JSON object, so the stack has no scripts"]
    scripts = package.get("scripts")
    scripts = scripts if isinstance(scripts, dict) else {}
    faults: list[str] = [
        f"{where}: has no `{name}` script, which `make {target}` runs"
        for name, target in (("check", "lint"), ("test", "test"))
        if not isinstance(scripts.get(name), str) or not scripts[name].strip()
    ]
    engines = package.get("engines")
    pinned = isinstance(engines, dict) and bool(engines.get("node"))
    nvmrc = ".nvmrc" if root == "." else f"{root}/.nvmrc"
    if not pinned and nvmrc not in repo.paths:
        faults.append(
            Advice(
                f"{root}: pins no Node version, in `.nvmrc` or package.json `engines.node`,"
                " so CI runs the runner's Node"
            )
        )
    return faults


def scripts_home(repo: Repo) -> list[str]:
    faults = []
    for path, text in sorted(repo.workflows.items()):
        for script in sorted(set(RUNS_SCRIPT.findall(text))):
            top = script.split("/")[0]
            if top not in ("scripts", repo.config.features) and not script.startswith("./scripts/"):
                faults.append(f"{path}: runs {script}, outside scripts/ and the features")
    return faults


def _own_modules(repo: Repo) -> set[str]:
    found = set()
    for path in repo.paths:
        if path.endswith(".py"):
            parts = PurePosixPath(path).parts
            found.add(PurePosixPath(path).stem)
            found.update(parts[:-1])
    return found


def runner_python(repo: Repo) -> list[str]:
    known = set(sys.stdlib_module_names) | _own_modules(repo) | {"__future__"}
    faults = []
    for path, text in sorted(repo.workflows.items()):
        for script in sorted(set(BARE_PYTHON.findall(text))):
            body = repo.read(script)
            for found in IMPORT.finditer(body):
                names = [found[1]] if found[1] else found[2].split(",")
                for one in names:
                    top = one.strip().split(".")[0]
                    if top and top not in known:
                        faults.append(
                            f"{path}: runs {script} in the runner's python3, which imports {top}"
                        )
    return faults


def sizes(repo: Repo) -> list[str]:
    return _faults(size.sizes(repo.root, repo.config, repo.paths))


def comments(repo: Repo) -> list[str]:
    return _faults(size.comments(repo.root, repo.config, repo.paths))


def tests_home(repo: Repo) -> list[str]:
    seen: dict[str, str] = {}
    faults = []
    for path in repo.paths:
        name = PurePosixPath(path).name
        if TEST_FILE.match(name):
            if name in seen:
                faults.append(f"{path}: shares its name with {seen[name]}")
            seen.setdefault(name, path)
    return faults


def selects(repo: Repo) -> list[str]:
    faults = [] if "select" in repo.targets else ["Makefile: has no `select` target"]
    for name, stack in repo.config.stacks.items():
        if stack.adapter != "node-vite":
            continue
        if stack.e2e is None:
            faults.append(
                Advice(f"stack {name}: sets no `e2e:`, so no browser test runs on a pull request")
            )
        else:
            if stack.e2e.mock is None:
                faults.append(
                    Advice(
                        f"stack {name}: its e2e sets no `mock:`, so no contract holds the API its"
                        " browser tests run on to the real one"
                    )
                )
            faults += _browser(repo, stack)
    return faults


def _browser(repo: Repo, stack: Stack) -> list[str]:
    """The browser tests of a node stack that no change reaches, as the repo's own selection,
    `scripts/node_browser.py`, reads them."""
    scripts = repo.root / "scripts"
    if not (scripts / "node_browser.py").is_file():
        return ["scripts/node_browser.py: is not there, so no change selects a browser test"]
    names = ("node_browser", "node_graph", "node_table")
    saved = {name: sys.modules.pop(name) for name in names if name in sys.modules}
    sys.path.insert(0, str(scripts))
    try:
        module = importlib.import_module("node_browser")
        assert stack.e2e is not None
        suite = module.Suite(stack.roots, json.loads(stack.e2e.json()), repo.paths, repo.read)
        return list(suite.faults)
    finally:
        sys.path.remove(str(scripts))
        for name in names:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def main_runs_all(repo: Repo) -> list[str]:
    for text in repo.workflows.values():
        on_main = re.search(r"^\s*push:\s*$", text, re.M) and re.search(r"\bmain\b", text)
        runs = _makes(text, "check") or re.search(r"make test(?! *TESTS=)", text)
        if on_main and (runs or SHARED_CHECK.search(text)):
            return []
    return ["no workflow runs `make check` on a push to main"]


def pull_request_runs(repo: Repo) -> list[str]:
    for text in repo.workflows.values():
        runs = (_makes(text, "lint") and _makes(text, "test")) or SHARED_CHECK.search(text)
        if "pull_request" in text and runs:
            return []
    return ["no workflow of a pull request runs both `make lint` and `make test`"]


def gathers(repo: Repo) -> list[str]:
    for text in repo.workflows.values():
        jobs = [(found.start(), found[1]) for found in JOB.finditer(text)]
        for at, (start, name) in enumerate(jobs):
            end = jobs[at + 1][0] if at + 1 < len(jobs) else len(text)
            if name == "check" and re.search(r"^    needs:", text[start:end], re.M):
                return []
    return ["no workflow has a job named `check` that needs the other jobs"]


def deploys(repo: Repo) -> tuple[str, ...]:
    entries = repo.config.deploy
    if entries is None:
        raise Refused("the config has no `deploy` part: list each deploy entry, or `deploy: []`")
    return entries


def gated(repo: Repo) -> list[str]:
    return [
        f"deploy entry `{entry}` names neither deploy nor release, so no gate stops it"
        for entry in deploys(repo)
        if not any(word in entry.lower().replace("-", " ").split() for word in GATED)
    ]


@dataclass(frozen=True)
class Recipe:
    """One target of a make file: where its rule is, the prerequisites make runs before it (its
    order-only ones apart), and each command of its recipe with the line it starts on."""

    path: str
    line: int
    target: str
    prerequisites: tuple[str, ...]
    commands: tuple[tuple[int, str], ...]


def recipes(path: str, text: str) -> list[Recipe]:
    """The targets of one make file and their recipes. A `define` block is text, not a rule, a
    line that ends in `\\` goes on to the next, and a command keeps its `@`, `-` and `+`. A
    target-specific variable adds no recipe, and a conditional's lines (`ifeq`, `else`, `endif`)
    leave the recipe open, so a command behind one is still its target's."""
    found: list[Recipe] = []
    lines = text.splitlines()
    at, defining, current = 0, False, []
    while at < len(lines):
        start, line = at + 1, lines[at]
        while line.endswith("\\") and at + 1 < len(lines):
            at += 1
            line = line[:-1] + " " + lines[at].lstrip("\t ")
        at += 1
        if defining:
            defining = not re.match(r"^\s*endef\b", line)
            continue
        if re.match(r"^\s*define\b", line):
            defining, current = True, []
            continue
        if line.startswith("\t") and current:
            command = line[1:].lstrip()
            if command.strip() and not command.lstrip(" @-+").startswith("#"):
                for one in current:
                    found[one] = replace(
                        found[one], commands=(*found[one].commands, (start, command))
                    )
            continue
        if not line.strip() or line.lstrip().startswith("#") or CONDITIONAL.match(line):
            continue
        rule = docs_true.RULE.match(line)
        rest = line[rule.end() :] if rule else ""
        if not rule or "$" in rule[1] or "=" in rest.split(";")[0]:
            current = []
            continue
        given, _, inline = rest.partition(";")
        normal = tuple(given.split("|")[0].split())
        current = []
        for target in rule[1].split():
            current.append(len(found))
            commands = ((start, inline.strip()),) if inline.strip() else ()
            found.append(Recipe(path, start, target, normal, commands))
    return found


def _recipes(repo: Repo) -> dict[str, Recipe]:
    """Each target of the Makefile and the make files it includes. A target named by several
    rules has the prerequisites of all of them and the recipe of the one that has it."""
    merged: dict[str, Recipe] = {}
    for path, text in repo.makefiles.items():
        for one in recipes(path, text):
            had = merged.get(one.target)
            if had is None:
                merged[one.target] = one
                continue
            ran = one if one.commands else had
            given = (*had.prerequisites, *one.prerequisites)
            merged[one.target] = replace(ran, prerequisites=given)
    return merged


def _deploy(text: str) -> str:
    """The deploy command a line runs, by its name in `DEPLOY`, or ``""``."""
    hit = DEPLOYS.search(text)
    return list(DEPLOY)[int(hit.lastgroup[1:])] if hit and hit.lastgroup else ""


def _entry_target(entry: str) -> str | None:
    """The one make target a deploy entry `make [flags] [VAR=value] <target>` runs, or None."""
    words = entry.split()
    if words[:1] != ["make"]:
        return None
    named = [one for one in words[1:] if not one.startswith("-") and "=" not in one]
    return named[0] if len(named) == 1 else None


def _goes_on(command: str, at: int) -> str:
    """The first operator after `at` that runs on when the command there fails: any `||`, `;` or
    lone `&` up to the line's end, since a failed command skips only the `&&` part after it and
    the next of those runs, and a `|` that pipes the command itself. ``""`` when there is none."""
    for nth, hit in enumerate(GOES_ON.finditer(command, at)):
        if hit[0] != "&&" and (hit[0] != "|" or nth == 0):
            return hit[0]
    return ""


def _goes_on_flags(words: list[str], bare_first: bool = False) -> list[str]:
    """The `-i` and `-k` flags, or their long forms, among make's words: in a short cluster such as
    `-sk`, and in a long name that make reads as one of theirs, such as `--keep`. With `bare_first`,
    as in `MAKEFLAGS`, the first word may leave out its `-`."""
    found = []
    for at, word in enumerate(words):
        if word.startswith("--"):
            name = word[2:].split("=")[0]
            found += [
                one for one in GOES_ON_FLAG.values() if len(name) > 1 and one[2:].startswith(name)
            ]
        elif word.startswith("-") or (bare_first and at == 0 and "=" not in word):
            for letter in word.lstrip("-"):
                if letter in ARGUMENT_FLAGS:
                    break
                if letter in GOES_ON_FLAG:
                    found.append(f"-{letter}")
    return found


def _makeflags(repo: Repo) -> list[str]:
    """Each `MAKEFLAGS` assignment of the make files that sets `-i` or `-k`, by where it is."""
    faults = []
    for path, text in sorted(repo.makefiles.items()):
        for hit in MAKEFLAGS.finditer(text):
            line = text.count("\n", 0, hit.start()) + 1
            faults.extend(
                f"{path}:{line}: `MAKEFLAGS` sets `{flag}`, so make goes on past a deploy "
                "entry's failing `repo-standard green`"
                for flag in dict.fromkeys(_goes_on_flags(hit[1].split(), bare_first=True))
            )
    return faults


def green_first(repo: Repo) -> list[str]:
    """Each deploy entry runs `repo-standard green` before any other command."""
    faults = []
    known = _recipes(repo)
    entries = deploys(repo)
    faults += _makeflags(repo) if entries else []
    every = [one for path, text in repo.makefiles.items() for one in recipes(path, text)]
    ignores = [one for one in every if one.target == ".IGNORE"]
    for entry in entries:
        target = _entry_target(entry)
        if target is None:
            faults.append(
                f"deploy entry `{entry}` is not `make <target>`, so conform cannot read its recipe"
            )
            continue
        faults += [
            f"deploy entry `{entry}` runs make with `{flag}`, which goes on past a failing "
            "`repo-standard green`"
            for flag in dict.fromkeys(_goes_on_flags(entry.split()[1:]))
        ]
        faults += [
            f"{one.path}:{one.line}: `.IGNORE` covers deploy entry `{entry}`, so make goes on "
            "past its failing `repo-standard green`"
            for one in ignores
            if not one.prerequisites or target in one.prerequisites
        ]
        recipe = known.get(target)
        if recipe is None:
            faults.append(f"deploy entry `{entry}`: the Makefile has no target {target}")
            continue
        where = f"{recipe.path}:{recipe.line}: deploy entry `{entry}`"
        if recipe.prerequisites:
            names = ", ".join(recipe.prerequisites)
            faults.append(f"{where} has prerequisites ({names}), which make runs before its recipe")
        first = recipe.commands[0][1] if recipe.commands else ""
        command = first.lstrip(" \t@+-")
        prefix = first[: len(first) - len(command)]
        green = GREEN.search(COMMAND_END.split(command)[0])
        if not green:
            faults.append(f"{where} does not run `repo-standard green` before its first command")
        elif "-" in prefix:
            faults.append(
                f"{where} runs `repo-standard green` on a `-` line, which make goes on past "
                "when it fails"
            )
        elif after := _goes_on(command, green.end()):
            faults.append(
                f"{where} follows `repo-standard green` with `{after}`, so its recipe goes on "
                "when it fails"
            )
    return faults


def _deploy_lines(text: str) -> list[tuple[int, str, str]]:
    """Each line of a script or workflow that is not a comment, with its number, and the deploy
    command it runs or ``""``."""
    found = []
    for at, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        found.append((at, line, _deploy(line)))
    return found


def _is_shell(repo: Repo, path: str) -> bool:
    if path.endswith(SHELL_SUFFIXES):
        return True
    if "." in PurePosixPath(path).name or path.startswith(WORKFLOWS):
        return False
    return SHEBANG.match(repo.read(path)) is not None


def deploy_commands(repo: Repo) -> list[str]:
    """Only a deploy entry's recipe, or a script that runs `repo-standard green` first, runs a
    deploy command."""
    faults = []
    entries = {_entry_target(one) for one in repo.config.deploy or ()}
    for recipe in _recipes(repo).values():
        if recipe.target in entries:
            continue
        for line, command in recipe.commands:
            said = _deploy(command)
            if said:
                faults.append(
                    f"{recipe.path}:{line}: target {recipe.target} runs {said}, "
                    "and only a deploy entry's recipe may"
                )
    for path, text in sorted(repo.workflows.items()):
        faults += [
            f"{path}:{line}: runs {said}, where a step runs a deploy entry instead"
            for line, _, said in _deploy_lines(text)
            if said
        ]
    for path in sorted(repo.paths):
        if path in repo.workflows or not _is_shell(repo, path):
            continue
        green_at = None
        for line, text, said in _deploy_lines(repo.read(path)):
            if green_at is None and GREEN.search(text):
                green_at = line
            if said and green_at is None:
                faults.append(f"{path}:{line}: runs {said} before any `repo-standard green`")
                break
    return faults


def pinned(repo: Repo) -> list[str]:
    if repo.config.standard is None:
        return ["the config pins no version: set `standard: N`, for the tag repo-standard-vN"]
    return []


def drift(repo: Repo) -> list[str]:
    """Each file the pinned version owns that is not its copy at the tag, less the `local:` ones.
    A pin of another version than the tool's is the version rule's fault, not this one's."""
    pin = repo.config.standard
    if pin != VERSION:
        return []
    feature = owned.tree(pin, repo.root, repo.upstream)
    copies = owned.files(feature, repo.config, repo.paths, owned.Kind.OWNED)
    held, faults = set(repo.paths), []
    for path, copy in sorted(copies.items()):
        if path in repo.config.local:
            continue
        if path not in held:
            faults.append(f"{path}: is not here, and {TAG}{pin} owns it")
        elif owned.masked(path, repo.read(path)) != owned.masked(path, copy.read_text("utf-8")):
            faults.append(f"{path}: differs from {TAG}{pin}'s copy")
    return [
        f"{fault}: `repo-standard upgrade --to {pin}` writes the copy, or `local:` keeps it"
        for fault in faults
    ]


def enforcer(rule: str):
    """The check of a rule the repo's own files enforce, as `enforced-by` names them."""

    def check(repo: Repo) -> list[str]:
        named = repo.config.enforced_by.get(rule, ())
        if not named:
            return [f"the config's `enforced-by` names no file that enforces {rule}"]
        tracked = set(repo.paths)
        runners = [*repo.workflows.values(), *repo.makefiles.values()]
        runners += [
            script
            for one in repo.config.stacks.values()
            for script in COMMANDS[one.adapter].scripts
        ]
        faults = []
        for path in named:
            if path not in tracked:
                faults.append(f"enforced-by: {path} is not a file git tracks")
            elif not (
                TEST_FILE.match(PurePosixPath(path).name)
                or path in repo.workflows
                or any(path in text for text in runners)
            ):
                faults.append(
                    f"enforced-by: {path} is no test, and no workflow or make target runs it"
                )
        return faults

    return check
