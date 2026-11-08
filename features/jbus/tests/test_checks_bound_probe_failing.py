"""A throwaway test for sa-checks-bound-rounds: head 3 of 14 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 3


def test_head_3() -> None:
    assert HEAD == 3
