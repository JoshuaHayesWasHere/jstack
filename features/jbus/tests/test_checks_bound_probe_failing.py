"""A throwaway test for sa-checks-bound-rounds-2: head 13 of 16 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 13


def test_head_13() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
