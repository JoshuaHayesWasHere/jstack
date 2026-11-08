"""A throwaway test for sa-checks-bound-rounds: head 5 of 14 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 5


def test_head_5() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "head 5 of sa-checks-bound-rounds fails on purpose"
