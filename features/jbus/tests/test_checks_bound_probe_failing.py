"""A throwaway test for sa-checks-bound-rounds-2: head 9 of 12 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 9


def test_head_9() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
