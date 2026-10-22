"""The two probe sessions behind features/jgauge/docs/meter-findings.md, checked against the
hand recounts.

The fixtures are trimmed copies of the real transcripts (features/jgauge/tests/fixtures/README.md).
The expected numbers come from a recount by hand of the untrimmed files. Each expected number
was counted from one of those transcript files, and this test file computes none of them.
"""

from pathlib import Path

from jgauge import session

FIXTURES = Path(__file__).parent / "fixtures" / "projects" / "-tmp-pipeline-check"
SMOKE = "a59133d5-44b2-40ea-bca3-6eef6f94ba6f"
NESTED = "4aa8337b-ff06-40a6-b509-eb8dbc273077"
SMOKE_SCOUT = "aa8a78fae39e2eb67"
BUILDER = "a2232bee059d5cce5"
NESTED_SCOUT = "a6eb3a80c377662fd"


def rows(name):
    report = session.of_transcript(FIXTURES / f"{name}.jsonl")
    return {row["agent"]: row for row in report["rows"]}, report["total"]


def counts(row):
    keys = ("tokens_in", "cache_write", "cache_read", "tokens_out", "calls")
    return tuple(row[key] for key in keys)


def floor(row):
    return row["out_floor"], row["out_floor_calls"]


def test_the_smoke_test_session_matches_the_hand_recount():
    by_agent, total = rows(SMOKE)
    assert list(by_agent) == [None, SMOKE_SCOUT]
    assert counts(by_agent[None]) == (4, 16666, 42948, 295, 2)
    assert floor(by_agent[None]) == (0, 0)
    scout = by_agent[SMOKE_SCOUT]
    assert counts(scout) == (2, 6592, 0, 0, 1)
    assert floor(scout) == (3, 1)
    assert list(scout["models"]) == ["claude-haiku-5-5"]
    assert (total["calls"], total["total"], total["peak_context"]) == (3, 66510, 30211)


def test_the_nesting_session_matches_the_hand_recount():
    by_agent, total = rows(NESTED)
    assert counts(by_agent[None]) == (4, 17348, 42777, 1276, 2)
    builder = by_agent[BUILDER]
    assert counts(builder) == (4, 21175, 18552, 0, 2)
    assert floor(builder) == (26, 2)
    assert list(builder["models"]) == ["claude-opus-5-5"]
    assert (total["calls"], total["total"], total["peak_context"]) == (5, 107405, 30893)


def test_the_nested_scout_is_its_own_row_and_not_in_the_builders_counts():
    by_agent, _ = rows(NESTED)
    assert list(by_agent) == [None, BUILDER, NESTED_SCOUT]
    nested = by_agent[NESTED_SCOUT]
    assert counts(nested) == (2, 6236, 0, 0, 1)
    assert floor(nested) == (5, 1)
    assert by_agent[BUILDER]["cache_write"] == 21175
