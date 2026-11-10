"""`jbus telemetry` copies every Claude and Codex call's token usage into the store, by thread.

The tests write what the agents write: a Claude Code transcript with a subagent's beside it, and
a Codex rollout, under a home of the test's own, with T3 Code's store naming each session's
thread. They run the real command and read the store as any reader would. A call keeps its
thread, row and role after its transcript is gone; a call written across two builds is one row
with its final counts; no message text reaches the file; and `row_spend` gives each merged row's
spend by role.
"""

import contextlib
import io
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from jbus import cli, telemetry
from jgauge import spend as jgauge_spend

SECRET = "the user said this and it stays out"
NOW = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
C1 = "01a19ad5-25f1-70f0-84e4-714c6bada68b"
"""A Codex session id, as the end of its rollout's name gives it."""
T3_SCHEMA = """
CREATE TABLE projection_projects (project_id TEXT PRIMARY KEY, title TEXT NOT NULL);
CREATE TABLE orchestration_v2_projection_threads (
    thread_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL);
CREATE TABLE orchestration_v2_projection_provider_threads (
    provider_thread_id TEXT PRIMARY KEY, thread_id TEXT, provider TEXT NOT NULL,
    payload_json TEXT NOT NULL, driver TEXT, provider_instance_id TEXT);
"""


def iso(moment):
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Machine:
    """A jbus config of one project, `alpha`, a home with `~/.claude` and `~/.codex`, and T3
    Code's store in the test's own `T3CODE_HOME`."""

    def __init__(self, tmp_path, monkeypatch, t3_settings):
        self.root = tmp_path
        config, self.state_dir, self.home_dir = (tmp_path / name for name in ("c", "s", "h"))
        (self.state_dir / "alpha").mkdir(parents=True)
        (self.home_dir / "alpha").mkdir(parents=True)
        config.mkdir()
        (config / "config.toml").write_text(
            'server = "http://127.0.0.1:1"\n[[project]]\nname = "alpha"\n'
            f'checkout = "{tmp_path / "alpha"}"\nprojectId = "alpha-id"\n'
        )
        (config / "config.toml").chmod(0o600)
        monkeypatch.setenv("JBUS_CONFIG_DIR", str(config))
        monkeypatch.setenv("JBUS_STATE_DIR", str(self.state_dir))
        monkeypatch.setenv("JBUS_HOME_DIR", str(self.home_dir))
        self.home = tmp_path / "home"
        self.home.mkdir()
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.delenv("CODEX_HOME", raising=False)
        self.t3 = sqlite3.connect(t3_settings.parent / "statev2.sqlite", isolation_level=None)
        self.t3.executescript(T3_SCHEMA)
        self.t3.execute("INSERT INTO projection_projects VALUES ('alpha-id', 'Alpha')")

    def thread(self, thread, title, driver, native, instance=None):
        """A T3 thread titled `title`, and a provider thread of `driver` on the native session
        `native`. A thread resumed on a new native session has a provider thread for each."""
        self.t3.execute(
            "INSERT OR IGNORE INTO orchestration_v2_projection_threads VALUES (?, 'alpha-id', ?)",
            (thread, title),
        )
        payload = {"nativeThreadRef": {"driver": driver, "nativeId": native}}
        self.t3.execute(
            "INSERT INTO orchestration_v2_projection_provider_threads VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"pt-{native}",
                thread,
                instance or driver,
                json.dumps(payload),
                driver,
                instance or driver,
            ),
        )

    def claude(self, session, *lines, agent=None):
        """Append to a Claude Code transcript, or with `agent` to a subagent's beside it."""
        where = self.home / ".claude" / "projects" / "-home-worktree"
        path = (
            where / session / "subagents" / f"agent-{agent}.jsonl"
            if agent
            else where / f"{session}.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as handle:
            handle.writelines(json.dumps(line) + "\n" for line in lines)
        return path

    def codex(self, session, *lines):
        where = self.home / ".codex" / "sessions" / "2026" / "10" / "28"
        where.mkdir(parents=True, exist_ok=True)
        path = where / f"rollout-2026-10-28T15-00-00-{session}.jsonl"
        with open(path, "a") as handle:
            handle.writelines(json.dumps(line) + "\n" for line in lines)
        return path

    def merged(self, *slugs):
        (self.state_dir / "alpha" / "queue.json").write_text(
            json.dumps([{"slug": slug, "approval": {"ran_at": iso(NOW)}} for slug in slugs])
        )
        (self.state_dir / "alpha" / "merged.json").write_text(
            json.dumps(
                {
                    slug: {"number": n, "mergedAt": iso(NOW + timedelta(hours=2))}
                    for n, slug in enumerate(slugs, 1)
                }
            )
        )

    def run(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["telemetry", *argv])
        assert code == 0, out.getvalue()
        return out.getvalue()

    def store(self, path=None):
        return contextlib.closing(sqlite3.connect(path or self.state_dir / telemetry.FILE))


@pytest.fixture
def machine(tmp_path, monkeypatch, t3_settings):
    return Machine(tmp_path, monkeypatch, t3_settings)


def said(at, message, usage, model="claude-opus-5-5", stop="end_turn", session="s1"):
    """One line of a Claude transcript: a block of an assistant message, with the user's words
    in it."""
    return {
        "type": "assistant",
        "timestamp": iso(at),
        "sessionId": session,
        "message": {
            "id": message,
            "model": model,
            "stop_reason": stop,
            "content": [{"type": "text", "text": SECRET}],
            "usage": {
                "input_tokens": usage[0],
                "cache_creation_input_tokens": usage[1],
                "cache_read_input_tokens": usage[2],
                "output_tokens": usage[3],
            },
        },
    }


def asked(at, session="s1"):
    return {
        "type": "user",
        "timestamp": iso(at),
        "sessionId": session,
        "message": {"role": "user", "content": SECRET},
    }


def counted(at, last, total):
    """A Codex `token_count`: `last` is the call's (input, cached, output), `total` the
    session's running total."""
    usage = {
        "input_tokens": last[0],
        "cached_input_tokens": last[1],
        "cache_write_input_tokens": 0,
        "output_tokens": last[2],
        "reasoning_output_tokens": 0,
        "total_tokens": last[0] + last[2],
    }
    return {
        "timestamp": iso(at),
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": usage,
                "total_token_usage": {**usage, "total_tokens": total},
            },
        },
    }


