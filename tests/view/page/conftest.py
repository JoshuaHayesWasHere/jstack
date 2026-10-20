"""The fixtures of the page's tests: one browser at a time, and a browser to open the page in."""

import os

import pytest

from view.page.browser import CHROMIUM, NAMED, heavy


@pytest.fixture(autouse=True)
def one_browser_at_a_time(request):
    """The browser lock, held for the whole test: one wait for it, whatever it browses. A test
    with a home of its own starts no real browser and takes its own lock."""
    if "own_home" in request.fixturenames:
        yield
        return
    with heavy():
        yield


@pytest.fixture(autouse=True)
def a_browser():
    """With no browser a desk skips the test, and a runner fails it. A browser named in
    `JSTACK_TEST_BROWSER` that is not there fails it anywhere."""
    if NAMED and not CHROMIUM:
        pytest.fail(f"JSTACK_TEST_BROWSER is {NAMED}, which is no program to open the page in")
    if CHROMIUM:
        return
    if os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail("no chromium on PATH to open the page in, and a runner skips no browser test")
    pytest.skip("no chromium on PATH to open the page in")
