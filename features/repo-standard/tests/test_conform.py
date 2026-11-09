"""`repo-standard conform` holds a repo to each rule of the standard, at the version it pins.

A small git repo that is not jstack meets every rule, and conform passes on it. For each rule of
`features/repo-standard/docs/standard.md`, one case takes from that repo what the rule asks for,
and conform names the rule: an error fails the run, a warning prints and fails nothing. The rules
conform lists are the standard's headings, so a new rule with no check, or no case here, fails.

The cases run `repo_standard.cli.main`, the entry point of the command, which runs
`repo_standard.conform` over the checks of `repo_standard.rules`. Further cases hold its waivers
and versions, the config's `stacks:` part, jstack itself, the step of CI's `lint` job that runs
it, and the command as `uvx` runs it from a tag of a jstack checkout.
"""

import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import textwrap

import pytest

from repo_standard import PYTHON, TAG, VERSION, too_old
from repo_standard import conform as conform_module
from repo_standard.cli import main
from repo_standard.config import Refused, Stack, build, parse
from testing.paths import REPO

STANDARD = REPO / "features" / "repo-standard" / "docs" / "standard.md"
CORE = REPO / "schemas" / "feature.core.schema.json"
ENFORCED = {
    "a-commands-page-matches-its-help": "features/alpha/tests/test_alpha.py",
    "new-prose-has-one-sentence-per-line": "scripts/prose.py",
    "shell-runs-on-macos-as-well-as-on-linux": "features/alpha/tests/test_alpha.py",
    "a-test-runs-the-code": "features/beta/tests/test_beta.py",
    "a-shared-path-forces-the-whole-suite": "features/beta/tests/test_beta.py",
    "a-pair-of-trees-passes-once": ".github/workflows/check.yml",
    "a-passing-tree-leaves-a-marker": ".github/workflows/check.yml",
}
CONFIG = f"""\
standard: {VERSION}
features: features
manifest-schema: schemas/feature.core.schema.json
layout: [features/, schemas/, scripts/, .github/]
owners:
  INFRA:
    - Makefile
    - .repo-standard.yml
    - README.md
    - INDEX.md
    - "schemas/**"
    - "scripts/**"
    - ".github/**"
generators:
  - [{{python}}, scripts/gen.py]
docs:
  pages: ["*.md", "features/*/docs/**/*.md"]
  roots: [features, scripts]
size:
  - files: ["features/*/src/**"]
    cap: 20
comments:
  files: ["features/*/src/**", "scripts/*.py"]
deploy: [make deploy]
local:
  Makefile: the repo's own targets, written before the skeleton was
  .github/workflows/check.yml: the repo runs its own jobs, not the shared check
  .github/workflows/borders.yml: the repo checks its borders in its own lint
  scripts/generate-index.py: scripts/gen.py writes the repo's index
enforced-by:
""" + "".join(f"  {rule}: [{path}]\n" for rule, path in ENFORCED.items())
WORKFLOW = """\
name: check
on:
  pull_request:
    types: [opened, synchronize, labeled, unlabeled]
  push:
    branches: [main]
jobs:
  lint:
    runs-on: ubuntu-24.04
    steps:
      - run: python3 scripts/prose.py
      - run: make lint
  part:
    runs-on: ubuntu-24.04
    steps:
      - run: make test TESTS=features/alpha/tests
  full:
    runs-on: ubuntu-24.04
    steps:
      - run: make check
  check:
    needs: [lint, part]
    runs-on: ubuntu-24.04
    steps:
      - run: "true"
"""
GENERATOR = '''\
"""Write INDEX.md, the list of the features, or with --check say whether it is current."""
import sys
from pathlib import Path

names = sorted(p.parent.name for p in Path("features").glob("*/feature.json"))
text = "".join(f"- {name}\\n" for name in names)
if "--check" in sys.argv:
    sys.exit(0 if Path("INDEX.md").read_text() == text else 1)
Path("INDEX.md").write_text(text)
'''
MAKEFILE = (
    "lint:\n\tpython3 scripts/gen.py --check\ntest check: lint\n\ttrue\nselect:\n\techo all\n"
)
MAKEFILE += "deploy:\n\t@repo-standard green\n\ttrue\n"


def git(root, *args):
    command = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def write(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text if isinstance(text, str) else json.dumps(text))


def manifest(name, **more):
    core = {"$schema": "../../schemas/feature.core.schema.json", "name": name, "description": "x."}
    return {**core, **more}


