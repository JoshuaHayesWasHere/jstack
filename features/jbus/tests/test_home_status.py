"""`jbus home status --home` over a state with several scopes and many briefs naming them."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from jbus import homestatus

SCOPES = ("alpha", "beta", "gamma")
BRIEFS = 4


def test_home_status_reads_each_scopes_home_id_once_however_many_briefs_name_it(
    tmp_path, monkeypatch
):
    """A home's start asks of every brief whose home it is, and reads the repo's scopes once for
    all of them, not once a brief: each scope's `home-id` is read once a run."""
    state = tmp_path / "demo"
    (state / "tasks").mkdir(parents=True)
    for scope in SCOPES:
        (state / scope).mkdir()
        (state / scope / "home-id").write_text(f"thread-{scope}\n")
        (state / scope / "read-seen").write_text("")
        for n in range(BRIEFS):
            (state / "tasks" / f"{scope}-{n}.md").write_text(
                f"# {scope}-{n}\nHome: {scope}\n\n## Result\nStatus: done\n"
            )
    monkeypatch.setattr(homestatus.paths, "repo_name", lambda: state.name)
    reads: Counter[Path] = Counter()
    read_text = Path.read_text

    def counted(self: Path, *args, **kwargs) -> str:
        if self.name == "home-id":
            reads[self] += 1
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted)

    said = homestatus.run(str(state / "beta"), installed=False, only_gates=False)

    unread = said[said.index("## to read") + 1 :]
    assert unread == [f"tasks/beta-{n}.md: ## Result" for n in range(BRIEFS)]
    assert {state / scope / "home-id" for scope in SCOPES} <= set(reads)
    assert set(reads.values()) == {1}
