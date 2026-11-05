"""`jbus telemetry` keeps each Claude call's reasoning effort, and prices each successful merge.

The tests write what the agents write, Claude Code transcripts with a subagent's beside them and a
Codex rollout, with T3 Code's store naming each session's thread, run the real command, and read
the store as a reader does. A call keeps the `effort` its lines name, or none where they name
none, whatever T3's run of it asked for; a store copied before calls kept effort takes it from the
transcripts still on disk, and changes nothing else; `merge_cost` gives each successful merge's
own spend by role, model and effort, and leaves a redone row out; `weekly_merge_cost` divides all
of a week's priced calls, a home's and an unmerged crew's too, by its successful merges; and
`jbus kpis` shows that figure first.

The code is `jbus.telemetry.tokens` and `jgauge.transcript`, which copy the effort, the migration
`jbus.telemetry.migrations.v013_call_effort`, the views `jbus.telemetry.views.call_rows`,
`jbus.telemetry.views.merge_cost` and `jbus.telemetry.views.weekly_merge_cost`, and the KPI
`jbus.telemetry.kpis.k00_cost_per_merge`.
"""

from __future__ import annotations

import contextlib
import io
import json
import statistics
from datetime import UTC, datetime, timedelta

import pytest

from jbus import cli
from jbus.telemetry import kpis
from jgauge import spend
from test_jbus_kpi_page import Cells
from test_jbus_telemetry_tokens import C1, NOW, Machine, counted, iso, rollout, said

MERGED = datetime(2026, 10, 14, 13, 0, tzinfo=UTC)
"""The fixture's merges, a Wednesday: their 7 days end on 2026-10-21, in the week of 2026-10-18,
long before any build, so each is judged."""
WEEK = "2026-10-18"
EARLY = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
"""A call a week before the merges: its row's own, in no week of theirs."""
OPUS, SONNET = "claude-opus-5-5", "claude-sonnet-5-5"


def at_effort(line, effort):
    """A transcript line that names its effort, as Claude Code 2.1.303 and later write it."""
    return {**line, "effort": effort, "perTurnEffort": effort}


@pytest.fixture
def machine(tmp_path, monkeypatch, t3_settings):
    found = Machine(tmp_path, monkeypatch, t3_settings)
    found.t3.execute(
        "CREATE TABLE orchestration_v2_projection_runs (run_id TEXT PRIMARY KEY, thread_id TEXT, "
        "requested_at TEXT, completed_at TEXT, payload_json TEXT)"
    )
    return found


def run_of(machine, thread, began, ended, effort=None):
    """A T3 run of `thread`, whose model selection names `effort`, or no effort option."""
    options = [{"id": "effort", "value": effort}] if effort else []
    payload = {"startedAt": iso(began), "modelSelection": {"model": OPUS, "options": options}}
    machine.t3.execute(
        "INSERT INTO orchestration_v2_projection_runs VALUES (?, ?, ?, ?, ?)",
        (f"run-{thread}-{began}", thread, iso(began), iso(ended), json.dumps(payload)),
    )


def efforts(machine):
    with machine.store() as store:
        return store.execute("SELECT call, agent, effort FROM call_rows ORDER BY call").fetchall()


def test_a_call_keeps_the_effort_its_lines_name_and_none_where_they_name_none(machine):
    """Each call's effort is what its own lines name, the main thread's and a subagent's alike.
    A call that no T3 run covers, and one whose run named no effort option, still have the
    effort their lines name; a call whose lines name none has none."""
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    run_of(machine, "mcp:crew-a", MERGED, MERGED + timedelta(minutes=5))
    machine.claude(
        "s1",
        at_effort(said(MERGED, "m1", (1, 0, 0, 1), stop=None), "medium"),
        at_effort(said(MERGED, "m1", (1, 0, 0, 9)), "medium"),
        said(MERGED + timedelta(minutes=1), "m2", (1, 0, 0, 1), model=SONNET, stop=None),
        at_effort(said(MERGED + timedelta(minutes=1), "m2", (1, 0, 0, 2), model=SONNET), "high"),
        said(MERGED + timedelta(minutes=2), "m3", (1, 0, 0, 1)),
        at_effort(said(MERGED + timedelta(hours=3), "m4", (1, 0, 0, 1)), "low"),
    )
    machine.claude("s1", at_effort(said(MERGED, "m5", (1, 0, 0, 1)), "xhigh"), agent="a1")
    machine.run()

    assert efforts(machine) == [
        ("m1", None, "medium"),
        ("m2", None, "high"),
        ("m3", None, None),
        ("m4", None, "low"),
        ("m5", "agent-a1", "xhigh"),
    ]


