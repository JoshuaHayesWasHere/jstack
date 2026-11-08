"""A throwaway test for sa-checks-bound-rounds-3: head 13 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 13


def test_head_13() -> None:
    assert HEAD == 13
