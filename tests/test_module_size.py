"""No module under src/ grows past `CAP` lines: a long module is a hot file, which every
change appends to and every rebase fights over. A feature goes in a module of its own.

`OVER` is the modules that were over the cap when it was set, with their length then. One
that is cut under the cap leaves the list, so the list only shrinks, and none is added.
"""

from pathlib import Path

from testing.paths import REPO

SRC = REPO / "src"
CAP = 800
OVER = {
    "jbus/questions.py": 860,
    "jmerge/ready.py": 1062,
    "jinstall/kinds.py": 1098,
    "jbus/watch.py": 1112,
    "jbus/queue.py": 1219,
    "jbus/view/state.py": 1405,
    "jmerge/cli.py": 1586,
}


def lengths(root: Path = SRC) -> dict[str, int]:
    """The length in lines of each module under `root`, by its path from there."""
    return {
        path.relative_to(root).as_posix(): len(path.read_text().splitlines())
        for path in sorted(root.rglob("*.py"))
    }


def offences(found: dict[str, int], over: dict[str, int] = OVER) -> list[str]:
    """What is wrong with the lengths `found`: a module over the cap that is not listed, and
    a listed module that is under it now, or gone, and leaves the list."""
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