def skill(name):
    return f"---\nname: {name}\ndescription: x.\n---\n\nDoes x.\n"


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "other"
    write(
        root,
        {
            ".repo-standard.yml": CONFIG.replace("{python}", json.dumps(sys.executable)),
            ".github/workflows/check.yml": WORKFLOW,
            "schemas/feature.core.schema.json": CORE.read_text(),
            "scripts/gen.py": GENERATOR,
            "scripts/prose.py": '"""One sentence a line."""\nimport re\n',
            "Makefile": MAKEFILE,
            "README.md": "# other\n\nRun `make lint`, and see features/alpha/docs/alpha.md.\n",
            "features/alpha/feature.json": manifest("alpha", docs=["docs/alpha.md"]),
            "features/alpha/SKILL.md": skill("alpha"),
            "features/alpha/docs/alpha.md": "# alpha\n\nIt is written by scripts/gen.py.\n",
            "features/alpha/src/alpha.py": '"""Alpha."""\n\nVALUE = 1\n',
            "features/alpha/tests/test_alpha.py": "def test_alpha():\n    assert True\n",
            "features/beta/feature.json": manifest("beta"),
            "features/beta/skills/gamma/SKILL.md": skill("gamma"),
            "features/beta/tests/test_beta.py": "def test_beta():\n    assert True\n",
        },
    )
    git(root, "init", "-q", "-b", "main")
    subprocess.run([sys.executable, "scripts/gen.py"], cwd=root, check=True)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    return root


def conform(root, capsys, *more):
    code = main(["conform", "--root", str(root), "--upstream", "", *more])
    return code, capsys.readouterr().out.splitlines()


def edit(path, old, new):
    text = path.read_text()
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new))


def drop(root, name):
    (root / name).unlink()


BREAKS = {
    "every-file-has-a-place": lambda r: write(r, {"notes/stray.txt": "x\n"}),
    "every-path-has-one-owner": lambda r: edit(
        r / ".repo-standard.yml",
        '    - ".github/**"\n',
        '    - ".github/**"\n    - features/alpha/SKILL.md\n',
    ),
    "a-feature-owns-its-folder-and-nothing-else": lambda r: edit(
        r / "schemas/feature.core.schema.json",
        '"additionalProperties": false',
        '"additionalProperties": true',
    ),
    "a-change-touches-one-feature": lambda r: edit(
        r / ".github/workflows/check.yml", ", labeled, unlabeled", ""
    ),
    "a-features-parts-sit-in-named-folders": lambda r: write(
        r, {"features/alpha/test_loose.py": "def test_loose():\n    assert True\n"}
    ),
    "every-feature-has-a-manifest": lambda r: drop(r, "features/beta/feature.json"),
    "a-manifest-declares-only-what-exists": lambda r: write(
        r, {"features/beta/feature.json": manifest("beta", docs=["docs/gone.md"])}
    ),
    "each-item-has-one-feature-and-one-name": lambda r: write(
        r, {"features/beta/skills/gamma/SKILL.md": skill("delta")}
    ),
    "the-indexes-are-generated-from-the-manifests": lambda r: edit(
        r / ".repo-standard.yml",
        f"generators:\n  - [{json.dumps(sys.executable)}, scripts/gen.py]\n",
        "generators: []\n",
    ),
    "a-stale-index-fails-the-lint": lambda r: write(r, {"INDEX.md": "- alpha\n"}),
    "a-features-pages-live-in-its-folder": lambda r: write(
        r, {"features/alpha/feature.json": manifest("alpha")}
    ),
    "pages-that-span-every-feature-belong-to-no-feature": lambda r: write(
        r, {"features/alpha/docs/all.md": "See features/alpha/ and features/beta/.\n"}
    ),
    "the-docs-say-what-the-tree-has": lambda r: write(
        r, {"README.md": "# other\n\nRun scripts/gone.py.\n"}
    ),
    "each-check-has-one-make-target": lambda r: edit(r / "Makefile", "test check:", "test:"),
    "the-repos-own-scripts-live-in-scripts": lambda r: edit(
        r / ".github/workflows/check.yml", "- run: make lint", "- run: bash tools/x.sh && make lint"
    ),
    "a-script-ci-runs-before-setup-needs-only-the-runners-python": lambda r: edit(
        r / "scripts/prose.py", "import re", "import yaml"
    ),
    "a-cap-on-size-only-shrinks": lambda r: write(
        r, {"features/alpha/src/long.py": '"""Long."""\n' + "X = 1\n" * 30}
    ),
    "code-holds-no-plain-comment": lambda r: edit(
        r / "features/alpha/src/alpha.py", "VALUE = 1", "VALUE = 1  # one"
    ),
    "a-features-tests-live-in-its-folder": lambda r: write(
        r, {"features/beta/tests/test_alpha.py": "def test_twin():\n    assert True\n"}
    ),
    "a-change-selects-its-tests": lambda r: edit(r / "Makefile", "select:\n\techo all\n", ""),
    "main-runs-the-whole-suite-after-each-merge": lambda r: edit(
        r / ".github/workflows/check.yml", "  push:\n    branches: [main]\n", ""
    ),
    "a-pull-request-runs-the-selection-the-lint-and-the-selected-tests": lambda r: edit(
        r / ".github/workflows/check.yml", "make test TESTS=features/alpha/tests", "true"
    ),
    "one-required-check-gathers-the-rest": lambda r: edit(
        r / ".github/workflows/check.yml", "  check:\n    needs:", "  gather:\n    needs:"
    ),
    "every-deploy-entry-refuses-a-tree-that-is-not-green-main": lambda r: edit(
        r / "Makefile", "\t@repo-standard green\n", ""
    ),
    "only-a-deploy-entry-runs-a-deploy-command": lambda r: write(
        r, {"scripts/ship.sh": "#!/bin/sh\naws s3 sync dist s3://site\n"}
    ),
    "a-deploy-is-behind-the-touches-prod-gate": lambda r: edit(
        r / ".repo-standard.yml", "deploy: [make deploy]", "deploy: [./ship.sh]"
    ),
    "the-standard-is-versioned-by-a-tag": lambda r: edit(
        r / ".repo-standard.yml", f"standard: {VERSION}\n", ""
    ),
    "a-breaking-change-takes-a-new-version": lambda r: edit(
        r / ".repo-standard.yml", f"standard: {VERSION}\n", f"standard: {VERSION + 1}\n"
    ),
    "a-file-a-version-owns-is-that-versions-copy": lambda r: edit(
        r / ".repo-standard.yml",
        "  Makefile: the repo's own targets, written before the skeleton was\n",
        "",
    ),
}
for _rule, _path in ENFORCED.items():
    BREAKS.setdefault(
        _rule,
        lambda r, rule=_rule, path=_path: edit(
            r / ".repo-standard.yml", f"  {rule}: [{path}]\n", ""
        ),
    )


