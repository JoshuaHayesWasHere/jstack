"""Each TLA+ model under `features/` has a verify skill that says which code it describes and the
commit at which someone last read that code against it.

A model check keeps passing while the code it describes changes under it, and that pass looks like
a proof. So each model has a project skill, named in its feature's `feature.json` under
`projectSkills`, whose record names the model (`Model:`), the commit it was last confirmed
against (`Sync:`, a full sha), and each file it covers with the names in it the model's steps
stand for (`Covers:`). An agent changing a covered file finds its model there, and
`/maintain-formal-verification-skill` diffs the covered files from the sync commit.

The test fails when a `.tla` file outside a `canary/` folder has no skill naming it, when a
skill's record names no covered file or no sync commit, and when a covered file or a name in it
is gone: a rename leaves the record pointing at code that no longer exists, and the agent who
renamed it moves the record with it. The fixture cases show each of those caught.
"""

import ast
import json
import re
from pathlib import Path

from testing.paths import REPO

READ_SET = (
    "features/*/feature.json",
    "features/*/project-skill/",
    "features/*/spec/",
    "features/*/src/",
    "features/skill-library/skills/statechart/scripts/",
)

MODEL = re.compile(r"^Model: `([^`]+\.tla)`$", re.M)
SYNC = re.compile(r"^Sync: `([0-9a-f]{40})`$", re.M)
COVERS = re.compile(r"^Covers:\n\n?((?:- .+\n)+)", re.M)
COVERED = re.compile(r"^- `([^`]+)`(?:: (.+))?$")
NAME = re.compile(r"`([^`]+)`")


def models(root: Path) -> list[str]:
    """Each `.tla` file under `features/`, by its path from `root`, but a canary's."""
    return sorted(
        str(spec.relative_to(root))
        for spec in root.glob("features/**/*.tla")
        if "canary" not in spec.relative_to(root).parts
    )


def project_skills(root: Path) -> list[Path]:
    """The SKILL.md of each project skill a feature names."""
    return [
        manifest.parent / folder / "SKILL.md"
        for manifest in sorted(root.glob("features/*/feature.json"))
        for folder in json.loads(manifest.read_text(encoding="utf-8")).get("projectSkills", [])
    ]


def covered(text: str) -> list[tuple[str, list[str]]]:
    """Each covered file of a record, with the names in it the model stands for."""
    block = COVERS.search(text)
    if block is None:
        return []
    files = []
    for line in block.group(1).splitlines():
        match = COVERED.match(line)
        if match:
            files.append((match.group(1), NAME.findall(match.group(2) or "")))
    return files


def defined(tree: ast.Module, name: str) -> bool:
    """Whether a module defines `name`: a function, a class or a name it assigns at its top
    level, or `Class.method` inside that class. A word in a comment or a string is no definition,
    so a rename that leaves the old name in a comment is still caught."""
    *outer, last = name.split(".")
    body = tree.body
    for part in outer:
        found = [n for n in body if isinstance(n, ast.ClassDef) and n.name == part]
        if not found:
            return False
        body = found[0].body
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == last:
                return True
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == last for t in targets):
                return True
    return False


def has(source: Path, name: str) -> bool:
    """Whether a covered file still has `name`: defined in a Python module, or as a word in
    any other file."""
    body = source.read_text(encoding="utf-8")
    if source.suffix == ".py":
        return defined(ast.parse(body), name)
    return re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", body) is not None


def problems(root: Path) -> list[str]:
    """What keeps the models under `root` from each having a verify skill that holds."""
    said, named = [], set()
    for skill in project_skills(root):
        text = skill.read_text(encoding="utf-8") if skill.exists() else ""
        mine = MODEL.findall(text)
        if not mine:
            continue
        where = skill.parent.relative_to(root)
        named.update(mine)
        said.extend(
            f"{where}: names {model}, which is gone"
            for model in mine
            if not (root / model).is_file()
        )
        if not SYNC.search(text):
            said.append(f"{where}: no `Sync:` line with the full sha its model was confirmed at")
        files = covered(text)
        if not files:
            said.append(f"{where}: no `Covers:` list of the files its model describes")
        for path, names in files:
            source = root / path
            if not source.is_file():
                said.append(f"{where}: covers {path}, which is gone")
                continue
            said.extend(
                f"{where}: covers `{name}` in {path}, which no longer has it"
                for name in names
                if not has(source, name)
            )
    said.extend(
        f"{model}: no verify skill names it on a `Model:` line"
        for model in models(root)
        if model not in named
    )
    return said


