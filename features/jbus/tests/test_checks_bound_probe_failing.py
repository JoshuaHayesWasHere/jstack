"""A throwaway test for sa-checks-bound-rounds-2: head 1 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 1


def test_head_1() -> None:
    assert HEAD == 1