def rollout(session):
    """The head of a Codex rollout: its meta, and a turn on its model."""
    return (
        {
            "timestamp": iso(NOW),
            "type": "session_meta",
            "payload": {
                "id": session,
                "timestamp": iso(NOW),
                "cwd": "/w",
                "base_instructions": {"text": SECRET},
            },
        },
        {"timestamp": iso(NOW), "type": "turn_context", "payload": {"model": "gpt-6.1-terra"}},
        {
            "timestamp": iso(NOW),
            "type": "event_msg",
            "payload": {"type": "token_count", "info": None},
        },
        {
            "timestamp": iso(NOW),
            "type": "response_item",
            "payload": {"type": "message", "content": [{"type": "input_text", "text": SECRET}]},
        },
    )


def spend(store):
    return store.execute(
        "SELECT slug, role, provider, calls, input, cache_write, cache_read, output, units "
        "FROM row_spend ORDER BY slug, role, provider"
    ).fetchall()


def test_every_call_keeps_its_thread_row_and_role_after_its_transcript_is_gone(machine):
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1b", "claudeAgent_prime")
    machine.thread("mcp:review-a", "review: row-a, 2", "codex", C1)
    machine.thread("mcp:home", "home: alpha", "claudeAgent", "s9")
    one = machine.claude(
        "s1",
        asked(NOW),
        said(NOW, "m1", (10, 100, 1000, 1), stop=None),
        said(NOW, "m1", (10, 100, 1000, 1), stop=None),
        said(NOW + timedelta(seconds=5), "m1", (10, 100, 1000, 40)),
        said(NOW, "m-synthetic", (0, 0, 0, 0), model="<synthetic>"),
        said(NOW + timedelta(minutes=1), "m2", (20, 0, 2000, 60), model="claude-sonnet-5-5"),
    )
    sub = machine.claude("s1", said(NOW, "m3", (5, 50, 500, 10)), agent="a1")
    resumed = machine.claude(
        "s1b",
        said(
            NOW + timedelta(minutes=1),
            "m2",
            (20, 0, 2000, 60),
            model="claude-sonnet-5-5",
            session="s1b",
        ),
        said(NOW + timedelta(minutes=9), "m4", (1, 0, 0, 3), session="s1b"),
    )
    home = machine.claude("s9", said(NOW, "m9", (1, 0, 0, 1), session="s9"))
    stray = machine.claude("cli", said(NOW, "m-cli", (7, 0, 0, 7), session="cli"))
    codex = machine.codex(
        C1,
        *rollout(C1),
        counted(NOW + timedelta(minutes=2), (1000, 800, 30), 1030),
        counted(NOW + timedelta(minutes=2), (1000, 800, 30), 1030),
        counted(NOW + timedelta(minutes=3), (2000, 1900, 50), 3080),
    )
    machine.merged("row-a")

    machine.run()
    for path in (one, sub, resumed, home, stray, codex):
        path.unlink()
    machine.run()

    with machine.store() as store:
        calls = store.execute(
            "SELECT provider, call, session, agent, thread, project, role, slug, model, input, "
            "cache_write, cache_read, output, final FROM call_rows ORDER BY provider, call"
        ).fetchall()
        rows = spend(store)
    assert calls == [
        (
            "claude",
            "m1",
            "s1",
            None,
            "mcp:crew-a",
            "alpha",
            "crew",
            "row-a",
            "claude-opus-5-5",
            10,
            100,
            1000,
            40,
            1,
        ),
        (
            "claude",
            "m2",
            "s1",
            None,
            "mcp:crew-a",
            "alpha",
            "crew",
            "row-a",
            "claude-sonnet-5-5",
            20,
            0,
            2000,
            60,
            1,
        ),
        (
            "claude",
            "m3",
            "s1",
            "agent-a1",
            "mcp:crew-a",
            "alpha",
            "crew",
            "row-a",
            "claude-opus-5-5",
            5,
            50,
            500,
            10,
            1,
        ),
        (
            "claude",
            "m4",
            "s1b",
            None,
            "mcp:crew-a",
            "alpha",
            "crew",
            "row-a",
            "claude-opus-5-5",
            1,
            0,
            0,
            3,
            1,
        ),
        (
            "claude",
            "m9",
            "s9",
            None,
            "mcp:home",
            "alpha",
            "home",
            "alpha",
            "claude-opus-5-5",
            1,
            0,
            0,
            1,
            1,
        ),
        (
            "codex",
            f"{C1}:1030",
            C1,
            None,
            "mcp:review-a",
            "alpha",
            "reviewer",
            "row-a",
            "gpt-6.1-terra",
            200,
            0,
            800,
            30,
            1,
        ),
        (
            "codex",
            f"{C1}:3080",
            C1,
            None,
            "mcp:review-a",
            "alpha",
            "reviewer",
            "row-a",
            "gpt-6.1-terra",
            100,
            0,
            1900,
            50,
            1,
        ),
    ]
    opus = 5 / 3
    crew = (
        (10 + 100 * 1.25 + 1000 * 0.1 + 40 * 5) * opus
        + (20 + 2000 * 0.1 + 60 * 5)
        + (5 + 50 * 1.25 + 500 * 0.1 + 10 * 5) * opus
        + (1 + 3 * 5) * opus
    )
    review = 200 + 800 * 0.1 + 30 * 5 + 100 + 1900 * 0.1 + 50 * 5
    assert rows == [
        ("row-a", "crew", "claude", 4, 36, 150, 3500, 113, pytest.approx(crew)),
        ("row-a", "reviewer", "codex", 2, 300, 0, 2700, 80, pytest.approx(review)),
    ]


