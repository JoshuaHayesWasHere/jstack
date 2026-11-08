"""A throwaway test for sa-checks-bound-rounds: head 11 of 14 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 11


def test_head_11() -> None:
    assert HEAD == 11