def older(machine):
    """Make the machine's store one an older jbus copied: no `effort` column, its migration not
    run. Each cursor stays where that build left it."""
    with machine.store() as store:
        names = [
            name for (name,) in store.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        ]
        store.executescript(
            "".join(f"DROP VIEW {name};\n" for name in names)
            + "ALTER TABLE calls DROP COLUMN effort;\n"
            + "DELETE FROM migrations WHERE name = 'v013_call_effort';\n"
        )


def test_a_store_copied_before_calls_kept_effort_takes_it_from_the_transcripts_on_disk(machine):
    """The first build after the store gains `effort` reads each Claude transcript again and sets
    each call's effort from it, a subagent's too, and changes no other column of a call it holds.
    A call whose transcript is gone keeps its counts and has no effort. A Codex call has none."""
    machine.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    machine.thread("mcp:crew-b", "crew: row-b", "claudeAgent", "s2")
    machine.thread("mcp:review-a", "review: row-a", "codex", C1)
    machine.claude("s1", at_effort(said(MERGED, "m1", (10, 100, 1000, 40)), "medium"))
    machine.claude("s1", at_effort(said(MERGED, "m2", (5, 50, 500, 10)), "xhigh"), agent="a1")
    gone = machine.claude(
        "s2", at_effort(said(MERGED, "m3", (7, 0, 70, 3), session="s2"), "medium")
    )
    machine.codex(C1, *rollout(C1), counted(NOW, (1000, 800, 30), 1030))
    machine.run()
    older(machine)
    with machine.store() as store:
        store.execute("UPDATE calls SET output = 41 WHERE call = 'm1'")
        store.commit()
        before = sorted(store.execute("SELECT * FROM calls").fetchall())
    gone.unlink()

    machine.run()

    with machine.store() as store:
        after = store.execute(
            "SELECT provider, call, session, agent, at, model, input, cache_write, cache_read, "
            "output, final, day, effort FROM calls ORDER BY provider, call"
        ).fetchall()
    assert [row[:-1] for row in after] == before
    assert [(row[1], row[-1]) for row in after] == [
        ("m1", "medium"),
        ("m2", "xhigh"),
        ("m3", None),
        (f"{C1}:1030", None),
    ]
    assert "nothing new" in machine.run()


def queue_and_merges(machine, merges, redoes):
    """`queue.json` and `merged.json` for merged rows of (slug, merge time), and for each
    (redoer, parent), a follow-up whose go names its parent, approved 3 hours after it merged."""
    times = dict(merges)
    rows = [
        {"slug": slug, "approval": {"ran_at": iso(at - timedelta(hours=2))}} for slug, at in merges
    ]
    rows += [
        {
            "slug": redoer,
            "status": "queued",
            "approval": {
                "basis": "rule",
                "follows": parent,
                "ran_at": iso(times[parent] + timedelta(hours=3)),
            },
        }
        for redoer, parent in redoes
    ]
    (machine.state_dir / "alpha" / "queue.json").write_text(json.dumps(rows))
    (machine.state_dir / "alpha" / "merged.json").write_text(
        json.dumps(
            {slug: {"number": n, "mergedAt": iso(at)} for n, (slug, at) in enumerate(merges, 1)}
        )
    )


