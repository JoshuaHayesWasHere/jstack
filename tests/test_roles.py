"""`jroles <role>` prints the model selection a launch of that role takes, from the role map.
It is run here as a thread runs it, against a map in a temporary config directory, and what
it prints is put into the skills' own launch blocks and held against the tool's schema."""

import json

import pytest

from jroles import ROLES
from jroles.cli import main
from test_tool_calls import LAUNCHES, errors

MAP = """# who runs on what
crew: codex gpt-5-codex
scout: claudeAgent claude-sonnet-5-5 claude-work

review: inherit
"""


@pytest.fixture
def roles(tmp_path, monkeypatch, capsys):
    """Run `jroles <role>` over a map, or over none: what it printed, on stdout and stderr."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def run(role, text=None):
        if text is not None:
            (tmp_path / "jstack").mkdir(exist_ok=True)
            (tmp_path / "jstack" / "roles").write_text(text)
        assert main([role]) == 0
        return capsys.readouterr()

    return run


def test_no_file_prints_nothing(roles):
    assert roles("crew") == ("", "")


def test_a_role_with_no_line_prints_nothing(roles):
    assert roles("home", MAP) == ("", "")


def test_an_expert_is_a_role_and_gets_what_the_map_gives_it_or_nothing(roles):
    assert roles("expert") == ("", "")
    assert roles("expert", MAP) == ("", "")
    assert roles("expert", MAP + "expert: inherit\n") == ("", "")
    given = MAP + "expert: grok grok-build\n"
    assert roles("expert", given) == ('{"provider": "grok", "model": "grok-build"}\n', "")
    assert roles("crew", given) == ('{"provider": "codex", "model": "gpt-5-codex"}\n', "")


def test_the_roles_are_the_four_threads_and_an_expert_and_no_other(roles):
    """A line for a role that is gone refuses the map, and the role cannot be asked for."""
    assert ROLES == ("crew", "scout", "review", "home", "expert")
    line = "orchestrator: claudeAgent claude-haiku-5-5"
    assert roles("crew", MAP + line + "\n") == ("", f"bad line 6: {line}\n")
    with pytest.raises(SystemExit):
        main(["orchestrator"])


def test_inherit_is_the_same_as_no_line(roles):
    assert roles("review", MAP) == ("", "")


def test_a_full_line_prints_the_selection_as_one_json_object(roles):
    assert roles("crew", MAP) == ('{"provider": "codex", "model": "gpt-5-codex"}\n', "")
    printed = roles("scout", MAP)
    assert printed.err == ""
    assert json.loads(printed.out) == {
        "provider": "claudeAgent",
        "model": "claude-sonnet-5-5",
        "instanceId": "claude-work",
        "options": [{"id": "effort", "value": "medium"}],
    }


@pytest.mark.parametrize(
    "line",
    [
        "crew codex gpt-5-codex",
        "crew: codex",
        "crew: codex gpt-5-codex an-instance more",
        "crew: inherit gpt-5-codex",
        "captain: codex gpt-5-codex",
    ],
)
def test_a_bad_line_is_said_on_stderr_and_no_role_gets_a_selection(roles, line):
    text = f"scout: grok grok-build\n# a comment\n{line}\n"
    for role in ("crew", "scout"):
        assert roles(role, text) == ("", f"bad line 3: {line}\n")


def test_a_role_named_twice_is_a_bad_line(roles):
    text = "crew: codex gpt-5-codex\ncrew: grok grok-build\n"
    assert roles("crew", text) == ("", "bad line 2: crew: grok grok-build\n")


def test_a_provider_that_is_not_one_of_the_four_is_refused(roles):
    text = "crew: opencode composer-2\nscout: grok grok-build\n"
    assert roles("crew", text) == (
        "",
        "refused crew: opencode is not Claude, Codex, Cursor or Grok\n",
    )
    assert roles("scout", text) == ('{"provider": "grok", "model": "grok-build"}\n', "")


DUAL = """review: codex gpt-6-sol effort=xhigh
review: cursor grok-4.7 effort=xhigh fast=off
"""


def test_two_review_lines_print_two_selections_in_order_each_with_its_own_option_ids(roles):
    assert roles("review", DUAL) == (
        '{"provider": "codex", "model": "gpt-6-sol", "options": [{"id": "reasoningEffort", '
        '"value": "xhigh"}]}\n'
        '{"provider": "cursor", "model": "grok-4.7", "options": [{"id": "reasoning_effort", '
        '"value": "xhigh"}, {"id": "fastMode", "value": false}]}\n',
        "",
    )
    flipped = "".join(reversed(DUAL.splitlines(keepends=True)))
    assert [json.loads(line)["provider"] for line in roles("review", flipped).out.splitlines()] == [
        "cursor",
        "codex",
    ]


def test_a_review_list_leaves_the_other_roles_one_line_each(roles):
    assert roles("crew", MAP.replace("review: inherit\n", DUAL)) == (
        '{"provider": "codex", "model": "gpt-5-codex"}\n',
        "",
    )


@pytest.mark.parametrize(
    ("line", "options"),
    [
        ("review: cursor grok-4.7", None),
        ("review: cursor grok-4.7 fast=on", [{"id": "fastMode", "value": True}]),
        ("review: cursor grok-4.7 fast=off", [{"id": "fastMode", "value": False}]),
        ("review: codex gpt-6-sol cx-work effort=max", [{"id": "reasoningEffort", "value": "max"}]),
        ("review: claudeAgent claude-opus-5-5", [{"id": "effort", "value": "medium"}]),
    ],
)
def test_each_provider_names_its_effort_and_fast_by_its_own_option_id(roles, line, options):
    selection = json.loads(roles("review", line + "\n").out)
    assert selection.get("options") == options


@pytest.mark.parametrize(
    ("line", "why"),
    [
        (
            "review: claudeAgent claude-opus-5-5 effort=xhigh",
            "effort=xhigh is not low, medium or high",
        ),
        (
            "review: codex gpt-6-sol effort=turbo",
            "effort=turbo is not low, medium, high, xhigh, max or ultra",
        ),
        ("review: cursor grok-4.7 effort=max", "effort=max is not low, medium, high or xhigh"),
        ("review: cursor grok-4.7 fast=maybe", "fast=maybe is not on or off"),
        ("review: codex gpt-6-sol fast=off", "only a Cursor line names fast"),
        ("review: grok grok-build effort=low", "a Grok line names no effort"),
    ],
)
def test_a_level_the_provider_does_not_list_refuses_every_review_line(roles, line, why):
    """One refused line refuses the list: half a list of reviewers is a review nobody chose."""
    text = f"review: codex gpt-6-sol effort=xhigh\n{line}\ncrew: grok grok-build\n"
    assert roles("review", text) == ("", f"refused review: {why}\n")
    assert roles("crew", text) == ('{"provider": "grok", "model": "grok-build"}\n', "")


@pytest.mark.parametrize(
    "line",
    [
        "review: inherit",
        "review: cursor grok-4.7 fast=off fast=on",
        "review: cursor grok-4.7 effort=low effort=high",
        "review: cursor fast=off grok-4.7",
        "review: cursor grok-4.7 speed=fast",
    ],
)
def test_inherit_beside_a_review_line_and_a_word_named_twice_are_bad_lines(roles, line):
    text = f"review: codex gpt-6-sol\n{line}\n"
    assert roles("review", text) == ("", f"bad line 2: {line}\n")


def test_a_map_that_cannot_be_read_is_said_on_stderr_and_the_launch_inherits(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tmp_path / "jstack" / "roles"
    path.mkdir(parents=True)
    assert main(["crew"]) == 0
    assert capsys.readouterr() == ("", f"cannot read {path}: Is a directory\n")
    path.rmdir()
    path.write_bytes(b"crew: codex \xff\n")
    assert main(["crew"]) == 0
    assert capsys.readouterr() == ("", f"cannot read {path}: it is not UTF-8\n")
    path.unlink()
    path.parent.rmdir()
    path.parent.write_text("")
    assert main(["crew"]) == 0
    assert capsys.readouterr() == ("", f"cannot read {path}: Not a directory\n")


def test_with_no_xdg_config_home_the_map_is_under_the_home_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".config" / "jstack").mkdir(parents=True)
    (tmp_path / ".config" / "jstack" / "roles").write_text("home: grok grok-build\n")
    assert main(["home"]) == 0
    assert capsys.readouterr().out == '{"provider": "grok", "model": "grok-build"}\n'


@pytest.mark.parametrize(("role", "text"), [("crew", MAP), ("scout", MAP), ("review", DUAL)])
def test_what_it_prints_is_a_model_selection_the_launch_tool_takes(roles, role, text):
    selections = [json.loads(line) for line in roles(role, text).out.splitlines()]
    twins = [call for call in LAUNCHES if "modelSelection" in call.given]
    assert selections
    assert twins
    for twin in twins:
        for selection in selections:
            assert errors(twin, {**twin.given, "modelSelection": selection}) == []


@pytest.mark.parametrize(
    ("line", "effort"),
    [
        ("scout: claudeAgent claude-sonnet-5-5", "medium"),
        ("scout: claudeAgent claude-sonnet-5-5 effort=medium", "medium"),
        ("scout: claudeAgent claude-sonnet-5-5 effort=low", "low"),
        ("scout: claudeAgent claude-sonnet-5-5 claude-work effort=low", "low"),
    ],
)
def test_a_claude_selection_always_names_an_effort_of_medium_or_lower(roles, line, effort):
    """T3 Code launches a model with no effort option at its own default, which is high for
    Claude Sonnet 5.5: the selection names one, so the role map never raises a thread."""
    selection = json.loads(roles("scout", line + "\n").out)
    assert selection["options"] == [{"id": "effort", "value": effort}]


@pytest.mark.parametrize("role", ["crew", "scout", "home", "expert"])
@pytest.mark.parametrize("level", ["high", "xhigh", "max", "ultracode", "ultrathink", ""])
def test_an_effort_above_medium_is_refused_and_the_launch_inherits(roles, role, level):
    """Only the review line may run a Claude thread above medium: the user said so for it."""
    text = f"{role}: claudeAgent claude-opus-5-5 effort={level}\nreview: grok grok-build\n"
    assert roles(role, text) == ("", f"refused {role}: effort={level} is not low or medium\n")
    assert roles("review", text) == ('{"provider": "grok", "model": "grok-build"}\n', "")


SONNETS = "review: claudeAgent claude-sonnet-5-5 effort=high\n" * 2


def test_two_sonnet_review_lines_at_high_print_two_selections(roles):
    """The user's word of 2026-10-20: every review is two Claude Sonnet 5.5 threads on High."""
    sonnet = (
        '{"provider": "claudeAgent", "model": "claude-sonnet-5-5", '
        '"options": [{"id": "effort", "value": "high"}]}\n'
    )
    assert roles("review", SONNETS + "crew: claudeAgent claude-sonnet-5-5\n") == (sonnet * 2, "")


