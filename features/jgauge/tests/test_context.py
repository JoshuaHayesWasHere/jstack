"""`jgauge context`: how full a thread's context is, the input side of the transcript's last call.
Each test runs the command on a made-up transcript."""

import json

import pytest

from jgauge import cli

SESSION = "22222222-2222-4222-8222-222222222222"


def call(key, fresh, read, written, *, stop="tool_use"):
    usage = {
        "input_tokens": fresh,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": written,
        "output_tokens": 7,
    }
    message = {"id": key, "model": "claude-x", "stop_reason": stop, "usage": usage}
    return {"type": "assistant", "message": message}


def transcript(tmp_path, *entries):
    path = tmp_path / f"{SESSION}.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    return path

def test_context_prints_the_input_side_of_the_last_call_and_not_the_peak(tmp_path, capsys):
    path = transcript(tmp_path, call("m1", 5, 900, 95), call("m2", 2, 300, 40))
    assert cli.main(["context", str(path)]) == 0
    assert capsys.readouterr().out == "342\n"


def test_context_counts_a_call_with_no_finished_line(tmp_path, capsys):
    path = transcript(tmp_path, call("m1", 1, 10, 0), call("m2", 3, 20, 4, stop=None))
    assert cli.main(["context", str(path)]) == 0
    assert capsys.readouterr().out == "27\n"


def test_context_prints_0_for_a_transcript_with_no_call(tmp_path, capsys):
    said = {"type": "user", "message": {"role": "user", "content": "hello"}}
    for entries in ([said], []):
        assert cli.main(["context", str(transcript(tmp_path, *entries))]) == 0
        assert capsys.readouterr().out == "0\n"


def test_context_says_so_when_there_is_no_transcript(tmp_path):
    with pytest.raises(SystemExit, match="jgauge: transcript missing"):
        cli.main(["context", str(tmp_path / "none.jsonl")])


