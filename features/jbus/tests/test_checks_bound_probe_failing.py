"""A throwaway test for sa-checks-bound-rounds-2: head 6 of 12 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 6


def test_head_6() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