@pytest.mark.parametrize("level", ["xhigh", "max", "ultrathink"])
def test_a_review_line_above_high_is_refused(roles, level):
    text = f"review: claudeAgent claude-sonnet-5-5 effort={level}\n"
    assert roles("review", text) == (
        "",
        f"refused review: effort={level} is not low, medium or high\n",
    )


def test_an_effort_comes_after_the_model_and_instance(roles):
    line = "crew: claudeAgent effort=low claude-opus-5-5"
    assert roles("crew", line + "\n") == ("", f"bad line 1: {line}\n")
    line = "crew: claudeAgent claude-opus-5-5 a b effort=low"
    assert roles("crew", line + "\n") == ("", f"bad line 1: {line}\n")


PRIME = "claudeAgent_claude_prime"
POOL_MAP = (
    f"crew: claudeAgent claude-sonnet-5-5 claudeAgent,{PRIME}\n"
    "scout: codex gpt-5-codex\n"
    f"review: claudeAgent claude-opus-5-5 {PRIME} effort=low\n"
)
INVENTORY = {
    "claudeAgent": {"driver": "claudeAgent", "enabled": True},
    PRIME: {"driver": "claudeAgent", "enabled": True, "config": {"homePath": "~/.claude_prime"}},
    "codex": {"driver": "codex", "enabled": True},
}


