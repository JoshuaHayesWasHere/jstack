"""`loopback.second` gives a test 127.0.0.2 where this machine has that address, and skips the
test with the reason where it does not, as on a stock Mac."""

import errno
import socket

import pytest

from testing import loopback


def test_it_gives_the_second_address_where_a_bind_to_it_succeeds(monkeypatch):
    monkeypatch.setattr(socket.socket, "bind", lambda self, address: None)
    assert loopback.second() == "127.0.0.2"


def test_it_skips_with_the_reason_where_a_bind_to_it_fails(monkeypatch):
    def refused(self, address):
        raise OSError(errno.EADDRNOTAVAIL, "Can't assign requested address")

    monkeypatch.setattr(socket.socket, "bind", refused)
    with pytest.raises(pytest.skip.Exception) as skipped:
        loopback.second()
    assert str(skipped.value) == (
        "127.0.0.2 is not an address of this machine: macOS's lo0 has only 127.0.0.1"
        " unless an alias is added"
    )
