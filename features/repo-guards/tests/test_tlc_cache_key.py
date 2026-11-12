"""TLC's cache key in the check reads every feature's spec folder through one glob.

The key hashes the specs, their configs and statechart's scripts. When it named each feature's
spec folder, every pull request that added a model added its folder to the same line in two
jobs, and each one that merged put the others in conflict with main on check.yml alone, with
no check run (#1710, #1711, #1716 and #1719 after #1714). `features/*/spec/**` covers a new
model with no edit to the workflow.
"""

import re

from testing.paths import REPO

FLOW = REPO / ".github/workflows/check.yml"
ONE_FEATURE = re.compile(r"'features/(?!\*/)[^/']+/spec/")


def hashing_lines() -> list[tuple[int, str]]:
    lines = FLOW.read_text(encoding="utf-8").splitlines()
    return [(n, line.strip()) for n, line in enumerate(lines, 1) if "hashFiles(" in line]


def test_no_hash_names_one_features_spec_folder():
    named = [f"line {n}: {line}" for n, line in hashing_lines() if ONE_FEATURE.search(line)]
    assert not named, (
        "a hashFiles in .github/workflows/check.yml names one feature's spec folder, so each"
        " new model edits that line: hash 'features/*/spec/**' instead.\n" + "\n".join(named)
    )


def test_each_tlc_key_hashes_every_spec():
    keys = [(n, line) for n, line in hashing_lines() if "tlc-${{ hashFiles(" in line]
    assert keys, ".github/workflows/check.yml has no TLC cache key that hashes files"
    missing = [f"line {n}: {line}" for n, line in keys if "'features/*/spec/**'" not in line]
    assert not missing, (
        "a TLC cache key in .github/workflows/check.yml leaves out 'features/*/spec/**', so a"
        " change to a spec restores runs it did not make.\n" + "\n".join(missing)
    )
