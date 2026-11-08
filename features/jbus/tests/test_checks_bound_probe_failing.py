"""A throwaway test for sa-checks-bound-rounds: head 6 of 14 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 6


def test_head_6() -> None:
    assert HEAD == 6
