"""`meaning.changed` names a line exactly when `meaning.same` says the brief changed, so a gate
that asks again always says what to look at."""

from jbriefs import meaning

APPROVED = """\
# alpha: a brief whose go is kept
Task: "make the queue check a brief"
Done when:
- `jbus queue add` refuses an incomplete brief, with one line per fault
- an approval holds through a wording-only edit
- `make check` exits 0, in 3 minutes or less
Size: M
Where: `src/jbus/queue.py`
"""


def test_changed_names_only_the_changed_line_beside_a_fixed_typo_in_its_field():
    approved = meaning.meaning(APPROVED)
    both = APPROVED.replace("wording-only", "wordnig-only").replace("3 minutes", "5 minutes")
    assert not meaning.same(approved, meaning.meaning(both))
    assert meaning.changed(approved, both) == [
        "Done when: `make check` exits 0, in 5 minutes or less"
    ]


def test_changed_is_empty_exactly_when_same_holds():
    approved = meaning.meaning(APPROVED)
    edits = [
        APPROVED,
        APPROVED.replace("wording-only", "wordnig-only"),
        APPROVED.replace("3 minutes", "5 minutes"),
        APPROVED.replace("- an approval holds through a wording-only edit\n", ""),
        APPROVED.replace("Size: M", "Size: L"),
        APPROVED.replace("Size: M", "- extra line\nSize: M"),
    ]
    for again in edits:
        names = meaning.changed(approved, again)
        assert (names == []) == meaning.same(approved, meaning.meaning(again)), again
