"""A throwaway test for sa-checks-bound-rounds-4: head 0 of 12 passes, so the checks probe times a
passed round. It never merges."""

HEAD = 0


def test_head_0() -> None:
    assert HEAD == 0
