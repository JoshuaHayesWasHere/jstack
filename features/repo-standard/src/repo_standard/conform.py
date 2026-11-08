"""`repo-standard conform`: hold a repo to each rule of the standard, at the version it pins.

`RULES` has one entry for each `###` rule of `features/repo-standard/docs/standard.md`, in its
order. A rule's id is its heading's anchor, so `standard.md#<id>` is the rule's text. Each rule has
a level: a fault of an `error` rule fails the run, and a fault of a `warn` rule is printed and
fails nothing.

The repo's `.repo-standard.yml` may waive a rule with a reason. A waived rule still runs, its
faults print as `waived`, and they fail nothing. Every waiver prints with its reason, a waiver
with no reason or for no rule of the standard fails the run, and a waiver whose rule passes says
it can go.

The config pins the version as `standard: N`, the tag `repo-standard-vN` of jstack. The tool is
the standard at one version, `VERSION`, and judges by that version's rules, so a pin of another
version fails. It lists the tags of `--upstream` and says when a newer version is out, which
fails nothing: a repo moves its pin when it chooses to.

It prints one line a fault, waiver and note, then a count, and exits 1 on any error, 0 otherwise.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from repo_standard import rules
from repo_standard.config import Config, Refused
from repo_standard.rules import Repo, enforcer
from repo_standard.tree import Unreadable

VERSION = 1
TAG = "repo-standard-v"
UPSTREAM = "https://github.com/JoshuaHayesWasHere/jstack"
LIST_SECONDS = 20
COUNTED = {"error": "errors", "warn": "warnings", "waived": "waived"}

Level = Literal["error", "warn"]


@dataclass(frozen=True)
class Rule:
    id: str
    level: Level
    check: Callable[[Repo], list[str]]


def _version(repo: Repo) -> list[str]:
    pin = repo.config.standard
    if pin is None or pin == VERSION:
        return []
    return [f"the config pins v{pin}, and this tool is {TAG}{VERSION}: run the tool at {TAG}{pin}"]


def _deploy_refuses(repo: Repo) -> list[str]:
    if not rules.deploys(repo):
        return []
    return enforcer("every-deploy-entry-refuses-a-tree-that-is-not-green-main")(repo)


def _named(rule: str, level: Level = "error") -> Rule:
    return Rule(rule, level, enforcer(rule))


RULES: tuple[Rule, ...] = (
    Rule("every-file-has-a-place", "error", rules.place),
    Rule("every-path-has-one-owner", "error", rules.owner),
    Rule("a-feature-owns-its-folder-and-nothing-else", "error", rules.own_folder),
    Rule("a-change-touches-one-feature", "error", rules.one_feature),
    Rule("a-features-parts-sit-in-named-folders", "warn", rules.named_folders),
    Rule("every-feature-has-a-manifest", "error", rules.manifest),
    Rule("a-manifest-declares-only-what-exists", "error", rules.declared),
    Rule("each-item-has-one-feature-and-one-name", "error", rules.one_name),
    Rule("the-indexes-are-generated-from-the-manifests", "error", rules.generated),
    Rule("a-stale-index-fails-the-lint", "error", rules.fresh),
    Rule("a-features-pages-live-in-its-folder", "error", rules.pages_home),
    Rule("pages-that-span-every-feature-belong-to-no-feature", "warn", rules.no_index),
    Rule("the-docs-say-what-the-tree-has", "error", rules.docs_true_),
    _named("a-commands-page-matches-its-help"),
    _named("new-prose-has-one-sentence-per-line"),
    Rule("each-check-has-one-make-target", "error", rules.make_targets),
    Rule("the-repos-own-scripts-live-in-scripts", "warn", rules.scripts_home),
    Rule(
        "a-script-ci-runs-before-setup-needs-only-the-runners-python", "warn", rules.runner_python
    ),
    Rule("a-cap-on-size-only-shrinks", "error", rules.sizes),
    Rule("code-holds-no-plain-comment", "error", rules.comments),
    _named("shell-runs-on-macos-as-well-as-on-linux"),
    _named("a-test-runs-the-code"),
    Rule("a-features-tests-live-in-its-folder", "error", rules.tests_home),
    Rule("a-change-selects-its-tests", "error", rules.selects),
    _named("a-shared-path-forces-the-whole-suite"),
    Rule("main-runs-the-whole-suite-after-each-merge", "error", rules.main_runs_all),
    Rule(
        "a-pull-request-runs-the-selection-the-lint-and-the-selected-tests",
        "error",
        rules.pull_request_runs,
    ),
    Rule("one-required-check-gathers-the-rest", "error", rules.gathers),
    _named("a-pair-of-trees-passes-once", "warn"),
    _named("a-passing-tree-leaves-a-marker", "warn"),
    Rule("every-deploy-entry-refuses-a-tree-that-is-not-green-main", "error", _deploy_refuses),
    Rule("a-deploy-is-behind-the-touches-prod-gate", "error", rules.gated),
    Rule("the-standard-is-versioned-by-a-tag", "error", rules.pinned),
    Rule("a-breaking-change-takes-a-new-version", "error", _version),
)


def newest(upstream: str) -> int | str:
    """The highest N of the upstream's `repo-standard-vN` tags, 0 with none, or why not known."""
    command = ["git", "ls-remote", "--tags", "--refs", upstream, f"refs/tags/{TAG}*"]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        listed = subprocess.run(
            command, capture_output=True, text=True, env=env, timeout=LIST_SECONDS
        )
    except subprocess.TimeoutExpired:
        return f"git ls-remote {upstream} took over {LIST_SECONDS}s"
    if listed.returncode != 0:
        return f"git ls-remote {upstream} failed: {listed.stderr.strip()}"
    found = re.findall(rf"refs/tags/{re.escape(TAG)}(\d+)$", listed.stdout, re.M)
    return max((int(one) for one in found), default=0)


