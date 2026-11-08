"""The feature schema is a core any repo uses, `schemas/feature.core.schema.json`, and jstack's
extension, `schemas/feature.schema.json`, which takes the core's keys by `$ref`. A manifest of
core keys alone holds to the core; each jstack key fails the core and holds to the extension;
every jstack manifest holds to the extension, and the generator's check is clean. Each verdict is
the generator's stdlib validator's and `jsonschema`'s both."""

import importlib
import json
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from testing.paths import REPO

READ_SET = ("schemas/", "features/*/feature.json")

sys.path.insert(0, str(REPO / "scripts"))

schema = importlib.import_module("jtrees.schema")

CORE_PATH = REPO / "schemas" / "feature.core.schema.json"
FEATURE_PATH = REPO / "schemas" / "feature.schema.json"
CORE = json.loads(CORE_PATH.read_text())
REGISTRY = Registry().with_resource(CORE["$id"], Resource.from_contents(CORE))
MANIFESTS = sorted((REPO / "features").glob("*/feature.json"))

JSTACK_KEYS = {
    "packages": ["src/foo"],
    "commands": {"foo": "foo.cli:main"},
    "units": ["units/foo.timer"],
    "hooks": [{"event": "Stop", "script": "hooks/x.sh", "harnesses": ["codex"]}],
    "statusLine": {"script": "hooks/limits.sh"},
    "gitHooks": [{"name": "pre-push", "script": "hooks/p.sh"}],
    "projectSkills": ["skills/foo"],
    "everyRun": ["tests/test_foo.py"],
    "needs": ["a"],
    "hidden": ["foo"],
    "nameable": ["foo-run"],
    "upstream": [{"from": "pstack/x", "to": "x", "source": "pstack"}],
}
CORE_ONLY = {"name": "foo", "description": "Does foo.", "docs": ["docs/foo.md"]}
JSTACK = CORE_ONLY | {"$schema": "../../schemas/feature.schema.json"}


def faults(instance, path):
    """The stdlib validator's faults, after it checks `jsonschema` gives the same verdict."""
    found = schema.validate(instance, schema.load(path))
    rules = json.loads(path.read_text())
    errors = list(Draft202012Validator(rules, registry=REGISTRY).iter_errors(instance))
    assert (found == []) == (errors == []), (found, errors)
    return found


def test_a_manifest_of_only_core_keys_holds_to_the_core():
    assert faults(CORE_ONLY, CORE_PATH) == []
    assert faults({"name": "foo", "description": "Does foo."}, CORE_PATH) == []
    assert faults({"name": "Foo", "description": "Does foo."}, CORE_PATH) != []


def test_jstack_adds_exactly_the_keys_this_test_covers_and_each_value_holds():
    extension = json.loads(FEATURE_PATH.read_text())["properties"]
    assert set(extension) - set(CORE["properties"]) == set(JSTACK_KEYS)
    assert faults(JSTACK | JSTACK_KEYS, FEATURE_PATH) == []
    assert faults(JSTACK | JSTACK_KEYS | {"packages": "src/foo"}, FEATURE_PATH) != []


@pytest.mark.parametrize("key", sorted(JSTACK_KEYS))
def test_a_jstack_key_fails_the_core_and_holds_to_the_extension(key):
    added = {key: JSTACK_KEYS[key]}
    assert faults(CORE_ONLY | added, CORE_PATH) == [
        f"/: has {key}, which the schema does not allow"
    ]
    assert faults(JSTACK | added, FEATURE_PATH) == []


def test_the_extension_holds_jstack_manifests_to_the_core_rules_too():
    assert faults(JSTACK | {"name": "foo-"}, FEATURE_PATH) != []
    assert faults(JSTACK | {"docs": ["foo.md"]}, FEATURE_PATH) != []


def test_every_jstack_manifest_holds_to_the_extension_and_names_its_folder():
    assert len(MANIFESTS) == 42
    for path in MANIFESTS:
        manifest = json.loads(path.read_text())
        assert faults(manifest, FEATURE_PATH) == [], path
        assert manifest["name"] == path.parent.name


def test_the_generator_check_is_clean():
    run = subprocess.run(
        [sys.executable, "scripts/generate-jstack-trees.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
