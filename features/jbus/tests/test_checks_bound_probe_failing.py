"""A throwaway test for sa-checks-bound-rounds-2: head 16 of 16 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 16


def test_head_16() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
