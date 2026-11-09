"""A launch of any role goes to the first instance of its pool that can sign in. `jbus` reads
which instances cannot (T3 Code's `Provider is not authenticated.`, as `jbus.failover` reads it)
and hands them to `jroles.pool.routes`, which skips each one for the next of the pool. The tests
run the choice over a role map in a temporary config directory, as a pass does."""

import json
from datetime import UTC, datetime

import pytest

from jroles import pool

PRIME = "claudeAgent_claude_prime"
MAP = (
    f"home: claudeAgent claude-opus-5-5 claudeAgent,{PRIME}\n"
    f"crew: claudeAgent claude-opus-5-5 claudeAgent,{PRIME}\n"
    f"scout: claudeAgent claude-sonnet-5-5 claudeAgent,{PRIME}\n"
    f"review: claudeAgent claude-opus-5-5 claudeAgent,{PRIME}\n"
)
INVENTORY = {
    "claudeAgent": {"driver": "claudeAgent", "enabled": True},
    PRIME: {"driver": "claudeAgent", "enabled": True, "config": {"homePath": "~/.claude_prime"}},
}
NOW = datetime(2026, 11, 9, 15, 13, tzinfo=UTC)
OUT = "Provider is not authenticated."


@pytest.fixture(autouse=True)
def mapped(tmp_path, monkeypatch, t3_settings):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "config" / "jstack").mkdir(parents=True)
    (tmp_path / "config" / "jstack" / "roles").write_text(MAP)
    t3_settings.write_text(json.dumps({"providerInstances": INVENTORY}))


def launched(role, out):
    (routed,) = pool.routes(role, NOW, out)
    return routed.choice.instance, routed.as_json().get("instanceId")


@pytest.mark.parametrize("role", ["home", "crew", "scout", "review"])
def test_a_signed_out_first_instance_launches_the_role_on_the_second(role):
    assert launched(role, {"claudeAgent": OUT}) == (PRIME, PRIME)


def test_a_pool_whose_every_instance_is_signed_out_launches_nothing():
    (routed,) = pool.routes("home", NOW, {"claudeAgent": OUT, PRIME: OUT})
    assert routed.choice.instance is None
    assert routed.choice.until is None
    assert routed.choice.passed == ("claudeAgent", PRIME)
    assert routed.choice.why == f"claudeAgent cannot sign in ({OUT}); {PRIME} cannot sign in ({OUT})"


def test_an_instance_that_signs_in_again_is_chosen_again_on_the_next_pass():
    assert launched("home", {"claudeAgent": OUT})[0] == PRIME
    assert launched("home", {})[0] == "claudeAgent"
    assert launched("crew", {})[0] == "claudeAgent"