def test_a_calls_units_are_jgauge_spends_for_each_model_kind(machine):
    """The store weighs a call as `jgauge.spend.units` weighs a run of the same counts: on Opus,
    on another Claude model and on a Codex model, with no rate written here."""
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    machine.thread("mcp:review-a", "review: row-a", "codex", C1)
    machine.claude(
        "s1",
        said(NOW, "m1", (7, 300, 9000, 41)),
        said(NOW, "m2", (13, 200, 7000, 59), model="claude-sonnet-5-5"),
    )
    machine.codex(C1, *rollout(C1), counted(NOW, (3000, 2900, 77), 3077))
    machine.run()

    with machine.store() as store:
        calls = store.execute(
            "SELECT model, input, cache_write, cache_read, output, units FROM call_rows "
            "ORDER BY call"
        ).fetchall()
    assert {model for model, *_ in calls} == {
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "gpt-6.1-terra",
    }
    for model, plain, written, cached, output, units in calls:
        tokens = jgauge_spend.Tokens(plain + written + cached, cached, written, output)
        run = jgauge_spend.Run(model, "i", model, "t", 1, NOW, tokens, "", "", False)
        assert units == jgauge_spend.units(run), model


def test_a_calls_dollars_are_its_tokens_times_the_price_table(machine):
    """A call of a priced model costs each of its four counts at its class's price in
    `jgauge.spend.PRICES`, in the store as in `jgauge.spend.dollars`; a Codex call, of a model
    the table does not price, has no dollars and counts as unpriced."""
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    machine.thread("mcp:review-a", "review: row-a", "codex", C1)
    machine.merged("row-a")
    machine.claude(
        "s1",
        said(NOW, "m1", (7, 300, 9000, 41)),
        said(NOW, "m2", (13, 200, 7000, 59), model="claude-sonnet-5-5"),
        said(NOW, "m3", (2, 100, 400, 9), model="claude-haiku-5-5"),
    )
    machine.codex(C1, *rollout(C1), counted(NOW, (3000, 2900, 77), 3077))
    machine.run()

    with machine.store() as store:
        calls = store.execute(
            "SELECT model, input, cache_write, cache_read, output, dollars FROM call_rows "
            "ORDER BY call"
        ).fetchall()
        week = store.execute(
            "SELECT rows, dollars, unpriced, dollars_per_row FROM weekly_row_spend"
        ).fetchall()
    priced = 0.0
    for model, plain, written, cached, output, dollars in calls:
        price = jgauge_spend.PRICES.get(model)
        if price is None:
            assert model == "gpt-6.1-terra"
            assert dollars is None
            assert jgauge_spend.dollars(model, plain, written, cached, output) is None
            continue
        tokens_times_table = (
            plain * price.plain
            + written * price.written
            + cached * price.cached
            + output * price.output
        ) / 1e6
        assert dollars == pytest.approx(tokens_times_table), model
        assert jgauge_spend.dollars(model, plain, written, cached, output) == pytest.approx(
            tokens_times_table
        )
        priced += dollars
    assert len(calls) == 4
    assert week == [(1, pytest.approx(priced), 1, pytest.approx(priced))]