CALLS = {
    "m1": ("s1", None, OPUS, "medium", (10, 1_000, 20_000, 400), MERGED),
    "m2": ("s1", "a1", OPUS, "xhigh", (5, 500, 10_000, 100), MERGED),
    "m3": ("s2", None, SONNET, "high", (20, 0, 30_000, 600), MERGED),
    "m4": ("s1", None, OPUS, "medium", (3, 0, 9_000, 50), EARLY),
    "m5": ("s3", None, OPUS, "medium", (1, 100, 2_000, 30), MERGED),
    "m6": ("s4", None, OPUS, "medium", (2, 300, 5_000, 70), MERGED),
    "m7": ("s5", None, OPUS, "medium", (9, 900, 90_000, 900), MERGED),
    "m8": ("s6", None, OPUS, "medium", (4, 400, 40_000, 400), MERGED),
    "m9": ("s7", None, OPUS, "medium", (6, 600, 60_000, 600), MERGED),
    "m10": ("s8", None, OPUS, "medium", (8, 800, 80_000, 800), MERGED),
}
"""Each Claude call of the fixture: its session, subagent, model, effort, counts and time.
`row-a` has m1 to m4, a subagent's, a reviewer's on Sonnet and one a week early; `row-b` m5,
`row-c` m6; `redone`, which a follow-up redid, m7; the home m8, an unmerged crew m9, and a thread
of no role m10."""


def dollars(*names):
    return sum(spend.dollars(CALLS[name][2], *CALLS[name][4]) for name in names)


def units(*names):
    total = 0.0
    for name in names:
        _, _, model, _, (plain, written, cached, output), _ = CALLS[name]
        weight = spend.OPUS if spend.OPUS_NAME in model else 1
        total += (
            plain * spend.PLAIN
            + written * spend.WRITTEN
            + cached * spend.CACHED
            + output * spend.OUTPUT
        ) * weight
    return total


@pytest.fixture
def week(machine):
    """Three successful merges, `row-a`, `row-b` and `row-c`, a merge a follow-up redid, a home,
    an unmerged crew and a thread of no role, each with its calls, and a Codex reviewer's call
    on `row-a`, a later week's, which no table prices."""
    for thread, title, session in (
        ("mcp:crew-a", "crew: row-a", "s1"),
        ("mcp:review-a", "review: row-a", "s2"),
        ("mcp:crew-b", "crew: row-b", "s3"),
        ("mcp:crew-c", "crew: row-c", "s4"),
        ("mcp:crew-redone", "crew: redone", "s5"),
        ("mcp:home", "home: alpha", "s6"),
        ("mcp:crew-x", "crew: never-merged", "s7"),
        ("mcp:chat", "lunch plans", "s8"),
    ):
        machine.thread(thread, title, "claudeAgent", session)
    machine.thread("mcp:review-a2", "review: row-a, 2", "codex", C1)
    for name, (session, agent, model, effort, counts, at) in CALLS.items():
        line = at_effort(said(at, name, counts, model=model, session=session), effort)
        machine.claude(session, line, agent=agent)
    machine.codex(C1, *rollout(C1), counted(NOW, (1000, 800, 30), 1030))
    queue_and_merges(
        machine,
        [
            ("row-a", MERGED),
            ("row-b", MERGED + timedelta(hours=1)),
            ("row-c", MERGED + timedelta(hours=2)),
            ("redone", MERGED - timedelta(hours=1)),
        ],
        [("fix-redone", "redone")],
    )
    machine.run()
    return machine


def test_merge_cost_gives_each_successful_merges_own_spend_by_role_model_and_effort(week):
    with week.store() as store:
        found = store.execute(
            "SELECT slug, week, role, model, effort, calls, input, cache_write, cache_read, "
            "output, units, dollars FROM merge_cost ORDER BY slug, role, model, effort"
        ).fetchall()
    assert found == [
        (
            "row-a",
            WEEK,
            "crew",
            OPUS,
            "medium",
            2,
            13,
            1_000,
            29_000,
            450,
            pytest.approx(units("m1", "m4")),
            pytest.approx(dollars("m1", "m4")),
        ),
        (
            "row-a",
            WEEK,
            "crew",
            OPUS,
            "xhigh",
            1,
            5,
            500,
            10_000,
            100,
            pytest.approx(units("m2")),
            pytest.approx(dollars("m2")),
        ),
        (
            "row-a",
            WEEK,
            "reviewer",
            SONNET,
            "high",
            1,
            20,
            0,
            30_000,
            600,
            pytest.approx(units("m3")),
            pytest.approx(dollars("m3")),
        ),
        (
            "row-a",
            WEEK,
            "reviewer",
            "gpt-6.1-terra",
            None,
            1,
            200,
            0,
            800,
            30,
            pytest.approx(200 + 80 + 150),
            None,
        ),
        (
            "row-b",
            WEEK,
            "crew",
            OPUS,
            "medium",
            1,
            1,
            100,
            2_000,
            30,
            pytest.approx(units("m5")),
            pytest.approx(dollars("m5")),
        ),
        (
            "row-c",
            WEEK,
            "crew",
            OPUS,
            "medium",
            1,
            2,
            300,
            5_000,
            70,
            pytest.approx(units("m6")),
            pytest.approx(dollars("m6")),
        ),
    ]


