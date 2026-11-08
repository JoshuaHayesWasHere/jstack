"""A throwaway test for sa-checks-bound-rounds: head 14 of 14 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 14


def test_head_14() -> None:
    assert HEAD == 14