def anchor(heading):
    """A heading's anchor as GitHub writes it: lower case, punctuation gone, spaces as `-`."""
    return re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")


def rules(capsys):
    assert main(["conform", "--list"]) == 0
    return [line.split(" ", 1) for line in capsys.readouterr().out.splitlines()]


def test_conform_checks_each_rule_of_the_standard_and_each_has_a_case(capsys):
    headings = re.findall(r"^### (.+)$", STANDARD.read_text(), re.M)
    listed = rules(capsys)
    assert [rule for _, rule in listed] == [anchor(one) for one in headings]
    assert {level for level, _ in listed} == {"error", "warn"}
    assert sorted(BREAKS) == sorted(rule for _, rule in listed)


def test_a_repo_that_meets_every_rule_passes(repo, capsys):
    code, lines = conform(repo, capsys)
    assert code == 0, lines
    assert lines == [f"conform {TAG}{VERSION}, {len(BREAKS)} rules: errors 0, warnings 0, waived 0"]


@pytest.mark.parametrize("rule", sorted(BREAKS))
def test_a_repo_that_breaks_a_rule_is_named_at_the_rules_level(repo, capsys, rule):
    level = {name: at for at, name in rules(capsys)}[rule]
    BREAKS[rule](repo)
    code, lines = conform(repo, capsys)
    assert any(line.startswith(f"{level} {rule}: ") for line in lines), lines
    failed = [line for line in lines if line.startswith("error ")]
    assert code == (1 if level == "error" else 0), lines
    assert level == "warn" or failed


def test_an_enforcer_that_nothing_runs_does_not_meet_its_rule(repo, capsys):
    write(repo, {"notes.md": "a page\n"})
    git(repo, "add", "notes.md")
    edit(
        repo / ".repo-standard.yml",
        "a-test-runs-the-code: [features/beta/tests/test_beta.py]",
        "a-test-runs-the-code: [notes.md]",
    )
    code, lines = conform(repo, capsys)
    assert code == 1
    assert "error a-test-runs-the-code: enforced-by: notes.md is no test" in "\n".join(lines)


def waive(repo, *waivers):
    with (repo / ".repo-standard.yml").open("a") as config:
        config.write("waivers:\n" + "".join(textwrap.dedent(one) for one in waivers))


def test_a_waived_rule_fails_nothing_and_every_waiver_prints_with_its_reason(repo, capsys):
    BREAKS["a-change-selects-its-tests"](repo)
    waive(
        repo,
        "  - rule: a-change-selects-its-tests\n    reason: the select target lands next\n",
        "  - rule: a-test-runs-the-code\n    reason: an old waiver\n",
    )
    code, lines = conform(repo, capsys)
    assert code == 0, lines
    assert lines == [
        "note a-test-runs-the-code: passes, so its waiver can go",
        "waived a-change-selects-its-tests: Makefile: has no `select` target",
        "waiver a-change-selects-its-tests: the select target lands next",
        "waiver a-test-runs-the-code: an old waiver",
        f"conform {TAG}{VERSION}, {len(BREAKS)} rules: errors 0, warnings 0, waived 1",
    ]


@pytest.mark.parametrize(
    ("waiver", "said"),
    [
        ("  - rule: a-change-selects-its-tests\n", "has no reason, and a waiver needs one"),
        ('  - rule: a-change-selects-its-tests\n    reason: ""\n', "has no reason"),
        ("  - rule: no-such-rule\n    reason: x\n", "the standard has no such rule"),
    ],
)
def test_a_waiver_with_no_reason_or_no_rule_fails(repo, capsys, waiver, said):
    BREAKS["a-change-selects-its-tests"](repo)
    waive(repo, waiver)
    code, lines = conform(repo, capsys)
    assert code == 1
    assert any(line.startswith("error waiver ") and said in line for line in lines), lines


