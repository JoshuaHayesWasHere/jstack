"""A throwaway test for sa-checks-bound-rounds-2: head 2 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 2


def test_head_2() -> None:
    assert HEAD == 2
