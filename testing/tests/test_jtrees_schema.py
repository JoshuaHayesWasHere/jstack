"""`jtrees.schema.validate`, the generator's stdlib validator, gives the same verdict as
`jsonschema` on a corpus of good and bad manifests, with each schema's `$ref`s resolved by
`jtrees.schema.load` on one side and by a `referencing` registry on the other, and plugin.json
holds to its schema."""

import importlib
import json
import sys

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from testing.paths import REPO

sys.path.insert(0, str(REPO / "scripts"))

schema = importlib.import_module("jtrees.schema")

SCHEMAS = REPO / "schemas"
CORE = json.loads((SCHEMAS / "feature.core.schema.json").read_text())
FEATURE = json.loads((SCHEMAS / "feature.schema.json").read_text())
PLUGIN = json.loads((SCHEMAS / "agent-plugins-1.0.0.plugin.schema.json").read_text())
REGISTRY = Registry().with_resource(CORE["$id"], Resource.from_contents(CORE))
LOADED = {
    rules["$id"]: schema.load(SCHEMAS / name)
    for rules, name in (
        (CORE, "feature.core.schema.json"),
        (FEATURE, "feature.schema.json"),
        (PLUGIN, "agent-plugins-1.0.0.plugin.schema.json"),
    )
}


def holds(instance, rules):
    """`jsonschema`'s verdict on `instance`."""
    return list(Draft202012Validator(rules, registry=REGISTRY).iter_errors(instance)) == []


def test_the_schemas_are_draft_2020_12_and_closed():
    for rules in (CORE, FEATURE, PLUGIN):
        Draft202012Validator.check_schema(rules)
        assert rules["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert rules["additionalProperties"] is False


def test_plugin_json_holds_to_agent_plugins_1_0_0():
    plugin = json.loads((REPO / "plugin.json").read_text())
    assert holds(plugin, PLUGIN)
    assert plugin["$schema"] == PLUGIN["$id"]


GOOD = {"$schema": "../../schemas/feature.schema.json", "name": "foo", "description": "Does foo."}
CORES = [
    {"name": "foo", "description": "Does foo."},
    {"$schema": "x.json", "name": "foo", "description": "Does foo.", "docs": ["docs/foo.md"]},
    {"name": "foo"},
    {"name": "foo", "description": "Does foo.", "docs": ["foo.md"]},
    {"name": "foo", "description": "Does foo.", "packages": ["src/foo"]},
    {"$schema": "", "name": "foo", "description": "Does foo."},
]
FEATURES = [
    GOOD,
    GOOD | {"packages": ["src/foo"], "commands": {"foo": "foo.cli:main"}, "docs": ["docs/foo.md"]},
    GOOD
    | {
        "hooks": [
            {
                "event": "PreToolUse",
                "matcher": "Bash",
                "script": "hooks/x.sh",
                "harnesses": ["codex"],
                "refuses": True,
            }
        ]
    },
    GOOD
    | {
        "statusLine": {"script": "hooks/limits.sh"},
        "gitHooks": [
            {"name": "pre-push", "script": "hooks/p.sh"},
            {"name": "commit-msg", "script": "hooks/m.sh"},
        ],
    },
    GOOD
    | {"upstream": [{"from": "pstack/skills/x/SKILL.md", "to": "SKILL.md", "source": "adapted"}]},
    GOOD
    | {
        "owns": ["src/foo/**"],
        "nameable": ["foo-run"],
        "everyRun": ["tests/test_foo.py"],
        "needs": ["a"],
    },
    GOOD | {"units": ["templates/foo.service", "units/foo.timer"]},
    {},
    [],
    "foo",
    GOOD | {"name": "Foo"},
    GOOD | {"name": "foo-"},
    GOOD | {"name": "f" * 65},
    GOOD | {"description": ""},
    GOOD | {"description": 1},
    GOOD | {"$schema": "schemas/feature.schema.json"},
    GOOD | {"extra": True},
    {"name": "foo", "description": "x"},
    GOOD | {"packages": "src/foo"},
    GOOD | {"packages": ["foo"]},
    GOOD | {"commands": {"foo": "foo"}},
    GOOD | {"commands": {"foo": 1}},
    GOOD | {"hooks": [{"event": "Stop", "script": "hooks/x.sh", "harnesses": []}]},
    GOOD | {"hooks": [{"event": "PreToolUse", "script": "hooks/x.sh"}]},
    GOOD | {"hooks": [{"event": "PreToolUse", "script": "hooks/x.sh", "harnesses": ["grok"]}]},
    GOOD
    | {"hooks": [{"event": "PreToolUse", "script": "hooks/x.sh", "harnesses": [], "refuses": 1}]},
    GOOD
    | {"hooks": [{"event": "PreToolUse", "script": "hooks/x.sh", "harnesses": [], "matcher": ""}]},
    GOOD | {"statusLine": {}},
    GOOD | {"gitHooks": [{"name": "pre-commit", "script": "hooks/p.sh"}]},
    GOOD | {"upstream": [{"from": "elsewhere/x", "to": "x", "source": "pstack"}]},
    GOOD | {"upstream": [{"from": "pstack/x", "to": "x", "source": "jstack"}]},
    GOOD | {"units": ["foo.service"]},
    GOOD | {"owns": [""]},
    GOOD | {"nameable": ["Foo Run"]},
]
PLUGINS = [
    json.loads((REPO / "plugin.json").read_text()),
    {"$schema": PLUGIN["$id"], "name": "x"},
    {"$schema": PLUGIN["$id"], "name": "x", "extensions": {"com.example": {}}},
    {"$schema": PLUGIN["$id"]},
    {"$schema": "https://example.com", "name": "x"},
    {"$schema": PLUGIN["$id"], "name": "a--b"},
    {"$schema": PLUGIN["$id"], "name": ""},
    {"$schema": PLUGIN["$id"], "name": "x", "skills": []},
    {"$schema": PLUGIN["$id"], "name": "x", "author": {"name": "a", "x": 1}},
    {"$schema": PLUGIN["$id"], "name": "x", "keywords": [1]},
    {"$schema": PLUGIN["$id"], "name": "x", "extensions": {"com.example": []}},
]


@pytest.mark.parametrize(
    ("rules", "instance"),
    [(CORE, one) for one in CORES]
    + [(FEATURE, one) for one in FEATURES]
    + [(PLUGIN, one) for one in PLUGINS],
)
def test_the_stdlib_validator_agrees_with_jsonschema(rules, instance):
    assert (schema.validate(instance, LOADED[rules["$id"]]) == []) == holds(instance, rules)


def test_the_corpus_has_good_and_bad_of_each():
    for rules, corpus in ((CORE, CORES), (FEATURE, FEATURES), (PLUGIN, PLUGINS)):
        assert {holds(one, rules) for one in corpus} == {True, False}


def test_a_schema_with_a_keyword_outside_the_subset_is_refused():
    with pytest.raises(
        schema.Unsupported, match="/properties/a: keywords outside the subset: minimum"
    ):
        schema.validate({}, {"properties": {"a": {"minimum": 1}}})


def test_a_ref_beside_a_keyword_or_naming_nothing_is_refused(tmp_path):
    (tmp_path / "beside.json").write_text('{"$ref": "#/properties", "type": "object"}')
    with pytest.raises(schema.Unsupported, match="beside type"):
        schema.load(tmp_path / "beside.json")
    (tmp_path / "nothing.json").write_text('{"properties": {"a": {"$ref": "#/nowhere"}}}')
    with pytest.raises(ValueError, match="names nothing"):
        schema.load(tmp_path / "nothing.json")
