"""One setting, `wake`, picks where a project's wakes go: its home thread through T3 Code (`home`,
the default), its webhook (`webhook`), or both (`both`).

A wake to the home thread is one `t3_thread_send` in queue mode, with the chat lines and the events
a webhook POST carries (`wake.body`) and a retry key made from that body, so a retry sends the same
message. It keeps the webhook's five-minute gap. A send T3 Code refuses keeps the events in the
outbox for the next pass, and its streak alerts in the journal and on the desk.

Every test runs the real pass or the real command against the faked T3 Code server and webhook of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json

import pytest

import jbus
from jbus import wake
from test_jbus_kitchen import NOW
from test_jbus_signal import decide, later

HOME = "mcp:home-of-demo"
TOP = "mcp:top-home"


def wakes(kitchen, thread=HOME):
    """What the thread was sent as wakes, in order."""
    return [
        given
        for given in kitchen.t3.messages.values()
        if given["threadId"] == thread and given["clientRequestId"].startswith("wake|")
    ]


def waiting(kitchen):
    """What waits for the home thread."""
    return jbus.read_json(kitchen.state / "home-thread" / "outbox.json", [])


def homed(kitchen, **config):
    """Write the config with these settings, give the project's home a thread, and have a decision
    wait."""
    kitchen.config(**config)
    (kitchen.home / "home-id").write_text(HOME + "\n")
    decide(kitchen)


def test_with_no_wake_setting_and_no_webhook_the_event_reaches_the_home_thread(kitchen):
    homed(kitchen, url="", project_wake=None)
    said = kitchen.poll(NOW)
    (sent,) = wakes(kitchen)
    assert sent["mode"] == "queue"
    assert "demo: decision alpha: which one?" in sent["message"]
    body = json.loads(sent["message"].split("```json\n", 1)[1].split("\n```", 1)[0])
    assert body["kind"] == "events" and body["say"] == ["demo: decision alpha: which one?"]
    assert [one["event"] for one in body["events"]] == ["decision"]
    assert kitchen.webhook.posts == []
    assert "woke demo: 1 events" in said


def test_a_webhook_pair_with_wake_home_is_kept_and_not_posted_to(kitchen):
    homed(kitchen, wake="home", project_wake=None)
    kitchen.poll(NOW)
    assert len(wakes(kitchen)) == 1 and kitchen.webhook.posts == []
    assert jbus.load().project("demo").webhook_url


def test_wake_webhook_posts_to_the_webhook_alone(kitchen):
    homed(kitchen, wake="webhook", project_wake=None)
    kitchen.poll(NOW)
    assert wakes(kitchen) == [] and len(kitchen.webhook.posts) == 1


def test_wake_both_posts_to_the_webhook_and_sends_to_the_home_thread(kitchen):
    homed(kitchen, wake="both", project_wake=None)
    kitchen.poll(NOW)
    assert len(wakes(kitchen)) == 1 and len(kitchen.webhook.posts) == 1


def test_a_project_s_own_wake_wins_over_the_top_level_one(kitchen):
    homed(kitchen, wake="webhook", project_wake="home")
    kitchen.poll(NOW)
    assert len(wakes(kitchen)) == 1 and kitchen.webhook.posts == []


@pytest.mark.parametrize("picked", ["webhook", "both"])
def test_a_wake_that_needs_the_webhook_is_refused_without_the_pair(kitchen, picked):
    kitchen.config(wake=picked, project_wake=None)
    path = kitchen.config_dir / "config.toml"
    path.write_text(
        "\n".join(line for line in path.read_text().splitlines() if "webhook_" not in line)
    )
    with pytest.raises(jbus.Refused, match=f'wake = "{picked}"') as refused:
        jbus.load()
    assert "webhook_url" in str(refused.value)


def test_a_wake_that_is_none_of_the_three_is_refused(kitchen):
    kitchen.config(project_wake="grok")
    with pytest.raises(jbus.Refused, match="wake"):
        jbus.load()


def test_a_retry_after_a_lost_answer_keeps_one_message(kitchen):
    homed(kitchen, url="", project_wake=None)
    kitchen.t3.lose_send = True
    kitchen.poll(NOW)
    assert len(waiting(kitchen)) == 1
    kitchen.t3.lose_send = False
    kitchen.t3.messages.clear()
    kitchen.poll(later(5))
    kitchen.poll(later(10))
    (first,) = wakes(kitchen)
    assert waiting(kitchen) == []
    keys = [given["clientRequestId"] for tool, given in kitchen.t3.calls if tool.endswith("_send")]
    assert {key for key in keys if key.startswith("wake|")} == {first["clientRequestId"]}


def test_the_home_thread_gets_at_most_one_wake_in_five_minutes(kitchen):
    homed(kitchen, url="", project_wake=None)
    kitchen.poll(NOW)
    decide_again(kitchen)
    kitchen.poll(later(2))
    assert len(wakes(kitchen)) == 1
    kitchen.poll(later(5))
    assert len(wakes(kitchen)) == 2


def decide_again(kitchen):
    config = jbus.load()
    wake.Box(kitchen.state, config.project("demo")).send("beta", "decision", "decision beta: ?")


def test_t3_refusing_keeps_the_events_and_alerts_in_the_journal_and_on_the_desk(kitchen):
    homed(kitchen, url="", project_wake=None)
    kitchen.t3.refuse_send = True
    said = []
    for number in range(3):
        said += kitchen.poll(later(5 * number))
    assert wakes(kitchen) == []
    assert any(one["event"] == "decision" for one in waiting(kitchen))
    line = next(one for one in said if one.startswith("demo: alert: home thread demo failed 3"))
    assert f"jbus | {line.removeprefix('demo: ')}" in kitchen.log("notify")
    assert kitchen.main("wakes")[0] == 1
    kitchen.t3.refuse_send = False
    said = kitchen.poll(later(20))
    (sent,) = wakes(kitchen)
    assert "decision alpha" in sent["message"]
    assert any(one.startswith("demo: recovered: home thread demo") for one in said)


def test_a_failing_webhook_does_not_stop_the_home_thread_s_wakes(kitchen):
    homed(kitchen, wake="both", project_wake=None)
    kitchen.webhook.status = 400
    for number in range(3):
        kitchen.poll(later(5 * number))
    assert any("decision alpha" in one["message"] for one in wakes(kitchen))
    code, said = kitchen.main("wakes")
    lines = said.splitlines()
    assert code == 0 and lines[0].startswith("wakes go:")
    assert any(one.startswith("webhook fails (optional): alert: webhook demo") for one in lines)


def test_with_no_home_thread_the_top_level_home_thread_gets_the_wake(kitchen):
    kitchen.config(url="", project_wake=None, home_thread=TOP)
    decide(kitchen)
    kitchen.poll(NOW)
    assert len(wakes(kitchen, TOP)) == 1


def test_with_no_thread_at_all_the_events_wait_and_the_journal_says_so_once(kitchen):
    kitchen.config(url="", project_wake=None)
    decide(kitchen)
    said = kitchen.poll(NOW) + kitchen.poll(later(5))
    assert len([one for one in said if "no home thread" in one]) == 1
    assert waiting(kitchen) and kitchen.main("wakes")[0] == 0


def test_no_webhook_is_not_something_waiting_on_the_user(kitchen):
    homed(kitchen, url="", project_wake=None)
    said = kitchen.poll(NOW) + kitchen.poll(later(70))
    assert not any("set webhook_url" in one for one in said)
    assert not any("set webhook_url" in one["line"] for one in kitchen.events())
    assert jbus.read_json(kitchen.state / "stall.json", {}) == {}


def test_status_names_each_project_s_wake(kitchen):
    homed(kitchen, wake="both", project_wake=None)
    kitchen.poll(NOW)
    assert kitchen.status()["projects"]["demo"]["wake"] == "both"


def test_a_flip_of_wake_keeps_the_wakes_that_wait_for_a_route_it_leaves(kitchen):
    homed(kitchen, url="", project_wake=None)
    kitchen.t3.refuse_send = True
    kitchen.poll(NOW)
    assert waiting(kitchen)
    kitchen.config(project_wake="webhook")
    kitchen.poll(later(5))
    assert any(one["event"] == "decision" for one in waiting(kitchen))
    kitchen.t3.refuse_send = False
    kitchen.config(project_wake="home")
    kitchen.poll(later(10))
    assert any("decision alpha" in one["message"] for one in wakes(kitchen))


def test_the_relay_health_check_counts_no_top_level_pair_while_wake_is_home(kitchen):
    from jbus import health

    relay = "http://127.0.0.1:4390/wake"
    kitchen.config(url="", project_wake=None, webhook_url=relay, webhook_key="k")
    assert not health.posts_to_relay(jbus.load())
    kitchen.config(project_wake="both", webhook_url=relay, webhook_key="k")
    assert health.posts_to_relay(jbus.load())


def test_status_and_the_digest_show_the_last_sweep_whatever_the_wake(kitchen):
    from jbus import digest, record

    homed(kitchen, wake="home", project_wake=None)
    config = jbus.load()
    wake.Box(kitchen.state, config.project("demo")).swept("2026-10-23 ran", True)
    assert record.status(config, NOW)["projects"]["demo"]["sweep"] == "2026-10-23 ran"
    assert digest.build(config, now=NOW)["projects"]["demo"]["sweep"] == "2026-10-23 ran"


def test_an_event_of_the_machine_reaches_the_home_thread_beside_the_top_level_webhook(kitchen):
    from test_jbus_kitchen import KEY, Webhook

    top = Webhook()
    try:
        homed(kitchen, project_wake="both", webhook_url=top.url + "/wake", webhook_key=KEY)
        config = jbus.load()
        box = wake.Box(kitchen.state, config.project("demo"), config.webhook)
        box.send("", "alert", "alert: the machine's own", machine=True)
        kitchen.poll(NOW)
        assert any("alert: the machine's own" in one["message"] for one in wakes(kitchen))
        assert any("alert: the machine's own" in json.dumps(post) for post in top.posts)
    finally:
        top.close()


def test_with_wake_both_and_no_home_thread_the_webhook_s_post_counts_as_the_wake(kitchen):
    kitchen.config(project_wake="both")
    decide(kitchen)
    said = kitchen.poll(NOW)
    assert len(kitchen.webhook.posts) == 1
    assert "woke demo: 1 events" in said
    (decision,) = kitchen.events("decision")
    assert decision["posted"] is not None


@pytest.mark.parametrize("picked", ["home", "both"])
def test_an_event_the_home_thread_took_shows_as_posted(kitchen, picked):
    homed(kitchen, project_wake=picked)
    kitchen.webhook.status = 400
    kitchen.poll(NOW)
    assert len(wakes(kitchen)) == 1
    (decision,) = kitchen.events("decision")
    assert decision["posted"] is not None


def test_a_log_line_of_the_own_webhook_from_before_posted_home_still_counts(kitchen):
    kitchen.config()
    box = wake.Box(kitchen.state, jbus.load().project("demo"))
    box.send("alpha", "decision", "decision alpha: which one?")
    (made,) = jbus.read_json(kitchen.state / "outbox.json", [])
    line = {"at": NOW.isoformat(), "posted_webhook": [wake._id(made)]}
    with open(kitchen.state / wake.LOG, "a") as log:
        log.write(json.dumps(line) + "\n")
    (decision,) = kitchen.events("decision")
    assert decision["posted"] == NOW.isoformat()
