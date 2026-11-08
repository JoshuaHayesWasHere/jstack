"""A throwaway test for sa-checks-bound-rounds: head 2 of 13 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 2


def test_head_2() -> None:
    assert HEAD == 2
