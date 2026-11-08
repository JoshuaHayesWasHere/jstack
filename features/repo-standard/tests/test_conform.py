"""`repo-standard conform` holds a repo to each rule of the standard, at the version it pins.

A small git repo that is not jstack meets every rule, and conform passes on it. For each rule of
`features/repo-standard/docs/standard.md`, one case takes from that repo what the rule asks for,
and conform names the rule: an error fails the run, a warning prints and fails nothing. The rules
conform lists are the standard's headings, so a new rule with no check, or no case here, fails.

The cases run `repo_standard.cli.main`, the entry point of the command, which runs
`repo_standard.conform` over the checks of `repo_standard.rules`. Further cases hold its waivers
and versions, jstack itself, the step of CI's `lint` job that runs it, and the command as `uvx`
runs it from a tag of a jstack checkout.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap

import pytest

from repo_standard.cli import main
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
    "every-deploy-entry-refuses-a-tree-that-is-not-green-main": ".github/workflows/check.yml",
}
CONFIG = """\
standard: 1
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
  - [{python}, scripts/gen.py]
docs:
  pages: ["*.md", "features/*/docs/**/*.md"]
  roots: [features, scripts]
size:
  - files: ["features/*/src/**"]
    cap: 20
comments:
  files: ["features/*/src/**", "scripts/*.py"]
deploy: [make deploy]
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
MAKEFILE += "deploy:\n\ttrue\n"


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
    "a-deploy-is-behind-the-touches-prod-gate": lambda r: edit(
        r / ".repo-standard.yml", "deploy: [make deploy]", "deploy: [./ship.sh]"
    ),
    "the-standard-is-versioned-by-a-tag": lambda r: edit(
        r / ".repo-standard.yml", "standard: 1\n", ""
    ),
    "a-breaking-change-takes-a-new-version": lambda r: edit(
        r / ".repo-standard.yml", "standard: 1\n", "standard: 2\n"
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
    assert lines == [
        f"conform repo-standard-v1, {len(BREAKS)} rules: errors 0, warnings 0, waived 0"
    ]


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
        f"conform repo-standard-v1, {len(BREAKS)} rules: errors 0, warnings 0, waived 1",
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
    assert "note: repo-standard-v10 is out, and this repo pins v1: move the pin when ready" in lines


def test_the_pinned_version_as_the_newest_or_no_upstream_reports_nothing_and_fails_nothing(
    repo, tmp_path, capsys
):
    upstream = tagged(tmp_path / "jstack", 1)
    assert main(["conform", "--root", str(repo), "--upstream", str(upstream)]) == 0
    assert not [line for line in capsys.readouterr().out.splitlines() if "note" in line]
    assert main(["conform", "--root", str(repo), "--upstream", str(tmp_path / "gone")]) == 0
    said = capsys.readouterr().out
    assert "note: cannot list the standard's versions: git ls-remote" in said


def test_jstack_meets_the_standard(capsys):
    code, lines = conform(REPO, capsys)
    assert code == 0, "\n".join(lines)


def lint_steps():
    """Each `run:` of the `lint` job of check.yml, which `check` needs."""
    text = (REPO / ".github" / "workflows" / "check.yml").read_text()
    jobs = dict(re.findall(r"^  ([\w-]+):\n((?:(?:    .*)?\n)*)", text, re.M))
    assert re.search(r"^    needs:.*\blint\b", jobs["check"], re.M)
    return re.findall(r"^\s+(?:- )?run: (.+)$", jobs["lint"], re.M)


def test_the_lint_job_that_check_needs_runs_conform_and_fails_when_it_does(repo, capsys):
    (step,) = [one for one in lint_steps() if "repo-standard conform" in one]
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
    git(source, "tag", "repo-standard-v1")
    command = ["uvx", "--from", f"git+file://{source}@repo-standard-v1", "repo-standard"]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("VIRTUAL_ENV", "UV_PROJECT"))}
    ran = subprocess.run(
        [*command, "conform", "--root", str(repo), "--upstream", str(source)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert ran.stdout.splitlines()[-1].startswith("conform repo-standard-v1, ")


@pytest.mark.parametrize(
    ("line", "said"),
    [
        ("standard: v1\n", "standard is not a whole number"),
        ("waivers: none\n", "waivers is not a list"),
        ("waivers:\n  - reason: x\n", "waivers[0] names no rule"),
        ("waivers:\n  - rule: x\n    reason: y\n    until: z\n", "waivers[0] has until"),
    ],
)
def test_a_config_conform_cannot_read_exits_2_and_says_why(repo, capsys, line, said):
    edit(repo / ".repo-standard.yml", "standard: 1\n", line)
    assert main(["conform", "--root", str(repo), "--upstream", ""]) == 2
    assert said in capsys.readouterr().err


def test_python_m_repo_standard_runs_the_command(repo):
    """`python -m repo_standard`, which `repo_standard.__main__` serves, runs as the command does."""
    env = {**os.environ, "PYTHONPATH": str(REPO / "features" / "repo-standard" / "src")}
    command = [sys.executable, "-m", "repo_standard", "conform", "--upstream", ""]
    ran = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True)
    assert (ran.returncode, ran.stdout.splitlines()[-1]) == (
        0,
        f"conform repo-standard-v1, {len(BREAKS)} rules: errors 0, warnings 0, waived 0",
    )
