"""A throwaway test for sa-checks-bound-rounds-3: head 9 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 9


def test_head_9() -> None:
    assert HEAD == 9