def test_a_sonnet_call_costs_anthropics_published_prices(machine):
    """A Sonnet 5.5 call of a million tokens of each class costs what Anthropic's pricing page,
    https://platform.claude.com/docs/en/about-claude/pricing, read on 2026-11-09, gives per
    million: $2 input, $4 one-hour cache write, $0.10 cache hit and $10 output."""
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    machine.merged("row-a")
    million = 1_000_000
    machine.claude(
        "s1", said(NOW, "m1", (million, million, million, million), model="claude-sonnet-5-5")
    )
    machine.run()

    with machine.store() as store:
        calls = store.execute("SELECT model, dollars FROM call_rows").fetchall()
    assert calls == [("claude-sonnet-5-5", pytest.approx(2 + 4 + 0.10 + 10))]


def test_a_fable_call_has_dollars_and_is_not_named_unpriced(machine):
    """A Fable 5.2 call on a merged row is priced: `call_rows` gives it dollars, and
    `weekly_unpriced` names no model for its week."""
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    machine.merged("row-a")
    machine.claude("s1", said(NOW, "m1", (7, 300, 9000, 41), model="claude-fable-5-2"))
    machine.run()

    with machine.store() as store:
        calls = store.execute("SELECT model, dollars FROM call_rows").fetchall()
        unpriced = store.execute("SELECT name, count FROM weekly_unpriced").fetchall()
    assert len(calls) == 1
    model, dollars = calls[0]
    assert model == "claude-fable-5-2"
    assert dollars is not None
    assert dollars > 0
    assert unpriced == []