def _version_note(config: Config, upstream: str | None) -> list[str]:
    if upstream is None or config.standard is None:
        return []
    top = newest(upstream)
    if isinstance(top, str):
        return [f"note: cannot list the standard's versions: {top}"]
    if top > config.standard:
        pin = config.standard
        return [f"note: {TAG}{top} is out, and this repo pins v{pin}: move the pin when ready"]
    return []


def run(
    root: Path, config: Config, paths: list[str], upstream: str | None
) -> tuple[list[str], bool]:
    """Every line the run prints, and whether it failed."""
    repo = Repo(root, config, paths)
    known = {rule.id for rule in RULES}
    waived = {waiver.rule for waiver in config.waivers}
    lines, failed, counts = [], False, {"errors": 0, "warnings": 0, "waived": 0}
    for rule in RULES:
        try:
            faults = rule.check(repo)
        except (Refused, Unreadable) as refused:
            faults = [str(refused)]
        kind = "waived" if rule.id in waived else rule.level
        counts[COUNTED[kind]] += len(faults)
        failed = failed or (kind == "error" and bool(faults))
        lines += [f"{kind} {rule.id}: {fault}" for fault in faults]
        if rule.id in waived and not faults:
            lines.append(f"note {rule.id}: passes, so its waiver can go")
    for waiver in config.waivers:
        if waiver.rule not in known:
            lines.append(f"error waiver {waiver.rule}: the standard has no such rule")
            failed = True
        elif not waiver.reason:
            lines.append(f"error waiver {waiver.rule}: has no reason, and a waiver needs one")
            failed = True
        else:
            lines.append(f"waiver {waiver.rule}: {waiver.reason}")
    lines += _version_note(config, upstream)
    total = ", ".join(f"{kind} {count}" for kind, count in counts.items())
    lines.append(f"conform {TAG}{VERSION}, {len(RULES)} rules: {total}")
    return lines, failed


def listing() -> list[str]:
    return [f"{rule.level} {rule.id}" for rule in RULES]
