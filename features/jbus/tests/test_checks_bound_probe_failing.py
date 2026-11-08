"""A throwaway test for sa-checks-bound-rounds-4: head 3 of 12 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 3


def test_head_3() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
