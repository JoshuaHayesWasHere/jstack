"""A throwaway test for sa-checks-bound-rounds-4: head 7 of 12 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 7


def test_head_7() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
