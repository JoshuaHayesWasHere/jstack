"""A throwaway test for sa-checks-bound-rounds-2: head 21 of 21 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 21


def test_head_21() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "fails on purpose"
