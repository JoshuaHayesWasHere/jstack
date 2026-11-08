"""A throwaway test for sa-checks-bound-rounds: head 7 of 14 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 7


def test_head_7() -> None:
    assert HEAD == 7
