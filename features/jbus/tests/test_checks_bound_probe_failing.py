"""A throwaway test for sa-checks-bound-rounds-2: head 19 of 21 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 19


def test_head_19() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
