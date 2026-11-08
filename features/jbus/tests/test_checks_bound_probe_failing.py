"""A throwaway test for sa-checks-bound-rounds-3: head 3 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 3


def test_head_3() -> None:
    assert HEAD == 3
