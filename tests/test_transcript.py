import json

import pytest

from jgauge import transcript


def line(key, out, *, stop=None, model="claude-x", kind="text", **usage):
    counts = {"input_tokens": 2, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 5}
    counts.update(usage, output_tokens=out)
    return {
        "type": "assistant",
        "timestamp": "2026-01-01T00:00:00.000Z",
        "message": {
            "id": key,
            "model": model,
            "stop_reason": stop,
            "usage": counts,
            "content": [{"type": kind}],
        },
    }


def test_a_message_on_several_lines_is_one_call_with_its_stop_lines_count():
    entries = [line("m1", 3), line("m1", 3), line("m1", 40, stop="tool_use"), line("m1", 3)]
    (call,) = transcript.calls(entries)
    assert (call.out, call.final) == (40, True)
    whole, _ = transcript.totals([call])
    assert whole == {
        "calls": 1,
        "tokens_in": 2,
        "tokens_out": 40,
        "cache_read": 5,
        "cache_write": 10,
        "out_floor": 0,
        "out_floor_calls": 0,
    }


def test_a_line_with_no_stop_after_the_stop_line_never_changes_the_final_count():
    entries = [line("m1", 40, stop="end_turn"), line("m1", 90, input_tokens=70), line("m1", 3)]
    (call,) = transcript.calls(entries)
    assert (call.out, call.tokens_in, call.final) == (40, 2, True)


def test_a_line_written_twice_is_counted_once():
    entries = [line("m1", 7, stop="end_turn"), line("m1", 7, stop="end_turn")]
    whole, _ = transcript.totals(transcript.calls(entries))
    assert (whole["calls"], whole["tokens_out"], whole["tokens_in"]) == (1, 7, 2)


def test_a_message_with_no_stop_line_is_a_flagged_floor_and_not_final_output():
    entries = [line("m1", 2), line("m1", 4), line("m2", 9, stop="end_turn")]
    whole, _ = transcript.totals(transcript.calls(entries))
    assert whole["tokens_out"] == 9
    assert (whole["out_floor"], whole["out_floor_calls"]) == (4, 1)
    assert (whole["calls"], whole["tokens_in"], whole["cache_write"]) == (2, 4, 20)


def test_totals_are_split_by_model():
    entries = [line("m1", 1, stop="end_turn", model="a"), line("m2", 2, stop="end_turn", model="b")]
    _, by_model = transcript.totals(transcript.calls(entries))
    assert {model: sums["tokens_out"] for model, sums in by_model.items()} == {"a": 1, "b": 2}


def test_synthetic_messages_and_lines_without_an_id_or_usage_are_not_calls():
    bad_usage = line("m3", 1)
    bad_usage["message"]["usage"] = "none"
    no_id = line("m4", 1)
    del no_id["message"]["id"]
    entries = [line("m1", 5, stop="end_turn", model="<synthetic>"), bad_usage, no_id]
    assert transcript.calls(entries) == []


def test_a_boolean_or_a_negative_is_not_a_count():
    entries = [line("m1", True, stop="end_turn", input_tokens=-4, cache_read_input_tokens="9")]
    (call,) = transcript.calls(entries)
    assert (call.out, call.tokens_in, call.cache_read) == (0, 0, 0)


def test_a_line_still_being_written_is_skipped(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps(line("m1", 5, stop="end_turn")) + '\n{"type":"assist')
    assert len(transcript.lines(path)) == 1


def test_a_missing_transcript_and_one_that_is_not_json_say_why(tmp_path):
    with pytest.raises(transcript.TranscriptError) as missing:
        transcript.lines(tmp_path / "none.jsonl")
    assert missing.value.reason == "missing"
    (tmp_path / "junk.jsonl").write_text("not json\n[1, 2]\n")
    with pytest.raises(transcript.TranscriptError) as junk:
        transcript.lines(tmp_path / "junk.jsonl")
    assert junk.value.reason == "unknown-shape"


def test_a_line_holding_a_unicode_line_separator_is_still_one_line(tmp_path):
    entry = {"type": "assistant", "text": "a\u2028b\u2029c\u0085d"}
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    assert transcript.lines(path) == [entry]
