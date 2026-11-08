"""The checks behind the rules of the standard, one function a rule, each over a `Repo`.

A check returns the faults it finds, as lines of text, and an empty list when the repo meets the
rule. Some checks run a guard: a guard whose config part is missing raises `Refused`, which
`conform` records as that rule's fault. The rest read the tree: the Makefile's targets, the text of
the workflows, the manifests and the config.

A rule that no check of the tree can judge in every stack is met by the files that enforce it in
the repo, named in the config's `enforced-by`. `enforcer` holds each named file to two things: git
tracks it, and something the checks run reaches it. A test file, a workflow, and a file a workflow
or the Makefile names by its path are reached, so a page or a file nothing runs does not meet it.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Any

from repo_standard import borders, docs_true, size, stale
from repo_standard.config import Config, Refused
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


@dataclass
class Repo:
    """What the checks read of one repo, each part read once."""

    root: Path
    config: Config
    paths: list[str]
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
    """The paths a manifest declares: a string in a list, or a `script`, that holds a `/`."""
    if isinstance(value, dict):
        return [one for k, v in value.items() for one in _declared(v, k)]
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
    return [f"Makefile: has no `{one}` target" for one in lacking]


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
    return [] if "select" in repo.targets else ["Makefile: has no `select` target"]


def main_runs_all(repo: Repo) -> list[str]:
    for text in repo.workflows.values():
        on_main = re.search(r"^\s*push:\s*$", text, re.M) and re.search(r"\bmain\b", text)
        if on_main and (_makes(text, "check") or re.search(r"make test(?! *TESTS=)", text)):
            return []
    return ["no workflow runs `make check` on a push to main"]


def pull_request_runs(repo: Repo) -> list[str]:
    for text in repo.workflows.values():
        if "pull_request" in text and _makes(text, "lint") and _makes(text, "test"):
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


def pinned(repo: Repo) -> list[str]:
    if repo.config.standard is None:
        return ["the config pins no version: set `standard: N`, for the tag repo-standard-vN"]
    return []


def enforcer(rule: str):
    """The check of a rule the repo's own files enforce, as `enforced-by` names them."""

    def check(repo: Repo) -> list[str]:
        named = repo.config.enforced_by.get(rule, ())
        if not named:
            return [f"the config's `enforced-by` names no file that enforces {rule}"]
        tracked = set(repo.paths)
        runners = [*repo.workflows.values(), repo.read("Makefile")]
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
