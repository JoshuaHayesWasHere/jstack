"""A throwaway test for sa-checks-bound-rounds: head 9 of 14 fails on GitHub Actions on purpose,
so the checks probe times a failed round. It never merges."""

import os

HEAD = 9


def test_head_9() -> None:
    assert not os.environ.get("GITHUB_ACTIONS"), "head 9 of sa-checks-bound-rounds fails on purpose"
