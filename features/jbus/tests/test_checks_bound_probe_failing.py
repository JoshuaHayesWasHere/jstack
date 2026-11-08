"""A throwaway test for sa-checks-bound-rounds: head 12 of 14 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 12


def test_head_12() -> None:
    assert HEAD == 12
