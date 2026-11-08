"""A throwaway test for sa-checks-bound-rounds: head 8 of 14 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 8


def test_head_8() -> None:
    assert HEAD == 8