def test_a_weeks_cost_per_merge_divides_all_its_priced_calls_by_its_successful_merges(week):
    """Own-thread dollars and units per merge, mean and median, are the successful merges' own.
    All-in is every priced call of the week: the redone row's, the home's and the unmerged
    crew's too, but no call of a thread with no role and none made in another week, over the
    week's successful merges."""
    with week.store() as store:
        found = store.execute(
            "SELECT week, merges, own_dollars, own_dollars_mean, own_dollars_median, "
            "own_units_mean, own_units_median, all_in_dollars, all_in_per_merge, waiting "
            "FROM weekly_merge_cost"
        ).fetchall()
    own = [dollars("m1", "m2", "m3", "m4"), dollars("m5"), dollars("m6")]
    own_units = [units("m1", "m2", "m3", "m4") + 430, units("m5"), units("m6")]
    all_in = dollars("m1", "m2", "m3", "m5", "m6", "m7", "m8", "m9")
    assert found == [
        (
            WEEK,
            3,
            pytest.approx(sum(own)),
            pytest.approx(statistics.mean(own)),
            pytest.approx(statistics.median(own)),
            pytest.approx(statistics.mean(own_units)),
            pytest.approx(statistics.median(own_units)),
            pytest.approx(all_in),
            pytest.approx(all_in / 3),
            0,
        )
    ]


def page(machine, week):
    """The KPI page `jbus kpis` writes with `week` as this week, as its table's cells."""
    out = machine.root / "page" / "kpis.html"
    said_out = io.StringIO()
    with contextlib.redirect_stdout(said_out):
        code = cli.main(["kpis", "--week", week, "--out", str(out)])
    assert code == 0, said_out.getvalue()
    cells = Cells()
    cells.feed(out.read_text())
    return cells.rows


def test_a_week_whose_merges_are_not_judged_yet_has_no_figure_and_says_how_many_wait(machine):
    """A merge whose 7 days are not over is not successful yet, so its week has no merge to
    divide by, and the page says how many of its merges wait."""
    machine.thread("mcp:crew-a", "crew: fresh", "claudeAgent", "s1")
    merged_at = datetime.now(UTC) - timedelta(days=1)
    machine.claude("s1", at_effort(said(merged_at, "m1", (1, 0, 100, 10)), "medium"))
    queue_and_merges(machine, [("fresh", merged_at)], [])
    machine.run()
    with machine.store() as store:
        (week,) = store.execute("SELECT week FROM redo_rows").fetchone()

    row = page(machine, week)["All-in dollars per successful merge"]

    assert row[5] == "n/a n 0 no data: 1 merge of the week not judged yet, whose calls count"


def test_the_kpi_page_puts_all_in_dollars_per_successful_merge_first_with_its_breakdown(week):
    assert kpis.KPIS[0].name == "All-in dollars per successful merge"
    rows = page(week, "2026-10-25")

    assert list(rows)[0] == "All-in dollars per successful merge"
    last = rows["All-in dollars per successful merge"][4]
    all_in = dollars("m1", "m2", "m3", "m5", "m6", "m7", "m8", "m9") / 3
    own = [dollars("m1", "m2", "m3", "m4"), dollars("m5"), dollars("m6")]
    by = sorted(
        [
            ("crew claude-opus-5-5 medium", dollars("m1", "m4", "m5", "m6") / 3),
            ("crew claude-opus-5-5 xhigh", dollars("m2") / 3),
            ("reviewer claude-sonnet-5-5 high", dollars("m3") / 3),
        ],
        key=lambda one: -one[1],
    )
    assert last == (
        f"${round(all_in, 1):g} n 3 tracked: own threads ${statistics.mean(own):.2f} mean, "
        f"${statistics.median(own):.2f} median a merge; by role, model and effort a merge: "
        + ", ".join(f"{name} ${value:.2f}" for name, value in by)
    )
