"""A throwaway test for sa-checks-bound-rounds-2: head 7 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 7


def test_head_7() -> None:
    assert HEAD == 7
