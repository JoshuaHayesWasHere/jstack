"""A throwaway test for sa-checks-bound-rounds-2: head 17 of 21 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 17


def test_head_17() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