def test_a_local_file_with_no_reason_fails(repo, capsys):
    edit(
        repo / ".repo-standard.yml",
        "  Makefile: the repo's own targets, written before the skeleton was\n",
        '  Makefile: ""\n',
    )
    code, lines = conform(repo, capsys)
    assert code == 1
    assert "error local Makefile: has no reason, and a local file needs one" in lines, lines


def test_a_waiver_until_the_pinned_version_warns_that_it_is_due(repo, capsys):
    BREAKS["a-change-selects-its-tests"](repo)
    waive(
        repo,
        f"  - rule: a-change-selects-its-tests\n    reason: soon\n    until: {TAG}{VERSION}\n",
        f"  - rule: a-test-runs-the-code\n    reason: later\n    until: {TAG}{VERSION + 1}\n",
    )
    code, lines = conform(repo, capsys)
    assert code == 0, lines
    due = [line for line in lines if line.startswith("warn waiver ")]
    assert due == [
        f"warn waiver a-change-selects-its-tests: is until {TAG}{VERSION}, and the repo pins"
        f" v{VERSION}:"
        " meet the rule and drop the waiver"
    ]
    assert lines[-1].endswith("errors 0, warnings 1, waived 1"), lines


def test_an_owned_file_that_differs_or_is_gone_warns(repo, capsys, tmp_path):
    """The repo made from the skeleton keeps its owned files as they are, but for the runner's
    label in its caller, and conform warns of one changed and one gone."""
    skeleton = REPO / "features" / "repo-standard" / "skeleton"
    caller = (skeleton / ".github/workflows/check.yml").read_text()
    caller = caller.replace("runner: ubuntu-24.04", "runner: self-hosted-a")
    write(
        repo,
        {
            "Makefile": (skeleton / "Makefile").read_text() + "# an edit\n",
            ".github/workflows/check.yml": caller,
            "scripts/generate-index.py": (skeleton / "scripts/generate-index.py").read_text(),
        },
    )
    git(repo, "add", "-A")
    keep = "local:\n  Makefile: the repo's own targets, written before the skeleton was\n"
    keep += "  .github/workflows/check.yml: the repo runs its own jobs, not the shared check\n"
    keep += "  .github/workflows/borders.yml: the repo checks its borders in its own lint\n"
    keep += "  scripts/generate-index.py: scripts/gen.py writes the repo's index\n"
    edit(repo / ".repo-standard.yml", keep, "")
    _, lines = conform(repo, capsys)
    drift = [line for line in lines if line.startswith("warn a-file-a-version-owns")]
    assert [line.split(": ")[1:3] for line in drift] == [
        [".github/workflows/borders.yml", f"is not here, and {TAG}{VERSION} owns it"],
        ["Makefile", f"differs from {TAG}{VERSION}'s copy"],
    ], lines


def tagged(path, *versions):
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "commit", "-q", "--allow-empty", "-m", "start")
    for version in versions:
        git(path, "tag", f"repo-standard-v{version}")
    return path


def test_a_newer_version_upstream_is_reported_and_fails_nothing(repo, tmp_path, capsys):
    upstream = tagged(tmp_path / "jstack", 1, 2, 10)
    code = main(["conform", "--root", str(repo), "--upstream", str(upstream)])
    lines = capsys.readouterr().out.splitlines()
    assert code == 0, lines
    assert f"note: {TAG}10 is out, and this repo pins v{VERSION}: move the pin when ready" in lines


def test_the_pinned_version_as_the_newest_or_no_upstream_reports_nothing_and_fails_nothing(
    repo, tmp_path, capsys
):
    upstream = tagged(tmp_path / "jstack", 1)
    assert main(["conform", "--root", str(repo), "--upstream", str(upstream)]) == 0
    assert not [line for line in capsys.readouterr().out.splitlines() if "note" in line]
    assert main(["conform", "--root", str(repo), "--upstream", str(tmp_path / "gone")]) == 0
    said = capsys.readouterr().out
    assert "note: cannot list the standard's versions: git ls-remote" in said