@pytest.fixture
def pooled(tmp_path, monkeypatch, capsys):
    """`jroles <role>` over a map of pools, the inventory, and a ledger, on a clock it is given:
    its exit code and what it printed."""
    from datetime import UTC, datetime

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("LIMITS", str(tmp_path / "state" / "limits"))
    (tmp_path / "config" / "jstack").mkdir(parents=True)
    (tmp_path / "config" / "jstack" / "roles").write_text(POOL_MAP)
    (tmp_path / "config" / "jstack" / "providers.json").write_text(json.dumps(INVENTORY))

    def ask(role, at=datetime(2026, 10, 17, 19, 45, tzinfo=UTC)):
        code = main([role], now=at)
        return code, *capsys.readouterr()

    ask.config = tmp_path / "config" / "jstack"
    return ask


def cap(instance, text):
    from datetime import UTC, datetime

    from jroles import ledger

    at = datetime(2026, 10, 17, 19, 45, tzinfo=UTC)
    ledger.write(ledger.cap_of([{"text": text}], at).record(instance))


WEEKLY = "You've hit your weekly limit · resets Oct 18, 4pm (America/New_York)"


def test_a_pool_launches_on_its_first_instance_and_says_which_and_why(pooled):
    first = {
        "provider": "claudeAgent",
        "model": "claude-sonnet-5-5",
        "instanceId": "claudeAgent",
        "options": [{"id": "effort", "value": "medium"}],
    }
    assert pooled("crew") == (
        0,
        json.dumps(first) + "\n",
        f"jroles: crew on claudeAgent: the first of claudeAgent,{PRIME} with headroom\n",
    )
    assert pooled("scout") == (0, '{"provider": "codex", "model": "gpt-5-codex"}\n', "")
    assert json.loads(pooled("review")[1])["instanceId"] == PRIME


