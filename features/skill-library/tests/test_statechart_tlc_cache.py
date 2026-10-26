"""`kept`, the cache of TLC's output: a run is kept under the sha256 of its inputs, beside the
pinned jar in the user's cache, and an output its caller does not call finished is never kept."""

from statechart_support import statechart_tools


def test_an_output_is_kept_by_its_inputs_beside_the_jar(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert statechart_tools.tlc_cache() == tmp_path / "jstack" / "tlc"
    assert statechart_tools.tlc_cache().parent == statechart_tools.cached_jar().parents[2]
    calls = []

    def output_of(said):
        def run():
            calls.append(said)
            return said

        return run

    def done(out):
        return out != "cut short"

    assert statechart_tools.kept(output_of("first"), ["a", b"b"], done) == "first"
    assert statechart_tools.kept(output_of("second"), ["a", b"b"], done) == "first"
    assert statechart_tools.kept(output_of("third"), ["ab", b""], done) == "third"
    assert statechart_tools.kept(output_of("cut short"), ["c"], done) == "cut short"
    assert statechart_tools.kept(output_of("fourth"), ["c"], done) == "fourth"
    assert calls == ["first", "third", "cut short", "fourth"]
    assert len(list(statechart_tools.tlc_cache().iterdir())) == 3
