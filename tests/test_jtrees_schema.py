"""Every feature.json and plugin.json holds to its schema as `jsonschema` reads it, and
`jtrees.schema.validate`, the generator's stdlib validator, gives the same verdict as
`jsonschema` on a corpus of good and bad manifests."""

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from jtrees import schema  # noqa: E402

FEATURE = json.loads((REPO / "schemas" / "feature.schema.json").read_text())
PLUGIN = json.loads((REPO / "schemas" / "agent-plugins-1.0.0.plugin.schema.json").read_text())
MANIFESTS = sorted((REPO / "features").glob("*/feature.json"))


def test_the_schemas_are_draft_2020_12_and_closed():
    for rules in (FEATURE, PLUGIN):
        Draft202012Validator.check_schema(rules)
        assert rules["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert rules["additionalProperties"] is False


def test_every_feature_has_a_manifest_and_each_holds_to_the_schema():
    assert len(MANIFESTS) == 39
    for path in MANIFESTS:
        manifest = json.loads(path.read_text())
        assert list(Draft202012Validator(FEATURE).iter_errors(manifest)) == [], path
        assert manifest["name"] == path.parent.name


def test_plugin_json_holds_to_agent_plugins_1_0_0():
    plugin = json.loads((REPO / "plugin.json").read_text())
    assert list(Draft202012Validator(PLUGIN).iter_errors(plugin)) == []
    assert plugin["$schema"] == PLUGIN["$id"]


GOOD = {"$schema": "../../schemas/feature.schema.json", "name": "foo", "description": "Does foo."}
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
        "gitHooks": [{"name": "pre-push", "script": "hooks/p.sh"}],
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
    GOOD | {"upstream": [{"from": "pstack/x", "to": "x", "source": "josh"}]},
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
    [(FEATURE, one) for one in FEATURES] + [(PLUGIN, one) for one in PLUGINS],
)
def test_the_stdlib_validator_agrees_with_jsonschema(rules, instance):
    expected = list(Draft202012Validator(rules).iter_errors(instance)) == []
    assert (schema.validate(instance, rules) == []) == expected


def test_the_corpus_has_good_and_bad_of_each():
    for rules, corpus in ((FEATURE, FEATURES), (PLUGIN, PLUGINS)):
        verdicts = {list(Draft202012Validator(rules).iter_errors(one)) == [] for one in corpus}
        assert verdicts == {True, False}


def test_a_schema_with_a_keyword_outside_the_subset_is_refused():
    with pytest.raises(
        schema.Unsupported, match="/properties/a: keywords outside the subset: minimum"
    ):
        schema.validate({}, {"properties": {"a": {"minimum": 1}}})