def test_jstack_meets_the_standard_with_no_waiver(capsys):
    """jstack waives no rule: its one deploy entry, `make release`, runs `repo-standard green`
    first like any other repo's."""
    code, lines = conform(REPO, capsys)
    assert code == 0, "\n".join(lines)
    assert lines[-1].endswith(", waived 0"), lines
    assert not [line for line in lines if line.startswith(("waived ", "waiver "))], lines


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@pytest.mark.parametrize("base", ["HEAD", EMPTY_TREE])
def test_jstacks_make_select_prints_what_select_tests_selects(base):
    """From HEAD the change is empty and selects the tests every change runs, one a line; from
    the empty tree it adds every file, a shared path among them, so it selects `all`."""
    made = subprocess.run(
        ["make", "--no-print-directory", "select", f"BASE={base}"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    script = [sys.executable, "scripts/select_tests.py", base, "HEAD"]
    selected = subprocess.run(script, cwd=REPO, capture_output=True, text=True)
    assert made.returncode == 0, made.stderr
    assert made.stdout == selected.stdout
    lines = made.stdout.splitlines()
    if base == "HEAD":
        assert lines and "all" not in lines
        assert all(re.fullmatch(r"\S+/test_\w+\.py", line) for line in lines), lines
    else:
        assert lines == ["all"]


def lint_steps():
    """Each `run:` of the `lint` job of check.yml, which `check` needs."""
    text = (REPO / ".github" / "workflows" / "check.yml").read_text()
    jobs = dict(re.findall(r"^  ([\w-]+):\n((?:(?:    .*)?\n)*)", text, re.M))
    assert re.search(r"^    needs:.*\blint\b", jobs["check"], re.M)
    return re.findall(r"^\s+(?:- )?run: (.+)$", jobs["lint"], re.M)


def test_the_lint_job_that_check_needs_runs_conform_and_fails_when_it_does(repo, capsys):
    """The lint job runs conform inside its `make lint` step, so the command is make's."""
    assert any(run.startswith("make lint") for run in lint_steps())
    planned = subprocess.run(
        ["make", "-n", "--no-print-directory", "lint"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    (step,) = [one for one in planned if "repo-standard conform" in one]
    passed = subprocess.run(step, shell=True, cwd=REPO, capture_output=True, text=True)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    BREAKS["a-change-selects-its-tests"](repo)
    failed = subprocess.run(
        f"{step} --root {repo}", shell=True, cwd=REPO, capture_output=True, text=True
    )
    assert failed.returncode == 1, failed.stdout + failed.stderr


def test_uvx_runs_conform_from_a_tag_of_a_jstack_checkout(repo, tmp_path):
    if shutil.which("uvx") is None:
        pytest.fail("uvx is not on PATH, and this test runs the command the way a repo does")
    source = tmp_path / "jstack"
    listed = git(REPO, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    for name in filter(None, listed.split("\0")):
        if (REPO / name).is_file():
            (source / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, source / name)
    git(source, "init", "-q", "-b", "main")
    git(source, "add", "-A")
    git(source, "commit", "-q", "-m", "jstack")
    git(source, "tag", f"{TAG}{VERSION}")
    command = ["uvx", "--from", f"git+file://{source}@{TAG}{VERSION}", "repo-standard"]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("VIRTUAL_ENV", "UV_PROJECT"))}
    ran = subprocess.run(
        [*command, "conform", "--root", str(repo), "--upstream", str(source)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert ran.stdout.splitlines()[-1].startswith(f"conform {TAG}{VERSION}, ")


@pytest.mark.parametrize(
    ("line", "said"),
    [
        ("standard: v1\n", "standard is not a whole number"),
        ("waivers: none\n", "waivers is not a list"),
        ("waivers:\n  - reason: x\n", "waivers[0] names no rule"),
        ("waivers:\n  - rule: x\n    reason: y\n    until: z\n", "waivers[0].until is not a"),
        ("waivers:\n  - rule: x\n    reason: y\n    by: v2\n", "waivers[0] has by"),
    ],
)
def test_a_config_conform_cannot_read_exits_2_and_says_why(repo, capsys, line, said):
    edit(repo / ".repo-standard.yml", f"standard: {VERSION}\n", line)
    assert main(["conform", "--root", str(repo), "--upstream", ""]) == 2
    assert said in capsys.readouterr().err


def stacks(*rows):
    """A `stacks:` config of one stack to a row: its name, adapter and the line of its roots."""
    text = "stacks:\n"
    for name, adapter, roots in rows:
        text += f"  {name}:\n    adapter: {adapter}\n" + (f"    {roots}\n" if roots else "")
    return text


def test_a_config_of_two_stacks_over_their_own_roots_loads_into_both():
    text = stacks(("api", "go", "roots: [api]"), ("capture", "python-uv", "roots: [tools/capture]"))
    assert build(parse(text)).stacks == {
        "api": Stack("go", ("api",)),
        "capture": Stack("python-uv", ("tools/capture",)),
    }


@pytest.mark.parametrize(
    "rows",
    [
        [("api", "rust", "roots: [api]")],
        [("api", "go", "roots: []")],
        [("api", "go", None)],
        [("api", "go", "roots: [api]"), ("x", "python-uv", "roots: [api/x]")],
        [("all", "go", "roots: [.]"), ("x", "python-uv", "roots: [x]")],
        [("api", "go", "roots: [../x]")],
    ],
    ids=["unknown-adapter", "empty-roots", "no-roots", "nested-roots", "dot-root", "outside-root"],
)
def test_a_stacks_config_the_stacks_cannot_run_is_refused(rows):
    """Each stack runs its adapter over folders of the repo that no other stack owns."""
    keys = parse(stacks(*rows))
    with pytest.raises(Refused):
        build(keys)


@pytest.mark.parametrize(
    ("local", "said"),
    [
        ("local: [Makefile]\n", "local is not a map"),
        ("local:\n  ../Makefile: x\n", "local has ../Makefile, not a file"),
    ],
)
def test_a_local_part_conform_cannot_read_exits_2_and_says_why(repo, capsys, local, said):
    config = repo / ".repo-standard.yml"
    config.write_text(re.sub(r"^local:\n(?:  .*\n)*", local, config.read_text(), flags=re.M))
    assert main(["conform", "--root", str(repo), "--upstream", ""]) == 2
    assert said in capsys.readouterr().err


def test_a_python3_under_the_floor_is_refused_by_name_before_any_verb(monkeypatch, capsys):
    """`python -m repo_standard` in a python3 one minor version under `PYTHON` exits with the
    reason, naming the floor and the version it found, and `floor` at or past it says so."""
    floor = ".".join(map(str, PYTHON))
    under = (PYTHON[0], PYTHON[1] - 1, 9)
    said = (
        f"repo-standard needs python3 {floor} or later, the floor of {TAG}{VERSION}, "
        f"and this python3 is {'.'.join(map(str, under))}: put a newer python3 first on PATH"
    )
    assert too_old(under) == said
    assert too_old((*PYTHON, 0)) is None
    monkeypatch.setattr(sys, "version_info", under)
    monkeypatch.setattr(sys, "argv", ["repo_standard", "floor"])
    with pytest.raises(SystemExit) as refused:
        runpy.run_module("repo_standard", run_name="__main__")
    assert refused.value.code == said
    monkeypatch.undo()
    assert main(["floor"]) == 0
    found = ".".join(map(str, sys.version_info[:3]))
    assert capsys.readouterr().out == f"python3 {found}, at or past the floor {floor}\n"


def test_python_m_repo_standard_runs_the_command(repo):
    """`python -m repo_standard`, which `repo_standard.__main__` serves, runs as the command."""
    env = {**os.environ, "PYTHONPATH": str(REPO / "features" / "repo-standard" / "src")}
    command = [sys.executable, "-m", "repo_standard", "conform", "--upstream", ""]
    ran = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True)
    assert (ran.returncode, ran.stdout.splitlines()[-1]) == (
        0,
        f"conform {TAG}{VERSION}, {len(BREAKS)} rules: errors 0, warnings 0, waived 0",
    )


def no_owners(repo):
    config = repo / ".repo-standard.yml"
    text = config.read_text()
    config.write_text(text[: text.index("owners:")] + text[text.index("generators:") :])


def deploys_nothing(repo):
    """`deploy: []` says the repo deploys nothing, so no recipe need refuse a tree."""
    edit(repo / ".repo-standard.yml", "deploy: [make deploy]", "deploy: []")
    edit(repo / "Makefile", "\t@repo-standard green\n", "")


def one_feature_only(repo):
    shutil.rmtree(repo / "features" / "beta")
    edit(
        repo / ".repo-standard.yml",
        "[features/beta/tests/test_beta.py]",
        "[features/alpha/tests/test_alpha.py]",
    )
    subprocess.run([sys.executable, "scripts/gen.py"], cwd=repo, check=True)
    write(repo, {"features/alpha/docs/alpha.md": "# alpha\n\nAll of features/alpha/.\n"})


PASSED = f"conform {TAG}{VERSION}, 36 rules: errors 0, warnings 0, waived 0"
CALLER = f"""\
name: check
on:
  pull_request:
    types: [opened, synchronize, labeled, unlabeled]
  push:
    branches: [main]
jobs:
  standard:
    uses: owner/jstack/.github/workflows/repo-standard-check.yml@{TAG}{VERSION}
  check:
    needs: standard
    runs-on: ubuntu-24.04
    steps:
      - run: "true"
"""


def calls_the_shared_check(repo, at=f"{TAG}{VERSION}"):
    """The repo's one workflow calls the shared check, which runs its make targets."""
    write(repo, {".github/workflows/check.yml": CALLER.replace(f"{TAG}{VERSION}", at)})
    edit(repo / "Makefile", "lint:\n", "lint:\n\tpython3 scripts/prose.py\n")


def selects_in_an_included_make_file(repo):
    """The select target and its selector are named only in a make file the Makefile includes."""
    rule = "a-shared-path-forces-the-whole-suite"
    edit(repo / "Makefile", "select:\n\techo all\n", "include scripts/stack.mk\n")
    write(
        repo,
        {
            "scripts/stack.mk": "select:\n\tpython3 scripts/select.py\n",
            "scripts/select.py": '"""Print all."""\nprint("all")\n',
        },
    )
    git(repo, "add", "-A")
    edit(repo / ".repo-standard.yml", f"{rule}: [{ENFORCED[rule]}]", f"{rule}: [scripts/select.py]")
    edit(
        repo / ".repo-standard.yml",
        "local:\n",
        "local:\n  scripts/stack.mk: the repo's own\n  scripts/select.py: the repo's own\n",
    )


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (
            calls_the_shared_check,
            PASSED,
        ),
        (
            lambda r: calls_the_shared_check(r, at="repo-standard-v2-rc"),
            PASSED,
        ),
        (
            lambda r: calls_the_shared_check(r, at="main"),
            "error a-pull-request-runs-the-selection-the-lint-and-the-selected-tests: no workflow",
        ),
        (
            selects_in_an_included_make_file,
            PASSED,
        ),
        (
            lambda r: write(r, {"schemas/feature.core.schema.json": "{not json"}),
            "error a-feature-owns-its-folder-and-nothing-else: schemas/feature.core.schema.json: "
            "is not JSON",
        ),
        (
            lambda r: write(r, {"features/beta/skills/gamma/SKILL.md": "No front matter.\n"}),
            "error each-item-has-one-feature-and-one-name: features/beta/skills/gamma/SKILL.md: "
            "names no skill in its front matter",
        ),
        (
            lambda r: write(r, {"features/alpha/skills/gamma/SKILL.md": skill("gamma")}),
            "error each-item-has-one-feature-and-one-name: features/beta/skills/gamma/SKILL.md: "
            "names gamma, as features/alpha/skills/gamma/SKILL.md does",
        ),
        (
            lambda r: edit(r / ".repo-standard.yml", "deploy: [make deploy]\n", ""),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: the config has no "
            "`deploy` part",
        ),
        (
            lambda r: edit(r / ".repo-standard.yml", "[scripts/prose.py]", "[scripts/gone.py]"),
            "error new-prose-has-one-sentence-per-line: enforced-by: scripts/gone.py is not a file "
            "git tracks",
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml", "layout: [features/, schemas/, scripts/, .github/]\n", ""
            ),
            "error every-file-has-a-place: the config sets no `layout`",
        ),
        (
            no_owners,
            "error every-path-has-one-owner: the config sets no `owners`",
        ),
        (
            lambda r: write(
                r, {"features/beta/feature.json": manifest("beta", reads=["features/*/gone.sql"])}
            ),
            "error a-manifest-declares-only-what-exists: features/beta/feature.json: reads "
            "features/*/gone.sql, which matches no file",
        ),
        (
            lambda r: write(
                r, {"features/beta/feature.json": manifest("beta", reads=["features/alpha/*.md"])}
            ),
            PASSED,
        ),
        (deploys_nothing, PASSED),
        (
            lambda r: write(
                r,
                {
                    "scripts/ship.sh": "#!/bin/sh\n# aws s3 sync in a comment runs nothing\n"
                    "repo-standard green || exit 1\naws --profile prod s3 sync dist s3://site\n"
                    "aws cloudfront create-invalidation --distribution-id X --paths '/*'\n"
                },
            ),
            PASSED,
        ),
        (
            lambda r: write(r, {"scripts/ship": "#!/usr/bin/env bash\nnpx cdk deploy --all\n"}),
            "error only-a-deploy-entry-runs-a-deploy-command: scripts/ship:2: runs cdk deploy "
            "before any `repo-standard green`",
        ),
        (
            lambda r: edit(
                r / ".github/workflows/check.yml",
                "      - run: make check\n",
                "      - run: make check\n      - run: |\n          cd infra\n"
                "          terraform -chdir=prod apply -auto-approve\n",
            ),
            "error only-a-deploy-entry-runs-a-deploy-command: .github/workflows/check.yml:23: "
            "runs terraform apply, where a step runs a deploy entry instead",
        ),
        (
            lambda r: edit(r / "Makefile", "deploy:\n", "upload:\n\tsam deploy\ndeploy:\n"),
            "error only-a-deploy-entry-runs-a-deploy-command: Makefile:8: target upload runs "
            "sam deploy, and only a deploy entry's recipe may",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n",
                "upload:\nifeq ($(ENV),prod)\n\taws s3 sync dist s3://x\nendif\ndeploy:\n",
            ),
            "error only-a-deploy-entry-runs-a-deploy-command: Makefile:9: target upload runs "
            "aws s3 sync, and only a deploy entry's recipe may",
        ),
        (
            lambda r: edit(r / "Makefile", "deploy:\n", "deploy: build\n"),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` has prerequisites (build), which make runs before its recipe",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\ttrue && repo-standard green\n",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` does not run `repo-standard green` before its first command",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green || true\n",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` follows `repo-standard green` with `||`, so its recipe goes on "
            "when it fails",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green ; aws s3 sync dist s3://x\n",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` follows `repo-standard green` with `;`, so its recipe goes on "
            "when it fails",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green | tee green.log\n",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` follows `repo-standard green` with `|`, so its recipe goes on "
            "when it fails",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green & aws s3 sync dist s3://x\n",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` follows `repo-standard green` with `&`, so its recipe goes on "
            "when it fails",
        ),
        (
            lambda r: edit(r / "Makefile", "\t@repo-standard green\n", "\t@-repo-standard green\n"),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` runs `repo-standard green` on a `-` line, which make goes on past "
            "when it fails",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green && echo ok ; aws s3 sync dist s3://x\n",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` follows `repo-standard green` with `;`, so its recipe goes on "
            "when it fails",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green && true || true\n",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` follows `repo-standard green` with `||`, so its recipe goes on "
            "when it fails",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green && x & aws s3 sync dist s3://x\n",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:7: deploy "
            "entry `make deploy` follows `repo-standard green` with `&`, so its recipe goes on "
            "when it fails",
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green && a && b\n",
            ),
            PASSED,
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green && aws s3 sync dist s3://x | tee sync.log\n",
            ),
            PASSED,
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml", "deploy: [make deploy]", "deploy: [make -i deploy]"
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: deploy entry "
            "`make -i deploy` runs make with `-i`, "
            "which goes on past a failing `repo-standard green`",
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml", "deploy: [make deploy]", "deploy: [make -k deploy]"
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: deploy entry "
            "`make -k deploy` runs make with `-k`, "
            "which goes on past a failing `repo-standard green`",
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml", "deploy: [make deploy]", "deploy: [make -sk deploy]"
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: deploy entry "
            "`make -sk deploy` runs make with `-k`, "
            "which goes on past a failing `repo-standard green`",
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml",
                "deploy: [make deploy]",
                "deploy: [make --ignore-errors deploy]",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: deploy entry "
            "`make --ignore-errors deploy` runs make with `--ignore-errors`, "
            "which goes on past a failing `repo-standard green`",
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml",
                "deploy: [make deploy]",
                "deploy: [make --keep-going deploy]",
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: deploy entry "
            "`make --keep-going deploy` runs make with `--keep-going`, "
            "which goes on past a failing `repo-standard green`",
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml", "deploy: [make deploy]", "deploy: [make -s deploy]"
            ),
            PASSED,
        ),
        (
            lambda r: edit(r / "Makefile", "green\n\ttrue\n", "green\n\ttrue\n.IGNORE:\n"),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:10: "
            "`.IGNORE` covers deploy entry `make deploy`, so make goes on past its failing "
            "`repo-standard green`",
        ),
        (
            lambda r: edit(
                r / "Makefile", "green\n\ttrue\n", "green\n\ttrue\n.IGNORE: lint deploy\n"
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:10: "
            "`.IGNORE` covers deploy entry `make deploy`, so make goes on past its failing "
            "`repo-standard green`",
        ),
        (
            lambda r: edit(r / "Makefile", "green\n\ttrue\n", "green\n\ttrue\n.IGNORE: lint\n"),
            PASSED,
        ),
        (
            lambda r: edit(r / "Makefile", "lint:\n", "MAKEFLAGS += -i\nlint:\n"),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:1: "
            "`MAKEFLAGS` sets `-i`, so make goes on past a deploy entry's failing "
            "`repo-standard green`",
        ),
        (
            lambda r: edit(
                r / "Makefile", "lint:\n", "override MAKEFLAGS += --keep-going\nlint:\n"
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:1: "
            "`MAKEFLAGS` sets `--keep-going`, so make goes on past a deploy entry's failing "
            "`repo-standard green`",
        ),
        (
            lambda r: edit(r / "Makefile", "lint:\n", "MAKEFLAGS := k\nlint:\n"),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: Makefile:1: "
            "`MAKEFLAGS` sets `-k`, so make goes on past a deploy entry's failing "
            "`repo-standard green`",
        ),
        (
            lambda r: edit(
                r / "Makefile", "lint:\n", "MAKEFLAGS += -s --no-print-directory\nlint:\n"
            ),
            PASSED,
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n",
                "deploy:\n\trepo-standard green 2>&1\n",
            ),
            PASSED,
        ),
        (
            lambda r: edit(
                r / "Makefile",
                "deploy:\n\t@repo-standard green\n\ttrue\n",
                "define SHIP\ndeploy:\n\tnothing\nendef\n"
                "deploy: | .cache\n\t$(REPO_STANDARD) green && \\\n\t  aws s3 sync dist s3://x\n",
            ),
            PASSED,
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml", "deploy: [make deploy]", "deploy: [make ship]"
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: deploy entry "
            "`make ship`: the Makefile has no target ship",
        ),
        (
            lambda r: edit(
                r / ".repo-standard.yml", "deploy: [make deploy]", "deploy: [./ship.sh]"
            ),
            "error every-deploy-entry-refuses-a-tree-that-is-not-green-main: deploy entry "
            "`./ship.sh` is not `make <target>`",
        ),
        (one_feature_only, PASSED),
    ],
)
def test_each_way_a_rule_is_broken_is_named(repo, capsys, change, said):
    change(repo)
    code, lines = conform(repo, capsys)
    found = [line for line in lines if line.startswith(said)]
    assert found, lines
    assert code == (0 if said.startswith("conform ") else 1)


def test_a_tag_lookup_that_hangs_is_a_note_and_fails_nothing(repo, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(conform_module, "LIST_SECONDS", 0.001)
    upstream = tagged(tmp_path / "jstack", 1, 2)
    assert main(["conform", "--root", str(repo), "--upstream", str(upstream)]) == 0
    assert "note: cannot list the standard's versions: git ls-remote" in capsys.readouterr().out
