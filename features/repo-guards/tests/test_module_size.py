"""No module under src/, or a feature's src/, grows past `CAP` lines. A long module is one that many
changes touch: every change appends to it, and every rebase conflicts on it. A
feature goes in a module of its own.

`OVER` is the modules that were over the cap when the cap was set, with their length then. When a
change shortens a module to under the cap, the change must also take the module off the list. So the
list only shrinks, and no module joins it.
"""

from pathlib import Path

from testing.paths import sources

CAP = 800
OVER = {
    "jbus/questions.py": 860,
    "jbus/wake.py": 901,
    "jmerge/ready.py": 1062,
    "jinstall/kinds.py": 1098,
    "jbus/watch.py": 1112,
    "jbus/queue.py": 1219,
    "jbus/view/state.py": 1405,
    "jmerge/cli.py": 1586,
}


def lengths(*roots: Path) -> dict[str, int]:
    """The length in lines of each module under `roots`, keyed by its path from the root it is
    under. With no `roots`, it measures the modules under each feature's `src/`."""
    return {
        path.relative_to(root).as_posix(): len(path.read_text().splitlines())
        for root in roots or sources()
        for path in sorted(root.rglob("*.py"))
    }


def offences(found: dict[str, int], over: dict[str, int] = OVER) -> list[str]:
    """What is wrong with the lengths `found`. One fault is a module over the cap that is not on the
    list. The other is a listed module that is now under the cap or no longer exists: that module
    must come off the list."""
    said = [
        f"{name} has {length} lines, over {CAP}: split it, a feature in a module of its own"
        for name, length in found.items()
        if length > CAP and name not in over
    ]
    said += [
        f"{name} has {found[name]} lines, under {CAP}: take it off OVER"
        if name in found
        else f"{name} is gone: take it off OVER"
        for name in over
        if found.get(name, 0) <= CAP
    ]
    return said


def test_no_module_is_over_the_cap_but_those_listed_and_each_listed_one_still_is():
    assert offences(lengths()) == []


def test_a_new_long_module_and_a_listed_one_cut_under_the_cap_each_fail(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "long.py").write_text("x = 1\n" * (CAP + 1))
    (tmp_path / "pkg" / "cut.py").write_text("x = 1\n" * CAP)
    (tmp_path / "pkg" / "kept.py").write_text("x = 1\n" * (CAP + 5))
    found = lengths(tmp_path)
    assert offences(found, {"pkg/cut.py": 900, "pkg/kept.py": 900, "pkg/gone.py": 900}) == [
        f"pkg/long.py has {CAP + 1} lines, over {CAP}: split it, a feature in a module of its own",
        f"pkg/cut.py has {CAP} lines, under {CAP}: take it off OVER",
        "pkg/gone.py is gone: take it off OVER",
    ]
