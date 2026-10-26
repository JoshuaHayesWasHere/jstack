"""A second loopback address for the tests that listen on two. Linux answers on all of
127.0.0.0/8, and macOS's lo0 has only 127.0.0.1 unless an alias is added, so a bind to
127.0.0.2 there fails with "Can't assign requested address"."""

import socket

import pytest

SECOND = "127.0.0.2"


def second() -> str:
    """`SECOND` where this machine can bind it, or a skip of the calling test that says why not."""
    with socket.socket() as probe:
        try:
            probe.bind((SECOND, 0))
        except OSError:
            pytest.skip(
                f"{SECOND} is not an address of this machine: macOS's lo0 has only 127.0.0.1"
                " unless an alias is added"
            )
    return SECOND
