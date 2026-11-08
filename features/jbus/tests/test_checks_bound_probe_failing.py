"""A throwaway test for sa-checks-bound-rounds-3: head 5 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 5


def test_head_5() -> None:
    assert HEAD == 5
