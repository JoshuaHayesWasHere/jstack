"""Every HTTP server jbus defines binds without the reverse DNS lookup that stalls on a Mac (#425):
each is built while `socket.getfqdn` fails, and must bind and name itself by its address."""

from __future__ import annotations

import http.server
import importlib
import pkgutil
import socket

import pytest

import jbus


def _servers() -> list[type[http.server.HTTPServer]]:
    for module in pkgutil.walk_packages(jbus.__path__, "jbus."):
        if not module.name.endswith(".__main__"):
            importlib.import_module(module.name)
    found, todo = [], [http.server.HTTPServer]
    while todo:
        for one in todo.pop().__subclasses__():
            todo.append(one)
            if one.__module__.startswith("jbus."):
                found.append(one)
    return sorted(found, key=lambda one: f"{one.__module__}.{one.__qualname__}")


SERVERS = _servers()


def test_the_three_servers_are_found():
    names = {f"{one.__module__}.{one.__qualname__}" for one in SERVERS}
    assert {"jbus.t3.Listener", "jbus.relay.Server", "jbus.view.Door"} <= names


@pytest.mark.parametrize("server", SERVERS, ids=lambda one: f"{one.__module__}.{one.__qualname__}")
def test_a_jbus_server_binds_without_asking_dns_for_a_name(server, monkeypatch):
    def getfqdn(name: str = "") -> str:
        raise AssertionError(f"{server.__qualname__} asked DNS for a name of {name!r}")

    monkeypatch.setattr(socket, "getfqdn", getfqdn)
    host = "::1" if server.address_family == socket.AF_INET6 else "127.0.0.1"
    try:
        listener = server((host, 0), http.server.BaseHTTPRequestHandler)
    except OSError as error:
        pytest.skip(f"{host} cannot be bound here: {error}")
    try:
        assert listener.server_name == host
        assert listener.server_port == listener.server_address[1] > 0
    finally:
        listener.server_close()
