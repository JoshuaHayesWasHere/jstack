"""A throwaway test for sa-checks-bound-rounds-3: head 10 of 12 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 10


def test_head_10() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