def test_a_call_written_across_two_builds_is_one_row_with_its_final_counts(machine):
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    machine.thread("mcp:review-a", "review: row-a", "codex", C1)
    machine.merged("row-a")
    machine.claude("s1", said(NOW, "m1", (10, 100, 1000, 1), stop=None))
    machine.codex(C1, *rollout(C1), counted(NOW, (1000, 800, 30), 1030))
    machine.run()
    with machine.store() as store:
        floor = store.execute("SELECT output, final FROM calls WHERE call = 'm1'").fetchone()
    assert floor == (1, 0)

    machine.claude(
        "s1",
        said(NOW + timedelta(seconds=5), "m1", (10, 100, 1000, 40)),
        said(NOW + timedelta(seconds=6), "m1", (10, 100, 1000, 2), stop=None),
    )
    machine.codex(
        C1,
        counted(NOW, (1000, 800, 30), 1030),
        {"timestamp": iso(NOW), "type": "turn_context", "payload": {"model": "gpt-6.2"}},
        counted(NOW + timedelta(minutes=1), (2000, 1900, 50), 3080),
    )
    added = machine.run()
    assert "calls 2" in added
    assert "nothing new" in machine.run()

    with machine.store() as store:
        calls = store.execute(
            "SELECT call, model, output, final FROM calls ORDER BY call"
        ).fetchall()
    assert calls == [
        (f"{C1}:1030", "gpt-6.1-terra", 30, 1),
        (f"{C1}:3080", "gpt-6.2", 50, 1),
        ("m1", "claude-opus-5-5", 40, 1),
    ]
    again = machine.root / "again.sqlite"
    machine.run("--rebuild", str(again))
    with machine.store() as store, machine.store(again) as rebuilt:
        for table in ("calls", "sessions"):
            held = sorted(store.execute(f"SELECT * FROM {table}").fetchall())
            assert held == sorted(rebuilt.execute(f"SELECT * FROM {table}").fetchall())


def test_no_byte_of_the_store_holds_what_a_transcript_said(machine):
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    machine.thread("mcp:review-a", "review: row-a", "codex", C1)
    machine.claude("s1", asked(NOW), said(NOW, "m1", (10, 100, 1000, 40)))
    machine.codex(C1, *rollout(C1), counted(NOW, (1000, 800, 30), 1030))
    machine.run()

    with machine.store() as store:
        assert store.execute("SELECT count(*) FROM calls").fetchone() == (2,)
    for path in sorted(machine.state_dir.glob(f"{telemetry.FILE}*")):
        assert SECRET.encode() not in path.read_bytes()


def test_a_call_counts_on_its_own_day_in_the_users_zone(machine):
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    late = datetime(2026, 11, 1, 3, 30, tzinfo=UTC)
    machine.claude("s1", said(late, "m1", (1, 0, 0, 1)))
    machine.run()
    with machine.store() as store:
        assert store.execute("SELECT at, day FROM calls").fetchone() == (
            "2026-11-01T03:30:00.000000Z",
            "2026-10-31",
        )
