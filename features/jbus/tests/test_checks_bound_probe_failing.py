"""A throwaway test for sa-checks-bound-rounds: head 10 of 14 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 10


def test_head_10() -> None:
    assert HEAD == 10