def test_each_model_has_a_verify_skill_whose_record_holds():
    assert problems(REPO) == []


SKILL = """---
name: verify-demo
description: Check Demo.tla.
---

# verify-demo

Model: `features/demo/spec/Demo.tla`
Sync: `{sync}`
Covers:
- `features/demo/src/demo/core.py`: `step`, `Box.move`
"""


def demo(root: Path, skill: str = SKILL, sync: str = "a" * 40) -> Path:
    feature = root / "features" / "demo"
    (feature / "spec" / "canary").mkdir(parents=True)
    (feature / "spec" / "Demo.tla").write_text("---- MODULE Demo ----\n====\n")
    (feature / "spec" / "canary" / "NoStep.tla").write_text("---- MODULE NoStep ----\n====\n")
    (feature / "src" / "demo").mkdir(parents=True)
    (feature / "src" / "demo" / "core.py").write_text(
        "def step():\n    pass\n\n\nclass Box:\n    def move(self):\n        pass\n"
    )
    (feature / "project-skill" / "verify-demo").mkdir(parents=True)
    (feature / "project-skill" / "verify-demo" / "SKILL.md").write_text(skill.format(sync=sync))
    (feature / "feature.json").write_text(
        json.dumps({"name": "demo", "projectSkills": ["project-skill/verify-demo"]})
    )
    return feature


def test_a_whole_record_passes_and_a_canary_needs_none(tmp_path):
    demo(tmp_path)
    assert problems(tmp_path) == []


def test_a_model_no_skill_names_is_caught(tmp_path):
    feature = demo(tmp_path)
    (feature / "spec" / "Other.tla").write_text("---- MODULE Other ----\n====\n")
    assert problems(tmp_path) == [
        "features/demo/spec/Other.tla: no verify skill names it on a `Model:` line"
    ]


def test_a_skill_no_feature_names_does_not_count(tmp_path):
    feature = demo(tmp_path)
    (feature / "feature.json").write_text(json.dumps({"name": "demo"}))
    assert problems(tmp_path) == [
        "features/demo/spec/Demo.tla: no verify skill names it on a `Model:` line"
    ]


def test_a_record_with_no_sync_commit_is_caught(tmp_path):
    demo(tmp_path, SKILL.replace("Sync: `{sync}`\n", ""))
    assert problems(tmp_path) == [
        "features/demo/project-skill/verify-demo: no `Sync:` line with the full sha its model"
        " was confirmed at"
    ]


def test_a_short_sync_commit_is_caught(tmp_path):
    demo(tmp_path, sync="abc1234")
    assert len(problems(tmp_path)) == 1


def test_a_record_with_no_covered_file_is_caught(tmp_path):
    demo(tmp_path, SKILL.split("Covers:")[0])
    assert problems(tmp_path) == [
        "features/demo/project-skill/verify-demo: no `Covers:` list of the files its model"
        " describes"
    ]


def test_a_covered_file_that_is_gone_is_caught(tmp_path):
    feature = demo(tmp_path)
    (feature / "src" / "demo" / "core.py").unlink()
    assert problems(tmp_path) == [
        "features/demo/project-skill/verify-demo: covers features/demo/src/demo/core.py,"
        " which is gone"
    ]


def test_a_covered_name_that_is_gone_is_caught_though_a_comment_keeps_it(tmp_path):
    feature = demo(tmp_path)
    core = feature / "src" / "demo" / "core.py"
    core.write_text(core.read_text().replace("def move(self):", "def shift(self):  # was move"))
    assert problems(tmp_path) == [
        "features/demo/project-skill/verify-demo: covers `Box.move` in"
        " features/demo/src/demo/core.py, which no longer has it"
    ]


def test_a_model_path_that_is_gone_is_caught(tmp_path):
    demo(tmp_path, SKILL.replace("Demo.tla", "Dmeo.tla"))
    assert problems(tmp_path) == [
        "features/demo/project-skill/verify-demo: names features/demo/spec/Dmeo.tla, which is gone",
        "features/demo/spec/Demo.tla: no verify skill names it on a `Model:` line",
    ]


def test_a_blank_line_after_covers_still_reads(tmp_path):
    demo(tmp_path, SKILL.replace("Covers:\n", "Covers:\n\n"))
    assert problems(tmp_path) == []
