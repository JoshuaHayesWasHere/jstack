"""A throwaway test for sa-checks-bound-rounds: head 1 of 12 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 1


def test_head_1() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "head 1 of sa-checks-bound-rounds fails on purpose"
