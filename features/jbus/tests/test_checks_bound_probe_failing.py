"""A throwaway test for sa-checks-bound-rounds-2: head 4 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 4


def test_head_4() -> None:
    assert HEAD == 4