def test_a_capped_first_instance_sends_the_role_to_the_next_until_its_reset(pooled):
    from datetime import UTC, datetime

    cap("claudeAgent", WEEKLY)
    why = "claudeAgent is capped until 2026-10-18T20:00:00+00:00"
    code, out, err = pooled("crew")
    assert (code, json.loads(out)["instanceId"], err) == (
        0,
        PRIME,
        f"jroles: crew on {PRIME}: {why}\n",
    )
    code, out, _ = pooled("crew", datetime(2026, 10, 18, 20, 1, tzinfo=UTC))
    assert json.loads(out)["instanceId"] == "claudeAgent"


def test_a_pool_with_every_instance_capped_waits_for_the_first_reset(pooled):
    cap("claudeAgent", WEEKLY)
    cap(PRIME, "You've hit your weekly limit · resets Oct 20, 4pm (America/New_York)")
    both = f"claudeAgent and {PRIME} are both capped until 2026-10-18T20:00:00+00:00"
    assert pooled("crew") == (75, "", f"jroles: crew waits: {both}\n")
    assert pooled("review")[0] == 75


def test_one_capped_review_line_holds_the_whole_list_and_the_other_launches_nothing(pooled):
    """Half a list of reviewers is a review nobody chose: every line waits for the reset."""
    (pooled.config / "roles").write_text(
        "review: codex gpt-6-sol codex effort=xhigh\n"
        f"review: claudeAgent claude-opus-5-5 claudeAgent,{PRIME}\n"
    )
    assert [json.loads(line)["provider"] for line in pooled("review")[1].splitlines()] == [
        "codex",
        "claudeAgent",
    ]
    cap("codex", WEEKLY)
    assert pooled("review") == (
        75,
        "",
        "jroles: review waits: codex is capped until 2026-10-18T20:00:00+00:00\n",
    )


def test_a_pool_grows_by_an_inventory_line_and_an_id_on_the_role_line(pooled):
    """An id the inventory does not declare under the line's provider refuses the line, and
    one more line of the inventory lets it in."""
    third = "claudeAgent_claude_third"
    (pooled.config / "roles").write_text(
        f"crew: claudeAgent claude-sonnet-5-5 claudeAgent,{PRIME},{third}\n"
    )
    assert pooled("crew") == (
        0,
        "",
        f"refused crew: {third} is no claudeAgent instance of providers.json\n",
    )
    grown = {**INVENTORY, third: {"driver": "claudeAgent", "config": {"homePath": "~/.c3"}}}
    (pooled.config / "providers.json").write_text(json.dumps(grown))
    cap("claudeAgent", WEEKLY)
    cap(PRIME, WEEKLY)
    assert json.loads(pooled("crew")[1])["instanceId"] == third


def test_a_claude_pool_never_names_a_codex_or_cursor_instance(pooled):
    (pooled.config / "roles").write_text("crew: claudeAgent claude-sonnet-5-5 claudeAgent,codex\n")
    assert pooled("crew") == (
        0,
        "",
        "refused crew: codex is no claudeAgent instance of providers.json\n",
    )


def test_with_no_inventory_the_pool_is_taken_as_written(pooled):
    (pooled.config / "providers.json").unlink()
    assert json.loads(pooled("review")[1])["instanceId"] == PRIME


@pytest.mark.parametrize("pool", ["claudeAgent,", ",claudeAgent", "claudeAgent,claudeAgent"])
def test_a_pool_that_names_an_instance_twice_or_none_is_refused(roles, pool):
    assert roles("crew", f"crew: claudeAgent claude-opus-5-5 {pool}\n") == (
        "",
        f"refused crew: the pool {pool} names an instance twice or none\n",
    )


def test_a_launch_passes_an_instance_by_at_the_headroom_and_a_move_waits_for_the_cap(pooled):
    """`jgauge limits` wrote claudeAgent at 90% of its five hours: a new crew goes to prime, a
    running thread stays (failover's choice counts only 100), and under 90 it comes back."""
    from datetime import UTC, datetime

    from jroles import ledger, pool

    at = datetime(2026, 10, 17, 19, 45, tzinfo=UTC)
    resets = int(at.timestamp()) + 3600
    ledger.write(ledger.Record("claudeAgent", "five_hour", 90, resets))
    code, out, err = pooled("crew")
    assert (code, json.loads(out)["instanceId"]) == (0, PRIME)
    assert err.startswith(f"jroles: crew on {PRIME}: claudeAgent is capped until ")
    kept = ledger.read(("claudeAgent", PRIME))
    assert pool.choose(("claudeAgent", PRIME), kept, at).instance == "claudeAgent"
    (pooled.config / "config.toml").write_text("headroom = 95\n")
    assert json.loads(pooled("crew")[1])["instanceId"] == "claudeAgent"
    (pooled.config / "config.toml").unlink()
    ledger.path().write_text(f"five_hour 89.9 {resets + 60}\n")
    assert json.loads(pooled("crew")[1])["instanceId"] == "claudeAgent"
