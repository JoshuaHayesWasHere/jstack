"""`NoLookup`: the one `server_bind` jbus's HTTP servers share, which skips the reverse DNS lookup.

`http.server.HTTPServer.server_bind` calls `socket.getfqdn` on the address before it listens,
and on a Mac that reverse lookup of 127.0.0.1 can wait on mDNS for longer than a server may take
to start (#425). A server class puts `NoLookup` before its `HTTPServer` base, and binds with
the address as its name.
"""

from __future__ import annotations

import socketserver


class NoLookup:
    """A mixin for an `http.server.HTTPServer` that binds without asking DNS for a name."""

    server_address: tuple
    server_name: str
    server_port: int

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)  # type: ignore[arg-type]
        self.server_name, self.server_port = self.server_address[:2]
