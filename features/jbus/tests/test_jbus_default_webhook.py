"""A `webhook_url` and `webhook_key` above the first `[[project]]` are the webhook of every
project that has none of its own. A project's own pair wins whole, and half a pair of its own
is refused.

Every test loads a config written into the made-up config directory of `test_jbus_kitchen`
with the real `jbus.load`, and `project add` is the real command.
"""

import json

import pytest

import jbus
from test_jbus_kitchen import PROJECT

URL = "https://example.test/hooks/jbus-default"
KEY = "default-key-0123456789"
OWN_URL = "https://example.test/hooks/demo-own"
OWN_KEY = "own-key-9876543210"


def table(kitchen, name, *own):
    checkout = kitchen.root / name
    lines = [
        "[[project]]",
        f"name = {json.dumps(name)}",
        f"checkout = {json.dumps(str(checkout))}",
        f"projectId = {json.dumps(PROJECT + name)}",
    ]
    return "\n".join([*lines, *own])


TOP = (f"webhook_url = {json.dumps(URL)}", f'webhook_key = "{KEY}"')


def write(kitchen, *tables, top=TOP):
    head = [f"server = {json.dumps(kitchen.t3.url)}", *top]
    text = "\n".join(head) + "\n" + "\n".join(tables) + "\n"
    kitchen.write(kitchen.config_dir / "config.toml", text)


def pairs(config):
    return {one.name: (one.webhook_url, one.webhook_key) for one in config.projects}


def test_every_project_with_no_pair_of_its_own_takes_the_top_level_pair(kitchen):
    write(kitchen, table(kitchen, "one"), table(kitchen, "two"))
    assert pairs(jbus.load()) == {"one": (URL, KEY), "two": (URL, KEY)}


def test_a_project_with_its_own_pair_keeps_it_whole(kitchen):
    own = (f"webhook_url = {json.dumps(OWN_URL)}", f'webhook_key = "{OWN_KEY}"')
    write(kitchen, table(kitchen, "demo", *own), table(kitchen, "two"))
    assert pairs(jbus.load()) == {"demo": (OWN_URL, OWN_KEY), "two": (URL, KEY)}


@pytest.mark.parametrize(
    ("own", "missing"),
    [
        (f"webhook_url = {json.dumps(OWN_URL)}", "webhook_key"),
        (f'webhook_key = "{OWN_KEY}"', "webhook_url"),
    ],
    ids=["url-alone", "key-alone"],
)
def test_half_a_pair_of_its_own_is_refused_with_one_line_and_no_value(kitchen, own, missing):
    write(kitchen, table(kitchen, "demo", own), table(kitchen, "two"))
    with pytest.raises(jbus.Refused) as refused:
        jbus.load()
    line = str(refused.value)
    assert line == (
        f"refused: project demo has no {missing} of its own beside the other: "
        "give it both, or neither to take the top-level pair"
    )
    assert "\n" not in line and not {URL, KEY, OWN_URL, OWN_KEY} & set(line.split())


@pytest.mark.parametrize(
    ("top", "missing"),
    [
        ((f"webhook_url = {json.dumps(URL)}",), "webhook_key"),
        ((f'webhook_key = "{KEY}"',), "webhook_url"),
    ],
    ids=["url-alone", "key-alone"],
)
def test_half_a_top_level_pair_is_refused_the_same_way(kitchen, top, missing):
    write(kitchen, table(kitchen, "demo"), top=top)
    with pytest.raises(jbus.Refused) as refused:
        jbus.load()
    path = kitchen.config_dir / "config.toml"
    assert str(refused.value) == (
        f"refused: {path} has no top-level {missing} beside the other: give it both, or neither"
    )


def test_with_no_top_level_pair_a_project_with_none_has_no_webhook(kitchen):
    write(kitchen, table(kitchen, "demo"), top=())
    config = jbus.load()
    assert pairs(config) == {"demo": ("", "")} and config.webhook == ("", "")


def test_the_top_level_url_and_key_are_taken_out_of_a_line_whoever_holds_them(kitchen):
    own = (f"webhook_url = {json.dumps(OWN_URL)}", f'webhook_key = "{OWN_KEY}"')
    write(kitchen, table(kitchen, "demo", *own))
    config = jbus.load()
    said = f"post to {URL} with {KEY}"
    assert jbus.redact(said, config.secrets()) == "post to [redacted] with [redacted]"
    write(kitchen, table(kitchen, "one"))
    inherits = jbus.load()
    assert set(jbus.secrets(inherits.project("one"))) <= set(inherits.secrets())
    assert jbus.redact(said, jbus.secrets(inherits.project("one"))) == (
        "post to [redacted] with [redacted]"
    )


def test_project_add_writes_no_webhook_and_the_new_project_takes_the_top_level_pair(kitchen):
    write(kitchen, table(kitchen, "demo"))
    checkout = kitchen.root / "added"
    kitchen.repo(checkout, kitchen.root / "added-origin.git")
    code, _ = kitchen.main(
        "project", "add", "added", "--checkout", str(checkout), "--project-id", "p-new"
    )
    assert code == 0
    assert (
        "webhook" not in (kitchen.config_dir / "config.toml").read_text().split("[[project]]")[-1]
    )
    assert pairs(jbus.load())["added"] == (URL, KEY)


@pytest.mark.parametrize("top", [True, False], ids=["top-level", "own"])
def test_a_url_with_an_empty_key_is_refused_as_a_key_missing(kitchen, top):
    blank = (f"webhook_url = {json.dumps(URL)}", 'webhook_key = ""')
    if top:
        write(kitchen, table(kitchen, "demo"), top=blank)
        line = f"refused: {kitchen.config_dir / 'config.toml'} has no top-level webhook_key"
    else:
        write(kitchen, table(kitchen, "demo", *blank))
        line = "refused: project demo has no webhook_key of its own"
    with pytest.raises(jbus.Refused) as refused:
        jbus.load()
    assert str(refused.value).startswith(line + " beside the other")


def test_an_empty_url_beside_a_key_loads_as_no_webhook(kitchen):
    write(kitchen, table(kitchen, "demo", 'webhook_url = ""', f'webhook_key = "{OWN_KEY}"'))
    assert pairs(jbus.load()) == {"demo": ("", OWN_KEY)}


def test_a_brace_in_a_project_name_is_no_placeholder_in_the_refusal(kitchen):
    write(kitchen, table(kitchen, "a{b}x}", f'webhook_key = "{OWN_KEY}"'))
    with pytest.raises(jbus.Refused) as refused:
        jbus.load()
    assert str(refused.value).startswith("refused: project a{b}x} has no webhook_url of its own")
